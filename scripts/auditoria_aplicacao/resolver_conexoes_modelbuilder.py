"""Investiga relações de um trecho e prepara um cenário explícito de revisão."""

from collections import defaultdict, deque
from copy import deepcopy
from math import dist, isfinite

from auditoria_fronteiras.entradas import digest
from auditoria_fronteiras.modelos import verificar_cancelamento
from . import duplicatas_conexoes_gis
from .investigacao_gis import geometria
from .validacao_modelbuilder_gis import EPS


MANTER='MANTER'
EXCLUIR='FORA_DA_HIPOTESE'
REJEITAR='SEM_CONEXAO'
DECISOES={MANTER:'Manter na hipótese',EXCLUIR:'Deixar fora da nova hipótese',REJEITAR:'Registrar Sem conexão'}


def _ponto(tubos,porta):
    u,f=porta
    item=tubos.get(u)
    g=geometria(item.get('wkb')) if item else None
    if g and isinstance(f,(int,float)) and isfinite(f) and 0<=f<=1:
        p=g.interpolate(f*g.length()).asPoint()
        return p.x(),p.y()
    return None


def _cadeia(registros,a,b):
    amigos=defaultdict(list)
    for r in registros:
        portas=list(map(tuple,r['portas']))
        if not portas:continue
        for p in portas[1:]:
            amigos[portas[0]].append((p,r['uuid']))
            amigos[p].append((portas[0],r['uuid']))
    fila=deque([a])
    antes={a:None}
    while fila:
        u=fila.popleft()
        if u==b:
            caminho=set()
            while antes[u]:
                u,uid=antes[u]
                caminho.add(uid)
            return caminho
        for v,uid in amigos[u]:
            if v not in antes:
                antes[v]=(u,uid)
                fila.append(v)
    return set()


def investigar(foto,pipe,vigentes,cancelar=None):
    """Classifica as relações ancoradas na parte, intervalo e nós da ocorrência."""
    tubos={t['uid']:t for t in foto['tubos']}
    parte=pipe['parte']
    t=tubos.get(parte)
    if t is None:return dict(ligacoes=[],tubos=tubos,parte=parte,duplicatas=[])
    comprimento=t['comprimento_m']
    tol=foto['parametros']['tolerancia']
    a,b=(parte,pipe['inicio']),(parte,pipe['fim'])
    ids_nos={pipe.get('no_a'),pipe.get('no_b')}
    nos={n['uid']:n for n in foto['nos'] if n['uid'] in ids_nos}
    portas_no={tuple(p) for n in nos.values() for p in n['portas']}
    distancia_frac=tol/comprimento if comprimento else 0.
    participantes={r['uuid']:r for r in foto.get('participantes',()) if r['tipo']=='CONEXAO'}
    atual={r['uuid']:r for r in vigentes if r['tipo']=='CONEXAO'}
    candidatos={r['uid']:r for r in foto.get('diagnosticos',()) if r.get('portas')}
    ligacoes=[]
    for u,r in {**atual,**participantes}.items():
        verificar_cancelamento(cancelar)
        if r.get('excluido') or r.get('substituida_por'):continue
        portas=list(map(tuple,r.get('portas',())))
        fs=[f for pu,f in portas if pu==parte]
        if not portas_no.intersection(portas) and not any(a[1]-distancia_frac<=f<=b[1]+distancia_frac for f in fs):
            continue
        referencia=foto.get('resolucoes_conexoes',{}).get(u)
        cand=candidatos.get(r.get('candidato'))
        pontos=[_ponto(tubos,p) for p in portas]
        motivos=[f'Porta indisponível na parte {p[0]} ({p[1]}).' for p,xy in zip(portas,pontos) if xy is None]
        for pu,_ in portas:
            wkb=r.get('geometrias_rede',{}).get(pu)
            if wkb and pu in tubos and (g:=geometria(tubos[pu].get('wkb'))) and wkb!=bytes(g.asWkb()).hex():
                motivos.append(f'O traçado da parte {pu} mudou desde a revisão da ligação.')
        if r.get('candidato') and not cand:
            motivos.append('Candidata original ausente dos diagnósticos desta execução.')
        elif cand and list(map(tuple,cand['portas']))!=portas:
            motivos.append('As portas da candidata nesta execução diferem da decisão registrada.')
        incompativel=bool(motivos) or referencia=='REFERENCIA_ALTERADA'
        if not referencia and motivos:
            referencia='REFERENCIA_ALTERADA'
        if not r.get('habilitado',True):
            motivos.append('Ligação desabilitada no cadastro.')
        ligacoes.append(dict(registro=r,participa=u in participantes,situacao=referencia or 'FORA_DA_HIPOTESE',
            ultima_revisao=atual.get(u,{}).get('rev'),fracoes=fs,pontos=pontos,motivos=motivos,
            referencia_incompativel=incompativel,
            coordenada=_ponto(tubos,(parte,fs[0])) if fs else None))
    elo=_cadeia([x['registro'] for x in ligacoes if x['situacao']=='APLICADA'],a,b)
    ligacoes.sort(key=lambda x:(min(x['fracoes'],default=2.),x['registro']['uuid']))
    distancias=[(f,x['registro']['uuid']) for x in ligacoes for f in x['fracoes']]
    for i,x in enumerate(ligacoes):
        r=x['registro']
        x.update(letra=chr(65+i) if i<26 else f'L{i+1}',na_cadeia=r['uuid'] in elo,
            distancia_m=min((abs(f-g)*comprimento for f in x['fracoes'] for g,u in distancias if u!=r['uuid']),default=None))
    similares,_=duplicatas_conexoes_gis.auditar([], [x['registro'] for x in ligacoes],tubos,tol,cancelar)
    return dict(ligacoes=ligacoes,tubos=tubos,parte=parte,nos=nos,tolerancia=tol,
                comprimento_m=pipe['comprimento_m'],intervalo=[a[1],b[1]],duplicatas=similares)


