import json
import os

def get_firestore_client():
    import firebase_admin
    from firebase_admin import credentials, firestore

    project_id = os.environ.get('FIREBASE_PROJECT_ID', '').strip()
    service_account_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT_JSON', '').strip()

    if service_account_json:
        try:
            service_account_info = json.loads(service_account_json)
        except json.JSONDecodeError as error:
            raise RuntimeError('FIREBASE_SERVICE_ACCOUNT_JSON precisa conter um JSON válido.') from error

        credential_project_id = service_account_info.get('project_id')
        if project_id and credential_project_id != project_id:
            raise RuntimeError('FIREBASE_PROJECT_ID não corresponde ao projeto da credencial.')

        credential = credentials.Certificate(service_account_info)
        options = {'projectId': project_id or credential_project_id}
        try:
            firebase_app = firebase_admin.get_app()
        except ValueError:
            firebase_app = firebase_admin.initialize_app(credential, options)
    else:
        if not os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
            raise RuntimeError(
                'Configure FIREBASE_SERVICE_ACCOUNT_JSON no servidor ou '
                'GOOGLE_APPLICATION_CREDENTIALS no ambiente local.'
            )
        options = {'projectId': project_id} if project_id else None
        try:
            firebase_app = firebase_admin.get_app()
        except ValueError:
            firebase_app = firebase_admin.initialize_app(options=options)

    return firestore.client(app=firebase_app)
