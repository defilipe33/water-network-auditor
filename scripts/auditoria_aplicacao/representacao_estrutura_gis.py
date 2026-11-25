"""Geometrias da fotografia topológica, camadas geridas e exportação local."""

import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from qgis.PyQt.QtCore import QVariant
from qgis.core import (QgsCoordinateReferenceSystem, QgsFeature, QgsField,
                       QgsGeometry, QgsLineSymbol, QgsMarkerSymbol, QgsPointXY, QgsProject, QgsVectorLayer)

from auditoria_fronteiras.modelos import verificar_cancelamento
from auditoria_fronteiras.organizacao_camadas import publicar, grupo
from .corredores_gis import CATEGORIAS
from .investigacao_gis import geometria


CAMADAS = (
    ('CRITICA','Ligações críticas','#bf423a','solid'),
    ('CORREDOR','Corredores alimentadores','#017aa6','solid'),
    ('REDUNDANCIA','Trajetos alternativos independentes','#38856c','dash'),
    ('PASSAGEM','Redes de passagem','#9154ba','dash'),
    ('DESTINOS','Destinos analisados','#d07822','solid'),
)


class GeometriasEstrutura:
    def __init__(self,d):
        self.d=d
        foto=d['foto']
        self.crs=QgsCoordinateReferenceSystem(foto['crs'])
        self.partes={t['uid']:t for t in foto['tubos']}
        self.nos={n['uid']:n['xy'] for n in foto['nos']}
        self.arestas=foto['arestas']
        self.areas={a['uid']:a for a in foto.get('areas',[])}
        self.pipes={t['uid']:t for t in d['tubulacoes']}
        self.rotas={r['uid']:r for r in d['rotas']}
        self.destinos={x['uid']:x for x in d['destinos']}
        self.origens={r['uuid']:r for r in foto['participantes'] if r['tipo']=='ORIGEM'}
        self.conexoes={r['uuid']:r for r in foto['participantes'] if r['tipo']=='CONEXAO'}

    def referencia(self,r):
        from .mapa_topologia_gis import geometria_referencia
        return geometria_referencia(r,self.crs) if r else None

    def tubo(self,uid):
        r=self.pipes.get(uid)
        if not r:return None
        gs=[g for u in r['partes'] if (g:=geometria(self.partes[u].get('wkb')))]
        return QgsGeometry.collectGeometry(gs) if gs else None

    def no(self,uid):
        xy=self.nos.get(uid)
        return QgsGeometry.fromPointXY(QgsPointXY(*xy)) if xy else None

    def destino(self,r):
        if r.get('no_alvo'):return self.no(r['no_alvo'])
        if r['tipo']=='NO':return self.no(r['ref'])
        if r.get('no'):return self.no(r['no'])
        return geometria(self.partes.get(r['ref'],{}).get('wkb'))

    def trecho(self,i):
        e=self.arestas[i];g=geometria(self.partes[e['tubo']].get('wkb'))
        if not g:return None
        a,b=e.get('inicio',0.),e.get('fim',1.)
        if (a,b)==(0.,1.):return g
        return QgsGeometry(g.constGet().curveSubstring(a*g.length(),b*g.length()))

    def itens(self,tipo,r,opcao=None):
        if tipo=='TUBOS':
            g=self.tubo(r['uid'])
            return [('tubo',g)] if g else []
        if tipo=='ROTAS':
            de=self.destinos[r['destino']]
            itens=[('evento',self.destino(de))]
            if opcao not in ('alternativa','origem'):
                g=QgsGeometry.collectGeometry([g for i in r['segmentos'] if (g:=self.trecho(i))])
                itens.append(('tubo',g))
            if opcao in (None,'alternativa') and r.get('alternativa'):
                g=QgsGeometry.collectGeometry([g for i in r['alternativa']['segmentos'] if (g:=self.trecho(i))])
                itens.append(('vinculo',g))
            fonte=self.referencia(self.origens[r['origem']])
            if not fonte:fonte=self.no(r['nos'][0])
            if opcao=='origem':return [('equipamento',fonte)]
            itens.append(('equipamento',fonte))
            return itens
        if tipo=='DESTINOS':
            return [('evento',self.destino(r))]
        if tipo=='ARTICULACOES':
            return [('evento',self.no(r['uid']))]
        if tipo=='ZONAS':
            a=geometria(self.areas.get(r['uid'],{}).get('wkb'))
            vias={i for u in r['rotas'] for i in self.rotas[u]['segmentos']}
            g=QgsGeometry.collectGeometry([g for i in vias if (g:=self.trecho(i))])
            return [('local',a),('tubo',g)]
        if tipo=='COMPONENTES':
            partes=r.get('partes')
            gs=([g for u in partes if (g:=geometria(self.partes[u].get('wkb')))] if partes is not None else
                [g for u in r['tubos'] if (g:=self.tubo(u))])
            return [('tubo',QgsGeometry.collectGeometry(gs))]
        return []

    def feicoes(self,codigo,cancelar):
        if codigo=='DESTINOS':
            for d in self.destinos.values():
                verificar_cancelamento(cancelar)
                g=self.destino(d)
                if g and not g.isEmpty():yield (d['uid'],d['nome'],d['estado']),g.centroid()
            return
        if codigo in ('CORREDOR','REDUNDANCIA'):
            unicos={}
            for r in self.rotas.values():
                via=r if codigo=='CORREDOR' else r.get('alternativa') if r['alternativa_estado']=='DISJUNTA_VERIFICADA' else None
                if via:
                    for i in via['segmentos']:unicos.setdefault(i,r['uid'])
            for i,u in unicos.items():
                verificar_cancelamento(cancelar)
                g=self.trecho(i)
                if g and not g.isEmpty():yield (str(i),u,CATEGORIAS[codigo]),g
            return
        for r in self.pipes.values():
            verificar_cancelamento(cancelar)
            if codigo not in r['funcoes']:continue
            for u in r['partes']:
                g=geometria(self.partes[u].get('wkb'))
                if g and not g.isEmpty():yield (r['uid'],str(r.get('id') or r.get('nome') or u[:10]),CATEGORIAS[codigo]),g


