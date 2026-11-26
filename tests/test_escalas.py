"""Testes das regras de escala com um Firestore falso em memória."""
from datetime import datetime, timedelta

import app as app_module
from conflitos import conflitos_da_escala, periodo_da_missa
from tests.helpers import Cenario, TRADICIONAL, proxima_data

JARRA = 'Jarra'
MISSAL = 'Acólito (Missal)'


# ---------------------------------------------------------------- restrições de data
def test_restricao_dia_todo_nao_escala():
    c = Cenario()
    acolitos, coroinhas = c.elenco()
    quando = proxima_data(6, hora=9)
    missa = c.missa(quando)
    c.restricao(coroinhas[0], quando, 'Dia Todo')

    c.gerar()

    escalados = c.ids_escalados(missa)
    assert coroinhas[0] not in escalados
    assert acolitos[0] in escalados
    assert len(escalados) == 5  # 1 acólito + 4 coroinhas: a vaga restante fica em aberto


def test_restricao_do_periodo_da_missa_bloqueia_e_de_outro_periodo_nao():
    for hora, bloqueia, nao_bloqueia in [(9, 'Manhã', 'Tarde'), (15, 'Tarde', 'Noite'), (19, 'Noite', 'Manhã')]:
        # período igual ao da missa: bloqueia
        c = Cenario()
        _, coroinhas = c.elenco()
        quando = proxima_data(6, hora=hora)
        missa = c.missa(quando)
        c.restricao(coroinhas[0], quando, bloqueia)
        c.gerar()
        assert coroinhas[0] not in c.ids_escalados(missa), f'{bloqueia} deveria bloquear missa das {hora}h'

        # período diferente: não bloqueia (elenco exato, então todos precisam ser escalados)
        c = Cenario()
        _, coroinhas = c.elenco()
        missa = c.missa(quando)
        c.restricao(coroinhas[0], quando, nao_bloqueia)
        c.gerar()
        assert coroinhas[0] in c.ids_escalados(missa), f'{nao_bloqueia} não deveria bloquear missa das {hora}h'


def test_restricao_de_outro_dia_nao_bloqueia():
    c = Cenario()
    _, coroinhas = c.elenco()
    quando = proxima_data(6, hora=9)
    missa = c.missa(quando)
    c.restricao(coroinhas[0], quando + timedelta(days=7), 'Dia Todo')
    c.gerar()
    assert coroinhas[0] in c.ids_escalados(missa)


def test_limites_dos_periodos():
    d = datetime(2026, 12, 6)
    assert periodo_da_missa(d.replace(hour=11, minute=59)) == 'Manhã'
    assert periodo_da_missa(d.replace(hour=12)) == 'Tarde'
    assert periodo_da_missa(d.replace(hour=17, minute=59)) == 'Tarde'
    assert periodo_da_missa(d.replace(hour=18)) == 'Noite'


# ---------------------------------------------------------------- restrição de função
def test_funcao_proibida_nao_e_atribuida():
    c = Cenario()
    _, coroinhas = c.elenco()
    missa = c.missa(proxima_data(6))
    c.restricao_funcao(coroinhas[1], JARRA)
    c.gerar()
    escalas = c.escalas_da_missa(missa)
    assert escalas.get(JARRA) != coroinhas[1]
    assert coroinhas[1] in escalas.values()  # ainda é escalado, só que em outra função
    assert len(escalas) == 6


def test_grau_incompativel_nao_e_escalado():
    c = Cenario()
    # só coroinhas comuns: a função de Acólito não pode ser preenchida
    c.elenco(acolitos=0, coroinhas=5)
    missa = c.missa(proxima_data(6))
    c.gerar()
    assert MISSAL not in c.escalas_da_missa(missa)


# ---------------------------------------------------------------- editar missa
def _missa_escalada(c, quando, **kw):
    acolitos, coroinhas = c.elenco()
    ajudante = c.ajudante('Ajudante A')
    missa = c.missa_completa(quando, acolitos + coroinhas, ajudante_id=ajudante, **kw)
    return missa, ajudante


def _editar(c, client, missa, quando, tipo='Tradicional', descricao='Missa'):
    return c.post(client, f'/missa/editar/{missa}', descricao=descricao, tipo_missa=tipo,
                  data_hora=quando.strftime('%Y-%m-%dT%H:%M'))


