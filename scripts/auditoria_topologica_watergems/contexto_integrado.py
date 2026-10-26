"""Recuperação de execuções persistidas e contexto espacial em cópias de memória."""
from collections import Counter,defaultdict
from copy import deepcopy
import json
from pathlib import Path
from qgis.core import (QgsVectorLayer,QgsGeometry,QgsSpatialIndex,QgsFeature,QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,QgsProject,QgsUnitTypes)
from .topologia import analisar
from .arquivos import hash_arquivo
from .investigacao import checar_cancelamento
from auditoria_fronteiras.entradas import valor_python


def carregar_topologica(json_origem,gpkg_origem,cancelar=None):
    p=Path(json_origem).resolve(strict=True);gpkg=Path(gpkg_origem).resolve(strict=True)
    hash_json=hash_arquivo(p);hash_gpkg=hash_arquivo(gpkg)
    dados=json.loads(p.read_text(encoding='utf-8'))
    if dados['resultado']['resumo']['modo']!='ESTRUTURAL':raise ValueError('Selecione a execução ESTRUTURAL; a hipótese é reconstruída separadamente')
    if not dados.get('execucao_uid'):raise ValueError('Execução topológica sem identificador técnico')
    m=deepcopy(dados['modelo']);m['elementos']={};geoms={};crs=None
    conexoes={c['id']:c for c in dados['resultado']['conexoes']}
    jusantes={r['id']:r for r in dados['resultado'].get('auditoria_jusantes',[])}
    for nome,familia in [('WG_TUBULACOES','LINK'),('WG_NOS','NO'),('WG_DISPOSITIVOS','DISPOSITIVO')]:
        c=QgsVectorLayer(str(gpkg)+'|layername='+nome,nome,'ogr')
        if not c.isValid():raise ValueError('Tabela topológica ausente: '+nome)
        if not {'WG_ID','WG_UID','TIPO','ROTULO','ATIVO'}<=set(c.fields().names()):raise ValueError('Schema topológico incompleto')
        if crs is None:crs=c.crs()
        elif crs!=c.crs():raise ValueError('Camadas topológicas em CRS diferentes')
        for f in c.getFeatures():
            checar_cancelamento(cancelar);i=int(f['WG_ID']);uid=f['WG_UID']
            if uid!=f"{m['projeto']}:{i}" or i in m['elementos']:raise ValueError('Identidade topológica conflitante')
            top={}
            if familia=='LINK':
                if i not in conexoes:raise ValueError('Snapshot sem topologia de uma tubulação; recupere exportação completa, sem inferência geométrica')
                r=conexoes[i];top=dict(HMITopologyStartNodeID=r.get('inicio_bruto',r['inicio']),HMITopologyStopNodeID=r.get('fim_bruto',r['fim']))
            elif familia=='DISPOSITIVO':
                if i not in jusantes:raise ValueError('Snapshot de dispositivos incompleto')
                top=dict(HMITopologyDownstreamLinkID=jusantes[i]['jusante'])
            ativo=True if str(f['ATIVO'])=='True' else False if str(f['ATIVO'])=='False' else None
            m['elementos'][i]=dict(id=i,uid=uid,label=valor_python(f['ROTULO']),tipo=valor_python(f['TIPO']) or 'TIPO_NAO_INFORMADO',familia=familia,
                excluido=False,ativo=ativo,topologia=top,geometria=bytes(f.geometry().asWkb()),atributos={},estados={},alternativas={})
            geoms[i]=QgsGeometry(f.geometry())
    estrutural=analisar(m);potencial=analisar(m,'TODAS_VALVULAS_ABERTAS')
    def assinatura(r):return sorted((c['id'],c['inicio'],c['fim']) for c in r['conexoes'])
    if assinatura(estrutural)!=assinatura(dados['resultado']) or {c['uid'] for c in estrutural['componentes']}!={c['uid'] for c in dados['resultado']['componentes']}:
        raise ValueError('GPKG e execução JSON não representam o mesmo grafo; origens não foram misturadas')
    referencia=m.get('referencia_espacial',{})
    metrica=crs.isValid() and not crs.isGeographic() and crs.mapUnits()==QgsUnitTypes.DistanceMeters
    if metrica and (referencia.get('crs')!=crs.authid() or not referencia.get('fonte')):
        raise ValueError('CRS atribuído ao GPKG sem evidência correspondente na execução')
    origem=dict(execucao_uid=dados['execucao_uid'],data=dados.get('data'),json=str(p),gpkg=str(gpkg),
        json_sha256=hash_json,gpkg_sha256=hash_gpkg,cenario=m['cenario'],projeto=m['projeto'])
    if hash_arquivo(p)!=hash_json or hash_arquivo(gpkg)!=hash_gpkg:raise RuntimeError('Origem topológica alterada durante a recuperação')
    return dict(modelo=m,estrutural=estrutural,potencial=potencial,geometrias=geoms,
        crs=crs,metrica=metrica,origem=origem,persistido=dados)


