import random
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///paroquia.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ==========================================
# 1. TABELAS DO BANCO DE DADOS
# ==========================================

# Tabela de Associação (Muitos-para-Muitos) entre Ajudantes(Pais) e Coroinhas(Filhos)
ajudante_coroinha = db.Table('ajudante_coroinha',
    db.Column('ajudante_id', db.Integer, db.ForeignKey('ajudante.id'), primary_key=True),
    db.Column('coroinha_id', db.Integer, db.ForeignKey('coroinha.id'), primary_key=True)
)

class Ajudante(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    telefone = db.Column(db.String(20), nullable=False)
    ativo = db.Column(db.Boolean, default=True)
    coroinhas_vinculados = db.relationship('Coroinha', secondary=ajudante_coroinha, backref=db.backref('responsaveis_cadastrados', lazy=True))
    restricoes = db.relationship('RestricaoAjudante', backref='ajudante', lazy=True, cascade="all, delete-orphan")
    escalas = db.relationship('EscalaAjudante', backref='ajudante', lazy=True, cascade="all, delete-orphan")

class RestricaoAjudante(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_exata = db.Column(db.Date, nullable=False)
    periodo = db.Column(db.String(50), nullable=False)
    ajudante_id = db.Column(db.Integer, db.ForeignKey('ajudante.id'), nullable=False)

class Coroinha(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    telefone_jovem = db.Column(db.String(20), nullable=True)
    tipo = db.Column(db.String(20), nullable=False, default='Coroinha')
    responsavel_nome = db.Column(db.String(100), nullable=False)
    responsavel_telefone = db.Column(db.String(20), nullable=False)
    responsavel2_nome = db.Column(db.String(100), nullable=True)
    responsavel2_telefone = db.Column(db.String(20), nullable=True)
    ativo = db.Column(db.Boolean, default=True)
    restricoes = db.relationship('Restricao', backref='coroinha', lazy=True, cascade="all, delete-orphan")
    restricoes_funcao = db.relationship('RestricaoFuncao', backref='coroinha', lazy=True, cascade="all, delete-orphan")
    escalas = db.relationship('Escala', backref='coroinha', lazy=True, cascade="all, delete-orphan")

class Restricao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_exata = db.Column(db.Date, nullable=False)
    periodo = db.Column(db.String(50), nullable=False)
    coroinha_id = db.Column(db.Integer, db.ForeignKey('coroinha.id'), nullable=False)

class RestricaoFuncao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    funcao_proibida = db.Column(db.String(50), nullable=False)
    coroinha_id = db.Column(db.Integer, db.ForeignKey('coroinha.id'), nullable=False)

class Missa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(100), nullable=False)
    data_hora = db.Column(db.DateTime, nullable=False)
    tipo_missa = db.Column(db.String(20), nullable=False, default='Tradicional')
    ajudante_id = db.Column(db.Integer, db.ForeignKey('ajudante.id'), nullable=True)
    ajudante = db.relationship('Ajudante', backref='missas_ajudadas')
    escalas = db.relationship('Escala', backref='missa', lazy=True, cascade="all, delete-orphan")
    escalas_ajudante = db.relationship('EscalaAjudante', backref='missa', lazy=True, cascade="all, delete-orphan")

class Escala(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    coroinha_id = db.Column(db.Integer, db.ForeignKey('coroinha.id'), nullable=False)
    missa_id = db.Column(db.Integer, db.ForeignKey('missa.id'), nullable=False)
    funcao_atribuida = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), default='Confirmado')

class EscalaAjudante(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ajudante_id = db.Column(db.Integer, db.ForeignKey('ajudante.id'), nullable=False)
    missa_id = db.Column(db.Integer, db.ForeignKey('missa.id'), nullable=False)


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
    return render_template('index.html', coroinhas=Coroinha.query.all())

@app.route('/coroinha/novo', methods=['POST'])
def novo_coroinha():
    novo = Coroinha(
        nome=request.form.get('nome'), 
        telefone_jovem=request.form.get('telefone_jovem'), 
        tipo=request.form.get('tipo'),
        responsavel_nome=request.form.get('responsavel_nome'), 
        responsavel_telefone=request.form.get('responsavel_telefone'),
        responsavel2_nome=request.form.get('responsavel2_nome'), 
        responsavel2_telefone=request.form.get('responsavel2_telefone')
    )
    db.session.add(novo)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/coroinha/deletar/<int:id>')
def deletar_coroinha(id):
    coroinha = Coroinha.query.get(id)
    if coroinha:
        db.session.delete(coroinha)
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/coroinha/editar/<int:id>', methods=['POST'])
def editar_coroinha(id):
    c = Coroinha.query.get_or_404(id)
    c.nome, c.telefone_jovem, c.tipo = request.form.get('nome'), request.form.get('telefone_jovem'), request.form.get('tipo')
    c.responsavel_nome, c.responsavel_telefone = request.form.get('responsavel_nome'), request.form.get('responsavel_telefone')
    c.responsavel2_nome, c.responsavel2_telefone = request.form.get('responsavel2_nome'), request.form.get('responsavel2_telefone')
    db.session.commit()
    return redirect(url_for('index'))


# ==========================================
# 4. ROTAS DE AJUDANTES (NOVO CRUD)
# ==========================================
@app.route('/ajudantes')
def ajudantes():
    todos_ajudantes = Ajudante.query.all()
    todos_coroinhas = Coroinha.query.all()
    return render_template('ajudantes.html', ajudantes=todos_ajudantes, coroinhas=todos_coroinhas)

@app.route('/ajudante/novo', methods=['POST'])
def novo_ajudante():
    novo = Ajudante(nome=request.form.get('nome'), telefone=request.form.get('telefone'))
    
    # Vincula múltiplos filhos se selecionados
    filhos_ids = request.form.getlist('coroinhas_vinculados')
    for cid in filhos_ids:
        filho = Coroinha.query.get(int(cid))
        if filho: novo.coroinhas_vinculados.append(filho)
            
    db.session.add(novo)
    db.session.commit()
    return redirect(url_for('ajudantes'))

@app.route('/ajudante/deletar/<int:id>')
def deletar_ajudante(id):
    ajudante = Ajudante.query.get(id)
    if ajudante:
        db.session.delete(ajudante)
        db.session.commit()
    return redirect(url_for('ajudantes'))

@app.route('/ajudante/<int:id>/restricao/nova', methods=['POST'])
def nova_restricao_ajudante(id):
    data_obj = datetime.strptime(request.form.get('data_exata'), '%Y-%m-%d').date()
    nova = RestricaoAjudante(data_exata=data_obj, periodo=request.form.get('periodo'), ajudante_id=id)
    db.session.add(nova)
    db.session.commit()
    return redirect(url_for('ajudantes'))


# ==========================================
# 5. ROTAS DE MISSAS E EVENTOS
# ==========================================
@app.route('/missas')
def missas():
    query = Missa.query
    if request.args.get('data_inicio'):
        query = query.filter(Missa.data_hora >= datetime.strptime(request.args.get('data_inicio'), '%Y-%m-%d'))
    if request.args.get('data_fim'):
        query = query.filter(Missa.data_hora <= datetime.strptime(request.args.get('data_fim') + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
    return render_template('missas.html', missas=query.order_by(Missa.data_hora).all(), data_inicio=request.args.get('data_inicio'), data_fim=request.args.get('data_fim'))

@app.route('/missa/nova', methods=['POST'])
def nova_missa():
    nova = Missa(
        descricao=request.form.get('descricao'), 
        data_hora=datetime.strptime(request.form.get('data_hora'), '%Y-%m-%dT%H:%M'), 
        tipo_missa=request.form.get('tipo_missa')
    )
    db.session.add(nova)
    db.session.commit()
    return redirect(url_for('missas'))

@app.route('/missa/editar/<int:id>', methods=['POST'])
def editar_missa(id):
    m = Missa.query.get_or_404(id)
    m.descricao, m.tipo_missa = request.form.get('descricao'), request.form.get('tipo_missa')
    if request.form.get('data_hora'): m.data_hora = datetime.strptime(request.form.get('data_hora'), '%Y-%m-%dT%H:%M')
    db.session.commit()
    return redirect(url_for('missas'))

@app.route('/missa/deletar/<int:id>')
def deletar_missa(id):
    missa = Missa.query.get(id)
    if missa:
        db.session.delete(missa)
        db.session.commit()
    return redirect(url_for('missas'))


# ==========================================
# 6. RESTRIÇÕES DE COROINHAS
# ==========================================
@app.route('/coroinha/<int:id>/restricoes')
def restricoes(id):
    c = Coroinha.query.get_or_404(id)
    return render_template('restricoes.html', coroinha=c, horarios=Restricao.query.filter_by(coroinha_id=id).all(), funcoes=RestricaoFuncao.query.filter_by(coroinha_id=id).all())

@app.route('/coroinha/<int:id>/restricao_data/nova', methods=['POST'])
def nova_restricao_data(id):
    nova = Restricao(data_exata=datetime.strptime(request.form.get('data_exata'), '%Y-%m-%d').date(), periodo=request.form.get('periodo'), coroinha_id=id)
    db.session.add(nova)
    db.session.commit()
    return redirect(url_for('restricoes', id=id))

@app.route('/coroinha/<int:id>/restricao_funcao/nova', methods=['POST'])
def nova_restricao_funcao(id):
    db.session.add(RestricaoFuncao(funcao_proibida=request.form.get('funcao_proibida'), coroinha_id=id))
    db.session.commit()
    return redirect(url_for('restricoes', id=id))

@app.route('/restricao_data/deletar/<int:id>')
def deletar_restricao_data(id):
    r = Restricao.query.get(id)
    if r: db.session.delete(r); db.session.commit(); return redirect(url_for('restricoes', id=r.coroinha_id))
    return redirect(url_for('index'))

@app.route('/restricao_funcao/deletar/<int:id>')
def deletar_restricao_funcao(id):
    r = RestricaoFuncao.query.get(id)
    if r: db.session.delete(r); db.session.commit(); return redirect(url_for('restricoes', id=r.coroinha_id))
    return redirect(url_for('index'))


# ==========================================
# 7. GERADOR DE WHATSAPP E MOTOR DE ESCALAS
# ==========================================
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
    query = Missa.query
    if request.args.get('data_inicio'): query = query.filter(Missa.data_hora >= datetime.strptime(request.args.get('data_inicio'), '%Y-%m-%d'))
    if request.args.get('data_fim'): query = query.filter(Missa.data_hora <= datetime.strptime(request.args.get('data_fim') + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
    
    todas_missas = query.order_by(Missa.data_hora).all()
    texto_wpp = gerar_texto_whatsapp(todas_missas)
    
    return render_template('escalas.html', missas=todas_missas, texto_whatsapp=texto_wpp, data_inicio=request.args.get('data_inicio'), data_fim=request.args.get('data_fim'))

@app.route('/escala/gerar', methods=['POST'])
def gerar_escala_automatica():
    missas = Missa.query.all()

    for missa in missas:
        funcoes_da_missa = MOLDES_LITURGICOS.get(missa.tipo_missa, [])
        hora = missa.data_hora.hour
        periodo_missa = 'Manhã' if hora < 12 else 'Tarde' if hora < 18 else 'Noite'

        # Passo 1: Preencher Coroinhas e Acólitos
        for item in funcoes_da_missa:
            if Escala.query.filter_by(missa_id=missa.id, funcao_atribuida=item['funcao']).first(): continue

            escalados_agora = Escala.query.filter_by(missa_id=missa.id).all()
            telefones_na_missa = [e.coroinha.responsavel_telefone for e in escalados_agora]

            candidatos_validos = []
            for candidato in Coroinha.query.filter_by(ativo=True, tipo=item['exigencia']).all():
                if Escala.query.filter_by(missa_id=missa.id, coroinha_id=candidato.id).first(): continue
                
                if any(r.data_exata == missa.data_hora.date() and r.periodo in [periodo_missa, 'Dia Todo'] for r in candidato.restricoes): continue
                if any(item['funcao'] in r.funcao_proibida for r in RestricaoFuncao.query.filter_by(coroinha_id=candidato.id).all()): continue
                
                candidatos_validos.append(candidato)

            if candidatos_validos:
                random.shuffle(candidatos_validos)
                candidatos_validos.sort(key=lambda c: (not c.responsavel_telefone in telefones_na_missa, Escala.query.filter_by(coroinha_id=c.id).count()))
                db.session.add(Escala(coroinha_id=candidatos_validos[0].id, missa_id=missa.id, funcao_atribuida=item['funcao']))
                db.session.flush()

        # Passo 2: Sorteio do Ajudante (Garante pais na mesma missa)
        escalas_finais = Escala.query.filter_by(missa_id=missa.id).all()
        if escalas_finais and not missa.ajudante_id:
            ajudantes_disponiveis = []
            for ajud in Ajudante.query.filter_by(ativo=True).all():
                if not any(r.data_exata == missa.data_hora.date() and r.periodo in [periodo_missa, 'Dia Todo'] for r in ajud.restricoes):
                    if not EscalaAjudante.query.filter_by(missa_id=missa.id, ajudante_id=ajud.id).first():
                        ajudantes_disponiveis.append(ajud)
            
            if ajudantes_disponiveis:
                ids_na_missa = [e.coroinha_id for e in escalas_finais]
                # Filtra os ajudantes que tem filhos escalados nesta missa específica
                pais_na_missa = [a for a in ajudantes_disponiveis if any(filho.id in ids_na_missa for filho in a.coroinhas_vinculados)]
                
                escolhido = random.choice(pais_na_missa) if pais_na_missa else random.choice(ajudantes_disponiveis)
                missa.ajudante_id = escolhido.id
                db.session.add(EscalaAjudante(ajudante_id=escolhido.id, missa_id=missa.id))

    db.session.commit()
    return redirect(url_for('escalas'))

@app.route('/escala/regerar/<int:id>', methods=['POST'])
def regerar_escala(id):
    Escala.query.filter_by(missa_id=id).delete()
    EscalaAjudante.query.filter_by(missa_id=id).delete()
    missa = Missa.query.get_or_404(id)
    missa.ajudante_id = None
    db.session.commit()
    gerar_escala_automatica()
    return redirect(url_for('escalas'))

@app.route('/escala/deletar/<int:id>')
def deletar_escala(id):
    escala = Escala.query.get(id)
    if escala:
        db.session.delete(escala)
        db.session.commit()
    return redirect(url_for('escalas'))

if __name__ == '__main__':
    app.run(debug=True)