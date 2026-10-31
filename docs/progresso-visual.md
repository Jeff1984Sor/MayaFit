# Progresso — Visual (repaginação no padrão MayaJus)

Branch: `worktree-agent-a571dc72090b1b5fb`. Referência visual: MayaJus (`MayacorpAutomacoes_CFME/frontend`).

## O que mudou

O MayaFit já nasceu do mesmo kit do MayaJus (`components/ui/*` idênticos, mesma estrutura de `components/mayacorp`).
A diferença visível era a **paleta vinho** (#4A1A2C / #B0486B / #6B1F3A). A repaginação:

1. **Paleta MayaCorp** em `app/globals.css` (agora igual à do MayaJus): Navy #1E2D6B é o primário, Indigo #7C8FFF a cor de
   destaque padrão. A cor do estúdio (Configurações › Identidade) continua sobrescrevendo `--brand` em tempo de execução
   (`lib/brand.tsx`). Identidade ganhou os atalhos "Indigo MayaCorp" e "Navy" (Marsala e Vinho continuam como opção).
   O app do aluno usa #7C8FFF como cor padrão quando o estúdio não escolheu uma.
2. **Shell** (`components/mayacorp/shell.tsx`):
   - seção **Admin MayaFit** (arquivo novo `nav-admin.ts`). Com `usuario.estudio.mayacorp === true` o menu mostra só
     Admin MayaFit + Configurações (com Auditoria) + Conta › Minha conta; telas de módulos do estúdio viram "sem acesso" e
     `/dashboard` leva a `/admin`. Para estúdios, `/admin/*` vira "sem acesso". Sem `estudio` (um banco só) nada muda;
   - **FaixaEstudio**: faixa discreta no topo do conteúdo. `teste` → "Período de teste até dd/mm"; `suspenso` →
     "Há uma pendência no seu plano" + link para `/minha-conta/plano`;
   - menu do usuário: **Meu plano** (administrador de estúdio, no modo multi) e **Tour guiado**;
   - `data-tour` no menu, na busca, no menu do usuário e em cada item (`nav:<href>`), `aria-current` no item ativo;
   - selo **novo** e filtro por **recurso do plano** nos itens (ver "Menu" abaixo).
3. **Tour guiado** (`components/mayacorp/tour.tsx`, portado do MayaJus): passos do estúdio e do admin; abre sozinho no
   primeiro acesso (em `/dashboard`, ou `/admin` no admin) e grava `preferencias.tour_visto`.
4. **Busca rápida (Ctrl+K)**: todas as telas do menu (respeitando permissão, admin e recursos), alunos por nome/CPF/telefone,
   grupo **Atalhos** (Minha conta, Meu plano, Tour guiado) e alternar tema.
5. **Login / auth**: painel da marca com selo "MayaFit", prévia flutuante da agenda (decorativa, `aria-hidden`, some em
   telas com menos de 820px de altura) e assinatura "MayaFit · uma solução MayaCorp".
6. **Painel** (`components/painel/*`, só visual, mesma consulta `/painel/resumo`): faixa de boas-vindas escura com
   saudação, resumo do dia (aulas, aniversariantes, alertas) e atalhos por permissão; KPIs com número animado, filete de cor,
   minigráfico (aulas dos últimos 6 meses) e seta ao passar o mouse; gráfico com degradê + linha de média; próximas aulas
   em linha do tempo; aniversariantes com avatar e confete no aniversário do dia; alertas com faixa de gravidade;
   primeiros passos com barra de progresso; ranking de professores com barras animadas.
7. **Acabamento global**: anel de foco visível em links/botões sem estilo próprio, `Skeleton` com brilho deslizante,
   `PageHeader` com entrada suave, `prefers-reduced-motion` respeitado em tudo.

Nenhuma página de módulo teve lógica alterada. Tocadas só no visual: `app/(app)/configuracoes/identidade/page.tsx`
(cor padrão e atalhos de cor) e `app/(aluno)/layout.tsx`, `app/(aluno)/app/icone/[tamanho]/route.tsx`,
`app/(aluno)/app/manifest.json/route.ts` (cor padrão #7C8FFF).

## Design system (especificação)

### Tokens (`app/globals.css`)

| Token | Claro | Escuro | Uso |
|---|---|---|---|
| `--brand` | #7C8FFF (ou a cor do estúdio) | igual | destaque, item ativo, anel de foco, gráficos |
| `--navy` / `text-navy` | #1E2D6B | — | primário claro, ícones sobre fundo tonal (`dark:text-brand`) |
| `--primary` | #1E2D6B | `var(--brand)` | botão padrão |
| `--background` | #F7F8FC (Gray) | #0F1729 (Dark) | fundo da página |
| `--card` | #FFFFFF | Dark + 6% Gray | cartões |
| `--success` / `-ink` | #1A8F5E (Teal) | | pago, ok |
| `--warning` / `-ink` | #F5A623 (Amber) | | atenção, teste |
| `--danger` / `-ink` | #C94343 (Red) | | atrasado, erro |
| `--info-ink` | #1E2D6B | #7C8FFF | texto informativo |
| `--sidebar` | #0F1729 | #0F1729 | menu lateral (sempre escuro) |
| `--radius` | 0.75rem | | `rounded-lg`; cartões usam `rounded-2xl`, faixas de destaque `rounded-3xl` |
| `--sb` / `--tb` / `--faixa` | 248px (64px recolhido) / 52px / 0 ou 22px (hml) | | medidas do shell |

Fontes: DM Sans (texto, `font-sans`) e JetBrains Mono (`font-mono`; números com a classe `num`, que liga `tabular-nums`).
Use `-ink` para texto sobre fundo tonal (`bg-success/10 text-success-ink`) — garante contraste nos dois temas.
Gráficos: `--chart-1..5` e a paleta validada `--viz-*`.

### Utilitários

- `card-surface`: cartão padrão (borda, `rounded-2xl`, sombra suave). `card-hover`: sobe 2px com sombra (cartões clicáveis).
- `glass`: barra translúcida (topo). `brand-gradient`: Navy → cor do estúdio (logos, botões de destaque, barras de progresso).
- `brand-text`: texto em degradê. `grid-bg`: quadriculado sutil (painéis escuros). `brand-glow`: brilho da marca.
- `skeleton-shimmer` (já aplicado no `Skeleton`). `flutuar`: flutuação lenta (ilustrações).
- Animações de entrada: `animate-in fade-in slide-in-from-bottom-1` (tw-animate-css) ou `motion` com atraso escalonado
  (`delay: indice * 0.05`). Tudo é desligado com `prefers-reduced-motion`.

### Componentes compartilhados (`components/mayacorp/*`)

| Componente | Para quê |
|---|---|
| `AppShell`, `FaixaAmbiente`, `FaixaEstudio` | shell; faixa de hml; faixa de teste/pendência do estúdio |
| `nav.ts` (`NAV`, `navPara`, `itemDaRota`, `rotaForaDaCasa`, `temRecurso`, `ativo`) | menu e bloqueio leve de tela |
| `nav-admin.ts` (`NAV_ADMIN`) | seção Admin MayaFit |
| `TourGuiado`, `iniciarTour()` | tour guiado |
| `CommandPalette`, `abrirPaleta()` | busca rápida (Ctrl+K; `/` foca o campo `input[data-busca]` da tela) |
| `PageHeader` | cabeçalho de página (migalhas, ícone, título, descrição, ações) |
| `DataTable`, `EmptyState`, `FormDialog`, `ConfirmDialog`, `Field`/`form.tsx`, `StatusBadge`/`Pill`, `KpiCard`, `AnimatedNumber`, `UserAvatar`, `SemAcesso` | padrão de telas de cadastro |
| `ClientLogo`, `MarcaLogo`, `MayaCorpAssinatura` (= `VersaoRodape`, mantido) | marca do estúdio e assinatura do produto |

Painel (`components/painel/blocos.tsx`): `KpiPainel` (props novas opcionais `indice`, `animar`, `serie`), `Sparkline`,
`Secao` (prop nova `icone`), `Vazio`, `LinhasEsqueleto`, `ItemAlerta`, `LinhaAniversariante`, `ListaPassos`.

### Padrão de página de cadastro

Cabeçalho (`PageHeader`) → toolbar (busca + filtros + botão **Novo**) → tabela (`DataTable`) → vazio ilustrado
(`EmptyState`) → paginação → modal (`FormDialog`) → confirmação (`ConfirmDialog`) → toast (`sonner`).
Carregamento sempre com `Skeleton` no formato do conteúdo (não spinner de página inteira).

### Menu: como entram os módulos novos (CRM/Vendas, Site, Controle de acesso, NFS-e, Wellhub)

Acrescente um grupo em `NAV` (`components/mayacorp/nav.ts`) — a ordem do array é a ordem do menu:

```ts
{
  titulo: "Vendas",
  itens: [
    { label: "CRM", href: "/crm", icone: Handshake, permissao: "crm.ver", recurso: "crm", novo: true },
  ],
},
```

- `permissao`: some se o perfil não tiver; a tela vira "sem acesso" se a pessoa digitar o endereço.
- `recurso`: some se o plano do estúdio não tiver o recurso (`usuario.estudio.recursos`, lista `["crm"]` ou mapa
  `{crm: true}`). Sem estúdio ou sem a informação, aparece.
- `planejado: true`: aparece esmaecido com "em breve" e não é clicável. `novo: true`: selo "novo".
- O grupo some sozinho quando nenhum item sobra; grupos recolhidos são lembrados por usuário. O Ctrl+K e o bloqueio de
  tela já leem o mesmo `NAV`. Para o tour, o item já tem `data-tour="nav:<href>"`.

## Verificação

- `npm run lint` sem erros/avisos; `npm run build` ok.
- Conferência no navegador **não** foi feita por este agente (sem navegador na sessão). O `next dev` subiu sem erros;
  `/login` e `/esqueci-senha` responderam 200 e `/dashboard` redireciona ao login sem sessão (esperado). Vale abrir o
  painel, o menu no celular, o tema escuro e o tour com o backend rodando.

## Pendências / dúvidas para o Jefferson

- `/auth/me` ainda não manda `estudio` (outro agente está no backend); até lá o menu e a faixa ficam como no modo um banco só.
- `lib/auth.tsx` não busca `/auth/me` em `/login`, `/esqueci-senha`, `/redefinir-senha`... Quem cria `primeiro-acesso` e
  `cadastro` deve conferir se essas rotas públicas precisam entrar nessa lista.
- O tour abre sozinho uma vez para cada usuário (inclusive os atuais) no próximo acesso ao painel. Se preferir que só
  usuários novos vejam, basta gravar `tour_visto` na migração/seed.
- Cartões de exemplo do login usam dados ilustrativos (não são do estúdio).
