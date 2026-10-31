# Site grátis do estúdio — especificação e progresso

## 1. Especificação

### Objetivo
Todo estúdio do MayaFit ganha um site one-page bonito, rápido e otimizado para o Google, publicado no próprio endereço
(`<slug>.<domínio base>` ou domínio próprio), que **se mantém sozinho**: modalidades, planos, grade de horários e
equipe vêm dos cadastros do sistema. O site existe para **captar alunos**: todo pedido de aula experimental vira lead no
CRM. Meta de aceite do produto: um estúdio recém-criado publica o site em menos de 5 minutos.

### Personas
- **Dona/gestora do estúdio (perfil Full):** edita textos e fotos, escolhe o modelo visual, publica e acompanha os contatos.
- **Secretária / perfil com `site.ver`:** consulta o site e os contatos recebidos (editar depende de `site.editar`).
- **Visitante (futuro aluno):** conhece o estúdio pelo celular, vê planos e horários e pede uma aula experimental.
- **Robô de spam:** tenta enviar o formulário em massa (precisa ser barrado sem atrapalhar o visitante).
- **Google / redes sociais:** leem título, descrição, OpenGraph, sitemap e dados estruturados.

### Fluxos
1. **Primeira visita ao editor** (`/site`): o sistema cria um rascunho pronto (textos de exemplo com o nome do estúdio,
   todas as modalidades, FAQ básico, seções principais ligadas). A prévia ao vivo já mostra o site.
2. **Editar:** escolher o modelo (Aurora, Zen, Energia) → ligar/desligar e ordenar seções → abrir cada seção e editar
   textos/fotos (fotos comprimidas no navegador e enviadas) → a prévia muda a cada tecla, em computador, tablet ou
   celular → **Salvar** (ou Ctrl+S). O checklist "Pronto para publicar" mostra o que falta.
3. **Publicar:** botão "Publicar site" (salva antes se houver alteração). Na primeira vez, confete e o endereço fica no ar.
   Depois, editar não muda o site público até "Publicar alterações". "Descartar alterações" volta o rascunho à versão
   publicada. "Tirar o site do ar" (com confirmação) devolve a raiz do endereço para a tela de login.
4. **Visitante:** abre `https://<slug>.<domínio>/` → vê o site → toca em "Agende sua aula experimental" → preenche nome,
   telefone/e-mail, interesse, mensagem, marca a autorização LGPD → recebe confirmação na tela (e atalho para o WhatsApp).
5. **Contato recebido:** gravado no histórico do site (`site_contato`) e enviado ao CRM (`crm.servico.criar_lead`, origem
   "site"). Aparece em "Contatos recebidos" com selo "No CRM" ou "Só no site", botão de WhatsApp com mensagem pronta e
   marcação de lido.

### Regras de negócio
1. O site público só existe com `publicado = true`; ele mostra a **versão publicada** (`conteudo_publicado`/`tema_publicado`),
   nunca o rascunho.
2. Publicar exige ao menos uma seção ligada.
3. Modalidades = tipos de serviço **ativos**; serviço novo aparece sozinho (só some se o estúdio desligar).
4. Planos = planos **ativos**, menos os ocultados e os de modalidade escondida. Com "mostrar preços" desligado, a API
   **não envia** o valor (aparece "Consulte valores"). Plano avulso mostra "/aula"; os demais "/mês".
5. Grade = grade fixa (`horario_studio`) das unidades ativas; sem grade fixa, as aulas dos próximos 14 dias agrupadas por
   dia da semana/horário. Só leitura, sem vagas, reservas ou alunos.
6. Equipe: **só quem o estúdio marca** aparece (padrão: ninguém). Bio/foto de quem não aparece não sai na API pública.
   Na grade, o professor aparece só pelo **primeiro nome** e só se estiver marcado na equipe (e a opção ligada).
