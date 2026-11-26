"""Cobertura integral e caminhos de referência sobre uma fotografia do grafo GIS."""

from collections import defaultdict
from datetime import datetime, timezone
from heapq import heappop, heappush
from itertools import chain
from math import inf, isclose, isfinite, fsum
from uuid import uuid4

from auditoria_fronteiras.entradas import digest
from auditoria_fronteiras.modelos import verificar_cancelamento
from .agrupamento_corredores_gis import sequencias
from .dependencias_gis import PontesGIS, RedeGIS
from .blocos_gis import _intersecoes


VERSAO = 'gis-macro-origem-1'


def assinatura(origens,parametros):
    return digest([VERSAO,sorted(origens),parametros])


def _chave(foto,i):
    e=foto['arestas'][i]
    return e['tubo'],e.get('inicio',0.),e.get('fim',1.)


def _arvore(rede,origens,cancelar):
    """Dijkstra multiorigem. Um predecessor por nó e máscara de empates."""
    n=len(rede.uids)
    dist=[inf]*n
    pais=[None]*n
    grupos=[0]*n
    fila=[]
    fontes=sorted(origens)
    for i,u in enumerate(fontes):
        for v in rede.origens[u]:
            if dist[v]>0:
                dist[v]=0.
                heappush(fila,(0.,rede.uids[v],v))
            grupos[v]|=1<<i
    ordem=[]
    fechados=set()
    while fila:
        verificar_cancelamento(cancelar)
        d,_,u=heappop(fila)
        if d!=dist[u] or u in fechados:continue
        ordem.append(u)
        fechados.add(u)
        for v,i in rede.adj[u]:
            if v in fechados:continue
            custo=d+rede.arestas[i][3]
            empate=isclose(custo,dist[v],rel_tol=0.,abs_tol=1e-8)
            if custo<dist[v] and not empate:
                dist[v]=custo
                grupos[v]=grupos[u]
                pais[v]=[u,i]
                heappush(fila,(custo,rede.uids[v],v))
            elif empate and pais[v]:
                anterior,aresta=pais[v]
                assinatura=lambda no,seg:((grupos[no]&-grupos[no]).bit_length(),rede.uids[no],_chave(rede.foto,seg))
                if assinatura(u,i)<assinatura(anterior,aresta):pais[v]=[u,i]
                grupos[v]|=grupos[u]
    return dist,pais,grupos,fontes,ordem


def _corredores(rede,arvore,minimo,cancelar):
    _,pais,mascaras,fontes,ordem=arvore
    suporte=[0.]*len(pais)
    filhos=defaultdict(list)
    origens_raiz={}
    for u in ordem:
        p=pais[u]
        origens_raiz[u]=origens_raiz[p[0]] if p else mascaras[u]
    for u in reversed(ordem):
        verificar_cancelamento(cancelar)
        if p:=pais[u]:
            v,i=p
            m=rede.arestas[i][3]
            suporte[v]+=m+suporte[u]
            filhos[v].append((u,i))
    troncos=set()
    for raiz in (u for u in ordem if pais[u] is None):
        u=raiz
        while filhos[u]:
            verificar_cancelamento(cancelar)
            u,i=min(filhos[u],key=lambda x:(-(suporte[x[0]]+rede.arestas[x[1]][3]),rede.uids[x[0]]))
            troncos.add(i)
    assinaturas={i:'TRONCO' if i in troncos else 'RAMAL' for u,p in enumerate(pais) if p
                 for i in [p[1]] if i in troncos or suporte[u]+rede.arestas[i][3]>=minimo}
    dist=arvore[0]
    cs=[]
    no_de_inicio=defaultdict(list)
    por_fim={}
    for es,ns in sequencias(rede.foto['arestas'],assinaturas,cancelar):
        if dist[rede.nos[ns[0]]]>dist[rede.nos[ns[-1]]]:
            es.reverse()
            ns.reverse()
        uid=digest(['corredor-referencia',sorted(_chave(rede.foto,i) for i in es)])
        mascara=origens_raiz[rede.nos[ns[0]]]
        c=dict(uid=uid,tipo=assinaturas[es[0]],segmentos=es,nos=ns,
               comprimento_m=fsum(rede.arestas[i][3] for i in es),
               pipes=sorted({rede.arestas[i][2] for i in es}),
               origens=[f for j,f in enumerate(fontes) if mascara&(1<<j)],
               distancia_final_m=dist[rede.nos[ns[-1]]])
        cs.append(c)
        no_de_inicio[ns[0]].append(uid)
        por_fim[ns[-1]]=uid
    cs.sort(key=lambda c:(c['tipo']!='TRONCO',dist[rede.nos[c['nos'][0]]],-c['comprimento_m'],c['uid']))
    for j,c in enumerate(cs,1):
        c.update(nome=('Tronco ' if c['tipo']=='TRONCO' else 'Ramal ')+str(j).zfill(2),
                 pai=por_fim.get(c['nos'][0]),ramos=no_de_inicio[c['nos'][-1]])
    return cs


