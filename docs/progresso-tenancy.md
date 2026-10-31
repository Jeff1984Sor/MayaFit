# Multi-tenant (um banco por estúdio): especificação e progresso

> Fundação multi-tenant do backend do MayaFit, portada do MayaJus (`app/core/tenancy.py`, `escritorio_http.py`,
> `app/controle/*`). "Escritório" → "Estúdio". O admin aparece para as pessoas como **Admin MayaFit** (no código
> continua `tipo="mayacorp"`, `Estudio.mayacorp`, banco `mayafit_mayacorp`).

## 1. Especificação

### 1.1 Peças

| Peça | Onde | O que faz |
|---|---|---|
| Banco de controle `mayafit_controle` | `app/controle/models.py`, `alembic_controle/` | Estúdios (`cliente`), domínios, catálogo de logins, planos, contratos, cobrança. Nenhum estúdio o enxerga. |
| Banco do estúdio `mayafit_<slug>` | `alembic/` (esquema inteiro) | Tudo do estúdio, sem `tenant_id`. Hífen do slug vira `_`. |
| Estúdio do pedido | `app/core/tenancy.py` | `Estudio(slug, banco, mayacorp)` numa ContextVar. `SessionLocal` (`SessaoDoEstudio.get_bind`) escolhe o banco por ela. |
| Middleware | `app/core/estudio_http.py` | Confere o Host e define o estúdio de cada pedido HTTP/WebSocket. |
| Regras do controle | `app/controle/service.py` | API estável (ver §3). |
| Catálogo de logins | `app/controle/sincronia.py` | Mantém `login(chave, cliente_id, usuario_id)` em dia depois de cada commit. |
| Terminal | `python -m app.controle.cli` | `ativar`, `migrar`, `novo-estudio`, `novo-admin-mayacorp`, `dominio`, `listar`, `sincronizar-logins`. |
| Demonstração | `python -m app.demo` | Ambiente multi completo com dados sintéticos (ver §5). |

### 1.2 Liga sozinho

- **Sem** o banco de controle: um banco só (o `DATABASE_URL`), arquivos em `storage/`, tokens sem `est`. É o modo de dev e
  dos testes dos módulos. Nada muda em relação a antes.
- **Com** o banco de controle (Postgres: banco `mayafit_controle` no mesmo servidor; SQLite: `data/mayafit_controle.db` ao
  lado do `dev.db`): o modo multi liga (decidido uma vez por processo; reinicie API e worker após `cli ativar`).
- O estúdio "principal" (`banco = None`) usa o `DATABASE_URL` e `storage/`. Na ativação, se o banco principal já tem uma
  Identidade, esse estúdio entra no controle sozinho, com os logins (`registrar_principal_se_faltar`).

### 1.3 Como o estúdio é identificado (em cada caso)

| Caso | Como |
|---|---|
| Pedido com token (header `Authorization: Bearer` ou `?token=`) | Claim **`est`** do token (equipe e app do aluno). O token **sempre vence** o endereço. |
| Pedido sem token | Endereço: **`X-Forwarded-Host`** (o BFF do Next repassa o host original) e, sem ele, **`Host`** → tabela `dominio`. |
| Login (`POST /api/auth/login`) | Endereço do estúdio; sem endereço de estúdio, **catálogo de logins** (chave = login minúsculo). |
| Esqueci a senha / código WhatsApp (`forgot`, `forgot-codigo`, `reset-codigo`) | Igual ao login (endereço, senão catálogo). |
| Redefinir senha / convite (`POST /api/auth/reset`) | O próprio token do link: **`<slug>.<aleatório>`** (ver regra 8). |
| Renovar sessão (`POST /api/auth/refresh`, `/api/aluno-app/auth/refresh`) | Claim `est` do refresh token (vem no corpo). |
| Primeiro acesso (`GET`/`POST /api/auth/primeiro-acesso`) | Claim `est` do token assinado `primeiro` (query no GET, corpo no POST). |
| App do aluno (pedir/verificar código por CPF) | Endereço (o BFF do aluno repassa `X-Forwarded-Host`). |
| Links públicos (`/api/arquivos-publicos/...`, assinatura) | Endereço do estúdio. |
| Worker | Percorre os estúdios ativos (relidos a cada volta). |
| Terminal (`seed`, `criar_usuario`) | `--estudio <slug>` (obrigatório no modo multi). |

