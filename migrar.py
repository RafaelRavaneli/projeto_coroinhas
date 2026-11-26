import sqlite3
from contextlib import closing
from pathlib import Path



PROJECT_DIR = Path(__file__).resolve().parent
SOURCE_PATH = PROJECT_DIR / 'instance' / 'antigo.db'
DESTINATION_PATH = PROJECT_DIR / 'instance' / 'paroquia.db'

SOURCE_COLUMNS = {
    'coroinha': {'id', 'nome', 'telefone_jovem', 'tipo', 'responsavel_nome', 'responsavel_telefone', 'responsavel2_nome', 'responsavel2_telefone', 'ativo'},
    'restricao': {'id', 'data_exata', 'periodo', 'coroinha_id'},
    'restricao_funcao': {'id', 'funcao_proibida', 'coroinha_id'},
    'missa': {'id', 'descricao', 'data_hora', 'tipo_missa'},
    'escala': {'id', 'coroinha_id', 'missa_id', 'funcao_atribuida', 'status'},
}

DESTINATION_COLUMNS = {
    'coroinha': {'id', 'nome', 'telefone_jovem', 'tipo', 'responsavel_nome', 'responsavel_telefone', 'responsavel2_nome', 'responsavel2_telefone', 'ativo'},
    'ajudante': {'id', 'nome', 'telefone', 'ativo'},
    'ajudante_coroinha': {'ajudante_id', 'coroinha_id'},
    'restricao': {'id', 'data_exata', 'periodo', 'coroinha_id'},
    'restricao_funcao': {'id', 'funcao_proibida', 'coroinha_id'},
    'missa': {'id', 'descricao', 'data_hora', 'tipo_missa', 'ajudante_id'},
    'escala': {'id', 'coroinha_id', 'missa_id', 'funcao_atribuida', 'status'},
}


def table_columns(connection, table):
    return {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}


def validate_tables(connection, required_columns, label):
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    missing_tables = set(required_columns) - tables
    if missing_tables:
        raise ValueError(f'{label}: tabelas ausentes: {", ".join(sorted(missing_tables))}')
    for table, required in required_columns.items():
        missing_columns = required - table_columns(connection, table)
        if missing_columns:
            raise ValueError(f'{label}: colunas ausentes em {table}: {", ".join(sorted(missing_columns))}')


def ensure_destination_empty():
    if not DESTINATION_PATH.exists():
        return
    with closing(sqlite3.connect(DESTINATION_PATH)) as connection:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
        populated = [table for table in tables if connection.execute(f'SELECT 1 FROM "{table}" LIMIT 1').fetchone()]
    if populated:
        raise ValueError(f'Destino já contém dados nas tabelas: {", ".join(sorted(populated))}. A migração foi cancelada para preservar esses dados.')


def create_destination_schema():
    statements = (
        'CREATE TABLE IF NOT EXISTS coroinha (id INTEGER PRIMARY KEY, nome VARCHAR(100) NOT NULL, telefone_jovem VARCHAR(20), tipo VARCHAR(20) NOT NULL DEFAULT \'Coroinha\', responsavel_nome VARCHAR(100) NOT NULL, responsavel_telefone VARCHAR(20) NOT NULL, responsavel2_nome VARCHAR(100), responsavel2_telefone VARCHAR(20), ativo BOOLEAN DEFAULT 1)',
        'CREATE TABLE IF NOT EXISTS ajudante (id INTEGER PRIMARY KEY, nome VARCHAR(100) NOT NULL, telefone VARCHAR(20) NOT NULL, ativo BOOLEAN DEFAULT 1)',
        'CREATE TABLE IF NOT EXISTS ajudante_coroinha (ajudante_id INTEGER NOT NULL REFERENCES ajudante(id), coroinha_id INTEGER NOT NULL REFERENCES coroinha(id), PRIMARY KEY (ajudante_id, coroinha_id))',
        'CREATE TABLE IF NOT EXISTS restricao (id INTEGER PRIMARY KEY, data_exata DATE NOT NULL, periodo VARCHAR(50) NOT NULL, coroinha_id INTEGER NOT NULL REFERENCES coroinha(id))',
        'CREATE TABLE IF NOT EXISTS restricao_funcao (id INTEGER PRIMARY KEY, funcao_proibida VARCHAR(50) NOT NULL, coroinha_id INTEGER NOT NULL REFERENCES coroinha(id))',
        'CREATE TABLE IF NOT EXISTS restricao_ajudante (id INTEGER PRIMARY KEY, data_exata DATE NOT NULL, periodo VARCHAR(50) NOT NULL, ajudante_id INTEGER NOT NULL REFERENCES ajudante(id))',
        'CREATE TABLE IF NOT EXISTS missa (id INTEGER PRIMARY KEY, descricao VARCHAR(100) NOT NULL, data_hora DATETIME NOT NULL, tipo_missa VARCHAR(20) NOT NULL DEFAULT \'Tradicional\', ajudante_id INTEGER REFERENCES ajudante(id))',
        'CREATE TABLE IF NOT EXISTS escala (id INTEGER PRIMARY KEY, coroinha_id INTEGER NOT NULL REFERENCES coroinha(id), missa_id INTEGER NOT NULL REFERENCES missa(id), funcao_atribuida VARCHAR(50), status VARCHAR(20) DEFAULT \'Confirmado\')',
        'CREATE TABLE IF NOT EXISTS escala_ajudante (id INTEGER PRIMARY KEY, ajudante_id INTEGER NOT NULL REFERENCES ajudante(id), missa_id INTEGER NOT NULL REFERENCES missa(id))',
    )
    with closing(sqlite3.connect(DESTINATION_PATH)) as destination:
        destination.execute('PRAGMA foreign_keys = ON')
        for statement in statements:
            destination.execute(statement)
        destination.commit()


