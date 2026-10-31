# Progresso — Admin MayaFit (backend)

Backend do **Admin MayaFit** (cliente `tipo="mayacorp"` no controle; identificadores de código continuam `mayacorp`,
`admin_mayacorp`, `/api/admin/*`; todo texto visível diz "MayaFit"/"Admin MayaFit"/"Equipe MayaFit"). Porte do admin do
MayaJus (`MayacorpAutomacoes_CFME/backend/app/controle/routes_*.py`) com escritório → estúdio, robôs → extras,
notas → alunos ativos, mais o que o Jefferson pediu (indicadores, linha do tempo, saúde, ações de um clique, demo).

---

## 1. Especificação

### 1.1 Regras de negócio (numeradas)

**Planos e recursos**
- **R1.** Planos padrão (criados uma vez por `planos.garantir_padrao`, depois editáveis no admin; nenhum preço fixo nas telas):

  | Plano | Mensal | Anual | Usuários | Alunos ativos | Recursos |
  |---|---|---|---|---|---|
  | Essencial | R$ 49,90 | R$ 499,00 | 2 | 60 | gestao, site, crm |
  | Estúdio | R$ 89,90 | R$ 899,00 | 5 | 150 | Essencial + app_aluno, whatsapp, checkin, integracoes |
  | Pro | R$ 149,90 | R$ 1.499,00 | 10 | 350 | Estúdio + ia, nfse |
  | Rede | R$ 289,90 | R$ 2.899,00 | 25 | ilimitado | todos (inclui catraca) |

  Excedentes padrão: **R$ 0,50 por aluno ativo** acima do limite e **R$ 14,90 por usuário** acima do limite (também são os
  defaults de `Plano` em `controle/models.py`). Limite vazio = ilimitado.
- **R2.** Recursos (`planos.RECURSOS`): gestao, site, crm, app_aluno, whatsapp, checkin, integracoes, ia, nfse, catraca.
  Extras liberados estúdio a estúdio (`planos.EXTRAS`, `Cliente.extras`): receita_saude, etl, catraca (avulsa p/ quem não é Rede).
  Chave desconhecida é descartada ao salvar a ficha; recurso desconhecido no plano → 400.

**Estúdio novo e teste grátis**
- **R3.** Estúdio novo (admin ou aprovação do cadastro do site) chama `service.provisionar(..., primeiro_acesso=True)`, com
  **60 dias de teste por padrão** (editável na criação; `0`/vazio = sem teste). O e-mail de boas-vindas leva o link de primeiro
  acesso (o dono cria o usuário master). O e-mail do financeiro, se vazio, vira o e-mail do primeiro acesso.
- **R4.** Durante o teste **nada é cobrado**. Quando o teste acaba (tarefa diária), o estúdio passa a **ativo** e nasce a
  **1ª mensalidade** (plano − desconto, sem excedentes), vencendo em **3 dias**; com Mercado Pago conectado, vai por e-mail.
  Estúdio criado **sem** teste já nasce com a 1ª mensalidade.
- **R5.** Estender teste: +N dias (1–90) a partir do maior entre hoje e `teste_ate`. Vale para quem está em teste ou para quem
  saiu dele **sem nunca ter pago** (as mensalidades em aberto são canceladas e o status volta a "teste"). Quem já pagou → 400.

**Mensalidade**
- **R6.** Mensalidade = plano (mensal; ou anual só no mês de aniversário do contrato) − desconto por indicação
  + alunos ativos acima do limite × preço do aluno excedente + usuários acima do limite × preço do usuário adicional.
  Quem paga no **cartão** (assinatura) tem o plano debitado pelo Mercado Pago: a mensalidade leva só os excedentes.
  Valor zero não gera cobrança. Uma mensalidade por estúdio e mês (idempotente).
  Exemplo testado: Estúdio R$ 89,90, 163 alunos (limite 150), 6 usuários (limite 5), 1 indicado → 89,90 − 4,49 + 6,50 + 14,90 = **R$ 106,81**.
- **R7.** O uso vem de `Cliente.uso` (foto gravada pela tarefa diária: `{alunos_ativos, usuarios, aulas_mes, em}`); sem foto,
  é coletado na hora com `service.coletar_uso(estudio)`. O usuário Suporte não conta (responsabilidade do `coletar_uso`).
