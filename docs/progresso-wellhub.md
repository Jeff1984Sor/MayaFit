# Progresso — Integração Wellhub (antigo Gympass)

> Dono: `backend/app/modules/wellhub/**`, `backend/tests/wellhub/**`, `frontend/app/(app)/configuracoes/integracoes/wellhub/**`,
> `frontend/components/wellhub/**`, `frontend/lib/tipos-wellhub.ts`. Migração `0140_wellhub` (down: `0001_pilates_inicial`).

---

## 1. Especificação

### 1.1 Objetivo

Permitir que um estúdio receba alunos do Wellhub sem trabalho manual: as aulas do estúdio aparecem no app do Wellhub com
as vagas reais; a reserva feita no app vira reserva na agenda (mesma regra de capacidade); o cancelamento libera a vaga;
o check-in é validado no Wellhub (sem validação não há repasse); e a gerência confere, mês a mês, quantos check-ins
validados houve e quanto deve receber.

### 1.2 Conceitos

| Wellhub | MayaFit |
|---|---|
| Gym (`gym_id`, cabeçalho `X-Gym-Id`) | Unidade (`WellhubConfig`, uma por unidade) |
| Produto (plano Wellhub) | escolhido por serviço no mapeamento |
| Classe (`class_id`) | Tipo de serviço mapeado (`WellhubMapeamento`) |
| Slot (horário com `total_capacity`/`total_booked`) | Aula da agenda (`AulaSessao`) → `WellhubSlot` |
| Booking (`booking_number`) | Reserva da agenda → `WellhubReserva` |
| Usuário (`unique_token` = Gympass ID, 13 dígitos) | Aluno → `WellhubAluno` |
| Check-in (app) + validação (Access Control) | `WellhubCheckin` (um por aluno/dia/unidade) |

### 1.3 Fluxos passo a passo

**F1. Configurar (assistente, 5 passos — cada um com o seu teste)**
1. *Credenciais*: escolhe ambiente (sandbox/produção), informa gym id e chave de API → Salvar → **Testar conexão**
   (`GET /booking/v1/gyms/{gym}/classes`, sem efeito). Resultado aparece no passo; o painel guarda o último teste.
2. *Webhook*: copia o endereço `https://<estúdio>/api/webhooks/wellhub`; cola o segredo dado pelo Wellhub ou **gera** um
   (aparece uma única vez) → Salvar → **Testar assinatura** (assina um evento de exemplo com o segredo salvo e confere pelo
   mesmo código do webhook, sem rede).
3. *Serviços ↔ produtos*: liga cada serviço vendido no Wellhub a um produto. **Buscar produtos no Wellhub** lista os
   produtos do gym (ou digita o id).
4. *Grade*: janela de N dias (padrão 7), publicação automática (desligada por padrão) → **Testar (prévia)** mostra o que
   seria criado/atualizado/removido sem chamar o Wellhub → **Publicar agora**.
5. *Repasse e ativação*: valor por check-in validado, criar aluno automático, validar check-in na chegada do aviso
   (estúdio sem catraca), serviço padrão, **Integração ativa**.

**F2. Publicar a grade** (botão ou tarefa `wellhub-publicar-grade` a cada 30 min)
1. Para cada mapeamento ativo com produto: cria a classe se ainda não existe (guarda `class_id`); se o mapeamento mudou
   depois da última publicação, atualiza a classe (PUT).
2. Para cada aula futura do serviço na unidade dentro da janela: calcula vagas = capacidade efetiva da aula e reservas
   ativas (TODAS, do estúdio e do Wellhub). Sem slot → cria (POST); vagas mudaram → PATCH; iguais → nada.
3. Slot publicado cuja aula foi excluída (ou mudou de serviço/unidade) → DELETE e marca "removido".
4. Erro num item não para os outros (vai para o resumo); credencial recusada interrompe e vira alerta.

**F3. Reserva pedida (`booking-requested`)**
1. Webhook confere a assinatura → acha a unidade pelo gym → grava o evento (idempotente).
2. Acha o horário (`slot.id`) publicado por nós → aula da agenda.
3. Acha o aluno pelo Gympass ID; senão pelo CPF (se vier e for válido; vincula); senão cria (se permitido) com nome,
   e-mail e telefone do Wellhub, `sem_cpf` quando não houver CPF.
