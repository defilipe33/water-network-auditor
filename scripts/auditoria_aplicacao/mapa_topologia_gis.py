"""Consulta cartográfica e camadas geridas das hipóteses GIS."""

from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import QInputDialog
from qgis.core import (
    QgsCategorizedSymbolRenderer, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsFeature, QgsFeatureRequest, QgsField, QgsGeometry, QgsLineSymbol, QgsMarkerSymbol,
    QgsPointXY, QgsProject, QgsRectangle, QgsRendererCategory, QgsVectorLayer,
)
from qgis.gui import QgsMapToolEmitPoint

from .grafo_gis import _indexar, ROTULOS
from .investigacao_gis import geometria
from auditoria_fronteiras.modelos import verificar_cancelamento


GRUPO = 'WATER NETWORK AUDITOR — MODELO GIS'
PAPEL = 'wna/topologia_gis/papel'
CONTEXTO = 'wna/topologia_gis/projeto'

# Formas, preenchimento e contorno distinguem os estados também sem as cores.
ESTILOS = {
    'CADASTRADA':('Fonte cadastrada habilitada','triangle','#19a2cf','solid'),
    'INFORMADA':('Fonte complementar habilitada','pentagon','#118b76','solid'),
    'A_CONFIRMAR':('Fonte a confirmar habilitada','diamond','#d99523','solid'),
    'PROPOSTA':('Fonte proposta habilitada','triangle','#00000000','dash'),
    'HIPOTETICA':('Fonte hipotética habilitada','pentagon','#00000000','dash'),
    'DESABILITADA':('Fonte fora da hipótese','triangle','#879197','dot'),
    'CONFIRMADA':('Conexão confirmada nesta hipótese','circle','#119b73','solid'),
    'DECLARADA':('Conexão declarada nesta hipótese','square','#177ead','solid'),
    'CANDIDATA':('Conexão candidata','diamond','#e59c13','solid'),
    'SEPARADA':('Sem conexão','cross2','#7f878d','solid'),
    'HIPOTESE':('Conexão proposta ou hipotética','circle','#00000000','dash'),
    'FORA':('Conexão fora da hipótese','square','#00000000','dot'),
    'INDETERMINADA':('Conexão indeterminada','hexagon','#9868c4','solid'),
    'DIAGNOSTICO':('Diagnóstico','cross','#b8589a','solid'),
}


def _ponto(xy):
    return QgsGeometry.fromPointXY(QgsPointXY(*xy))


def _transformar(g, origem, destino):
    if not origem.isValid() or not destino.isValid():
        raise ValueError('Confira o CRS da geometria e do mapa.')
    if origem!=destino:
        trans=QgsCoordinateTransform(origem,destino,QgsProject.instance())
        if g.transform(trans)!=0:
            raise ValueError('Não foi possível transformar a posição selecionada.')
    return g


def geometria_referencia(r, destino):
    g=geometria(r.get('wkb'))
    if g is None and r.get('xy'):
        g=_ponto(r['xy'])
    if g is None or not r.get('crs'):return None
    return _transformar(g,QgsCoordinateReferenceSystem(r['crs']),destino)


def pontos_portas(portas,tubos):
    pontos=[]
    for u,pos in portas:
        t=tubos.get(u,{})
        g=t.get('geom') or geometria(t.get('wkb'))
        if g is not None and not g.isEmpty() and g.length()>0:
            p=g.interpolate(g.length()*pos).asPoint()
            pontos.append([p.x(),p.y()])
    return pontos


def estilo_conexao(r, ativo):
    if not ativo:return 'FORA'
    decisao=r.get('decisao','CANDIDATA')
    if decisao=='CONFIRMADA':
        if r['situacao'] in ('HIPOTETICA','PROPOSTA'):return 'HIPOTESE'
        return 'CONFIRMADA' if r.get('candidato') else 'DECLARADA'
    return decisao


class IndiceSelecao:
    def __init__(self, elementos, cancelar=None):
        self.elementos=[]
        self.geometrias=[]
        for e in elementos:
            verificar_cancelamento(cancelar)
            g=e.get('geom') or geometria(e.get('wkb'))
            if g is not None and not g.isEmpty():
                self.elementos.append(e)
                self.geometrias.append(g)
        self.indice=_indexar(self.geometrias)
        verificar_cancelamento(cancelar)

    def consultar(self,g,distancia):
        caixa=QgsRectangle(g.boundingBox())
        caixa.grow(distancia)
        encontrados=[]
        for i in self.indice.intersects(caixa):
            outra=self.geometrias[i]
            d=outra.distance(g)
            if 0<=d<=distancia:
                encontrados.append((d,self.elementos[i]['uid'],self.elementos[i],outra))
        return sorted(encontrados,key=lambda r:r[:2])


