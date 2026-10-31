# Controle de acesso: check-in facial + catraca (`feat/acesso`)

## 1. Especificação do módulo

### Objetivo
Fazer o aluno entrar no estúdio **sem fila e sem papel**: ele olha para o tablet da recepção (ou digita CPF/código + PIN,
ou mostra o QR do app), o sistema confere se ele **pode entrar agora** (cadastro, mensalidade, aula marcada ou plano livre),
cumprimenta pelo nome, **marca a presença na aula** e **libera a catraca**. A equipe vê em tempo real quem está no
estúdio, o histórico e os relatórios. Tudo respeitando a LGPD (biometria é dado sensível).

### Personas
| Persona | O que faz |
|---|---|
| **Aluno** | Faz check-in no totem (rosto, CPF/código + PIN ou QR do app); pode cadastrar o próprio rosto no totem com um código da recepção. |
| **Recepção / Secretária** | Vê o painel "quem está aqui", libera manualmente com motivo, cadastra rosto/PIN, gera código para o totem. |
| **Gestor (Full)** | Configura regras, catracas e totens; consulta histórico e relatórios; apaga biometria a pedido. |
| **Técnico de instalação** | Cadastra a catraca, testa a conexão, pareia o tablet, instala o agente local se preciso. |

### Fluxos passo a passo
1. **Check-in facial (totem)**: tela ociosa (nome do estúdio, relógio, oval da câmera) → rosto centralizado por 3
   quadros → animação de leitura → "pisque devagar" (prova de vida) → o navegador gera o **descritor** (1024 números)
   e envia só ele → servidor compara com os descritores cifrados → aplica a regra → registra a tentativa → marca
   presença na aula → devolve o resultado e o plano da catraca → totem aciona a catraca na rede local, toca o som,
   mostra "Olá, Ana! Boa aula." com a aula/professor (aniversário: confete + música; mensalidade vencida dentro da
   tolerância: aviso gentil) → volta à tela ociosa; a mesma pessoa só dispara de novo depois de sair do enquadramento.
2. **CPF/código + PIN**: botão "Usar CPF ou código" → teclado numérico grande → PIN → mesma regra.
3. **QR do app**: o app do aluno mostra um QR assinado (vale 90 s, uso único) → o totem lê pela câmera → mesma regra.
4. **Cadastro do rosto pela recepção**: Biometria e PIN → aluno → ler o termo e marcar "o aluno concorda" →
   "Registrar consentimento" → "Cadastrar rosto" (câmera do computador, piscar) → 3 descritores salvos cifrados.
5. **Cadastro do rosto no totem**: recepção gera um **código de 6 dígitos** (15 min, uso único) na ficha do aluno →
   no totem, "Cadastrar meu rosto" → CPF/código + código → termo LGPD (rolar até o fim) → "Li e concordo" → captura →
   pronto. O consentimento registra o canal "totem" e quem gerou o código.
6. **Liberação manual**: "Liberar agora" (painel ou cartão da catraca) → catraca, sentido, aluno opcional, motivo
   obrigatório → registra, audita e aciona.
7. **Pareamento do totem**: Catracas e totens → Novo dispositivo → aparece um **QR Code** com o link de pareamento →
   no tablet, abrir `/totem/parear` e apontar a câmera (ou abrir o link) → o token vai para cookie httpOnly do totem.
8. **Testar conexão**: modo servidor testa do servidor; modo totem devolve o plano e **o navegador de quem clicou**
   testa na rede local; modo agente enfileira um comando de status.
9. **Apagar biometria**: ficha → "Apagar biometria" → motivo → descritores apagados na hora, consentimento revogado.

