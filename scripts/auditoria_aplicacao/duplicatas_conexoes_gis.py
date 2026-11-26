"""Audita ligações por identidade de parte e posição na linha métrica."""

from bisect import bisect_left
from collections import Counter, defaultdict
from itertools import product
from math import dist, floor, fsum, isfinite

from auditoria_fronteiras.entradas import digest
from auditoria_fronteiras.modelos import verificar_cancelamento
from .investigacao_gis import geometria


CATEGORIAS={'CONEXAO_T','EXTREMIDADES_PROXIMAS','CRUZAMENTO'}
ROTULOS={
    'EXATA':'Duplicata exata','PROVAVEL':'Provável duplicata','CONFLITO':'Decisões conflitantes',
    'LOCAL':'Registros distintos na mesma localização','REVISAO':'Revisões da mesma relação',
    'VINCULO':'Candidata e sua revisão declarada',
    'RELACIONADA_T':'Cruzamento representado também por conexão em T',
}


def _referenciar(r, tubos):
    portas=r.get('portas',())
    if len(portas)<2:return None
    dirigidas=bool(r.get('dirigida') or r.get('direcao'))
    posicoes=[]
    for u,f in portas:
        g=tubos.get(u)
        if g is None or not isinstance(f,(float,int)) or not 0<=f<=1:return None
        comprimento,linha=g
        if not comprimento or not isfinite(comprimento):return None
        wkb=r.get('geometrias_rede',{}).get(u)
        if wkb and wkb!=bytes(linha.asWkb()).hex():return None
        p=linha.interpolate(comprimento*f).asPoint()
        posicoes.append((u,float(f),comprimento*f,(p.x(),p.y())))
    if not dirigidas:posicoes.sort()
    xy=tuple(fsum(p[3][i] for p in posicoes)/len(posicoes) for i in range(2))
    tipo=r.get('categoria_candidata') or (r.get('tipo') if r.get('tipo') in CATEGORIAS else None)
    return dict(r=r,uid=r.get('uuid') or r['uid'],posicoes=posicoes,xy=xy,tipo=tipo,
                sentido=str(r.get('direcao') or dirigidas),natureza=r.get('situacao') if 'uuid' in r else None)


def _classificar(a,b,tol):
    x,y=a['r'],b['r']
    if (x.get('candidato')==b['uid'] and 'uuid' not in y or y.get('candidato')==a['uid'] and 'uuid' not in x):
        return 'VINCULO'
    compat=a['sentido']==b['sentido'] and (not a['tipo'] or not b['tipo'] or a['tipo']==b['tipo'])
    mesmas=compat and len(a['posicoes'])==len(b['posicoes']) and all(
        p[0]==q[0] and abs(p[2]-q[2])<=tol for p,q in zip(a['posicoes'],b['posicoes']))
    if not mesmas or dist(a['xy'],b['xy'])>tol:
        return 'LOCAL' if dist(a['xy'],b['xy'])<=tol else None
    if {x.get('decisao'),y.get('decisao')}=={'CONFIRMADA','SEPARADA'}:return 'CONFLITO'
    exata=(a['tipo']==b['tipo'] and a['natureza']==b['natureza']
           and all(p[1]==q[1] for p,q in zip(a['posicoes'],b['posicoes'])))
    return 'EXATA' if exata else 'PROVAVEL'