def escolher(parent, itens, rotulo):
    if not itens:return None
    if len(itens)==1:return itens[0]
    nomes=[f'{rotulo(r)} · opção {i+1}' for i,r in enumerate(itens)]
    nome,ok=QInputDialog.getItem(parent,'Escolher feição no mapa','Foram encontradas várias feições',nomes,editable=False)
    return itens[nomes.index(nome)] if ok else None


def fracao_clicada(linha,ponto,tolerancia):
    medida=linha.lineLocatePoint(ponto)
    comprimento=linha.length()
    if medida<0 or comprimento<=0:raise ValueError('A linha não permite projetar a posição.')
    if comprimento>2*tolerancia:
        if medida<=tolerancia:return 0.
        if comprimento-medida<=tolerancia:return 1.
    return round(max(0.,min(1.,medida/comprimento)),12)


class FerramentaMapa(QgsMapToolEmitPoint):
    """Captura explícita. Esc cancela e botão direito conclui."""
    def __init__(self,canvas,clique,concluir,cancelar):
        super().__init__(canvas)
        self._cancelar=cancelar
        self.canvasClicked.connect(lambda p,b: clique(p) if b==Qt.LeftButton else concluir() if b==Qt.RightButton else None)
        self.setCursor(Qt.CrossCursor)

    def keyPressEvent(self,evento):
        if evento.key()==Qt.Key_Escape:
            evento.accept()
            self._cancelar()
        else:super().keyPressEvent(evento)


