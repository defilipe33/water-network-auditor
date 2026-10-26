"""Contratos internos da auditoria espacial. Distâncias em metros."""
from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Callable, Optional


class Modo(str, Enum):
    TRANSICAO = "TRANSICAO"
    PERIMETRO = "PERIMETRO"


@dataclass(frozen=True)
class CamadaEntrada:
    camada: Any
    campo_id: Optional[str] = None
    campo_nome: Optional[str] = None
    modo: Modo = Modo.PERIMETRO
    # Identidade persistente opcional para fontes temporárias/renomeadas.
    chave_origem: Optional[str] = None


@dataclass(frozen=True)
class Parametros:
    crs: str = "EPSG:31983"
    tolerancia_geometrica: float = 0.01
    distancia_continuidade: float = 1.0
    distancia_agrupamento: float = 5.0  # Pós-processamento; não altera a detecção geométrica.
    raio_equipamentos: float = 15.0  # Reservado para Etapa 2.

    def validar(self):
        for nome in ("tolerancia_geometrica", "distancia_continuidade",
                     "distancia_agrupamento", "raio_equipamentos"):
            valor = getattr(self, nome)
            if not math.isfinite(valor) or valor < 0:
                raise ValueError(f"{nome} precisa ser finito e não negativo")


@dataclass
class Elemento:
    chave: str
    origem: str
    camada: str
    id_original: Any
    nome: Any
    geometria: Any
    modo: Optional[Modo] = None
    atributos: dict = field(default_factory=dict)

    def referencia(self):
        return dict(chave=self.chave, origem=self.origem, camada=self.camada,
                    id_original=self.id_original, nome=self.nome,
                    atributos_originais=self.atributos)


@dataclass
class Ocorrencia:
    id: str
    classificacao: str
    modo: Modo
    geometria: Any
    tubulacoes: list
    poligonos: list
    parte: int
    distancia_linha: float
    regiao_antes: list = field(default_factory=list)
    regiao_depois: list = field(default_factory=list)
    lado_antes_disponivel: bool = True
    lado_depois_disponivel: bool = True
    ambigua: bool = False
    observacoes: list = field(default_factory=list)
    detalhes: dict = field(default_factory=dict)
    evidencia: str = "CADASTRO"


@dataclass
class Resultado:
    parametros: Parametros
    ocorrencias: list = field(default_factory=list)
    problemas: list = field(default_factory=list)
    contadores: dict = field(default_factory=dict)
    ambiente: dict = field(default_factory=dict)
    fontes: list = field(default_factory=list)
    cancelado: bool = False


class Cancelado(Exception):
    pass


def verificar_cancelamento(cancelar: Optional[Callable[[], bool]]):
    if cancelar and cancelar():
        raise Cancelado("Auditoria cancelada; resultado parcial identificado")
