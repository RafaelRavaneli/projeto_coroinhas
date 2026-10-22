import argparse
import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

from firebase_store import get_firestore_client


SOURCE_PATH = Path(__file__).resolve().parent / 'instance' / 'paroquia.db'
COLLECTIONS = ('ajudantes', 'restricoes_ajudantes', 'coroinhas', 'restricoes', 'restricoes_funcoes', 'missas', 'escalas', 'escalas_ajudantes')
MIGRATION_DOCUMENT = ('_migrations', 'sqlite_v1')
MAX_BATCH_WRITES = 450


def serialize(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    return value


def load_snapshot():
    if not SOURCE_PATH.is_file():
        raise FileNotFoundError(f'Banco SQLite não encontrado: {SOURCE_PATH}')

    uri = SOURCE_PATH.as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        specifications = {
            'ajudantes': ('ajudante', 'id, nome, telefone, ativo'),
            'restricoes_ajudantes': ('restricao_ajudante', 'id, data_exata, periodo, ajudante_id'),
            'coroinhas': ('coroinha', 'id, nome, telefone_jovem, tipo, responsavel_nome, responsavel_telefone, responsavel2_nome, responsavel2_telefone, ativo'),
            'restricoes': ('restricao', 'id, data_exata, periodo, coroinha_id'),
            'restricoes_funcoes': ('restricao_funcao', 'id, funcao_proibida, coroinha_id'),
            'missas': ('missa', 'id, descricao, data_hora, tipo_missa, ajudante_id'),
            'escalas': ('escala', 'id, coroinha_id, missa_id, funcao_atribuida, status'),
            'escalas_ajudantes': ('escala_ajudante', 'id, ajudante_id, missa_id'),
        }
        snapshot = {}
        for collection, (table, columns) in specifications.items():
            rows = connection.execute(f'SELECT {columns} FROM "{table}" ORDER BY id').fetchall()
            snapshot[collection] = [(str(row['id']), dict(row)) for row in rows]

        links = connection.execute('SELECT ajudante_id, coroinha_id FROM ajudante_coroinha').fetchall()
        linked_children = {}
        for helper_id, child_id in links:
            linked_children.setdefault(str(helper_id), []).append(child_id)
        for document_id, data in snapshot['ajudantes']:
            data['coroinhas_vinculados_ids'] = sorted(linked_children.get(document_id, []))

    for collection in ('restricoes_ajudantes', 'restricoes'):
        for _, data in snapshot[collection]:
            data['data_exata'] = serialize(date.fromisoformat(data['data_exata']))
    for _, data in snapshot['missas']:
        data['data_hora'] = datetime.fromisoformat(data['data_hora'])
    return snapshot


def ensure_firestore_is_empty(client):
    marker_ref = client.collection(MIGRATION_DOCUMENT[0]).document(MIGRATION_DOCUMENT[1])
    if marker_ref.get().exists:
        raise RuntimeError(
            'Já existe marcador sqlite_v1 no Firestore. Migração cancelada para evitar sobrescrita.'
        )

    for collection in COLLECTIONS:
        if next(client.collection(collection).limit(1).stream(), None) is not None:
            raise RuntimeError(
                f'A coleção {collection} já contém documentos. Migração cancelada; nenhum dado foi sobrescrito.'
            )
    return marker_ref


def write_snapshot(client, snapshot, marker_ref):
    marker_ref.create({'state': 'started', 'source': 'sqlite', 'version': 1})
    batch = client.batch()
    pending_writes = 0
    counts = {}

    for collection, documents in snapshot.items():
        counts[collection] = len(documents)
        for document_id, data in documents:
            batch.set(client.collection(collection).document(document_id), data)
            pending_writes += 1
            if pending_writes >= MAX_BATCH_WRITES:
                batch.commit()
                batch = client.batch()
                pending_writes = 0

    if pending_writes:
        batch.commit()

    marker_ref.update({'state': 'completed', 'counts': counts})
    return counts


def migrate(apply_changes):
    snapshot = load_snapshot()
    counts = {collection: len(documents) for collection, documents in snapshot.items()}
    total = sum(counts.values())
    print(f'Prévia local: {total} documentos em {len(counts)} coleções.')
    if not apply_changes:
        print('Nenhuma gravação foi feita. Revise a origem e execute novamente com --apply.')
        return

    client = get_firestore_client()
    marker_ref = ensure_firestore_is_empty(client)
    written_counts = write_snapshot(client, snapshot, marker_ref)
    print(f'Migração concluída: {sum(written_counts.values())} documentos gravados.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Copia o banco SQLite local para coleções vazias do Firestore.')
    parser.add_argument(
        '--apply',
        action='store_true',
        help='grava os dados no Firestore; sem esta opção, apenas exibe a prévia local',
    )
    arguments = parser.parse_args()
    try:
        migrate(arguments.apply)
    except Exception as error:
        raise SystemExit(f'Migração interrompida: {error}') from error
