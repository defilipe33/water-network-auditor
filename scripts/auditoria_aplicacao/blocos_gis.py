"""Blocos de arestas biconexas e encadeamento de pontes da fotografia GIS."""

from collections import defaultdict
from auditoria_fronteiras.entradas import digest
from auditoria_fronteiras.modelos import verificar_cancelamento
from .dependencias_gis import PontesGIS, RedeGIS
from .corredores_gis import _buscar


VERSAO='gis-blocos-1'
ORCAMENTO_VISITAS=4_000_000


def _encadear_pontes(rede,dfs,cancelar):
    """Preserva bifurcações, origens e contatos com malhas como limites."""
    adj = defaultdict(list)
    for i in dfs.pontes:
        u,v,_,_=rede.arestas[i]
        adj[u].append((v,i))
        adj[v].append((u,i))
    origens={n for ns in rede.origens.values() for n in ns}
    limites={n for n,es in adj.items() if len(es)!=2 or len(rede.adj[n])!=2 or n in origens}
    visitadas=set()
    for limite in sorted(limites):
        for v,i in adj[limite]:
            verificar_cancelamento(cancelar)
            if i in visitadas:continue
            cadeia=[i]
            visitadas.add(i)
            while v not in limites:
                verificar_cancelamento(cancelar)
                v,i=next((w,e) for w,e in adj[v] if e not in visitadas)
                cadeia.append(i)
                visitadas.add(i)
            yield cadeia


def analisar(d,detalhe='MACRO',cancelar=None,etapa=lambda *_:None):
    if detalhe not in ('MACRO','DETALHADO'):
        raise ValueError('Escolha o nível de detalhamento dos blocos.')
    foto = d['foto']
    etapa(0,'Separando malhas, pontes e articulações')
    rede=RedeGIS(foto,d['fontes'],cancelar)
    dfs=PontesGIS(rede,cancelar,coletar_blocos=True)
    _,componentes=rede.componentes(cancelar=cancelar)
    # A numeração de grupos acompanha a primeira visita na mesma ordem de nós.
    if detalhe=='MACRO':
        grupos=[g for g in dfs.blocos if len(g)!=1 or g[0] not in dfs.pontes]
        grupos.extend(_encadear_pontes(rede,dfs,cancelar))
    else:grupos=dfs.blocos
    por_segmento=defaultdict(set)
    for c in d.get('agrupamento',{}).get('corredores',()):
        for i in c['segmentos']:por_segmento[i].add(c['uid'])
    alternativas=defaultdict(set)
    for r in d.get('rotas',()):
        a=r.get('alternativa') or {}
        for i in a.get('segmentos',()):alternativas[i].add(r['uid'])
    criticas={t['uid'] for t in d.get('tubulacoes',()) if 'CRITICA' in t['funcoes']}
    busca = _buscar(rede,rede.origens,cancelar) if rede.origens else None
    referencia_por_no = dict(busca[2]) if busca else {}
    custo=len(rede.nos)+len(rede.arestas)
    permitir_buscas = custo*len(rede.origens)<=ORCAMENTO_VISITAS
    por_fonte = {u:_buscar(rede,[u],cancelar)[0] for u in rede.origens} if permitir_buscas else {}
    blocos, por_no = [], defaultdict(list)
    resto = max(0,ORCAMENTO_VISITAS-custo*(1+len(por_fonte)))
    etapa(0,'Relacionando origens, corredores e áreas')
    reg_areas = _intersecoes(foto,cancelar)
    for es in sorted(grupos,key=min):
        verificar_cancelamento(cancelar)
        ns={v for i in es for v in rede.arestas[i][:2]}
        ids=sorted(rede.uids[u] for u in ns)
        ts=sorted({rede.arestas[i][2] for i in es})
        partes={foto['arestas'][i]['tubo'] for i in es}
        chave=sorted((e['tubo'],e['inicio'],e['fim']) for i in es for e in [foto['arestas'][i]])
        uid=digest(['bloco-gis',chave])
        fontes=rede.nomes_origens(componentes[dfs.grupo[min(ns)]][1])
        entrada = min(ns,key=lambda u:(busca[0][u],rede.uids[u])) if fontes and busca else None
        ref = None
        if entrada is not None:
            ref=dict(no=rede.uids[entrada],origem=_fonte(busca,referencia_por_no,entrada,cancelar),
                     distancia_m=busca[0][entrada])
            if resto>0:
                caminho=_rota_limitada(rede,busca,entrada,cancelar,resto)
                if caminho is not None:
                    ref['segmentos']=caminho
                    resto-=len(caminho)+1
        dists={u:min(por_fonte[u][v] for v in ns) for u in fontes if u in por_fonte}
        c=set().union(*(por_segmento[i] for i in es))
        ciclo=len(es)>=len(ns)
        redundancia=('MALHA_COM_PIPES_DISTINTOS' if ciclo and len(ts)>1 and
                     all(len(rede.pipes[t])==1 for t in ts) else
                     'MALHA_SEM_INDEPENDENCIA_DE_PIPE_VERIFICADA' if ciclo else 'SEM_MALHA_INTERNA')
        bloco=dict(uid=uid,nome='Bloco '+str(len(blocos)+1).zfill(3),tipo='MALHA' if ciclo else 'RAMIFICACAO',
            segmentos=sorted(es),pipes=ts,nos=ids,comprimento_m=sum(rede.arestas[i][3] for i in es),
            origens=fontes,referencia=ref,distancias_m=dists,corredores=sorted(c),criticas=sorted(criticas.intersection(ts)),
            redundancia=redundancia,alternativas=sorted({u for i in es for u in alternativas.get(i,())}),
            areas=sorted({a for i in es for a in reg_areas.get(i,())}),
            propostas=sorted({rede.tubos[t]['proposta_uid'] for t in partes if rede.tubos[t].get('proposta_uid')}),
            articulacoes=sorted(rede.uids[v] for v in ns & dfs.articulacoes))
        blocos.append(bloco)
        for no in ids:por_no[no].append(uid)
    ligacoes=[dict(no=u,blocos=ids) for u,ids in por_no.items() if len(ids)>1]
    # Uma junção com muitos ramos é um único registro, sem pares quadráticos.
    for b in blocos:
        b['fronteiras']=[n for n in b['nos'] if len(por_no[n])>1]
    return dict(algoritmo=VERSAO,detalhe=detalhe,blocos=blocos,ligacoes=ligacoes,
                distancias_por_fonte=permitir_buscas,limite_buscas=ORCAMENTO_VISITAS,
                criterio='Componentes biconexos por arestas. No nível macro, agrupa pontes consecutivas sem bifurcações, fontes ou entrada de malha.')


