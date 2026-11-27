"""Regras de conflito de escala, sem dependência de Flask ou Firestore.

Este módulo é a ÚNICA fonte da regra. O gerador de escalas, a tela de escalas
e a edição de missas usam estas funções, para que as regras não divirjam.

Os IDs vêm misturados nos dados migrados do SQLite (inteiros em campos como
coroinha_id e missa_id, texto em Document.id); por isso toda comparação de ID
usa str(...).
"""


def periodo_da_missa(data_hora):
    """Manhã antes das 12h, Tarde antes das 18h, senão Noite."""
    hora = data_hora.hour
    if hora < 12:
        return 'Manhã'
    if hora < 18:
        return 'Tarde'
    return 'Noite'


HORARIO_ESPECIFICO = 'Horário'


def horario_da_restricao(restricao):
    """Horário 'HH:MM' de uma restrição do tipo Horário; None nas demais."""
    return getattr(restricao, 'horario', None)


def descricao_restricao(restricao):
    """Texto curto do período: 'Dia Todo', 'Manhã'... ou 'às 08h00'."""
    if restricao.periodo == HORARIO_ESPECIFICO:
        horario = horario_da_restricao(restricao) or '?'
        return 'às ' + horario.replace(':', 'h')
    return restricao.periodo


def restricao_de_data_bloqueia(restricao, data_hora):
    """True se a restrição (data exata + período ou horário exato) cobre a missa.

    Horário específico bloqueia só a missa que começa naquele horário, no dia;
    as outras missas do mesmo período continuam liberadas (ex.: não pode às
    8h, mas pode às 10h).
    """
    if restricao.data_exata != data_hora.date():
        return False
    if restricao.periodo == HORARIO_ESPECIFICO:
        return horario_da_restricao(restricao) == data_hora.strftime('%H:%M')
    return restricao.periodo in (periodo_da_missa(data_hora), 'Dia Todo')


def exigencia_da_funcao(molde, funcao):
    """Grau exigido pela função no molde da missa; None se a função não existe nele."""
    for item in molde:
        if item['funcao'] == funcao:
            return item['exigencia']
    return None


def motivos_conflito_coroinha(coroinha, missa, funcao, molde, restricoes_data, restricoes_funcao):
    """Motivos pelos quais o coroinha não pode exercer `funcao` nesta missa.

    Lista vazia significa que não há conflito. Usada tanto para filtrar
    candidatos no gerador quanto para validar quem já está escalado.
    """
    exigencia = exigencia_da_funcao(molde, funcao)
    if exigencia is None:
        return ['função não existe neste tipo de missa']

    motivos = []
    if coroinha.tipo != exigencia:
        motivos.append(f'grau incompatível (a função exige {exigencia})')

    coroinha_id = str(coroinha.id)
    for restricao in restricoes_data:
        if str(restricao.coroinha_id) == coroinha_id and restricao_de_data_bloqueia(restricao, missa.data_hora):
            motivos.append(f'restrição {descricao_restricao(restricao)} em {missa.data_hora:%d/%m}')
    for restricao in restricoes_funcao:
        if str(restricao.coroinha_id) == coroinha_id and restricao.funcao_proibida == funcao:
            motivos.append('função proibida')
    return motivos


def conflitos_da_escala(escala, missa, coroinha, molde, restricoes_data, restricoes_funcao):
    """Motivos de conflito de um registro de Escala já existente."""
    if coroinha is None:
        return ['coroinha não encontrado']
    return motivos_conflito_coroinha(
        coroinha, missa, escala.funcao_atribuida, molde, restricoes_data, restricoes_funcao
    )


def motivos_conflito_ajudante(ajudante, missa, restricoes_ajudantes):
    """Motivos pelos quais o ajudante não pode ser o responsável por esta missa."""
    if ajudante is None:
        return ['ajudante não encontrado']
    ajudante_id = str(ajudante.id)
    return [
        f'restrição {descricao_restricao(restricao)} em {missa.data_hora:%d/%m}'
        for restricao in restricoes_ajudantes
        if str(restricao.ajudante_id) == ajudante_id and restricao_de_data_bloqueia(restricao, missa.data_hora)
    ]
