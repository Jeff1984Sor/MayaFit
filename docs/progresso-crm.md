# CRM de vendas (funil de leads) — especificação e progresso

> Módulo `crm`. Dono de `backend/app/modules/crm/**`, `backend/tests/crm/**`, `frontend/app/(app)/crm/**`,
> `frontend/components/crm/**`, `frontend/lib/tipos-crm.ts` e deste arquivo.

## 1. Especificação

### Objetivo
Transformar interessados (quem mandou mensagem no Instagram, preencheu o site, veio pelo Wellhub/TotalPass, foi
indicado ou passou na porta) em alunos matriculados, sem perder ninguém no caminho. O dono do estúdio enxerga
**quantos leads tem, onde eles travam, de onde vêm os que fecham e o que fazer hoje**.

### Personas
- **Dono(a) / gerência (perfil Full):** configura o funil, acompanha os números (relatório), exclui registros.
- **Secretária / recepção:** atende os contatos, registra ligações e WhatsApp, agenda aula experimental, matricula.
  Vê e edita tudo do CRM; não exclui (perfil padrão).
- **Professor:** não vê o CRM.
- **Site do estúdio (sistema):** cria leads pela função `criar_lead` (sem usuário; audita como "Robô").

### Fluxos (passo a passo)
1. **Lead chega pelo site** → `criar_lead` → se já existe lead ABERTO com o mesmo telefone ou e-mail, acrescenta
   uma interação "Entrou em contato de novo" (não duplica) → senão cria na 1ª etapa ("Novo contato") → cria a tarefa
   automática "Fazer o primeiro contato" (ou "Agendar aula experimental", se pediu) para daqui a 15 min no horário
   comercial → aparece no Kanban e em "Minhas tarefas" de todos (tarefa sem responsável = da equipe).
2. **Lead cadastrado pela equipe** → botão "Novo lead" (atalho **N**) ou "+" na coluna → nome + telefone/e-mail
   (o resto opcional) → quem cadastra vira responsável → duplicado aberto é recusado com o nome do existente.
3. **Primeiro contato** → na ficha, botão **WhatsApp** (link wa.me) com **mensagens prontas** para o momento do lead
   (primeiro contato, confirmar aula, pós-aula, follow-up de proposta, remarcar, reconquistar); ao escolher uma,
   o sistema registra a interação "Mensagem enviada" sozinho. Ou registra ligação/visita/nota (Ctrl+Enter).
4. **Aula experimental** → "Agendar" (atalhos "Amanhã 7h/18h") com professor e unidade opcionais → o lead avança para
   "Aula experimental agendada" (marco) → tarefa automática "Confirmar aula experimental" na véspera → depois da aula,
   "Compareceu" (avança para "Fez aula experimental" + tarefa "Enviar proposta") ou "Faltou" (tarefa "Remarcar").
5. **Proposta** → arrasta o cartão para "Proposta" (ou clica na etapa no topo da ficha).
6. **Matrícula** → "Matricular" (ou arrastar para Matriculado) → o sistema procura **alunos parecidos** (mesmo
   telefone, e-mail ou nome) para vincular em vez de duplicar → ou cria o aluno pelo serviço do módulo alunos
   (unidade obrigatória; CPF e nascimento opcionais; sem CPF vira `sem_cpf`) → lead vai para Matriculado, tarefas
   pendentes são concluídas, confete e atalho "Abrir ficha do aluno".
7. **Perda** → "Perdido" (ou arrastar para a coluna) → escolher o motivo (obrigatório) + detalhe → tarefas pendentes
   concluídas → pode **reabrir** depois (volta para a última etapa aberta em que estava).
8. **Rotina diária** → "Minhas tarefas": saudação, progresso do dia, atrasadas em vermelho no topo, concluir com um
   clique (com "Desfazer"), WhatsApp direto da tarefa.
9. **Gestão** → Relatório com período (30/90 dias, este ano, 12 meses ou datas) e Configurações (etapas e motivos).

### Regras de negócio
1. O funil tem etapas **abertas** configuráveis (nome, cor, ordem, marco, alerta) e exatamente **uma etapa de ganho**
   ("Matriculado") e **uma de perda** ("Perdido"), fixas no fim: podem ser renomeadas, não excluídas nem reordenadas.
2. O funil padrão (Novo contato → Aula experimental agendada → Fez aula experimental → Proposta → Matriculado /
   Perdido) e 8 motivos de perda são criados sozinhos no primeiro uso (`garantir_padrao`, idempotente).
3. A **situação** do lead (ABERTO/GANHO/PERDIDO) deriva da etapa e é guardada para consulta.
4. **Dedup:** não pode haver dois leads ABERTOS com o mesmo telefone (forma canônica 55+DDD+número) ou o mesmo e-mail
   (sem diferenciar maiúsculas). Pela equipe → 409; pelo site → vira interação no lead existente. Reabrir um lead
   também respeita a regra.