def migrate():
    if not SOURCE_PATH.is_file():
        raise FileNotFoundError(f'Banco de origem não encontrado: {SOURCE_PATH}')
    if SOURCE_PATH.resolve() == DESTINATION_PATH.resolve():
        raise ValueError('Origem e destino apontam para o mesmo arquivo.')

    with closing(sqlite3.connect(SOURCE_PATH.as_uri() + '?mode=ro', uri=True)) as source:
        validate_tables(source, SOURCE_COLUMNS, 'Banco de origem')
        coroinhas = source.execute('SELECT id, nome, telefone_jovem, tipo, responsavel_nome, responsavel_telefone, responsavel2_nome, responsavel2_telefone, ativo FROM coroinha').fetchall()
        restricoes = source.execute('SELECT id, data_exata, periodo, coroinha_id FROM restricao').fetchall()
        restricoes_funcao = source.execute('SELECT id, funcao_proibida, coroinha_id FROM restricao_funcao').fetchall()
        missas = source.execute('SELECT id, descricao, data_hora, tipo_missa FROM missa').fetchall()
        escalas = source.execute('SELECT id, coroinha_id, missa_id, funcao_atribuida, status FROM escala').fetchall()
        responsaveis = source.execute("SELECT DISTINCT responsavel_nome, responsavel_telefone FROM coroinha WHERE trim(coalesce(responsavel_nome, '')) != '' AND trim(coalesce(responsavel_telefone, '')) != ''").fetchall()
        vinculos = source.execute('SELECT id, responsavel_nome, responsavel_telefone FROM coroinha').fetchall()

    ensure_destination_empty()
    create_destination_schema()

    with closing(sqlite3.connect(DESTINATION_PATH)) as destination:
        destination.execute('PRAGMA foreign_keys = ON')
        validate_tables(destination, DESTINATION_COLUMNS, 'Banco de destino')
        try:
            destination.execute('BEGIN IMMEDIATE')
            destination.executemany('INSERT INTO coroinha (id, nome, telefone_jovem, tipo, responsavel_nome, responsavel_telefone, responsavel2_nome, responsavel2_telefone, ativo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', coroinhas)
            destination.executemany('INSERT INTO restricao (id, data_exata, periodo, coroinha_id) VALUES (?, ?, ?, ?)', restricoes)
            destination.executemany('INSERT INTO restricao_funcao (id, funcao_proibida, coroinha_id) VALUES (?, ?, ?)', restricoes_funcao)
            destination.executemany('INSERT INTO missa (id, descricao, data_hora, tipo_missa, ajudante_id) VALUES (?, ?, ?, ?, NULL)', missas)
            destination.executemany('INSERT INTO escala (id, coroinha_id, missa_id, funcao_atribuida, status) VALUES (?, ?, ?, ?, ?)', escalas)

            helper_ids = {}
            for nome, telefone in responsaveis:
                cursor = destination.execute('INSERT INTO ajudante (nome, telefone, ativo) VALUES (?, ?, 1)', (nome, telefone))
                helper_ids[(nome, telefone)] = cursor.lastrowid

            destination.executemany(
                'INSERT INTO ajudante_coroinha (ajudante_id, coroinha_id) VALUES (?, ?)',
                [(helper_ids[(nome, telefone)], coroinha_id) for coroinha_id, nome, telefone in vinculos if (nome, telefone) in helper_ids]
            )
            destination.commit()
        except Exception:
            destination.rollback()
            raise

    print(f'Migração concluída: {len(coroinhas)} coroinhas, {len(missas)} missas e {len(escalas)} escalas.')


if __name__ == '__main__':
    try:
        migrate()
    except (OSError, sqlite3.Error, ValueError) as error:
        raise SystemExit(f'Migração cancelada: {error}') from error