### Regras de negócio (numeradas)
- **R1** Cadastro INATIVO nunca entra ("Cadastro inativo. Procure a recepção.").
- **R2** Parcela ABERTA vencida há **mais** de `tolerancia_atraso_dias` (padrão 5) bloqueia: "Mensalidade em atraso desde 05/10. Procure a recepção." Vencer hoje não é atraso. Dentro da tolerância entra com aviso gentil.
- **R3** Aula marcada hoje (reserva RESERVADA/PENDENTE/CONCLUIDA) dentro da janela `[início − janela_antes_min, início + janela_depois_min]` (padrão 30/15) libera. Com duas aulas, vale a mais próxima do início.
- **R4** Reserva de contrato exige o contrato vigente; reserva sem contrato (avulsa, experimental, TotalPass/Wellhub) vale por si.
- **R5** Plano marcado como **acesso livre** + contrato vigente: entra a qualquer hora dentro do horário de funcionamento da unidade (Cadastros › Horários); fora dele: "Fora do horário de funcionamento. Abrimos às 14:00."
- **R6** Ao negar, o motivo mais útil: antes da janela ("Sua aula de Pilates é às 09:00. A entrada libera a partir das 08:30."), depois da janela, contrato encerrado (com a data), sem contrato, "Sem aula marcada agora."
- **R7** Check-in permitido marca "chegou" na reserva **pela função da agenda** (`agenda.servico.aplicar_acao_presenca`). Falha de lotação não impede a entrada (avisa).
- **R8** Reconhecimento: similaridade de cosseno ≥ `limiar_similaridade` (padrão 0,60) **e** pelo menos `margem_ambiguidade` (0,03) acima do melhor de outro aluno; senão nega ("Não consegui ter certeza…").
- **R9** Prova de vida exigida (configurável): piscou **ou** antispoof ≥ 0,5 e liveness ≥ 0,5.
- **R10** PIN de 4 a 6 dígitos, sem sequência nem repetição; 5 erros bloqueiam por 15 min. CPF/código sem PIN não entra quando `exigir_pin`.
- **R11** QR do app: HMAC, 90 s, uso único (o nonce fica no registro).
- **R12** Até 5 descritores por aluno (os mais antigos saem). Descritor só com consentimento ativo. Trocar o termo pede novo aceite (o novo substitui o antigo).
- **R13** Catraca só é acionada quando o acesso é permitido. Comando ao agente expira em 30 s (giro atrasado é pior que nenhum).
- **R14** "Quem está no estúdio": última entrada permitida de hoje, sem saída depois, até o fim da aula + 15 min (ou a permanência estimada no acesso livre).
- **R15** Aluno INATIVO tem a biometria apagada pela rotina do worker (a cada 6 h) e não é reconhecido nem antes disso.

### Telas
| Tela | Detalhe "uau" |
|---|---|
| `/acesso` Quem está aqui | Painel **ao vivo** (5 s, ponto pulsando), cartões animados de chegada/saída com barra até a saída prevista, selo "chegou agora", bolo para aniversariante, progresso "x/y chegaram" das próximas aulas, feed com flash nos novos. |
| `/acesso/historico` | **Mapa de calor dos horários** (pico da recepção), barras por dia, "por que negamos", ranking dos mais frequentes, CSV. |
| `/acesso/biometria` | Cartão **"Se chegasse agora no totem"** (simula a regra em tempo real), código do totem em destaque, histórico de consentimentos. |
| `/acesso/equipamentos` | **Pareamento por QR Code**, teste de conexão executado do próprio navegador na rede local, status online dos totens. |
| `/acesso/configuracoes` | **Linha do tempo ao vivo** da janela de entrada que muda enquanto você digita. |
| `/totem` (+ `/parear`, `/cadastro`) | Oval com varredura, pedido de piscada, sons WebAudio, confete de aniversário, cartão de resultado com contagem, modo retrato, tela cheia e tela sempre acesa. |

### Estados vazios e de erro
Vazios ilustrados ("Ninguém no estúdio agora", "Nenhum acesso no período", "Nenhuma catraca cadastrada" com atalho para a
simulada, "Nenhum totem pareado"). Erros: câmera bloqueada/ausente/ocupada (mensagens específicas), modelos faciais não
carregaram (o totem oferece CPF/QR), sem internet (faixa offline), totem revogado (volta ao pareamento), catraca fora do ar
ou bloqueada por HTTPS/CORS (mensagem e registro "Catraca falhou"), PIN bloqueado, QR vencido/usado, código do totem vencido.

### Permissões (`acesso.*`)
| Ação | Permissão |
|---|---|
| Ver painel, histórico, relatório, ficha, regras | `acesso.ver` |
| Liberar manualmente, marcar saída, informar resultado da catraca | `acesso.liberar_manual` |
| Regras, catracas, totens, consentimento, rosto, PIN, código do totem, CSV | `acesso.configurar` (CSV: `acesso.ver`) |
Perfil Full tem tudo. Secretária e Professor não recebem nada por padrão (o coordenador decide; sugestão: Secretária com `ver` + `liberar_manual`).

### LGPD
Base legal: consentimento específico e destacado (art. 11, I). Registro de **quem coletou, quando, canal, IP e hash do texto
do termo**. O servidor **nunca recebe foto**: só o descritor; o descritor do check-in é comparado e descartado. Descritores
gravados **cifrados** (Fernet/MASTER_KEY), apagáveis a qualquer momento (botão + motivo, auditado), apagados automaticamente
para inativos. Alternativa sem biometria sempre disponível (CPF/código + PIN, QR). Nenhum dado biométrico na demonstração.

