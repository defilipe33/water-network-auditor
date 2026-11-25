"""Dependência estrutural sobre a fotografia imutável de uma execução GIS."""

from bisect import bisect_left
from collections import defaultdict
from itertools import accumulate

from auditoria_fronteiras.modelos import verificar_cancelamento


class RedeGIS:
    """Indexa o grafo resolvido, preservando segmentos e a feição física."""

    def __init__(self, foto, origens=None, cancelar=None):
        self.foto=foto
        self.nos={n['uid']:i for i,n in enumerate(foto['nos'])}
        self.uids=list(self.nos)
        self.tubos={t['uid']:t for t in foto['tubos']}
        self.por_parte={u:t.get('feicao',u) for u,t in self.tubos.items()}
        self.partes=defaultdict(list)
        for u,f in self.por_parte.items():self.partes[f].append(u)
        self.adj=[[] for _ in self.nos]
        self.arestas=[]
        self.pipes=defaultdict(list)
        self.nos_parte=defaultdict(set)
        for e in foto['arestas']:
            verificar_cancelamento(cancelar)
            u,v=self.nos[e['a']],self.nos[e['b']]
            parte=e['tubo'];f=self.por_parte[parte]
            i=len(self.arestas)
            self.arestas.append((u,v,f,e['comprimento_m']))
            self.adj[u].append((v,i))
            if u!=v:self.adj[v].append((u,i))
            self.pipes[f].append(i)
            self.nos_parte[parte].update((u,v))
        if not self.arestas:raise ValueError('A execução não possui arestas GIS para analisar.')
        validas=set(foto['origens_validas'])
        selecionadas=validas if origens is None else set(origens)
        if not selecionadas<=validas:raise ValueError('Escolha apenas origens válidas nesta execução topológica.')
        portas={tuple(p):self.nos[n['uid']] for n in foto['nos'] for p in n['portas']}
        self.origens={}
        for r in foto['participantes']:
            if r['uuid'] not in selecionadas or r['tipo']!='ORIGEM':continue
            if any(tuple(p) not in portas for p in r['portas']):
                raise ValueError('Os vínculos topológicos gravados de uma origem estão incompletos.')
            self.origens[r['uuid']]=sorted({portas[tuple(p)] for p in r['portas']})
        if self.origens.keys()!=selecionadas or any(not ns for ns in self.origens.values()):
            raise ValueError('Os pontos de ligação das origens não estão disponíveis nesta execução.')
        self.ids_origens=sorted(self.origens)
        self.bits=[0]*len(self.nos)
        for i,u in enumerate(self.ids_origens):
            for v in self.origens[u]:self.bits[v]|=1<<i

    def nomes_origens(self,bits):
        ids=[]
        while bits:
            bit=bits & -bits
            ids.append(self.ids_origens[bit.bit_length()-1])
            bits-=bit
        return ids

    def destinos(self,registros):
        """Um destino é um nó persistido ou uma parte de feição cadastrada."""
        resultado={}
        for d in registros:
            if d['tipo']=='NO' and d['ref'] in self.nos:
                no=self.nos[d['ref']]
            elif d['tipo']=='PIPE' and d['ref'] in self.nos_parte:
                ref=d.get('no')
                if ref is not None and self.nos.get(ref) not in self.nos_parte[d['ref']]:
                    raise ValueError('O nó do destino não pertence à tubulação selecionada.')
                no=self.nos[ref] if ref else min(self.nos_parte[d['ref']])
            else:raise ValueError('Um destino não pertence à execução GIS selecionada.')
            if d['uid'] in resultado:raise ValueError('Há destinos com identidades repetidas.')
            resultado[d['uid']]=(d,no)
        return resultado

    def componentes(self,excluir=(),cancelar=None,escopo=None):
        """Busca única, sem ligar entre si as portas de uma origem."""
        bloqueadas=set(excluir)
        grupos=[-1]*len(self.nos) if escopo is None else {u:-1 for u in escopo}
        registros=[]
        for inicial in range(len(grupos)) if escopo is None else escopo:
            verificar_cancelamento(cancelar)
            if grupos[inicial]!=-1:continue
            i=len(registros);grupos[inicial]=i
            fila=[inicial];bits=0
            for u in fila:
                verificar_cancelamento(cancelar)
                bits|=self.bits[u]
                for v,e in self.adj[u]:
                    if self.arestas[e][2] in bloqueadas or grupos[v]!=-1:continue
                    grupos[v]=i;fila.append(v)
            registros.append((fila,bits))
        return grupos,registros