def auditar(candidatas,relacoes,tubos,tolerancia=.20,cancelar=None,*,historico=()):
    if not isinstance(tolerancia,(int,float)) or not isfinite(tolerancia) or tolerancia<0:
        raise ValueError('Informe uma tolerância métrica finita e não negativa.')
    atuais={r['uuid']:r for r in relacoes if r.get('tipo')=='CONEXAO'}
    elegiveis=[r for r in atuais.values() if not r.get('excluido') and not r.get('substituida_por')]
    registros=[*elegiveis,*(r for r in candidatas if r.get('tipo') in CATEGORIAS)]
    relacao_t={r['uid']:r['prioridade_cruzamento']['referencia_t'] for r in registros
               if r.get('prioridade_cruzamento',{}).get('referencia_t')}
    ids={u for r in registros for u,_ in r.get('portas',())}
    geometrias={}
    for u in ids:
        verificar_cancelamento(cancelar)
        t=tubos.get(u,{})
        g=t.get('geom') or geometria(t.get('wkb'))
        if g:geometrias[u]=g.length(),g
    saida=[]
    grupos=defaultdict(list)
    grade=defaultdict(list)
    recs=[]
    pendentes=[]
    faixa=max(tolerancia,1e-8)
    for r in registros:
        verificar_cancelamento(cancelar)
        a=_referenciar(r,geometrias)
        if a is None:
            pendentes.append(r.get('uuid') or r['uid'])
            continue
        i=len(recs)
        recs.append(a)
        grupos[tuple(p[0] for p in a['posicoes'])].append((a['posicoes'][0][2],i))
        grade[tuple(floor(x/faixa) for x in a['xy'])].append(i)
    vistos=set()
    def comparar(i,j):
        verificar_cancelamento(cancelar)
        if i==j:return
        par=tuple(sorted((i,j)))
        if par in vistos:return
        vistos.add(par)
        a,b=recs[i],recs[j]
        tipo=('RELACIONADA_T' if relacao_t.get(a['uid'])==b['uid'] or relacao_t.get(b['uid'])==a['uid']
              else _classificar(a,b,tolerancia))
        if not tipo:return
        registros=[a['r'],b['r']]
        uids=sorted((a['uid'],b['uid']))
        principal=min(registros,key=lambda r:('uuid' not in r,
            r.get('decisao') not in ('CONFIRMADA','SEPARADA'),r.get('uuid') or r['uid']))
        saida.append(dict(uid=digest([tipo,uids]),tipo=tipo,registros=registros,
                          principal=principal.get('uuid') or principal['uid'],distancia_m=dist(a['xy'],b['xy'])))
    for grupo in grupos.values():
        grupo.sort()
        for i,(m,u) in enumerate(grupo):
            inicio=bisect_left(grupo,(m-tolerancia,-1),0,i)
            for _,v in grupo[inicio:i]:comparar(u,v)
    for i,a in enumerate(recs):
        x,y=(floor(z/faixa) for z in a['xy'])
        for pos in product(range(x-1,x+2),range(y-1,y+2)):
            for j in grade[pos]:
                if j<i:comparar(i,j)
    quant=Counter(r['uuid'] for r in historico if r.get('tipo')=='CONEXAO')
    for u,n in quant.items():
        if n>1 and u in atuais:
            saida.append(dict(uid=digest(['revisoes',u]),tipo='REVISAO',registros=[atuais[u]],principal=u,revisoes=n))
    ordem={k:i for i,k in enumerate(('CONFLITO','EXATA','PROVAVEL','RELACIONADA_T','LOCAL','VINCULO','REVISAO'))}
    return sorted(saida,key=lambda r:(ordem[r['tipo']],r['uid'])),pendentes


def equivalentes(nova,relacoes,candidatas,tubos,tolerancia):
    """Verifica a inscrição nova somente entre registros com as mesmas partes."""
    ps=Counter(p[0] for p in nova['portas'])
    u='nova-conexao-a-conferir'
    rel=[r for r in relacoes if r.get('tipo')=='CONEXAO' and Counter(p[0] for p in r.get('portas',()))==ps]
    cand=[r for r in candidatas if Counter(p[0] for p in r.get('portas',()))==ps]
    if not rel and not cand:return []
    resultados,_=auditar(cand,[*rel,dict(nova,uuid=u,tipo='CONEXAO')],tubos,tolerancia)
    return [x for r in resultados if r['tipo'] in ('EXATA','PROVAVEL','CONFLITO')
            and any(x.get('uuid')==u for x in r['registros']) for x in r['registros'] if x.get('uuid')!=u]