### 1.4 Ciclo de vida do estúdio

1. **Provisionar** (`service.provisionar`, CLI `novo-estudio`, admin): cria o banco (`CREATE DATABASE`; erro claro sem
   `CREATEDB`), registra no controle (status `ativo`, ou `teste` com `dias_teste`), domínios (+ `<slug>.<DOMINIO_BASE>`),
   aplica as migrations, cria Identidade (nome do estúdio), configs, perfis padrão, o usuário **Suporte** e:
   - com `primeiro_acesso=True`: devolve o **link de primeiro acesso** (o dono cria o usuário master);
   - senão: cria o administrador (com senha → devolve `""`; sem senha → devolve o link do convite).
   Qualquer erro no meio desfaz o registro no controle (cliente, domínios e logins); o banco vazio pode ser reaproveitado.
2. **Primeiro acesso**: o link vale 7 dias e só enquanto o estúdio não tem administrador além do Suporte.
3. **Status**: `teste | ativo | suspenso` entram (suspenso só é avisado); `inativo` não entra (tokens param na hora, com
   cache de até 60 s em outros processos), some do worker e da lista de ativos. `definir_status(slug, status)`.
4. **Uso**: o worker grava `Cliente.uso = {alunos_ativos, usuarios, aulas_mes, em}` de hora em hora (tarefa global).

### 1.5 Regras

1. Todo banco de estúdio tem o esquema inteiro; módulos **não** usam `tenant_id`.
2. Toda sessão (`SessionLocal`/`get_db`) usa o banco do estúdio atual; sem estúdio no modo multi → `EstudioNaoIdentificado`
   → **401 "Sessão expirada. Entre novamente."** (nenhum banco é aberto por engano).
3. Todo token emitido no modo multi leva `est=<slug>` (`security.criar_token` e o JWT do app do aluno).
4. Token só vale no estúdio que o emitiu: `deps.usuario_do_token`, `auth_service.rotacionar_refresh` e
   `app_aluno.servico.decodificar` exigem `est == estúdio atual` (`tenancy.token_do_estudio_atual`). Token sem `est`
   (ex.: emitido antes da ativação) não vale no modo multi → a pessoa entra de novo.
5. Login é **sempre** pelo login curto (nunca e-mail). O catálogo guarda só a chave login, de quem pode entrar
   (ativo + acesso ao sistema); PK `(chave, cliente_id)`: o mesmo login pode existir em vários estúdios.
6. No endereço principal, o catálogo resolve só quando o login existe em **um** estúdio que pode entrar. Repetido em mais
   de um → falha com a **mesma** mensagem de senha errada (não revela). Nesse caso a pessoa precisa entrar pelo endereço
   do estúdio. O Admin MayaFit nunca é achado pelo catálogo: abre só no domínio dele.
7. No endereço de um estúdio inativo, o login não cai no catálogo (não "escorrega" para outro estúdio).
8. **Link de redefinição/convite**: a tabela `recuperacao_senha` mora no banco do estúdio, então o token do link é
   `<slug>.<aleatório>` (o digest guardado cobre o texto inteiro, slug incluído): trocar o slug só faz procurar um digest
   inexistente noutro banco. O link continua `…/redefinir-senha?token=…` (o frontend não muda) e funciona no endereço principal.