def test_editar_data_remove_escalas_antigas():
    c = Cenario()
    quando = proxima_data(6)
    missa, _ = _missa_escalada(c, quando)
    client = c.cliente()

    resposta = _editar(c, client, missa, quando + timedelta(days=14))

    assert resposta.status_code == 302
    assert c.escalas_da_missa(missa) == {}
    assert c.escalas_ajudantes_da_missa(missa) == []
    assert not c.ajudante_da_missa(missa)
    assert any('Gerar / Corrigir' in texto for texto in c.flashes(client))
    nova = c.fs.docs('missas')[missa]['data_hora'].replace(tzinfo=None)
    assert nova.date() == (quando + timedelta(days=14)).date()


def test_editar_tipo_remove_escalas_antigas():
    c = Cenario()
    quando = proxima_data(6)
    missa, _ = _missa_escalada(c, quando)
    client = c.cliente()
    _editar(c, client, missa, quando, tipo='Solene')
    assert c.escalas_da_missa(missa) == {}
    assert c.fs.docs('missas')[missa]['tipo_missa'] == 'Solene'


def test_editar_so_descricao_mantem_escala():
    c = Cenario()
    quando = proxima_data(6)
    missa, ajudante = _missa_escalada(c, quando)
    antes = c.ids_das_escalas(missa)
    client = c.cliente()

    _editar(c, client, missa, quando, descricao='Missa renomeada')

    assert c.ids_das_escalas(missa) == antes
    assert c.ajudante_da_missa(missa) == ajudante
    assert c.fs.docs('missas')[missa]['descricao'] == 'Missa renomeada'
    assert c.flashes(client) == []


# ---------------------------------------------------------------- gerar corrige conflitos
def test_gerar_remove_escalado_com_restricao_nova_e_preenche_com_outra_pessoa():
    c = Cenario()
    acolitos, coroinhas = c.elenco(coroinhas=6)  # c5 é reserva
    quando = proxima_data(6)
    titulares = acolitos + coroinhas[:5]
    missa = c.missa_completa(quando, titulares)
    antes = c.escalas_da_missa(missa)
    ids_antes = c.ids_das_escalas(missa)
    c.restricao(coroinhas[2], quando, 'Dia Todo')  # restrição cadastrada DEPOIS da escala

    resultado = c.gerar()

    depois = c.escalas_da_missa(missa)
    assert coroinhas[2] not in depois.values()
    assert depois[JARRA] != coroinhas[2]
    assert coroinhas[5] in depois.values()  # a reserva ocupou a vaga
    assert len(depois) == 6
    assert resultado['removidos'] == 1 and resultado['preenchidos'] == 1
    # o restante da escala continua intacto (mesmos registros)
    assert len(c.ids_das_escalas(missa) & ids_antes) == 5


def test_gerar_remove_funcao_que_nao_existe_no_tipo_atual():
    c = Cenario()
    acolitos, coroinhas = c.elenco()
    missa = c.missa(proxima_data(6), tipo='Tradicional')
    c.escala(missa, coroinhas[0], 'Acólito (Mitra)')  # só existe no molde Bispo
    c.gerar()
    assert 'Acólito (Mitra)' not in c.escalas_da_missa(missa)


def test_gerar_sem_conflitos_nao_altera_escala_existente():
    c = Cenario()
    acolitos, coroinhas = c.elenco()
    missa = c.missa_completa(proxima_data(6), acolitos + coroinhas)
    antes = c.fs.docs('escalas')
    c.gerar()
    assert c.fs.docs('escalas') == antes


# ---------------------------------------------------------------- fim de semana
def test_mesma_pessoa_nao_e_escalada_duas_vezes_no_fim_de_semana():
    c = Cenario()
    c.elenco(acolitos=2, coroinhas=10)
    sabado = proxima_data(5, hora=18)
    domingo = (sabado + timedelta(days=1)).replace(hour=9)
    m1, m2 = c.missa(sabado), c.missa(domingo)
    c.gerar()
    e1, e2 = c.ids_escalados(m1), c.ids_escalados(m2)
    assert len(e1) == 6 and len(e2) == 6
    assert not (e1 & e2)


def test_elenco_curto_deixa_vagas_em_aberto_em_vez_de_repetir_pessoa():
    c = Cenario()
    c.elenco(acolitos=1, coroinhas=5)
    sabado = proxima_data(5, hora=18)
    domingo = (sabado + timedelta(days=1)).replace(hour=9)
    m1, m2 = c.missa(sabado), c.missa(domingo)
    c.gerar()
    assert len(c.ids_escalados(m1)) == 6
    assert c.ids_escalados(m2) == set()
    assert not c.ajudante_da_missa(m2)


