# Progresso — Admin MayaFit (frontend)

Telas do **Admin MayaFit** (`/admin/*`, só no estúdio `mayacorp`) e as telas públicas ligadas a ele, portadas do MayaJus
(`MayacorpAutomacoes_CFME/frontend`) com escritório → estúdio, robôs → extras, notas → alunos ativos.
Nome visível: sempre "Admin MayaFit"; identificadores de código e rotas continuam `mayacorp` / `/api/admin/*`.

## Arquivos

| Onde | O quê |
|---|---|
| `frontend/lib/tipos-admin.ts` | Tipos (Estudio, PlanoOut, UsoEstudio, Cobranca, Solicitacao, MeuPlano…), rótulos e tons de situação |
| `frontend/lib/admin.ts` | Consultas compartilhadas (`useEstudios`, `usePlanos`, `useRecursos`, `useExtras`, `useResumoAdmin`), `useAreaMayaCorp`, `DIAS_TESTE_PADRAO = 60`, utilitários |
| `frontend/components/admin/` | `area-mayacorp` (guarda), `estudio-dialog`, `ficha-abas` (uso, usuários, domínios, contratos), `cobranca` (avulsa, aba da ficha), `acoes-rapidas`, `saude` (saúde + linha do tempo), `graficos` (receita, novos, funil), `indicador`, `medidor` |
| `frontend/app/(app)/admin/` | `layout.tsx` (guarda), `page.tsx` (Início), `estudios`, `estudios/[id]`, `solicitacoes`, `planos`, `contratos`, `cobrancas` |
| `frontend/app/(app)/minha-conta/plano/page.tsx` | Meu plano (no estúdio) |
| `frontend/app/cadastro/` | Formulário público "Quero o MayaFit" |
| `frontend/app/(auth)/primeiro-acesso/page.tsx` | Dono cria o usuário master pelo link |
| `frontend/app/(auth)/aprovar/page.tsx` | Aprovar/recusar pedido pelo link do e-mail |

### Arquivos compartilhados alterados (mudança mínima)

- `frontend/proxy.ts`, `frontend/lib/api.ts`, `frontend/lib/auth.tsx`: `cadastro|primeiro-acesso|aprovar` entram na lista de
  páginas públicas (sem isso o `/auth/me` do AuthProvider recebia 401 e mandava a pessoa para o login).
- `frontend/app/bff/[...path]/route.ts`: `auth/primeiro-acesso` entra em `ROTAS_PUBLICAS` e em `ROTAS_DE_TOKEN`
  (o POST devolve TokenOut e vira cookie, como o login); `ROTAS_DE_TOKEN` só vale para **POST** (o GET da mesma rota é JSON comum).
- Nenhum layout, `globals.css`, `components/ui`, `components/mayacorp` ou `nav.ts` foi alterado. O menu "Admin MayaFit"
  fica a cargo do `components/mayacorp/nav-admin.ts` (agente do visual) com os itens:
  Início `/admin`, Estúdios `/admin/estudios`, Solicitações `/admin/solicitacoes`, Planos `/admin/planos`,
  Contratos `/admin/contratos`, Cobranças `/admin/cobrancas`; e "Meu plano" `/minha-conta/plano` no menu do estúdio.

## Especificação das telas

Padrão de todas as listas: cabeçalho (migalhas "Admin MayaFit › …") → toolbar (busca + filtros + ação principal) →
tabela → vazio ilustrado → paginação (20–25 por página, no cliente) → modal → confirmação → toast. Valores `R$ 1.234,50`
e números/CNPJ/datas em JetBrains Mono (`.num`). Erros da API viram toast (QueryCache global).

### Guarda `/admin/*`
- **Objetivo:** só abrir no estúdio MayaCorp, para administradores.
- **Dados:** `usuario.estudio?.mayacorp` e `usuario.administrador` do `/auth/me`.
- **Estados:** carregando (esqueleto); não-mayacorp → "Área exclusiva do admin MayaFit"; não administrador → "Só administradores do Admin MayaFit".
- **Aceite:** sem `estudio.mayacorp` nenhuma chamada `/admin/*` é feita; com ele, a página abre.