4. Reserva pela agenda (`agenda.criar_reserva`, bloqueio atômico) ou reativa a reserva cancelada do mesmo aluno/aula.
5. Responde ao Wellhub: `PATCH /bookings/{booking_number}` `{"status": 2}` (aceita). Aula lotada → nada é gravado
   (nem o aluno) e responde `{"status": 3, "reason": "CLASS_IS_FULL"}` (evento "rejeitado").
6. Reenvia as vagas do horário (melhor esforço; a próxima publicação corrige).

**F4. Cancelamento (`booking-canceled` / `booking-late-canceled`)** → acha a reserva pelo `booking_number`, muda para
CANCELADA (libera a vaga, sem reposição), marca `cancelada`/`cancelada_tarde`, reenvia as vagas. Sem reserva conhecida:
"cancelado" sem criar nada.

**F5. Check-in**
- `checkin` (Access Control): acha/cria o aluno e registra o check-in do dia (pendente). Com "validar na chegada" ligado,
  valida na hora.
- `checkin-booking-occurred`: marca presença ("chegou") na reserva e registra o check-in do dia.
- Validação: recepção busca o aluno no painel e clica **Validar**, ou o módulo de controle de acesso chama
  `validar_checkin(db, aluno_id)` → `POST /access/v1/validate {"gympass_id"}` com `X-Gym-Id`.

**F6. Eventos e erros** → lista com filtros (resultado, tipo, nº da reserva/Gympass ID/slot), detalhe com o JSON
(mascarado), **Reprocessar** (erro/pendente), **Marcar como conferido** (sai dos alertas; pode desfazer).

**F7. Relatório de repasse** → mês a mês (navegação ‹ ›), por unidade, por dia (gráfico) e por aluno; variação contra o
mês anterior; **Exportar CSV** (uma linha por check-in, Gympass ID completo, valor estimado por linha).

### 1.4 Regras (numeradas)

1. Uma configuração por unidade; `gym_id` único entre unidades.
2. Chave de API e segredo do webhook: cifrados (`app.core.segredos`), **somente escrita** (tela mostra "configurado" +
   4 últimos caracteres), apagar só com `limpar`; nunca aparecem em resposta, log ou auditoria.
3. Trocar chave, ambiente ou gym id zera o "último teste" (precisa testar de novo).
4. Ativar exige segredo do webhook; ligar a publicação automática exige gym id e chave.
5. Webhook exige `X-Gympass-Signature` = HMAC-SHA1 (hex) do **corpo cru** com o segredo; comparação em tempo constante,
   aceita maiúsculas/minúsculas e prefixo `sha1=`. Sem segredo configurado → 403; sem assinatura → 401; inválida → 403
   (conta no rate limit de falhas e no alerta do painel). Rate limit 300/min por IP; corpo máx. 256 KB.
6. Unidade do evento = configuração cujo segredo confere + gym do payload. Gym diferente do configurado → 400.
   Integração desligada → 202 e nada é gravado.
7. Idempotência: chave do evento = `event_id`/`id` explícito ou SHA-256 do JSON canônico. Evento já com resultado final
   (processado/cancelado/rejeitado/descartado) → `duplicado` (sem efeitos, sem nova resposta ao Wellhub). Evento com erro
   pode chegar de novo ou ser reprocessado (reaproveita a mesma linha, soma tentativas).
8. Processamento em SAVEPOINT: nada fica pela metade (aluno criado sem reserva, etc.).
9. Capacidade = a da agenda (capacidade da aula ou da unidade; contador atômico `reservas_ativas`). Lotada = reserva
   recusada no Wellhub com `CLASS_IS_FULL` (não é erro).
10. A resposta da reserva só é enviada uma vez por desfecho; se o PATCH falhar, a reserva aqui fica e o evento vira "erro"
    ("Reserva feita aqui, mas…"); o reprocessar só reenvia a resposta. O Wellhub rejeita sozinho reserva não respondida
    em 15 min → alerta vermelho no painel.
