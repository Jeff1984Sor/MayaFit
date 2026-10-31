# NFS-e (nota fiscal de serviço) — especificação e progresso

Branch: `worktree-agent-a4cd66f17ca80e9ae` · Dono: `backend/app/modules/nfse/**`, `backend/tests/nfse/**`,
`frontend/app/(app)/nfse/**`, `frontend/app/(app)/configuracoes/nfse/**`, `frontend/components/nfse/**`,
`frontend/lib/tipos-nfse.ts`, este arquivo. Migration `0150_nfse` (down: `0001_pilates_inicial`).

---

## 1. Especificação

### 1.1 Objetivo

O estúdio emite a nota fiscal de serviço do que recebe dos alunos sem sair do MayaFit: configura uma vez
(assistente), emite avulsa, em lote a partir dos recebimentos pagos ou automaticamente quando o recebimento é
pago. Funciona em qualquer cidade: **Padrão Nacional** (Emissor Nacional / Sefin Nacional, a maioria dos
municípios e todos os MEI) e **Prefeitura de São Paulo** (layout 2, sistema próprio). Nada de nota em dobro,
nada de erro em "códigos": cada recusa vira mensagem em português + o que fazer.

### 1.2 Fluxos

**F1. Configuração (assistente em 5 passos — `/configuracoes/nfse`, permissão `nfse.configurar`)**
1. *Estúdio e município*: digita o CEP → ViaCEP devolve o código IBGE → o MayaFit sugere o provedor
   (`3550308` = São Paulo; capitais com emissor próprio conhecido = aviso; demais = Nacional). CNPJ (validado),
   razão social, inscrição municipal (CCM de 8 dígitos obrigatório em SP), e-mail.
2. *Serviço e tributos*: regime (MEI / Simples / Presumido / Real) em cartões; item da LC 116 sugerido
   (**06.04** atividades físicas — sugerido; **04.08** fisioterapia; 04.09; 08.02); código nacional gerado
   (`06.04` → `060401`); alíquota do ISS (2–5%); % aproximado de tributos do Simples (Lei 12.741); código
   municipal; em SP, NBS/cClassTrib/cIndOp (IBS/CBS do layout 2); ISS retido; "informar alíquota na DPS".
3. *Certificado A1*: envia .pfx + senha → o servidor abre, lê titular/CNPJ/emissor/validade, recusa vencido,
   guarda **cifrado** (`app.core.segredos`); a tela mostra só titular, validade, barra de validade, dias
   restantes e se o CNPJ do certificado confere com o do estúdio. Remover exige confirmação.
4. *Nota e automações*: modelo da discriminação com variáveis clicáveis e prévia ao vivo; série e próximo
   número (nunca reaproveita número usado); enviar e-mail ao aluno; emissão automática.
5. *Ambiente e revisão*: Simulado / Teste / Produção (Produção desabilitada fora do servidor de produção);
   liga/desliga a emissão; checklist de pendências; botão "Testar conexão".

**F2. Emissão avulsa (`/nfse/nova`, `nfse.emitir`)**
1. Escolhe o tomador: aluno (busca por nome/CPF; CPF obrigatório), outra pessoa (CPF) ou empresa (CNPJ).
2. Valor, competência, descrição curta (vira `{descricao}`) ou discriminação livre.
3. O raio-x roda a cada alteração (nota de saúde, totais, ISS estimado, achados). Com erro o botão trava.
4. Emitir → entra na fila e é enviada na hora → abre o detalhe (emitida / rejeitada com o raio-x do retorno).

**F3. Emissão a partir de recebimentos (`/nfse/recebimentos`, `nfse.emitir`)**
1. Lista os recebimentos PAGOS do período (padrão: mês atual) com a situação fiscal (sem nota / com nota) e os
   problemas (aluno sem CPF → link "Corrigir cadastro").