- **R8.** Vencimento = dia configurado (1–28) do mês; se a mensalidade nasce depois desse dia no mês corrente, vence em 3 dias.
- **R9.** Desconto por indicação: cada estúdio indicado **ativo** dá X% (política, padrão 5%) a quem indicou, somando até o
  máximo da política, **nunca acima de 10%**. Arredondamento ao centavo (meio para cima).

**Mercado Pago**
- **R10.** Token e assinatura secreta são **somente escrita**, cifrados com `app.core.segredos` (a tela vê "configurado" e os 4
  últimos caracteres); salvar o token já testa a conta (`/users/me`). A auditoria registra a troca, nunca o valor.
- **R11.** Link de pagamento (Checkout Pro: Pix/cartão/boleto) é criado uma vez por cobrança e reaproveitado.
  Assinatura no cartão: só ciclo mensal, exige e-mail do financeiro; ao trocar de plano, o valor da assinatura autorizada é ajustado.
- **R12.** Webhook `/api/public/mercadopago`: com assinatura secreta cadastrada, aviso **sem `x-signature` válido é ignorado**
  (responde 200 para o MP não insistir). Nada é aceito às cegas: pagamento/assinatura são **relidos na API do MP** com o nosso token.
  Pagamento aprovado → baixa + e-mail "pagamento recebido"; débito da assinatura → cobrança "cartao" paga.
- **R13.** Régua (padrão −3, 0, 3, 10 dias do vencimento): um e-mail por dia no máximo, só o passo mais recente; passos enviados
  ficam em `Cobranca.avisos`.

**Atraso e status**
- **R14.** Status: `teste | ativo | suspenso | inativo`. Suspenso **entra e é avisado**; inativo não entra.
- **R15.** Cobrança vencida há **15 dias** (`SUSPENDER_APOS_DIAS`) → estúdio **suspenso** automaticamente + e-mail.
  Quando não sobra nada vencido (baixa manual ou pelo MP), volta a **ativo** sozinho.
- **R16.** Suspender/Reativar manuais registram motivo opcional. Reativar só faz sentido para suspenso/inativo (senão 400).

**Indicadores do Início**
- **R17.** MRR = Σ (plano mensalizado — anual ÷ 12 — com desconto) + excedentes estimados pela foto de uso, dos estúdios
  ativos e suspensos. Em teste e inativos não entram.
- **R18.** Crescimento = estúdios criados no mês (por `criado_em`) × mês anterior, e série de 12 meses (novos e saídas).
- **R19.** Churn do mês = estúdios cujo status virou **inativo** no mês (pela linha do tempo); taxa = saídas ÷ (ativos+suspensos + saídas).
- **R20.** Receita por mês = soma das cobranças **pagas** pela data do pagamento (12 meses, mais antigo → atual).
- **R21.** Funil do site: recebidas → aprovadas (em teste) → convertidas (aprovadas cujo estúdio está ativo/suspenso); taxa = convertidas ÷ recebidas.
- **R22.** Testes vencendo = em teste com `teste_ate` entre hoje e hoje + 7.

**Ficha: linha do tempo e saúde**
- **R23.** Linha do tempo (`evento_cliente`): criação, status (com de/para e motivo), plano/ciclo, extras, teste estendido, endereços,
  cobranças geradas/canceladas, pagamentos, contratos gerados/enviados/assinados, acessos reenviados. Autor = usuário do admin ou "Sistema".
- **R24.** Saúde: **Em risco** se suspenso/inativo, cobrança vencida há 15+ dias, sem acesso há 14+ dias, ou ninguém entrou
  (fora do teste). **Atenção** se alguma cobrança vencida, sem acesso há 7+ dias, uso ≥ 90% de um limite (ou acima), ninguém
  entrou ainda (em teste) ou teste acabando em ≤ 7 dias. Senão **Saudável**. Último acesso = maior `ultimo_acesso` da equipe (Suporte não conta).

**Usuários do estúdio e acesso**
- **R25.** Admin cria usuário no banco do estúdio (perfil Full/Secretária/Professor; login curto gerado do e-mail se vazio,
  único no estúdio) e manda convite (link de uso único, 48 h). "Zerar senha" apaga a senha, derruba as sessões e manda link.
