"""Auditoria espacial para execução no Python empacotado com QGIS."""
from .modelos import CamadaEntrada, Modo, Parametros, Resultado
from .nucleo import auditar

__all__ = ["CamadaEntrada", "Modo", "Parametros", "Resultado", "auditar"]