def _particionar(rede,detalhes,arvore,minimo,dominio,cancelar):
    """Enraíza a árvore de articulações e reúne sub-ramos no mesmo grupo."""
    media,pais,_,_,_=arvore
    ns=[{v for i in es for v in rede.arestas[i][:2]} for es in detalhes]
    por_no=defaultdict(list)
    for b,vertices in enumerate(ns):
        for n in vertices:por_no[n].append(b)
    visto=set()
    saida=[]
    for raiz in sorted((u for u in por_no if isfinite(media[u])),
                       key=lambda u:(pais[u] is not None,media[u],rede.uids[u])):
        verificar_cancelamento(cancelar)
        if all(b in visto for b in por_no[raiz]):continue
        # Codifica nó como negativo e bloco como não negativo.
        inicial=-raiz-1
        arv=[inicial]
        filhos=defaultdict(list)
        nos_vistos={raiz}
        for x in arv:
            verificar_cancelamento(cancelar)
            if x<0:
                for b in por_no[-x-1]:
                    if b not in visto:
                        visto.add(b)
                        filhos[x].append(b)
                        arv.append(b)
            else:
                for n in sorted(ns[x]):
                    if n not in nos_vistos:
                        nos_vistos.add(n)
                        filhos[x].append(-n-1)
                        arv.append(-n-1)
        peso={}
        for x in reversed(arv):
            peso[x]=fsum(chain((rede.arestas[i][3] for i in detalhes[x]) if x>=0 else (),
                               (peso[y] for y in filhos[x])))
        atual=[]
        saida.append(atual)
        fila=[(inicial,atual,None)]
        for x,g,area in fila:
            verificar_cancelamento(cancelar)
            if x>=0:
                g.extend(detalhes[x])
                area=dominio.get(x) or area
            seguintes=sorted(filhos[x],key=lambda y:(-peso[y],y))
            for pos,y in enumerate(seguintes):
                divide_area=(x<0 and area and dominio.get(y) and dominio[y]!=area)
                if x<0 and peso[y]>=minimo and (pos>0 or divide_area):
                    destino=[]
                    saida.append(destino)
                else:destino=g
                fila.append((y,destino,area))
    return [sorted(g) for g in saida if g]