### Critérios de aceite (todos atendidos e cobertos por teste, salvo indicação)
- [x] Regra de acesso pura com motivos claros (`tests/acesso/test_regra_dominio.py`, 30 casos).
- [x] Check-in facial/CPF+PIN/QR registra tentativa, presença e aciona a catraca (`test_totem_checkin.py`).
- [x] Biometria cifrada, só com consentimento, apagável; rotina para inativos.
- [x] Token do dispositivo só como hash, revogável, token da equipe não abre o totem.
- [x] Drivers Control iD (HTTP falso nos testes), Henry esqueleto, simulado; modos totem/agente/servidor (`test_catracas.py`).
- [x] Liberação manual com motivo, permissão e auditoria.
- [x] Painel ao vivo, histórico com filtros, CSV, relatório (`test_painel_relatorio.py`).
- [x] `popular_demo(db)` idempotente.
- [ ] Validar reconhecimento e catraca com hardware real (seção 4).

## 2. O que foi feito
- **Backend** `app/modules/acesso/`: `models.py`, `schemas.py`, `servico.py` (contrato estável no docstring), `routes.py`
  (equipe), `rotas_totem.py` (totem, agente, QR do app), `drivers/` (base, controlid, henry, simulado), `tarefas.py`,
  `demo.py`. Regra pura em `app/domain/acesso.py`. Migração `0130_acesso` (down `0001_pilates_inicial`), testada up/down no SQLite.
- **Frontend**: `app/(app)/acesso/{page,historico,biometria,equipamentos,configuracoes}`, `app/(totem)/` (layout, `/totem`,
  `/totem/parear`, `/totem/cadastro`, BFF `/totem/api/[...path]` com cookie httpOnly `mf_totem` path `/totem` e lista fechada),
  `components/acesso/**` (motor facial, executor da catraca local, telas; `totem/` com o quiosque), `lib/tipos-acesso.ts`.
- **Agente local** `deploy/agente-catraca/agente.py` (só biblioteca padrão; polling HTTPS; Control iD e simulado; Henry esqueleto).
- Testes: `uv run python -m pytest -q -p no:cacheprovider tests/acesso tests/test_cobertura_rotas.py` → 80 passaram.
  Smoke ponta a ponta (uvicorn + `next start`): pareamento pelo BFF do totem, check-in por documento, painel e relatório pelo BFF.

### Rotas
Equipe (`/api/acesso`): `GET/PUT config`, `GET opcoes`, `GET painel`, `POST presentes/{id}/saida`, `GET registros`,
`GET registros.csv`, `GET relatorio`, `GET alunos`, `GET alunos/{id}`, `GET alunos/{id}/decisao`, `POST alunos/{id}/consentimento`,
`POST alunos/{id}/descritores`, `DELETE alunos/{id}/descritores/{d}`, `POST alunos/{id}/biometria/apagar`, `PUT/DELETE alunos/{id}/pin`,
`POST alunos/{id}/codigo-totem`, `POST liberar`, `POST registros/{id}/catraca`, `GET/POST catracas`, `PUT/DELETE catracas/{id}`,
`POST catracas/{id}/testar|liberar|teste-navegador`, `GET/POST dispositivos`, `PATCH/DELETE dispositivos/{id}`, `POST dispositivos/{id}/regenerar|revogar`.
Autenticação própria: `/api/totem/{me, identificar/facial|documento|qr, registros/{id}/catraca, cadastro/iniciar|concluir}`
(X-Dispositivo-Token), `/api/catraca-agente/{comandos, comandos/{id}/resultado}`, `/api/aluno-app/acesso/qr` (sessão do aluno).

### Bibliotecas adicionadas (npm)
- `@vladmandic/human@3.3.6` (MIT): detecção, malha, íris (piscada), descritor `faceres`, antispoof e liveness, tudo no navegador
  (WebGL). Os modelos usados (≈13 MB) e `human.esm.js` foram **copiados para `public/totem/`** e são carregados sob demanda
  (import nativo, fora do bundle; nenhuma CDN). Ao atualizar a lib, copie de novo `models/{blazeface,facemesh,faceres,iris,antispoof,liveness}.*` e `dist/human.esm.js` (o arquivo tem `/* eslint-disable */` no topo).
- `jsqr@1.4.0`: leitura de QR quando o navegador não tem `BarcodeDetector`.
- `qrcode@1.5.4` (+ `@types/qrcode`): QR de pareamento do totem.
Nenhuma dependência Python nova (httpx já existia).