### Início `/admin`
- **Objetivo:** a carteira num relance e o que pede ação hoje.
- **Dados:** resumo (por situação, MRR), resumo de cobranças, lista de estúdios, todas as cobranças, todas as solicitações.
- **Indicadores (clicáveis, levam à lista filtrada):** MRR; Crescimento (estúdios criados no mês x mês anterior);
  Churn acumulado (inativos ÷ total); Em teste (quantos acabam em ≤ 7 dias); Cobranças vencidas (+ estúdios em atraso);
  Em aberto; Recebido no mês; Solicitações novas.
- **Gráficos:** receita por mês (12 meses, faturado pela competência/vencimento x recebido pela data do pagamento,
  canceladas fora); funil do cadastro pelo site (pedidos → aprovados → usando → pagando, com % de conversão);
  estúdios novos por mês (6 meses).
- **Pedem atenção:** testes acabando/acabados, suspensos, sem plano — com ações rápidas (+15 dias, suspender/reativar, copiar endereço).
- **Vazio:** "Tudo em dia". **Aceite:** números batem com as listas de Estúdios e Cobranças; clicar no indicador abre a lista já filtrada.

### Estúdios `/admin/estudios`
- **Objetivo:** achar e abrir um estúdio; criar um novo.
- **Dados:** lista de estúdios (busca e situação vão para a API; plano e paginação no cliente), resumo (contagens nos filtros), planos.
- **Colunas:** estúdio (identificador · CNPJ), plano · ciclo, valor (com desconto por indicação), alunos ativos x limite (barra),
  endereço, situação (+ "até dd/mm" no teste).
- **Ações:** Novo estúdio (modal: ficha, plano/ciclo, **60 dias de teste por padrão**, indicação, extras, e-mail do primeiro acesso,
  identificador, domínio próprio). Ao criar: toast com "Copiar link" do primeiro acesso e vai para a ficha.
- **Filtro inicial** por `?status=` (usado pelos indicadores do Início).
- **Vazio:** com filtro → "Nenhum estúdio encontrado"; sem → "Nenhum estúdio ainda" + Novo estúdio.
- **Aceite:** busca por nome/identificador/CNPJ; filtros combinam; criar estúdio mostra o link e abre a ficha.

### Ficha `/admin/estudios/[id]`
- **Objetivo:** tudo sobre um estúdio e as ações sobre ele.
- **Cabeçalho:** nome, identificador · CNPJ, Editar ficha, Mudar situação (com confirmação explicando o efeito de cada uma).
  Faixa: situação + teste até, plano/valor/desconto, indicado por, extras liberados.
- **Ações de um clique:** +15 / +30 dias de teste (PUT da ficha com `teste_ate`), Suspender (confirmação), Reativar,
  Reenviar primeiro acesso (toast com "Copiar link"), Copiar endereço.
- **Abas:** (`?aba=` abre direto)
  - **Visão geral:** Saúde do cliente (último acesso da equipe, uso de alunos x limite, cobranças vencidas → selo Saudável/Atenção/Em risco),
    uso do mês e dados comerciais, linha do tempo (criação, início do contrato, fim do teste, contratos gerados/enviados,
    cobranças pagas/vencidas/a vencer, últimos acessos).
  - **Uso e dados:** barras de alunos ativos e usuários contra o limite, aulas do mês, valor além do plano, foto do uso (`uso.em`).
  - **Usuários:** cartão do usuário Suporte (`suporte.<slug>`, senha em Planos), tabela (login, perfil, último acesso, ativo),
    Novo usuário (nome, e-mail, login, perfil Full/Secretária/Professor), Zerar senha (confirmação), Reenviar primeiro acesso (enquanto não há master).
  - **Domínios:** adicionar, abrir, remover (confirmação).
  - **Contratos:** gerar de um modelo, revisar texto (rascunho), PDF, enviar/reenviar por e-mail, marcar assinado.
  - **Cobranças:** forma de pagamento (link ou cartão), enviar link do cartão, lista, cobrança avulsa.