7. **Nenhum dado de aluno** é lido pelo site. Contatos de profissionais (celular, e-mail) também não.
8. Fotos do site: categoria de storage própria (`site`, JPG/PNG/WebP até 5 MB, assinatura conferida); nome aleatório;
   servidas pela rota pública `/api/site-publico/imagens/<nome>` **só** para a pasta `site/`. O conteúdo só aceita fotos
   `site/<hex32>.<ext>` que existam no storage.
9. Mapa: aceita só link do Google Maps ou o `<iframe>` de "Incorporar" (https, domínios do Google). Sem mapa, gera o
   mapa pelo endereço. Nada de iframe de domínio arbitrário.
10. Redes sociais: `@usuario` ou link `https://`; WhatsApp/telefone com DDD (10 a 13 dígitos).
11. Formulário: exige nome, telefone **ou** e-mail e **consentimento LGPD** (texto e data do consentimento ficam gravados).
12. Anti-spam: campo isca invisível (honeypot) e tempo mínimo de preenchimento (2,5 s) → descartado em silêncio (o robô
    recebe "ok"); **rate limit** de 5 envios por IP a cada 10 min (429).
13. O contato é **sempre** gravado antes de chamar o CRM; se o CRM não existir ou falhar, o contato fica com `erro_crm`
    e não se perde.
14. Página pública: rate limit de 300 leituras/min por IP; imagens 900/min.
15. Ações do editor (salvar, publicar, despublicar, descartar, enviar foto) ficam na **auditoria**.
16. Cor e logo vêm de Configurações › Identidade (nunca fixos no código).

### Telas
- **`/site` (sistema):** cabeçalho com status (No ar / Fora do ar / Não salvo / Alterações não publicadas), Ver site,
  Salvar, Publicar e menu (copiar endereço, descartar, tirar do ar); cartão do endereço (subdomínio, domínios próprios,
  aviso de que domínio próprio é com a MayaCorp); abas **Editar e pré-visualizar** (painel à esquerda com checklist,
  modelo visual, seções e ordem, um painel por seção, SEO com prévia do resultado no Google, Privacidade; à direita a
  prévia ao vivo com computador/tablet/celular) e **Contatos recebidos** (lista paginada, selos, WhatsApp, marcar lido).
- **Site público (`/` do host do estúdio, também em `/s`):** topo fixo com menu (hambúrguer no celular), capa, sobre,
  modalidades, planos, horários, equipe, depoimentos, galeria, perguntas frequentes, localização com mapa, contato com
  formulário, rodapé com redes e política; botão flutuante de WhatsApp.
- **`/s/privacidade`:** política de privacidade gerada (LGPD) com os dados do estúdio.
- **`/sitemap.xml` e `/robots.txt`** do host.

### Estados vazios e de erro
- Seção ligada sem conteúdo: **some do site**; na prévia aparece um aviso tracejado dizendo o que falta, e na lista de
  seções um selo "vazia".
- Editor sem serviços/planos/profissionais/horários: cartão com chamada para o cadastro correspondente.
- Contatos vazios: ilustração + "Publicar o site" (se fora do ar) ou dica de divulgação.
- Site não publicado: `/` e `/s` levam ao login; `robots.txt` bloqueia tudo; `sitemap.xml` vazio.
- Formulário: mensagens claras (falta contato, falta consentimento, muitos envios, falha de rede com sugestão de WhatsApp).
- Erros de validação ao salvar chegam em português (toast). Sair com alteração não salva pede confirmação.

### Permissões
- Recurso `site` no catálogo (grupo "Site"): `site.ver` (editor só leitura + contatos) e `site.editar` (salvar, publicar,
  despublicar, descartar, fotos, marcar contato lido). Perfis padrão: só **Full** (administrador). Liberar para a
  Secretária pela matriz de perfis, se o Jefferson quiser.
- Rotas públicas em `/api/site-publico/` (lista `PUBLICAS_AUTENTICACAO_PROPRIA`, cada rota com rate limit).

