import sqlite3
import os

# Caminhos para os arquivos na pasta instance
db_antigo = os.path.join('instance', 'antigo.db')
db_novo = os.path.join('instance', 'paroquia.db')

# Conectar aos bancos
con_antigo = sqlite3.connect(db_antigo)
con_novo = sqlite3.connect(db_novo)
cur_a = con_antigo.cursor()
cur_n = con_novo.cursor()

try:
    print("Iniciando migração de dados...")

    # 1. Migrar Coroinhas
    cur_a.execute("SELECT id, nome, telefone_jovem, tipo, responsavel_nome, responsavel_telefone, responsavel2_nome, responsavel2_telefone, ativo FROM coroinha")
    coroinhas = cur_a.fetchall()
    cur_n.executemany("INSERT INTO coroinha (id, nome, telefone_jovem, tipo, responsavel_nome, responsavel_telefone, responsavel2_nome, responsavel2_telefone, ativo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", coroinhas)
    print(f"✅ {len(coroinhas)} Coroinhas migrados.")

    # 2. Migrar Restrições de Data e Função
    cur_a.execute("SELECT id, data_exata, periodo, coroinha_id FROM restricao")
    cur_n.executemany("INSERT INTO restricao (id, data_exata, periodo, coroinha_id) VALUES (?, ?, ?, ?)", cur_a.fetchall())
    
    cur_a.execute("SELECT id, funcao_proibida, coroinha_id FROM restricao_funcao")
    cur_n.executemany("INSERT INTO restricao_funcao (id, funcao_proibida, coroinha_id) VALUES (?, ?, ?)", cur_a.fetchall())
    print("✅ Restrições migradas.")

    # 3. Migrar Missas (Substituindo o antigo ajudante em texto por NULL para a nova chave estrangeira)
    cur_a.execute("SELECT id, descricao, data_hora, tipo_missa FROM missa")
    missas_novo = [(m[0], m[1], m[2], m[3], None) for m in cur_a.fetchall()]
    cur_n.executemany("INSERT INTO missa (id, descricao, data_hora, tipo_missa, ajudante_id) VALUES (?, ?, ?, ?, ?)", missas_novo)
    print(f"✅ {len(missas_novo)} Missas migradas.")

    # 4. Migrar Escalas
    cur_a.execute("SELECT id, coroinha_id, missa_id, funcao_atribuida, status FROM escala")
    cur_n.executemany("INSERT INTO escala (id, coroinha_id, missa_id, funcao_atribuida, status) VALUES (?, ?, ?, ?, ?)", cur_a.fetchall())
    print("✅ Escalas migradas.")

    # 5. Migração Inteligente: Transformar Responsáveis 1 em Ajudantes e vincular aos filhos
    cur_a.execute("SELECT DISTINCT responsavel_nome, responsavel_telefone FROM coroinha WHERE responsavel_nome IS NOT NULL AND responsavel_nome != ''")
    responsaveis = cur_a.fetchall()
    
    ajudante_id = 1
    vinculos = 0
    for resp in responsaveis:
        nome, telefone = resp
        cur_n.execute("INSERT INTO ajudante (id, nome, telefone, ativo) VALUES (?, ?, ?, 1)", (ajudante_id, nome, telefone))
        
        # Encontra todos os filhos desse responsável específico para criar o vínculo
        cur_a.execute("SELECT id FROM coroinha WHERE responsavel_nome = ? AND responsavel_telefone = ?", (nome, telefone))
        filhos = cur_a.fetchall()
        for filho in filhos:
            cur_n.execute("INSERT INTO ajudante_coroinha (ajudante_id, coroinha_id) VALUES (?, ?)", (ajudante_id, filho[0]))
            vinculos += 1
        
        ajudante_id += 1
        
    print(f"✅ {len(responsaveis)} Ajudantes cadastrados automaticamente e {vinculos} vínculos familiares criados.")

    # Salva todas as alterações
    con_novo.commit()
    print("\n🚀 Migração concluída com sucesso! Pode iniciar o servidor (python app.py).")

except Exception as e:
    print(f"\n❌ Erro durante a migração: {e}")

finally:
    con_antigo.close()
    con_novo.close()