### Linhas em arquivos compartilhados
- `backend/app/core/permissoes.py`: grupo "Controle de acesso" no fim do `CATALOGO`; `r"/api/totem/"` e `r"/api/catraca-agente/"` em `PUBLICAS_AUTENTICACAO_PROPRIA`. As regras de rota são registradas pelo módulo (`adicionar_regras`).
- `frontend/components/mayacorp/nav.ts`: grupo "Controle de acesso" (5 itens) + 4 ícones importados.
- `frontend/proxy.ts`: `totem` na lista pública e cabeçalho `Permissions-Policy: camera=(self)` só em `/totem` e `/acesso` (o `next.config.ts` bloqueia a câmera no sistema todo; conferido com `next start` que o cabeçalho do proxy prevalece).
- `frontend/package.json`/`package-lock.json`: dependências acima.

## 3. Pedidos ao coordenador
1. **IMPORTANTE**: acrescentar `acesso` em `registrar_modelos()` (`backend/app/modules/__init__.py`). Sem isso o `alembic revision --autogenerate` de outro módulo vai propor DROP das tabelas `acesso_*` (o app e os testes funcionam porque o `routes.py` importa os modelos).
2. `ROTULO_ACAO` em `core/permissoes.py`: acrescentar `"liberar_manual": "Liberar manualmente"` (a matriz mostra a chave crua).
3. Decidir permissões padrão da Secretária (sugestão: `acesso.ver` + `acesso.liberar_manual`; cadastro de rosto/PIN hoje exige `acesso.configurar` — se quiser separar, criar a ação `acesso.biometria`).
4. **App do aluno** (outro módulo): a rota `GET /api/aluno-app/acesso/qr` já existe; falta o BFF do app liberar `acesso/qr` na lista `PERMITIDAS` e uma tela "Meu QR de entrada" que renove a cada 60 s (usar `qrcode`, já instalado).
5. **Ficha do aluno** (módulo alunos): botão "Acesso e biometria" com link para `/acesso/biometria?aluno=<id>` (abre a ficha de acesso direto).
6. Worker multi-tenant: a tarefa `acesso-apagar-biometria-inativos` usa `SessionLocal()` como as demais; percorrer os estúdios é do worker.
7. `popular_demo(db)` em `app/modules/acesso/demo.py` (catraca simulada, totem sem token, histórico de 14 dias e 3 pessoas "no estúdio agora").

## 4. O que precisa ser validado com hardware real
- **Reconhecimento**: calibrar `limiar_similaridade` (0,60 é ponto de partida para cosseno do `faceres`) com ~20 alunos reais, luz da recepção e o tablet escolhido; medir falsos positivos (gêmeos/parentes → `margem_ambiguidade`). Desempenho do WebGL no tablet (recomendado Android 10+ com Chrome, ou notebook). Testar óculos, máscara, boné.
- **Prova de vida**: a piscada depende do modelo de íris; conferir taxa de detecção. É feita no cliente (totem autenticado): barra foto/tela comum, não substitui câmera 3D.
- **Control iD** (pela documentação pública da Access API): conferir no firmware do cliente `login.fcgi` → `session`, `execute_actions.fcgi` com `{"action":"catra","parameters":"allow=clockwise|anticlockwise|both"}` (iDBlock) e `{"action":"door","parameters":"door=N"}` (iDAccess/iDFlex/iDFace), `system_information.fcgi`, `logout.fcgi`; o sentido físico de ENTRADA; se a sessão precisa ser renovada; tempo de resposta.
- **Caminho pelo totem (navegador → catraca)**: a página é HTTPS, então o navegador **bloqueia http://IP** (mixed content) e exige **CORS** do equipamento (e, no Chrome, Private Network Access). Validar: ligar HTTPS na catraca e aceitar o certificado no tablet; verificar se o firmware responde `Access-Control-Allow-Origin`/preflight. Se não der, usar o **agente local** (sem essas restrições) — ou o modo "Push/online" da Control iD (o equipamento consulta o servidor), a avaliar.
- **Agente local**: rodar `deploy/agente-catraca/agente.py` como serviço no Windows (NSSM), conferir reconexão e latência do polling (1 s).
- **Henry/Topdata**: só esqueleto; precisa do manual do protocolo do modelo (TCP porta 3000/3570 ou SDK EasyInner) e implementar no agente.
- **Leitura de QR** pela câmera frontal do tablet (foco/distância) e `BarcodeDetector` no Chrome Android.

## 5. Decisões e observações
- Comparação no servidor por cosseno sobre vetores normalizados, em Python puro (sem numpy): ~1.500 descritores × 1024 ≈ dezenas de ms.
- O descritor do check-in não é guardado; o registro guarda só a similaridade (auditoria de qualidade).
- O totem trata "pendente" sem plano (modo agente) como acionado de forma otimista; o resultado real chega ao histórico quando o agente responde.
- Bloqueio por plano do MayaCorp não foi implementado (é do coordenador).
- Não foi possível testar câmera e WebGL num navegador real nesta máquina: build, lint, tipos e smoke HTTP passaram.