class PontesGIS:
    """DFS iterativa e intervalos de subárvore em multigrafo não dirigido."""

    def __init__(self,rede,cancelar=None):
        tamanho=len(rede.nos)
        self.ordem=[]
        self.inicio=[-1]*tamanho
        self.fim=[0]*tamanho
        self.grupo=[-1]*tamanho
        self.pontes={}
        self.articulacoes=set()
        self.componentes=[]
        minimo=[0]*tamanho
        raiz=[0]*tamanho
        for s in range(tamanho):
            if self.inicio[s]>=0:continue
            ini=len(self.ordem)
            self._visitar(s)
            minimo[s]=ini
            pilha=[(s,-1,iter(rede.adj[s]))]
            while pilha:
                verificar_cancelamento(cancelar)
                u,aresta_pai,adj=pilha[-1]
                vizinho=next(adj,None)
                if vizinho is not None:
                    v,e=vizinho
                    if e==aresta_pai:continue
                    if self.inicio[v]<0:
                        self._visitar(v)
                        minimo[v]=self.inicio[v]
                        raiz[u]+=1
                        pilha.append((v,e,iter(rede.adj[v])))
                    else:minimo[u]=min(minimo[u],self.inicio[v])
                    continue
                self.fim[u]=len(self.ordem)
                pilha.pop()
                if pilha:
                    pai,e_pai,_=pilha[-1]
                    minimo[pai]=min(minimo[pai],minimo[u])
                    if minimo[u]>self.inicio[pai]:self.pontes[aresta_pai]=u
                    if e_pai!=-1 and minimo[u]>=self.inicio[pai]:self.articulacoes.add(pai)
                elif raiz[u]>1:self.articulacoes.add(u)
            self.componentes.append((ini,len(self.ordem)))

    def _visitar(self,u):
        self.inicio[u]=len(self.ordem)
        self.grupo[u]=len(self.componentes)
        self.ordem.append(u)


class _Fenwick:
    def __init__(self,n):
        self.a=[0]*(n+1)

    def somar(self,i,delta):
        i+=1
        while i<len(self.a):
            self.a[i]+=delta
            i+=i & -i

    def prefixo(self,i):
        resultado=0
        while i:
            resultado+=self.a[i]
            i-=i & -i
        return resultado


def _contagens(posicoes,consultas,n,cancelar):
    """Distintos dentro e completamente contidos em intervalos de DFS."""
    eventos=sorted((i,f) for f,ps in posicoes.items() for i in ps)
    primeiros={f:min(ps) for f,ps in posicoes.items()}
    ultimos={f:max(ps) for f,ps in posicoes.items()}
    anterior={}
    distintos=_Fenwick(n);contidos=_Fenwick(n)
    i=0
    for fim,inicio,chave in sorted(consultas):
        verificar_cancelamento(cancelar)
        while i<len(eventos) and eventos[i][0]<fim:
            pos,f=eventos[i];i+=1
            if i%2048==0:verificar_cancelamento(cancelar)
            if f in anterior:distintos.somar(anterior[f],-1)
            distintos.somar(pos,1);anterior[f]=pos
            if pos==ultimos[f]:
                contidos.somar(primeiros[f],1)
        yield chave,(distintos.prefixo(fim)-distintos.prefixo(inicio),
                     contidos.prefixo(fim)-contidos.prefixo(inicio))


