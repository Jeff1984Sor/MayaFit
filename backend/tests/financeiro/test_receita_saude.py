"""Receita Saúde (R8): configuração, arquivo por aluno e em lote (erros, ano misto, mais de 1000 linhas, duplicidade)."""

import io
import zipfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import insert, select

from app.core.models import Auditoria
from app.modules.alunos.models import Aluno
from app.modules.financeiro import servico
from app.modules.financeiro.models import ContaReceber, ReceitaSaudeConfig, StatusReceber
from tests.financeiro.conftest import cpf_valido, novo_aluno

CPF_PROF = cpf_valido(555666777)


@pytest.fixture(autouse=True)
def _relogio(monkeypatch):
    from app.modules.financeiro import recibos_saude

    for mod in (servico, recibos_saude):  # o recibo usa o relógio dele (nome do arquivo com a data)
        monkeypatch.setattr(mod, "agora", lambda: datetime(2026, 10, 25, 15, 0, tzinfo=UTC))


@pytest.fixture
def config(db):
    c = ReceitaSaudeConfig(cpf_profissional=CPF_PROF, registro_profissional="CREFITO-3/12345", codigo_ocupacao="231",
                           descricao_padrao="Aulas de Pilates")
    db.add(c)
    db.commit()
    return c


def _paga(db, aluno_id, valor, pag, descricao=None, **kw):
    c = ContaReceber(aluno_id=aluno_id, valor=Decimal(str(valor)), vencimento=pag, status=StatusReceber.PAGO, pagamento=pag,
                     competencia=pag.strftime("%Y-%m"), descricao=descricao, **kw)
    db.add(c)
    db.flush()
    return c


def _linhas(resp):
    return resp.content.decode("utf-8").split("\r\n")[:-1]


# ---------------------------------------------------------------------------------------------- configuração
def test_config_nao_configurada_e_validacoes(client, adm):
    j = client.get("/api/receita-saude/config", headers=adm).json()
    assert j["configurado"] is False and j["problemas"] and j["ocupacoes"]["231"] == "Fisioterapeuta"
    base = {"cpf_profissional": CPF_PROF, "registro_profissional": "CREFITO-3/1", "codigo_ocupacao": "231", "descricao_padrao": "Pilates"}
    assert client.put("/api/receita-saude/config", json={**base, "cpf_profissional": "111.111.111-11"}, headers=adm).status_code == 422
    assert client.put("/api/receita-saude/config", json={**base, "cpf_profissional": "123"}, headers=adm).status_code == 422
    assert client.put("/api/receita-saude/config", json={**base, "codigo_ocupacao": "999"}, headers=adm).status_code == 422
    assert client.put("/api/receita-saude/config", json={**base, "registro_profissional": "x" * 16}, headers=adm).status_code == 422


def test_salvar_config_formata_cpf_e_audita(client, adm, db):
    mascarado = f"{CPF_PROF[:3]}.{CPF_PROF[3:6]}.{CPF_PROF[6:9]}-{CPF_PROF[9:]}"
    r = client.put("/api/receita-saude/config", headers=adm,
                   json={"cpf_profissional": mascarado, "registro_profissional": " CREFITO-3/9 ", "codigo_ocupacao": "231",
                         "descricao_padrao": "Aulas de Pilates"})
    assert r.status_code == 200 and r.json()["cpf_profissional"] == CPF_PROF and r.json()["problemas"] == []
    assert r.json()["registro_profissional"] == "CREFITO-3/9"
    # segunda gravação atualiza o mesmo registro
    client.put("/api/receita-saude/config", headers=adm, json={"cpf_profissional": CPF_PROF, "codigo_ocupacao": "230"})
    assert db.query(ReceitaSaudeConfig).count() == 1
    assert len(list(db.scalars(select(Auditoria).where(Auditoria.acao == "configurar")))) == 2