def geometrias_no_crs(topologia,destino):
    if not topologia['metrica']:return None
    crs=QgsCoordinateReferenceSystem(destino)
    if not crs.isValid() or crs.isGeographic() or crs.mapUnits()!=QgsUnitTypes.DistanceMeters:return None
    transformacao=QgsCoordinateTransform(topologia['crs'],crs,QgsProject.instance().transformContext())
    resultado={}
    for i,g in topologia['geometrias'].items():
        nova=QgsGeometry(g)
        if topologia['crs']!=crs:nova.transform(transformacao)
        if not nova.isNull() and not nova.isEmpty():resultado[i]=nova
    return resultado


def contexto_espacial(componentes,geoms,areas=(),cancelar=None):
    """Mínimo entre geometrias completas, usando índice com geometria armazenada."""
    if geoms is None:return []
    indice=QgsSpatialIndex(flags=QgsSpatialIndex.FlagStoreFeatureGeometries);colecoes={};mapeamento={}
    for k,c in enumerate(componentes):
        checar_cancelamento(cancelar)
        gs=[geoms[i] for i in c['nos']+c['tubos'] if i in geoms]
        if not gs:continue
        g=QgsGeometry.collectGeometry(gs);f=QgsFeature(k);f.setGeometry(g)
        indice.addFeature(f);colecoes[k]=g;mapeamento[k]=c
    relacoes=[]
    for k,g in colecoes.items():
        checar_cancelamento(cancelar)
        vizinhos=indice.nearestNeighbor(g,2)
        distancias=[(g.distance(colecoes[j]),j) for j in vizinhos if j!=k]
        distancias=[(d,j) for d,j in distancias if d>=0]
        if distancias:
            menor=min(d for d,j in distancias);c=mapeamento[k];c['distancia_m']=menor
            c['vizinhos']=[mapeamento[j]['uid'] for d,j in distancias if abs(d-menor)<=1e-9]
            for u in c['vizinhos']:relacoes.append(dict(comp_uid=c['uid'],vizinho_uid=u,distancia_m=menor,
                criterio='Distância mínima entre geometrias; não cria conexão nem prova conexão ausente'))
    # Relação espacial com áreas é contexto cadastral, sem precedência entre polígonos.
    indice_areas=QgsSpatialIndex(flags=QgsSpatialIndex.FlagStoreFeatureGeometries)
    for k,a in enumerate(areas):
        f=QgsFeature(k);f.setGeometry(a['geometria']);indice_areas.addFeature(f)
    for k,g in colecoes.items():
        for j in indice_areas.intersects(g.boundingBox()):
            if g.intersects(areas[j]['geometria']):mapeamento[k]['areas'].append(areas[j]['uid'])
    return relacoes


def ler_areas(configuracoes,crs_destino):
    from auditoria_fronteiras.entradas import digest,valor_python
    from auditoria_fronteiras.apresentacao import legivel
    resultado=[];fontes=[]
    for config in configuracoes:
        c=config['camada'];idcampo=config['campo_id'];nomecampo=config.get('campo_nome') or idcampo
        if c.fields().indexFromName(idcampo)<0 or c.fields().indexFromName(nomecampo)<0:raise ValueError('Campo de contexto inexistente')
        if not c.crs().isValid():raise ValueError('Área sem CRS válido')
        origem=digest([c.providerType(),c.source()]);transformacao=QgsCoordinateTransform(c.crs(),QgsCoordinateReferenceSystem(crs_destino),QgsProject.instance().transformContext())
        assinaturas=[];repetidas=Counter()
        for f in c.getFeatures():
            g=QgsGeometry(f.geometry());attrs={v.name():valor_python(f[v.name()]) for v in c.fields()}
            base_uid=digest([origem,attrs,bytes(g.asWkb()).hex()]);assinaturas.append(base_uid);repetidas[base_uid]+=1
            uid=base_uid if repetidas[base_uid]==1 else base_uid+'_'+str(repetidas[base_uid])
            if g.isEmpty() or not g.isGeosValid():raise ValueError('Polígono vazio/inválido no contexto '+c.name())
            if c.crs().authid()!=crs_destino:g.transform(transformacao)
            resultado.append(dict(uid=uid,origem=origem,camada=c.name(),id_original=attrs[idcampo],
                exibicao=legivel(attrs[nomecampo] if attrs[nomecampo] not in (None,'') else attrs[idcampo]),
                tipo=config.get('tipo') or c.name(),campo_id=idcampo,campo_nome=nomecampo,geometria=g,
                substituicao_exibicao=nomecampo!=idcampo and attrs[nomecampo] in (None,'')))
        fontes.append(dict(origem=origem,fonte=c.source(),provedor=c.providerType(),camada=c.name(),campo_id=idcampo,
            campo_nome=nomecampo,tipo=config.get('tipo') or c.name(),assinatura=digest(sorted(assinaturas)),
            natureza='CONTEXTO_ESPACIAL_CONSULTADO_NESTA_INTEGRACAO'))
    return resultado,fontes