- **R26.** "Zerar senha do Suporte" volta a senha do `suporte.<slug>` para a senha do Suporte definida no admin (hash da
  `PoliticaComercial`), desbloqueia e derruba as sessões. Sem senha definida → 400.
- **R27.** "Reenviar acesso": sem master → novo link de primeiro acesso; com master → link de nova senha a cada administrador
  (a senha atual continua valendo).

**Segurança**
- **R28.** Toda rota `/api/admin/*` exige login + estúdio atual `mayacorp` + usuário administrador; senão **403 "Área exclusiva do
  admin MayaFit."**. "Meu plano" (`/api/meu-plano`) só em estúdio cliente (404 no admin e no modo de um banco só) e só para administradores (403).
- **R29.** Rotas públicas (na lista `PUBLICAS`, todas com limite por IP): planos (120/min), cadastro (5/hora; campo-isca `site`
  descarta robôs), solicitação/aprovar/recusar pelo link assinado (`app.core.links`, finalidade própria, 7 dias), webhook (300/min).
- **R30.** Toda ação que muda algo audita no banco do admin (`ctx.auditar`) e a maioria também vira evento na linha do tempo.

### 1.2 Critérios de aceite (cobertos em `backend/tests/admin_mayacorp/`)

1. Secretária, estúdio cliente ou modo de um banco só → 403 em `/api/admin/*`; sem login → 401. (`test_guarda_*`)
2. Planos padrão com os preços/limites da R1; editar valida recursos e nome único. (`test_planos_padrao_e_edicao`, `test_planos_padrao`)
3. Estúdio novo nasce em teste de 60 dias, com subdomínio padrão, convite por e-mail "Equipe MayaFit", evento "criado" e **sem cobrança**;
   sem teste nasce com a 1ª mensalidade vencendo em 3 dias. (`test_novo_estudio_com_teste_de_60_dias`)
4. Ficha: troca de plano/extras/status/endereços aparecem na linha do tempo; o endereço padrão não sai. (`test_ficha_status_dominios_e_linha_do_tempo`)
5. Uso com foto e sem foto (coleta). (`test_uso_foto_ou_coleta`) · Usuários, convite, zerar senha, Suporte. (`test_usuarios_do_estudio`, `test_senha_do_suporte`)
6. Mensalidade com excedentes (R$ 94,90 = 89,90 + 10 × 0,50), idempotente; webhook dá baixa; assinatura secreta errada é ignorada. (`test_cobranca.py`)
7. Régua manda um aviso com o passo mais recente; 15 dias de atraso suspende; pagar reativa; fim do teste gera a 1ª mensalidade. (`test_regua_fim_do_teste_e_suspensao`)
8. Meu plano: upgrade, cartão, link; downgrade com usuários demais é barrado; só administrador. (`test_meu_plano_*`)
9. Cadastro público → aprovação no admin ou pelo link (link vencido/de outra finalidade → 400); 6º cadastro na hora → 429. (`test_cadastro.py`)
10. Início com a demonstração: MRR R$ 556,63 (550,13 + 6,50), churn 1 (20,0%), funil, receita de 12 meses, testes vencendo. (`test_inicio_com_dados_de_demonstracao`)
11. Saúde e ações de um clique (estender, suspender, reativar). (`test_saude_e_acoes_de_um_clique`) · Tarefas só no modo multi e 1×/dia. (`test_tarefas_*`)

---

## 2. Rotas (para o frontend)

Todas sob `/api`. Dinheiro sai como **texto** `"189.00"`; datas ISO. Erros: `{"detail": "..."}` (422 com `erros[]`).

### 2.1 Admin (`/api/admin/*`, guarda R28)