# -------------------------------------------------------------------------------------------------- por aluno
def test_arquivo_por_aluno_formato_16_colunas_crlf_e_marca_gerado(client, adm, db, cenario, config):
    c1 = _paga(db, cenario.aluno.id, "300.00", date(2026, 10, 12), "Mensalidade; outubro / Pilates")
    c2 = _paga(db, cenario.aluno.id, "1234.5", date(2026, 9, 3))
    db.commit()
    r = client.post(f"/api/receita-saude/alunos/{cenario.aluno.id}/arquivo", json={"conta_ids": [c1.id, c2.id]}, headers=adm)
    assert r.status_code == 200, r.text
    assert r.headers["content-disposition"] == 'attachment; filename="receita-saude-maria-souza-20261025.csv"'
    assert r.content.endswith(b"\r\n") and b"\n" not in r.content.replace(b"\r\n", b"")
    linhas = _linhas(r)
    assert len(linhas) == 2
    cols = linhas[0].split(";")
    assert len(cols) == 16
    # ordenado por data do pagamento: setembro primeiro
    assert cols[0] == "03/09/2026" and cols[1] == "R01.001.001" and cols[2] == "231" and cols[3] == "1234,50"
    assert cols[4] == "" and cols[6] == "PF" and cols[7] == cenario.aluno.cpf == cols[8] and cols[13] == "S"
    assert cols[14] == CPF_PROF and cols[15] == "CREFITO-3/12345"
    seg = linhas[1].split(";")
    assert seg[3] == "300,00" and "Mensalidade, outubro / Pilates" in seg[5] and "competencia 2026-10" in seg[5]
    db.expire_all()
    assert db.get(ContaReceber, c1.id).recibo_saude_gerado_em is not None
    assert db.scalar(select(Auditoria).where(Auditoria.acao == "gerar_arquivo"))


def test_duplicidade_bloqueada_e_liberar_permite_refazer(client, adm, db, cenario, config):
    c = _paga(db, cenario.aluno.id, 100, date(2026, 10, 1))
    db.commit()
    url = f"/api/receita-saude/alunos/{cenario.aluno.id}"
    assert client.post(f"{url}/arquivo", json={"conta_ids": [c.id]}, headers=adm).status_code == 200
    r = client.post(f"{url}/arquivo", json={"conta_ids": [c.id]}, headers=adm)
    assert r.status_code == 409 and "Liberar" in r.json()["detail"]
    item = client.get(url, headers=adm).json()["itens"][0]
    assert item["gerado_em"] and item["pronto"] is False
    assert client.post(f"{url}/liberar", json={"conta_ids": [c.id]}, headers=adm).status_code == 200
    assert client.get(url, headers=adm).json()["itens"][0]["pronto"] is True
    assert client.post(f"{url}/arquivo", json={"conta_ids": [c.id]}, headers=adm).status_code == 200
    assert db.scalar(select(Auditoria).where(Auditoria.acao == "liberar"))


def test_tudo_ou_nada_nenhuma_conta_e_marcada_se_algo_falha(client, adm, db, cenario, config):
    ok = _paga(db, cenario.aluno.id, 100, date(2026, 10, 1))
    zero = _paga(db, cenario.aluno.id, 0, date(2026, 10, 2))
    aberta = ContaReceber(aluno_id=cenario.aluno.id, valor=Decimal("50"), vencimento=date(2026, 10, 3), status=StatusReceber.ABERTO)
    db.add(aberta)
    db.commit()
    r = client.post(f"/api/receita-saude/alunos/{cenario.aluno.id}/arquivo", json={"conta_ids": [ok.id, zero.id, aberta.id]}, headers=adm)
    assert r.status_code == 422
    erros = r.json()["erros"]
    assert any("maior que zero" in e for e in erros) and any("Ainda nao esta paga" in e for e in erros)
    assert r.json()["detail"]
    db.expire_all()
    assert db.get(ContaReceber, ok.id).recibo_saude_gerado_em is None  # nada foi marcado


