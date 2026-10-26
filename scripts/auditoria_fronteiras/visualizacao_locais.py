"""Saídas de locais e vínculos; geometrias dos eventos não são modificadas."""
from qgis.PyQt.QtCore import QVariant
from qgis.core import (QgsVectorLayer,QgsField,QgsFeature,QgsGeometry,QgsPointXY,
                       QgsMarkerSymbol,QgsSingleSymbolRenderer,QgsEditorWidgetSetup)
from .entradas import crs_processamento
from .modelos import verificar_cancelamento
from .investigacao import CAMPOS_LOCAIS,validar_analise


def criar_camadas_locais(resultado,analise,cancelar=None):
    from .visualizacao import MARCA_RESULTADO,texto_json
    validar_analise(resultado,analise)
    if not analise.opcoes.habilitado:
        return []
    locais=QgsVectorLayer('Point','PONTOS_INVESTIGACAO','memory')
    locais.setCrs(crs_processamento(resultado.parametros))
    especificacao=[(n,QVariant.Int if n in ('N_EVENTOS','N_TUBOS') else
                    QVariant.Double if n in ('X','Y') else QVariant.String) for n in CAMPOS_LOCAIS]
    especificacao.append(('LOC_UID',QVariant.String))
    vinculos=QgsVectorLayer('None','VINCULOS_LOCAIS','memory')
    esquemas=[(locais,especificacao,'locais'),(vinculos,
        [('LOCAL',QVariant.String),('ID_EVENTO',QVariant.Int),('MOTIVO',QVariant.String),
         ('LOC_UID',QVariant.String),('EVT_UID',QVariant.String),('TECNICO',QVariant.String)],'vinculos')]
    for camada,campos,papel in esquemas:
        if not camada.isValid() or not camada.dataProvider().addAttributes([QgsField(n,t) for n,t in campos]):
            raise RuntimeError('Falha ao criar camada de locais/vínculos')
        camada.updateFields()
        camada.setCustomProperty(MARCA_RESULTADO,True)
        camada.setCustomProperty('auditoria_fronteiras/papel',papel)
        camada.setCustomProperty('auditoria_fronteiras/metadados',texto_json(analise.metadados))
    def gravar(camada,registros):
        lote=[]
        for attrs,geom in registros:
            verificar_cancelamento(cancelar)
            f=QgsFeature(camada.fields())
            f.setAttributes(attrs)
            if geom is not None:
                f.setGeometry(geom)
            lote.append(f)
            if len(lote)>=500:
                if not camada.dataProvider().addFeatures(lote)[0]:
                    raise RuntimeError('Falha ao preencher locais/vínculos')
                lote=[]
        if lote and not camada.dataProvider().addFeatures(lote)[0]:
            raise RuntimeError('Falha ao preencher locais/vínculos')
    gravar(locais,((list(l['registro'].values())+[l['uid']],
        QgsGeometry.fromPointXY(QgsPointXY(l['registro']['X'],l['registro']['Y']))) for l in analise.locais))
    detalhes={l['uid']:l for l in analise.locais}
    gravar(vinculos,(([v['LOCAL'],v['ID_EVENTO'],v['MOTIVO'],v['local_uid'],v['evento_uid'],
                      texto_json(detalhes[v['local_uid']])],None) for v in analise.vinculos))
    configuracao=locais.attributeTableConfig()
    colunas=configuracao.columns()
    for c in colunas:
        if c.name=='LOC_UID':
            c.hidden=True
    configuracao.setColumns(colunas)
    locais.setAttributeTableConfig(configuracao)
    locais.setEditorWidgetSetup(locais.fields().indexFromName('LOC_UID'),QgsEditorWidgetSetup('Hidden',{}))
    locais.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple(
        {'name':'square','color':'255,255,255,0','outline_color':'#005b96','outline_width':'0.7','size':'6'})))
    for c in (locais,vinculos):
        c.updateExtents()
        c.setReadOnly(True)
    return [locais,vinculos]