def test_durante_a_semana_nao_ha_limite():
    c = Cenario()
    c.elenco()
    quarta = proxima_data(2)
    m1, m2 = c.missa(quarta), c.missa(quarta + timedelta(days=1))
    c.gerar()
    assert len(c.ids_escalados(m1)) == 6 and len(c.ids_escalados(m2)) == 6


# ---------------------------------------------------------------- missas passadas
def test_missas_passadas_nao_sao_alteradas():
    c = Cenario()
    acolitos, coroinhas = c.elenco(coroinhas=6)
    passada = datetime.now() - timedelta(days=30)
    vazia = c.missa(passada, descricao='Passada vazia')
    escalada = c.missa_completa(passada - timedelta(days=7), acolitos + coroinhas[:5])
    c.restricao(coroinhas[0], passada - timedelta(days=7))  # conflito numa missa que já aconteceu
    antes = (c.fs.docs('escalas'), c.fs.docs('missas'))

    resultado = c.gerar()

    assert (c.fs.docs('escalas'), c.fs.docs('missas')) == antes
    assert c.escalas_da_missa(vazia) == {}
    assert resultado == {'removidos': 0, 'preenchidos': 0, 'ajudantes_removidos': 0, 'ajudantes_preenchidos': 0}


# ---------------------------------------------------------------- ajudantes
def test_ajudante_com_restricao_nao_e_escolhido():
    c = Cenario()
    c.elenco()
    quando = proxima_data(6)
    missa = c.missa(quando)
    impedido = c.ajudante('Impedido')
    livre = c.ajudante('Livre')
    c.restricao_ajudante(impedido, quando, 'Dia Todo')
    c.gerar()
    assert c.ajudante_da_missa(missa) == livre


def test_gerar_troca_ajudante_que_ganhou_restricao():
    c = Cenario()
    acolitos, coroinhas = c.elenco()
    quando = proxima_data(6)
    a, b = c.ajudante('A'), c.ajudante('B')
    missa = c.missa_completa(quando, acolitos + coroinhas, ajudante_id=a)
    c.restricao_ajudante(a, quando, 'Manhã')

    resultado = c.gerar()

    assert c.ajudante_da_missa(missa) == b
    vinculos = c.escalas_ajudantes_da_missa(missa)
    assert [str(v['ajudante_id']) for v in vinculos] == [b]
    assert resultado['ajudantes_removidos'] == 1 and resultado['ajudantes_preenchidos'] == 1


def test_ajudante_sem_alternativa_fica_em_aberto():
    c = Cenario()
    acolitos, coroinhas = c.elenco()
    quando = proxima_data(6)
    a = c.ajudante('Único')
    missa = c.missa_completa(quando, acolitos + coroinhas, ajudante_id=a)
    c.restricao_ajudante(a, quando, 'Dia Todo')
    c.gerar()
    assert not c.ajudante_da_missa(missa)
    assert c.escalas_ajudantes_da_missa(missa) == []


# ---------------------------------------------------------------- IDs mistos (dados migrados do SQLite)
def test_ids_inteiros_e_texto_sao_comparados_como_texto():
    c = Cenario()
    # documentos com ID '7' e '3', mas referências gravadas como INTEIROS, como na migração
    coroinha = c.coroinha('Migrado', id=7)
    reserva = c.coroinha('Reserva', id=8)
    quando = proxima_data(6)
    missa = c.missa(quando, id=3)
    c.escala(3, 7, JARRA)  # missa_id e coroinha_id inteiros
    c.restricao(7, quando, 'Dia Todo')  # coroinha_id inteiro

    c.gerar()

    assert c.escalas_da_missa(missa).get(JARRA) != coroinha
    assert coroinha not in c.ids_escalados(missa)
    assert reserva in c.ids_escalados(missa)