9. **Primeiro acesso**: token JWT `typ=primeiro`, 7 dias, `est=<slug>`, `email`; `GET` valida e devolve
   `{estudio, email}`; `POST {token, nome, email, login, senha}` cria o master (perfil administrador) e já devolve os
   tokens; 409 se o estúdio já tem administrador além do Suporte (uso único na prática).
10. **Usuário Suporte**: `suporte.<slug>`, `suporte+<slug>@mayacorp.com.br`, perfil administrador, `usuario.suporte = true`,
    senha = `PoliticaComercial.senha_suporte_hash` (definida no admin; sem ela nasce sem senha). Não conta no uso/limite.
11. Arquivos: estúdio principal em `storage/`, demais em `storage/estudios/<slug>/` (`storage.raiz()` = `tenancy.pasta_base()`).
12. Host: vale o que estiver em `ALLOWED_HOSTS` (aceita `*.dominio`) ou, no modo multi, qualquer domínio do controle.
    Outro host → 400 "Invalid host header" (o `EstudioMiddleware` substitui o `TrustedHostMiddleware`).
13. Rate limit com backend "banco" antes de haver estúdio (login no endereço principal) conta na memória do processo.
14. Worker: tarefas comuns rodam uma vez **por estúdio ativo** dentro de `tenancy.usando(esc)`, cada estúdio com o seu
    relógio; tarefas `registrar_tarefa(..., global_=True)` rodam uma vez só, sem estúdio (só o controle).
15. Thread/ThreadPool própria precisa levar o estúdio: `tenancy.com_estudio(fn)`. (`BackgroundTasks` do FastAPI já leva.)

### 1.6 Segurança e isolamento

- Não há caminho de um estúdio para outro dentro da API: o banco é escolhido pela ContextVar, definida só pelo token
  assinado (claim `est`) ou pelo endereço, e o token tem precedência.
- Forjar `X-Forwarded-Host` equivale a abrir o endereço daquele estúdio (o que qualquer um pode): só dá acesso às rotas
  públicas dele; com token, vale o `est` do token e a checagem da regra 4.
- Testes de ataque em `tests/tenancy/test_isolamento_malicioso.py`: token sem `est`, `est` adulterado sem reassinar,
  token assinado com outra chave, token do alfa no endereço do beta, refresh/token de estúdio que ficou inativo, slug
  forjado no link de redefinição (e o link verdadeiro continua valendo), forgot/reset-codigo em login ambíguo, primeiro
  acesso para estúdio que já tem master / sem `est` / com token de outro tipo, token do app do aluno levado para outro
  estúdio, token da equipe no app do aluno, Host falso e `X-Forwarded-Host` desconhecido.

### 1.7 Critérios de aceite (todos com teste em `tests/tenancy/`)

- [x] Sem banco de controle, tudo como antes (suíte inteira verde sem mudanças nos testes dos módulos).
- [x] Dois estúdios com dados isolados (usuários, identidade, arquivos).
- [x] Login pelo endereço e pelo catálogo; login ambíguo falha com a mensagem genérica.
- [x] Token de um estúdio não serve noutro; token sem `est` não vale.
- [x] Inativo não entra (login, token, refresh, endereço); suspenso entra.
- [x] Arquivos em `storage/estudios/<slug>`; principal em `storage/`.
- [x] Worker roda por estúdio; tarefa global uma vez; inativo sai da volta.
- [x] Provisionar cria Suporte (senha do admin) + subdomínio padrão + link de primeiro acesso; erro não deixa estúdio pela metade.
- [x] Primeiro acesso cria o master uma vez só.
- [x] Catálogo acompanha criar/renomear/inativar/excluir usuário; `sincronizar_todos` reconstrói.
- [x] Reset por link e refresh acham o estúdio pelo token; uso gravado no controle.
- [x] Estúdio do banco principal entra no controle na ativação.

## 2. O que foi feito

