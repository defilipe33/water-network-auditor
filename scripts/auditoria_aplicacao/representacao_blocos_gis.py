"""Camadas e saídas autônomas de blocos, com relações por segmento."""

import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from qgis.PyQt.QtCore import QVariant
from qgis.core import (QgsCategorizedSymbolRenderer, QgsFeature, QgsField, QgsGeometry, QgsLineSymbol,
                        QgsProject, QgsRendererCategory, QgsVectorLayer)

from auditoria_fronteiras.modelos import verificar_cancelamento
from auditoria_fronteiras.organizacao_camadas import publicar as publicar_camada


CAMADA='Blocos topológicos de abastecimento'
CORES=('#1976a4','#d27724','#8665ad','#267d59','#a94d6c','#296766','#a82532')


def registros(geo,blocos,cancelar=None):
    linhas=[]
    for b in blocos:
        verificar_cancelamento(cancelar)
        gs = [g for i in b['segmentos'] if (g:=geo.trecho(i))]
        if gs:linhas.append((b,bytes(QgsGeometry.collectGeometry(gs).asWkb())))
    return linhas


def publicar(d,crs,linhas):
    projeto=QgsProject.instance()
    existente=next((c for c in projeto.mapLayers().values() if c.customProperty('wna/uid')==d['uuid']
                    and c.customProperty('wna/tecnico')==CAMADA),None)
    c=existente if existente is not None else QgsVectorLayer('MultiLineString',CAMADA,'memory')
    p=c.dataProvider()
    if existente is None:
        c.setCrs(crs)
        c.setCustomProperty('skipMemoryLayersCheck',1)
        p.addAttributes([QgsField(k,QVariant.String) for k in ('UUID','Nome','Tipo','Origens')])
        c.updateFields()
        c.setReadOnly(True)
    else:p.truncate()
    fs,simbolos = [], []
    usadas={}
    for i,(b,wkb) in enumerate(linhas):
        ocupadas=set().union(*(usadas.get(n,set()) for n in b['fronteiras']))
        cor=next((u for u in CORES if u not in ocupadas),CORES[i%len(CORES)])
        for n in b['fronteiras']:usadas.setdefault(n,set()).add(cor)
        s=QgsLineSymbol.createSimple(dict(line_color=cor,line_width='0.78',line_style='solid' if b['tipo']=='MALHA' else 'dash'))
        simbolos.append(QgsRendererCategory(b['uid'],s,b['nome']))
        g=QgsGeometry()
        g.fromWkb(wkb)
        f=QgsFeature(c.fields())
        f.setAttributes([b['uid'],b['nome'],b['tipo'],', '.join(b['origens'])])
        f.setGeometry(g)
        fs.append(f)
    if not p.addFeatures(fs)[0]:raise ValueError('Falha ao representar os blocos.')
    c.setRenderer(QgsCategorizedSymbolRenderer('UUID',simbolos))
    c.updateExtents()
    c.triggerRepaint()
    return c if existente is not None else publicar_camada(c,projeto,'estrutura',d['uuid'],nome=d['nome'])


def exportar(d,geo,blocos,pasta,formato,cancelar=None):
    from osgeo import ogr,osr
    if formato not in ('GeoPackage','Shapefile','CSV'):
        raise ValueError('Escolha um formato de exportação válido.')
    destino=Path(pasta)/('Blocos_'+d['uuid'][:8]+'_'+uuid4().hex[:8])
    with TemporaryDirectory(prefix='.blocos_',dir=pasta) as tmp:
        saida=Path(tmp)/'saida'
        saida.mkdir()
        with (saida/'segmentos.csv').open('x',encoding='utf-8-sig',newline='') as arq:
            w=csv.writer(arq)
            w.writerow(('bloco','parte','pipe','id_gis','no_a','no_b','inicio','fim','comprimento_m','proposta'))
            for b in blocos:
                for i in b['segmentos']:
                    verificar_cancelamento(cancelar)
                    e=geo.arestas[i]
                    t=geo.partes[e['tubo']]
                    w.writerow((b['uid'],t['uid'],t.get('feicao',t['uid']),t.get('id'),e['a'],e['b'],
                                e['inicio'],e['fim'],e['comprimento_m'],t.get('proposta_uid')))
        ids={b['uid'] for b in blocos}
        metadados=dict(investigacao=d['uuid'],projeto=d['projeto_uid'],execucao=d['topologia_uid'],
            hipotese=d.get('hipotese'),crs=d['foto']['crs'],algoritmo=d['blocos']['algoritmo'],
            detalhe=d['blocos']['detalhe'],criterio=d['blocos']['criterio'],blocos=blocos,
            ligacoes=[a for a in d['blocos']['ligacoes'] if ids.intersection(a['blocos'])])
        (saida/'blocos.json').write_text(json.dumps(metadados,ensure_ascii=False,indent=2),encoding='utf-8')
        if formato!='CSV':
            gpkg=formato=='GeoPackage'
            srs=osr.SpatialReference()
            if srs.ImportFromWkt(geo.crs.toWkt())!=0:raise ValueError('CRS exportado inválido.')
            ds=ogr.GetDriverByName('GPKG' if gpkg else 'ESRI Shapefile').CreateDataSource(
                str(saida/('blocos.gpkg' if gpkg else 'blocos.shp')))
            if ds is None:raise OSError('Falha ao criar a saída espacial.')
            try:
                l=ds.CreateLayer('blocos',srs,ogr.wkbMultiLineString,options=[] if gpkg else ['ENCODING=UTF-8'])
                if l is None:raise OSError('Falha ao criar a camada de blocos.')
                for k,t in [('UUID',ogr.OFTString),('NOME',ogr.OFTString),('TIPO',ogr.OFTString),('COMP_M',ogr.OFTReal)]:
                    f=ogr.FieldDefn(k,t)
                    if t==ogr.OFTString:f.SetWidth(100)
                    if l.CreateField(f)!=0:raise OSError('Falha ao criar '+k)
                for b,wkb in registros(geo,blocos,cancelar):
                    f=ogr.Feature(l.GetLayerDefn())
                    for i,valor in enumerate((b['uid'],b['nome'],b['tipo'],b['comprimento_m'])):
                        f.SetField(i,valor)
                    f.SetGeometry(ogr.CreateGeometryFromWkb(wkb))
                    if l.CreateFeature(f)!=0:raise OSError('Falha ao gravar o bloco.')
            finally:
                # O Windows exige que o escritor libere o arquivo antes de publicar a pasta.
                f=l=None
                ds.Destroy()
                ds=None
        verificar_cancelamento(cancelar)
        saida.rename(destino)
    return destino