def organizar_grupos(foto,m,grupos,cancelar=None):
    """Recompõe relações sem alterar a fotografia, corredores ou blocos detalhados."""
    es=foto['arestas']
    por_cor={i:c['uid'] for c in m['corredores'] for i in c['segmentos']}
    corredores_no={}
    for c in m['corredores']:
        for n in c['nos']:
            corredores_no.setdefault(n,c['uid'])
    por_det={i:b['uid'] for b in m['detalhados'] for i in b['segmentos']}
    por_tubo={t['uid']:t for t in foto['tubos']}
    indice_pontes=set(m['pontes'])
    alt=set(m['alternativas'])
    indice_areas={int(i):a for i,a in m['areas_segmentos'].items()}
    por_no=defaultdict(list)
    contagem=defaultdict(dict)
    saida=[]
    for j,g in enumerate(grupos,1):
        verificar_cancelamento(cancelar)
        box=g if isinstance(g,dict) else {'segmentos':g}
        ids=sorted(box['segmentos'])
        nos={u for i in ids for u in (es[i]['a'],es[i]['b'])}
        u=digest(['bloco-macro',sorted(_chave(foto,i) for i in ids)])
        for n in nos:por_no[n].append(u)
        ts=[por_tubo[es[i]['tubo']] for i in ids]
        for i,t in zip(ids,ts):
            p=t.get('feicao') or t['uid']
            contagem[p][u]=contagem[p].get(u,0.)+es[i]['comprimento_m']
        saida.append(dict(uid=u,nome=box.get('nome') or f'Bloco macro {j:02d}',tipo='MACRO',
            segmentos=ids,nos=sorted(nos),pipes=sorted({t.get('feicao') or t['uid'] for t in ts}),
            detalhados=sorted({por_det[i] for i in ids}),
            comprimento_m=fsum(es[i]['comprimento_m'] for i in ids),
            corredores=sorted({por_cor[i] for i in ids if i in por_cor}),
            corredor_vizinho=min((corredores_no[n] for n in nos if n in corredores_no),default=None),
            areas=sorted({a for i in ids for a in indice_areas.get(i,{})}),
            areas_declaradas=list(box.get('areas_declaradas',[])),criterio=box.get('criterio','AUTOMATICO'),
            origens=sorted({f for i in ids for f in m['componentes'][m['componente_segmento'][i]]['origens']}),
            selecionadas=sorted({f for i in ids for f in m['componentes'][m['componente_segmento'][i]]['selecionadas']}),
            pontes=sorted(indice_pontes.intersection(ids)),alternativas=sorted(alt.intersection(ids)),
            propostas=sorted({t['proposta_uid'] for t in ts if t.get('proposta_uid')})))
    exclusivo=defaultdict(list)
    for p,opcoes in contagem.items():
        u=min(opcoes,key=lambda u:(-opcoes[u],u))
        exclusivo[u].append(p)
    for b in saida:
        b['pipes_principais']=sorted(exclusivo[b['uid']])
        b['fronteiras']=[n for n in b['nos'] if len(por_no[n])>1]
    ligacoes=[dict(no=n,blocos=sorted(ids)) for n,ids in sorted(por_no.items()) if len(ids)>1]
    return saida,ligacoes


