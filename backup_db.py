import os
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
DATABASE_PATH = PROJECT_DIR / 'instance' / 'paroquia.db'
BACKUP_DIR = PROJECT_DIR / 'backups'


def create_backup():
    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(f'Banco não encontrado: {DATABASE_PATH}')

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup_path = BACKUP_DIR / f'paroquia_{timestamp}.db'
    file_descriptor, temporary_path = tempfile.mkstemp(prefix='.paroquia-', suffix='.tmp', dir=BACKUP_DIR)
    os.close(file_descriptor)

    try:
        with closing(sqlite3.connect(DATABASE_PATH.as_uri() + '?mode=ro', uri=True)) as source:
            with closing(sqlite3.connect(temporary_path)) as destination:
                source.backup(destination)
                integrity = destination.execute('PRAGMA integrity_check').fetchone()[0]
                if integrity != 'ok':
                    raise sqlite3.DatabaseError(f'Backup inválido: {integrity}')
                destination.commit()
        os.replace(temporary_path, backup_path)
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)

    return backup_path


if __name__ == '__main__':
    try:
        print(f'Backup criado: {create_backup()}')
    except (OSError, sqlite3.Error) as error:
        raise SystemExit(f'Falha ao criar backup: {error}') from error