class MapaTopologiaGIS:
    NOMES={'origens':'Fontes de água','conexoes':'Conexões e interpretações',
           'vinculos':'Vínculos topológicos (linhas auxiliares)',
           'componentes':'Componentes','diagnosticos':'Diagnósticos'}

    def __init__(self):
        self.registros={}
        self.projeto=None
        self.camadas={}

    def _grupo(self):
        raiz=QgsProject.instance().layerTreeRoot()
        grupos=[g for g in raiz.findGroups() if g.customProperty(CONTEXTO)==self.projeto]
        if grupos:return grupos[0]
        g=raiz.insertGroup(0,GRUPO)
        g.setCustomProperty(CONTEXTO,self.projeto)
        return g

    def _camada(self,papel,crs):
        p=QgsProject.instance()
        anterior=next((c for c in p.mapLayers().values()
                       if c.customProperty(CONTEXTO)==self.projeto and c.customProperty(PAPEL)==papel),None)
        if anterior is not None and anterior.crs()==crs:
            return anterior,False
        vis=True
        if anterior is not None:
            no=p.layerTreeRoot().findLayer(anterior.id())
            vis=no.itemVisibilityChecked() if no else True
            p.removeMapLayer(anterior.id())
        tipo='LineString' if papel=='vinculos' else 'Point'
        c=QgsVectorLayer(tipo,self.NOMES[papel],'memory')
        c.setCrs(crs)
        c.setCustomProperty(CONTEXTO,self.projeto)
        c.setCustomProperty(PAPEL,papel)
        c.setCustomProperty('skipMemoryLayersCheck',1)
        c.dataProvider().addAttributes([QgsField(k,QVariant.String) for k in ('UID','Nome','Estado','Contexto')])
        c.updateFields()
        c.setReadOnly(True)
        p.addMapLayer(c,False)
        self._grupo().addLayer(c).setItemVisibilityChecked(vis if papel not in ('diagnosticos','componentes') else False)
        return c,True

    def _estilo(self,c,papel):
        if papel=='vinculos':
            c.renderer().setSymbol(QgsLineSymbol.createSimple(dict(line_color='#508caa',line_style='dash',line_width='0.45')))
            return
        categorias=[]
        chaves={
            'origens':('CADASTRADA','INFORMADA','A_CONFIRMAR','PROPOSTA','HIPOTETICA','DESABILITADA'),
            'conexoes':('CONFIRMADA','DECLARADA','CANDIDATA','SEPARADA','HIPOTESE','FORA','INDETERMINADA'),
        }.get(papel,('DIAGNOSTICO',))
        for chave in chaves:
            rotulo,forma,cor,contorno=ESTILOS[chave]
            borda='#d69025' if chave=='HIPOTESE' else '#258a99' if chave in ('HIPOTETICA','PROPOSTA') else '#263b42'
            if cor=='#00000000':cor='0,0,0,0'
            s=QgsMarkerSymbol.createSimple(dict(name=forma,color=cor,outline_color=borda,outline_style=contorno,
                                                outline_width='0.45',size='3.9' if papel=='origens' else '2.8'))
            categorias.append(QgsRendererCategory(chave,s,rotulo if papel!='componentes' else 'Componente'))
        c.setRenderer(QgsCategorizedSymbolRenderer('Estado',categorias))

    def atualizar(self,projeto,crs,registros,ativos,resultado=None,contexto=''):
        if not crs.isValid():return
        self.projeto=projeto
        for g in QgsProject.instance().layerTreeRoot().findGroups():
            outro=g.customProperty(CONTEXTO)
            if outro and outro!=projeto and g.itemVisibilityChecked():
                g.setCustomProperty('wna/topologia_gis/ocultado_por_contexto',1)
                g.setItemVisibilityChecked(False)
            if outro==projeto and g.customProperty('wna/topologia_gis/ocultado_por_contexto'):
                g.removeCustomProperty('wna/topologia_gis/ocultado_por_contexto')
                g.setItemVisibilityChecked(True)
        campos={k:[] for k in self.NOMES}
        self.registros={}
        candidatas={x['uid']:x for x in (resultado or {}).get('diagnosticos',[])
                    if x['tipo'] in ('CONEXAO_T','EXTREMIDADES_PROXIMAS','CRUZAMENTO')}
        representadas=set()

        def adicionar(papel,uid,nome,estado,g,registro):
            if g is None or g.isEmpty():return
            campos[papel].append((uid,nome,estado,g))
            self.registros[(papel,uid)]=registro

        for r in registros:
            u=r['uuid']
            ativo=u in ativos
            nome=r.get('nome') or r.get('categoria') or u[:8]
            try:
                g=geometria_referencia(r,crs)
                crs_r=QgsCoordinateReferenceSystem(r.get('crs_rede') or r.get('crs') or '')
                pontos=[_transformar(_ponto(xy),crs_r,crs) for xy in r.get('pontos_rede',[])]
            except (ValueError,RuntimeError):
                continue
            if r['tipo']=='ORIGEM':
                adicionar('origens',u,nome,r['situacao'] if ativo else 'DESABILITADA',g,r)
                if g is not None and g.type()==0 and not g.isMultipart():
                    for ponto in pontos if ativo else ():
                        if g.distance(ponto)>1e-8:
                            link=QgsGeometry.fromPolylineXY([QgsPointXY(g.asPoint()),QgsPointXY(ponto.asPoint())])
                            adicionar('vinculos',u,nome,'VINCULO',link,r)
                            adicionar('conexoes',u,nome,'DECLARADA',ponto,r)
            elif r['tipo']=='CONEXAO':
                cand=candidatas.get(r.get('candidato'))
                if g is None and cand and resultado:
                    g=geometria(cand['wkb'])
                if ativo and cand:representadas.add(cand['uid'])
                gs=[g] if g is not None else pontos
                for ponto in gs:
                    adicionar('conexoes',u,nome,estilo_conexao(r,ativo),ponto,r)
                if ativo and len(pontos)==2 and pontos[0].distance(pontos[1])>1e-8:
                    adicionar('vinculos',u,nome,'VINCULO',QgsGeometry.fromPolylineXY(
                        [QgsPointXY(p.asPoint()) for p in pontos]),r)
        for u,c in candidatas.items():
            if u not in representadas:
                adicionar('conexoes',u,ROTULOS[c['tipo']],'CANDIDATA',geometria(c['wkb']),c)
        for r in (resultado or {}).get('diagnosticos',[]):
            g=geometria(r.get('wkb'))
            if r['uid'] not in candidatas and g is not None:
                adicionar('diagnosticos',r['uid'],ROTULOS[r['tipo']],'DIAGNOSTICO',g.centroid(),r)
        for c in (resultado or {}).get('componentes',[]):
            if c.get('extensao'):
                caixa=c['extensao']
                adicionar('componentes',c['uid'],'Componente '+c['uid'][:8],'DIAGNOSTICO',
                          _ponto([(caixa[0]+caixa[2])/2,(caixa[1]+caixa[3])/2]),c)
        for papel,feicoes in campos.items():
            c,nova=self._camada(papel,crs)
            if nova:self._estilo(c,papel)
            provedor=c.dataProvider()
            provedor.truncate()
            fs=[]
            for u,nome,estado,g in feicoes:
                f=QgsFeature(c.fields())
                f.setGeometry(g)
                f.setAttributes([u,nome,estado,contexto])
                fs.append(f)
            provedor.addFeatures(fs)
            c.updateExtents()
            c.triggerRepaint()
            self.camadas[papel]=c.id()

    def consultar(self,g,crs,tolerancia):
        p=QgsProject.instance()
        achados={}
        for papel,id_camada in self.camadas.items():
            camada=p.mapLayer(id_camada)
            no=p.layerTreeRoot().findLayer(id_camada)
            if camada is None or no is None or not no.isVisible():continue
            pt=_transformar(QgsGeometry(g),crs,camada.crs())
            caixa=QgsRectangle(pt.boundingBox())
            caixa.grow(tolerancia)
            estados=None
            if isinstance(camada.renderer(),QgsCategorizedSymbolRenderer):
                estados={str(c.value()) for c in camada.renderer().categories() if c.renderState()}
            for f in camada.getFeatures(QgsFeatureRequest().setFilterRect(caixa)):
                if estados is not None and f['Estado'] not in estados:continue
                if (papel,f['UID']) in self.registros and f.geometry().distance(pt)<=tolerancia:
                    achados.setdefault(f['UID'],(f['Nome'],self.registros[(papel,f['UID'])]))
        return list(achados.values())