def analisar(foto,origens=None,*,minimo_m=500.,orientar_areas=False,comparar=False,cancelar=None,etapa=lambda *_:None):
    if not isinstance(minimo_m,(int,float)) or not isfinite(minimo_m) or minimo_m<=0:
        raise ValueError('Informe uma extensão mínima positiva para as ramificações.')
    rede=RedeGIS(foto,None,cancelar)
    fontes=rede.ids_origens if origens is None else sorted(set(origens))
    if not set(fontes)<=rede.origens.keys() or comparar and len(fontes)!=2:
        raise ValueError('Selecione duas origens válidas para comparar ou use a visão de uma origem.')
    if any(not isfinite(e[3]) or e[3]<=0 for e in rede.arestas):
        raise ValueError('A fotografia contém comprimentos nulos ou inválidos. Confira a topologia antes de calcular a visão macro.')
    etapa(0,'Percorrendo toda a rede alcançável')
    grupo,cs=rede.componentes(cancelar=cancelar)
    por_seg=[grupo[u] for u,_,_,_ in rede.arestas]
    escopo=set(fontes)
    comps=[dict(origens=fs,selecionadas=[u for u in fs if u in escopo],
                nos=len(vertices),comprimento_m=0.,segmentos=0)
           for vertices,bits in cs for fs in [rede.nomes_origens(bits)]]
    for i,g in enumerate(por_seg):
        verificar_cancelamento(cancelar)
        comps[g]['comprimento_m']+=rede.arestas[i][3]
        comps[g]['segmentos']+=1
    alc=[i for i,g in enumerate(por_seg) if comps[g]['selecionadas']]
    arv=_arvore(rede,fontes,cancelar)
    es_alc=set(alc)
    if any((i in es_alc)!=isfinite(arv[0][u]) for i,(u,_,_,_) in enumerate(rede.arestas)):
        raise ValueError('O percurso de referência divergiu da cobertura topológica.')
    etapa(0,'Agrupando corredores e blocos da rede completa')
    corredores=_corredores(rede,arv,minimo_m,cancelar)
    arv_es={p[1] for p in arv[1] if p}
    corr_es={i for c in corredores for i in c['segmentos']}
    dfs=PontesGIS(rede,cancelar,coletar_blocos=True)
    detalhes=sorted((sorted(g) for g in dfs.blocos if not fontes or g[0] in es_alc),
                    key=lambda g:min(_chave(foto,i) for i in g))
    partes=[dict(uid=digest(['detalhe-macro',sorted(_chave(foto,i) for i in g)]),segmentos=g,
                 nome=f'Bloco detalhado {n:02d}',
                 comprimento_m=fsum(rede.arestas[i][3] for i in g),
                 pipes=sorted({rede.arestas[i][2] for i in g}),
                 tipo='PONTE' if len(g)==1 and g[0] in dfs.pontes else 'BICONEXO') for n,g in enumerate(detalhes,1)]
    areas=_intersecoes(foto,cancelar,segmentos=alc,medir=True)
    for c in corredores:
        c['areas']=sorted({u for i in c['segmentos'] for u in areas.get(i,{})})
    dominio={}
    if orientar_areas:
        for j,g in enumerate(detalhes):
            peso=defaultdict(float)
            for i in g:
                for u,m in areas.get(i,{}).items():peso[u]+=m
            if peso:dominio[j]=min(peso,key=lambda u:(-peso[u],u))
    grupos=_particionar(rede,detalhes,arv,minimo_m,dominio,cancelar) if fontes else []
    membros=[i for g in grupos for i in g]
    if len(membros)!=len(alc) or set(membros)!=es_alc:
        raise ValueError('A partição não cobre exatamente a rede alcançável.')
    ctotal=fsum(rede.arestas[i][3] for i in alc)
    cm=fsum(rede.arestas[i][3] for i in corr_es)
    pipes={rede.arestas[i][2] for i in alc}
    parciais={p for p in pipes if any(i not in es_alc for i in rede.pipes[p])}
    sem_aresta=set(rede.tubos)-{e['tubo'] for e in foto['arestas']}
    c=dict(pipes_escopo=len(rede.pipes),pipes_alcancaveis=len(pipes),
           pipes_sem_acesso=len(rede.pipes)-len(pipes) if fontes else None,pipes_parciais=len(parciais),
           arestas_escopo=len(rede.arestas),arestas_alcancaveis=len(alc),alcancavel_m=ctotal,
           blocos_m=fsum(rede.arestas[i][3] for i in membros),corredores_m=cm,rede_restante_m=ctotal-cm,
           alternativa_m=fsum(rede.arestas[i][3] for i in es_alc-arv_es),
           partes_sem_aresta=sorted(sem_aresta),
           comprimento_excluido_conhecido_m=fsum(rede.tubos[u].get('comprimento_m') or 0. for u in sem_aresta),
           comprimento_sem_acesso_m=fsum(c['comprimento_m'] for c in comps if not c['selecionadas']) if fontes else None,
           avisos=list(foto.get('avisos',())),
           referencias_pendentes=[r.get('motivo','Referência não verificada') for r in foto.get('diagnosticos',())
                                  if r['tipo']=='EQUIPAMENTO_PENDENTE'])
    def serializar(a):
        dist,pai,mascaras,fs,ordem=a
        return dict(pais=pai,distancias=[d if isfinite(d) else None for d in dist],
                    mascaras=[format(x,'x') for x in mascaras],fontes=fs)
    m=dict(algoritmo=VERSAO,parametros=dict(minimo_m=minimo_m,orientar_areas=orientar_areas,comparar=comparar),
           cobertura=c,alcancaveis=alc,corredores=corredores,detalhados=partes,origens=fontes,
           arvore=serializar(arv),alternativas=sorted(es_alc-arv_es),
           pontes=sorted(es_alc.intersection(dfs.pontes) if fontes else dfs.pontes),
           articulacoes=sorted(rede.uids[i] for i in dfs.articulacoes if not fontes or isfinite(arv[0][i])),
           areas_segmentos={str(i):r for i,r in areas.items()},componentes=comps,componente_segmento=por_seg)
    if comparar:
        m['referencias_por_origem']={}
        for f in fontes:
            a=_arvore(rede,[f],cancelar)
            m['referencias_por_origem'][f]=dict(arvore=serializar(a),corredores=_corredores(rede,a,minimo_m,cancelar))
    m['blocos'],m['ligacoes']=organizar_grupos(foto,m,grupos,cancelar)
    return m


