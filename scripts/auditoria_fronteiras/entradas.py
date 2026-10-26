"""Leitura PyQGIS somente leitura; não inicia edição nem corrige originais."""
from collections import Counter
from hashlib import sha256
import json

from qgis.core import (Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsGeometry, QgsProject, QgsUnitTypes, QgsWkbTypes,
                       QgsVariantUtils)
from .modelos import Elemento, Modo, verificar_cancelamento


def digest(valor):
    return sha256(json.dumps(valor, ensure_ascii=False, sort_keys=True,
                             default=str).encode("utf-8")).hexdigest()[:24]


def valor_python(valor):
    return None if QgsVariantUtils.isNull(valor) else valor


def crs_processamento(parametros):
    parametros.validar()
    crs = QgsCoordinateReferenceSystem(parametros.crs)
    if (not crs.isValid() or crs.type() != Qgis.CrsType.Projected
            or crs.mapUnits() != QgsUnitTypes.DistanceMeters):
        raise ValueError("CRS de processamento deve ser projetado em metros")
    return crs


def ler_camadas(configuracoes, tipo, crs, resultado, cancelar=None):
    saida, origens = [], set()
    for config in configuracoes:
        verificar_cancelamento(cancelar)
        camada = config.camada
        if not camada or not camada.isValid():
            raise ValueError("Camada ausente ou inválida")
        if QgsWkbTypes.geometryType(camada.wkbType()) != tipo:
            raise ValueError(f"Tipo geométrico incompatível: {camada.name()}")
        if not camada.crs().isValid():
            raise ValueError(f"CRS ausente: {camada.name()}")
        for campo in (config.campo_id, config.campo_nome):
            if campo and camada.fields().indexFromName(campo) < 0:
                raise ValueError(f"Campo {campo!r} ausente: {camada.name()}")
        origem = config.chave_origem or digest([camada.providerType(), camada.source()])
        if origem in origens:
            raise ValueError("Fonte repetida: use seleções distintas ou chave_origem explícita")
        origens.add(origem)
        modo = Modo(config.modo) if tipo == QgsWkbTypes.PolygonGeometry else None
        resultado.fontes.append(dict(origem=origem, camada=camada.name(),
            fonte=camada.source(), provedor=camada.providerType(),
            campo_id=config.campo_id, campo_nome=config.campo_nome,
            crs_origem=camada.crs().authid(), modo=modo.value if modo else None))
        transformar = (QgsCoordinateTransform(camada.crs(), crs, QgsProject.instance())
                       if camada.crs() != crs else None)
        repeticoes = Counter()
        ids = Counter()
        lidos = 0
        for f in camada.getFeatures():
            verificar_cancelamento(cancelar)
            lidos += 1
            atributos = {campo.name(): valor_python(f[campo.name()]) for campo in camada.fields()}
            original = atributos.get(config.campo_id)
            ids[digest(original)] += 1
            geom = QgsGeometry(f.geometry())
            try:
                if geom.isNull() or geom.isEmpty():
                    raise ValueError("Geometria vazia")
                if QgsWkbTypes.isCurvedType(geom.wkbType()):
                    raise ValueError("Geometria curva: preparar cópia linear explicitamente")
                if not geom.isGeosValid():
                    raise ValueError("Geometria inválida; nenhuma correção automática aplicada")
                if transformar:
                    if geom.transform(transformar) != Qgis.GeometryOperationResult.Success:
                        raise ValueError("Falha na transformação de CRS")
                if geom.isEmpty() or not geom.isGeosValid():
                    raise ValueError("Geometria inválida após transformação")
                if tipo == QgsWkbTypes.LineGeometry and geom.length() <= 0:
                    raise ValueError("Linha sem comprimento")
                assinatura = digest([origem, atributos, bytes(f.geometry().asWkb()).hex()])
                repeticoes[assinatura] += 1
                chave = f"{assinatura}_{repeticoes[assinatura]}"
                saida.append(Elemento(chave, origem, camada.name(), original,
                                      atributos.get(config.campo_nome), geom, modo, atributos))
            except Exception as erro:
                resultado.problemas.append(dict(camada=camada.name(), origem=origem,
                    fid_diagnostico=f.id(), id_original=original, mensagem=str(erro)))
        if not lidos:
            resultado.problemas.append(dict(camada=camada.name(), mensagem="Fonte vazia"))
        if any(n > 1 for n in repeticoes.values()):
            resultado.problemas.append(dict(camada=camada.name(), mensagem=
                "Feições integralmente idênticas preservadas com ordinal; a distinção entre cópias "
                "idênticas não é estável após reordenação sem chave persistente externa"))
        resultado.contadores[f"{tipo}:{origem}"] = dict(lidas=lidos,
            ids_repetidos=sum(n - 1 for n in ids.values()) if config.campo_id else None,
            crs_origem=camada.crs().authid(), modo=modo.value if modo else None)
    return saida
