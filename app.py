import random
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///paroquia.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# 1. Tabelas do Banco de Dados
class Coroinha(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    telefone_jovem = db.Column(db.String(20), nullable=True) # Novo
    tipo = db.Column(db.String(20), nullable=False, default='Coroinha')
    
    responsavel_nome = db.Column(db.String(100), nullable=False)
    responsavel_telefone = db.Column(db.String(20), nullable=False)
    responsavel2_nome = db.Column(db.String(100), nullable=True) # Novo
    responsavel2_telefone = db.Column(db.String(20), nullable=True) # Novo
    
    ativo = db.Column(db.Boolean, default=True)
    restricoes = db.relationship('Restricao', backref='coroinha', lazy=True)
    escalas = db.relationship('Escala', backref='coroinha', lazy=True)

class Restricao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_exata = db.Column(db.Date, nullable=False)
    periodo = db.Column(db.String(50), nullable=False) # Adicionamos o período de volta
    coroinha_id = db.Column(db.Integer, db.ForeignKey('coroinha.id'), nullable=False)

class RestricaoFuncao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    funcao_proibida = db.Column(db.String(50), nullable=False) # Ex: 'Levar a Cruz', 'Turíbulo'
    coroinha_id = db.Column(db.Integer, db.ForeignKey('coroinha.id'), nullable=False)

class Missa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(100), nullable=False)
    data_hora = db.Column(db.DateTime, nullable=False)
    tipo_missa = db.Column(db.String(20), nullable=False, default='Tradicional')
    ajudante_nome = db.Column(db.String(100), nullable=True) # Novo: Salva o adulto sorteado
    escalas = db.relationship('Escala', backref='missa', lazy=True)