def caminho(foto,m,segmentos,origem=None,cancelar=None):
    arv=m['arvore'] if origem is None else m['referencias_por_origem'][origem]['arvore']
    por_no={n['uid']:i for i,n in enumerate(foto['nos'])}
    visitados=set()
    es=set()
    for i in segmentos:
        for n in (foto['arestas'][i]['a'],foto['arestas'][i]['b']):
            u=por_no[n]
            while u not in visitados:
                verificar_cancelamento(cancelar)
                visitados.add(u)
                if not (p:=arv['pais'][u]):break
                u,k=p
                es.add(k)
    return sorted(es)


def influencia(foto,m):
    """Vencedores nos nós, transições entre vencedores e empates."""
    a=m['arvore']
    nos={n['uid']:i for i,n in enumerate(foto['nos'])}
    grupos=defaultdict(list)
    for i,e in enumerate(foto['arestas']):
        x,y=(int(a['mascaras'][nos[e[k]]],16) for k in ('a','b'))
        if not x or not y:rotulo='SEM_ACESSO' if a['fontes'] else 'INDETERMINADO'
        elif x==y and x.bit_count()==1:rotulo=a['fontes'][x.bit_length()-1]
        elif x.bit_count()>1 or y.bit_count()>1:rotulo='EMPATE'
        else:rotulo='TRANSICAO'
        grupos[rotulo].append(i)
    return grupos


def acessos_comparados(m):
    saida=defaultdict(list)
    for i,g in enumerate(m['componente_segmento']):
        chave=tuple(m['componentes'][g]['selecionadas'])
        saida[chave].append(i)
    return saida


def alternativa(foto,m,segmentos,origem,cancelar=None):
    """Testa um destino explícito. Bloqueia Pipes físicos inteiros da rota de referência."""
    from .corredores_gis import _rota
    arv=m['arvore'] if origem is None else m['referencias_por_origem'][origem]['arvore']
    rede=RedeGIS(foto,arv['fontes'],cancelar)
    from .corredores_gis import _buscar
    ns={v for i in segmentos for v in rede.arestas[i][:2] if arv['distancias'][v] is not None}
    if not ns:return dict(situacao='Sem destino alcançável')
    u=min(ns,key=lambda n:(-arv['distancias'][n],rede.uids[n]))
    es=[]
    no=u
    while p:=arv['pais'][no]:
        verificar_cancelamento(cancelar)
        no,i=p
        es.append(i)
    if not es:return dict(situacao='O destino escolhido já é um ponto da origem')
    bloqueadas={rede.arestas[i][2] for i in es}
    fontes=[f for f,portas in rede.origens.items() if no in portas]
    f=min(fontes)
    via=_rota(rede,_buscar(rede,[f],cancelar,retiradas=bloqueadas,destino=u),u,cancelar)
    return dict(situacao='Alternativa sem Pipe físico compartilhado' if via else
                'Nenhuma alternativa independente da rota escolhida',
                destino=rede.uids[u],origem=f,referencia=es[::-1],alternativa=via)


def trabalho(foto,m,nome='Visão macro por origem'):
    return dict(uuid=uuid4().hex,nome=nome,projeto_uid=foto['projeto_uid'],topologia_uid=foto['uuid'],
        hipotese=foto.get('hipotese'),foto=foto,data_utc=datetime.now(timezone.utc).isoformat(),
        algoritmo=VERSAO,macro_origem=m,fontes=m['origens'],destinos=[],zonas=[],rotas=[],associacoes=[],
        tubulacoes=[],articulacoes=m['articulacoes'],pontes_segmentos=len(m['pontes']),parametros=m['parametros'])