def _impactos_pontes(rede,dfs,destinos,cancelar):
    pontes=dfs.pontes
    n=len(dfs.ordem)
    metros=[0.]*n
    posicoes=defaultdict(set)
    chaves_por_grupo=defaultdict(set)
    for u,v,f,m in rede.arestas:
        verificar_cancelamento(cancelar)
        pos=max(dfs.inicio[u],dfs.inicio[v])
        metros[pos]+=m
        g=dfs.grupo[u]
        posicoes[(g,f)].add(pos)
        chaves_por_grupo[g].add(f)
    prefixo=list(accumulate(metros,initial=0.))
    dentro=[rede.bits[u] for u in dfs.ordem]
    esquerda=dentro.copy()
    direita=dentro.copy()
    for ini,fim in dfs.componentes:
        for i in range(ini+1,fim):esquerda[i]|=esquerda[i-1]
        for i in range(fim-2,ini-1,-1):direita[i]|=direita[i+1]
    for u in reversed(dfs.ordem):
        # Uma subárvore é particionada pelos intervalos dos filhos imediatos.
        tin=dfs.inicio[u];i=tin+1
        while i<dfs.fim[u]:
            dentro[tin]|=dentro[i]
            i=dfs.fim[dfs.ordem[i]]
    ds=sorted(dfs.inicio[v] for _,v in destinos.values())
    por_pipe=defaultdict(list)
    for d,v in destinos.values():
        if d['tipo']=='PIPE':por_pipe[rede.por_parte[d['ref']]].append(dfs.inicio[v])
    contagens=dict(_contagens(posicoes,[(dfs.fim[u],dfs.inicio[u],e) for e,u in pontes.items()
                                         if len(rede.pipes[rede.arestas[e][2]])==1],n,cancelar))
    for f,eds in rede.pipes.items():
        verificar_cancelamento(cancelar)
        if len(eds)!=1:continue
        e=eds[0];v,_,_,m=rede.arestas[e]
        g=dfs.grupo[v];a,b=dfs.componentes[g]
        if e not in pontes:
            yield f,dict(estado='AVALIADA',ponte=False,componentes_novos=0,perda_m=0.,afetadas=0,
                         destinos_afetados=0,destinos_retirados=len(por_pipe[f]),fontes_perdidas=[],
                         fontes_alternativas=rede.nomes_origens(esquerda[b-1]))
            continue
        filho=pontes[e];x,y=dfs.inicio[filho],dfs.fim[filho]
        f1=dentro[x];f2=(esquerda[x-1] if x>a else 0)|(direita[y] if y<b else 0)
        c1,c2=contagens[e]
        perdidos=0;comprimento=0.;afetadas=0
        externos=lambda p,q:bisect_left(ds,q)-bisect_left(ds,p)-sum(p<=v<q for v in por_pipe[f])
        if not f1 and f2:
            comprimento=prefixo[y]-prefixo[x]-m;afetadas=c1-1;perdidos=externos(x,y)
        elif f1 and not f2:
            comprimento=(prefixo[b]-prefixo[a])-(prefixo[y]-prefixo[x])
            afetadas=len(chaves_por_grupo[g])-c2;perdidos=externos(a,x)+externos(y,b)
        perdas=0
        if c1>1 or externos(x,y):perdas|=f2 & ~f1
        if len(chaves_por_grupo[g])>c2 or externos(a,x)+externos(y,b):perdas|=f1 & ~f2
        yield f,dict(estado='AVALIADA',ponte=True,componentes_novos=1,perda_m=max(0.,comprimento),
                     afetadas=afetadas,destinos_afetados=perdidos,destinos_retirados=len(por_pipe[f]),
                     fontes_perdidas=rede.nomes_origens(perdas),
                     fontes_alternativas=rede.nomes_origens(f1|f2) if f1 and f2 else [],
                     lados=[rede.nomes_origens(f1),rede.nomes_origens(f2)])