### Critérios de aceite
- [x] Rascunho inicial pronto na primeira visita; publicar leva 1 clique.
- [x] 3 modelos visuais com cor e logo da Identidade; seções ligáveis e ordenáveis.
- [x] Modalidades, planos (com opção de esconder preço), grade e equipe vêm dos cadastros.
- [x] Prévia ao vivo idêntica ao site (mesmo componente), em computador, tablet e celular.
- [x] Formulário → contato gravado + lead no CRM; honeypot, tempo mínimo, rate limit e consentimento LGPD.
- [x] Política de privacidade gerada; SEO (title, description, canonical, OpenGraph/Twitter), sitemap, robots e dados
      estruturados (`SportsActivityLocation`/`ExerciseGym` + `FAQPage`).
- [x] Nenhum dado de aluno (teste automático) e nenhum contato de profissional na API pública.
- [x] Site servido na raiz do endereço do estúdio quando publicado; sistema continua em `/login`, `/dashboard`…
- [x] Testes do módulo e de cobertura de rotas verdes; lint e build do frontend sem erro.

## 2. Como o site é servido

- `frontend/proxy.ts`: requisição a **`/` sem cookie de sessão** é reescrita (rewrite, a URL continua `/`) para `/s`.
  Quem está logado continua indo para o painel. `/s` e `/sitemap.xml` entraram na lista de rotas públicas do proxy
  (`robots.txt` e imagens já passavam pelo `matcher`).
- `app/(site)/s/page.tsx` (server component) busca `GET /api/site-publico/pagina` repassando `X-Forwarded-Host` (host
  original) e `X-Forwarded-For` (IP do visitante, para o rate limit). Site não publicado → `redirect("/login")`.
- Fotos: `/s/img/<nome>` (route handler) → `/api/site-publico/imagens/<nome>`, com cache de 1 ano (nome muda quando a foto muda).
  Logo: `/s/logo` → `/api/public/logo`.
- Formulário: **server action** (`components/site/acoes.ts`) → `POST /api/site-publico/contato` com host e IP.
  (Não passa pelo BFF `/bff`, que não é deste módulo.)
- Performance: HTML renderizado no servidor, JS só no formulário; animações 100% CSS (scroll-driven quando suportado,
  desligadas com `prefers-reduced-motion`); fontes dos temas sem preload (o navegador baixa só a do tema em uso); fotos
  comprimidas no navegador antes do envio (lado maior 1600 px, WebP), `loading="lazy"` fora da capa e
  `fetchpriority="high"` na capa; mapa com `loading="lazy"`.

## 3. Rotas da API

| Método | Rota | Permissão |
|---|---|---|
| GET | `/api/site` | `site.ver` (cria o rascunho na 1ª vez) |
| PUT | `/api/site` | `site.editar` |
| POST | `/api/site/publicar` · `/despublicar` · `/descartar` | `site.editar` |
| POST | `/api/site/imagens` | `site.editar` |
| GET | `/api/site/contatos` | `site.ver` |
| POST | `/api/site/contatos/{id}/lido` · `/api/site/contatos/lidos` | `site.editar` |
| GET | `/api/site-publico/pagina` | pública (rate limit 300/min) |
| GET | `/api/site-publico/imagens/{nome}` | pública (rate limit 900/min) |
| POST | `/api/site-publico/contato` | pública (rate limit 5/10 min, honeypot, LGPD) |

## 4. Arquivos

- Backend: `backend/app/modules/site/` (`models.py`, `schemas.py`, `regras.py` — funções puras, `servico.py`,
  `routes.py`, `demo.py`), migration `backend/alembic/versions/0120_site.py` (`down_revision = "0001_pilates_inicial"`),
  testes `backend/tests/site/` (46 testes).
- Frontend: `frontend/app/(site)/` (site público, privacidade, imagens, logo, sitemap, robots), `frontend/app/(app)/site/`
  (editor), `frontend/components/site/` (renderizador, temas `site.css`, formulário, server action, editor),
  `frontend/lib/tipos-site.ts`.