11. Cancelamento não cria aluno nem aula; cancelamento tardio também libera a vaga (situação `cancelada_tarde`).
12. Aluno: Gympass ID → CPF válido → criação automática (opcional). Nunca sobrescreve cadastro existente.
13. Check-in: no máximo um por aluno, por dia (fuso de negócio), por unidade. Só check-in **validado** entra no repasse.
14. `validar_checkin` é idempotente no dia (já validado → não chama o Wellhub de novo).
15. Slots publicados: só aulas futuras dentro da janela; vagas nunca negativas nem reservas > capacidade.
16. Publicação: `cancellable_until` = início − 6 h (mesma regra de aviso da agenda).
17. Repasse estimado = check-ins validados × valor por check-in da unidade (Decimal, 2 casas, meio para cima).
18. CSV protegido contra injeção de fórmula; Gympass ID completo só no CSV (tela mostra os 4 últimos).
19. Payload exibido na tela com e-mail, telefone, documento e Gympass ID mascarados.
20. Auditoria: configurar, gerar segredo, testar conexão, mapear, publicar grade, reprocessar, conferir, exportar,
    validar manualmente, e as ações do robô (aluno criado/vinculado, reserva criada/reativada/cancelada, check-in validado).

### 1.5 Telas (`/configuracoes/integracoes/wellhub`)

- **Painel**: alertas; indicadores (check-ins validados do mês com variação, repasse estimado, reservas/recusadas/
  canceladas, eventos com erro e check-ins pendentes); gráfico de check-ins por dia (validados × pendentes); progresso da
  configuração (5 passos, ativo, ambiente, horários publicados); últimos eventos; **validar check-in na recepção**.
- **Assistente** (`/configurar`): 5 passos com estado (concluído/pendência), testes em cada passo.
- **Eventos** (`/eventos`, aceita `?resultado=erro`): tabela, filtros, detalhe, reprocessar, conferido.
- **Relatório de repasse** (`/relatorio`): mês, unidade, indicadores, gráfico, por unidade, por aluno, CSV.
- Card "Wellhub" em Configurações › Integrações.

### 1.6 Estados de erro (mensagens ao usuário)

| Situação | Onde aparece |
|---|---|
| Credencial recusada (401/403) | "o Wellhub recusou a credencial. Confira a chave de API, o gym id e o ambiente." (teste/publicação; alerta) |
| Sem rede / timeout | "não foi possível falar com o Wellhub…" |
| 404 / 400 / 422 / 429 / 5xx | mensagens específicas, sem corpo da resposta nem segredo |
| Slot não publicado por nós | evento "erro": "O horário (slot X) não foi publicado por este sistema. Publique a grade e reprocesse." |
| Aluno não encontrado e criação desligada | evento "erro" |
| Sem Gympass ID / sem booking_number | evento "erro" |
| Aula lotada | evento "rejeitado" + PATCH `CLASS_IS_FULL` |
| Resposta ao Wellhub falhou | evento "erro" + alerta "reserva sem resposta" (15 min) |
| Assinatura inválida | 403 + alerta "Chamadas com assinatura inválida" (24 h) |
| Validação sem check-in no app | "O Wellhub não encontrou check-in deste aluno hoje…" |
| Tipo de evento desconhecido | evento "descartado" (202) |

### 1.7 Permissões

- `GET /api/wellhub/**` → `integracoes.ver`; demais métodos → `integracoes.editar` (perfil **Full**). Registradas por
  `adicionar_regras` no `routes.py` do módulo (nada editado em `core/permissoes.py`).
- Secretária e Professor: 403 em tudo (testado). Sem login: 401.
- Webhook `POST /api/webhooks/wellhub`: autenticação própria (assinatura), já coberto por `PUBLICAS_AUTENTICACAO_PROPRIA`.

### 1.8 Critérios de aceite (todos cobertos por teste em `backend/tests/wellhub/`)

- [x] Credenciais cifradas, somente escrita, auditoria sem valor, "Testar conexão" (OK, recusada, sem rede, 5xx).
- [x] Assinatura válida aceita; ausente 401; inválida/corpo alterado 403; sem segredo 403; rate limit; alerta.
- [x] Reserva cria aluno + reserva e responde `status 2`; reenvio idêntico = duplicado, sem segundo PATCH.
- [x] Capacidade cheia (inclusive por reservas da agenda) → `status 3 CLASS_IS_FULL`, nada gravado pela metade.
- [x] Cancelamento libera vaga; cancelar sem reserva não cria nada; reservar de novo reativa.
- [x] PATCH falhou → erro → reprocessar reenvia; reprocessar resolvido → 409.
- [x] Check-in (pendente, validação automática opcional, um por dia), check-in em reserva marca presença.
- [x] `validar_checkin`: não aplicável, ok, idempotente no dia, 404 do Wellhub, integração desligada/sem chave.
- [x] Grade: prévia sem rede, criar classe + slots com vagas/instrutor, republicar só o que mudou, remover excluída,
      erro por item, credencial recusada interrompe, tarefa periódica desligada por padrão.