- **Erro/vazio:** estúdio inexistente → "Estúdio não encontrado"; cada aba tem vazio próprio.
- **Aceite:** mudar situação reflete na lista; estender teste atualiza "teste até"; zerar senha mostra a mensagem da API.

### Solicitações `/admin/solicitacoes`
- **Objetivo:** aprovar/recusar os pedidos do formulário público.
- **Dados:** solicitações por situação (nova padrão). Busca local por estúdio/responsável/e-mail/CNPJ.
- **Ações:** Aprovar (modal: dias de teste, padrão 60; identificador opcional) → toast com link; Recusar (confirmação);
  Abrir estúdio; Ver formulário; Copiar link do formulário (`<origem>/cadastro`).
- **Vazio:** "Nenhuma solicitação nova" + copiar link. **Aceite:** aprovar some de "Novas" e aparece o botão "Abrir estúdio".

### Planos e indicação `/admin/planos`
- **Objetivo:** catálogo de planos, desconto por indicação e senha do Suporte.
- **Planos:** tabela (mensal, anual, alunos ativos, usuários, preço por aluno acima do limite e por usuário adicional, recursos).
  Modal com ordem, preços, limites (vazio = ilimitado), recursos (rótulos de `GET /admin/recursos`), ativo. **Nenhum preço fixo no código.**
- **Indicação:** % por indicação e máximo (teto vem da API), com exemplo calculado.
- **Usuário Suporte** (`#suporte`): senha somente escrita (selo "senha definida"), confirmação e medidor de força.
- **Aceite:** plano novo aparece no cadastro público e no Meu plano; salvar a senha não a mostra de volta.

### Contratos `/admin/contratos`
- **Abas:** Contratos dos estúdios (busca, filtro por situação com contagens, paginação; clique abre a ficha na aba Contratos)
  e Modelos (lista, aviso de variável desconhecida). Modal do modelo com variáveis clicáveis (`GET /admin/contratos/variaveis`) e ativo.
- **Vazio:** sem modelos → Novo modelo; sem contratos → "Ver modelos".

### Cobranças `/admin/cobrancas`
- **Objetivo:** receber dos estúdios.
- **Faixa:** aviso para conectar o Mercado Pago, ou selo "conectado · conta" + dia de vencimento, régua e geração automática.
- **Indicadores:** recebido no mês, em aberto, vencido, estúdios em atraso.
- **Lista:** busca, situação (`?status=`), tipo; colunas estúdio, cobrança (tipo, competência, itens), valor, vencimento,
  situação (+ pago em/forma, lembretes enviados), ações (copiar link, enviar, dar baixa com forma, cancelar). Total do filtro no rodapé.
- **Mercado Pago (modal):** Access Token e assinatura secreta **somente escrita** (selo configurado / não configurado; vazio mantém),
  endereço das notificações para copiar, dia do vencimento (1–28), régua (dias, mostrada em palavras), gerar sozinho, **Testar conexão**.
- **Gerar mensalidades:** mês + enviar por e-mail; toast com criadas/erros. **Avulsa:** estúdio, descrição, valor, vencimento, enviar.
- **Aceite:** baixa e cancelamento atualizam indicadores; sem Mercado Pago os botões de gerar/avulsa ficam desabilitados.

### Meu plano `/minha-conta/plano` (no estúdio)
- Plano atual (teste grátis com dias restantes), valor, forma de pagamento; "Pagar no cartão todo mês" (abre o Mercado Pago);
  uso de alunos ativos e usuários x limites e valor além do plano; cobranças em aberto com **Pagar** (link novo do MP);
  cartões dos planos com upgrade/mudança (só administrador; confirmação); pagamentos feitos; aviso quando suspenso.
- **Erro:** 404 → "Plano não disponível aqui" (instalação sem modo multi ou admin); outro erro → mensagem + Tentar de novo.

