"""Visões QGIS derivadas do histórico; sem alteração das camadas originais."""
from qgis.core import QgsVectorLayer,QgsField,QgsFeature,QgsGeometry,QgsPointXY,QgsCoordinateReferenceSystem,QgsCoordinateTransform
from qgis.PyQt.QtCore import QVariant
from auditoria_fronteiras.organizacao_camadas import publicar


def _publicar(painel,camada,papel,secao):
    meta=painel.pacote['resultado']['meta'];projeto=painel.legado.projeto
    camada.setCustomProperty('wna/tecnico',papel)
    return publicar(camada,projeto,'integrada',meta['uid'],base=painel.base,nome=meta.get('projeto') or 'Investigação',secao=secao)


def carregar_manuais(painel):
    from .conjuntos_investigacao import atuais
    rs=atuais(painel.base,painel.pacote,'LOCAL_MANUAL');meta=painel.pacote['resultado']['meta'];projeto=painel.legado.projeto
    tecnico='LOCAIS_MANUAIS';anteriores=[c for c in projeto.mapLayers().values() if c.customProperty('wna/uid')==meta['uid'] and c.customProperty('wna/tecnico')==tecnico and c.customProperty('wna/base')==str(__import__('pathlib').Path(painel.base).resolve())]
    if not rs and not anteriores:return None
    crs=painel.pacote['dossie']['contexto']['parametros']['crs'];c=QgsVectorLayer('Point?crs='+crs,'Locais manuais de investigação','memory');pr=c.dataProvider()
    pr.addAttributes([QgsField('LOC_UUID',QVariant.String,len=64),QgsField('TITULO',QVariant.String,len=254),QgsField('ORIGEM',QVariant.String,len=10),QgsField('OBS',QVariant.String)]);c.updateFields();fs=[]
    for r in rs:
        d=r['dados'];p=QgsCoordinateTransform(QgsCoordinateReferenceSystem(d['crs']),c.crs(),projeto).transform(QgsPointXY(d['x'],d['y']));f=QgsFeature(c.fields());f.setAttributes([r['obj_uid'],d.get('titulo',''),'MANUAL',d.get('observacoes','')]);f.setGeometry(QgsGeometry.fromPointXY(p));fs.append(f)
    pr.addFeatures(fs);c.updateExtents()
    if anteriores:
        if len(anteriores)!=1 or not anteriores[0].isValid():raise ValueError('Representações manuais conflitantes/inválidas; preserve as camadas e reabra a execução')
        a=anteriores[0];selecionados={f['LOC_UUID'] for f in a.selectedFeatures()};a.dataProvider().deleteFeatures([f.id() for f in a.getFeatures()]);a.dataProvider().addFeatures(fs);a.updateExtents();a.selectByIds([f.id() for f in a.getFeatures() if f['LOC_UUID'] in selecionados]);a.triggerRepaint();return a
    from qgis.core import QgsMarkerSymbol
    c.renderer().setSymbol(QgsMarkerSymbol.createSimple(dict(name='diamond',color='255,130,20',size='3')))
    c=_publicar(painel,c,tecnico,'Locais manuais');c.setName('Locais manuais de investigação')
    node=projeto.layerTreeRoot().findLayer(c.id())
    if node:node.setItemVisibilityChecked(True)
    def selecionou():
        if not painel._ativo or painel._sincronizando:return
        fs=c.selectedFeatures()
        if len(fs)==1:
            caso=next((v for v in painel.casos if v.get('manual_uid')==fs[0]['LOC_UUID']),None)
            if caso:painel.selecionar_uid(caso['uid'])
    c.selectionChanged.connect(selecionou);painel._conexoes.append((c,selecionou));return c


def carregar_conjunto(painel,vs,nome,registro=None):
    if not painel.pacote['resultado']['meta']['parametros'].get('espacial_habilitado'):raise ValueError('Geometrias WaterGEMS bloqueadas: valide a referência espacial')
    crs=painel.pacote['dossie']['contexto']['parametros']['crs'];c=QgsVectorLayer('LineString?crs='+crs,nome,'memory');pr=c.dataProvider()
    pr.addAttributes([QgsField('WG_ID',QVariant.String,len=30),QgsField('WG_UID',QVariant.String,len=80),QgsField('LABEL',QVariant.String),QgsField('ORIGEM',QVariant.String,len=20),QgsField('CRITERIOS',QVariant.String),QgsField('CLASSE',QVariant.String),QgsField('N_ROTAS',QVariant.Int),QgsField('N_DEST',QVariant.Int),QgsField('COMP_M',QVariant.Double)]);c.updateFields();fs=[]
    for v in vs:
        g=(painel.pacote.get('geometrias') or {}).get(int(v['chave']))
        if not g:raise ValueError('Geometria indisponível para '+v['chave']+'; exporte a lista técnica')
        m=v['dados'].get('metricas',{});f=QgsFeature(c.fields());f.setAttributes([v['chave'],v['dados']['uid'],v['dados']['label'],v['natureza'],'; '.join(v['dados'].get('criterios',[])),m.get('classe','SELECAO_CADASTRAL_OU_MANUAL'),m.get('rotas'),m.get('destinos'),m.get('comprimento_m')]);f.setGeometry(g);fs.append(f)
    from qgis.core import QgsCategorizedSymbolRenderer,QgsRendererCategory,QgsLineSymbol
    categorias=[]
    for classe,cor in [('CORREDOR_COMPARTILHADO','#1464dc'),('RAMO_DESTINO','#e58a13'),('CAMINHO_ENTRE_PONTOS','#008a69'),('SELECAO_CADASTRAL_OU_MANUAL','#666666')]:categorias.append(QgsRendererCategory(classe,QgsLineSymbol.createSimple(dict(line_color=cor,line_width='0.8' if classe=='CORREDOR_COMPARTILHADO' else '0.5')),classe))
    c.setRenderer(QgsCategorizedSymbolRenderer('CLASSE',categorias))
    pr.addFeatures(fs);c.updateExtents();identidade=registro['uid'] if registro else __import__('uuid').uuid4().hex
    c=_publicar(painel,c,'REDE_PRINCIPAL_'+identidade,'Conjuntos de redes');c.setCustomProperty('wna/topo_uid',painel.pacote['resultado']['meta']['topologia']['execucao_uid']);c.setName(nome+' · seleção investigativa');c.selectAll()
    node=painel.legado.projeto.layerTreeRoot().findLayer(c.id())
    if node:node.setItemVisibilityChecked(True)
    return c