- [x] Painel (KPIs, série, alertas, passos), relatório mensal (valores, variação, por aluno) e CSV (fórmula escapada).
- [x] Eventos: lista, filtros, detalhe mascarado, conferido/desfazer.
- [x] `demo.popular_demo(db)` idempotente.
- [x] Migração 0140 = modelos (colunas, uniques, índices) e downgrade limpa.
- [x] `tests/test_cobertura_rotas.py` verde.

---

## 2. O que foi feito

- **Backend** (`app/modules/wellhub/`): `models.py`, `cliente.py` (HTTP, fábrica trocável), `regras.py` (funções puras),
  `eventos.py` (processamento, `validar_checkin`), `grade.py`, `relatorio.py`, `servico.py`, `schemas.py`, `routes.py`,
  `tarefas.py` (`wellhub-publicar-grade`, 30 min), `demo.py`. Migração `alembic/versions/0140_wellhub.py`.
- **Testes**: `tests/wellhub/` — 100+ casos, Wellhub simulado com `httpx.MockTransport` (internet proibida por fixture).
- **Frontend**: painel, assistente, eventos, relatório; componentes em `components/wellhub/`; tipos em `lib/tipos-wellhub.ts`.

### Rotas

| Método | Caminho | Permissão |
|---|---|---|
| GET | `/api/wellhub` | integracoes.ver |
| PUT | `/api/wellhub/unidades/{id}` | integracoes.editar |
| POST | `/api/wellhub/unidades/{id}/segredo-webhook` | integracoes.editar |
| POST | `/api/wellhub/unidades/{id}/testar-conexao` | integracoes.editar |
| POST | `/api/wellhub/unidades/{id}/testar-webhook` | integracoes.editar |
| POST | `/api/wellhub/unidades/{id}/produtos` | integracoes.editar |
| PUT | `/api/wellhub/unidades/{id}/mapeamentos` | integracoes.editar |
| POST | `/api/wellhub/unidades/{id}/grade/previa` | integracoes.editar |
| POST | `/api/wellhub/unidades/{id}/grade/publicar` | integracoes.editar |
| GET | `/api/wellhub/unidades/{id}/painel` | integracoes.ver |
| GET | `/api/wellhub/relatorio` · `/api/wellhub/relatorio.csv` | integracoes.ver |
| GET | `/api/wellhub/eventos` · `/api/wellhub/eventos/{id}` | integracoes.ver |
| POST | `/api/wellhub/eventos/{id}/reprocessar` · `/conferido` | integracoes.editar |
| GET | `/api/wellhub/alunos?q=` | integracoes.ver |
| POST | `/api/wellhub/validar-checkin` | integracoes.editar |
| POST | `/api/webhooks/wellhub` | assinatura `X-Gympass-Signature` |

### API estável para outros módulos

```python
from app.modules.wellhub.servico import validar_checkin, ResultadoValidacao
res = validar_checkin(db, aluno_id)          # faz commit (use commit=False dentro da sua transação)
res.aplicavel  # False = aluno não é do Wellhub → siga a sua regra normal
res.ok         # True = pode entrar (validado agora ou antes, hoje)
res.mensagem   # texto pronto para a recepção
```

`demo.popular_demo(db)` → para o seed (idempotente; usa a 1ª unidade e o 1º serviço ativos; sandbox sem chave, sem rede).

---

## 3. A confirmar com a credencial real (sandbox do Wellhub)

A documentação pública (developers.wellhub.com) é uma SPA e os detalhes de campos não são todos legíveis sem acesso de
parceiro; o que segue foi implementado pelo que é público e está isolado em `cliente.py`/`regras.py` para ajuste fácil:

1. **URLs**: produção `https://api.partners.gympass.com`, sandbox `https://apitesting.partners.gympass.com`
   (troque por `WELLHUB_URL_PRODUCAO`/`WELLHUB_URL_SANDBOX` sem mexer em código).
2. **Autenticação**: `Authorization: Bearer <chave>` + `X-Gym-Id` em todas as chamadas (um token para Booking e Access
   Control). Confirmar se a Booking API aceita/exige o `X-Gym-Id`.
3. **Caminhos da Booking API**: `/booking/v1/gyms/{gym}/classes` (GET/POST `{"classes":[…]}`, PUT `/{id}`),
   `/classes/{id}/slots` (POST; PATCH `{total_capacity,total_booked}`; DELETE), `/bookings/{booking_number}` (PATCH),
   `/products` (GET — **confirmar** se existe nesse caminho ou só pelo time do Wellhub). Formato das respostas (`id` da
   classe/slot) lido de forma tolerante.
4. **Status do PATCH de reserva**: `2` = reservado, `3` = rejeitado; motivo `CLASS_IS_FULL`. **Confirmar códigos.**
5. **Campos do slot**: `occur_date` (UTC ISO), `length_in_minutes`, `total_capacity`, `total_booked`, `product_id`,
   `booking_window{opens_at,closes_at}`, `cancellable_until`, `instructors[{name,substitute}]`, `virtual`.
6. **Webhooks**: `event_type` (`booking-requested`, `booking-canceled`, `booking-late-canceled`, `checkin`,
   `checkin-booking-occurred`) e `event_data{user{unique_token,name|first_name/last_name,email,phone_number},
   slot{id,gym_id,class_id,booking_number}, gym{id,product}, timestamp}`. Confirmar se há `event_id` (usado na
   idempotência quando vier) e se CPF é enviado.
7. **Assinatura**: HMAC-SHA1 hex maiúsculo do corpo cru no `X-Gympass-Signature` (doc do check-in webhook). Confirmar
   que os webhooks da Booking API usam o mesmo esquema e se o segredo é um por gym ou um por parceiro (o código aceita
   os dois: tenta todos os segredos e desempata pelo gym).
8. **Access Control**: `POST /access/v1/validate` `{"gympass_id"}`; 200 = validado; 400/404 = sem check-in. Confirmar
   códigos de resposta e se o sandbox valida IDs de teste.
9. **Cancelamento tardio**: tratado como cancelamento (libera vaga). Confirmar se o Wellhub conta como visita (repasse).
10. **`cancellable_until` = início − 6 h**: confirmar se o Wellhub aceita/precisa.
11. **Check-in em reserva** (`checkin-booking-occurred`): registrado como pendente de validação; confirmar se já conta
    como validado no Wellhub.

## 4. Pedidos ao coordenador / avisos

- **`tests/dados/test_migracao.py` falha** com qualquer migração nova: ele aplica só a `0001` e compara com TODOS os
  modelos. Com a `0140_wellhub` (e as dos outros módulos paralelos) o teste precisa aplicar a cadeia inteira (`0001` +
  as novas, na ordem do `down_revision`). Meu teste próprio (`test_migracao_0140_igual_aos_modelos_e_reversivel`)
  verifica `0001 → 0140` só para as tabelas `wellhub_*`. Atenção: vários módulos com `down_revision = "0001_pilates_inicial"`
  geram múltiplas heads no Alembic — encadeie na integração.
- `app/modules/__init__.py::registrar_modelos` não importa `wellhub` (não é meu arquivo). As tabelas entram no metadata
  quando o `main.py` descobre `wellhub/routes.py`; para o `alembic autogenerate` enxergar sem o app, acrescente
  `wellhub` na lista.
- Seed: chamar `from app.modules.wellhub.demo import popular_demo; popular_demo(db)` depois de criar unidades e serviços.
- Bloqueio por plano: não implementado (coordenador).

## 5. Linhas em arquivos compartilhados

- `frontend/app/(app)/configuracoes/integracoes/page.tsx`: +1 import (`Dumbbell`) e +1 cartão "Wellhub" (8 linhas).
- Nenhuma alteração em `core/permissoes.py` (regras via `adicionar_regras`), `nav.ts` (a aba Integrações já cobre as
  sub-rotas), `types.ts` ou arquivos do TotalPass.
