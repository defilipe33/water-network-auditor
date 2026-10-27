"""Locais manuais como projeção complementar, sem eventos geométricos fictícios."""
from collections import defaultdict
from . import conjuntos_investigacao as storage
from . import decisoes as db


def redes_gis(pacote,projeto):
    """Feições de fontes exatas, com assinatura completa e cópias ambíguas omitidas."""
    from qgis.core import QgsVectorLayer,QgsGeometry,QgsCoordinateReferenceSystem,QgsCoordinateTransform
    from auditoria_fronteiras.entradas import digest,valor_python
    saida=[];destino=QgsCoordinateReferenceSystem(pacote['dossie']['contexto']['parametros']['crs'])
    fontes={f['origem']:f for f in pacote['dossie']['contexto']['fontes']};tubos={t['uid'].rsplit('_',1)[0]:t for t in pacote['dossie']['tubulacoes']}
    for origem,fonte in fontes.items():
        camadas=[c for c in projeto.mapLayers().values() if isinstance(c,QgsVectorLayer) and c.isValid() and c.geometryType()==1 and c.providerType()==fonte.get('provedor') and c.source()==fonte.get('fonte')]
        if len(camadas)!=1:continue
        camada=camadas[0];grupos=defaultdict(list)
        for f in camada.getFeatures():
            attrs={c.name():valor_python(f[c.name()]) for c in camada.fields()};g=f.geometry();assinatura=digest([origem,attrs,bytes(g.asWkb()).hex()]);grupos[assinatura].append((f.id(),attrs,QgsGeometry(g)))
        for assinatura,fs in grupos.items():
            if len(fs)!=1:continue
            fid,attrs,g=fs[0];uid=assinatura+'_1';t=tubos.get(assinatura)
            if t:uid=t['uid']
            if camada.crs()!=destino:g.transform(QgsCoordinateTransform(camada.crs(),destino,projeto))
            v=dict(origem='GIS',chave=uid,natureza='MANUAL',dados=dict(origem=origem,camada=camada.name(),fonte=camada.source(),provedor=camada.providerType(),id=t['id_exibido'] if t else str(attrs.get(fonte.get('campo_id'),'')),atributos=attrs,geometria_wkb=bytes(g.asWkb()).hex(),assinatura=assinatura))
            saida.append((v,g,camada.id(),fid))
    return saida


def casos(base,pacote,contexto=None):
    registros=storage.atuais(base,pacote,'LOCAL_MANUAL');el=pacote['topologia']['modelo']['elementos']
    historicos=defaultdict(list)
    for h in storage.historico(base,pacote,'LOCAL_MANUAL'):historicos[h['obj_uid']].append(h)
    mapas={modo:defaultdict(set) for modo in db.MODOS}
    for modo in db.MODOS:
        for c in pacote['resultado']['componentes' if modo=='ESTRUTURAL' else 'componentes_potenciais']:
            for i in c['nos']+c['tubos']:mapas[modo][i].add(c['uid'])
    tubos={t['uid']:t for t in pacote['dossie']['tubulacoes']};saida=[]
    for r in registros:
        d=r['dados'];reconciliacao=storage.reconciliar(r,pacote)
        ids=[int(v['chave']) for v in r['vinculos'] if v['origem']=='WG' and v['natureza']!='REFERENCIA_HISTORICA' and int(v['chave']) in el and el[int(v['chave'])]['uid']==v['dados'].get('uid') and el[int(v['chave'])].get('excluido') is False]
        gis=[v['chave'] for v in r['vinculos'] if v['origem']=='GIS'];areas=[v['chave'] for v in r['vinculos'] if v['origem']=='AREA']
        # Mudança de posição/composição abre contexto de análise novo. A UUID do
        # local continua estável e todos os resultados anteriores permanecem no IGD.
        identidade=dict(local=r['obj_uid'],topologia=r['topo_uid'],x=d['x'],y=d['y'],crs=d['crs'],vinculos=[(v['origem'],v['chave'],v['dados']) for v in r['vinculos']])
        uid=db.digest(identidade);comps={modo:sorted({u for i in ids for u in mapas[modo][i]}) for modo in db.MODOS}
        c=dict(uid=uid,tipo='MANUAL',origem='MANUAL',chave=r['obj_uid'],manual_uid=r['obj_uid'],manual_hist=r['uid'],
            manual_registro=r,manual_posicao=dict(x=d['x'],y=d['y'],crs=d['crs']),
            categorias=['OUTROS'],titulo=d.get('titulo') or 'Local manual · '+r['obj_uid'][:8],
            resumo=(d.get('classificacao','')+' · ' if d.get('classificacao') else '')+(d.get('observacoes') or 'Local definido pelo usuário; associações não comprovam conexão hidráulica.'),
            wg_ids=ids,gis_uids=gis,area_uids=[a.removeprefix('CTX:') for a in areas],local_uid=None,
            regioes=[str(v['dados'].get('exibicao') or v['chave']) for v in r['vinculos'] if v['origem']=='AREA'],
            elementos=[el[i]['tipo']+' '+str(el[i]['label']) for i in ids],
            tubos_gis=[str(v['dados'].get('id',v['chave']))+' — '+v['dados'].get('camada','') for v in r['vinculos'] if v['origem']=='GIS'],
            evidencias=['Associação manual para investigação; não adiciona arestas ao grafo.'],
            proxima='Conferir os elementos escolhidos e registrar sua interpretação; sem aprovação formal.',
            tecnico=[('Vínculo '+v['chave'],v['situacao']) for v in reconciliacao],componentes=comps,
            fontes={modo:None for modo in db.MODOS},prioridade='Média',revisao='SEM_REVISAO_POR_OCORRENCIA',
            perspectivas={modo:dict(texto='Associações manuais; conectividade não inferida',avisos=[]) for modo in db.MODOS})
        c['busca']=' '.join([c['titulo'],c['resumo'],*c['elementos'],*c['tubos_gis'],*c['regioes']]).casefold()
        c['tecnico'] += [('Histórico '+h['data_utc'],f"{h['dados'].get('titulo','')} · {h['dados'].get('observacoes','')} · X {h['dados']['x']} / Y {h['dados']['y']} · {h['dados']['crs']} · {len(h['vinculos'])} vínculos · excluído: {bool(h['excluido'])}") for h in historicos[r['obj_uid']]]
        if contexto:
            for area in areas:
                if area in contexto.areas:
                    # Apenas relação declarada, jamais DENTRO/FRONTEIRA inferidos.
                    c['area_uids'].append(area)
            for v in r['vinculos']:
                if v['origem']=='GIS' and v['chave'] not in contexto._gis:
                    dados=v['dados'];k='GIS_REDE:'+dados.get('origem','MANUAL');contexto.camadas.setdefault(k,dict(chave=k,origem='GIS',nome=dados.get('camada','Fonte manual'),natureza='Tubulações'))
                    entidade=dict(uid=v['chave'],camada=k,dados=dados.get('atributos',{}),proveniencia=dict(origem=dados.get('origem'),execucao=r['ig_uid'],natureza='ASSOCIACAO_MANUAL'))
                    contexto._gis[v['chave']]=entidade;contexto._por_camada[k].append(entidade);contexto._campos.pop(k,None)
        saida.append(c)
    return saida


