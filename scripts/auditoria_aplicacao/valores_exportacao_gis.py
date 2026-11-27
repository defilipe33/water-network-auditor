"""Representação JSON dos atributos GIS, com indicação explícita de tipos indisponíveis."""

from datetime import date, datetime, time
from math import isfinite

from qgis.PyQt.QtCore import QByteArray, QDate, QDateTime, QTime, Qt, QVariant
from qgis.core import QgsVariantUtils


def normalizar(valor, pendencias, campo=''):
    if isinstance(valor,QVariant):
        return None if valor.isNull() else normalizar(valor.value(),pendencias,campo)
    if QgsVariantUtils.isNull(valor):
        return None
    if isinstance(valor,(str,int,bool)) or isinstance(valor,float) and isfinite(valor):
        return valor
    if isinstance(valor,QDateTime):
        if valor.timeSpec()==Qt.LocalTime:valor=valor.toOffsetFromUtc(valor.offsetFromUtc())
        return valor.toString(Qt.ISODateWithMs) or None
    if isinstance(valor,(QDate,QTime)):
        return valor.toString(Qt.ISODate if isinstance(valor,QDate) else Qt.ISODateWithMs) or None
    if isinstance(valor,(datetime,date,time)):
        return valor.isoformat()
    if isinstance(valor,(bytes,QByteArray)):
        return {'codificacao':'hex','bytes':bytes(valor).hex()}
    if isinstance(valor,(list,tuple)):
        return [normalizar(v,pendencias,f'{campo}[{i}]') for i,v in enumerate(valor)]
    if isinstance(valor,dict):
        resultado={}
        for k,v in valor.items():
            if isinstance(k,str):
                resultado[k]=normalizar(v,pendencias,f'{campo}.{k}')
            else:
                pendencias.append(dict(campo=campo,tipo=type(k).__name__,motivo='Chave de atributo incompatível'))
        return resultado
    pendencias.append(dict(campo=campo,tipo=type(valor).__name__,motivo='Valor de atributo indisponível no formato'))
    return None
