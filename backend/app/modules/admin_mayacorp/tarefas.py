"""Tarefas periódicas do admin MayaFit. São GLOBAIS (mexem só no banco de controle) e só rodam no modo multi.

- fim dos testes → estúdio "ativo" + 1ª mensalidade;
- mensalidades do mês (se automático) + e-mails da régua;
- suspensão por atraso (SUSPENDER_APOS_DIAS) com aviso;
- foto de uso (`Cliente.uso`) de cada estúdio.

Rodam de hora em hora, mas cada uma no máximo uma vez por dia (o dia fica guardado em memória do worker); todas
são idempotentes, então rodar de novo depois de reiniciar o worker não duplica nada.
"""

import inspect
import logging
from datetime import date

from app import worker
from app.controle import cobranca, ponte

log = logging.getLogger(__name__)

_feito_em: dict[str, date] = {}


def _uma_vez_por_dia(nome: str, fn, hoje: date | None = None) -> bool:
    hoje = hoje or date.today()
    if not ponte.multi() or _feito_em.get(nome) == hoje:
        return False
    fn()
    _feito_em[nome] = hoje
    return True


def rotina_cobranca() -> None:
    """Na ordem: testes que acabaram → mensalidades e régua → suspensão por atraso."""
    def rodar():
        log.info("Fim dos testes: %s", cobranca.encerrar_testes())
        log.info("Cobrança do dia: %s", cobranca.rotina_diaria())
        suspensos = cobranca.suspender_atrasados()
        if suspensos:
            log.info("Suspensos por atraso: %s", ", ".join(suspensos))

    _uma_vez_por_dia("admin-cobranca", rodar)


def fotos_de_uso() -> None:
    _uma_vez_por_dia("admin-uso", lambda: log.info("Fotos de uso: %d estúdio(s)", cobranca.atualizar_fotos_de_uso()))


def _registrar(nome: str, intervalo_s: float, fn) -> None:
    # TODO(fundação): o worker multi-tenant percorre os estúdios; estas tarefas são do CONTROLE e devem rodar uma vez
    # só. Quando `registrar_tarefa` aceitar `global_=True`, ela é passada aqui (detectado pela assinatura).
    if "global_" in inspect.signature(worker.registrar_tarefa).parameters:
        worker.registrar_tarefa(nome, intervalo_s, fn, global_=True)
    else:
        worker.registrar_tarefa(nome, intervalo_s, fn)


_registrar("admin-cobranca", 3600, rotina_cobranca)
_registrar("admin-fotos-de-uso", 3600, fotos_de_uso)
