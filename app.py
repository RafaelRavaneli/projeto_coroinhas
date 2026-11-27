import hashlib
import random
import hmac
import os
import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash
from firestore_repository import FirestoreRepository
from conflitos import (
    conflitos_da_escala,
    motivos_conflito_ajudante,
    motivos_conflito_coroinha,
)

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


# As missas são gravadas no horário de Brasília (sem fuso). O servidor da Vercel
# roda em UTC, então "agora" precisa ser calculado no fuso da paróquia.
FUSO_PAROQUIA = ZoneInfo('America/Sao_Paulo')


def agora_local():
    return datetime.now(FUSO_PAROQUIA).replace(tzinfo=None)


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
    return {'csrf_token': csrf_token, 'moldes': MOLDES_LITURGICOS, 'asset_version': ASSET_VERSION}


def _asset_version():
    """Muda quando CSS ou JS mudam, para o navegador não usar arquivo antigo do cache.

    Usa o conteúdo dos arquivos, não a data: na Vercel todos os arquivos
    publicados têm a mesma data de modificação em qualquer deploy.
    """
    pasta = os.path.join(app.root_path, 'static')
    resumo = hashlib.sha256()
    for raiz, pastas, nomes in os.walk(pasta):
        pastas.sort()
        for nome in sorted(nomes):
            caminho = os.path.join(raiz, nome)
            resumo.update(os.path.relpath(caminho, pasta).encode('utf-8'))
            with open(caminho, 'rb') as arquivo:
                resumo.update(arquivo.read())
    return resumo.hexdigest()[:10]


ASSET_VERSION = _asset_version()


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


def avisar_se_data_suspeita(data):
    """Avisa (sem bloquear) quando a restrição cadastrada está no passado ou muito distante."""
    hoje = agora_local().date()
    if data < hoje:
        flash(f'Atenção: a data {data:%d/%m/%Y} já passou. Confira se o ano está correto.', 'warning')
    elif data > hoje + timedelta(days=183):
        flash(f'Atenção: a data {data:%d/%m/%Y} está a mais de 6 meses. Confira se o ano está correto.', 'warning')


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


# Apresentação de datas em português para os templates
DIAS_CURTOS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
DIAS_LONGOS = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']
MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']


@app.template_filter('dia_curto')
def dia_curto(dt):
    return DIAS_CURTOS[dt.weekday()]


@app.template_filter('mes_curto')
def mes_curto(dt):
    return MESES[dt.month - 1][:3]


@app.template_filter('data_extenso')
def data_extenso(dt):
    return f'{dt.day} de {MESES[dt.month - 1]} de {dt.year}'


@app.template_filter('hora')
def hora(dt):
    return dt.strftime('%Hh%M')


@app.template_filter('chegada')
def chegada(dt):
    return (dt - timedelta(minutes=30)).strftime('%Hh%M')


@app.template_global()
def agrupar_por_fim_de_semana(missas):
    """Agrupa missas já ordenadas: sábado e domingo juntos; dias de semana separados."""
    grupos = []
    for missa in missas:
        dia = missa.data_hora.date()
        if dia.weekday() in (5, 6):
            sabado = dia - timedelta(days=dia.weekday() - 5)
            domingo = sabado + timedelta(days=1)
            chave = ('fds', sabado)
            if sabado.month == domingo.month:
                rotulo = f'Fim de semana de {sabado.day} e {domingo.day} de {MESES[sabado.month - 1]}'
            else:
                rotulo = f'Fim de semana de {sabado.day} de {MESES[sabado.month - 1]} e {domingo.day} de {MESES[domingo.month - 1]}'
        else:
            chave = ('dia', dia)
            rotulo = f'{DIAS_LONGOS[dia.weekday()]}, {dia.day} de {MESES[dia.month - 1]}'
        if grupos and grupos[-1]['chave'] == chave:
            grupos[-1]['missas'].append(missa)
        else:
            grupos.append({'chave': chave, 'rotulo': rotulo, 'missas': [missa]})
    return grupos

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
        responsavel2_telefone=validated_phone('responsavel2_telefone', 'Telefone do segundo responsável'),
        ativo=True,
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
    data = parsed_date(request.form.get('data_exata'), 'Data')
    create_record(RestricaoAjudante, data_exata=data.isoformat(), periodo=validated_period(), ajudante_id=id)
    avisar_se_data_suspeita(data)
    flash('Restrição cadastrada. Escalas já geradas não mudam sozinhas: use "Gerar / Corrigir" na tela de Escalas.', 'info')
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
    store.all(Escala)
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

