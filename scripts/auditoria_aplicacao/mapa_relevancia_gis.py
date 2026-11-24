"""Estilo e identificação apenas das camadas próprias de resultados."""
from qgis.core import (QgsExpression, QgsField, QgsCategorizedSymbolRenderer,
                       QgsRendererCategory, QgsMarkerSymbol)
from qgis.PyQt.QtCore import QVariant
from .relevancia_gis import ROTULOS, SIMBOLOS, VERSAO


def assinatura_renderer(camada):
    from qgis.PyQt.QtXml import QDomDocument
    from qgis.core import QgsReadWriteContext
    from hashlib import sha256
    doc=QDomDocument();doc.appendChild(camada.renderer().save(doc,QgsReadWriteContext()))
    return sha256(doc.toString().encode()).hexdigest()


def configurar(camada, indice, nova=True):
    # Expressões virtuais ficam no projeto QGIS; não alteram o GeoPackage.
    # Uma expressão por categoria, não uma cláusula por feição para cada atributo.
    por_categoria = {k: [] for k in ROTULOS}
    for uid, r in indice.relevancias.items(): por_categoria[r['categoria']].append(uid)
    partes = []
    for k, uids in por_categoria.items():
        if uids:
            partes.append('WHEN "EVT_UID" IN ('+','.join(QgsExpression.quotedString(u) for u in uids)+') THEN '+QgsExpression.quotedString(k))
    expr = 'CASE '+' '.join(partes)+" ELSE 'INDETERMINADA' END" if partes else "'INDETERMINADA'"
    campo = 'WNA_RELEVANCIA'
    i = camada.fields().indexFromName(campo)
    if i < 0: camada.addExpressionField(expr, QgsField(campo, QVariant.String))
    elif camada.expressionField(i): camada.updateExpressionField(i, expr)
    anterior = camada.customProperty('wna/renderer_relevancia', '')
    atual = assinatura_renderer(camada) if camada.renderer() else ''
    if (nova and not anterior) or (anterior and atual == anterior):
        categorias = []
        for k, (cor, forma) in SIMBOLOS.items():
            simbolo = QgsMarkerSymbol.createSimple(dict(name=forma, color=cor, size='2.6',
                                                        outline_color='#202020', outline_width='0.25'))
            categorias.append(QgsRendererCategory(k, simbolo, ROTULOS[k]))
        camada.setRenderer(QgsCategorizedSymbolRenderer(campo, categorias))
        camada.setCustomProperty('wna/renderer_relevancia', assinatura_renderer(camada))
    camada.setCustomProperty('wna/regra_relevancia', VERSAO)
    camada.setMapTipTemplate('Ocorrência [% "EVT_UID" %]<br>[% "WNA_RELEVANCIA" %]<br>Selecione o ponto para consultar os vínculos e o motivo no Auditor.')
    camada.triggerRepaint()