5. Mover para **Perdido exige motivo ativo**; encerrar (ganho ou perda) conclui as tarefas pendentes do lead.
6. **Marcos:** agendar aula leva o lead à etapa `AULA_AGENDADA`; "compareceu" leva à `AULA_REALIZADA` — só avança,
   nunca volta (se o lead já está numa etapa posterior, fica onde está). Cada marco existe em no máximo uma etapa.
7. Aula experimental não pode ser marcada no passado (tolerância de 12 h) nem para lead encerrado. Remarcar substitui
   os lembretes automáticos pendentes.
8. **Converter** exige `alunos.editar` para criar aluno (ou `alunos.ver` para vincular a um existente); um lead só
   converte uma vez.
9. Etapa com leads só é excluída escolhendo para qual etapa aberta eles vão (o histórico registra a mudança). O funil
   precisa de ao menos uma etapa aberta; no máximo 15.
10. Motivo de perda **em uso não é apagado**: é desativado (os relatórios continuam com o nome).
11. Interações automáticas (SISTEMA) não podem ser excluídas; interação não pode ser no futuro (para isso, tarefa).
12. **Temperatura:** quente = aula agendada no futuro, aula feita há ≤ 3 dias ou contato há ≤ 2 dias; morno = contato
    há ≤ 7 dias (ou sem contato e no funil há ≤ 2 dias); frio = o resto.
13. **Parado:** dias na etapa ≥ `dias_alerta` da etapa (0 desliga).
14. Tarefa: `atrasada` (venceu), `hoje` (vence hoje, fuso America/Sao_Paulo), `futura`, `concluida`. "Minhas" = minhas
    + sem responsável. Lembretes automáticos caem no horário comercial (8h–20h).
15. **Relatório:** coorte = leads que **entraram** no período. Conversão por etapa = quantos alcançaram cada etapa ou
    além (pelo histórico de movimentos; matriculado conta como tendo passado por todas). Tempo até matricular =
    média de `ganho_em - criado_em`. Perdas por motivo = leads **perdidos** no período. Melhor origem = maior taxa com
    ≥ 3 leads; gargalo = passagem com menor % (com ≥ 5 leads).
16. Kanban mostra todos os abertos e os ganhos/perdidos dos últimos 30 dias.
17. Valores em `Numeric(15,2)`; instantes em UTC (`UtcDateTime`).

