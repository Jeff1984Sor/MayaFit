# CLAUDE.md — MayaFit

> **Leia primeiro.** **MayaFit** (MayaCorp): gestão de estúdios (Pilates, funcional, academias), **multi-tenant com um
> banco por estúdio** e um **admin MayaCorp** para administrar clientes, planos, contratos e cobrança.
> Nasceu como clone do `Pilates_NovaVersao` (reescrita do Studio Mayris); o Mayris vira **um estúdio** do MayaFit.
> Nome, logo e cor de cada estúdio vêm de Configurações › Identidade; nunca deixe nome de estúdio fixo no código.
> Referência de multi-tenant, admin e visual: o MayaJus (`C:\Users\JeffersonFernandes\Projetos\MayacorpAutomacoes_CFME`).
> Herdado do Pilates: [`docs/MIGRACAO.md`](docs/MIGRACAO.md) e [`docs/inventario-pilates-django.md`](docs/inventario-pilates-django.md).

| | Origem | Este projeto |
|---|---|---|
| Código | `C:\Users\JeffersonFernandes\Projetos\Pilates_NovaVersao` (não mexer) | `C:\Users\JeffersonFernandes\Projetos\MayaFit` · `https://github.com/Jeff1984Sor/MayaFit.git` |
| Sistema antigo do Mayris | Django em `https://mayris.mayacorp.com.br` (NÃO MEXER) | os dados entram por ETL no banco do estúdio `mayris`, só no final |

**Proibido:** alterar o sistema antigo, conectar na produção antiga ou baixar dados reais de alunos para a máquina de desenvolvimento. Testes usam dados sintéticos. A carga real é etapa final, com autorização explícita do Jefferson.

## Multi-tenant (um banco por estúdio)

- **Banco de controle `mayafit_controle`** (mesmo servidor do `DATABASE_URL`; no SQLite, `data/mayafit_controle.db`).
  Modelos em `app/controle/models.py` (Cliente = estúdio, Plano, Dominio, Login, Cobranca, ContratoCliente, Solicitacao…),
  migrations próprias em `alembic_controle/`. Nenhum estúdio enxerga este banco.
- **Liga sozinho**: sem o banco de controle, o sistema roda como antes (um banco só, `storage/`) — é assim em dev e nos testes
  dos módulos. Com ele, o modo multi liga (nada no `.env`). Igual ao MayaJus (`app/core/tenancy.py`).
- **Cada estúdio = um banco `mayafit_<slug>`** com o esquema inteiro (`alembic/`). Os módulos continuam sem `tenant_id`.
  Arquivos em `storage/estudios/<slug>/`.
- `app/core/tenancy.py`: `Estudio(slug, banco, mayacorp)` numa ContextVar; `SessionLocal` escolhe o banco por ela
  (`SessaoDoEstudio.get_bind`). Quem define o estúdio: o middleware (`app/core/estudio_http.py`) pelo token (claim `est`)
  ou pelo host (`X-Forwarded-Host` vindo do BFF, senão `Host`); o login, pelo host ou pelo catálogo de logins; o worker, percorrendo os ativos.
- **Endereços**: cada estúdio ganha `<slug>.<DOMINIO_BASE>` e pode ter domínio próprio (tabela `dominio`). App do aluno e
  links públicos (assinatura) acham o estúdio pelo host.
- **Login curto** ("ana") pode repetir entre estúdios. No endereço principal, o catálogo resolve quando o login é único;
  ambíguo → a pessoa entra pelo endereço do estúdio.
- **Admin MayaCorp** = cliente `tipo="mayacorp"` (banco `mayafit_mayacorp`), aberto só no domínio do admin. Rotas
  `/api/admin/*` exigem estúdio `mayacorp` + usuário administrador. Menu "MayaCorp" (`/admin/*`): Início, Estúdios (ficha,
  domínios, plano, uso, status, usuário Suporte, acessar), Solicitações (cadastro pelo site), Planos e indicação, Contratos,
  Cobranças (Mercado Pago, régua). Os estúdios veem "Meu plano" em Minha conta.
- Todo estúdio novo nasce com o usuário **Suporte** (`suporte.<slug>`, senha definida no admin) e um link de primeiro acesso
  para o dono criar o usuário master. Status: `teste | ativo | suspenso | inativo` (suspenso entra e é avisado; inativo não entra).

## Visual

Padrão MayaCorp do MayaJus (shell, menu lateral, cards, tabelas, login): Navy `#1E2D6B`, Indigo `#7C8FFF`, Teal `#1A8F5E`,
Amber `#F5A623`, Red `#C94343`, Dark `#0F1729`, Gray `#F7F8FC`. Fontes DM Sans + JetBrains Mono (números).
Telas de cadastro: cabeçalho → toolbar (busca + filtros + Novo) → tabela → vazio ilustrado → paginação → modal → confirmação → toast.