def candidatos(pacote,contexto,x,y,crs,raio=15):
    from qgis.core import (QgsGeometry,QgsPointXY,QgsCoordinateReferenceSystem,
                           QgsCoordinateTransform,QgsProject,QgsUnitTypes,QgsFeature,QgsSpatialIndex)
    if raio<0:raise ValueError('Raio inválido')
    destino=QgsCoordinateReferenceSystem(pacote['dossie']['contexto']['parametros']['crs'])
    if destino.isGeographic() or destino.mapUnits()!=QgsUnitTypes.DistanceMeters:raise ValueError('Busca em metros exige CRS métrico válido')
    origem=QgsCoordinateReferenceSystem(crs)
    if not origem.isValid():raise ValueError('CRS do ponto inválido')
    p=QgsCoordinateTransform(origem,destino,QgsProject.instance()).transform(QgsPointXY(x,y));ponto=QgsGeometry.fromPointXY(p)
    geoms=[];index=QgsSpatialIndex()
    def incluir(g,v):
        if g is None or g.isEmpty():return
        f=QgsFeature(len(geoms));f.setGeometry(g);index.addFeature(f);geoms.append((g,v))
    if pacote['resultado']['meta']['parametros'].get('espacial_habilitado'):
        for i,g in pacote.get('geometrias',{}).items():
            e=pacote['topologia']['modelo']['elementos'].get(i)
            if e and e.get('excluido') is False:incluir(g,storage.vinculo_wg(pacote,i))
    for v,g,_,_ in redes_gis(pacote,QgsProject.instance()):incluir(g,v)
    for u,g in contexto._contexto_geometrico.items():
        a=contexto.areas[u];incluir(g,dict(origem='AREA',chave=u,natureza='MANUAL',dados=dict(exibicao=a.get('exibicao'),camada=a['camada'],origem=a['origem'])))
    for l in pacote['resultado']['locais']:
        r=l['registro'];incluir(QgsGeometry.fromPointXY(QgsPointXY(r['X'],r['Y'])),dict(origem='LOCAL',chave=l['uid'],natureza='MANUAL',dados=dict(exibicao=r['LOCAL'])))
    caixa=ponto.boundingBox();caixa.grow(raio)
    saida=[]
    for n in index.intersects(caixa):
        g,v=geoms[n];distancia=ponto.distance(g)
        if distancia<=raio:saida.append(dict(v,distancia_m=distancia))
    return sorted(saida,key=lambda v:(v['distancia_m'],v['origem'],v['chave']))