def limpar_escala_da_missa(missa):
    """Remove escalados e ajudante da missa (como regerar_escala já fazia)."""
    for escala in store.all(Escala, missa_id=missa.id):
        store.delete(Escala, escala.id)
    for escala in store.all(EscalaAjudante, missa_id=missa.id):
        store.delete(EscalaAjudante, escala.id)
    missa.ajudante_id = None


@app.route('/missa/editar/<id>', methods=['POST'])
def editar_missa(id):
    m = get_record(Missa, id)
    tipo_missa = request.form.get('tipo_missa')
    if tipo_missa not in MOLDES_LITURGICOS:
        abort(400, description='Selecione um tipo de celebração válido.')
    descricao = required_text('descricao', 'Descrição', 100)
    nova_data_hora = parsed_datetime(request.form.get('data_hora'), 'Data e hora')

    # Data/hora ou tipo mudaram: a escala antiga foi montada para outra celebração
    # e as restrições não foram verificadas para a nova. Descartar e pedir nova geração.
    mudou = nova_data_hora != m.data_hora or tipo_missa != m.tipo_missa
    tinha_escala = bool(store.all(Escala, missa_id=m.id) or store.all(EscalaAjudante, missa_id=m.id) or m.ajudante_id)
    if mudou:
        limpar_escala_da_missa(m)

    m.descricao = descricao
    m.tipo_missa = tipo_missa
    m.data_hora = nova_data_hora
    save_record(m)
    if mudou and tinha_escala:
        flash(
            f'A data ou o tipo de "{descricao}" mudou, então a escala antiga foi removida. '
            'Vá em Escalas e use "Gerar / Corrigir" para montar a nova.',
            'warning',
        )
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
    data = parsed_date(request.form.get('data_exata'), 'Data')
    create_record(Restricao, data_exata=data.isoformat(), periodo=validated_period(), coroinha_id=id)
    avisar_se_data_suspeita(data)
    flash('Restrição cadastrada. Escalas já geradas não mudam sozinhas: use "Gerar / Corrigir" na tela de Escalas.', 'info')
    return redirect(url_for('restricoes', id=id))

@app.route('/coroinha/<id>/restricao_funcao/nova', methods=['POST'])
def nova_restricao_funcao(id):
    get_record(Coroinha, id)
    funcao = request.form.get('funcao_proibida')
    funcoes_validas = {item['funcao'] for molde in MOLDES_LITURGICOS.values() for item in molde}
    if funcao not in funcoes_validas:
        abort(400, description='Selecione uma função válida.')
    create_record(RestricaoFuncao, funcao_proibida=funcao, coroinha_id=id)
    flash('Restrição cadastrada. Escalas já geradas não mudam sozinhas: use "Gerar / Corrigir" na tela de Escalas.', 'info')
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

