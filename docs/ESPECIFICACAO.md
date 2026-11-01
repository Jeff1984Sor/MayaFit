# MayaFit — Especificação do produto

> Versão 1.0 · 31/10/2026 · MayaCorp
> Documento-mãe do produto. Cada módulo detalha a sua parte no topo do seu `docs/progresso-<módulo>.md`.
> Arquitetura e convenções de código: [`CLAUDE.md`](../CLAUDE.md).

---

## 1. Visão

**MayaFit é o sistema completo para estúdios de Pilates, funcional, fisioterapia e academias de bairro**, vendido como
assinatura (SaaS), com o preço dos sistemas mais simples e os recursos dos mais caros.

Promessa em uma frase: *"Do primeiro contato no Instagram até a nota fiscal do aluno, tudo num lugar só, por menos que um
aluno paga por mês."*

### 1.1 Para quem

| Persona | Quem é | O que quer do sistema |
|---|---|---|
| **Dona do estúdio** | Fisioterapeuta ou educadora física, 1 a 3 unidades, 40 a 400 alunos | Agenda cheia, inadimplência baixa, saber quanto lucra, menos WhatsApp manual |
| **Secretária / recepção** | Atende telefone, WhatsApp e balcão | Marcar, remarcar, cobrar e matricular rápido, sem planilha |
| **Professor(a)** | Dá as aulas, registra evolução | Ver só as próprias aulas e alunos, fazer chamada e evolução pelo celular |
| **Aluno** | Faz 1 a 3 aulas por semana | Ver horários, pedir reposição, pagar, receber lembrete |
| **Lead** | Pessoa interessada que viu o estúdio no Instagram/Google | Ver horários e preços e agendar aula experimental sem atrito |
| **Admin MayaFit** | Jefferson e equipe | Vender, ativar, cobrar e dar suporte a centenas de estúdios sem esforço manual |

### 1.2 Diferenciais frente aos concorrentes

| | MayaFit | seuFisio | Pilates Tool | Next Fit / Tecnofit |
|---|---|---|---|---|
| Preço de entrada | **R$ 49,90** | R$ 154 (1 profissional) | R$ 49 | sob consulta (Tecnofit: a partir de R$ 139) |
| Teste grátis | **60 dias, sem cartão** | 7 dias | — | demonstração |
| Site do estúdio | ✅ grátis, ligado ao CRM | só no plano mais caro | ❌ | ❌ |
| CRM com funil e aula experimental | ✅ desde o Essencial | ✅ | ❌ | parcial |
| App do aluno com reposição | ✅ | check-in | ❌ | ✅ |
| Check-in facial + catraca | ✅ | ✅ (planos maiores) | ❌ | ✅ |
| TotalPass **e** Wellhub | ✅ | ✅ | ❌ | ✅ |
| NFS-e (Nacional + SP) | ✅ | só no Full | ❌ | ✅ |
| Contrato com assinatura eletrônica | ✅ | emissão | ❌ | ✅ |
| IA (evolução clínica, cadastro, textos) | ✅ | ❌ | ❌ | ❌ |
| Recibo Receita Saúde | ✅ (extra) | ❌ | ❌ | ❌ |

---

## 2. Planos e cobrança

| Plano | Mensal | Anual | Usuários | Alunos ativos | Recursos |
|---|---|---|---|---|---|
| **Essencial** | R$ 49,90 | R$ 499 | 2 | 60 | Gestão + Site + CRM |
| **Estúdio** | R$ 89,90 | R$ 899 | 5 | 150 | + App do aluno, WhatsApp, Check-in facial, Integrações (TotalPass, Wellhub, API) |
| **Pro** | R$ 149,90 | R$ 1.499 | 10 | 350 | + IA, NFS-e |
| **Rede** | R$ 289,90 | R$ 2.899 | 25 | ilimitado | tudo, inclusive catraca |

Regras (numeradas para referência nos testes):