## Stack (igual à do MayaJus, `C:\Users\JeffersonFernandes\Projetos\MayacorpAutomacoes_CFME`)

- `backend/`: FastAPI + SQLAlchemy 2 + Pydantic v2 + Alembic, Python 3.12, gerenciado com `uv`. Rode com `uv run python -m ...` (os `.exe` do venv são bloqueados no Windows desta máquina; `uv run pytest` falha e `uv run python -m pytest` funciona).
- `frontend/`: Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + TanStack Query + Zod.
- Banco: PostgreSQL (hml/prod), SQLite só em dev/testes. Fila e tarefas periódicas no worker (`app.worker`).
- Deploy: `deploy/` (systemd templated + nginx), hml antes de prod, tag `vN` em prod.

## Decisões já tomadas

1. **Um estúdio por banco** (sem `tenant_id`; ver Multi-tenant). Identidade (nome, logo, cor) vem do banco (white-label), nunca fixa no código.
2. **Segurança por padrão**: toda rota exige login; rota pública precisa estar numa lista explícita. JWT com expiração e refresh, OTP com limite de tentativas, segredos de integração **cifrados** no banco (Fernet com `MASTER_KEY`), webhooks exigem token, arquivos só por rota autenticada ou por link assinado com prazo.
3. **Perfis de acesso por catálogo de permissões** (como no MayaJus), com perfis padrão: Administrador, Recepção/Gestão, Financeiro, **Professor** (só as próprias aulas, nada de financeiro) e Somente leitura. Profissional **sem login** é permitido.
4. **Regras de negócio ficam em `app/domain/` como funções puras com testes** (preço, parcelas, capacidade, reposição, status...). Rota só orquestra. Nada de regra escondida em CRUD genérico.
5. Dinheiro sempre `Decimal`/`Numeric(15,2)`. Datas de negócio em `Date`; instantes em `UtcDateTime`. Fuso de negócio: `America/Sao_Paulo`.
6. Códigos de negócio antigos (`cdAluno`, `cdContrato`...) são **preservados** em colunas `codigo_legado` (integradores externos usam `cdAluno`).
7. Capacidade da aula é garantida com transação + bloqueio (não só validação em Python).

## Como trabalhar (agentes e humanos)