| Método | Caminho | Corpo | Resposta |
|---|---|---|---|
| GET | `/admin/resumo` | — | `{clientes, por_status{teste,ativo,suspenso,inativo}, novos_mes, churn_mes, mrr, mrr_planos, mrr_excedentes, crescimento{novos_mes, novos_mes_anterior, variacao, serie[{mes, novos, saidas}]}, churn{saidas_mes, taxa_mes, estudios[{id,slug,nome}]}, cobrancas{vencidas{quantidade,valor}, pendentes_mes{quantidade,valor}, recebido_mes, inadimplentes}, receita_por_mes[{mes, valor}], solicitacoes_novas, funil{recebidas, novas, recusadas, aprovadas, em_teste, convertidas, taxa_conversao}, testes_vencendo[{id,slug,nome,teste_ate,dias}]}` |
| GET | `/admin/meta` | — | `{status[{chave,rotulo}], dias_teste_padrao}` |
| GET | `/admin/clientes` | `?q=&status=` | `Estudio[]` |
| POST | `/admin/clientes` | ficha + `slug?, admin_nome?, admin_email, dias_teste? (padrão 60; 0 = sem teste), dominios[]` | 201 `Estudio + convite` |
| GET | `/admin/clientes/{id}` | — | `Estudio` |
| PUT | `/admin/clientes/{id}` | ficha completa (campo ausente = vazio; `extras` ausente = não mexe) | `Estudio` |
| POST | `/admin/clientes/{id}/status` | `{status, teste_ate?}` | `Estudio` |
| POST | `/admin/clientes/{id}/estender-teste` | `{dias: 1..90}` | `Estudio` |
| POST | `/admin/clientes/{id}/suspender` | `{motivo?}` | `Estudio` |
| POST | `/admin/clientes/{id}/reativar` | `{motivo?}` | `Estudio` |
| POST | `/admin/clientes/{id}/reenviar-acesso` | — | `{tipo: "primeiro_acesso"\|"redefinir_senha", enviado_para[], link?}` |
| POST | `/admin/clientes/{id}/boas-vindas` | — | `{link, enviado_para}` (400 se o master já existe) |
| POST | `/admin/clientes/{id}/dominios` | `{host}` | 201 `Estudio` |
| DELETE | `/admin/clientes/{id}/dominios/{did}` | — | `Estudio` (400 no endereço padrão) |
| GET | `/admin/clientes/{id}/uso` | — | `{mes, usuarios, limite_usuarios, alunos_ativos, limite_alunos, aulas_mes, em, usuarios_excedentes, alunos_excedentes, valor_excedente}` |
| GET | `/admin/clientes/{id}/saude` | — | `{nivel: boa\|atencao\|risco, rotulo, motivos[], acesso{ultimo_acesso, dias_sem_acesso}, uso{...uso, pct_alunos, pct_usuarios}, inadimplencia{vencidas, valor, maior_atraso_dias}, teste{teste_ate, dias_restantes}}` |
| GET | `/admin/clientes/{id}/eventos` | `?tipo=&limite=200` | `[{id, tipo, tipo_rotulo, descricao, dados, usuario, criado_em}]` (mais recente primeiro) |
| GET | `/admin/clientes/{id}/usuarios` | — | `[{id, nome, email, login, ativo, acesso_sistema, convite_pendente, perfil, administrador, ultimo_acesso, suporte, equipe_mayacorp}]` |
| POST | `/admin/clientes/{id}/usuarios` | `{nome, email, login?, perfil: Full\|Secretária\|Professor}` | 201 usuário + `convite` |
| POST | `/admin/clientes/{id}/usuarios/{uid}/convite` | — | `{mensagem, link}` |
| POST | `/admin/clientes/{id}/usuarios/{uid}/zerar-senha` | — | `{mensagem, link}` |
| POST | `/admin/clientes/{id}/usuarios/{uid}/ativo` | `{ativo}` | usuário |
| POST | `/admin/clientes/{id}/suporte/zerar-senha` | — | `{mensagem, login}` |
| GET/PUT | `/admin/clientes/{id}/pagamento` | PUT `{forma_pagamento: link\|cartao}` | `{forma_pagamento, assinatura_id, assinatura_status}` |
| POST | `/admin/clientes/{id}/assinatura` | — | idem + `link` (e-mail ao financeiro) |
| GET | `/admin/clientes/{id}/contratos` | — | `ContratoEstudio[]` |
| POST | `/admin/clientes/{id}/contratos` | `{modelo_id}` | 201 contrato + `variaveis_vazias[]` |
| GET | `/admin/contratos` | — | `ContratoEstudio[]` + `cliente_nome` |
| GET | `/admin/contratos/variaveis` | — | `[{chave, rotulo}]` (inclui `alunos_ativos`, `aluno_excedente`) |
| PUT | `/admin/contratos/{kid}` | `{titulo, corpo}` | contrato (400 se não for rascunho) |
| GET | `/admin/contratos/{kid}/pdf` | — | PDF |
| POST | `/admin/contratos/{kid}/enviar` | `{para[], mensagem?}` | contrato |
| POST | `/admin/contratos/{kid}/status` | `{status: assinado\|cancelado}` | contrato |
| GET/POST | `/admin/modelos-contrato` | `{nome, corpo, ativo}` | `ModeloContrato{…, variaveis_desconhecidas[]}` |
| PUT | `/admin/modelos-contrato/{mid}` | idem | idem |
| GET/POST | `/admin/planos` | `PlanoIn` | `PlanoOut` |
| PUT | `/admin/planos/{pid}` | `PlanoIn` | `PlanoOut` |
| GET | `/admin/recursos` | — | `[{chave, rotulo}]` (10) |
| GET | `/admin/extras` | — | `[{chave, rotulo}]` (receita_saude, etl, catraca) |
| GET/PUT | `/admin/politica-indicacao` | PUT `{desconto_por_indicacao, desconto_maximo}` (≤ 10) | `{desconto_por_indicacao, desconto_maximo, teto}` |
| GET/PUT | `/admin/suporte` | PUT `{senha}` | `{senha_definida}` |
| GET/PUT | `/admin/cobranca/config` | PUT `{token?, segredo?, dia_vencimento, gerar_automatico, regua[]}` | `{conectado, segredo_definido, token_final, conta, dia_vencimento, gerar_automatico, regua, url_notificacao}` |
| POST | `/admin/cobranca/config/testar` | — | `{ok, conta, id}` |
| GET | `/admin/cobrancas` | `?status=pendente\|vencida\|paga\|cancelada&cliente_id=` | `Cobranca[]` |
| GET | `/admin/cobrancas/resumo` | — | `{em_aberto, vencido, recebido_mes, inadimplentes}` |
| POST | `/admin/cobrancas/avulsa` | `{cliente_id, descricao, valor, vencimento, enviar}` | 201 `Cobranca` |
| POST | `/admin/cobrancas/gerar` | `{competencia: AAAA-MM, enviar}` | `{criadas[], erros[]}` |
| POST | `/admin/cobrancas/{kid}/enviar` | — | `Cobranca + enviado_para[]` |
| POST | `/admin/cobrancas/{kid}/baixa` | `{forma}` | `Cobranca` |
| POST | `/admin/cobrancas/{kid}/cancelar` | — | `Cobranca` |
| GET | `/admin/solicitacoes` | `?status=nova\|aprovada\|recusada` | `Solicitacao[]` |
| POST | `/admin/solicitacoes/{sid}/aprovar` | `{dias_teste? (60), slug?}` | `Estudio + convite` |
| POST | `/admin/solicitacoes/{sid}/recusar` | — | `Solicitacao` |
| POST | `/admin/ia/ficha` · `/admin/ia/contrato` · `/admin/ia/mensagem` | `{texto}` · `{instrucao?, corpo?}` · `{titulo, cliente_id, instrucao?}` | `{campos}` · `{corpo, resumo, variaveis_desconhecidas}` · `{mensagem}` |