2. Seleciona vários (ou todos os elegíveis) → raio-x do conjunto.
3. "Emitir N notas" → lote: cada recebimento vira no máximo UMA nota (chave `rec:<id>`); ignorados aparecem com
   o motivo. Até 10 notas são enviadas na hora; acima disso seguem pela fila do worker.

**F4. Emissão automática (worker, `nfse-automatica` a cada 5 min)**
Com a emissão ligada e "automática" ativa, todo recebimento pago desde a data em que a automação foi ligada e
ainda sem nota viva entra na fila; alunos sem CPF válido ficam de fora (aparecem nas pendências do painel).

**F5. Fila e retentativa (worker, `nfse-fila` a cada 60 s)**
`pendente → processando → emitida | validada | rejeitada`. Falha de comunicação (timeout, 5xx, 429) → volta a
`pendente`, retentativas em 1, 5, 15, 30, 60 min e depois a cada 2 h; **antes de reenviar, consulta** o provedor
(Nacional: `GET /dps/{id}`; SP: `ConsultaNFe` por RPS). Depois de 8 tentativas → `falha` (botão "Tentar de
novo"). Nota presa em `processando` por mais de 15 min (worker caiu) volta para a fila com consulta.

**F6. Correção e reenvio**: nota rejeitada → "Corrigir" (CPF/CNPJ, nome, e-mail, discriminação) → reenvia com o
MESMO número de DPS/RPS. "Consultar no provedor" busca a nota se ela tiver sido gerada.

**F7. Cancelamento (`nfse.cancelar`)**: motivo (1 erro na emissão, 2 serviço não prestado, 9 outros) +
justificativa de 15 a 255 caracteres. Nacional: evento `e101101` assinado; SP: `CancelamentoNFe`. Nota que
nunca saiu (fila/rejeitada) é só descartada. Cancelada libera a chave (`rec:7` → `rec:7:x<id>`) para nova emissão.

**F8. PDF e e-mail**: emitida → PDF (DANFSe oficial do ADN quando disponível; senão o espelho MayaFit, marcado
"SEM VALOR FISCAL" fora de produção) guardado em `storage/nfse/AAAA-MM/`; e-mail ao tomador com o PDF e o link
oficial (Nacional: consulta pública por chave; SP: `notaprint.aspx`). Reenvio de e-mail pelo detalhe.

**F9. Painel (`/nfse`)**: notas emitidas no mês, valor, ISS estimado (marcado "dentro do DAS" para MEI/Simples),
pagos sem nota (quantidade e valor), gráfico de 6 meses, pendências (rejeitadas, fila, pagos sem nota,
configuração) e o certificado com a barra de validade. Abaixo, a lista com filtros.

### 1.3 Regras fiscais (numeradas)

- **R1** ISS = (valor − deduções) × alíquota, `Decimal`, arredondado em centavos meio-para-cima.
- **R2** Alíquota do ISS entre 2% e 5% (LC 116 art. 8º e 8º-A); fora disso é erro de cadastro.
- **R3** MEI: ISS zero na nota (recolhido no DAS-MEI); `opSimpNac=2`, sem `pAliq`.
- **R4** Simples Nacional: ISS dentro do DAS (o painel mostra estimativa); `opSimpNac=3`, `regApTribSN=1`,
  `pTotTribSN` = % aproximado informado (Lei 12.741). Presumido/Real: `opSimpNac=1`, `indTotTrib=0`.
- **R5** Tomador com CPF/CNPJ obrigatório e com dígitos verificadores válidos (aluno sem CPF não emite).
- **R6** Competência nunca posterior à data de emissão (rejeição E0015) nem futura no raio-x.
- **R7** Discriminação de 1 a 2000 caracteres, sem caracteres de controle; em SP, sem acento.
- **R8** Um recebimento = no máximo uma nota viva (`chave_emissao` UNIQUE `rec:<id>`).
- **R9** Numeração DPS/RPS sequencial por série, reservada com bloqueio (`SELECT ... FOR UPDATE`) e única por
  (provedor, série, número); rejeitada reenvia com o mesmo número; a configuração nunca volta o contador.
- **R10** Id da DPS = `DPS` + município(7) + tipo de inscrição(1) + CNPJ(14) + série(5) + número(15) = 45.
- **R11** Emissão real só com `AMBIENTE=prod` no servidor **e** modo Produção na tela; senão a nota é recusada
  com "Emissão real bloqueada".
- **R12** Certificado vencido ou de outro CNPJ bloqueia (fora do simulado); vencendo em ≤ 30 dias = aviso.
- **R13** Cancelamento com justificativa de 15 a 255 caracteres e código 1/2/9 (TSCodJustCanc).
- **R14** Item LC 116 sugerido: 06.04 (atividades físicas); 04.08 para fisioterapia. Código nacional = item +
  subitem + desdobro `01` (confirmar com o contador).
- **R15** `dhEmi` no fuso de São Paulo, sem frações, recuado 1 minuto (relógio adiantado = rejeição).

### 1.4 Telas

| Rota | O quê |
|---|---|
| `/nfse` | Painel do mês + lista (Todas / Emitidas / Precisam de atenção / Na fila / Validadas / Canceladas; busca por tomador, CPF/CNPJ ou nº; origem; competência) |
| `/nfse/[id]` | Detalhe: status + ambiente, raio-x do retorno, discriminação, tomador, valores, identificação (chave, Id DPS, código de verificação, chave de idempotência), XML enviado/retorno, PDF, nota oficial, linha do tempo, ações |
| `/nfse/nova` | Emissão avulsa com raio-x ao vivo |
| `/nfse/recebimentos` | Recebimentos pagos → seleção → raio-x → lote |
| `/configuracoes/nfse` | Assistente fiscal em 5 passos + resumo lateral |

### 1.5 Estados de erro (mensagem + ação)

| Situação | Mensagem | Ação |
|---|---|---|
| Configuração incompleta | "Configuração incompleta: CNPJ do estúdio ausente ou inválido." | Abrir o passo indicado do assistente |
| Aluno sem CPF | "Sem CPF/CNPJ: Fulano." | Link para a ficha do aluno |
| CPF inválido (local) | "Documento com dígito verificador errado" | Corrigir antes de emitir |
| Já existe nota do recebimento | "N recebimento(s) já têm nota" | Abrir a nota; cancelar para reemitir |
| Possível nota em dobro | "Fulano já recebeu a NFS-e nº X com o mesmo valor neste mês" | Conferir |
| Falha de comunicação | "Sem resposta do provedor; vamos tentar de novo sozinhos." | Nenhuma (consulta antes de reenviar) |
| Falha definitiva | "A prefeitura/Sefin não respondeu depois de várias tentativas." | "Tentar de novo" |
| Produção fora de prod | "Emissão real bloqueada: este servidor não é o de produção." | Mudar para Teste |
| Certificado | vencido / outro CNPJ / não abre (senha) | Enviar o .pfx correto no passo 3 |
| Rejeições Nacional | E0010 série, E0015 competência, E0717 assinatura, E1228 prefixo, E1235 Id DPS, E2404, E999 + heurísticas (CPF/CNPJ do tomador, convênio, alíquota, código de tributação, cadastro nacional, Simples) | Texto específico em `provedores/nacional/erros.py` |
| Rejeições SP | 1057, 1206, 1101, 1102, 1112, 1209, 1211, 1214, 1223, 1301, 1306, 1404, 1405, 1601–1603 | `provedores/sao_paulo/erros.py` (porte do MayaJus) |
| XML fora do XSD | "O XML ficou fora do schema oficial" + linha do erro no detalhe técnico | Conferir o campo; avisar suporte |

### 1.6 Permissões (recurso `nfse`, grupo "Fiscal" no CATALOGO)

`nfse.ver` (painel, lista, detalhe, PDF/XML, ver configuração) · `nfse.emitir` (raio-x, avulsa, lote,
recebimentos, busca de tomador, corrigir, reenviar, consultar, e-mail) · `nfse.cancelar` · `nfse.configurar`
(assistente, certificado, testar). Full tem tudo; **Professor e Secretária não têm nada por padrão** (dar pela
matriz de perfis). Regras em `routes.py` com `adicionar_regras`; ações sensíveis auditadas (emitir, lote,
corrigir, cancelar, configurar, certificado — sem o arquivo nem a senha —, testar).

### 1.7 Critérios de aceite (todos implementados e testados)

- [x] Assistente salva configuração, descobre provedor pelo CEP, valida/cifra certificado e lista pendências.
- [x] DPS nacional e pedido de cancelamento válidos nos XSD oficiais v1.01 e assinados (verificação independente).
- [x] Pedido SP válido no XSD layout 2, assinado com `ds:` (verificado pelo signxml), RPS na ordem do `tpRPS`.
- [x] Emissão avulsa, em lote e automática; lote repetido não duplica (idempotência por recebimento).
- [x] Falha de comunicação → retentativa crescente; a retentativa consulta antes e não gera segundo envio.
- [x] Rejeições mapeadas para mensagem + ação; correção e reenvio com o mesmo número.
- [x] Cancelamento com motivo libera nova emissão; cancelar de novo é recusado.
- [x] Emissão real bloqueada fora de `AMBIENTE=prod`.
- [x] Professor e Secretária recebem 403; rotas cobertas no mapa de permissões.
- [x] Painel com notas do mês, valor, ISS estimado, pendências e série de 6 meses.
- [x] `demo.popular_demo(db)` idempotente.
- [x] `pytest tests/nfse tests/test_cobertura_rotas.py` verde; `npm run lint` e `npm run build` sem erro.

---

## 2. O que foi feito

### Backend (`backend/app/modules/nfse/`)
- `regras.py` — regras puras (R1–R15), sugestões LC 116, variáveis da discriminação.
- `models.py` — `nfse_config` (linha única), `nota_fiscal`, `nota_fiscal_evento`. Migration `0150_nfse.py`
  gerada por autogenerate contra a 0001 (só cria tabelas).
- `certificado.py` — leitura do A1, info, cifra, TLS mútuo, certificado autoassinado para simulado/testes.
- `provedores/base.py` — `Provedor` (montar_xml/emitir/consultar/cancelar/danfse/testar), dataclasses,
  `TransporteHttpx` (TLS mútuo; 5xx/429/timeout = `FalhaComunicacao`).
- `provedores/xmldsig.py` — XMLDSig enveloped sem prefixo (ver "Decisões").
- `provedores/nacional/` — `dps.py` (DPS v1.01 e evento e101101), cliente REST, `erros.py`, `simulador.py`
  (fala o JSON real da API), `xsd/` (pacote oficial NFSe-ESQUEMAS_XSD v1.01 de 09/02/2026, gov.br).
- `provedores/sao_paulo/` — porte do `prefeitura_sp` do MayaJus: `xml_layout2.py`, `assinatura.py`, `erros.py`,
  simulador como transporte SOAP, `xsd/` (os mesmos do MayaJus).
- `servico.py` — configuração, pendências, fila idempotente, processamento, correção, cancelamento, e-mail,
  PDF, listas, painel. `raio_x.py` — análise antes de emitir. `municipios.py` — CEP/IBGE → provedor.
  `pdf.py` — espelho. `routes.py` — API. `tarefas.py` — `nfse-fila`, `nfse-automatica`, `nfse-certificado`.
  `demo.py` — `popular_demo(db)`.

### Rotas (`/api/nfse`)
`GET painel` · `GET notas` · `GET notas/{id}` · `GET notas/{id}/xml?tipo=` · `GET notas/{id}/pdf` ·
`POST raio-x` · `POST notas` · `PATCH notas/{id}` · `POST notas/{id}/reprocessar` · `POST notas/{id}/consultar` ·
`POST notas/{id}/cancelar` · `POST notas/{id}/email` · `GET recebimentos` · `POST recebimentos/emitir` ·
`GET tomadores` · `GET/PUT configuracao` · `GET configuracao/opcoes` · `GET configuracao/municipio` ·
`POST/DELETE configuracao/certificado` · `POST configuracao/testar`.

### Testes (`backend/tests/nfse/`, 83 testes, sem rede)
`test_regras.py` (ISS Decimal, documentos, chaves, Id DPS, datas, discriminação, certificado, retentativa),
`test_xml.py` (XSD oficiais, assinatura conferida de forma independente, C14N contra texto escrito à mão,
MEI/presumido/endereço, evento, SP com signxml, string de assinatura do RPS), `test_provedores.py` (clientes com
transporte falso no formato real, erros mapeados, SOAPAction, homologação SP), `test_api.py` (fluxos completos,
idempotência, consulta antes de reenviar, cancelamento, permissões, worker, demo).

### Frontend
Telas da seção 1.4; componentes em `components/nfse/` (status, achados, certificado com barra de validade,
raio-x com medidor, gráfico); tipos em `lib/tipos-nfse.ts`.

---

## 3. Decisões

1. **Assinatura nacional própria (`xmldsig.py`) em vez do signxml.** O C14N de subárvore do lxml/libxml2 6.x
   emite `xmlns=""` nos netos quando o namespace padrão vem do ancestral (bug reproduzido no teste). O
   signxml usa o mesmo C14N, então "assina e confere" consigo mesmo, mas a Sefin calcularia outro digest.
   Canonicalizamos uma cópia da subárvore (vira raiz e herda as declarações): saída correta, conferida contra
   texto canônico escrito à mão. SP continua no signxml (assina a raiz; validado em produção pelo MayaJus).
2. **XSD nacional sem alteração no disco**; só na validação local um resolvedor troca o padrão da série
   `^0{0,4}\d{1,5}$` (em XSD `^`/`$` são literais: o libxml2 recusaria "1").
3. Signature da DPS sem prefixo (namespace padrão) e RSA-SHA256, como NF-e. SP mantém `ds:` (exigido).
4. Três modos: `simulado` (nada sai; XML montado, assinado e validado; resposta do simulador no formato real),
   `homologacao` (Nacional: produção restrita; SP: TesteEnvioLoteRPS) e `producao`.
5. Emissão automática por varredura (recebimentos pagos sem nota desde a data de ativação), sem depender de
   gancho no financeiro.
6. O prestador emitente não informa `xNome`/`end` na DPS (vêm do Cadastro Nacional de Contribuintes).

---

## 4. Validar na homologação real (produção restrita / Prefeitura)

**Padrão Nacional** (nada disso pôde ser testado sem certificado e sem rede):
- [ ] Algoritmo e forma da assinatura aceitos (RSA-SHA256, C14N inclusivo, `Signature` sem prefixo, transform
      enveloped + c14n). Se vier E0714/E0717 ou similar, testar SHA-1 e/ou exclusive C14N.
- [ ] JSON de envio `{"dpsXmlGZipB64"}` e de evento `{"pedidoRegistroEventoXmlGZipB64"}` (confirmados por relatos
      no fórum ACBr; não estão no manual em PDF) e nomes dos campos de retorno (`chaveAcesso`, `idDps`,
      `nfseXmlGZipB64`, `alertas`, `erros[].Codigo/Descricao/Complemento`).
- [ ] Faixa da série para aplicativo próprio (E0010) — hoje série "1".
- [ ] `pAliq`: quando o município parametrizou a alíquota, informar dá erro? (opção "Informar alíquota na DPS",
      desligada por padrão). `pTotTribSN` obrigatório para Simples?
- [ ] Prestador sem `xNome`/`end` e com `IM` — aceito em todos os municípios?
- [ ] `cTribNac` 060401/040801 (desdobro 01) existentes no ANEXO B; NBS/IBSCBS não são enviados (opcionais no XSD).
- [ ] Id do evento de cancelamento (`PRE` + chave + `101101`, 59 posições no XSD 1.01) e códigos de motivo.
- [ ] URL da consulta pública (`https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave=`) e do DANFSe no ADN
      (`/danfse/{chave}`); parametrização municipal (`/parametros_municipais/{cMun}/convenio`) usada no "Testar".
- [ ] Tabela de erros (`nacional/erros.py`) conferida com o ANEXO I (aba de regras) — hoje é mapeamento inicial.
- [ ] Lista de capitais com emissor próprio (`provedores/__init__.py`) revisada.

**São Paulo**: o porte é fiel ao MayaJus (em produção), mas falta definir com o contador **NBS, cClassTrib e
cIndOp** para estúdios (IBS/CBS do layout 2) e o código de serviço municipal de 5 dígitos; `TributacaoRPS`
padrão "T" (configurável em `parametros_extras.tributacao_sp`).

---

## 5. Pedidos ao coordenador (arquivos que não são meus)

1. **`app/modules/__init__.py` → `registrar_modelos()` precisa importar `nfse`** (como os outros módulos).
   Sem isso o `alembic revision --autogenerate` de outro módulo vai propor `drop_table` das tabelas da NFS-e.
2. `app/core/permissoes.py` → `ROTULO_ACAO`: acrescentar `"emitir": "Emitir"` e `"cancelar": "Cancelar"` (a
   matriz de perfis hoje mostra o id cru). Opcional: dar `nfse.ver`/`nfse.emitir` à Secretária se o Jefferson quiser.
3. Multi-tenant: as tarefas usam `SessionLocal()`; o worker precisa rodá-las com o estúdio definido na
   ContextVar (como as demais tarefas). O storage do PDF usa a categoria `nfse` (`nfse.ver`).
4. Bloqueio por plano: não implementado (coordenador).
5. Seed: chamar `app.modules.nfse.demo.popular_demo(db)` (cria configuração SIMULADA só se ainda não houver CNPJ).
6. `tests/dados/test_migracao.py::test_upgrade_igual_ao_create_all_e_downgrade_limpa` aplica SÓ a `0001` e
   compara com o `create_all` de todo o metadata: com qualquer migration nova (como a `0150_nfse`) ele falha
   por design. Precisa aplicar a cadeia inteira (`alembic upgrade head`). A `0150_nfse` foi conferida à parte:
   `upgrade head` cria `nfse_config`, `nota_fiscal` e `nota_fiscal_evento`; o `downgrade` para a 0001 as remove.
7. Suíte completa (31/10/2026): 3854 passaram; falham o item 6 e dois testes antigos que dependem da data de
   hoje (`app_aluno/test_aulas_reposicao.py::test_lista_so_as_proprias_aulas_futuras_sem_canceladas`, prazo
   fixo em 27/10/2026, e `financeiro/test_receita_saude.py::test_arquivo_por_aluno_...`, nome de arquivo com a
   data fixa 20261025). Nenhum deles é do módulo NFS-e.
8. Financeiro: se no futuro existir um gancho "recebimento pago", basta chamar
   `nfse.servico.enfileirar_recebimento(db, conta_id, origem="automatica")`; hoje a varredura do worker cobre.

## 6. Linhas em arquivos compartilhados

- `backend/app/core/permissoes.py`: grupo "Fiscal" no fim do `CATALOGO` (recurso `nfse`).
- `frontend/components/mayacorp/nav.ts`: 2 ícones importados + 2 itens no grupo Financeiro.
- `backend/pyproject.toml` / `uv.lock`: `lxml>=6.1.3`, `signxml>=5.2.0` (mesmas do MayaJus).
