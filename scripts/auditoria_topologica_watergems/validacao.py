"""Evidências de correspondência; não altera topologia nem geometrias brutas."""
from collections import defaultdict,Counter
from math import dist
from statistics import median
from qgis.core import QgsGeometry,QgsSpatialIndex,QgsFeature,QgsRectangle


def erro_vertices(wkb,gis,fator):
    g=QgsGeometry();g.fromWkb(bytes(wkb))
    a=[(v.x()*fator,v.y()*fator) for v in g.vertices()]
    b=[(v.x(),v.y()) for v in gis.vertices()]
    if not a or len(a)!=len(b):return None
    return min(max(dist(x,y) for x,y in zip(a,b)),max(dist(x,y) for x,y in zip(a,reversed(b))))


def provar_correspondencia(modelo,registros_gis,fator,tolerancia):
    """registros: uid, chave_cadastral, geometria, origem. Mapeamento explícito.

    Critério: chave única em AMBAS fontes + todos os vértices XY compatíveis.
    Os rótulos não substituem DomainElementID e a identidade GIS nunca é descartada.
    """
    wg=defaultdict(list);gis=defaultdict(list)
    for i,e in modelo['elementos'].items():
        if e['familia']=='LINK' and e['excluido'] is False:wg[e['label']].append(i)
    for r in registros_gis:gis[r['chave_cadastral']].append(r['uid'])
    saida=[];erros=[]
    for r in registros_gis:
        chave=r['chave_cadastral'];candidatos=wg.get(chave,[]) if chave is not None else []
        codigo='NAO_ENCONTRADA';erro=None
        if chave is None or not str(chave).strip():codigo='INCONSISTENTE'
        elif not candidatos:codigo='NAO_ENCONTRADA'
        elif len(candidatos)>1 or len(gis[chave])>1:codigo='MULTIPLAS_CANDIDATAS'
        elif candidatos:
            e=modelo['elementos'][candidatos[0]]
            if e['geometria']:
                erro=erro_vertices(e['geometria'],r['geometria'],fator)
            codigo='INEQUIVOCA' if erro is not None and erro<=tolerancia else 'INCONSISTENTE'
            if erro is not None:erros.append(erro)
        nos=[]
        for i in candidatos:
            t=modelo['elementos'][i]['topologia']
            nos.append(dict(tubo=i,inicio=t.get('HMITopologyStartNodeID'),fim=t.get('HMITopologyStopNodeID')))
        saida.append(dict(gis_uid=r['uid'],origem=r['origem'],chave_cadastral=chave,
            situacao=codigo,candidatos=candidatos,erro_xy_m=erro,nos=nos,
            indicadores=['CHAVE_GIS_REPETIDA'] if len(gis[chave])>1 else []))
    evidencia=dict(fator=fator,tolerancia_m=tolerancia,pares_com_vertices_comparaveis=len(erros),
        pares_ate_tolerancia=sum(e<=tolerancia for e in erros),
        mediana_m=median(erros) if erros else None,maximo_m=max(erros) if erros else None,
        contagens=dict(Counter(r['situacao'] for r in saida)),
        criterio='Label WaterGEMS ↔ campo GIS explicitamente mapeado; unicidade bilateral e todos os vértices XY')
    return saida,evidencia


def associar_dossie(dossie,correspondencias):
    por_gis={r['gis_uid']:r for r in correspondencias}
    eventos=defaultdict(list)
    for r in dossie['evento_rede']:
        if r['tubo_uid'] in por_gis:eventos[r['evento_uid']].append(por_gis[r['tubo_uid']])
    resultado=[]
    for r in dossie['local_evento']:
        for c in eventos[r['evento_uid']]:
            resultado.append(dict(local_uid=r['local_uid'],evento_uid=r['evento_uid'],
                gis_uid=c['gis_uid'],situacao=c['situacao'],candidatos=c['candidatos'],nos=c['nos']))
    return resultado


def geometrias_jusante(modelo,registros):
    """Coincidências em unidades BRUTAS; não há cálculo em metros nem novo vínculo."""
    el=modelo['elementos'];index=QgsSpatialIndex();geoms={}
    for k,(i,e) in enumerate((i,e) for i,e in el.items() if e['familia']=='LINK' and e['excluido'] is False):
        if not e['geometria']:continue
        g=QgsGeometry();g.fromWkb(e['geometria'])
        if g.isNull() or g.isEmpty():continue
        f=QgsFeature(k);f.setGeometry(g);index.addFeature(f);geoms[k]=(i,g)
    for r in registros:
        e=el[r['id']];r['candidatos_geometricos']=[]
        if not e['geometria']:continue
        g=QgsGeometry();g.fromWkb(e['geometria'])
        if g.isNull() or g.isEmpty():continue
        caixa=QgsRectangle(g.boundingBox());caixa.grow(1e-7)
        for k in index.intersects(caixa):
            i,t=geoms[k];d=g.distance(t)
            if 0<=d<=1e-7:r['candidatos_geometricos'].append(dict(link=i,distancia_bruta=d))
        r['geometria_status']='COINCIDENCIAS_BRUTAS_APENAS_HIPOTESE'
        r['hipotese_geometrica']=bool(r['candidatos_geometricos'])
    return registros