def calcular_conflitos(missas):
    """Conflitos das escalas já existentes das missas futuras.

    Devolve (por_escala, por_missa_ajudante, total):
    - por_escala: {id da Escala: [motivos]}
    - por_missa_ajudante: {id da Missa: [motivos]} para o ajudante responsável
    Missas passadas são ignoradas: o gerador não mexe nelas.
    """
    agora = agora_local()
    coroinhas_por_id = {coroinha.id: coroinha for coroinha in store.all(Coroinha)}
    ajudantes_por_id = {ajudante.id: ajudante for ajudante in store.all(Ajudante)}
    escalas = store.all(Escala)
    restricoes_coroinhas = store.all(Restricao)
    restricoes_funcoes = store.all(RestricaoFuncao)
    restricoes_ajudantes = store.all(RestricaoAjudante)

    por_escala = {}
    por_missa_ajudante = {}
    for missa in missas:
        if missa.data_hora < agora:
            continue
        molde = MOLDES_LITURGICOS.get(missa.tipo_missa, [])
        for escala in escalas:
            if str(escala.missa_id) != missa.id:
                continue
            motivos = conflitos_da_escala(
                escala, missa, coroinhas_por_id.get(str(escala.coroinha_id)),
                molde, restricoes_coroinhas, restricoes_funcoes,
            )
            if motivos:
                por_escala[escala.id] = motivos
        if missa.ajudante_id:
            motivos = motivos_conflito_ajudante(
                ajudantes_por_id.get(str(missa.ajudante_id)), missa, restricoes_ajudantes
            )
            if motivos:
                por_missa_ajudante[missa.id] = motivos
    return por_escala, por_missa_ajudante, len(por_escala) + len(por_missa_ajudante)


@app.route('/escalas')
def escalas():
    todas_missas = apply_date_filters(store.all(Missa))
    todas_missas.sort(key=lambda missa: missa.data_hora)
    store.all(Escala)
    store.all(Coroinha)
    store.all(Ajudante)
    texto_wpp = gerar_texto_whatsapp(todas_missas)
    conflitos_escalas, conflitos_ajudantes, total_conflitos = calcular_conflitos(todas_missas)

    return render_template(
        'escalas.html', missas=todas_missas, texto_whatsapp=texto_wpp,
        data_inicio=request.args.get('data_inicio'), data_fim=request.args.get('data_fim'),
        conflitos_escalas=conflitos_escalas, conflitos_ajudantes=conflitos_ajudantes,
        total_conflitos=total_conflitos, agora=agora_local(),
    )