def _reposicionar(r,portas,tubos,tolerancia):
    if r.get('dirigida') or r.get('direcao'):
        raise ValueError('Revise relações direcionais no editor de conectividade.')
    if len(set(portas))!=len(portas) or len(portas)<2:
        raise ValueError('A relação precisa de ao menos duas portas diferentes.')
    pontos=[_ponto(tubos,p) for p in portas]
    if any(p is None for p in pontos) or any(dist(p,q)>tolerancia+EPS for p in pontos for q in pontos):
        raise ValueError('Os pontos declarados não identificam uma ligação dentro da tolerância do grafo.')
    dados={k:v for k,v in r.items() if k not in ('candidato','geometrias_rede','pontos_rede','wkb')}
    return dict(dados,portas=[list(p) for p in portas],candidato=None,pontos_rede=pontos,
                candidato_anterior=r.get('candidato'),portas_anteriores=r['portas'])


def planejar(foto,analise,escolhas,*,edicoes=None,consolidar=None,notas=None):
    """Retorna as revisões a gravar e os participantes a executar em memória."""
    registros={x['registro']['uuid']:x for x in analise['ligacoes']}
    edicoes=edicoes or {}
    notas=notas or {}
    if set(escolhas)!=set(registros) or (set(edicoes)|set(notas))-set(registros) or set(escolhas.values())-DECISOES.keys():
        raise ValueError('Confira a decisão para cada ligação listada.')
    parte,tubos,tol=analise['parte'],analise['tubos'],analise['tolerancia']
    participantes={r['uuid']:r for r in foto.get('participantes',())}
    operacoes={}
    manter=[u for u,d in escolhas.items() if d==MANTER]
    if consolidar is not None:
        if consolidar not in manter or len(manter)<2:
            raise ValueError('Escolha uma ligação principal e pelo menos duas ligações a manter.')
        alvo=edicoes.get(consolidar,registros[consolidar]['registro']['portas'])
        fs=[f for u,f in alvo if u==parte]
        if len(fs)!=1:
            raise ValueError('A ligação principal precisa identificar uma única posição na tubulação investigada.')
        edicoes=dict(edicoes)
        for u in manter:
            x=registros[u]
            ps=edicoes.get(u,x['registro']['portas'])
            f=[p[1] for p in ps if p[0]==parte]
            if len(f)!=1 or abs(fs[0]-f[0])*tubos[parte]['comprimento_m']>tol+EPS:
                raise ValueError('A consolidação exige posições próximas e inequívocas na mesma parte.')
            proposta=[(p,fs[0] if p==parte else fr) for p,fr in ps]
            if list(map(tuple,ps))!=proposta:
                edicoes[u]=proposta
        if not edicoes:
            # Relações com as mesmas portas representam a mesma operação.
            pp=set(map(tuple,alvo))
            iguais=[u for u in manter if u!=consolidar
                    and set(map(tuple,registros[u]['registro']['portas']))==pp
                    and not registros[u]['registro'].get('direcao') and not registros[u]['registro'].get('dirigida')]
            escolhas={**escolhas,**dict.fromkeys(iguais,EXCLUIR)}
    for u,d in escolhas.items():
        x=registros[u]
        r=x['registro']
        nova=None
        if d==MANTER:
            if not r.get('habilitado',True):
                raise ValueError('Habilite a ligação no cadastro e confira sua revisão antes de incluí-la.')
            if x['referencia_incompativel'] and u not in edicoes:
                raise ValueError('Revise a referência alterada antes de incluir esta ligação.')
            if u in edicoes:
                nova=_reposicionar(r,list(map(tuple,edicoes[u])),tubos,tol)
            if r.get('decisao')!='CONFIRMADA' or u in notas:
                nova=dict(nova or r,decisao='CONFIRMADA',acompanhamento='VERIFICADO')
            participantes[u]=nova or r
        elif d==REJEITAR:
            ps=list(map(tuple,edicoes.get(u,r['portas'])))
            if any(_ponto(tubos,p) is None for p in ps) or len(set(ps))<2:
                raise ValueError('Reassocie as portas incompatíveis antes de gravar uma rejeição.')
            nova=dict(r,portas=[list(p) for p in ps],decisao='SEPARADA',acompanhamento='VERIFICADO')
            if len(ps)==2 and all(f in (0.,1.) for _,f in ps):
                nova['categoria_candidata']='EXTREMIDADES_PROXIMAS'
            if x['referencia_incompativel'] or u in edicoes:
                nova.update(candidato=None,candidato_anterior=r.get('candidato'),portas_anteriores=r['portas'])
            participantes[u]=nova
        else:
            participantes.pop(u,None)
        if nova:
            if x['ultima_revisao']!=r['rev']:
                raise ValueError('A ligação mudou desde a execução. Confira a revisão vigente antes de alterar suas portas ou veredito.')
            nova=deepcopy(nova)
            nova.update(nota=notas.get(u,r.get('nota','')),habilitado=True)
            if u in edicoes or d==REJEITAR:
                for campo in ('geometrias_rede','wkb','pontos_rede'):nova.pop(campo,None)
            participantes[u]=nova
        if nova or x['participa']!=(u in participantes):
            operacoes[u]=dict(rev=r['rev'],antecessora=x['ultima_revisao'],incluir=u in participantes,dados=nova)
    if len({r['candidato'] for r in participantes.values() if r.get('candidato')})!=sum(
           bool(r.get('candidato')) for r in participantes.values()):
        raise ValueError('A nova hipótese selecionaria mais de uma interpretação da mesma candidata.')
    dados=dict(escolhas=escolhas,notas=notas,revisoes={u:x['ultima_revisao'] for u,x in registros.items()},
               operacoes=operacoes,consolidada_em=consolidar)
    return dict(**dados,assinatura=digest(dados),participantes=list(participantes.values()))


