"""Destaques efêmeros no canvas; nenhuma escrita ou mudança de simbologia."""
from qgis.core import QgsGeometry,QgsCoordinateReferenceSystem,QgsCoordinateTransform,QgsUnitTypes
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt import sip


class MapaDiagnosticos:
    def __init__(self,pacote,projeto,canvas=None):
        self.pacote=pacote;self.projeto=projeto;self.canvas=canvas;self.destaques=[];self.geometrias=[];self.foco=[];self.selecoes={}
        self.elementos=pacote['topologia']['modelo']['elementos']
        self.comps={c['uid']:c for c in pacote['resultado']['componentes']+pacote['resultado']['componentes_potenciais']}

    def limpar(self):
        for item in self.destaques:
            if self.canvas and not sip.isdeleted(self.canvas):self.canvas.scene().removeItem(item)
        self.destaques=[];self.geometrias=[];self.foco=[];self.foco_origem=[];self.centro_local=None

    def adicionar(self,g,cor,tracado=False,foco=True):
        if not g or g.isEmpty():return
        copia=QgsGeometry(g)
        if self.canvas:
            origem=QgsCoordinateReferenceSystem(self.pacote['dossie']['contexto']['parametros']['crs'])
            trans=QgsCoordinateTransform(origem,self.canvas.mapSettings().destinationCrs(),self.projeto)
            copia.transform(trans)
        self.geometrias.append(copia)
        if foco:self.foco.append(copia);self.foco_origem.append(QgsGeometry(g))
        if not self.canvas:return
        from qgis.gui import QgsRubberBand
        b=QgsRubberBand(self.canvas,copia.type());b.setColor(QColor(cor));b.setFillColor(QColor(0,0,0,0))
        b.setWidth(4);b.setIconSize(12);b.setIcon(QgsRubberBand.ICON_CIRCLE)
        if tracado:b.setLineStyle(Qt.DashLine)
        b.setToGeometry(copia,None);self.destaques.append(b)

    def destacar(self,caso,modo='ESTRUTURAL',completo=False):
        self.limpar();ids=set(caso['wg_ids']);p=self.pacote;gs=p.get('geometrias') or {}
        if completo:
            for u in caso['componentes'][modo]:
                c=self.comps[u];ids.update(c['nos']+c['tubos'])
        # Um destaque por família/tipo, evitando milhares de itens de canvas
        # quando o engenheiro solicita um componente extenso completo.
        grupos={}
        for i in sorted(ids):
            g=gs.get(i)
            if g and not g.isEmpty():
                e=self.elementos[i];cor='#1464dc' if e['familia']=='LINK' else '#b817c8' if e['familia']=='DISPOSITIVO' else '#008a69'
                grupos.setdefault((cor,g.type()),[]).append(g)
        for (cor,tipo),geometrias in grupos.items():self.adicionar(QgsGeometry.collectGeometry(geometrias),cor)
        for a in p['areas']:
            if a['uid'] in caso['area_uids']:self.adicionar(a['geometria'],'#887100',foco=False)
        for pend in p['resultado']['pendencias']:
            if pend['gis_uid'] in caso['gis_uids'] and pend['geometria_wkb']:
                g=QgsGeometry();g.fromWkb(bytes.fromhex(pend['geometria_wkb']));self.adicionar(g,'#008ac0')
        if caso['local_uid']:
            l=next(l for l in p['resultado']['locais'] if l['uid']==caso['local_uid']);r=l['registro']
            self.adicionar(QgsGeometry.fromWkt(f"POINT({r['X']} {r['Y']})"),'#dd5500')
            if not completo:self.centro_local=QgsGeometry.fromWkt(f"POINT({r['X']} {r['Y']})")
            for par in p['resultado']['pares']:
                if par['local_uid']==l['uid'] and par['modo']==modo and 'POSSIVEL_CONEXAO_AUSENTE' in par['classes'] and len(par['wg_a'])==len(par['wg_b'])==1:
                    ga,gb=gs.get(par['wg_a'][0]),gs.get(par['wg_b'][0])
                    if ga and gb:self.adicionar(ga.shortestLine(gb),'#f07800',True)
        return len(self.geometrias)

    def aproximar(self):
        if not self.canvas:return 'Mapa indisponível nesta sessão.'
        if not self.foco:return 'Geometria ou referência espacial insuficiente; aproximação não executada.'
        origem=QgsCoordinateReferenceSystem(self.pacote['dossie']['contexto']['parametros']['crs'])
        if origem.isGeographic() or origem.mapUnits()!=QgsUnitTypes.DistanceMeters:return 'Aproximação métrica bloqueada: CRS de processamento não confirmado em metros.'
        caixa=(self.centro_local if self.centro_local else QgsGeometry.collectGeometry(self.foco_origem)).boundingBox()
        caixa.grow(max(15,caixa.width()*.1,caixa.height()*.1))
        trans=QgsCoordinateTransform(origem,self.canvas.mapSettings().destinationCrs(),self.projeto)
        self.canvas.setExtent(trans.transformBoundingBox(caixa));self.canvas.refresh();return 'Mapa aproximado aos destaques; nenhuma geometria foi alterada.'

    def selecionar_gis(self,caso):
        from auditoria_fronteiras.painel import localizar_tubulacoes
        d=self.pacote['dossie'];t=[t for t in d['tubulacoes'] if t['uid'] in caso['gis_uids']]
        encontrados,avisos=localizar_tubulacoes(d,t,self.projeto)
        for u,ids in encontrados.items():
            c=self.projeto.mapLayer(u)
            if ids:
                if u not in self.selecoes:self.selecoes[u]=list(c.selectedFeatureIds())
                c.selectByIds(ids)
        return '; '.join(avisos) or ('Tubulações GIS selecionadas por assinatura completa.' if any(encontrados.values()) else 'Nenhuma origem GIS identificável nesta sessão.')

    def fechar(self):
        self.limpar()
        for u,ids in self.selecoes.items():
            c=self.projeto.mapLayer(u)
            if c is not None:c.selectByIds(ids)
        self.selecoes={}