- **P1.** Teste grátis de **60 dias**, sem cartão, com todos os recursos do plano escolhido. A 1ª mensalidade só é gerada quando o teste acaba.
- **P2.** Aluno ativo = aluno com contrato vigente no mês. Acima do limite: **R$ 0,50 por aluno**. Usuário com login acima do limite: **R$ 14,90**. O usuário Suporte da MayaCorp não conta.
- **P3.** Anual = 10 mensalidades (2 meses grátis).
- **P4.** Indicação: 5% de desconto por estúdio indicado ativo, teto de 10% (editável no admin).
- **P5.** Extras liberados cliente a cliente: Receita Saúde, migração de dados (ETL) e catraca avulsa para o Pro.
- **P6.** Cobrança pelo Mercado Pago: link mensal por e-mail (Pix, cartão, boleto) ou assinatura no cartão. Régua de avisos: 3 dias antes, no dia, 3 e 10 dias depois.
- **P7.** Inadimplência: **30 dias** após o vencimento o estúdio fica **suspenso** automaticamente (continua entrando, com faixa de aviso e link de pagamento); pagou, volta a ativo sozinho. **Inativo** (não entra) só por ação manual do Admin MayaFit. Os dados nunca são apagados. *(decisão do Jefferson, 31/10/2026)*
- **P8.** Recurso fora do plano aparece no menu com cadeado e a mensagem "Disponível no plano X", com botão para falar com o MayaFit. Nunca some sem explicação.

---

## 3. Arquitetura (resumo)

- **Um banco por estúdio** (`mayafit_<slug>`) e o banco de controle `mayafit_controle`. Isolamento físico: um estúdio nunca enxerga dado de outro, nem por erro de consulta.
- Cada estúdio tem o endereço `<slug>.<domínio base>` e pode ter domínio próprio. Por esse endereço entram o sistema, o app do aluno, o site e os links de assinatura.
- Admin MayaFit num domínio próprio, com banco próprio.
- Stack: FastAPI + SQLAlchemy + Alembic (Python 3.12), Next.js + Tailwind + shadcn/ui, PostgreSQL 16, worker próprio, nginx + systemd na VPS. Homologação antes de produção, com tag `vN` em produção.
- Segurança: login curto + senha (Argon2), JWT com refresh rotativo, bloqueio por tentativas, permissões negadas por padrão, auditoria imutável e segredos de integração cifrados (Fernet) e somente-escrita.

---

## 4. Módulos

Cada módulo tem a sua especificação detalhada (fluxos, regras numeradas, telas e critérios de aceite) em `docs/progresso-<módulo>.md`.
Abaixo, o escopo e o resultado esperado de cada um.

### 4.1 Gestão (herdado e validado no Pilates Nova Versão)
- **Cadastros:** unidades (capacidade > 0), tipos de serviço, profissões, profissionais (comissão em %), planos, horários de funcionamento, bloqueios, fornecedores, categorias, modelos de contrato, de evolução e de termos.
- **Alunos:** ficha completa, documentos, termos assinados, evolução clínica (com IA), histórico.
- **Contratos:** plano, parcelas e preço calculados no domínio, agenda gerada, assinatura eletrônica por link, PDF.
- **Agenda:** grade semanal, aulas, capacidade garantida com bloqueio no banco, presença e falta. Reposição: **o aluno pede e a gerência decide**. Desmarcação só com 6 h de antecedência, com exceção registrada.
- **Financeiro:** contas a receber e a pagar, bancos, caixa, DRE, comissões, recibos Receita Saúde.
- **Comunicação:** WhatsApp (Wasender/Evolution) com avisos automáticos (lembrete de aula, vencimento, aniversário, fim de ciclo) e comunicados.
- **Painel:** KPIs por permissão, alertas e primeiros passos.
- **Perfis:** Full, Secretária e Professor (só as próprias aulas, sem financeiro), além de perfis livres pela matriz de permissões.

