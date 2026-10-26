"""Integração versionada por referência, sem alterar as execuções de origem."""
from collections import defaultdict,Counter
from copy import deepcopy
from datetime import datetime,timezone
import json
from math import isfinite
from pathlib import Path
from uuid import uuid4
from qgis.core import QgsGeometry,QgsVectorLayer,QgsCoordinateTransform,QgsCoordinateReferenceSystem,QgsProject
from auditoria_fronteiras.persistencia import carregar_execucao
from auditoria_fronteiras.versoes import abrir_ro,validar_base
from auditoria_fronteiras.entradas import digest,valor_python
from .arquivos import hash_arquivo
from .contexto_integrado import carregar_topologica,geometrias_no_crs,contexto_espacial,ler_areas
from .investigacao import inventariar_componentes,integrar_locais,VERSAO_REGRAS,checar_cancelamento


def geometria_gis_preservada(dossie,selecionados,crs):
    refs={t['uid']:t for t in dossie['tubulacoes'] if t['uid'] in selecionados}
    por_origem=defaultdict(list);geoms={};avisos=[]
    for t in refs.values():por_origem[t['origem']].append(t)
    fontes={f['origem']:f for f in dossie['contexto']['fontes']}
    for origem,ts in por_origem.items():
        fonte=fontes[origem];c=QgsVectorLayer(fonte['fonte'],fonte['camada'],fonte['provedor'])
        if not c.isValid():avisos.append('Fonte GIS ausente: '+fonte['camada']);continue
        procuradas={t['uid'].rsplit('_',1)[0] for t in ts};candidatas=defaultdict(list)
        for f in c.getFeatures():
            attrs={v.name():valor_python(f[v.name()]) for v in c.fields()}
            chave=digest([origem,attrs,bytes(f.geometry().asWkb()).hex()])
            if chave in procuradas:candidatas[chave].append(QgsGeometry(f.geometry()))
        transformacao=QgsCoordinateTransform(c.crs(),QgsCoordinateReferenceSystem(crs),QgsProject.instance().transformContext())
        for t in ts:
            gs=candidatas[t['uid'].rsplit('_',1)[0]]
            if len(gs)!=1:
                avisos.append('Geometria GIS ausente/alterada/ambígua: '+t['uid']);continue
            g=gs[0]
            if c.crs().authid()!=crs:g.transform(transformacao)
            geoms[t['uid']]=g
    return geoms,avisos