### Quero o MayaFit `/cadastro` (público)
- Selo **"2 meses grátis, sem cartão"**, planos vindos de `/public/planos` (mensal/anual), dados do estúdio, nº de alunos ativos,
  como prefere pagar, indicação, mensagem, autorização LGPD, isca para robôs (`site`). `?plano=<nome>`, `?ciclo=anual`, `?embed=1`.
  Ao enviar: tela de confirmação e `postMessage({mayafit: "cadastro-enviado"})` para o site.

### Primeiro acesso `/primeiro-acesso?token=` (público)
- Lê o estúdio pelo token; o dono informa nome, e-mail (contato), **login curto** (sugerido pelo nome, validado `^[a-z0-9._-]{3,60}$`)
  e senha com confirmação; ao criar, o BFF grava os cookies e a página recarrega em `/`.
- **Erro:** link sem token, expirado ou master já criado → mensagem da API + "Ir para o login".

### Aprovar `/aprovar?token=` (público, link do e-mail para os administradores)
- Mostra o pedido, dias de teste (60), Aprovar e criar estúdio / Recusar; depois, "Copiar o link" do primeiro acesso.

## Chamadas de API (via `/bff`, o backend recebe em `/api/...`)

| Tela | Método | Caminho | Envia | Espera na resposta |
|---|---|---|---|---|
| Guarda | GET | `/auth/me` | — | `administrador`, **`estudio: {slug, nome, mayacorp}`** |
| Início, Estúdios | GET | `/admin/resumo` | — | `{clientes, por_status: {teste, ativo, suspenso, inativo}, mrr}` |
| Início, Estúdios, diálogos | GET | `/admin/clientes` | `?q=&status=` | `Estudio[]` (ver "Estudio" abaixo) |
| Início, Cobranças | GET | `/admin/cobrancas/resumo` | — | `{em_aberto, vencido, recebido_mes, inadimplentes}` |
| Início, Cobranças, ficha | GET | `/admin/cobrancas` | `?status=pendente\|vencida\|paga\|cancelada&cliente_id=` | `Cobranca[]` |
| Início, Solicitações | GET | `/admin/solicitacoes` | `?status=nova\|aprovada\|recusada` | `Solicitacao[]` |
| Novo estúdio | POST | `/admin/clientes` | ficha + `slug, admin_nome, admin_email, dias_teste, dominios[]` | `Estudio` + `convite` (link do 1º acesso) |
| Ficha | GET | `/admin/clientes/{id}` | — | `Estudio` |
| Editar ficha, +15/+30 dias | PUT | `/admin/clientes/{id}` | ficha: `nome, documento, responsavel, email_financeiro, telefone, plano_id, ciclo, inicio_contrato, teste_ate, observacao, indicado_por_id, extras[]` | `Estudio` |
| Situação, suspender, reativar | POST | `/admin/clientes/{id}/status` | `{status}` | `Estudio` |
| Reenviar 1º acesso | POST | `/admin/clientes/{id}/boas-vindas` | — | `{link, enviado_para}` |
| Uso | GET | `/admin/clientes/{id}/uso` | — | `{mes, alunos_ativos, limite_alunos, usuarios, limite_usuarios, aulas_mes?, alunos_excedentes, usuarios_excedentes, valor_excedente}` |
| Usuários | GET | `/admin/clientes/{id}/usuarios` | — | `[{id, nome, email, login, ativo, convite_pendente, perfil, ultimo_acesso, equipe_mayacorp}]` |
| Novo usuário | POST | `/admin/clientes/{id}/usuarios` | `{nome, email, login\|null, perfil: "Full"\|"Secretária"\|"Professor"}` | usuário + `convite?` |
| Zerar senha | POST | `/admin/clientes/{id}/usuarios/{uid}/zerar-senha` | — | `{mensagem, link?}` |
| Ativar/desativar | POST | `/admin/clientes/{id}/usuarios/{uid}/ativo` | `{ativo}` | usuário |
| Domínios | POST | `/admin/clientes/{id}/dominios` | `{host}` | `Estudio` |
| Domínios | DELETE | `/admin/clientes/{id}/dominios/{did}` | — | `Estudio` |
| Contratos (ficha) | GET | `/admin/clientes/{id}/contratos` | — | `ContratoEstudio[]` |
| Contratos (ficha) | POST | `/admin/clientes/{id}/contratos` | `{modelo_id}` | contrato + `variaveis_vazias[]` |
| Contratos | PUT | `/admin/contratos/{kid}` | `{titulo, corpo}` | contrato |
| Contratos | GET | `/admin/contratos/{kid}/pdf` | — | PDF |
| Contratos | POST | `/admin/contratos/{kid}/enviar` | `{para[], mensagem\|null}` | contrato |
| Contratos | POST | `/admin/contratos/{kid}/status` | `{status: "assinado"\|"cancelado"}` | contrato |
| Contratos | GET | `/admin/contratos` | — | `ContratoEstudio[]` com `cliente_nome` |
| Modelos | GET/POST | `/admin/modelos-contrato` | `{nome, corpo, ativo}` | `ModeloContrato` (`variaveis_desconhecidas[]`) |
| Modelos | PUT | `/admin/modelos-contrato/{mid}` | `{nome, corpo, ativo}` | `ModeloContrato` |
| Modelos | GET | `/admin/contratos/variaveis` | — | `[{chave, rotulo}]` |
| Pagamento (ficha) | GET/PUT | `/admin/clientes/{id}/pagamento` | PUT `{forma_pagamento: "link"\|"cartao"}` | `{forma_pagamento, assinatura_id, assinatura_status}` |
| Pagamento (ficha) | POST | `/admin/clientes/{id}/assinatura` | — | idem + `link` |
| Avulsa | POST | `/admin/cobrancas/avulsa` | `{cliente_id, descricao, valor: "123.45", vencimento, enviar}` | `Cobranca` |
| Gerar | POST | `/admin/cobrancas/gerar` | `{competencia: "AAAA-MM", enviar}` | `{criadas[], erros[]}` |
| Enviar | POST | `/admin/cobrancas/{kid}/enviar` | — | `Cobranca` + `enviado_para[]` |
| Baixa | POST | `/admin/cobrancas/{kid}/baixa` | `{forma: "pix"\|"transferência"\|"boleto"\|"dinheiro"\|"cartão"\|"outra"}` | `Cobranca` |
| Cancelar | POST | `/admin/cobrancas/{kid}/cancelar` | — | `Cobranca` |
| Mercado Pago | GET/PUT | `/admin/cobranca/config` | PUT `{token\|null, segredo\|null, dia_vencimento, gerar_automatico, regua[]}` (null = mantém) | `{conectado, segredo_definido, conta, dia_vencimento, gerar_automatico, regua[], url_notificacao}` |
| Mercado Pago | POST | `/admin/cobranca/config/testar` | — | `{ok, conta, id}` |
| Solicitações | POST | `/admin/solicitacoes/{sid}/aprovar` | `{dias_teste\|null, slug\|null}` | `Estudio` + `convite` |
| Solicitações | POST | `/admin/solicitacoes/{sid}/recusar` | — | solicitação |
| Planos | GET/POST | `/admin/planos` | `PlanoIn` | `PlanoOut` |
| Planos | PUT | `/admin/planos/{pid}` | `PlanoIn` | `PlanoOut` |
| Planos | GET | `/admin/recursos` | — | `[{chave, rotulo}]` (gestao, site, crm, app_aluno, whatsapp, checkin, integracoes, ia, nfse, catraca) |
| Ficha, novo estúdio | GET | `/admin/extras` | — | `[{chave, rotulo}]` (receita_saude, etl) |
| Indicação | GET/PUT | `/admin/politica-indicacao` | PUT `{desconto_por_indicacao, desconto_maximo}` | `{desconto_por_indicacao, desconto_maximo, teto}` |
| Suporte | GET/PUT | `/admin/suporte` | PUT `{senha}` | `{senha_definida}` |
| Meu plano | GET/PUT | `/meu-plano` | PUT `{plano_id, ciclo}` | `MeuPlano` |
| Meu plano | POST | `/meu-plano/cartao` | — | `{link}` |
| Meu plano | POST | `/meu-plano/cobrancas/{kid}/link` | — | `{link}` |
| Cadastro | GET | `/public/planos` | — | `PlanoOut[]` (ativos); opcional `recursos_rotulos: [{chave, rotulo}]` |
| Cadastro | POST | `/public/cadastro` | `{nome, documento\|null, responsavel, email, telefone, plano_id, ciclo, alunos\|null, indicacao\|null, mensagem\|null, aceite, site}` | `{ok}` |
| 1º acesso | GET | `/auth/primeiro-acesso` | `?token=` | `{estudio, email}` (aceita `escritorio` como no MayaJus) |
| 1º acesso | POST | `/auth/primeiro-acesso` | `{token, nome, email, login, senha}` | **TokenOut** `{access_token, refresh_token, usuario}` (o BFF vira cookie) |
| Aprovar | GET | `/public/solicitacao` | `?token=` | `Solicitacao` |
| Aprovar | POST | `/public/solicitacao/aprovar` · `/recusar` | `{token, dias_teste}` | aprovar: `Estudio` + `convite` |