def test_pagamentos_de_anos_diferentes_nao_geram_arquivo_por_aluno(client, adm, db, cenario, config):
    a = _paga(db, cenario.aluno.id, 100, date(2025, 12, 20))
    b = _paga(db, cenario.aluno.id, 100, date(2026, 1, 5))
    db.commit()
    r = client.post(f"/api/receita-saude/alunos/{cenario.aluno.id}/arquivo", json={"conta_ids": [a.id, b.id]}, headers=adm)
    assert r.status_code == 422 and any("mesmo ano" in e for e in r.json()["erros"])


def test_aluno_sem_cpf_e_cpf_invalido_do_pagador(client, adm, db, cenario, config):
    sem = Aluno(nome="Sem Documento", cpf=None, sem_cpf=True, unidade_id=cenario.unidade.id)
    db.add(sem)
    db.flush()
    c = _paga(db, sem.id, 80, date(2026, 10, 2))
    db.commit()
    j = client.get(f"/api/receita-saude/alunos/{sem.id}", headers=adm).json()
    assert j["sem_cpf"] is True and j["itens"][0]["problemas"] == ["Aluno sem CPF (obrigatorio no recibo)."]
    r = client.post(f"/api/receita-saude/alunos/{sem.id}/arquivo", json={"conta_ids": [c.id]}, headers=adm)
    assert r.status_code == 422
    assert client.put(f"/api/receita-saude/alunos/{sem.id}/pagador", json={"cpf": "123.456.789-00"}, headers=adm).status_code == 422


def test_cpf_do_pagador_vai_nas_colunas_8_e_9(client, adm, db, cenario, config):
    c = _paga(db, cenario.aluno.id, 100, date(2026, 10, 2))
    db.commit()
    pagador = cpf_valido(222333444)
    r = client.put(f"/api/receita-saude/alunos/{cenario.aluno.id}/pagador", json={"cpf": pagador}, headers=adm)
    assert r.status_code == 200 and r.json()["cpf_pagador_recibo"] == pagador
    arq = client.post(f"/api/receita-saude/alunos/{cenario.aluno.id}/arquivo", json={"conta_ids": [c.id]}, headers=adm)
    cols = _linhas(arq)[0].split(";")
    assert cols[7] == pagador and cols[8] == cenario.aluno.cpf
    assert db.scalar(select(Auditoria).where(Auditoria.acao == "definir_pagador"))
    # vazio volta a ser o próprio aluno
    r = client.put(f"/api/receita-saude/alunos/{cenario.aluno.id}/pagador", json={"cpf": ""}, headers=adm)
    assert r.json()["cpf_pagador_recibo"] is None


def test_sem_configuracao_nao_gera(client, adm, db, cenario):
    c = _paga(db, cenario.aluno.id, 100, date(2026, 10, 2))
    db.commit()
    j = client.get(f"/api/receita-saude/alunos/{cenario.aluno.id}", headers=adm).json()
    assert j["config_ok"] is False and j["problemas_config"]
    r = client.post(f"/api/receita-saude/alunos/{cenario.aluno.id}/arquivo", json={"conta_ids": [c.id]}, headers=adm)
    assert r.status_code == 422 and "Configure" in r.json()["detail"]


def test_conta_de_outro_aluno_e_recusada(client, adm, db, cenario, config):
    c = _paga(db, cenario.outro.id, 100, date(2026, 10, 2))
    db.commit()
    r = client.post(f"/api/receita-saude/alunos/{cenario.aluno.id}/arquivo", json={"conta_ids": [c.id]}, headers=adm)
    assert r.status_code == 422
    assert client.get("/api/receita-saude/alunos/9999", headers=adm).status_code == 404


