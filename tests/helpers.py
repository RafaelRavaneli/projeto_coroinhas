import itertools
import random
from datetime import datetime, timedelta, timezone

import app as app_module
from firestore_repository import FirestoreRepository
from tests.fake_firestore import FakeFirestore

TRADICIONAL = [
    'Acólito (Missal)', 'Cruciferário (Cruz)', 'Ceriferário (Vela 1)',
    'Ceriferário (Vela 2)', 'Jarra', 'Bacia/Lavabo',
]


def proxima_data(weekday, hora=9, semanas=3):
    """Data futura (daqui a ~3 semanas) no dia da semana pedido (0=segunda ... 6=domingo)."""
    base = datetime.now().replace(hour=hora, minute=0, second=0, microsecond=0) + timedelta(weeks=semanas)
    return base + timedelta(days=(weekday - base.weekday()) % 7)


class Cenario:
    """Banco falso + app apontando para ele. Cada teste cria o seu."""

    def __init__(self):
        random.seed(7)
        self.fs = FakeFirestore()
        self.repo = FirestoreRepository(client_factory=lambda: self.fs)
        app_module.store = self.repo
        app_module.app.config.update(TESTING=True, APP_USERNAME='coord', APP_PASSWORD_HASH='x')
        self._ids = itertools.count(1)

    # ---------- criação de dados (formato igual ao de produção) ----------
    def _id(self, id):
        return str(id) if id is not None else f'd{next(self._ids)}'

    def coroinha(self, nome, tipo='Coroinha', ativo=True, id=None, telefone=None):
        id = self._id(id)
        self.fs.seed('coroinhas', id, {
            'id': id, 'nome': nome, 'tipo': tipo, 'ativo': ativo,
            'responsavel_nome': f'Resp {nome}', 'responsavel_telefone': telefone or f'4499{id:0>6}'[:11],
        })
        return id

    def elenco(self, acolitos=1, coroinhas=5, prefixo='J'):
        ac = [self.coroinha(f'{prefixo}A{i}', 'Acólito') for i in range(acolitos)]
        co = [self.coroinha(f'{prefixo}C{i}', 'Coroinha') for i in range(coroinhas)]
        return ac, co

    def missa(self, quando, tipo='Tradicional', descricao='Missa', id=None, ajudante_id=None):
        id = self._id(id)
        data = {'id': id, 'descricao': descricao, 'tipo_missa': tipo,
                'data_hora': quando.replace(tzinfo=timezone.utc)}  # Firestore devolve com fuso
        if ajudante_id is not None:
            data['ajudante_id'] = ajudante_id
        self.fs.seed('missas', id, data)
        return id

    def escala(self, missa_id, coroinha_id, funcao, id=None):
        id = self._id(id)
        self.fs.seed('escalas', id, {'id': id, 'missa_id': missa_id, 'coroinha_id': coroinha_id,
                                      'funcao_atribuida': funcao, 'status': 'Confirmado'})
        return id

    def restricao(self, coroinha_id, quando, periodo='Dia Todo', horario=None):
        id = self._id(None)
        dados = {'id': id, 'coroinha_id': coroinha_id, 'data_exata': quando.date().isoformat(), 'periodo': periodo}
        if horario:
            dados['horario'] = horario
        self.fs.seed('restricoes', id, dados)
        return id

    def restricao_funcao(self, coroinha_id, funcao):
        id = self._id(None)
        self.fs.seed('restricoes_funcoes', id, {'id': id, 'coroinha_id': coroinha_id, 'funcao_proibida': funcao})
        return id

    def ajudante(self, nome, ativo=True, filhos=(), id=None):
        id = self._id(id)
        self.fs.seed('ajudantes', id, {'id': id, 'nome': nome, 'telefone': '44999999999', 'ativo': ativo,
                                        'coroinhas_vinculados_ids': list(filhos)})
        return id

    def restricao_ajudante(self, ajudante_id, quando, periodo='Dia Todo', horario=None):
        id = self._id(None)
        dados = {'id': id, 'ajudante_id': ajudante_id, 'data_exata': quando.date().isoformat(), 'periodo': periodo}
        if horario:
            dados['horario'] = horario
        self.fs.seed('restricoes_ajudantes', id, dados)
        return id

    def escala_ajudante(self, missa_id, ajudante_id):
        id = self._id(None)
        self.fs.seed('escalas_ajudantes', id, {'id': id, 'missa_id': missa_id, 'ajudante_id': ajudante_id})
        return id

    def missa_completa(self, quando, escalados, tipo='Tradicional', ajudante_id=None, **kw):
        """Missa já escalada. `escalados` = lista de ids na ordem das funções do molde."""
        missa = self.missa(quando, tipo=tipo, ajudante_id=ajudante_id, **kw)
        funcoes = [i['funcao'] for i in app_module.MOLDES_LITURGICOS[tipo]]
        for coroinha_id, funcao in zip(escalados, funcoes):
            self.escala(missa, coroinha_id, funcao)
        if ajudante_id is not None:
            self.escala_ajudante(missa, ajudante_id)
        return missa

    # ---------- leitura ----------
    def escalas_da_missa(self, missa_id):
        return {d['funcao_atribuida']: str(d['coroinha_id'])
                for d in self.fs.docs('escalas').values() if str(d['missa_id']) == str(missa_id)}

    def ids_escalados(self, missa_id):
        return set(self.escalas_da_missa(missa_id).values())

    def ids_das_escalas(self, missa_id):
        return {i for i, d in self.fs.docs('escalas').items() if str(d['missa_id']) == str(missa_id)}

    def ajudante_da_missa(self, missa_id):
        return self.fs.docs('missas')[str(missa_id)].get('ajudante_id')

    def escalas_ajudantes_da_missa(self, missa_id):
        return [d for d in self.fs.docs('escalas_ajudantes').values() if str(d['missa_id']) == str(missa_id)]

    # ---------- ações ----------
    def gerar(self, **kw):
        return app_module.preencher_escalas_pendentes(**kw)

    def cliente(self):
        client = app_module.app.test_client()
        with client.session_transaction() as sess:
            sess['authenticated'] = True
            sess['_csrf_token'] = 'tok'
        return client

    def post(self, client, url, **dados):
        dados['_csrf_token'] = 'tok'
        return client.post(url, data=dados)

    @staticmethod
    def flashes(client):
        with client.session_transaction() as sess:
            return [texto for _categoria, texto in sess.get('_flashes', [])]