def preencher_escalas_pendentes(missa_ids=None):
    """Corrige conflitos e preenche vagas das missas FUTURAS.

    1. Remove quem está escalado em conflito (restrição de data/período,
       função proibida, grau incompatível, função que não existe no tipo
       atual da missa) e ajudantes em conflito. O restante da escala fica intacto.
    2. Preenche as vagas, inclusive as abertas no passo 1.

    `missa_ids` limita a geração a essas missas (usado por regerar_escala); as
    demais missas continuam valendo como contexto da regra de um escalado por
    fim de semana. Missas passadas nunca são alteradas.
    Devolve contagens para a mensagem ao usuário.
    """
    agora = agora_local()
    missas = sorted(store.all(Missa), key=lambda missa: missa.data_hora)
    alvo_ids = {str(i) for i in missa_ids} if missa_ids is not None else None
    missas_alvo = [
        m for m in missas
        if m.data_hora >= agora and (alvo_ids is None or m.id in alvo_ids)
    ]
    coroinhas = store.all(Coroinha)
    coroinhas_por_id = {coroinha.id: coroinha for coroinha in coroinhas}
    ajudantes = store.all(Ajudante)
    ajudantes_por_id = {ajudante.id: ajudante for ajudante in ajudantes}
    escalas = store.all(Escala)
    escalas_ajudantes = store.all(EscalaAjudante)
    restricoes_coroinhas = store.all(Restricao)
    restricoes_funcoes = store.all(RestricaoFuncao)
    restricoes_ajudantes = store.all(RestricaoAjudante)
    resultado = {'removidos': 0, 'preenchidos': 0, 'ajudantes_removidos': 0, 'ajudantes_preenchidos': 0}

    # Passo 0: remover escalados em conflito de TODAS as missas alvo antes de
    # preencher qualquer uma, para que as vagas liberadas já contem na regra
    # de fim de semana das missas seguintes.
    for missa in missas_alvo:
        molde = MOLDES_LITURGICOS.get(missa.tipo_missa, [])
        for escala in [e for e in escalas if str(e.missa_id) == missa.id]:
            motivos = conflitos_da_escala(
                escala, missa, coroinhas_por_id.get(str(escala.coroinha_id)),
                molde, restricoes_coroinhas, restricoes_funcoes,
            )
            if motivos:
                store.delete(Escala, escala.id)
                escalas.remove(escala)
                resultado['removidos'] += 1
        if missa.ajudante_id:
            motivos = motivos_conflito_ajudante(
                ajudantes_por_id.get(str(missa.ajudante_id)), missa, restricoes_ajudantes
            )
            if motivos:
                for ea in [e for e in escalas_ajudantes if str(e.missa_id) == missa.id]:
                    store.delete(EscalaAjudante, ea.id)
                    escalas_ajudantes.remove(ea)
                missa.ajudante_id = None
                save_record(missa)
                resultado['ajudantes_removidos'] += 1

    for missa in missas_alvo:
        funcoes_da_missa = MOLDES_LITURGICOS.get(missa.tipo_missa, [])

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
            telefones_na_missa = [coroinhas_por_id[str(e.coroinha_id)].responsavel_telefone for e in escalados_agora if str(e.coroinha_id) in coroinhas_por_id]

            candidatos_validos = []
            for candidato in coroinhas:
                if not candidato.ativo:
                    continue
                if any(str(e.missa_id) == missa.id and str(e.coroinha_id) == candidato.id for e in escalas): continue

                # já escalado em outra missa deste fim de semana
                if candidato.id in coroinhas_ocupados: continue

                # mesma regra usada para validar quem já está escalado
                if motivos_conflito_coroinha(candidato, missa, item['funcao'], funcoes_da_missa, restricoes_coroinhas, restricoes_funcoes): continue

                candidatos_validos.append(candidato)

            if candidatos_validos:
                random.shuffle(candidatos_validos)
                candidatos_validos.sort(key=lambda c: (not c.responsavel_telefone in telefones_na_missa, sum(1 for escala in escalas if str(escala.coroinha_id) == c.id)))
                nova_escala = create_record(Escala, coroinha_id=candidatos_validos[0].id, missa_id=missa.id, funcao_atribuida=item['funcao'], status='Confirmado')
                escalas.append(nova_escala)
                resultado['preenchidos'] += 1

        # Passo 2: Sorteio do Ajudante (Garante pais na mesma missa)
        escalas_finais = [e for e in escalas if str(e.missa_id) == missa.id]
        if escalas_finais and not missa.ajudante_id:
            ajudantes_disponiveis = []
            for ajud in ajudantes:
                if not ajud.ativo:
                    continue
                # ajudante já responsável por outra missa deste fim de semana
                if ajud.id in ajudantes_ocupados: continue

                if motivos_conflito_ajudante(ajud, missa, restricoes_ajudantes):
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
                resultado['ajudantes_preenchidos'] += 1
    return resultado


def mensagem_do_resultado(resultado):
    partes = []
    removidos = resultado['removidos'] + resultado['ajudantes_removidos']
    preenchidos = resultado['preenchidos'] + resultado['ajudantes_preenchidos']
    if removidos:
        partes.append(f'{removidos} escalado(s) em conflito removido(s)')
    if preenchidos:
        partes.append(f'{preenchidos} vaga(s) preenchida(s)')
    if not partes:
        return 'Nada a gerar: não há conflitos nem vagas que possam ser preenchidas nas missas futuras.'
    return 'Escala atualizada: ' + ' e '.join(partes) + '.'


@app.route('/escala/gerar', methods=['POST'])
def gerar_escala_automatica():
    flash(mensagem_do_resultado(preencher_escalas_pendentes()), 'success')
    return redirect(url_for('escalas'))

@app.route('/escala/regerar/<id>', methods=['POST'])
def regerar_escala(id):
    missa = get_record(Missa, id)
    if missa.data_hora < agora_local():
        abort(400, description='Não é possível refazer a escala de uma missa que já passou.')
    limpar_escala_da_missa(missa)
    save_record(missa)
    flash(mensagem_do_resultado(preencher_escalas_pendentes(missa_ids={missa.id})), 'success')
    return redirect(url_for('escalas'))

@app.route('/escala/deletar/<id>', methods=['POST'])
def deletar_escala(id):
    store.delete(Escala, id)
    return redirect(url_for('escalas'))

if __name__ == '__main__':
    app.run(debug=False)
