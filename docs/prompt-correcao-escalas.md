# Prompt: correção de escalas que ignoram restrições

> Cole o texto abaixo no Claude Code (ou use como briefing), com o repositório `projeto_coroinhas` aberto na branch `redesign-moderno`.

---

## Contexto

Este é um app Flask (`app.py`) com Firestore (`firestore_repository.py`, `firebase_store.py`) que gera escalas de coroinhas e ajudantes para as missas da paróquia. O site está na Vercel (`projeto-coroinhas.vercel.app`). As instruções de configuração local estão em `OPERACAO.md`.

A coordenadora relatou que coroinhas com restrição estão aparecendo escalados em missas onde não poderiam. **O gerador em si filtra as restrições corretamente** (`preencher_escalas_pendentes`). O problema foi diagnosticado assim:

- As escalas atuais foram geradas em **outubro**, quando ainda não havia restrições de data cadastradas.
- Depois, as **missas foram reaproveitadas**: em vez de criar missas novas, a data/hora (e às vezes o tipo) das missas de outubro foi editada para dezembro e janeiro.
- `editar_missa` muda `data_hora` e `tipo_missa`, mas **mantém as escalas e o ajudante vinculados**, sem revalidar nada.
- `preencher_escalas_pendentes` **só preenche funções vazias**; nunca revalida quem já está escalado.
- Cadastrar uma restrição nova (de data ou de função) **não afeta escalas existentes** e a tela de escalas não mostra nenhum aviso.

Resultado: de 126 escalas, 59 violam restrições de data/período ou de função.

## O que fazer

### 1. Impedir que o problema se repita

1. **Edição de missa:** em `editar_missa`, se `data_hora` ou `tipo_missa` mudar, remover as escalas da missa (`Escala` e `EscalaAjudante`) e limpar `ajudante_id`, da mesma forma que `regerar_escala` já faz. Mostrar à usuária que a escala daquela missa precisa ser gerada de novo (ou gerar automaticamente só para ela). Se o tipo mudar, funções que não existem no novo molde também não podem ficar.
2. **Função única de conflito:** criar uma função reutilizável (por exemplo `conflitos_da_escala(escala, missa)`) que diga se um escalado viola restrição de data/período, restrição de função, ou grau exigido (`Coroinha`/`Acólito`). Usar a **mesma regra** do gerador (período: `< 12h` Manhã, `< 18h` Tarde, senão Noite; `Dia Todo` bloqueia o dia inteiro). Fazer o mesmo para ajudantes com `RestricaoAjudante`. O gerador deve passar a usar essa função, para as regras não divergirem.
3. **Aviso na tela de escalas** (`templates/escalas.html`): marcar visualmente cada escalado em conflito, com o motivo (ex.: "restrição Dia Todo em 05/12", "função proibida"), e um resumo no topo com a quantidade de conflitos.
4. **"Gerar escala" deve corrigir conflitos:** antes de preencher vagas, remover escalados (e ajudantes) que estejam em conflito, para que a vaga seja preenchida de novo por alguém válido. Manter o restante da escala intacto.
5. **Gerar só missas futuras:** `preencher_escalas_pendentes` hoje percorre todas as missas, inclusive passadas. Limitar a missas com `data_hora >= agora`.
6. **`regerar_escala`** hoje chama o gerador para todas as missas; fazer com que regenere apenas a missa escolhida (respeitando o limite de uma escala por fim de semana com base nas outras missas).

### 2. Cuidados técnicos

- **IDs mistos:** nos dados migrados do SQLite, campos como `coroinha_id`, `missa_id` e `ajudante_id` são **inteiros**, enquanto `Document.id` é **string**. Sempre comparar com `str(...)`, como o código atual faz.
- `data_exata` é gravada como texto ISO e o `Document` converte para `date`; `data_hora` vem do Firestore com fuso e é convertida para `datetime` sem fuso.
- Cada `create`/`save` limpa o cache do repositório. Dentro do gerador, trabalhar com as listas carregadas no início (como já é feito) para não multiplicar leituras.
- Há uma correção ainda **não commitada** no working tree: `ativo=True` no cadastro de coroinha (`app.py`) e `ativo` ausente tratado como `True` em `firestore_repository.py`. Incluí-la no mesmo PR ou em um commit separado.
- Mensagens e textos da interface em português.

### 3. Dados de produção (não alterar sem autorização)

- **Não grave no Firestore de produção** sem antes fazer backup e sem aprovação da coordenação. Para testar, use um projeto Firebase separado ou um repositório falso em memória.
- Depois do deploy, a coordenação deve usar o "Gerar escala" corrigido (que remove conflitos) ou "Regerar" nas missas de dezembro/janeiro.
- Levantar para a coordenação, **sem corrigir automaticamente**, as restrições com datas suspeitas: há registros em `2026-01-01`, `2026-02-12`, `2026-02-26`, `2026-06-13`, `2026-06-19`, `2026-11-25` e `2027-12-27`, que provavelmente eram para 2027-01-01 e 2026-12-27. Opcional: na tela de restrições, avisar ao cadastrar uma data no passado ou a mais de 6 meses.
- A missa "NATAL – sexta-feira – Capela" (25/12 às 9h30) está sem nenhum escalado.

### 4. Testes

Não existem testes no projeto. Criar `tests/` com `pytest`, usando um repositório falso em memória no lugar do Firestore, cobrindo pelo menos:

- coroinha com restrição `Dia Todo` / do período da missa não é escalado; restrição de outro período não bloqueia;
- coroinha com função proibida não recebe aquela função;
- editar a data de uma missa remove as escalas antigas;
- "Gerar" remove um escalado que passou a ter restrição e preenche a vaga com outra pessoa;
- a mesma pessoa não é escalada duas vezes no mesmo fim de semana;
- missas passadas não são alteradas pelo gerador;
- ajudantes respeitam `RestricaoAjudante`.

## Pronto quando

- Os testes acima passam.
- Editar a data/tipo de uma missa não deixa escala antiga pendurada.
- A tela de escalas mostra conflitos, e "Gerar escala" os resolve.
- Nenhum dado de produção foi alterado sem backup e autorização.
- PR aberto contra `main` a partir de `redesign-moderno` (ou de uma branch derivada dela), com descrição do problema e das mudanças.