**Estudio**: `id, slug, nome, status, status_rotulo, teste_ate, criado_em, documento, responsavel, email_financeiro, telefone,
plano (PlanoOut), plano_id, ciclo, valor, inicio_contrato, observacao, banco_principal, dominios[{id, host, padrao}],
dominio_padrao, extras[], forma_pagamento, assinatura_status, indicado_por{id,nome}, indicado_por_id, indicacoes_ativas,
desconto_percentual, valor_com_desconto, uso{mes, usuarios, limite_usuarios, alunos_ativos, limite_alunos, aulas_mes, em,
…excedentes, valor_excedente} (só a foto), mensalidade_estimada`.
**PlanoOut**: `id, nome, preco_mensal, preco_anual, usuarios, alunos_ativos, preco_aluno_excedente, preco_usuario_adicional, recursos[], ativo, ordem`.
**Cobranca**: `id, cliente_id, cliente_nome, tipo, competencia, descricao, itens[{descricao, valor}], valor, vencimento,
status (pendente|vencida|paga|cancelada), status_rotulo, link, pago_em, forma_paga, avisos[], criado_em`.
**Solicitacao**: `id, nome, documento, responsavel, email, telefone, plano, ciclo, alunos, indicacao, mensagem, status, cliente_id, criado_em`.

