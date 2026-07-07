# Especificação — SaaS de Análise de Faturas (multi-tenant, beta por convite)

> **Para o agente Claude que abrir este projeto:** este documento é o brief oficial
> para construir um app **novo**, multi-tenant, a partir da arquitetura de um projeto
> pessoal de análise de faturas de cartão. **Planeje antes de implementar** — leia esta
> spec inteira, proponha arquitetura + modelo de dados + fluxo de auth, e só codifique
> após aprovação. **Código modular por camadas**, nunca colapsar responsabilidades num
> arquivo só. Aponte riscos e trade-offs com franqueza.
>
> **NÃO é RAG.** A extração é PDF → LLM → dados estruturados, com **conferência humana
> antes de salvar**. Perguntas/agregações são feitas em pandas/SQL sobre dado estruturado.

---

## 1. Objetivo e posicionamento

Transformar um painel financeiro **pessoal** (single-tenant) num **SaaS multi-tenant de
beta fechado**, onde:

- Cada pessoa cria conta (login federado), **o admin aprova** quem pode usar.
- O usuário sobe o PDF da fatura do cartão, **confere/corrige** a extração e salva.
- O usuário vê um **dashboard só com os próprios dados**.

Escopo deliberado: **beta por convite**. Isso limita custo de LLM, superfície de risco e
responsabilidade legal enquanto o produto é validado. Não nascer como produto público.

> **Aviso honesto de viabilidade:** o código é ~30% do trabalho. Os 70% que importam são
> **segurança, isolamento de dados, LGPD e controle de custo** — dado financeiro de
> terceiros é PII sensível. "Funcionar em qualquer banco" é a parte tecnicamente mais
> difícil e nunca será 100%; a conferência antes de salvar é o que torna isso aceitável.

---

## 2. O que PRESERVAR vs REESCREVER (reaproveitamento)

O projeto de referência (pessoal, single-tenant) fica em:
`C:\Users\User\OneDrive - Claro SA\Área de Trabalho\notebook Dell\Diogo Coisas pessoais\Projetos\Financas`
**Essa instância pessoal fica intocada.** Este é um repo NOVO.

**Preservar (copiar as camadas e adaptar):**
- Arquitetura de 2 processos: **Backend FastAPI** (:8001) + **Frontend Streamlit** em
  camadas (`api/` → `dados/` → `componentes/` → `app.py`), **PostgreSQL (Neon)** via
  SQLAlchemy async.
- Fluxo de **upload**: PDF → extração por LLM → **preview editável** (`st.data_editor`)
  → salvar. E a tela de **gerenciar transações** (editar/excluir o dado cru por `id`).
- Camada de gráficos ECharts (adaptador fino que delega ao Baltazar — ver seção 8).

> **Recomendado:** copiar fisicamente do projeto de referência a estrutura de pastas e o
> fluxo de upload/gráficos ANTES de adaptar, para manter fidelidade ao padrão de camadas.

**Reescrever:**
- **Autenticação** (não existe hoje).
- **Isolamento multi-tenant** (`user_id` em tudo).
- **Extração** (hoje é acoplada ao layout do Bradesco — generalizar).

---

## 3. Contas + aprovação por admin

- **Login federado OIDC (Google)** via auth nativo do Streamlit (`st.login`/`st.user`).
  **NÃO** implementar senha própria (não rolar seu próprio auth).
- **Autenticação ≠ autorização:** qualquer conta Google *autentica*; só quem o admin
  **aprovar** é *autorizado* a usar. Deixar isso explícito no código e na UI.
- Tabela `users`: `id`, `email` (único), `nome`, `role` ∈ {`user`, `admin`},
  `status` ∈ {`pending`, `approved`, `blocked`}, `created_at`. Novo usuário nasce
  `pending`.
- **Bootstrap do admin:** e-mails listados em `ADMIN_EMAILS` (variável de ambiente)
  nascem `role='admin'`, `status='approved'`. É assim que o Diogo vira admin no dia 1.
- **Guard de acesso:** só `status='approved'` acessa o dashboard; `pending` vê tela
  "aguardando aprovação"; `blocked` é barrado.
- **Página de admin** (só `role='admin'`): listar, aprovar, bloquear e remover usuários.

---

## 4. Segurança multi-tenant (CRÍTICO)

- **O backend NÃO confia em `user_id` enviado pelo cliente.** Ele **valida o token/sessão
  OIDC por conta própria** em toda requisição e **deriva o `user_id` do token verificado**.
  Aceitar `user_id` de header/body é falha de isolamento trivial de explorar.
- Toda query de dados **filtra por esse `user_id`** derivado do token. Avaliar **Postgres
  RLS** como reforço no nível do banco.
- **Testes de isolamento obrigatórios (critério de aceite):** usuário A **não** pode ler
  nem editar dado do usuário B pela API, mesmo forjando ids.

---

## 5. Remover o Agente de Gastos

- Não portar `agents/`, `chat/`, rotas `/agente`, nem a avaliação do agente.
- **Sem dependência de OpenAI em runtime** (reduz custo e superfície).

---

## 6. Extração genérica (qualquer banco)