def simular(rede,retiradas,destinos,cancelar=None,antes=None):
    """Corte explícito de todas as arestas das feições escolhidas."""
    retiradas=set(retiradas)
    if not retiradas or not retiradas<=rede.pipes.keys():raise ValueError('Escolha tubulações da execução selecionada.')
    grupos0,componentes0=antes if antes is not None else rede.componentes(cancelar=cancelar)
    grupos,componentes=rede.componentes(retiradas,cancelar)
    impactos=[];comprimentos=[0.]*len(componentes);afetadas=set();perda_m=0.
    por_grupo=defaultdict(set)
    partes_por_grupo=defaultdict(set)
    fontes_perdidas=0;fontes_alternativas=0
    for i,(u,v,f,m) in enumerate(rede.arestas):
        verificar_cancelamento(cancelar)
        if f in retiradas:continue
        g=grupos[u];novo=componentes[g][1];antigo=componentes0[grupos0[u]][1]
        por_grupo[g].add(f);comprimentos[g]+=m
        partes_por_grupo[g].add(rede.foto['arestas'][i]['tubo'])
        perda=antigo & ~novo
        fontes_perdidas|=perda
        if perda and novo:fontes_alternativas|=novo
        if not novo and antigo:perda_m+=m;afetadas.add(f)
    for d,u in destinos.values():
        verificar_cancelamento(cancelar)
        b0=componentes0[grupos0[u]][1]
        direto=d['tipo']=='PIPE' and rede.por_parte[d['ref']] in retiradas
        b=0 if direto else componentes[grupos[u]][1]
        impactos.append(dict(uid=d['uid'],antes=rede.nomes_origens(b0),depois=rede.nomes_origens(b),
                             direto=direto,perdeu=bool(b0 and not b and not direto)))
        if not direto:
            fontes_perdidas|=b0 & ~b
            if b0 & ~b and b:fontes_alternativas|=b
    fotos=[]
    fontes_remanescentes=0
    for g,(vs,bits) in enumerate(componentes):
        verificar_cancelamento(cancelar)
        if por_grupo[g]:fontes_remanescentes|=bits
        fotos.append(dict(nos=[rede.uids[v] for v in vs],tubos=sorted(por_grupo[g]),partes=sorted(partes_por_grupo[g]),comprimento_m=comprimentos[g],
                          origens=rede.nomes_origens(bits),perdeu=not bits and bool(componentes0[grupos0[vs[0]]][1])))
    return dict(retiradas=sorted(retiradas),componentes=fotos,componentes_novos=len(componentes)-len(componentes0),
                perda_m=perda_m,afetadas=len(afetadas),tubos_afetados=sorted(afetadas),destinos=impactos,
                destinos_afetados=sum(x['perdeu'] for x in impactos),destinos_retirados=sum(x['direto'] for x in impactos),
                fontes_perdidas=rede.nomes_origens(fontes_perdidas),
                fontes_alternativas=rede.nomes_origens(fontes_alternativas),
                fontes_remanescentes=rede.nomes_origens(fontes_remanescentes))


def avaliar_cortes(rede,destinos,cancelar=None,etapa=lambda *_:None,orcamento=4_000_000):
    """Para feições partidas usa buscas exatas com orçamento explícito."""
    etapa(0,'Identificando pontes e articulações')
    dfs=PontesGIS(rede,cancelar)
    resultados=dict(_impactos_pontes(rede,dfs,destinos,cancelar))
    antes=rede.componentes(cancelar=cancelar)
    custo=len(rede.nos)+len(rede.arestas)+len(destinos)
    consumido=0
    etapa(0,'Avaliando tubulações com segmentos agrupados')
    for f,es in rede.pipes.items():
        verificar_cancelamento(cancelar)
        if f in resultados:continue
        ponte=any(e in dfs.pontes for e in es)
        if consumido+custo>orcamento:
            resultados[f]=dict(estado='INDETERMINADA_LIMITE',ponte=ponte)
            continue
        consumido+=custo
        teste=simular(rede,[f],destinos,cancelar,antes)
        resultados[f]={k:teste[k] for k in ('componentes_novos','perda_m','afetadas','destinos_afetados',
                                             'destinos_retirados','fontes_perdidas','fontes_alternativas')}
        resultados[f].update(estado='AVALIADA',ponte=ponte)
        resultados[f]['perdas_destino']={d['uid']:d['depois'] for d in teste['destinos']
                                         if not d['direto'] and d['antes']!=d['depois']}
    return resultados,dfs,antes