def test_conflitos_da_escala_motivos():
    c = Cenario()
    quando = proxima_data(6, hora=9)
    comum = c.coroinha('Comum')
    c.missa(quando, id='m1')
    c.restricao(comum, quando, 'Dia Todo')
    c.restricao_funcao(comum, JARRA)
    repo = c.repo
    missa = repo.get('Missa', 'm1')
    molde = app_module.MOLDES_LITURGICOS['Tradicional']
    coroinha = repo.get('Coroinha', comum)
    r_data, r_funcao = repo.all('Restricao'), repo.all('RestricaoFuncao')

    class E:  # escala mínima
        def __init__(self, funcao): self.funcao_atribuida = funcao

    motivos = conflitos_da_escala(E(JARRA), missa, coroinha, molde, r_data, r_funcao)
    assert f'restrição Dia Todo em {quando:%d/%m}' in motivos
    assert 'função proibida' in motivos
    assert any('grau incompatível' in m for m in conflitos_da_escala(E(MISSAL), missa, coroinha, molde, r_data, r_funcao))
    assert conflitos_da_escala(E('Acólito (Mitra)'), missa, coroinha, molde, r_data, r_funcao) == ['função não existe neste tipo de missa']
    assert conflitos_da_escala(E(JARRA), missa, None, molde, r_data, r_funcao) == ['coroinha não encontrado']


# ---------------------------------------------------------------- regerar
def test_regerar_so_mexe_na_missa_escolhida():
    c = Cenario()
    acolitos, coroinhas = c.elenco()
    quarta = proxima_data(2)
    alvo = c.missa_completa(quarta, acolitos + coroinhas)
    outra = c.missa_completa(quarta + timedelta(days=1), acolitos + coroinhas)
    ids_outra = c.ids_das_escalas(outra)
    ids_alvo = c.ids_das_escalas(alvo)
    client = c.cliente()

    resposta = c.post(client, f'/escala/regerar/{alvo}')

    assert resposta.status_code == 302
    assert c.ids_das_escalas(outra) == ids_outra         # intacta
    assert not (c.ids_das_escalas(alvo) & ids_alvo)       # registros novos
    assert len(c.ids_escalados(alvo)) == 6                # e completa de novo


def test_regerar_respeita_limite_do_fim_de_semana():
    c = Cenario()
    acolitos, coroinhas = c.elenco()
    sabado = proxima_data(5, hora=18)
    domingo = (sabado + timedelta(days=1)).replace(hour=9)
    m_sab = c.missa_completa(sabado, acolitos + coroinhas)
    m_dom = c.missa(domingo)
    client = c.cliente()

    c.post(client, f'/escala/regerar/{m_dom}')

    assert c.ids_escalados(m_dom) == set()          # todos já estão no sábado
    assert len(c.ids_escalados(m_sab)) == 6


def test_regerar_missa_passada_e_recusado():
    c = Cenario()
    acolitos, coroinhas = c.elenco()
    passada = c.missa_completa(datetime.now() - timedelta(days=10), acolitos + coroinhas)
    antes = c.ids_das_escalas(passada)
    client = c.cliente()
    resposta = c.post(client, f'/escala/regerar/{passada}')
    assert resposta.status_code == 400
    assert c.ids_das_escalas(passada) == antes


# ---------------------------------------------------------------- telas
def test_tela_de_escalas_mostra_conflitos_e_gerar_resolve():
    c = Cenario()
    acolitos, coroinhas = c.elenco(coroinhas=6)
    quando = proxima_data(6)
    missa = c.missa_completa(quando, acolitos + coroinhas[:5], descricao='Missa de teste')
    c.restricao(coroinhas[2], quando, 'Dia Todo')
    client = c.cliente()

    pagina = client.get('/escalas').get_data(as_text=True)
    assert '1 conflito(s) nas missas futuras' in pagina
    assert f'restrição Dia Todo em {quando:%d/%m}' in pagina

    resposta = c.post(client, '/escala/gerar')
    assert resposta.status_code == 302
    assert any('removido' in texto for texto in c.flashes(client))

    pagina = client.get('/escalas').get_data(as_text=True)
    assert 'conflito(s) nas missas futuras' not in pagina
    assert coroinhas[2] not in c.ids_escalados(missa)


def test_tela_de_escalas_sem_conflito_nao_mostra_aviso():
    c = Cenario()
    acolitos, coroinhas = c.elenco()
    c.missa_completa(proxima_data(6), acolitos + coroinhas)
    pagina = c.cliente().get('/escalas').get_data(as_text=True)
    assert 'conflito(s)' not in pagina


def test_restricao_com_data_suspeita_avisa_mas_cadastra():
    c = Cenario()
    coroinha = c.coroinha('Fulano')
    client = c.cliente()
    ontem = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')

    resposta = c.post(client, f'/coroinha/{coroinha}/restricao_data/nova', data_exata=ontem, periodo='Dia Todo')

    assert resposta.status_code == 302
    assert len(c.fs.docs('restricoes')) == 1
    assert any('já passou' in texto for texto in c.flashes(client))
