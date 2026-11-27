"""Firestore falso em memória, com a mesma interface que FirestoreRepository usa.

Mantém a comparação EXATA de tipos nos filtros (como o Firestore real):
o inteiro 5 não é igual ao texto '5'. Isso reproduz os IDs mistos dos dados
migrados do SQLite.
"""
import copy
import itertools


class FakeSnapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self.exists = data is not None
        self._data = data

    def to_dict(self):
        return copy.deepcopy(self._data)


class FakeDocumentRef:
    def __init__(self, collection, doc_id):
        self._collection = collection
        self.id = doc_id

    def set(self, data):
        self._collection.docs[self.id] = copy.deepcopy(data)
        self._collection.client.writes += 1

    def get(self):
        self._collection.client.reads += 1
        return FakeSnapshot(self.id, self._collection.docs.get(self.id))

    def update(self, values):
        self._collection.docs[self.id].update(copy.deepcopy(values))
        self._collection.client.writes += 1

    def delete(self):
        self._collection.docs.pop(self.id, None)
        self._collection.client.writes += 1


class FakeQuery:
    def __init__(self, collection, filters):
        self._collection = collection
        self._filters = filters

    def where(self, field, op, value):
        assert op == '=='
        return FakeQuery(self._collection, self._filters + [(field, value)])

    def stream(self):
        self._collection.client.reads += 1
        return [
            FakeSnapshot(doc_id, data)
            for doc_id, data in list(self._collection.docs.items())
            if all(data.get(field) == value and type(data.get(field)) is type(value) for field, value in self._filters)
        ]


class FakeCollection(FakeQuery):
    def __init__(self, client, name):
        self.client = client
        self.name = name
        self.docs = {}
        super().__init__(self, [])

    def document(self, doc_id=None):
        return FakeDocumentRef(self, doc_id or f'auto{next(self.client._ids)}')


class FakeFirestore:
    def __init__(self):
        self._collections = {}
        self._ids = itertools.count(1)
        self.reads = 0
        self.writes = 0

    def collection(self, name):
        if name not in self._collections:
            self._collections[name] = FakeCollection(self, name)
        return self._collections[name]

    def seed(self, name, doc_id, data):
        """Grava um documento direto, sem contar como escrita do app."""
        self.collection(name).docs[str(doc_id)] = copy.deepcopy(data)

    def docs(self, name):
        return dict(self.collection(name).docs)