- `app/core/tenancy.py` (novo), `app/core/estudio_http.py` (novo), `app/core/db.py` (`SessaoDoEstudio`, pragmas SQLite
  para todo banco), `app/core/storage.py` (raiz por estúdio), `app/core/security.py` (tipo `primeiro`, claim `est`),
  `app/core/deps.py` (regra 4), `app/core/auth_service.py` (link com slug, refresh com `est`), `app/core/ratelimit.py`
  (regra 13), `app/core/routes/auth.py` (login/forgot/reset por estúdio, primeiro acesso, `/me` com `estudio`),
  `app/core/schemas.py` (`EstudioInfo`, `PrimeiroAcessoIn/Info`, `UsuarioMe.estudio`), `app/core/config.py`
  (`DOMINIO_BASE`), `app/core/permissoes.py` (+1 linha em `PUBLICAS`: `/api/auth/primeiro-acesso`).
- `app/controle/service.py`, `sincronia.py`, `cli.py`; `alembic_controle/` + `alembic_controle.ini` (migration
  `0001_controle_inicial`); `alembic/env.py` aceita `cfg.attributes["connection"]`; migration `0002_usuario_suporte`.
- `app/main.py` (middleware, handler 401, `migrar_todos()` na subida), `app/worker.py` (por estúdio + `global_`,
  tarefa `controle-uso-dos-estudios`), `app/seed.py` e `app/criar_usuario.py` (`--estudio`), `app/demo.py` (novo).
- Frontend: os dois BFFs repassam `X-Forwarded-Host`; o BFF da equipe aceita `auth/primeiro-acesso` (público; o POST
  vira cookies); `lib/types.ts` ganhou `UsuarioMe.estudio?` e `EstudioInfo`.
- **Fora da minha área, por necessidade de tenancy** (registrado): `app/modules/app_aluno/servico.py` (token do aluno
  com `est`, checagem na decodificação, refresh define o estúdio pelo token) e `tests/test_cobertura_rotas.py` (as duas
  rotas públicas novas na lista esperada e na de rate limit).

### Campo `estudio` do `/api/auth/me` (e do `usuario` do login/refresh)

```json
"estudio": {"slug": "studio-ana", "nome": "Studio Ana", "mayacorp": false, "status": "teste",
            "teste_ate": "2026-11-30", "recursos": ["agenda", "financeiro"]}
```
`null` com um banco só. `recursos` = `Plano.recursos` + `Cliente.extras` (sem plano: `[]`).

## 3. API estável de `app/controle/service.py`

```python
SLUG; ATIVOS; STATUS; class RegraControle(ValueError)
normalizar_host(host) -> str
por_slug(slug) -> Estudio | None            # só teste/ativo/suspenso (cache 60 s)
por_host(host) -> Estudio | None            # idem, pela tabela dominio
host_conhecido(host) -> bool                # domínio cadastrado (qualquer status)
por_login(login) -> Estudio | None          # catálogo; ambíguo/inativo/admin → None
ativos() -> list[Estudio]
limpar_cache() -> None
recursos_do(slug) -> list[str]; info(slug) -> dict | None
registrar(slug, nome, *, banco, status="ativo", dias_teste=None, dominios=None, tipo="estudio", **ficha) -> Cliente
adicionar_dominio(db, cliente, host) -> Dominio
dominio_padrao(slug) -> str | None          # <slug>.<DOMINIO_BASE>
nome_do_banco(slug) -> str                  # "mayafit_<slug>" (hífen → _)
criar_banco(banco) -> None
migrar(estudio) -> None; migrar_controle() -> None; migrar_todos() -> list[str]
provisionar(slug, nome, *, admin_email, admin_nome="", dias_teste=None, dominios=None, tipo="estudio",
            admin_login=None, admin_senha=None, primeiro_acesso=False, **ficha) -> tuple[Cliente, str]
link_primeiro_acesso(slug, email) -> str
estudio_mayacorp() -> Estudio | None; endereco_do_painel() -> str | None
zerar_senha_suporte(slug, senha_hash) -> bool
definir_status(slug, status) -> Cliente
coletar_uso(estudio) -> dict                # {alunos_ativos, usuarios, aulas_mes}
gravar_uso_todos() -> int
registrar_principal_se_faltar(slug=None) -> str | None
sincronizar_usuario(slug, usuario_id, login | None) -> None; sincronizar_todos(slug) -> int; chave_do_usuario(u)
```