### 4.2 Site grátis do estúdio *(novo)*
- One-page em 3 temas com a cor e o logo do estúdio. Seções: hero, sobre, modalidades, planos, grade de horários, equipe, depoimentos, galeria, FAQ, localização e contato.
- Modalidades, planos, horários e equipe vêm **do próprio sistema**: o site nunca fica desatualizado.
- O formulário "Agende sua aula experimental" vira um **lead no CRM**, com anti-spam e consentimento LGPD.
- SEO completo (meta tags, OpenGraph, sitemap, robots, dados estruturados) e alta nota de performance.
- Editor com prévia, publicar e despublicar.
- **Aceite:** um estúdio recém-criado publica o site em menos de 5 minutos e o lead do formulário aparece no funil.

### 4.3 CRM de vendas *(novo)*
- Funil configurável: Novo contato → Aula experimental agendada → Fez aula experimental → Proposta → Matriculado ou Perdido (com motivo).
- Kanban de arrastar, ficha do lead com linha do tempo, tarefas e lembretes ("minhas tarefas de hoje"), WhatsApp em um clique e conversão em aluno.
- Origens: site, Instagram, indicação, Wellhub/TotalPass, passante e outros.
- Relatórios: conversão por etapa e por origem, tempo até matricular e motivos de perda.
- **Aceite:** um lead do site vira aluno com contrato sem redigitar nenhum dado.

### 4.4 Controle de acesso: check-in facial e catraca *(novo)*
- **Regra de acesso:** aluno ativo, contrato vigente e em dia (com tolerância) e aula marcada dentro da janela, ou plano livre no horário de funcionamento. Quando o acesso é negado, o motivo aparece claro.
- **Totem** (tablet na recepção): reconhece o rosto, cumprimenta pelo nome, mostra a aula, registra a presença e libera a catraca. Alternativas: CPF/código + PIN ou QR do app.
- **Biometria (dado sensível, LGPD):** consentimento registrado e descritores cifrados. A foto do check-in nunca vai para o servidor, e há botão para apagar a biometria.
- **Catraca:** drivers Control iD (completo), Henry/Topdata (esqueleto) e simulador. Liberação manual com motivo e auditoria.
- Histórico de acessos e painel "quem está no estúdio agora".

### 4.5 Integrações: TotalPass, Wellhub e API *(Wellhub é novo)*
- **TotalPass** (já existe): webhook de reservas e check-in, sincronização de grade.
- **Wellhub:** Booking API (grade, vagas, reservas e cancelamentos) e Access Control (validação do check-in), com webhook assinado e idempotente, log de eventos com reprocessamento e relatório mensal para conferir o repasse.
- **API para integradores:** tokens por integração (prefixo `mayafit_`), com `cdAluno` legado preservado.

### 4.6 NFS-e *(novo)*
- **Provedores:** NFS-e **Nacional** (padrão gov.br, DPS assinada, cobre a maioria dos municípios e o MEI) e **São Paulo** (layout 2, já validado em produção no MayaJus).
- Assistente de configuração (município → provedor, certificado A1 com validade, regime, código de serviço LC 116 6.04/4.08, ISS).
- **Emissão:** avulsa, a partir de recebimentos pagos (em lote) ou automática ao receber. Idempotente, com fila e retentativa.
- Cancelamento com motivo, PDF/link oficial, envio por e-mail ao aluno, raio-x de erros com mensagem e ação.
- Emissão real só com `AMBIENTE=prod` e o modo Produção ligado na tela.

### 4.7 App do aluno (herdado)
- PWA instalável com a marca do estúdio, entrada por código de 6 dígitos no WhatsApp (válido por 10 minutos).
- Funções: próximas aulas, pedido de reposição, desmarcação com 6 h, recibos e QR de check-in.

