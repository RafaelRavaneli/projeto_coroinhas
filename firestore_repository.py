from datetime import date, datetime

from flask import abort

from firebase_store import get_firestore_client


COLLECTIONS = {
    'Ajudante': 'ajudantes',
    'RestricaoAjudante': 'restricoes_ajudantes',
    'Coroinha': 'coroinhas',
    'Restricao': 'restricoes',
    'RestricaoFuncao': 'restricoes_funcoes',
    'Missa': 'missas',
    'Escala': 'escalas',
    'EscalaAjudante': 'escalas_ajudantes',
}


def as_id(value):
    return str(value) if value is not None else None


def date_value(value):
    if isinstance(value, datetime) and value.tzinfo:
        return value.replace(tzinfo=None)
    return value


class FirestoreRepository:
    def __init__(self, client_factory=get_firestore_client):
        self._client_factory = client_factory
        self._client = None
        self._cache = {}

    def clear_cache(self):
        self._cache.clear()

    @property
    def client(self):
        if self._client is None:
            self._client = self._client_factory()
        return self._client

    def collection(self, model):
        name = COLLECTIONS[model] if model in COLLECTIONS else model
        return self.client.collection(name)

    def all(self, model, **filters):
        cache_key = (model, tuple(sorted(filters.items())))
        if cache_key in self._cache:
            return list(self._cache[cache_key])
        query = self.collection(model)
        for field, value in filters.items():
            query = query.where(field, '==', value)
        snapshots = list(query.stream())
        for field, value in filters.items():
            if field.endswith('_id') and isinstance(value, str) and value.isdecimal():
                snapshots.extend(self.collection(model).where(field, '==', int(value)).stream())
        unique = {snapshot.id: snapshot for snapshot in snapshots}
        records = [Document(self, model, snapshot.id, snapshot.to_dict()) for snapshot in unique.values()]
        self._cache[cache_key] = records
        return list(records)

    def get(self, model, document_id):
        cache_key = (model, as_id(document_id))
        if cache_key in self._cache:
            return self._cache[cache_key]
        snapshot = self.collection(model).document(as_id(document_id)).get()
        if not snapshot.exists:
            return None
        record = Document(self, model, snapshot.id, snapshot.to_dict())
        self._cache[cache_key] = record
        return record

    def get_or_404(self, model, document_id):
        record = self.get(model, document_id)
        if record is None:
            abort(404)
        return record

    def create(self, model, **values):
        document = self.collection(model).document()
        values['id'] = document.id
        document.set(values)
        self.clear_cache()
        return Document(self, model, document.id, values)

    def save(self, record):
        record._data['id'] = record.id
        self.collection(record._model).document(record.id).set(record._data)
        self.clear_cache()

    def update(self, model, document_id, **values):
        document = self.collection(model).document(as_id(document_id))
        if not document.get().exists:
            abort(404)
        document.update(values)
        self.clear_cache()
        return self.get(model, document_id)

    def delete(self, model, document_id):
        record = self.get_or_404(model, document_id)
        if model == 'Coroinha':
            for relation in ('restricoes', 'restricoes_funcoes', 'escalas'):
                for related in self.all(relation, coroinha_id=record.id):
                    self.delete(relation, related.id)
            for ajudante in self.all('Ajudante'):
                linked_ids = [as_id(item) for item in ajudante.coroinhas_vinculados_ids]
                if record.id in linked_ids:
                    self.update('Ajudante', ajudante.id, coroinhas_vinculados_ids=[item for item in linked_ids if item != record.id])
        elif model == 'Ajudante':
            for relation in ('restricoes_ajudantes', 'escalas_ajudantes'):
                for related in self.all(relation, ajudante_id=record.id):
                    self.delete(relation, related.id)
            for missa in self.all('Missa', ajudante_id=record.id):
                self.update('Missa', missa.id, ajudante_id=None)
        elif model == 'Missa':
            for relation in ('Escala', 'EscalaAjudante'):
                for related in self.all(relation, missa_id=record.id):
                    self.delete(relation, related.id)
        self.collection(model).document(record.id).delete()
        self.clear_cache()


class Document:
    def __init__(self, repository, model, document_id, data):
        self._repository = repository
        self._model = model
        self._data = dict(data or {})
        self._data['id'] = document_id

    def __getattr__(self, name):
        if name in self._data:
            value = self._data[name]
            if name == 'data_exata' and isinstance(value, str):
                return date.fromisoformat(value)
            if name == 'data_hora':
                return date_value(value)
            return value
        if name == 'coroinhas_vinculados_ids':
            return []
        if name in {'ajudante_id', 'telefone_jovem', 'responsavel2_nome', 'responsavel2_telefone', 'funcao_atribuida'}:
            return None
        return self._relationship(name)

    def __setattr__(self, name, value):
        if name.startswith('_'):
            object.__setattr__(self, name, value)
        else:
            self._data[name] = value

    def _relationship(self, name):
        repo = self._repository
        if self._model == 'Ajudante':
            if name == 'coroinhas_vinculados':
                linked = [repo.get('Coroinha', item) for item in self.coroinhas_vinculados_ids]
                return [record for record in linked if record]
            if name == 'restricoes':
                return repo.all('RestricaoAjudante', ajudante_id=self.id)
            if name == 'escalas':
                return repo.all('EscalaAjudante', ajudante_id=self.id)
        if self._model == 'Coroinha':
            if name == 'restricoes':
                return repo.all('Restricao', coroinha_id=self.id)
            if name == 'restricoes_funcao':
                return repo.all('RestricaoFuncao', coroinha_id=self.id)
            if name == 'escalas':
                return repo.all('Escala', coroinha_id=self.id)
            if name == 'responsaveis_cadastrados':
                return [item for item in repo.all('Ajudante') if self.id in [as_id(value) for value in item.coroinhas_vinculados_ids]]
        if self._model == 'Missa':
            if name == 'ajudante':
                return repo.get('Ajudante', self.ajudante_id) if self.ajudante_id else None
            if name == 'escalas':
                return repo.all('Escala', missa_id=self.id)
            if name == 'escalas_ajudante':
                return repo.all('EscalaAjudante', missa_id=self.id)
        if self._model == 'Escala':
            if name == 'coroinha':
                return repo.get('Coroinha', self.coroinha_id)
            if name == 'missa':
                return repo.get('Missa', self.missa_id)
        if self._model == 'EscalaAjudante':
            if name == 'ajudante':
                return repo.get('Ajudante', self.ajudante_id)
            if name == 'missa':
                return repo.get('Missa', self.missa_id)
        raise AttributeError(name)

    def save(self):
        self._repository.save(self)

    def __eq__(self, other):
        return isinstance(other, Document) and self._model == other._model and self.id == other.id

    def __hash__(self):
        return hash((self._model, self.id))
