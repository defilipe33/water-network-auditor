"""Materialização verificável da fotografia GIS em Pipes e Junctions."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from qgis.core import QgsCoordinateReferenceSystem

from auditoria_fronteiras.entradas import digest
from auditoria_fronteiras.modelos import verificar_cancelamento
from .investigacao_gis import geometria


def preparar(foto,cancelar=None):
    crs = QgsCoordinateReferenceSystem(foto['crs'])
    from auditoria_fronteiras import Parametros
    from auditoria_fronteiras.entradas import crs_processamento
    crs_processamento(Parametros(crs=crs.toWkt()))
    tubos = {t['uid']:t for t in foto['tubos']}
    nos = {n['uid']:n for n in foto['nos']}
    if len(tubos)!=len(foto['tubos']) or len(nos)!=len(foto['nos']):
        raise ValueError('Identidades duplicadas na topologia de origem.')
    divisoes = {}
    for n in nos.values():
        verificar_cancelamento(cancelar)
        for uid,p in n['portas']:
            if uid!='J' and 0<p<1:
                divisoes.setdefault(uid,[]).append((p,n['uid']))
    saida, ids, problemas = [], set(), []
    for e in foto['arestas']:
        verificar_cancelamento(cancelar)
        u = e['tubo']
        if u not in tubos or e['a'] not in nos or e['b'] not in nos:
            raise ValueError('Aresta sem Pipe ou Junction correspondente.')
        t = tubos[u]
        g = geometria(t.get('wkb'))
        inicio,fim = e['inicio'],e['fim']
        if not g or g.isEmpty() or not 0<=inicio<fim<=1:
            raise ValueError('Segmento sem geometria ou com intervalo inválido.')
        if (inicio,fim)!=(0.,1.):
            g = type(g)(g.constGet().curveSubstring(inicio*g.length(),fim*g.length()))
        chave = digest(['segmento_gis',u,inicio,fim])
        comprimento = g.length()
        if chave in ids or not comprimento>1e-8:
            raise ValueError('Segmento duplicado ou de comprimento nulo.')
        ids.add(chave)
        ps = g.asPolyline()
        from qgis.core import QgsPointXY
        deslocamento = max(p.distance(QgsPointXY(*nos[uid]['xy'])) for p,uid in ((ps[0],e['a']),(ps[-1],e['b'])))
        if deslocamento>1e-6:
            problemas.append(dict(segmento=chave,deslocamento_m=deslocamento,
                                  motivo='Ponta geométrica e nó topológico têm coordenadas distintas.'))
        saida.append(dict(uid=chave,original=t.get('feicao') or u,parte=u,gis_id=t.get('id'),no_a=e['a'],no_b=e['b'],
            inicio=inicio,fim=fim,comprimento_m=comprimento,diametro_mm=t.get('diametro_mm'),
            material=t.get('material'),fontes=t.get('fontes',[]),proposta=t.get('proposta_uid'),
            natureza='PROPOSTA' if t.get('proposta_uid') else 'DIVISAO_VIRTUAL' if u in divisoes else 'CADASTRO',
            wkb=bytes(g.asWkb())))
    return saida,list(nos.values()),divisoes,problemas


def exportar(foto,pasta,cancelar=None,etapa=lambda *_:None):
    from osgeo import ogr,osr
    etapa(0,'Materializando os segmentos e conferindo suas conexões')
    tubos,nos,divisoes,problemas=preparar(foto,cancelar)
    epsg=osr.SpatialReference()
    if epsg.ImportFromWkt(foto['crs'])!=0:
        raise ValueError('CRS de exportação inválido.')
    destino=Path(pasta)/('Topologia_previa_'+foto['uuid'][:8]+'_'+uuid4().hex[:8])
    with TemporaryDirectory(prefix='.topologia_',dir=pasta) as temp:
        saida=Path(temp)/'saida'
        saida.mkdir()
        ds=ogr.GetDriverByName('GPKG').CreateDataSource(str(saida/'topologia.gpkg'))
        if not ds:raise OSError('Não foi possível criar o GeoPackage da prévia.')
        configs = (
            ('pipes',ogr.wkbLineString,('uid','original','parte','gis_id','no_a','no_b','inicio','fim',
              'comprimento_m','diametro_mm','material','fontes','proposta','natureza'),tubos),
            ('junctions',ogr.wkbPoint,('uid','natureza','portas'),nos),
        )
        for nome,tipo,colunas,linhas in configs:
            camada=ds.CreateLayer(nome,epsg,tipo)
            if camada is None:raise OSError('Não foi possível criar '+nome)
            for campo in colunas:
                real=campo in ('inicio','fim','comprimento_m','diametro_mm')
                if camada.CreateField(ogr.FieldDefn(campo,ogr.OFTReal if real else ogr.OFTString))!=0:
                    raise OSError('Não foi possível criar o campo '+campo)
            if camada.StartTransaction()!=0:raise OSError('O GeoPackage não iniciou a transação.')
            for r in linhas:
                verificar_cancelamento(cancelar)
                f=ogr.Feature(camada.GetLayerDefn())
                for k in colunas:
                    valor=r.get(k)
                    if valor is not None:
                        f.SetField(k,json.dumps(valor,ensure_ascii=False) if isinstance(valor,list) else
                                     str(valor) if k=='gis_id' else valor)
                if nome=='pipes':g=ogr.CreateGeometryFromWkb(r['wkb'])
                else:
                    g=ogr.Geometry(ogr.wkbPoint)
                    g.AddPoint_2D(*r['xy'])
                f.SetGeometry(g)
                if camada.CreateFeature(f)!=0:raise OSError('Falha ao escrever '+nome)
            if camada.CommitTransaction()!=0:raise OSError('Falha ao confirmar '+nome)
        f=camada=ds=None
        validar=dict(execucao=foto['uuid'],projeto=foto['projeto_uid'],hipotese=foto.get('hipotese'),
            algoritmo=foto['algoritmo'],crs=foto['crs'],unidades={'comprimento':'m','diametro':'mm'},
            contagens={'pipes':len(tubos),'junctions':len(nos)},divisoes=divisoes,pendencias=problemas,
            conexoes=foto.get('resolucoes_conexoes',{}),
            finalidade='Prévia de topologia GIS para conferência. Revisar pendências e campos antes de importar.')
        (saida/'validacao.json').write_text(json.dumps(validar,ensure_ascii=False,indent=2),encoding='utf-8')
        verificar_cancelamento(cancelar)
        saida.rename(destino)
    return destino