# ----------------------------------------------------------------------------------------------------- em lote
def test_lote_mostra_problemas_por_linha_antes_de_gerar(client, adm, db, cenario, config):
    sem = Aluno(nome="Sem Documento", cpf=None, sem_cpf=True, unidade_id=cenario.unidade.id)
    db.add(sem)
    db.flush()
    _paga(db, cenario.aluno.id, 300, date(2026, 10, 10))
    _paga(db, cenario.outro.id, 200, date(2026, 10, 11))
    ja = _paga(db, cenario.outro.id, 100, date(2026, 10, 12))
    ja.recibo_saude_gerado_em = datetime(2026, 10, 20, tzinfo=UTC)
    _paga(db, sem.id, 80, date(2026, 10, 13))
    _paga(db, cenario.aluno.id, 50, date(2026, 9, 30))  # fora do período
    db.commit()
    j = client.get("/api/receita-saude/lote", params={"de": "2026-10-01", "ate": "2026-10-31"}, headers=adm).json()
    assert (j["total"], j["prontos"], j["com_problema"], j["ja_gerados"], j["arquivos_previstos"]) == (4, 2, 1, 1, 1)
    sem_doc = next(i for i in j["itens"] if i["aluno_nome"] == "Sem Documento")
    assert sem_doc["problemas"] == ["Aluno sem CPF (obrigatorio no recibo)."] and sem_doc["pronto"] is False
    assert [i["aluno_nome"] for i in j["itens"] if i["pronto"]] == ["Maria Souza", "João Lima"]
    assert next(i for i in j["itens"] if i["gerado_em"])["pronto"] is False
    assert client.get("/api/receita-saude/lote", params={"de": "2026-10-31", "ate": "2026-10-01"}, headers=adm).status_code == 422


def test_lote_padrao_gera_so_o_que_esta_pronto(client, adm, db, cenario, config):
    a = _paga(db, cenario.aluno.id, 300, date(2026, 10, 10))
    b = _paga(db, cenario.outro.id, 200, date(2026, 10, 11))
    sem = Aluno(nome="Sem Documento", cpf=None, sem_cpf=True, unidade_id=cenario.unidade.id)
    db.add(sem)
    db.flush()
    ruim = _paga(db, sem.id, 80, date(2026, 10, 13))
    db.commit()
    r = client.post("/api/receita-saude/lote/arquivo", json={"de": "2026-10-01", "ate": "2026-10-31"}, headers=adm)
    assert r.status_code == 200 and r.headers["x-linhas"] == "2" and r.headers["x-arquivos"] == "1"
    assert r.headers["content-type"].startswith("text/csv") and len(_linhas(r)) == 2
    db.expire_all()
    assert db.get(ContaReceber, a.id).recibo_saude_gerado_em and db.get(ContaReceber, b.id).recibo_saude_gerado_em
    assert db.get(ContaReceber, ruim.id).recibo_saude_gerado_em is None
    # segunda tentativa: nada pronto
    assert client.post("/api/receita-saude/lote/arquivo", json={"de": "2026-10-01", "ate": "2026-10-31"}, headers=adm).status_code == 422
    assert db.scalar(select(Auditoria).where(Auditoria.acao == "gerar_arquivo_lote"))


def test_lote_selecao_explicita_com_erro_nao_gera_nada(client, adm, db, cenario, config):
    ok = _paga(db, cenario.aluno.id, 300, date(2026, 10, 10))
    sem = Aluno(nome="Sem Documento", cpf=None, sem_cpf=True, unidade_id=cenario.unidade.id)
    db.add(sem)
    db.flush()
    ruim = _paga(db, sem.id, 80, date(2026, 10, 13))
    db.commit()
    r = client.post("/api/receita-saude/lote/arquivo", json={"de": "2026-10-01", "ate": "2026-10-31", "conta_ids": [ok.id, ruim.id]}, headers=adm)
    assert r.status_code == 422 and any("Sem Documento" in e for e in r.json()["erros"])
    db.expire_all()
    assert db.get(ContaReceber, ok.id).recibo_saude_gerado_em is None
    # conta fora do período informado
    assert client.post("/api/receita-saude/lote/arquivo", json={"de": "2026-09-01", "ate": "2026-09-30", "conta_ids": [ok.id]},
                       headers=adm).status_code == 422