def carregar_camadas(d,geometrias):
    projeto=QgsProject.instance()
    for codigo,nome,cor,estilo in CAMADAS:
        existentes=[c for c in projeto.mapLayers().values() if c.customProperty('wna/categoria')=='estrutura'
                   and c.customProperty('wna/uid')==d['uuid'] and c.customProperty('wna/tecnico')==nome]
        if existentes and existentes[0].featureCount()>0:continue
        camada=QgsVectorLayer('Point' if codigo=='DESTINOS' else 'LineString',nome,'memory')
        camada.setCrs(geometrias.crs)
        camada.setCustomProperty('skipMemoryLayersCheck',1)
        p=camada.dataProvider()
        p.addAttributes([QgsField(k,QVariant.String) for k in ('UID','REF','CLASSE')])
        camada.updateFields()
        fs=[]
        for valores,g in geometrias.feicoes(codigo,None):
            f=QgsFeature(camada.fields());f.setAttributes(list(valores));f.setGeometry(g);fs.append(f)
        if not fs:continue
        if not p.addFeatures(fs)[0]:raise OSError('Não foi possível gerar a camada '+nome+'.')
        if codigo=='DESTINOS':
            camada.renderer().setSymbol(QgsMarkerSymbol.createSimple(dict(name='diamond',color=cor,size='2.9')))
        else:
            camada.renderer().setSymbol(QgsLineSymbol.createSimple(dict(line_color=cor,line_style=estilo,line_width='0.55')))
        camada.setReadOnly(True);camada.updateExtents()
        publicar(camada,projeto,'estrutura',d['uuid'],nome=d['nome'])
    grupo(projeto,'estrutura',d['uuid'],nome=d['nome'])


def exportar(d,pasta,formato,cancelar=None,etapa=lambda *_:None):
    from osgeo import ogr,osr
    if formato not in ('GPKG','ESRI Shapefile'):raise ValueError('Formato de exportação inválido.')
    destino=Path(pasta)/f"EstruturaGIS_{d['uuid'][:8]}_{uuid4().hex[:8]}"
    gs=GeometriasEstrutura(d)
    crs=osr.SpatialReference()
    if crs.ImportFromWkt(gs.crs.toWkt())!=0:raise ValueError('O CRS da execução está indisponível.')
    driver=ogr.GetDriverByName(formato)
    with TemporaryDirectory(prefix='.estrutura_',dir=pasta) as tmp:
        p=Path(tmp)/'saida';p.mkdir()
        gpkg=driver.CreateDataSource(str(p/'estrutura.gpkg')) if formato=='GPKG' else None
        if formato=='GPKG' and gpkg is None:raise OSError('Não foi possível criar o GeoPackage.')
        for codigo,nome,_,_ in CAMADAS:
            verificar_cancelamento(cancelar)
            etapa(0,'Exportando '+nome)
            ds=gpkg if gpkg is not None else driver.CreateDataSource(str(p/(codigo.lower()+'.shp')))
            if ds is None:raise OSError('Não foi possível criar '+nome+'.')
            ly=ds.CreateLayer(codigo.lower(),crs,ogr.wkbPoint if codigo=='DESTINOS' else ogr.wkbLineString,
                              options=['ENCODING=UTF-8'] if gpkg is None else [])
            if ly is None:raise OSError('Não foi possível publicar '+nome+'.')
            for k in ('UID','REF','CLASSE'):
                campo=ogr.FieldDefn(k,ogr.OFTString);campo.SetWidth(128)
                if ly.CreateField(campo)!=0:raise OSError('Falha no campo '+k+'.')
            for vals,g in gs.feicoes(codigo,cancelar):
                f=ogr.Feature(ly.GetLayerDefn())
                for i,v in enumerate(vals):f.SetField(i,v)
                f.SetGeometry(ogr.CreateGeometryFromWkb(bytes(g.asWkb())))
                if ly.CreateFeature(f)!=0:raise OSError('Falha ao gravar elemento em '+nome+'.')
            ly=None;ds=None
        gpkg=None
        for arquivo,chave in [('tubulacoes','tubulacoes'),('destinos','destinos'),('zonas','zonas'),('rotas','rotas')]:
            itens=d[chave]
            if not itens:continue
            colunas=list(dict.fromkeys(k for r in itens for k in r))
            with (p/(arquivo+'.csv')).open('x',newline='',encoding='utf-8-sig') as f:
                writer=csv.DictWriter(f,colunas);writer.writeheader()
                for r in itens:
                    verificar_cancelamento(cancelar)
                    writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()})
        meta={k:d[k] for k in ('uuid','topologia_uid','algoritmo','data_utc','fontes','parametros','associacoes')}
        if 'interrupcao' in d:meta['interrupcao']=d['interrupcao']
        (p/'execucao.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
        verificar_cancelamento(cancelar)
        p.rename(destino)
    return destino