### 2.2 Meu plano (estúdio cliente, administradores)

| Método | Caminho | Corpo | Resposta |
|---|---|---|---|
| GET | `/meu-plano` | — | `{nome, status, teste_ate, ciclo, plano, valor, forma_pagamento, assinatura_status, pode_alterar, uso, extras[{chave,rotulo}], planos[], recursos[], em_aberto[], pagas[]}` |
| PUT | `/meu-plano` | `{plano_id, ciclo}` | igual ao GET |
| POST | `/meu-plano/cartao` | — | `{link}` |
| POST | `/meu-plano/cobrancas/{kid}/link` | — | `{link}` |

### 2.3 Públicas (sem login)

| Método | Caminho | Corpo | Resposta |
|---|---|---|---|
| GET | `/public/planos` | — | `PlanoOut[]` (ativos) + `recursos_rotulos[{chave, rotulo}]` |
| POST | `/public/cadastro` | `{nome, documento?, responsavel, email, telefone, plano_id?, ciclo, alunos?, indicacao?, mensagem?, aceite, site?}` | 201 `{ok}` |
| GET | `/public/solicitacao` | `?token=` | `Solicitacao` |
| POST | `/public/solicitacao/aprovar` | `{token, dias_teste? (60)}` | `Estudio + convite` |
| POST | `/public/solicitacao/recusar` | `{token}` | `Solicitacao` |
| POST | `/public/mercadopago` | aviso do MP | `{ok}` (503 se o MP falhar, para ele tentar de novo) |

### 2.4 Divergências com `docs/progresso-admin-frontend.md` (frontend) — para ajustar na integração

1. **Estender teste**: o frontend faz `PUT /admin/clientes/{id}` com `teste_ate`. Funciona para quem está em teste, mas o
   backend tem `POST /admin/clientes/{id}/estender-teste {dias}`, que também trata quem já saiu do teste sem pagar (R5) e
   registra o evento. Sugiro usar a rota nova. Idem **Suspender/Reativar** (`/suspender`, `/reativar` com motivo) e
   **Reenviar acesso** (`/reenviar-acesso`), que escolhe sozinho entre primeiro acesso e nova senha.
2. **Churn/crescimento/linha do tempo**: não precisam mais ser calculados no navegador: `/admin/resumo` traz `novos_mes`,
   `churn_mes`, `crescimento`, `churn`, `receita_por_mes` (por **data do pagamento**; o "faturado por competência" do gráfico
   pode ser derivado de `/admin/cobrancas`), `funil`; e há `GET /admin/clientes/{id}/eventos` e `/saude`.
3. **Usuários**: `equipe_mayacorp` (= Suporte) e também `suporte`; mapeia a coluna `usuario.suporte` da fundação quando existir
   (`getattr`), senão o login `suporte.<slug>`. Há ainda `POST .../usuarios/{uid}/convite` e `POST .../suporte/zerar-senha`.
4. **Extras**: `GET /admin/extras` devolve também `catraca` (pedido do coordenador).
5. `dominios[]` tem `padrao` a mais; `Estudio` tem `dominio_padrao`, `forma_pagamento`, `mensalidade_estimada` a mais.

---

## 3. O que foi feito

