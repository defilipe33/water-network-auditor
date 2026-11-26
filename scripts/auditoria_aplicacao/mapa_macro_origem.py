"""Representação exclusiva por segmento, com visibilidade temporária no QGIS."""

from collections import defaultdict

from qgis.PyQt.QtCore import QVariant
from qgis.core import (QgsCategorizedSymbolRenderer, QgsFeature, QgsField, QgsGeometry, QgsLineSymbol,
                       QgsMarkerSymbol, QgsProject, QgsRendererCategory, QgsVectorLayer)

from auditoria_fronteiras.modelos import verificar_cancelamento
from .macro_origem_gis import influencia, acessos_comparados


LINHAS='Visão macro por origem'
ORIGENS='Origens da visão macro'
CORES=('#8ca99f','#b4a17b','#98a8be','#a29db4','#879f80','#bb9f9a','#87a9b4')
PADRAO='#166599'


def _cor(uid):
    from hashlib import sha256
    return CORES[int.from_bytes(sha256(uid.encode()).digest()[:2],'big')%len(CORES)]


def _cores_blocos(blocos):
    usadas=defaultdict(set)
    cores={}
    for b in sorted(blocos,key=lambda b:b['uid']):
        vizinhas={cor for n in b['fronteiras'] for cor in usadas[n]}
        inicial=CORES.index(_cor(b['uid']))
        opcoes=CORES[inicial:]+CORES[:inicial]
        cor=next((c for c in opcoes if c not in vizinhas),opcoes[0])
        cores[b['uid']]=cor
        for n in b['fronteiras']:usadas[n].add(cor)
    return cores


def plano(foto,m,modo,blocos,cor=PADRAO,uniforme=True,alvo=None,espessuras=None,*,papeis=False):
    """Cada segmento possui uma única classe de representação por vista."""
    visiveis={i for b in blocos for i in b['segmentos']}
    por_cor={i:c for c in m['corredores'] for i in c['segmentos']}
    saida=[]
    estilos=dict(contexto=.20,bloco=.36,corredor=1.,destaque=1.4)
    estilos.update(espessuras or {})
    def adicionar(nome,cor,largura,segmentos,prioridade=1):
        r=(nome,cor,str(largura),segmentos)
        saida.append((*r,prioridade) if papeis else r)
    if modo=='INFLUENCIA':
        for u,ids in influencia(foto,m).items():
            rotulo=dict(EMPATE='Empate',TRANSICAO='Transição entre origens',SEM_ACESSO='Sem origem alcançável',
                        INDETERMINADO='Alcance indeterminado').get(u)
            adicionar(rotulo or 'Origem '+u[:8],_cor(u) if rotulo is None else '#a1a5a7','0.52',ids)
        return saida
    if modo=='COMPARACAO':
        for fs,ids in sorted(acessos_comparados(m).items()):
            rotulo='Compartilhado' if len(fs)>1 else 'Origem '+fs[0][:8] if fs else 'Fora da seleção'
            adicionar(rotulo,'#567991' if len(fs)>1 else _cor(fs[0]) if fs else '#a5a9ad','0.68' if fs else '0.18',ids)
        return saida
    if modo in ('BLOCO','CORREDOR'):
        if alvo:adicionar(alvo['nome'],cor,estilos['destaque'],alvo['segmentos'],2)
        return saida
    if modo=='COMPLETA':
        fundo=set(range(len(foto['arestas'])))-visiveis
        if fundo:adicionar('Rede de contexto','#9da3aa',estilos['contexto'],sorted(fundo),0)
    if modo in ('BLOCOS','AMBOS','COMPLETA'):
        cores=_cores_blocos(m['blocos'])
        for b in blocos:
            ids=b['segmentos'] if modo=='BLOCOS' else [i for i in b['segmentos'] if i not in por_cor]
            if ids:adicionar(b['nome'],cores[b['uid']],estilos['bloco'],ids)
    if modo!='BLOCOS':
        for c in m['corredores']:
            ids=[i for i in c['segmentos'] if i in visiveis]
            if ids:adicionar('Corredores de referência' if uniforme else c['nome'],cor if uniforme else _cor(c['uid']),
                             estilos['corredor'],ids,2)
    return saida


def preparar(geo,plano_,origens,cancelar=None):
    linhas=[]
    faltantes=[]
    for nome,cor,largura,segmentos,prioridade in plano_:
        geometrias=[]
        for i in segmentos:
            verificar_cancelamento(cancelar)
            g=geo.trecho(i)
            if g and not g.isEmpty():geometrias.append(g)
            else:faltantes.append(i)
        if geometrias:
            linhas.append((nome,cor,largura,bytes(QgsGeometry.collectGeometry(geometrias).asWkb()),prioridade))
    pontos=[]
    por_porta=None
    for u,referencia in origens.items():
        verificar_cancelamento(cancelar)
        r=geo.origens[u]
        g=referencia
        if not g or g.isEmpty():
            if por_porta is None:
                por_porta={tuple(p):n['uid'] for n in geo.d['foto']['nos'] for p in n['portas']}
            g=next((geo.no(por_porta[tuple(p)]) for p in r['portas'] if tuple(p) in por_porta),None)
        if g and not g.isEmpty():
            pontos.append((r.get('nome') or u[:8],bytes(g.asWkb())))
    return linhas,pontos,faltantes