- Branch `develop` = integração (vai para hml); `main` = produção. Trabalho em branch `feat/<assunto>`; PR/merge em `develop`. **Nunca** force-push em `main`/`develop`.
- Commits pequenos, mensagem em português dizendo o que muda e por quê. Terminar mensagem com a linha `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Todo trecho de regra portada do Django precisa de **teste de caracterização** com o caso numérico do sistema antigo (ver `docs/MIGRACAO.md`, seção Regras).
- Antes de dar algo como pronto: `cd backend && uv run python -m pytest -q` verde; no frontend, `npm run build` sem erro.
- Não commitar `.env`, `*.pfx`, bancos, `storage/`, `node_modules`. Segredo nunca em código.
- Registre o andamento em `docs/PROGRESSO.md` (o que foi feito, o que falta, decisões e dúvidas para o Jefferson).

## Comandos

```bash
cd backend
uv sync
uv run python -m pytest -q
uv run python -m alembic revision --autogenerate -m "..."
uv run python -m alembic upgrade head
uv run python -m uvicorn app.main:app --reload --port 8000
cd ../frontend && npm install && npm run dev
```


## Contratos do core (fundação) para quem cria módulos

- **Tabelas do core (nomes fixos, podem receber FK):** `usuario`, `perfil_acesso`, `identidade`, `auditoria`, `config_email`, `config_ia` (e auxiliares `refresh_token`, `recuperacao_senha`, `rate_limit_evento`). Single-tenant: nada de `tenant_id`.
- **Rotas de um módulo:** crie `backend/app/modules/<nome>/routes.py` com `router` (protegido: o login é exigido no include) e, se tiver autenticação própria (webhook, chave de API, app do aluno), `router_publico`. O `main.py` descobre sozinho. Tarefas periódicas: `modules/<nome>/tarefas.py` chamando `app.worker.registrar_tarefa`.
- **Permissão é negada por padrão:** acrescente a regra da rota em `app/core/permissoes.py` (`adicionar_regras` ou `_REGRAS`). `tests/test_cobertura_rotas.py` falha se alguma rota ficar sem regra ou sem login.
- **Perfil Professor:** use `ctx.somente_proprias_aulas()` e `escopo.filtrar_proprias(ctx, query, Aula.profissional_id)`; registre uma vez `escopo.registrar_resolvedor_profissional(fn)` (ver `app/core/escopo.py`).
- **Arquivos:** `storage.registrar_categoria(...)`, salvar com `storage.salvar` (caminho RELATIVO no banco), servir por `/api/arquivos/...` (login + permissão da categoria) ou `storage.link_publico` (link assinado com prazo).
- **Segredos de integração:** cifrar com `app.core.segredos.cifrar_texto`; cadastrados pela tela, nunca em código nem no `.env` de negócio.
- **Frontend:** o navegador só fala com `/bff/*` (Next); tokens vivem em cookies httpOnly. Itens `planejado: true` em `components/mayacorp/nav.ts` viram clicáveis quando a tela existir.
- **Perfis padrão:** Full, Professor e Secretária (outros pela matriz de permissões).

## Decisões do Jefferson (registradas em 25/10/2026)

- **Perfis padrão: Full, Professor e Secretária.** Professor vê só as aulas dele (nada de financeiro). Secretária vê as aulas de todos. Escopo da Secretária é suposição a confirmar (ver `docs/progresso-fundacao.md`).
- **Todas as credenciais e integrações são cadastradas pelo usuário NA FERRAMENTA** (Configurações > Integrações): token do WhatsApp (Wasender/Evolution), chave da IA, chaves e token do webhook do TotalPass (futuro), SMTP. Nunca em `.env`/código. Regras: guardadas cifradas (`app.core.segredos`), **somente escrita** (a tela mostra "configurado" + últimos 4 caracteres, nunca o valor), botão "Testar conexão", só perfil Full altera, auditoria registra a troca sem o valor. O ETL **não migra** nenhum segredo; o usuário recadastra pela tela.
- **Dados antigos:** entram no banco novo só no final, por ETL, com autorização.

## Convenções para módulos desenvolvidos em paralelo (evitam conflito de merge)

- Cada módulo é dono de `backend/app/modules/<modulo>/` (routes, schemas, servico, tarefas), `backend/tests/<modulo>/` e `frontend/app/(app)/<area>/` + `frontend/components/<area>/`. **Não edite arquivos de outro módulo** nem `core/` (peça por escrito ao coordenador em `docs/progresso-<modulo>.md`).
- Permissões: registre as regras de rota do módulo com `adicionar_regras(...)` a partir do próprio módulo (não edite `_REGRAS` de `core/permissoes.py`). Se faltar um recurso no `CATALOGO`, anote o pedido no seu progresso.
- Tipos do frontend em arquivo próprio `frontend/lib/tipos-<area>.ts` (não editar o `types.ts` compartilhado). No `nav.ts` altere somente as linhas do seu módulo (`planejado: false`).
- Models existem em `backend/app/modules/*/models.py` (agente Dados). Mudança de modelo: faça via migração nova (`alembic revision --autogenerate`), nunca edite a `0001`. Avise o coordenador no progresso.
- Serviços que outros módulos vão chamar ficam em `modules/<modulo>/servico.py` com assinatura estável e testada; regras de negócio vêm de `app/domain` (não reimplementar).
- Todo endpoint: login + regra de permissão + `ctx.auditar(...)` nas ações sensíveis + teste; perfil Professor respeita `somente_proprias_aulas`.
- Antes de entregar: `uv run python -m pytest -q backend/tests/<modulo> backend/tests/test_cobertura_rotas.py`, `npm run lint`, `npm run build`. A suíte completa é lenta; rode-a só ao final.
- **Respostas de 25/10/2026:** fornecedores, categorias, subcategorias e termos passam a ter `ativo` (inativar em vez de excluir) · bloqueio recorrente pode ficar sem data final (pontual exige data final) · **Secretária edita** horários de funcionamento, bloqueios, termos e modelos (contrato e evolução) · valores nos documentos no formato `R$ 1.234,50`.
- **Login (decisão de 25/10/2026): todos entram com um LOGIN curto (ex.: `ana`), nunca com e-mail.** O e-mail fica só como contato e para recuperar senha/convite. O ETL gera o login dos usuários antigos a partir do e-mail (sem acento, único) e lista cada um no relatório (`logins_gerados`) para o Jefferson revisar. **Unidade com capacidade 0 é proibida. Comissão é um percentual por profissional. Secretária só consulta planos e profissionais. Excluir unidade leva junto horários e bloqueios.**
- **Reposição e desmarcação (decisão de 25/10/2026): o ALUNO NÃO repõe sozinho.** Ao desmarcar, ele pode PEDIR reposição; **só a gerência (perfil Full) decide** se aprova e em qual horário (recurso de permissão `reposicoes`). **Regra das 6 horas de aviso LIGADA:** o aluno só desmarca com 6 h ou mais de antecedência; a equipe pode abrir exceção (Full) com motivo registrado. Texto do código do app do aluno aprovado: "Olá, Ana! Seu código de acesso ao app é 123456. Vale por 10 minutos. Não compartilhe com ninguém."