def _rota_limitada(rede,busca,entrada,cancelar,limite):
    _,anteriores,_=busca
    segmentos=[]
    while entrada in anteriores:
        verificar_cancelamento(cancelar)
        if len(segmentos)>=limite:return None
        entrada,i=anteriores[entrada]
        segmentos.append(i)
    return segmentos[::-1]


def _fonte(busca,cache,no,cancelar):
    _,anteriores,_=busca
    visitados=[]
    while no not in cache:
        verificar_cancelamento(cancelar)
        visitados.append(no)
        no,_=anteriores[no]
    origem=cache[no]
    for u in visitados:cache[u]=origem
    return origem


def _intersecoes(foto,cancelar):
    from qgis.core import QgsGeometry
    from .grafo_gis import _indexar
    from .investigacao_gis import geometria
    areas = [(a['uid'],g) for a in foto.get('areas',()) if (g:=geometria(a.get('wkb')))]
    if not areas:return {}
    indice = _indexar([g for _,g in areas])
    tubos = {r['uid']:r for r in foto['tubos']}
    saida={}
    for i,e in enumerate(foto['arestas']):
        verificar_cancelamento(cancelar)
        g=geometria(tubos[e['tubo']].get('wkb'))
        if not g:continue
        a,b=e['inicio'],e['fim']
        if (a,b)!=(0.,1.):
            m=g.length()
            g=QgsGeometry(g.constGet().curveSubstring(m*a,m*b))
        # A seleção de área é independente da alcançabilidade no grafo.
        ids=[areas[j][0] for j in indice.intersects(g.boundingBox()) if g.intersects(areas[j][1])]
        if ids:saida[i]=ids
    return saida


def comparar(antes,depois):
    a={b['uid']:b for b in antes.get('blocos',())}
    b={b['uid']:b for b in depois.get('blocos',())}
    for uid in sorted(set(a)|set(b)):
        x,y=a.get(uid),b.get(uid)
        if x is None:tipo='Bloco adicionado'
        elif y is None:tipo='Bloco retirado'
        elif any(x.get(k)!=y.get(k) for k in ('origens','corredores','redundancia','alternativas')):
            tipo='Dependências do bloco alteradas'
        else:continue
        yield dict(uid=digest(['diff-bloco',uid,tipo]),tipo=tipo,ref=(y or x)['nome'],
            antes=', '.join((x or {}).get('origens',())),depois=', '.join((y or {}).get('origens',())),
            tubos=(y or x)['pipes'],nome=(y or x)['nome'])