def test_lote_com_mais_de_1000_linhas_divide_em_arquivos_de_ate_1000(client, adm, db, cenario, config):
    base = date(2026, 10, 1)
    rows = [{"aluno_id": cenario.aluno.id, "valor": Decimal("10.00"), "vencimento": base + timedelta(days=i % 28),
             "pagamento": base + timedelta(days=i % 28), "status": "PAGO", "competencia": "2026-10", "criado_em": datetime.now(UTC),
             "atualizado_em": datetime.now(UTC)} for i in range(1001)]
    db.execute(insert(ContaReceber), rows)
    db.commit()
    j = client.get("/api/receita-saude/lote", params={"de": "2026-10-01", "ate": "2026-10-31"}, headers=adm).json()
    assert j["total"] == 1001 and j["prontos"] == 1001 and j["arquivos_previstos"] == 2
    r = client.post("/api/receita-saude/lote/arquivo", json={"de": "2026-10-01", "ate": "2026-10-31"}, headers=adm)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip" and r.headers["x-arquivos"] == "2"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    nomes = sorted(z.namelist())
    assert nomes == ["receita-saude-2026-parte-01-de-02.csv", "receita-saude-2026-parte-02-de-02.csv"]
    contagem = [len(z.read(n).decode().split("\r\n")) - 1 for n in nomes]
    assert contagem == [1000, 1]
    assert db.query(ContaReceber).filter(ContaReceber.recibo_saude_gerado_em.is_not(None)).count() == 1001


def test_lote_nunca_mistura_anos(client, adm, db, cenario, config):
    _paga(db, cenario.aluno.id, 100, date(2025, 12, 20))
    _paga(db, cenario.outro.id, 110, date(2025, 12, 28))
    _paga(db, cenario.aluno.id, 120, date(2026, 1, 5))
    db.commit()
    j = client.get("/api/receita-saude/lote", params={"de": "2025-12-01", "ate": "2026-01-31"}, headers=adm).json()
    assert j["prontos"] == 3 and j["arquivos_previstos"] == 2
    r = client.post("/api/receita-saude/lote/arquivo", json={"de": "2025-12-01", "ate": "2026-01-31"}, headers=adm)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    anos = {}
    for n in z.namelist():
        datas = {linha.split(";")[0][-4:] for linha in z.read(n).decode().split("\r\n") if linha}
        assert len(datas) == 1  # cada arquivo tem um único ano
        anos[n] = datas.pop()
    assert sorted(anos.values()) == ["2025", "2026"]


def test_dividir_em_arquivos_e_puro_por_ano_e_por_1000(db, cenario):
    from app.modules.financeiro import recibos_saude as rs

    contas = []
    for i in range(2050):
        ano = 2025 if i < 1500 else 2026
        c = ContaReceber(id=i + 1, aluno_id=cenario.aluno.id, valor=Decimal("1"), vencimento=date(ano, 6, 1),
                         pagamento=date(ano, 6, 1), status=StatusReceber.PAGO)
        contas.append((c, cenario.aluno))
    blocos = rs.dividir_em_arquivos(contas)
    assert [len(b) for b in blocos] == [1000, 500, 550]
    assert [{c.pagamento.year for c, _ in b} for b in blocos] == [{2025}, {2025}, {2026}]


def test_liberar_lote(client, adm, db, cenario, config):
    c = _paga(db, cenario.aluno.id, 100, date(2026, 10, 2))
    c.recibo_saude_gerado_em = datetime(2026, 10, 3, tzinfo=UTC)
    db.commit()
    r = client.post("/api/receita-saude/lote/liberar", json={"conta_ids": [c.id]}, headers=adm)
    assert r.status_code == 200 and "1 pagamento" in r.json()["mensagem"]
    db.expire_all()
    assert db.get(ContaReceber, c.id).recibo_saude_gerado_em is None
    assert client.post("/api/receita-saude/lote/liberar", json={"conta_ids": [9999]}, headers=adm).status_code == 404


def test_novo_aluno_helper_gera_cpfs_distintos(db, cenario):
    a = novo_aluno(db, cenario.unidade.id, "Novo", 77)
    assert a.cpf != cenario.aluno.cpf
