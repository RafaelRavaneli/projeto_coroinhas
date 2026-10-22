import random
import hmac
import os
import secrets
from datetime import datetime, timedelta
import re
from flask import Flask, abort, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash
from firestore_repository import FirestoreRepository

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', '').lower() in {'1', 'true', 'yes'}
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024
app.config['APP_USERNAME'] = os.environ.get('APP_USERNAME', '').strip()
app.config['APP_PASSWORD_HASH'] = os.environ.get('APP_PASSWORD_HASH', '').strip()
store = FirestoreRepository()
Ajudante = 'Ajudante'
RestricaoAjudante = 'RestricaoAjudante'
Coroinha = 'Coroinha'
Restricao = 'Restricao'
RestricaoFuncao = 'RestricaoFuncao'
Missa = 'Missa'
Escala = 'Escala'
EscalaAjudante = 'EscalaAjudante'


def get_record(model, document_id):
    return store.get_or_404(model, document_id)


def save_record(record):
    record.save()


def create_record(model, **values):
    return store.create(model, **values)

PERIODOS = {'Manhã', 'Tarde', 'Noite', 'Dia Todo'}


def csrf_token():
    token = session.get('_csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['_csrf_token'] = token
    return token


@app.context_processor
def inject_csrf_token():
    return {'csrf_token': csrf_token}


@app.before_request
def reset_firestore_request_cache():
    store.clear_cache()


@app.before_request
def require_login_and_csrf():
    if request.endpoint == 'static':
        return
    if not app.config['APP_USERNAME'] or not app.config['APP_PASSWORD_HASH']:
        abort(503, description='Configure APP_USERNAME e APP_PASSWORD_HASH antes de usar o sistema.')
    if request.endpoint != 'login' and not session.get('authenticated'):
        return redirect(url_for('login', next=request.full_path if request.query_string else request.path))
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        expected = session.get('_csrf_token', '')
        supplied = request.form.get('_csrf_token', '') or request.headers.get('X-CSRF-Token', '')
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            abort(400, description='Token de segurança inválido. Atualize a página e tente novamente.')


@app.after_request
def add_security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    if request.is_secure:
        response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    if session.get('authenticated'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.errorhandler(400)
@app.errorhandler(503)
def handle_request_error(error):
    return render_template('error.html', status_code=error.code, message=error.description), error.code


def is_safe_next_url(target):
    return bool(target and target.startswith('/') and not target.startswith('//') and '\\' not in target)


def required_text(field, label, max_length):
    value = (request.form.get(field) or '').strip()
    if not value:
        abort(400, description=f'{label} é obrigatório.')
    if len(value) > max_length:
        abort(400, description=f'{label} deve ter no máximo {max_length} caracteres.')
    return value


def optional_text(field, label, max_length):
    value = (request.form.get(field) or '').strip()
    if len(value) > max_length:
        abort(400, description=f'{label} deve ter no máximo {max_length} caracteres.')
    return value or None


def validated_phone(field, label, required=False):
    value = (request.form.get(field) or '').strip()
    if not value:
        if required:
            abort(400, description=f'{label} é obrigatório.')
        return None
    digits = re.sub(r'\D', '', value)
    if len(digits) not in {10, 11, 12, 13} or (len(digits) > 11 and not digits.startswith('55')):
        abort(400, description=f'{label} deve conter telefone brasileiro válido, com DDD.')
    return value


def parsed_date(value, label):
    try:
        return datetime.strptime(value or '', '%Y-%m-%d').date()
    except ValueError:
        abort(400, description=f'{label} inválida.')


def parsed_datetime(value, label):
    try:
        return datetime.strptime(value or '', '%Y-%m-%dT%H:%M')
    except ValueError:
        abort(400, description=f'{label} inválida.')


def validated_period():
    period = request.form.get('periodo')
    if period not in PERIODOS:
        abort(400, description='Selecione um período válido.')
    return period


def validated_coroinhas(field='coroinhas_vinculados'):
    values = request.form.getlist(field)
    if any(not value for value in values):
        abort(400, description='Seleção de coroinhas inválida.')
    ids = [str(value) for value in values]
    if len(ids) != len(set(ids)):
        abort(400, description='A seleção contém coroinhas repetidos.')
    selected = [record for record in store.all('Coroinha') if record.id in ids] if ids else []
    if len(selected) != len(ids):
        abort(400, description='Um ou mais coroinhas selecionados não existem.')
    return selected


def apply_date_filters(records):
    start_value = request.args.get('data_inicio', '').strip()
    end_value = request.args.get('data_fim', '').strip()
    start_date = parsed_date(start_value, 'Data inicial') if start_value else None
    end_date = parsed_date(end_value, 'Data final') if end_value else None
    if start_date and end_date and start_date > end_date:
        abort(400, description='Data inicial não pode ser posterior à data final.')
    if start_date:
        records = [record for record in records if record.data_hora >= datetime.combine(start_date, datetime.min.time())]
    if end_date:
        end_exclusive = datetime.combine(end_date + timedelta(days=1), datetime.min.time()) if end_date < datetime.max.date() else None
        records = [record for record in records if record.data_hora < end_exclusive] if end_exclusive else records
    return records


@app.route('/login', methods=['GET', 'POST'])
def login():
    target = request.args.get('next') or request.form.get('next')
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if len(username) > 256 or len(password) > 1024:
            abort(400, description='Usuário ou senha excede o limite permitido.')
        try:
            password_valid = check_password_hash(app.config['APP_PASSWORD_HASH'], password)
        except (ValueError, TypeError):
            password_valid = False
        if hmac.compare_digest(username.encode('utf-8'), app.config['APP_USERNAME'].encode('utf-8')) and password_valid:
            session.clear()
            session.permanent = True
            session['authenticated'] = True
            csrf_token()
            return redirect(target if is_safe_next_url(target) else url_for('index'))
        return render_template('login.html', erro='Usuário ou senha inválidos.', next=target), 401
    return render_template('login.html', erro=None, next=target)


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('login'))

# Filtro Jinja: limpa o telefone e garante o DDI 55 para o link do WhatsApp
@app.template_filter('wa_link')
def wa_link(numero):
    if not numero:
        return ''
    limpo = re.sub(r'\D', '', numero)  # remove parênteses, traço, espaço
    if len(limpo) in {10, 11}:
        limpo = '55' + limpo
    elif len(limpo) not in {12, 13} or not limpo.startswith('55'):
        return ''
    return limpo

# ==========================================
# 2. DEFINIÇÕES LITÚRGICAS
# ==========================================
MOLDES_LITURGICOS = {
    'Tradicional': [
        {'funcao': 'Acólito (Missal)', 'exigencia': 'Acólito'},
        {'funcao': 'Cruciferário (Cruz)', 'exigencia': 'Coroinha'},
        {'funcao': 'Ceriferário (Vela 1)', 'exigencia': 'Coroinha'},
        {'funcao': 'Ceriferário (Vela 2)', 'exigencia': 'Coroinha'},
        {'funcao': 'Jarra', 'exigencia': 'Coroinha'},
        {'funcao': 'Bacia/Lavabo', 'exigencia': 'Coroinha'}
    ],
    'Solene': [
        {'funcao': 'Acólito (Missal)', 'exigencia': 'Acólito'},
        {'funcao': 'Acólito (Turíbulo)', 'exigencia': 'Acólito'},
        {'funcao': 'Acólito (Naveta)', 'exigencia': 'Acólito'},
        {'funcao': 'Cruciferário (Cruz)', 'exigencia': 'Coroinha'},
        {'funcao': 'Ceriferário (Vela 1)', 'exigencia': 'Coroinha'},
        {'funcao': 'Ceriferário (Vela 2)', 'exigencia': 'Coroinha'},
        {'funcao': 'Jarra', 'exigencia': 'Coroinha'},
        {'funcao': 'Bacia/Lavabo', 'exigencia': 'Coroinha'}
    ],
    'Bispo': [
        {'funcao': 'Acólito (Missal)', 'exigencia': 'Acólito'},
        {'funcao': 'Acólito (Turíbulo)', 'exigencia': 'Acólito'},
        {'funcao': 'Acólito (Naveta)', 'exigencia': 'Acólito'},
        {'funcao': 'Acólito (Mitra)', 'exigencia': 'Acólito'},
        {'funcao': 'Acólito (Báculo)', 'exigencia': 'Acólito'},
        {'funcao': 'Cruciferário (Cruz)', 'exigencia': 'Coroinha'},
        {'funcao': 'Ceriferário (Vela 1)', 'exigencia': 'Coroinha'},
        {'funcao': 'Ceriferário (Vela 2)', 'exigencia': 'Coroinha'},
        {'funcao': 'Jarra', 'exigencia': 'Coroinha'},
        {'funcao': 'Bacia/Lavabo', 'exigencia': 'Coroinha'}
    ]
}

# ==========================================
# 3. ROTAS DE COROINHAS (Mantidas)
# ==========================================
@app.route('/')
def index():
    coroinhas = sorted(store.all(Coroinha), key=lambda coroinha: coroinha.nome.casefold())
    return render_template('index.html', coroinhas=coroinhas)

@app.route('/coroinha/novo', methods=['POST'])
def novo_coroinha():
    tipo = request.form.get('tipo')
    if tipo not in {'Coroinha', 'Acólito'}:
        abort(400, description='Selecione um grau válido.')
    create_record(Coroinha,
        nome=required_text('nome', 'Nome do jovem', 100),
        telefone_jovem=validated_phone('telefone_jovem', 'Celular do jovem'),
        tipo=tipo,
        responsavel_nome=required_text('responsavel_nome', 'Nome do responsável', 100),
        responsavel_telefone=validated_phone('responsavel_telefone', 'Telefone do responsável', required=True),
        responsavel2_nome=optional_text('responsavel2_nome', 'Nome do segundo responsável', 100),
        responsavel2_telefone=validated_phone('responsavel2_telefone', 'Telefone do segundo responsável')
    )
    return redirect(url_for('index'))

@app.route('/coroinha/deletar/<id>', methods=['POST'])
def deletar_coroinha(id):
    store.delete(Coroinha, id)
    return redirect(url_for('index'))

@app.route('/coroinha/editar/<id>', methods=['POST'])
def editar_coroinha(id):
    c = get_record(Coroinha, id)
    tipo = request.form.get('tipo')
    if tipo not in {'Coroinha', 'Acólito'}:
        abort(400, description='Selecione um grau válido.')
    c.nome = required_text('nome', 'Nome do jovem', 100)
    c.telefone_jovem = validated_phone('telefone_jovem', 'Celular do jovem')
    c.tipo = tipo
    c.responsavel_nome = required_text('responsavel_nome', 'Nome do responsável', 100)
    c.responsavel_telefone = validated_phone('responsavel_telefone', 'Telefone do responsável', required=True)
    c.responsavel2_nome = optional_text('responsavel2_nome', 'Nome do segundo responsável', 100)
    c.responsavel2_telefone = validated_phone('responsavel2_telefone', 'Telefone do segundo responsável')
    c.ativo = request.form.get('ativo') == '1'
    save_record(c)
    return redirect(url_for('index'))


# ==========================================
# 4. ROTAS DE AJUDANTES (NOVO CRUD)
# ==========================================
@app.route('/ajudantes')
def ajudantes():
    todos_ajudantes = sorted(store.all(Ajudante), key=lambda ajudante: ajudante.nome.casefold())
    todos_coroinhas = sorted(store.all(Coroinha), key=lambda coroinha: coroinha.nome.casefold())
    store.all(RestricaoAjudante)
    return render_template('ajudantes.html', ajudantes=todos_ajudantes, coroinhas=todos_coroinhas)

@app.route('/ajudante/novo', methods=['POST'])
def novo_ajudante():
    selected = validated_coroinhas()
    create_record(Ajudante,
        nome=required_text('nome', 'Nome do ajudante', 100),
        telefone=validated_phone('telefone', 'Telefone do ajudante', required=True),
        ativo=True,
        coroinhas_vinculados_ids=[coroinha.id for coroinha in selected],
    )
    return redirect(url_for('ajudantes'))

@app.route('/ajudante/deletar/<id>', methods=['POST'])
def deletar_ajudante(id):
    store.delete(Ajudante, id)
    return redirect(url_for('ajudantes'))

@app.route('/ajudante/<id>/restricao/nova', methods=['POST'])
def nova_restricao_ajudante(id):
    get_record(Ajudante, id)
    create_record(RestricaoAjudante, data_exata=parsed_date(request.form.get('data_exata'), 'Data').isoformat(), periodo=validated_period(), ajudante_id=id)
    return redirect(url_for('ajudantes'))


@app.route('/ajudante/restricao/deletar/<id>', methods=['POST'])
def deletar_restricao_ajudante(id):
    store.delete(RestricaoAjudante, id)
    return redirect(url_for('ajudantes'))

@app.route('/ajudante/editar/<id>', methods=['POST'])
def editar_ajudante(id):
    ajudante = get_record(Ajudante, id)
    ajudante.nome = required_text('nome', 'Nome do ajudante', 100)
    ajudante.telefone = validated_phone('telefone', 'Telefone do ajudante', required=True)
    ajudante.ativo = request.form.get('ativo') == '1'
    ajudante.coroinhas_vinculados_ids = [coroinha.id for coroinha in validated_coroinhas()]
    save_record(ajudante)
    return redirect(url_for('ajudantes'))


# ==========================================
# 5. ROTAS DE MISSAS E EVENTOS
# ==========================================
@app.route('/missas')
def missas():
    missas_filtradas = apply_date_filters(store.all(Missa))
    missas_filtradas.sort(key=lambda missa: missa.data_hora)
    return render_template('missas.html', missas=missas_filtradas, data_inicio=request.args.get('data_inicio'), data_fim=request.args.get('data_fim'))

@app.route('/missa/nova', methods=['POST'])
def nova_missa():
    tipo_missa = request.form.get('tipo_missa')
    if tipo_missa not in MOLDES_LITURGICOS:
        abort(400, description='Selecione um tipo de celebração válido.')
    create_record(Missa,
        descricao=required_text('descricao', 'Descrição', 100),
        data_hora=parsed_datetime(request.form.get('data_hora'), 'Data e hora'),
        tipo_missa=tipo_missa
    )
    return redirect(url_for('missas'))

@app.route('/missa/editar/<id>', methods=['POST'])
def editar_missa(id):
    m = get_record(Missa, id)
    tipo_missa = request.form.get('tipo_missa')
    if tipo_missa not in MOLDES_LITURGICOS:
        abort(400, description='Selecione um tipo de celebração válido.')
    m.descricao = required_text('descricao', 'Descrição', 100)
    m.tipo_missa = tipo_missa
    m.data_hora = parsed_datetime(request.form.get('data_hora'), 'Data e hora')
    save_record(m)
    return redirect(url_for('missas'))

@app.route('/missa/deletar/<id>', methods=['POST'])
def deletar_missa(id):
    store.delete(Missa, id)
    return redirect(url_for('missas'))


# ==========================================
# 6. RESTRIÇÕES DE COROINHAS
# ==========================================
@app.route('/coroinha/<id>/restricoes')
def restricoes(id):
    c = get_record(Coroinha, id)
    return render_template('restricoes.html', coroinha=c, horarios=store.all(Restricao, coroinha_id=id), funcoes=store.all(RestricaoFuncao, coroinha_id=id))

@app.route('/coroinha/<id>/restricao_data/nova', methods=['POST'])
def nova_restricao_data(id):
    get_record(Coroinha, id)
    create_record(Restricao, data_exata=parsed_date(request.form.get('data_exata'), 'Data').isoformat(), periodo=validated_period(), coroinha_id=id)
    return redirect(url_for('restricoes', id=id))

@app.route('/coroinha/<id>/restricao_funcao/nova', methods=['POST'])
def nova_restricao_funcao(id):
    get_record(Coroinha, id)
    funcao = request.form.get('funcao_proibida')
    funcoes_validas = {item['funcao'] for molde in MOLDES_LITURGICOS.values() for item in molde}
    if funcao not in funcoes_validas:
        abort(400, description='Selecione uma função válida.')
    create_record(RestricaoFuncao, funcao_proibida=funcao, coroinha_id=id)
    return redirect(url_for('restricoes', id=id))

@app.route('/restricao_data/deletar/<id>', methods=['POST'])
def deletar_restricao_data(id):
    restriction = get_record(Restricao, id)
    coroinha_id = restriction.coroinha_id
    store.delete(Restricao, id)
    return redirect(url_for('restricoes', id=coroinha_id))

@app.route('/restricao_funcao/deletar/<id>', methods=['POST'])
def deletar_restricao_funcao(id):
    restriction = get_record(RestricaoFuncao, id)
    coroinha_id = restriction.coroinha_id
    store.delete(RestricaoFuncao, id)
    return redirect(url_for('restricoes', id=coroinha_id))


# ==========================================
# 7. GERADOR DE WHATSAPP E MOTOR DE ESCALAS
# ==========================================

def chave_fim_de_semana(dt):
    """Sábado e domingo devolvem a MESMA chave (a data do sábado).
    Dias de semana devolvem None (sem limite por fim de semana)."""
    d = dt.date() if hasattr(dt, 'date') else dt
    if d.weekday() == 5:   # sábado
        return d
    if d.weekday() == 6:   # domingo
        return d - timedelta(days=1)
    return None
 
 
def missas_do_mesmo_fim_de_semana(missa):
    """Outras missas do mesmo sábado/domingo (exclui a própria missa)."""
    chave = chave_fim_de_semana(missa.data_hora)
    if chave is None:
        return []
    inicio = datetime.combine(chave, datetime.min.time())   # sábado 00:00
    fim = inicio + timedelta(days=2)                        # segunda 00:00
    return [
        record for record in store.all(Missa)
        if record.id != missa.id and inicio <= record.data_hora < fim
    ]

def gerar_texto_whatsapp(missas_filtradas):
    dias = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
    texto = "Segue escala, *atualizada* das Missas desse final de semana!\n"
    
    # Nomenclaturas adaptadas para o modelo da paróquia
    nomes_zap = {
        "Cruciferário (Cruz)": "Cruz",
        "Ceriferário (Vela 1)": "Castiçal",
        "Ceriferário (Vela 2)": "Castiçal",
        "Jarra": "Lavabo - Jarro",
        "Bacia/Lavabo": "Lavabo - bacia",
        "Acólito (Missal)": "Acólito Missal",
        "Acólito (Turíbulo)": "Turíbulo",
        "Acólito (Naveta)": "Naveta",
        "Acólito (Mitra)": "Mitra",
        "Acólito (Báculo)": "Báculo"
    }

    for m in missas_filtradas:
        if not m.escalas: continue
        
        dia_sem = dias[m.data_hora.weekday()]
        data_str = m.data_hora.strftime('%d/%m')
        hora_str = m.data_hora.strftime('%Hh%M')
        chegada = (m.data_hora - timedelta(minutes=30)).strftime('%H:%M')
        local = "*CAPELA*" if "capela" in m.descricao.lower() else "*MATRIZ*"
        
        texto += f"\n *{dia_sem}* ({data_str}) {local}- {m.descricao} das {hora_str} (chegar até {chegada})\n\n"
        
        molde_atual = MOLDES_LITURGICOS.get(m.tipo_missa, [])
        for item in molde_atual:
            f_nome = item['funcao']
            escala_jovem = next((e for e in m.escalas if e.funcao_atribuida == f_nome), None)
            nome_coroinha = escala_jovem.coroinha.nome if escala_jovem else "*EM ABERTO*"
            texto += f"{nomes_zap.get(f_nome, f_nome)}: {nome_coroinha}\n"
            
        resp = m.ajudante.nome if m.ajudante else "*EM ABERTO*"
        texto += f"\n*Responsável: {resp}*\n"

    texto += "\nFavor chegar à igreja com no máximo 30 minutos de antecedência.\nAtentem-se a conversa no interior da igreja e *na sacristia*\n\nPOR FAVOR CONFIRMEM COM UM *OK* OU 👍"
    return texto

@app.route('/escalas')
def escalas():
    todas_missas = apply_date_filters(store.all(Missa))
    todas_missas.sort(key=lambda missa: missa.data_hora)
    store.all(Escala)
    store.all(Coroinha)
    store.all(Ajudante)
    texto_wpp = gerar_texto_whatsapp(todas_missas)
    
    return render_template('escalas.html', missas=todas_missas, texto_whatsapp=texto_wpp, data_inicio=request.args.get('data_inicio'), data_fim=request.args.get('data_fim'))

def preencher_escalas_pendentes():
    missas = sorted(store.all(Missa), key=lambda missa: missa.data_hora)
    coroinhas = store.all(Coroinha)
    ajudantes = store.all(Ajudante)
    escalas = store.all(Escala)
    escalas_ajudantes = store.all(EscalaAjudante)
    restricoes_coroinhas = store.all(Restricao)
    restricoes_funcoes = store.all(RestricaoFuncao)
    restricoes_ajudantes = store.all(RestricaoAjudante)
 
    for missa in missas:
        funcoes_da_missa = MOLDES_LITURGICOS.get(missa.tipo_missa, [])
        hora = missa.data_hora.hour
        periodo_missa = 'Manhã' if hora < 12 else 'Tarde' if hora < 18 else 'Noite'
 
        # Quem já está escalado em OUTRA missa deste mesmo fim de semana
        outras = [
            outra for outra in missas
            if outra.id != missa.id
            and chave_fim_de_semana(outra.data_hora) == chave_fim_de_semana(missa.data_hora)
            and chave_fim_de_semana(missa.data_hora) is not None
        ]
        ids_outras = [m.id for m in outras]
        coroinhas_ocupados = set()
        if ids_outras:
            coroinhas_ocupados = {
                str(e.coroinha_id) for e in escalas if str(e.missa_id) in ids_outras
            }
        ajudantes_ocupados = {str(m.ajudante_id) for m in outras if m.ajudante_id}
 
        # Passo 1: Preencher Coroinhas e Acólitos
        for item in funcoes_da_missa:
            if any(str(e.missa_id) == missa.id and e.funcao_atribuida == item['funcao'] for e in escalas): continue
 
            escalados_agora = [e for e in escalas if str(e.missa_id) == missa.id]
            coroinhas_por_id = {coroinha.id: coroinha for coroinha in coroinhas}
            telefones_na_missa = [coroinhas_por_id[str(e.coroinha_id)].responsavel_telefone for e in escalados_agora if str(e.coroinha_id) in coroinhas_por_id]
 
            candidatos_validos = []
            for candidato in coroinhas:
                if not candidato.ativo or candidato.tipo != item['exigencia']:
                    continue
                if any(str(e.missa_id) == missa.id and str(e.coroinha_id) == candidato.id for e in escalas): continue
 
                # NOVO: já escalado em outra missa deste fim de semana
                if candidato.id in coroinhas_ocupados: continue
 
                if any(str(r.coroinha_id) == candidato.id and r.data_exata == missa.data_hora.date() and r.periodo in [periodo_missa, 'Dia Todo'] for r in restricoes_coroinhas): continue
                if any(str(r.coroinha_id) == candidato.id and item['funcao'] == r.funcao_proibida for r in restricoes_funcoes): continue
 
                candidatos_validos.append(candidato)
 
            if candidatos_validos:
                random.shuffle(candidatos_validos)
                candidatos_validos.sort(key=lambda c: (not c.responsavel_telefone in telefones_na_missa, sum(1 for escala in escalas if str(escala.coroinha_id) == c.id)))
                nova_escala = create_record(Escala, coroinha_id=candidatos_validos[0].id, missa_id=missa.id, funcao_atribuida=item['funcao'], status='Confirmado')
                escalas.append(nova_escala)
 
        # Passo 2: Sorteio do Ajudante (Garante pais na mesma missa)
        escalas_finais = [e for e in escalas if str(e.missa_id) == missa.id]
        if escalas_finais and not missa.ajudante_id:
            ajudantes_disponiveis = []
            for ajud in ajudantes:
                if not ajud.ativo:
                    continue
                # NOVO: ajudante já responsável por outra missa deste fim de semana
                if ajud.id in ajudantes_ocupados: continue
 
                if any(str(r.ajudante_id) == ajud.id and r.data_exata == missa.data_hora.date() and r.periodo in [periodo_missa, 'Dia Todo'] for r in restricoes_ajudantes):
                    continue
                if any(str(e.missa_id) == missa.id and str(e.ajudante_id) == ajud.id for e in escalas_ajudantes):
                    continue
                ajudantes_disponiveis.append(ajud)
 
            if ajudantes_disponiveis:
                ids_na_missa = [str(e.coroinha_id) for e in escalas_finais]
                # Filtra os ajudantes que tem filhos escalados nesta missa específica
                pais_na_missa = [a for a in ajudantes_disponiveis if any(str(filho_id) in ids_na_missa for filho_id in a.coroinhas_vinculados_ids)]
 
                escolhido = random.choice(pais_na_missa) if pais_na_missa else random.choice(ajudantes_disponiveis)
                missa.ajudante_id = escolhido.id
                save_record(missa)
                escalas_ajudantes.append(create_record(EscalaAjudante, ajudante_id=escolhido.id, missa_id=missa.id))
 
@app.route('/escala/gerar', methods=['POST'])
def gerar_escala_automatica():
    preencher_escalas_pendentes()
    return redirect(url_for('escalas'))

@app.route('/escala/regerar/<id>', methods=['POST'])
def regerar_escala(id):
    missa = get_record(Missa, id)
    for escala in store.all(Escala, missa_id=id):
        store.delete(Escala, escala.id)
    for escala in store.all(EscalaAjudante, missa_id=id):
        store.delete(EscalaAjudante, escala.id)
    missa.ajudante_id = None
    save_record(missa)
    preencher_escalas_pendentes()
    return redirect(url_for('escalas'))

@app.route('/escala/deletar/<id>', methods=['POST'])
def deletar_escala(id):
    store.delete(Escala, id)
    return redirect(url_for('escalas'))

if __name__ == '__main__':
    app.run(debug=False)