def impacto(antes,depois,analise,conjuntos,plano=None):
    partes={analise['parte']}|{u for x in analise['ligacoes'] for u,_ in x['registro']['portas']}
    if plano:
        partes.update(u for op in plano['operacoes'].values() for u,_ in (op['dados'] or {}).get('portas',()))
    no_a={n['uid'] for n in antes['nos']}
    no_b={n['uid'] for n in depois['nos']}
    def arestas(f):
        return [{**e,'uid':digest(['segmento_gis',e['tubo'],e['inicio'],e['fim']])}
                for e in f['arestas'] if e['tubo'] in partes]
    a,b=arestas(antes),arestas(depois)
    mudancas={e['uid']:(e['a'],e['b']) for e in a}
    segs={e['uid']:(e['a'],e['b']) for e in b}
    partes_alteradas={e['tubo'] for e in (*a,*b) if mudancas.get(e['uid'])!=segs.get(e['uid'])}
    def componentes(f):
        return [g for g in f['componentes'] if partes.intersection(g['tubos'])]
    eqs=[e for e in antes.get('equipamentos',()) if any(
        partes_alteradas.intersection({u for u,_ in d.get('portas',())}|set(d.get('tubos_uid',())))
        for d in e.get('declaracoes',()))]
    sets=[s['nome'] for s in conjuntos if any(m.get('parte') in partes_alteradas
        or m.get('uid') in (no_a-no_b) or any(u in partes_alteradas for u,_ in m.get('portas',()))
        for m in s['membros'])]
    return dict(antes=a,depois=b,novos_nos=sorted(no_b-no_a),removidos_nos=sorted(no_a-no_b),
                nos_antes=[n for n in antes['nos'] if n['uid'] in analise['nos']],
                nos_depois=[n for n in depois['nos'] if n['uid'] in no_b-no_a],
                componentes_antes=componentes(antes),componentes_depois=componentes(depois),
                afetadas=sorted(partes_alteradas),equipamentos=eqs,conjuntos=sets)