**Estudio** (saída de `/admin/clientes*`): `id, slug, nome, status, status_rotulo, teste_ate, criado_em, documento, responsavel,
email_financeiro, telefone, plano (PlanoOut), plano_id, ciclo, valor, valor_com_desconto, desconto_percentual, indicacoes_ativas,
indicado_por {id, nome}, indicado_por_id, inicio_contrato, observacao, banco_principal, dominios [{id, host}], extras [],`
**`uso {alunos_ativos, usuarios, aulas_mes, em}`** (a foto do worker; usada na coluna de alunos da lista e na saúde).

**PlanoOut:** `id, nome, preco_mensal, preco_anual, usuarios, alunos_ativos, preco_aluno_excedente, preco_usuario_adicional, recursos[], ativo, ordem`.

**Solicitacao:** como no MayaJus, com `alunos` no lugar de `usuarios`.

## Suposições sobre o backend (conferir)

1. `/auth/me` traz `estudio: {slug, nome, mayacorp}` (a guarda depende disso).
2. `GET /admin/clientes` inclui `uso` (foto do worker) e `extras`; sem `uso`, a coluna de alunos mostra "—".
3. `GET /admin/clientes/{id}/uso` usa os nomes `alunos_ativos`, `limite_alunos`, `alunos_excedentes` (+ `aulas_mes` opcional).
4. A rota de extras é `GET /admin/extras` (no MayaJus era `/admin/robos`).
5. `GET /admin/clientes/{id}/usuarios` devolve `equipe_mayacorp` para identificar o Suporte; criar usuário aceita `login` e os perfis Full/Secretária/Professor.
6. `POST /auth/primeiro-acesso` devolve TokenOut e o GET devolve `estudio` (aceito `escritorio`). Login é obrigatório no MayaFit.
7. Variáveis do contrato do MayaFit: o modelo de exemplo usa `alunos_ativos` e `aluno_excedente` (no MayaJus `notas_mes` e `nota_excedente`); se tiverem outro nome, o próprio editor avisa "variável desconhecida".
8. `/public/planos` pode mandar `recursos_rotulos`; sem isso o cadastro usa rótulos de reserva para as 10 chaves conhecidas.
9. Churn e crescimento são calculados no navegador (inativos ÷ total; estúdios por `criado_em`). Um churn mensal de verdade
   precisa que o controle guarde quando o estúdio ficou inativo (sugestão: `Cliente.status_em` ou eventos) e que `/admin/resumo` devolva `novos_mes`/`churn_mes`.
10. A linha do tempo é montada com o que já existe (ficha, contratos, cobranças, acessos). Um histórico completo (mudanças de situação, plano)
    pediria `GET /admin/clientes/{id}/eventos` lendo a auditoria — fica como melhoria.

## Pronto

- `npm run lint` e `npm run build` sem erro (ver relatório do agente).
