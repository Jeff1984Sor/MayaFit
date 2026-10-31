"""Driver simulado: para testes e demonstração (não fala com nada). Guarda os giros em memória.

Host "falha" simula equipamento fora do ar.
"""

from __future__ import annotations

from app.modules.acesso.drivers.base import (
    DadosCatraca,
    Driver,
    PlanoNavegador,
    Resultado,
    SentidoGiro,
    giro_do_sentido,
)

GIROS: list[tuple[int, str]] = []


class Simulado(Driver):
    nome = "simulado"
    rotulo = "Simulado (demonstração, sem equipamento)"
    suporta_navegador = True

    def liberar(self, dispositivo: DadosCatraca, sentido: SentidoGiro = "entrada") -> Resultado:
        if (dispositivo.host or "").lower() == "falha":
            return Resultado(False, "Catraca simulada fora do ar.")
        GIROS.append((dispositivo.id, sentido))
        return Resultado(True, f"Giro liberado (simulado, {giro_do_sentido(dispositivo.sentido_entrada, sentido)}).")

    def status(self, dispositivo: DadosCatraca) -> Resultado:
        if (dispositivo.host or "").lower() == "falha":
            return Resultado(False, "Catraca simulada fora do ar.")
        return Resultado(True, "Conectado (catraca simulada).")

    def plano_navegador(self, dispositivo: DadosCatraca, acao: str = "liberar", sentido: SentidoGiro = "entrada") -> PlanoNavegador:
        return PlanoNavegador(self.nome, [], "Catraca simulada: nada a chamar na rede local.")
