"""Drivers de catraca (ver `base.py`)."""

from app.modules.acesso.drivers.base import DadosCatraca, Driver, ErroDriver, PlanoNavegador, Resultado
from app.modules.acesso.drivers.controlid import ControlId
from app.modules.acesso.drivers.henry import Henry
from app.modules.acesso.drivers.simulado import Simulado

DRIVERS: dict[str, Driver] = {d.nome: d for d in (ControlId(), Henry(), Simulado())}


def obter(nome: str) -> Driver:
    try:
        return DRIVERS[nome]
    except KeyError:
        raise ErroDriver(f"Driver de catraca desconhecido: {nome}.") from None


__all__ = ["DRIVERS", "DadosCatraca", "Driver", "ErroDriver", "PlanoNavegador", "Resultado", "obter"]