def preparar(geo_gpkg,geo_uid,topo_json,topo_gpkg,limiar=5,areas_config=(),restricoes=(),cancelar=None,topologia_pronta=None):
    if not isfinite(limiar) or limiar<0:raise ValueError('Distância investigativa deve ser finita e não negativa')
    validar_base(geo_gpkg);origem_geo=Path(geo_gpkg).resolve()
    hash_geo=hash_arquivo(origem_geo)
    with abrir_ro(origem_geo) as con:d=carregar_execucao(origem_geo,geo_uid,conexao=con)
    t=topologia_pronta if topologia_pronta is not None else carregar_topologica(topo_json,topo_gpkg,cancelar)
    crs=d['contexto']['parametros']['crs'];geoms=geometrias_no_crs(t,crs)
    if areas_config and geoms is None:raise ValueError('Contexto de áreas bloqueado: referência espacial topológica não validada')
    areas,fontes_areas=ler_areas(areas_config,crs) if areas_config else ([],[])
    estruturas=t['estrutural'];potencial=t['potencial'];m=t['modelo']
    inventario,membros,fontes=inventariar_componentes(m,estruturas,cancelar)
    inv_pot,mem_pot,fontes_pot=inventariar_componentes(m,potencial,cancelar)
    vizinhos=contexto_espacial(inventario,geoms,areas,cancelar)
    # Corresponder por UID técnico validado, nunca apenas por número cadastral.
    cadastradas={r['gis_uid']:r for r in t['persistido']['resultado'].get('associacoes',[])}
    associacoes=[];pendencias=[]
    for tubo in d['tubulacoes']:
        a=deepcopy(cadastradas.get(tubo['uid'],dict(gis_uid=tubo['uid'],origem=tubo['origem'],situacao='NAO_ENCONTRADA',candidatos=[],erro_xy_m=None,nos=[])))
        a['motivos']=[]
        if a.get('origem')!=tubo['origem'] or any(i not in m['elementos'] or m['elementos'][i]['familia']!='LINK' for i in a['candidatos']):
            a['situacao']='INCONSISTENTE';a['motivos'].append('Identidade/origem topológica incompatível')
        if a['situacao']!='INEQUIVOCA':
            if a.get('erro_xy_m') is not None:a['motivos'].append('Vértices GIS/WaterGEMS divergem: '+repr(a['erro_xy_m'])+' m')
            elif a['candidatos']:a['motivos'].append('Candidatos cadastrais múltiplos/não validados')
            else:a['motivos'].append('Sem candidato WaterGEMS validado para esta identidade GIS')
            if a.get('indicadores'):a['motivos']+=a['indicadores']
            pendencias.append(dict(gis_uid=tubo['uid'],origem=tubo['origem'],camada=tubo['camada'],id_bruto=tubo['id_bruto'],
                id_exibido=tubo['id_exibido'],atributos_originais=tubo['atributos'],situacao=a['situacao'],
                chave_correlacao=a.get('chave_cadastral'),candidatos=a['candidatos'],erro_xy_m=a.get('erro_xy_m'),
                motivos=a['motivos'],eventos=[],locais=[],geometria_status='PENDENTE',geometria_wkb=None))
        associacoes.append(a)
    if not cadastradas:t['modelo']['avisos'].append('Execução topológica sem prova GIS validada; correspondências ficam pendentes')
    pend_geo,avisos=geometria_gis_preservada(d,{r['gis_uid'] for r in pendencias},crs)
    evloc=defaultdict(set);evgis=defaultdict(set)
    for r in d['local_evento']:evloc[r['evento_uid']].add(r['local_uid'])
    for r in d['evento_rede']:evgis[r['tubo_uid']].add(r['evento_uid'])
    for p in pendencias:
        p['eventos']=sorted(evgis[p['gis_uid']]);p['locais']=sorted({u for e in p['eventos'] for u in evloc[e]})
        g=pend_geo.get(p['gis_uid'])
        if g is not None:p['geometria_status']='ORIGEM_VERIFICADA_POR_ASSINATURA';p['geometria_wkb']=bytes(g.asWkb()).hex()
    locais,pares=integrar_locais(d,m,estruturas,potencial,associacoes,geoms,limiar,restricoes,cancelar)
    for l in locais:
        ponto=QgsGeometry.fromWkt(f"POINT({l['registro']['X']} {l['registro']['Y']})")
        l['areas']=[a['uid'] for a in areas if ponto.intersects(a['geometria'])] if geoms is not None else []
    # Complemento de associações do mesmo pacote; nunca gera uma nova associação.
    comp_por_tubo={i:c['uid'] for c in inventario for i in c['tubos']};assoc_comp=[]
    prova=Path(topo_json).parent/'ASSOCIACOES_GIS_COMPLETAS.json'
    origem_prova=None
    if prova.is_file():
        origem_prova=dict(arquivo=str(prova.resolve()),sha256=hash_arquivo(prova),natureza='PROVA_COMPLEMENTAR_DO_MESMO_PACOTE')
        fontes_conhecidas={f['origem'] for f in d['contexto']['fontes']}
        for a in json.loads(prova.read_text(encoding='utf8')):
            if a['situacao']=='INEQUIVOCA' and a['origem'] in fontes_conhecidas and len(a['candidatos'])==1 and a['candidatos'][0] in comp_por_tubo:
                assoc_comp.append(dict(comp_uid=comp_por_tubo[a['candidatos'][0]],wg_id=a['candidatos'][0],gis_uid=a['gis_uid'],origem=a['origem'],chave=a.get('chave_cadastral'),situacao=a['situacao']))
    else:
        for a in associacoes:
            if a['situacao']=='INEQUIVOCA' and len(a['candidatos'])==1 and a['candidatos'][0] in comp_por_tubo:
                assoc_comp.append(dict(comp_uid=comp_por_tubo[a['candidatos'][0]],wg_id=a['candidatos'][0],gis_uid=a['gis_uid'],origem=a['origem'],chave=a.get('chave_cadastral'),situacao=a['situacao']))
    por_comp=defaultdict(set)
    for a in assoc_comp:por_comp[a['comp_uid']].add(a['wg_id'])
    for c in inventario:c['n_tubos_gis_validados']=len(por_comp[c['uid']]);c['cobertura_gis']='PROVA_COMPLEMENTAR' if origem_prova else 'SOMENTE_TUBOS_DO_DOSSIE'
    manual=[]
    for c in inventario:
        if c['n_tubos']<=1 or not c['reservatorios'] and not c['tanques']:
            for i in (c['nos']+c['tubos'])[:3]:
                e=m['elementos'][i];manual.append(dict(tipo='COMPONENTE',comp_uid=c['uid'],local_uid=None,wg_id=i,label=e['label'],
                    esperado=f"{c['porte']}; {c['n_tubos']} tubos; sem caminho cadastrado até fonte: {not c['caminho_estrutural_ate_fonte']}"))
    for r in estruturas['auditoria_jusantes']:
        if r['jusante'] is None:manual.append(dict(tipo='JUSANTE_NAO_INFORMADO',comp_uid=None,local_uid=None,wg_id=r['id'],label=r['label'],esperado='Campo Downstream nulo; não preencher por proximidade'))
    for p in pares:
        if p['modo']=='ESTRUTURAL' and 'POSSIVEL_CONEXAO_AUSENTE' in p['classes']:
            for i in p['wg_a']+p['wg_b']:manual.append(dict(tipo='CONTINUIDADE_GEOMETRICA',comp_uid=None,local_uid=p['local_uid'],wg_id=i,label=m['elementos'][i]['label'],esperado='Continuidade geométrica, componentes distintos; conferir sem conectar automaticamente'))
    for p in pendencias:
        for i in p['candidatos'] or [None]:manual.append(dict(tipo='CORRESPONDENCIA_GIS',comp_uid=None,local_uid=None,wg_id=i,label=m['elementos'][i]['label'] if i is not None else None,esperado='Conferir '+p['gis_uid']+' / '+p['camada']+'; '+ '; '.join(p['motivos'])))
    meta=dict(uid=str(uuid4()),versao=1,regras=VERSAO_REGRAS,data=datetime.now(timezone.utc).isoformat(),
        nome='Investigação integrada',geo=dict(base=str(origem_geo),execucao_uid=geo_uid,sha256=hash_geo),topologia=t['origem'],
        parametros=dict(distancia_investigativa_m=limiar,restricoes=deepcopy(list(restricoes)),crs=crs,espacial_habilitado=geoms is not None),
        fontes_contexto=fontes_areas,prova_complementar=origem_prova)
    resultado=dict(meta=meta,componentes=inventario,membros=membros,fontes=fontes,vizinhos=vizinhos,
        componentes_potenciais=inv_pot,membros_potenciais=mem_pot,fontes_potenciais=fontes_pot,
        associacoes_componentes=assoc_comp,pendencias=pendencias,locais=locais,pares=pares,manual=manual,avisos=avisos,
        resumo=dict(componentes=len(inventario),portes=dict(Counter(c['porte'] for c in inventario)),
            locais=len(locais),pares=len(pares),pendencias_gis=len(pendencias),
            classes={modo:dict(Counter(l['perspectivas'][modo]['classe'] for l in locais)) for modo in ('ESTRUTURAL','TODAS_VALVULAS_ABERTAS')}))
    if hash_arquivo(origem_geo)!=hash_geo:raise RuntimeError('Base geométrica mudou durante a integração; não publicar')
    if hash_arquivo(t['origem']['json'])!=t['origem']['json_sha256'] or hash_arquivo(t['origem']['gpkg'])!=t['origem']['gpkg_sha256']:
        raise RuntimeError('Execução topológica mudou durante a integração; não publicar')
    return dict(dossie=d,topologia=t,resultado=resultado,geometrias=geoms,areas=areas)