- Linhas acrescentadas em arquivos compartilhados:
  - `backend/app/core/permissoes.py`: grupo "Site" no fim do `CATALOGO` e `PUBLICAS_AUTENTICACAO_PROPRIA.append(r"/api/site-publico/")`.
  - `frontend/proxy.ts`: `s|sitemap\.xml` em `PUBLICAS` e o rewrite de `/` → `/s` sem sessão.
  - `frontend/components/mayacorp/nav.ts`: item "Site do estúdio" no grupo Comunicação (+ import do ícone `Globe`).
  - **`frontend/lib/auth.tsx` (fora da lista combinada, necessário):** o `AuthProvider` do layout raiz consulta
    `/auth/me` em toda página e, com 401, o `api.ts` manda para o login — o site público (inclusive na raiz `/`) era
    redirecionado. Acrescentei ao `enabled` da consulta `&& !document.getElementById("site-publico")`; as páginas
    públicas do site têm esse id. Coordenador: confirmar ou trocar por outro mecanismo (ex.: layout raiz sem providers
    para o grupo `(site)`).

## 5. Demo

`app.modules.site.demo.popular_demo(db)` — idempotente: preenche textos, destaques, descrições das modalidades, marca até
3 profissionais com cargo/bio, depoimentos, FAQ extra, endereço, horário, WhatsApp/Instagram, SEO e privacidade, e
publica. Não mexe em site que já foi publicado alguma vez. Não cria cadastros (usa os que a demo dos outros módulos criar).

## 6. Verificação manual (smoke test)

API + `next start` com banco sintético e a demo: `/` sem sessão abre o site (title, OpenGraph, canonical, JSON-LD,
planos com preço, grade); `/dashboard` sem sessão vai ao login; `robots.txt`, `sitemap.xml` e `/s/privacidade` 200.
Capturas no Edge headless dos 3 temas (1280 px e 700 px) conferidas: Aurora (serifa, luzes), Zen (areia, arco),
Energia (escuro, caixa alta, listras).

## 7. Pendências e pedidos ao coordenador

1. **`app/modules/__init__.py › registrar_modelos()`**: acrescentar `from app.modules.site import models as _site_models`
   para o autogenerate do Alembic e o ETL enxergarem as tabelas `site_config`/`site_contato` (hoje elas entram pelo
   `routes.py` descoberto pelo `main.py`, o que basta para app e testes; a migration 0120 foi escrita à mão).
2. **Tenancy:** `servico.endereco()` tenta `app.core.tenancy` (`estudio_atual()`/`atual()`) e `settings.dominio_base`
   para mostrar `<slug>.<domínio base>` e os domínios próprios; sem isso mostra o host da requisição. Ajustar os nomes
   quando o módulo de tenancy estiver pronto (o ideal é ele expor `slug` e `dominios` do estúdio atual).
3. **Storage por estúdio:** as fotos usam `app.core.storage`; com o storage por estúdio (`storage/estudios/<slug>/`) o
   isolamento vem de graça, desde que o middleware defina o estúdio pelo `X-Forwarded-Host` também nas rotas públicas.
4. **Plano:** bloqueio por plano não implementado (fica com o coordenador).
5. **Perfis padrão:** `site.*` só no Full. Decidir se a Secretária recebe `site.ver`/`site.editar`.
6. **CRM:** o contrato usado é `crm.servico.criar_lead(db, *, nome, telefone, email, origem="site", interesse, mensagem,
   quer_aula_experimental)` devolvendo objeto com `id` (ou o próprio id). O teste cobre CRM ausente, presente e com erro.
7. **Retenção LGPD:** a política diz "até 12 meses" para contatos não convertidos; falta a tarefa periódica que apaga
   `site_contato` antigos (sugestão: `modules/site/tarefas.py` quando o worker multi-estúdio estiver pronto).
8. Fotos enviadas e depois removidas do conteúdo continuam no storage (nome aleatório, não listável). Limpeza futura.
9. O cabeçalho `X-Frame-Options: DENY` do Next não afeta o site; o mapa do Google é um iframe de terceiro, permitido.
