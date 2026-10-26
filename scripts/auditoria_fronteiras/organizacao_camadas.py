"""Organização somente de saídas próprias, independente de nomes/posição na árvore."""
from pathlib import Path
from qgis.core import QgsLayerTreeGroup

CATEGORIAS={'gis':'AUDITORIA GIS','wg':'TOPOLOGIA WATERGEMS','integrada':'INVESTIGAÇÃO INTEGRADA'}
AMIGAVEIS={'WG_TUBULACOES':'Tubulações WaterGEMS','WG_NOS':'Nós WaterGEMS','WG_DISPOSITIVOS':'Dispositivos WaterGEMS'}

def grupo(projeto,categoria,uid,base='',nome='',versao=None,secao=None):
    raiz=projeto.layerTreeRoot()
    principal=next((g for g in raiz.children() if isinstance(g,QgsLayerTreeGroup) and g.customProperty('wna/categoria')==categoria),None)
    if principal is None:principal=raiz.insertGroup(0,CATEGORIAS[categoria]);principal.setCustomProperty('wna/categoria',categoria)
    origem=str(Path(base).resolve()) if base else ''
    contexto=next((g for g in principal.children() if isinstance(g,QgsLayerTreeGroup) and g.customProperty('wna/uid')==uid and g.customProperty('wna/base')==origem),None)
    if contexto is None:
        contexto=principal.addGroup((nome or 'Execução')+(f' — V{versao:03}' if isinstance(versao,int) else '')+' · '+str(uid)[:8]);contexto.setCustomProperty('wna/uid',uid);contexto.setCustomProperty('wna/base',origem)
    for g in principal.children():
        if not isinstance(g,QgsLayerTreeGroup) or not g.customProperty('wna/uid'):continue
        g.setCustomProperty('wna/ativa',g==contexto)
        rotulo=g.name().removesuffix(' [ATIVA]');g.setName(rotulo+(' [ATIVA]' if g==contexto else ''))
    if secao:
        s=next((g for g in contexto.children() if isinstance(g,QgsLayerTreeGroup) and g.customProperty('wna/secao')==secao),None)
        if s is None:s=contexto.addGroup(secao);s.setCustomProperty('wna/secao',secao);s.setExpanded(False)
        return s
    return contexto

def publicar(camada,projeto,categoria,uid,base='',nome='',versao=None,secao=None,temporaria=False):
    if projeto.mapLayer(camada.id()) and not (camada.customProperty('wna/categoria') in CATEGORIAS or camada.customProperty('integracao/uid') or camada.customProperty('auditoria_fronteiras/resultado',False)):
        raise ValueError('Camada existente sem metadados de propriedade da ferramenta; organização original preservada.')
    tecnico=camada.customProperty('wna/tecnico') or camada.name();fonte=((str(Path(base).resolve()) if base else str(uid))+'::'+tecnico) if camada.providerType()=='memory' and not temporaria else camada.source()
    g=grupo(projeto,categoria,uid,base,nome,versao,'VALIDAÇÃO ESPACIAL — TEMPORÁRIA' if temporaria else secao)
    for c in projeto.mapLayers().values():
        if c.customProperty('wna/categoria')==categoria and c.customProperty('wna/uid')==uid and c.customProperty('wna/base')==(str(Path(base).resolve()) if base else '') and c.customProperty('wna/tecnico')==tecnico:
            if c.isValid() and c.customProperty('wna/fonte')==fonte:
                if c.providerType()=='memory' and c.featureCount()==0 and camada.featureCount()>0:
                    if c.fields().names()!=camada.fields().names() or int(c.customProperty('wna/quantidade',-1))!=camada.featureCount():raise ValueError('Cache de representação incompatível; reabra a versão correta sem substituir as camadas anteriores.')
                    from qgis.core import QgsFeature
                    ok,_=c.dataProvider().addFeatures([QgsFeature(f) for f in camada.getFeatures()])
                    if not ok:raise ValueError('Não foi possível restaurar a representação temporária a partir da base persistente')
                    c.updateExtents()
                return c
            raise ValueError('Camada própria inválida ou fonte divergente; preserve a versão carregada e reabra explicitamente a fonte correta: '+c.name())
    for k,v in [('categoria',categoria),('uid',uid),('base',str(Path(base).resolve()) if base else ''),('tecnico',tecnico),('fonte',fonte),('projeto',nome),('versao',versao or ''),('temporaria',temporaria)]:camada.setCustomProperty('wna/'+k,v)
    camada.setCustomProperty('wna/quantidade',camada.featureCount())
    if categoria!='gis':camada.setName(AMIGAVEIS.get(tecnico,tecnico))
    if not projeto.mapLayer(camada.id()):projeto.addMapLayer(camada,False)
    node=projeto.layerTreeRoot().findLayer(camada.id())
    if node is None:node=g.addLayer(camada)
    elif node.parent()!=g:
        copia=node.clone();g.addChildNode(copia);node=copia
    if secao and not temporaria:node.setItemVisibilityChecked(False)
    return camada

def temporarias(projeto):return [c for c in projeto.mapLayers().values() if c.customProperty('wna/categoria') in CATEGORIAS and c.customProperty('wna/temporaria',False)]

def remover_temporarias(projeto):
    ids=[c.id() for c in temporarias(projeto)];projeto.removeMapLayers(ids);return len(ids)
