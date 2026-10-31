"""Driver Henry / Topdata — ESQUELETO DOCUMENTADO (não aciona equipamento ainda).

Como esses equipamentos costumam funcionar (a confirmar com o manual do modelo do cliente e o SDK do fabricante):

- Henry (linhas Primme, 7x, Lumen, Argos): protocolo TCP proprietário (porta padrão 3000), mensagens no formato
  ``<STX><tamanho><índice>+<comando>+<dados><checksum><ETX>``. Liberar a entrada é um comando de "liberação" (ex.:
  ``REON`` com o código ``00+5]5]Acesso liberado]1`` — sentido e mensagem no display variam por firmware). Há também o
  modo ONLINE, em que a catraca pergunta ao servidor a cada leitura e o servidor responde liberando ou negando.
- Topdata (Inner Acesso, Inner Plus): SDK "EasyInner" (DLL Windows) ou protocolo TCP na porta 3570, também com modo
  online. Na prática o caminho mais simples é o AGENTE LOCAL rodando no Windows da recepção com o SDK do fabricante.

Para implementar: (1) obter o manual do protocolo do modelo exato, (2) implementar `_enviar(frame)` por socket TCP
no agente local (`deploy/agente-catraca/`), (3) mapear `liberar`/`status`, (4) validar o sentido de giro no aparelho.
Por isso este driver NÃO oferece plano para o navegador (navegador não abre socket TCP).
"""

from __future__ import annotations

from app.modules.acesso.drivers.base import DadosCatraca, Driver, Resultado, SentidoGiro

PORTA_PADRAO = 3000


def montar_frame(indice: int, comando: str, dados: str) -> bytes:
    """Monta um frame no formato descrito pela documentação pública do protocolo Henry (A VALIDAR no equipamento)."""
    corpo = f"{indice:02d}+{comando}+{dados}".encode("latin-1")
    tamanho = len(corpo).to_bytes(2, "little")
    checksum = 0
    for b in tamanho + corpo:
        checksum ^= b
    return b"\x02" + tamanho + corpo + bytes([checksum]) + b"\x03"


class Henry(Driver):
    nome = "henry"
    rotulo = "Henry / Topdata (esqueleto: requer agente local)"
    suporta_navegador = False

    def liberar(self, dispositivo: DadosCatraca, sentido: SentidoGiro = "entrada") -> Resultado:
        return Resultado(False, "Driver Henry/Topdata ainda não implementado: use o agente local com o SDK do fabricante.",
                         {"frame_exemplo": montar_frame(1, "REON", "00+5]5]Acesso liberado]1").hex()})

    def status(self, dispositivo: DadosCatraca) -> Resultado:
        return Resultado(False, "Driver Henry/Topdata ainda não implementado (esqueleto).")