- **Schema canônico Pydantic** de transação, com campos **opcionais** onde faz sentido:
  - `date` (obrigatório), `descricao` (obrigatório), `amount` (obrigatório),
    `parcelas?`, `categoria?`, `cidade?`.
  - `cidade` é **nullable** no banco; normalização de cidade (IBGE) só roda **se houver**
    cidade — muitas faturas não têm.
- Trocar o pré-filtro por **regex específico do Bradesco** por extração robusta: enviar o
  **PDF a um modelo com visão** e usar **saída estruturada (Pydantic)**, tolerando
  formatos distintos de data/moeda/idioma e **faturas de múltiplas páginas**.
- **Não** assumir rótulo "PAGTO" nem `UPPERCASE` fixo no tratamento (premissas Bradesco).
- **A conferência antes de salvar é a rede de segurança** contra extração imperfeita: o
  usuário corrige o que o LLM errar. Manter essa etapa clara e à prova de erro.
- **Harness de avaliação com golden set por banco**, usando faturas
  **anonimizadas/sintéticas** (nunca PII real no repo). Métrica de **acurácia por campo**.
  Tratar como parte da entrega, não opcional.

---

## 7. Dados dos usuários (isolamento)

- **Banco SaaS separado** do banco pessoal do Diogo (`DATABASE_URL` próprio).
- **Multi-tenancy row-level:** coluna `user_id` (FK `users`) em **todas** as tabelas de
  dados; toda leitura/escrita filtra por `user_id`.
- Tabela `transactions`: `id`, `user_id` (FK, **`ON DELETE CASCADE`**), `date`,
  `descricao`, `parcelas`, `categoria`, `cidade` (nullable), `amount`.
- **Unicidade:** `(user_id, date, descricao, parcelas, amount)`. O `user_id` na chave
  impede que a fatura de um usuário deduplique contra a de outro; `parcelas` na chave
  impede que parcelas distintas da mesma compra (01/10, 02/10, …) sejam tratadas como
  duplicatas. Insert com `ON CONFLICT DO NOTHING` sobre essas colunas.

---

## 8. Baltazar (dependência de gráficos — fonte única)

Como todos os projetos do Diogo, os gráficos vêm da lib pessoal **Baltazar** — é a
**fonte única**, não duplicar código de gráfico no projeto.

- **Caminho local:** `c:\Users\User\OneDrive - Claro SA\Área de Trabalho\notebook Dell\Diogo Coisas pessoais\Projetos\baltazar`
- **Instalação:** local `pip install -e <caminho>`; deploy via
  `baltazar @ git+https://github.com/Diogohenrique1334/baltazar.git` no `requirements.txt`.
- Gráficos ECharts do dashboard vêm de `baltazar.graficos.graficos_streamlit.graficos`.
  As funções aceitam `cor`/`cores` + `key` e **renderizam** direto. No app, um **adaptador
  fino** só guarda a paleta e delega ao Baltazar. Gráfico que faltar: **criar no Baltazar**
  (aditivo, defaults compatíveis), não duplicar.
- Imports pesados (matplotlib/plotly/requests) são lazy dentro do Baltazar, então o app
  leve importa só os gráficos ECharts sem puxar tudo.

Padrão visual (preferência do Diogo): tema **dark fixo** via `.streamlit/config.toml`,
cards escuros com borda, headings com barra lateral colorida, KPIs em boxes estilizados,
`st.segmented_control` + render condicional em vez de `st.tabs` quando houver ECharts.

---

## 9. Não-funcionais (segurança / custo / LGPD)

- **LGPD:** consentimento no cadastro; botão **"excluir minha conta e meus dados"**
  (cascade real no banco); TLS; **criptografia em repouso**.
- **Custo:** **teto de upload por usuário** (ex.: N/dia) + **limite de tamanho** de
  arquivo. Cada upload dispara uma chamada de LLM.
- **Audit log** de login e uploads (quem fez o quê, quando).
- Segredos **só via variáveis de ambiente**; nada hardcoded.

---

## 10. Fora de escopo (agora)

Produto público aberto (é **beta por convite**), pagamentos/billing, app mobile, front
React/Next. Reavaliar só depois da validação com usuários reais.

---

## 11. Pronto quando (critérios de aceite)

- O admin (`ADMIN_EMAILS`) faz login e **aprova/bloqueia** usuários numa página de admin.
- Um usuário **aprovado** sobe uma fatura de **banco diferente do Bradesco** (com e sem
  cidade), confere o preview, salva e vê **só os próprios dados** no dashboard.
- Um usuário **não-aprovado** é barrado; um usuário **não vê** dado de outro
  (**testes de isolamento passam**).
- **Excluir conta** remove todos os dados daquele usuário (cascade).
- O **golden set** roda e reporta acurácia de extração por banco.

---

## 12. Como o Diogo quer trabalhar

- **Planejamento antes de implementação** não trivial — apreciar o processo.
- **Programação modular por camadas** (módulos dentro de módulos); nunca colapsar
  responsabilidades em arquivos únicos; respeitar a arquitetura existente.
- **Feedback direto e crítico**, sem suavizar — apontar bugs e problemas de design com
  impacto real.
- Ao final, gerar o `CLAUDE.md` do repo (via `/init`, quando já houver código) e sugerir
  atualização de portfólio com métricas e README.
```