| Arquivo | O quê |
|---|---|
| `app/controle/planos.py` | RECURSOS, EXTRAS, planos padrão (R1), `DIAS_TESTE_PADRAO = 60`, `garantir_padrao` |
| `app/controle/indicacao.py` | política, desconto com teto (R9) |
| `app/controle/cobranca.py` | uso (foto/coleta), itens da mensalidade (regra pura), gerar/1ª/avulsa, link, assinatura, baixa com reativação, webhook, e-mails, régua, fim do teste, suspensão, fotos de uso |
| `app/controle/mercadopago.py`, `email_modelo.py` | portados (descritor "MAYAFIT", rodapé MayaFit) |
| `app/controle/contratos.py` | variáveis (`alunos_ativos`, `aluno_excedente`…), preencher, PDF |
| `app/controle/emails.py` | `enviar_email(para, assunto, corpo, anexos=None)` pelo SMTP/identidade do banco do estúdio MayaCorp; manda o HTML do modelo quando `core.email.enviar` aceitar `html=` |
| `app/controle/eventos.py`, `saude.py` | linha do tempo; saúde e indicadores (regras puras) |
| `app/controle/ponte.py` | único ponto de contato com a fundação (`tenancy`/`service`) com import tardio: o app sobe mesmo sem ela |
| `app/controle/models.py` | **nova tabela `evento_cliente`** (EventoCliente) e defaults de `Plano` (0,50 / 14,90) |
| `app/modules/admin_mayacorp/` | `routes.py` (router + router_publico + regras), `rotas_estudios.py`, `rotas_cobranca.py` (admin, webhook, Meu plano), `rotas_cadastro.py`, `rotas_painel.py` (Início, saúde, eventos, ações), `schemas.py`, `servico.py` (guarda e saídas), `tarefas.py`, `demo.py` |
| `app/core/permissoes.py` | só **acréscimo** de 2 linhas em `PUBLICAS` |
| `tests/test_cobertura_rotas.py` | só **acréscimo** das 6 rotas públicas na lista esperada |
| `tests/admin_mayacorp/` | 38 testes (controle em SQLite temporário, fundação simulada) |

Demonstração: `uv run python -m app.modules.admin_mayacorp.demo` (idempotente; `--remover` apaga). Cria 6 estúdios "demo-*"
(todos os status), ~40 mensalidades em 12 meses, indicação, linha do tempo e 4 solicitações — só no controle.

## 4. Decisões

- Caminhos e respostas do MayaJus mantidos (`/admin/clientes/...`: "cliente" do controle = estúdio). `robos` → `extras`,
  `notas_mes` → `alunos_ativos`, `preco_nota_excedente` → `preco_aluno_excedente`, `usuarios` (solicitação) → `alunos`.
- Guarda devolve **403** (no MayaJus era 404) com "Área exclusiva do admin MayaFit.".
- Rotas `/admin/*` e `/meu-plano` ficam LIVRES no mapa de permissões; a guarda de cada uma é mais estrita (MayaCorp + administrador).
- Link de aprovação por e-mail usa `app.core.links` (HMAC + prazo, finalidade `aprovar-solicitacao`) — `criar_token` do MayaFit
  só aceita access/refresh.
- Convites e "zerar senha" usam `auth_service.criar_link_email` (link de uso único do MayaFit), não JWT de reset.
- Suspensão automática por atraso (R15) — no MayaJus era só manual; pedido do coordenador ("suspender/avisar"). Suspenso continua entrando.
- 1ª mensalidade só depois do teste (R4), conforme o Jefferson.

## 5. Pendências / dependências da fundação

1. **`alembic_controle/`**: falta a migração da tabela **`evento_cliente`** (modelo em `controle/models.py`) — a pasta é da fundação.
   Os defaults novos de `Plano` são só do lado Python (sem `server_default`), não exigem migração.
2. **`app.worker.registrar_tarefa(..., global_=True)`**: `tarefas.py` passa `global_=True` assim que a assinatura aceitar
   (detecta pela assinatura). Até lá, se o worker multi rodar as tarefas uma vez por estúdio, elas continuam corretas
   (idempotentes, 1×/dia por processo, só mexem no controle), mas rodariam mais de uma vez.
3. `service.coletar_uso(estudio)` deve devolver `{alunos_ativos, usuarios, aulas_mes}` sem contar o Suporte.
4. `service.provisionar(**ficha)` precisa aceitar os campos da ficha: `documento, responsavel, email_financeiro, telefone, plano_id,
   ciclo, inicio_contrato, observacao, indicado_por_id, extras`.
5. `core.email.enviar` ainda não aceita `html=`/`imagens=`: os e-mails saem em texto puro (o HTML com a marca liga sozinho quando aceitar).
6. Links de convite/nova senha usam `settings.frontend_url`; no modo multi devem apontar para o endereço do estúdio (fundação).
7. `/auth/me` com `estudio{slug, nome, mayacorp}` e `/auth/primeiro-acesso` (GET/POST) são da fundação (o frontend depende).
8. "Acessar o estúdio" (entrar como Suporte a partir do admin) não foi feito: depende do login multi da fundação.
9. Catálogo de logins (`Login`) não é atualizado quando o admin cria usuário no estúdio: a fundação sincroniza (sincronia.py).