class MapaMacroOrigem:
    def __init__(self):
        self.ids={}
        self.visibilidades={}

    @staticmethod
    def _arvore():
        return QgsProject.instance().layerTreeRoot()

    def ativo(self):
        return any(self._arvore().findLayer(i) and self._arvore().findLayer(i).itemVisibilityChecked()
                   for i in self.ids.values())

    def atenuar(self, destaque):
        c=QgsProject.instance().mapLayer(self.ids.get(LINHAS,''))
        opacidade=.32 if destaque else 1.
        if c is not None and c.opacity()!=opacidade:
            c.setOpacity(opacidade)
            c.triggerRepaint()

    def restaurar(self):
        self.atenuar(False)
        raiz=self._arvore()
        for i in self.ids.values():
            if n:=raiz.findLayer(i):n.setItemVisibilityChecked(False)
        for i in self.visibilidades:
            n=raiz.findLayer(i)
            if n and not n.itemVisibilityChecked():n.setItemVisibilityChecked(True)
        self.visibilidades.clear()

    def _suspender(self,sobrepostas):
        projeto=QgsProject.instance()
        ra=projeto.layerTreeRoot()
        for c in projeto.mapLayers().values():
            i=c.id()
            if i in self.ids.values():continue
            if (i in sobrepostas or c.customProperty('wna/categoria') in ('estrutura','gis')
                    or c.customProperty('wna/topologia_gis/papel') or c.customProperty('wna/mapa_macro')):
                n=ra.findLayer(i)
                if n and n.itemVisibilityChecked():
                    self.visibilidades[i]=True
                    n.setItemVisibilityChecked(False)

    def _camada(self,nome,tipo,crs,uid):
        projeto=QgsProject.instance()
        c=projeto.mapLayer(self.ids.get(nome,''))
        if c is None:
            c=next((l for l in projeto.mapLayersByName(nome) if l.customProperty('wna/mapa_macro')
                    and l.providerType()=='memory'),None)
        if c is None:
            c=QgsVectorLayer(tipo,nome,'memory')
            c.setCustomProperty('skipMemoryLayersCheck',1)
            c.setCustomProperty('wna/mapa_macro',True)
            c.setReadOnly(True)
            c.dataProvider().addAttributes([QgsField(k,QVariant.String) for k in ('Nome','Classe')])
            c.updateFields()
            projeto.addMapLayer(c,False)
            projeto.layerTreeRoot().insertLayer(0,c)
        self.ids[nome]=c.id()
        c.setCustomProperty('wna/uid',uid)
        c.setCrs(crs)
        return c

    def publicar(self,uid,crs,dados,sobrepostas):
        linhas,pontos,_=dados
        self._suspender(sobrepostas)
        for nome,tipo,registros in ((LINHAS,'MultiLineString',linhas),
                                    (ORIGENS,'MultiPoint',[(n,'#1b6d70','4.0',g,0) for n,g in pontos])):
            c=self._camada(nome,tipo,crs,uid)
            prov=c.dataProvider()
            prov.truncate()
            categorias={}
            fs=[]
            for rotulo,cor,largura,wkb,prioridade in registros:
                chave=f'{rotulo}|{cor}|{largura}|{prioridade}'
                if chave not in categorias:
                    s=(QgsLineSymbol.createSimple(dict(line_color=cor,line_width=largura)) if nome==LINHAS else
                       QgsMarkerSymbol.createSimple(dict(name='triangle',color=cor,outline_color='#ffffff',size=largura)))
                    if nome==LINHAS:
                        s.symbolLayer(0).setRenderingPass(prioridade)
                    categorias[chave]=QgsRendererCategory(chave,s,rotulo)
                g=QgsGeometry()
                g.fromWkb(wkb)
                if nome==ORIGENS and not g.isMultipart():g.convertToMultiType()
                f=QgsFeature(c.fields())
                f.setGeometry(g)
                f.setAttributes([rotulo,chave])
                fs.append(f)
            if fs and not prov.addFeatures(fs)[0]:
                raise OSError('A camada temporária da visão macro não pôde ser publicada.')
            renderer=QgsCategorizedSymbolRenderer('Classe',list(categorias.values()))
            renderer.setUsingSymbolLevels(nome==LINHAS)
            c.setRenderer(renderer)
            c.setOpacity(1.)
            c.updateExtents()
            c.triggerRepaint()
            self._arvore().findLayer(c.id()).setItemVisibilityChecked(bool(fs))
