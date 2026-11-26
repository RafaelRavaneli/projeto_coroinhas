# Operação e segurança

## Configurar acesso

O sistema exige login. Sem `APP_USERNAME` e `APP_PASSWORD_HASH`, as páginas do sistema respondem com erro 503 e não exibem os dados.

No PowerShell, com o ambiente virtual ativado, gere o hash da senha e uma chave de sessão:

```powershell
$env:APP_USERNAME = "coordenacao"
$env:APP_PASSWORD_HASH = & .venv\Scripts\python.exe -c "from getpass import getpass; from werkzeug.security import generate_password_hash; print(generate_password_hash(getpass('Senha: ')))"
$env:FLASK_SECRET_KEY = & .venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
$env:FIREBASE_PROJECT_ID = "projeto-coroinhas"
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\caminho\fora-do-projeto\chave.json"
$env:SESSION_COOKIE_SECURE = "0"
.venv\Scripts\python.exe app.py
```

Essas variáveis duram apenas na janela atual do PowerShell. Configure-as no ambiente persistente do servidor antes de publicar. Em produção, use HTTPS e defina `SESSION_COOKIE_SECURE=1`. Guarde os segredos fora do repositório. O sistema não cria usuário ou senha padrão.

O `FLASK_SECRET_KEY` deve permanecer estável entre reinicializações. Ao trocar a senha, troque também essa chave para encerrar sessões existentes. Use `app.py` apenas para desenvolvimento local; em produção, execute pelo servidor WSGI do host.

## Firebase Firestore

O app usa Firestore para leituras e gravações por meio de `firebase_store.py` e `firestore_repository.py`. A autenticação do servidor não usa as regras de segurança do cliente; proteja a conta de serviço com IAM e mantenha as regras do Firestore fechadas para acesso direto de clientes.

No Vercel, configure `FIREBASE_PROJECT_ID=projeto-coroinhas` e `FIREBASE_SERVICE_ACCOUNT_JSON` com o conteúdo completo da chave da conta de serviço, apenas nos ambientes necessários. Nunca coloque a chave no Git, em arquivos `.env` versionados, nem em variáveis expostas ao navegador (`NEXT_PUBLIC_*`/`VITE_*`). Dê à conta de serviço somente a função IAM necessária para acessar Firestore e não compartilhe a chave no chat.

Para desenvolvimento local, mantenha o arquivo de credencial fora do repositório e defina `GOOGLE_APPLICATION_CREDENTIALS` para o caminho absoluto dele e `FIREBASE_PROJECT_ID=projeto-coroinhas` na sessão do PowerShell. O app conecta ao Firestore quando uma rota acessa dados.

### Copiar SQLite para Firestore

Antes da cópia, pare a aplicação, faça backup do SQLite e configure as credenciais Firebase no PowerShell. Rode `python migrar_firestore.py` para ver somente a contagem local. A cópia exige a opção explícita `--apply` e só grava se todas as coleções de destino e o marcador de migração estiverem vazios. IDs são preservados como IDs de documentos; referências entre entidades são mantidas como IDs. Datas sem horário são armazenadas como texto ISO.

A migração não apaga nem altera o SQLite. Ao terminar, confira o marcador `_migrations/sqlite_v1` e as contagens gravadas. Se houver falha após o início da gravação, o marcador fica como `started`; não apague documentos nem repita automaticamente. Investigue o estado antes de retomar. O app agora usa Firestore; mantenha o SQLite e os backups preservados como cópia de segurança até validar produção.

## Backup do banco

O SQLite não é mais o banco ativo do app. Para preservar a cópia local anterior à migração, crie backup com:

```powershell
.venv\Scripts\python.exe backup_db.py
```

O script grava cópias verificadas em `backups/`, diretório ignorado pelo Git. Guarde backups em outro dispositivo ou serviço protegido. Para backup rotineiro do Firestore, use a exportação/backup do Google Cloud; o script `backup_db.py` cobre apenas o SQLite local antigo.

## Migração legada

`migrar.py` migra `instance/antigo.db` para `instance/paroquia.db`. Pare a aplicação e faça backup antes de migrar. O destino precisa estar vazio. O script cancela a operação se encontrar dados no destino, esquema incompleto ou origem ausente. Não execute sobre o banco atual, que já contém dados.