Notas: `provisionar` sem `admin_login` (e sem `primeiro_acesso`) usa a parte do e-mail antes do `@`. No admin
(`tipo="mayacorp"`) não nasce Suporte, a Identidade se chama "MayaFit" e não entra o subdomínio padrão.
`migrar_controle` chama `app.controle.planos.garantir_padrao(db)` se esse módulo existir.

## 4. Operação

```bash
uv run python -m app.controle.cli ativar [--slug-principal mayris]   # cria o controle; reinicie API e worker
uv run python -m app.controle.cli novo-admin-mayacorp --admin-nome "Jefferson" --admin-email voce@mayacorp.com.br \
    --login jeff --dominio admin.mayafit.com.br --senha-stdin
uv run python -m app.controle.cli novo-estudio --slug studio-ana --nome "Studio Ana" --admin-email ana@x.com --primeiro-acesso
uv run python -m app.controle.cli migrar          # o deploy chama sempre (sem controle, não faz nada)
```

## 5. Demonstração (`uv run python -m app.demo`)

Só `AMBIENTE=dev`. Monta em `data/demo/` (outra pasta com `--pasta`, recria com `--recriar`) o controle, o Admin MayaFit
(`admin.localhost`, login `admin`) e dois estúdios: "Studio Alfa Pilates" (`studio-alfa.localhost`: ana, carlos, dora)
e "Beta Funcional" (`studio-beta.localhost`: bruno, ana, eva), cada um com o Suporte. Chama `popular_demo(db)` de cada
`app/modules/<modulo>/demo.py` que existir, dentro de cada estúdio (commit depois), e
`app.modules.admin_mayacorp.demo.popular_demo()` para o controle. Senha: `DEMO_SENHA` ou gerada e impressa. O comando
imprime as variáveis (`DATABASE_URL`, `STORAGE_DIR`, `DOMINIO_BASE`) para subir a API/worker apontando para a demo.

## 6. Pendências e dúvidas

- **Frontend**: tela `/primeiro-acesso?token=…` (GET valida, POST cria o master; o BFF já trata) e aviso de estúdio
  `suspenso`/`teste` usando `usuario.estudio`. O aviso "login repetido: entre pelo endereço do seu estúdio" pode ir na
  tela de login (a API não diferencia, de propósito).
- **Lista de usuários do estúdio** (`/api/config/usuarios`) mostra o Suporte; decidir se esconde (`usuario.suporte`) e
  se o estúdio pode inativá-lo. O limite de usuários do plano deve ignorar `suporte=true` (quem implementar o limite).
- **Login repetido entre estúdios na criação**: hoje é permitido (decisão do CLAUDE.md); a tela de usuários poderia
  avisar quando o login já existe noutro estúdio (fica ambíguo no endereço principal).
- **Tokens antigos** (sem `est`) param de valer ao ligar o modo multi: todos entram de novo uma vez.
- **nginx/deploy**: cada domínio de estúdio precisa apontar para o servidor e ter certificado (curinga
  `*.DOMINIO_BASE` recomendado); o nginx deve repassar o `Host` original.
- **Links de e-mail** usam `FRONTEND_URL`; poderiam usar o domínio do estúdio (`dominio_padrao`) para a marca certa
  na tela de redefinição.
- Cache de 60 s do controle por processo: mudar status/domínio no admin leva até 60 s para valer nos outros processos.
- Postgres: cada estúdio abre até 5 conexões por processo (pool 2 + 3); revisar `max_connections` com muitos estúdios.