### Telas (frontend, visual MayaCorp)
| Tela | Endereço | Destaque ("uau") |
|---|---|---|
| Funil (Kanban) | `/crm` | Frase do dia ("2 aulas experimentais hoje: confirme..."), 5 indicadores clicáveis, arrastar com atualização otimista, cartão com temperatura, dias na etapa (vermelho se parado), tarefa atrasada, aula marcada e WhatsApp; atalhos **N** e **/** |
| Leads | `/crm/leads` | Filtros por situação, etapa, origem, responsável, tag; ordenar por "sem contato há mais tempo" |
| Ficha do lead | `/crm/leads/[id]` | Trilha de etapas clicável, "Próximo passo" sugerido, mensagens prontas de WhatsApp (registram o contato), timeline, tarefas, aula experimental com "Compareceu/Faltou", matricular com detecção de aluno parecido e confete |
| Minhas tarefas | `/crm/tarefas` | Saudação, barra de progresso do dia, atrasadas no topo, concluir com "Desfazer" |
| Relatório | `/crm/relatorio` | Funil em barras com % que avança, "Seu melhor canal" e "Gargalo" calculados, perdas por motivo, tabela por origem |
| Configurações | `/crm/configuracoes` | Etapas com cor, marco automático e alerta de parado; motivos com ativar/desativar |

### Estados vazios e erros
- Funil vazio: ilustração + "Cadastrar o primeiro lead" + explicação de que os leads do site entram sozinhos.
- Lista vazia com filtro: "Limpar filtros". Tarefas vazias: "Tudo em dia!" + "Abrir o funil". Relatório sem dados:
  sugere período maior. Coluna vazia: "Arraste ou clique em +". Lead inexistente: "Lead não encontrado" + voltar.
- Erros da API viram toast (mensagem em português do backend). Arrastar com erro desfaz o movimento otimista.
- Sem permissão: tela "Sem acesso" padrão.

### Permissões
Recurso `crm` (grupo "Vendas"): `crm.ver`, `crm.editar`, `crm.excluir`. Regra única `("*", "/crm", "crm.*")`
(GET=ver, DELETE=excluir, demais=editar). Padrão: Full tudo; **Secretária ver+editar**; Professor nada.
Converter em aluno exige também `alunos.editar` (criar) ou `alunos.ver` (vincular).

### Critérios de aceite (todos atendidos)
- [x] `criar_lead` cria lead/tarefa/auditoria; dedup por telefone e e-mail em leads abertos acrescenta interação.
- [x] Funil configurável (criar, renomear, cor, marco, alerta, reordenar, excluir movendo leads).
- [x] Lead com nome, telefone/WhatsApp, e-mail, origem, interesse, responsável, valor, observações, tags.
- [x] Interações (ligação, WhatsApp, visita, e-mail, nota) + registros automáticos.
- [x] Tarefas com data/hora e responsável; "Minhas tarefas de hoje" com atrasadas em destaque.
- [x] Aula experimental (data/hora, professor, unidade) com lembrete e resultado.
- [x] Converter em aluno via `alunos.servico.criar_aluno` (ou vincular a aluno existente).
- [x] Perda com motivo configurável; reabrir.
- [x] Relatórios: conversão por etapa, por origem, tempo médio até matricular, perdidos por motivo, período filtrável.
- [x] Kanban com arrastar, lista com filtros, ficha (timeline + tarefas), configurações, relatório, botão WhatsApp.
- [x] Toda ação de escrita audita (`ctx.auditar` / `audit.registrar` para o robô).
- [x] Testes: `tests/crm` (47 testes) + `tests/test_cobertura_rotas.py` verdes; `npm run lint` e `npm run build` sem erro.

## 2. Interface estável para outros módulos

```python
from app.modules.crm.servico import criar_lead

lead = criar_lead(db, *, nome: str, telefone: str | None, email: str | None, origem: str = "site",
                  interesse: str | None = None, mensagem: str | None = None,
                  quer_aula_experimental: bool = False) -> CrmLead
```
- Faz **commit**. Levanta `ValueError` (mensagem em português) se faltar nome (≥ 2 letras) ou não houver telefone
  nem e-mail válido. `origem` aceita texto livre ("Instagram", "gympass", "indicação"...; desconhecido = "outros").
- Devolve o lead novo ou o lead aberto existente (dedup). Testado em `tests/crm/test_criar_lead.py`.

Também úteis: `servico.garantir_padrao(db)` e `demo.popular_demo(db) -> int` (dados de demonstração idempotentes).

## 3. Rotas (`/api/crm`, todas com login + `crm.*`)
`GET resumo` · `GET opcoes` · `GET funil` · `GET/POST leads` · `GET/PUT/DELETE leads/{id}` · `POST leads/{id}/mover` ·
`POST leads/{id}/reabrir` · `POST leads/{id}/interacoes` · `DELETE leads/{id}/interacoes/{iid}` ·
`POST leads/{id}/aula-experimental` · `POST leads/{id}/aula-experimental/resultado` · `GET leads/{id}/conversao` ·
`POST leads/{id}/converter` · `GET/POST tarefas` · `PUT/DELETE tarefas/{id}` · `POST tarefas/{id}/concluir|reabrir` ·
`GET/POST etapas` · `PUT etapas/ordem` · `PUT/DELETE etapas/{id}` · `GET/POST motivos` · `PUT/DELETE motivos/{id}` ·
`GET relatorio?de&ate`.

## 4. Banco
Migration `backend/alembic/versions/0110_crm.py` (`revision="0110_crm"`, `down_revision="0001_pilates_inicial"`),
gerada por autogenerate e testada (upgrade → downgrade → upgrade no SQLite). Tabelas: `crm_etapa`,
`crm_motivo_perda`, `crm_lead`, `crm_interacao`, `crm_tarefa`, `crm_movimento`.

## 5. Arquivos compartilhados alterados (só acréscimos)
- `backend/app/core/permissoes.py`: grupo "Vendas" no fim do `CATALOGO` (recurso `crm`: ver/editar/excluir) e a linha
  `| {"crm.ver", "crm.editar"}` no `_SECRETARIA`.
- `frontend/components/mayacorp/nav.ts`: um `import { ChartColumn, ListTodo, Target } from "lucide-react"` e o grupo
  "Vendas" (Funil de vendas, Leads, Tarefas de vendas, Relatório de vendas), depois de "Alunos".

## 6. Pedidos ao coordenador / pendências
1. **Registrar os modelos do CRM em `app/modules/__init__.py::registrar_modelos`** (acrescentar `crm` na lista de
   imports). Sem isso, um `alembic revision --autogenerate` futuro acharia que as tabelas `crm_*` devem ser
   apagadas, e o ETL/seed não as enxergariam. (Em runtime e nos testes já funciona: o `main.py` importa as rotas.)
2. Chamar `app.modules.crm.demo.popular_demo(db)` no seed de demonstração (16 leads sintéticos, idempotente).
3. Encadear a migration `0110_crm` no merge.
4. **Agenda:** a aula experimental guarda só data/hora, professor e unidade no lead. Ligar a uma `AulaAvaliativa`
   exige `aluno_id` (o lead ainda não é aluno), então ficou de fora por ser arriscado. Sugestão futura: ao converter,
   criar a `AulaAvaliativa` pelo serviço da agenda se a aula ainda for futura.
5. As regras puras estão em `app/modules/crm/regras.py` (o módulo não podia tocar `app/domain`); podem ser movidas
   para `app/domain/crm.py` mudando só o import.
6. Futuro: envio de WhatsApp pela API do estúdio (hoje é link wa.me), distribuição automática de leads entre a equipe
   (rodízio), captura de leads do Instagram, e o bloqueio por plano (centralizado pelo coordenador).