class Escala(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    coroinha_id = db.Column(db.Integer, db.ForeignKey('coroinha.id'), nullable=False)
    missa_id = db.Column(db.Integer, db.ForeignKey('missa.id'), nullable=False)
    funcao_atribuida = db.Column(db.String(50), nullable=True) # Nova coluna para a função
    status = db.Column(db.String(20), default='Confirmado')

# 2. Rotas do Backend

# Rota Principal (Dashboard): Puxa os coroinhas do banco e envia para o HTML
@app.route('/')
def index():
    todos_coroinhas = Coroinha.query.all()
    return render_template('index.html', coroinhas=todos_coroinhas)

# Rota de Criação: Recebe os dados do formulário HTML e salva no banco
@app.route('/coroinha/novo', methods=['POST'])
def novo_coroinha():
    nome = request.form.get('nome')
    telefone_jovem = request.form.get('telefone_jovem')
    tipo = request.form.get('tipo')
    
    responsavel = request.form.get('responsavel_nome')
    telefone = request.form.get('responsavel_telefone')
    responsavel2 = request.form.get('responsavel2_nome')
    telefone2 = request.form.get('responsavel2_telefone')

    if nome and responsavel and telefone and tipo:
        novo = Coroinha(
            nome=nome, telefone_jovem=telefone_jovem, tipo=tipo,
            responsavel_nome=responsavel, responsavel_telefone=telefone,
            responsavel2_nome=responsavel2, responsavel2_telefone=telefone2
        )
        db.session.add(novo)
        db.session.commit()
        
    return redirect(url_for('index'))

# Rota de Exclusão: Deleta um coroinha baseado no ID
@app.route('/coroinha/deletar/<int:id>')
def deletar_coroinha(id):
    coroinha = Coroinha.query.get(id)
    if coroinha:
        db.session.delete(coroinha)
        db.session.commit()
        
    return redirect(url_for('index'))

# Rota de Edição: Atualiza os dados de um coroinha baseado no ID
@app.route('/coroinha/editar/<int:id>', methods=['POST'])
def editar_coroinha(id):
    coroinha = Coroinha.query.get_or_404(id)
    coroinha.nome = request.form.get('nome')
    coroinha.telefone_jovem = request.form.get('telefone_jovem')
    coroinha.tipo = request.form.get('tipo')
    coroinha.responsavel_nome = request.form.get('responsavel_nome')
    coroinha.responsavel_telefone = request.form.get('responsavel_telefone')
    coroinha.responsavel2_nome = request.form.get('responsavel2_nome')
    coroinha.responsavel2_telefone = request.form.get('responsavel2_telefone')
    
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/missa/editar/<int:id>', methods=['POST'])
def editar_missa(id):
    missa = Missa.query.get_or_404(id)
    missa.descricao = request.form.get('descricao')
    missa.tipo_missa = request.form.get('tipo_missa')
    
    data_hora_str = request.form.get('data_hora')
    if data_hora_str:
        missa.data_hora = datetime.strptime(data_hora_str, '%Y-%m-%dT%H:%M')
        
    db.session.commit()
    return redirect(url_for('missas'))

# ==========================================
# ROTAS DE MISSAS / EVENTOS
# ==========================================

@app.route('/missas')
def missas():
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    
    query = Missa.query
    if data_inicio:
        data_inicio_obj = datetime.strptime(data_inicio, '%Y-%m-%d')
        query = query.filter(Missa.data_hora >= data_inicio_obj)
    if data_fim:
        # Adiciona 23:59:59 para garantir que pegue o dia todo da data final
        data_fim_obj = datetime.strptime(data_fim + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
        query = query.filter(Missa.data_hora <= data_fim_obj)
        
    todas_missas = query.order_by(Missa.data_hora).all()
    return render_template('missas.html', missas=todas_missas, data_inicio=data_inicio, data_fim=data_fim)

@app.route('/missa/nova', methods=['POST'])
def nova_missa():
    descricao = request.form.get('descricao')
    data_hora_str = request.form.get('data_hora') 
    tipo_missa = request.form.get('tipo_missa') # Recebe Tradicional ou Solene

    if descricao and data_hora_str and tipo_missa:
        data_hora_obj = datetime.strptime(data_hora_str, '%Y-%m-%dT%H:%M')
        nova = Missa(descricao=descricao, data_hora=data_hora_obj, tipo_missa=tipo_missa)
        db.session.add(nova)
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
# ROTAS DE RESTRIÇÕES (HORÁRIOS E FUNÇÕES)
# ==========================================

@app.route('/coroinha/<int:id>/restricoes')
def restricoes(id):
    coroinha = Coroinha.query.get_or_404(id)
    # Puxa as restrições específicas deste coroinha
    restricoes_horario = Restricao.query.filter_by(coroinha_id=id).all()
    restricoes_funcao = RestricaoFuncao.query.filter_by(coroinha_id=id).all()
    
    return render_template('restricoes.html', coroinha=coroinha, horarios=restricoes_horario, funcoes=restricoes_funcao)

@app.route('/coroinha/<int:id>/restricao_data/nova', methods=['POST'])
def nova_restricao_data(id):
    data_str = request.form.get('data_exata')
    periodo = request.form.get('periodo')
    
    if data_str and periodo:
        data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
        nova = Restricao(data_exata=data_obj, periodo=periodo, coroinha_id=id)
        db.session.add(nova)
        db.session.commit()
        
    return redirect(url_for('restricoes', id=id))

@app.route('/coroinha/<int:id>/restricao_funcao/nova', methods=['POST'])
def nova_restricao_funcao(id):
    funcao = request.form.get('funcao_proibida')
    if funcao:
        nova = RestricaoFuncao(funcao_proibida=funcao, coroinha_id=id)
        db.session.add(nova)
        db.session.commit()
    return redirect(url_for('restricoes', id=id))

@app.route('/restricao_data/deletar/<int:id>')
def deletar_restricao_data(id):
    restricao = Restricao.query.get(id)
    if restricao:
        coroinha_id = restricao.coroinha_id
        db.session.delete(restricao)
        db.session.commit()
        return redirect(url_for('restricoes', id=coroinha_id))
    return redirect(url_for('index'))

@app.route('/restricao_funcao/deletar/<int:id>')
def deletar_restricao_funcao(id):
    restricao = RestricaoFuncao.query.get(id)
    if restricao:
        coroinha_id = restricao.coroinha_id
        db.session.delete(restricao)
        db.session.commit()
        return redirect(url_for('restricoes', id=coroinha_id))
    return redirect(url_for('index'))

# ==========================================
# ROTAS E ALGORITMO DE ESCALAS
# ==========================================

@app.route('/escalas')
def escalas():
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    
    query = Missa.query
    if data_inicio:
        data_inicio_obj = datetime.strptime(data_inicio, '%Y-%m-%d')
        query = query.filter(Missa.data_hora >= data_inicio_obj)
    if data_fim:
        data_fim_obj = datetime.strptime(data_fim + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
        query = query.filter(Missa.data_hora <= data_fim_obj)
        
    todas_missas = query.order_by(Missa.data_hora).all()
    return render_template('escalas.html', missas=todas_missas, data_inicio=data_inicio, data_fim=data_fim)

@app.route('/escala/gerar', methods=['POST'])
def gerar_escala_automatica():
    missas = Missa.query.all()
    
    molde_solene = [
        {'funcao': 'Acólito (Missal)', 'exigencia': 'Acólito'},
        {'funcao': 'Acólito (Turíbulo)', 'exigencia': 'Acólito'},
        {'funcao': 'Acólito (Naveta)', 'exigencia': 'Acólito'},
        {'funcao': 'Cruciferário (Cruz)', 'exigencia': 'Coroinha'},
        {'funcao': 'Ceriferário (Vela 1)', 'exigencia': 'Coroinha'},
        {'funcao': 'Ceriferário (Vela 2)', 'exigencia': 'Coroinha'},
        {'funcao': 'Jarra', 'exigencia': 'Coroinha'},
        {'funcao': 'Bacia/Lavabo', 'exigencia': 'Coroinha'}
    ]
    
    molde_tradicional = [
        {'funcao': 'Acólito (Missal)', 'exigencia': 'Acólito'},
        {'funcao': 'Cruciferário (Cruz)', 'exigencia': 'Coroinha'},
        {'funcao': 'Ceriferário (Vela 1)', 'exigencia': 'Coroinha'},
        {'funcao': 'Ceriferário (Vela 2)', 'exigencia': 'Coroinha'},
        {'funcao': 'Jarra', 'exigencia': 'Coroinha'},
        {'funcao': 'Bacia/Lavabo', 'exigencia': 'Coroinha'}
    ]

    for missa in missas:
        funcoes_da_missa = molde_solene if missa.tipo_missa == 'Solene' else molde_tradicional
        
        hora_missa = missa.data_hora.hour
        if hora_missa < 12:
            periodo_missa = 'Manhã'
        elif hora_missa < 18:
            periodo_missa = 'Tarde'
        else:
            periodo_missa = 'Noite'

        for item in funcoes_da_missa:
            funcao_atual = item['funcao']
            tipo_exigido = item['exigencia']

            ja_preenchida = Escala.query.filter_by(missa_id=missa.id, funcao_atribuida=funcao_atual).first()
            if ja_preenchida:
                continue

            # Lista todos os telefones de quem JÁ ESTÁ escalado nesta missa
            escalados_agora = Escala.query.filter_by(missa_id=missa.id).all()
            telefones_na_missa = [e.coroinha.responsavel_telefone for e in escalados_agora]

            candidatos_validos = []
            candidatos_base = Coroinha.query.filter_by(ativo=True, tipo=tipo_exigido).all()

            for candidato in candidatos_base:
                if Escala.query.filter_by(missa_id=missa.id, coroinha_id=candidato.id).first():
                    continue

                bloqueado_por_data = False
                for rest in Restricao.query.filter_by(coroinha_id=candidato.id).all():
                    if rest.data_exata == missa.data_hora.date() and (rest.periodo == periodo_missa or rest.periodo == 'Dia Todo'):
                        bloqueado_por_data = True
                        break
                if bloqueado_por_data:
                    continue

                bloqueado_por_funcao = False
                for rest_func in RestricaoFuncao.query.filter_by(coroinha_id=candidato.id).all():
                    if rest_func.funcao_proibida in funcao_atual:
                        bloqueado_por_funcao = True
                        break
                if bloqueado_por_funcao:
                    continue

                candidatos_validos.append(candidato)

            if not candidatos_validos:
                continue 

            # Embaralha para evitar ordem alfabética
            random.shuffle(candidatos_validos)
            
            # Ordenação Dupla: 1º Quem tem irmão na missa | 2º Quem tem menos escalas no mês
            def criterio_ordenacao(c):
                tem_irmao_na_missa = c.responsavel_telefone in telefones_na_missa
                qtd_escalas = Escala.query.filter_by(coroinha_id=c.id).count()
                # 'not tem_irmao_na_missa' faz com que True (tem irmão) vire 0 e venha primeiro na lista
                return (not tem_irmao_na_missa, qtd_escalas)
                
            candidatos_validos.sort(key=criterio_ordenacao)

            escolhido = candidatos_validos[0]
            nova_escala = Escala(coroinha_id=escolhido.id, missa_id=missa.id, funcao_atribuida=funcao_atual)
            db.session.add(nova_escala)
            db.session.flush() 

        # Sorteio do Ajudante (ocorre no final, quando as vagas da missa já foram preenchidas)
        escalas_finais = Escala.query.filter_by(missa_id=missa.id).all()
        # Se a missa já tem coroinhas e ainda não tem um ajudante sorteado
        if escalas_finais and not missa.ajudante_nome:
            responsaveis_possiveis = []
            for escala in escalas_finais:
                responsaveis_possiveis.append(f"{escala.coroinha.responsavel_nome} (Tel: {escala.coroinha.responsavel_telefone})")
                if escala.coroinha.responsavel2_nome: # Inclui o responsável 2 no sorteio, se existir
                    responsaveis_possiveis.append(f"{escala.coroinha.responsavel2_nome} (Tel: {escala.coroinha.responsavel2_telefone})")
            
            # Sorteia um nome garantindo que não haja duplicatas na lista de sorteio
            missa.ajudante_nome = random.choice(list(set(responsaveis_possiveis)))

    db.session.commit()
    return redirect(url_for('escalas'))

@app.route('/escala/regerar/<int:id>', methods=['POST'])
def regerar_escala(id):
    missa = Missa.query.get_or_404(id)
    # Limpa as escalas dessa missa específica e remove o ajudante antigo
    Escala.query.filter_by(missa_id=id).delete()
    missa.ajudante_nome = None
    db.session.commit()
    
    # Chama a função principal de gerar escalas apenas para preencher esta que ficou vazia
    gerar_escala_automatica()
    
    return redirect(url_for('escalas'))

@app.route('/escala/deletar/<int:id>')
def deletar_escala(id):
    # Rota para a coordenadora remover um coroinha específico da missa manualmente, caso necessário
    escala = Escala.query.get(id)
    if escala:
        db.session.delete(escala)
        db.session.commit()
    return redirect(url_for('escalas'))

if __name__ == '__main__':
    app.run(debug=True)
