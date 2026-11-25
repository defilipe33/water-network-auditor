"""Exporta uma fotografia da execução para camadas GIS e inventário tabular."""

from contextlib import closing
import csv
from pathlib import Path
import sqlite3
from uuid import uuid4

from auditoria_fronteiras.modelos import verificar_cancelamento

from .analise_modelo_gis import publicar
from .persistencia_grafo_gis import _verificar


def exportar(d, pasta, formato, cancelar=None, etapa=lambda *_:None):
    from osgeo import ogr, osr
    if formato not in ('GPKG','ESRI Shapefile'):
        raise ValueError('Formato de exportação desconhecido.')
    pasta=Path(pasta)
    destino=pasta/f"Topologia_{d['uuid'][:8]}_{uuid4().hex[:8]}"
    temp=destino.with_name('.preparando_'+destino.name)
    temp.mkdir()
    srs=osr.SpatialReference()
    if srs.ImportFromWkt(d['crs'])!=0:
        raise ValueError('CRS da execução não pôde ser exportado.')
    gpkg=None
    if formato=='GPKG':
        gpkg=ogr.GetDriverByName(formato).CreateDataSource(str(temp/'topologia.gpkg'))
        if gpkg is None:raise OSError('Não foi possível criar o GeoPackage.')
    campos=('UID','COMP_UID','TIPO','REF_GIS','METROS','DIAM_MM')

    def camada(nome,tipo,linhas):
        etapa(0,'Exportando '+nome)
        ds=gpkg if gpkg is not None else ogr.GetDriverByName(formato).CreateDataSource(str(temp/(nome+'.shp')))
        if ds is None:raise OSError('Não foi possível criar '+nome)
        ly=ds.CreateLayer(nome,srs,tipo,options=['ENCODING=UTF-8'] if gpkg is None else [])
        if ly is None:raise OSError('Não foi possível criar a camada '+nome)
        for i,c in enumerate(campos):
            campo=ogr.FieldDefn(c,ogr.OFTReal if i>=4 else ogr.OFTString)
            if i<4:campo.SetWidth(160 if i==3 else 48)
            if ly.CreateField(campo)!=0:raise OSError('Não foi possível criar o campo '+c)
        for valores,geom in linhas:
            verificar_cancelamento(cancelar)
            f=ogr.Feature(ly.GetLayerDefn())
            for i,v in enumerate(valores):
                if v is not None:f.SetField(i,v)
            f.SetGeometry(geom)
            if ly.CreateFeature(f)!=0:raise OSError('Falha ao gravar uma feição em '+nome)
        ly=None
        ds=None

    comp={t:g['uid'] for g in d['componentes'] for t in g['tubos']}
    camada('tubulacoes',ogr.wkbLineString,
           (((t['uid'],comp[t['uid']],t.get('classificacao'),str(t['id']) if t.get('id') is not None else None,
              t['comprimento_m'],t.get('diametro_mm')),ogr.CreateGeometryFromWkb(bytes.fromhex(t['wkb']))) for t in d['tubos']))
    def ponto(xy):
        g=ogr.Geometry(ogr.wkbPoint)
        g.AddPoint_2D(*xy)
        return g
    nos={n:g['uid'] for g in d['componentes'] for n in g['nos']}
    camada('nos',ogr.wkbPoint,(((n['uid'],nos[n['uid']],n['natureza']),ponto(n['xy'])) for n in d['nos']))
    for nome,tipo,exigir_linha in [('diagnosticos',ogr.wkbPoint,False),('sobreposicoes',ogr.wkbLineString,True)]:
        camada(nome,tipo,(((r['uid'],r.get('componente'),r['tipo']),ogr.CreateGeometryFromWkb(bytes.fromhex(r['wkb'])))
                           for r in d['diagnosticos'] if r.get('wkb')
                           and (r['tipo']=='SOBREPOSICAO')==exigir_linha and r.get('equipamento') is None))
    gpkg=None
    if formato=='GPKG':
        with closing(sqlite3.connect(temp/'topologia.gpkg')) as con:_verificar(con)
    with (temp/'componentes.csv').open('x',newline='',encoding='utf-8-sig') as f:
        escritor=csv.writer(f)
        escritor.writerow(['UID','Tubulações','Nós','Comprimento (m)','Maior diâmetro (mm)','Origens','Situação'])
        for g in d['componentes']:
            verificar_cancelamento(cancelar)
            escritor.writerow([g['uid'],g['quantidade_tubos'],len(g['nos']),g['comprimento_m'],g['max_mm'],
                                ' '.join(g['origens']),g['situacao']])
    with (temp/'diagnosticos.csv').open('x',newline='',encoding='utf-8-sig') as f:
        escritor=csv.writer(f);escritor.writerow(['ID','Tipo','Situação','Componente','Tubulações','Distância (m)','Motivo'])
        for r in d['diagnosticos']:
            verificar_cancelamento(cancelar)
            escritor.writerow([r['uid'],r['tipo'],r['situacao'],r.get('componente'),' '.join(r['tubos']),
                               r.get('distancia_m'),r.get('motivo','')])
    verificar_cancelamento(cancelar)
    temp.rename(destino)
    return destino