### 4.8 Admin MayaFit *(novo)*
- **Início:** MRR, crescimento, churn, receita de 12 meses, testes que vencem em 7 dias, cobranças vencidas e funil de solicitações.
- **Estúdios:** lista com status, plano e uso vs. limite. A ficha tem dados comerciais, domínios, recursos extras, usuários, cobranças, contratos, linha do tempo e "saúde" (último acesso, uso, inadimplência). Ações de um clique: estender o teste, suspender, reativar, reenviar o acesso e definir a senha do Suporte.
- **Solicitações:** cadastro pelo site do MayaFit, aprovado em um clique. O estúdio nasce com banco, subdomínio, usuário Suporte e link de primeiro acesso.
- **Planos e indicação:** planos, preços, limites e recursos, política de indicação e senha do usuário Suporte.
- **Contratos:** modelos com variáveis, gerados e enviados por e-mail.
- **Cobranças:** conta do Mercado Pago (somente-escrita, com teste), régua, geração automática, cobrança avulsa e baixa manual.
- **Meu plano** (do lado do estúdio): plano, uso, cobranças e pagamento.

### 4.9 Visual
- Padrão MayaCorp (o mesmo do MayaJus): menu lateral, Ctrl+K para navegar, skeletons, estados vazios ilustrados e toasts.
- Cores: Navy `#1E2D6B`, Indigo `#7C8FFF`, Teal `#1A8F5E`, Amber `#F5A623`, Red `#C94343`. Fontes: DM Sans e JetBrains Mono para números.
- White-label: a cor e o logo de cada estúdio.
- Funciona bem no celular: professor e recepção usam pelo telefone.

---

## 5. Jornadas ponta a ponta (critérios de aceite do produto)

1. **Venda:** a dona do estúdio preenche o cadastro no site do MayaFit. O admin aprova em um clique, e ela recebe o e-mail de boas-vindas, cria o próprio login e entra em `<slug>.mayafit…` com 60 dias de teste.
2. **Primeiros passos:** no painel, um passo a passo guia o cadastro de unidade, serviço, plano, profissional e horários e a publicação do site. Em menos de 30 minutos o estúdio está operando.
3. **Captação:** um lead agenda aula experimental pelo site e cai no CRM. A secretária confirma pelo WhatsApp com um clique, o lead faz a aula e vira aluno com contrato assinado pelo celular.
4. **Rotina:** o aluno recebe lembrete da aula, faz check-in pelo rosto no totem, a catraca libera e a presença é registrada. A professora registra a evolução pelo celular com ajuda da IA.
5. **Dinheiro:** a mensalidade vence, o aviso sai pelo WhatsApp, o aluno paga, a baixa é feita, a NFS-e é emitida sozinha e o recibo chega por e-mail. A DRE do mês fecha sem planilha.
6. **Parceiros:** a reserva do Wellhub/TotalPass ocupa a vaga na grade e o check-in é validado. No fim do mês, o relatório confere o repasse.
7. **Admin MayaFit:** o teste acaba e a 1ª cobrança sai pelo Mercado Pago. Se não for paga, a régua avisa e o estúdio fica suspenso. Quando paga, ele é reativado sozinho. O admin acompanha MRR e churn.

---

## 6. Requisitos não funcionais

- **Isolamento:** um teste automatizado tenta acessar o estúdio B com o token do A (por host, slug e id) e precisa falhar sempre.
- **LGPD:** biometria e dados de saúde só com consentimento, exportação e exclusão a pedido, logs de auditoria e nenhum dado real em desenvolvimento.
- **Desempenho:** telas comuns em menos de 1 s, site do estúdio com nota alta no Lighthouse e worker por estúdio sem um estúdio travar o outro.
- **Disponibilidade:** backup diário de todos os bancos (controle e estúdios), rollback por tag e homologação antes de produção.
- **Qualidade:** regras de negócio em funções puras com testes e testes de caracterização das regras herdadas do Django. `pytest` e `npm run build` verdes antes de qualquer entrega.

## 7. Fora do escopo desta versão (próximos passos)

- Pagamento do aluno direto pelo app (Pix/cartão com split para o estúdio).
- Mensageria oficial do WhatsApp (API Cloud da Meta) como alternativa ao Wasender/Evolution.
- Aplicativo nativo para lojas (hoje é PWA).
- Multiunidade com consolidação financeira entre unidades de bancos diferentes (rede com vários CNPJs).
