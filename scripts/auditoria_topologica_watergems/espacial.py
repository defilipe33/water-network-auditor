"""Candidatos espaciais em CRS/unidade explicitamente confirmados pelo usuário."""
from math import isfinite
from qgis.core import (QgsGeometry,QgsSpatialIndex,QgsFeature,QgsRectangle,
                       QgsCoordinateReferenceSystem,QgsUnitTypes)


def geometrias(modelo, crs, fator, fonte_confirmacao):
    referencia=QgsCoordinateReferenceSystem(crs)
    if not referencia.isValid() or referencia.isGeographic() or referencia.mapUnits()!=QgsUnitTypes.DistanceMeters:
        raise ValueError('Informe CRS projetado em metros; CRS original não é deduzido de coordenadas')
    if not isfinite(fator) or fator<=0 or not fonte_confirmacao.strip():
        raise ValueError('Confirme o fator unidade bruta → metro e registre a fonte dessa confirmação')
    saida={};avisos=[]
    for i,e in modelo['elementos'].items():
        if e['excluido'] is not False or not e['geometria']: continue
        g=QgsGeometry()
        g.fromWkb(bytes(e['geometria']))
        if g.isNull() or g.isEmpty():
            avisos.append(dict(codigo='GEOMETRIA_INVALIDA',id=i));continue
        from qgis.PyQt.QtGui import QTransform
        g.transform(QTransform.fromScale(fator,fator))
        saida[i]=g
    return saida,avisos


def candidatos(modelo, geoms, distancia, cruzamentos=True):
    if not isfinite(distancia) or distancia<0: raise ValueError('Distância deve ser não negativa')
    nos={i:g for i,g in geoms.items() if modelo['elementos'][i]['familia'] in ('NO','DISPOSITIVO')}
    indices=QgsSpatialIndex();feicoes={};chaves={}
    for k,(i,g) in enumerate(nos.items()):
        f=QgsFeature(k);f.setGeometry(g);indices.addFeature(f);feicoes[k]=i;chaves[i]=k
    arestas=set()
    for e in modelo['elementos'].values():
        if e['excluido'] is not False or e['familia']!='LINK': continue
        t=e['topologia'];arestas.add(frozenset((t.get('HMITopologyStartNodeID'),t.get('HMITopologyStopNodeID'))))
    saida=[]
    for i,g in nos.items():
        r=QgsRectangle(g.boundingBox());r.grow(distancia)
        for k in indices.intersects(r):
            j=feicoes[k]
            if j<=i or frozenset((i,j)) in arestas: continue
            d=g.distance(nos[j])
            if 0<=d<=distancia:
                saida.append(dict(codigo='PROXIMOS_SEM_LINK_DIRETO',id=i,relacionado=j,distancia=d,
                    descricao='Candidato espacial; não prova conexão ausente nem necessidade de intervenção'))
    if cruzamentos:
        tubos={i:g for i,g in geoms.items() if modelo['elementos'][i]['familia']=='LINK'}
        idx=QgsSpatialIndex();lookup={}
        for k,(i,g) in enumerate(tubos.items()):
            f=QgsFeature(k);f.setGeometry(g);idx.addFeature(f);lookup[k]=i
        for i,g in tubos.items():
            t=modelo['elementos'][i]['topologia'];ext={t.get('HMITopologyStartNodeID'),t.get('HMITopologyStopNodeID')}-{None}
            for k in idx.intersects(g.boundingBox()):
                j=lookup[k]
                if j<=i: continue
                u=modelo['elementos'][j]['topologia'];out={u.get('HMITopologyStartNodeID'),u.get('HMITopologyStopNodeID')}-{None}
                if ext & out: continue
                if g.intersects(tubos[j]):
                    saida.append(dict(codigo='INTERSECAO_SEM_NO_COMUM',id=i,relacionado=j,distancia=0,
                        descricao='Interseção espacial sem nó comum direto; pode existir outro caminho no grafo'))
    return saida
