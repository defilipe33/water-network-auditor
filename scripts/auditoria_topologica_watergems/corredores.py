"""Rotas escolhidas sobre o grafo validado, sem inferência de vazão ou novas ligações.

Predecessores identificam cada aresta paralela. Dijkstra multi-origem escolhe a
origem de menor custo; alternativas usam exclusões temporárias limitadas de arestas.
"""
from collections import defaultdict
import math
from heapq import heappush,heappop
from itertools import count
import networkx as nx
from . import decisoes as db
from .conjuntos_investigacao import vinculo_wg


def comprimentos_metricos(pacote):
    from qgis.core import QgsCoordinateReferenceSystem,QgsUnitTypes
    params=pacote['resultado']['meta']['parametros'];crs=QgsCoordinateReferenceSystem(params['crs'])
    if not params.get('espacial_habilitado') or not crs.isValid() or crs.isGeographic() or crs.mapUnits()!=QgsUnitTypes.DistanceMeters:return {}
    return {i:g.length() for i,g in (pacote.get('geometrias') or {}).items() if not g.isEmpty() and g.type()==1 and math.isfinite(g.length()) and g.length()>0}


def resolver_terminal(g,elementos,terminal):
    i=int(terminal['id'] if isinstance(terminal,dict) else terminal)
    e=elementos.get(i)
    if not e or e.get('excluido') is not False:raise ValueError(f'Elemento {i} ausente ou excluído')
    if e['familia'] not in ('NO','DISPOSITIVO'):raise ValueError(f'{i} é tubulação; selecione um nó ou dispositivo válido')
    portas=[n for n in g if n[0]==i]
    if isinstance(terminal,dict) and terminal.get('porta') is not None:
        porta=(i,terminal['porta'])
        if porta not in portas:raise ValueError(f'Porta de {i} indisponível na perspectiva')
        return porta
    if not portas:raise ValueError(f'Elemento {i} indisponível na perspectiva (atividade ou vínculo)')
    if len(portas)!=1:raise ValueError(f'Elemento {i} possui múltiplas portas: '+', '.join(str(n[1]) for n in portas)+'. Escolha a porta explicitamente; não serão conectadas entre si.')
    return portas[0]


def buscar_terminais(pacote,modo,texto='',limite=200):
    if modo not in db.MODOS:raise ValueError('Perspectiva indisponível')
    g=pacote['topologia']['estrutural' if modo=='ESTRUTURAL' else 'potencial']['grafo'];el=pacote['topologia']['modelo']['elementos'];texto=texto.strip().casefold();saida=[]
    for n in sorted(g,key=repr):
        e=el.get(n[0],{})
        if e.get('familia') not in ('NO','DISPOSITIVO') or e.get('excluido') is not False:continue
        if texto and texto!=str(n[0]) and texto not in str(e.get('label','')).casefold():continue
        saida.append(dict(id=n[0],porta=n[1],label=e.get('label'),tipo=e.get('tipo'),uid=e.get('uid')))
        if len(saida)>=limite:break
    return saida


def resumir_selecao(pacote,modo,ids,origens=(),destinos=(),grafo=None):
    """Componentes fracos da seleção efetiva, após combinações/edição manual."""
    g=grafo if grafo is not None else pacote['topologia']['estrutural' if modo=='ESTRUTURAL' else 'potencial']['grafo'];ids=set(ids);s=nx.Graph();pipes=[]
    for a,b,d in g.edges(data=True):
        if d.get('natureza')=='TUBULACAO' and d['elemento'] in ids:s.add_edge(a,b);pipes.append((a,b,d['elemento']))
    for a,b,d in g.edges(data=True):
        if d.get('natureza')=='DISPOSITIVO' and a in s and b in s:s.add_edge(a,b)
    def norm(t):return (int(t['id']),t.get('porta','E')) if isinstance(t,dict) else tuple(t)
    origens=[norm(o) for o in origens];destinos=[norm(o) for o in destinos];grupos=list(nx.connected_components(s));index={n:k for k,ns in enumerate(grupos) for n in ns};tubos=defaultdict(set)
    for a,b,i in pipes:tubos[index[a]].add(i)
    return dict(tubulacoes=len({i for _,_,i in pipes}),componentes=[dict(origens=[o for o in origens if o in ns],destinos=[t for t in destinos if t in ns],tubulacoes=sorted(tubos[k])) for k,ns in enumerate(grupos)],
        criterio='Conectividade fraca da seleção efetiva; não comprova alcance dirigido ou continuidade hidráulica. Componentes sem origem selecionada podem resultar de remoção manual/combinada.')


def calcular(pacote,modo,origens,destinos,criterio='ARESTAS',alternativas=0,
             metodo='CORREDORES',comprimentos=None,progresso=None,cancelado=None,restricoes=None,_trabalho=None):
    if restricoes is not None:
        from .restricoes_percurso import calcular as restrito
        return restrito(pacote,modo,origens,destinos,criterio,alternativas,metodo,comprimentos,progresso,cancelado,restricoes)
    if modo not in db.MODOS:raise ValueError('Perspectiva indisponível')
    if metodo not in ('CORREDORES','CAMINHO'):raise ValueError('Método de rotas inválido')
    if criterio not in ('ARESTAS','COMPRIMENTO'):raise ValueError('Critério de caminho inválido')
    if not origens or not destinos:raise ValueError('Selecione pelo menos uma origem e um destino. Pontes não serão incluídas automaticamente.')
    if metodo=='CAMINHO' and (len(origens)!=1 or len(destinos)!=1):raise ValueError('Caminho entre pontos requer exatamente uma origem e um destino')
    if not isinstance(alternativas,int) or not 0<=alternativas<=3:raise ValueError('Use de zero a três alternativas por destino')
    if alternativas and len(destinos)>50:raise ValueError('Alternativas limitadas a 50 destinos por cálculo; reduza a seleção ou desabilite alternativas')
    def passo(texto,n=None,total=None):
        if cancelado and cancelado():raise InterruptedError('Cálculo cancelado; nenhum conjunto publicado')
        if progresso:progresso(texto,n,total)
    passo('Verificando terminais e perspectiva')
    r=pacote['topologia']['estrutural' if modo=='ESTRUTURAL' else 'potencial'];g=_trabalho['grafo'] if _trabalho is not None else r['grafo'];el=pacote['topologia']['modelo']['elementos']
    fontes=sorted(set(resolver_terminal(g,el,o) for o in origens),key=repr)
    if comprimentos is None:comprimentos=comprimentos_metricos(pacote)
    destinos_validos=[];inalcancaveis=[]
    for t in destinos:
        try:
            p=resolver_terminal(g,el,t)
            if p not in destinos_validos:destinos_validos.append(p)
        except ValueError as e:inalcancaveis.append(dict(destino=t,motivo=str(e),interrupcoes=[]))
    arestas={};pesos={};pesos_base={};lex=bool(_trabalho and _trabalho['lexicografica']);zero=(0,0) if lex else 0
    def somar(a,b):return (a[0]+b[0],a[1]+b[1]) if lex else a+b
    numero_arestas=g.number_of_edges();numero_nos=g.number_of_nodes()
    for n,(a,b,k,d) in enumerate(g.edges(keys=True,data=True)):
        if n%1024==0:passo('Preparando arestas identificadas',n,numero_arestas)
        i=d['elemento'];tubo=d.get('natureza')=='TUBULACAO';comprimento=comprimentos.get(i) if tubo else 0
        if criterio=='COMPRIMENTO' and tubo and (comprimento is None or not math.isfinite(comprimento) or comprimento<=0):raise ValueError(f'Comprimento métrico validado indisponível para tubulação {i}; use número de arestas ou valide a referência espacial')
        chave=(a,b,k);peso=1 if criterio=='ARESTAS' else comprimento;pesos_base[chave]=peso
        if lex:
            from .restricoes_percurso import passagens
            pesos[chave]=(passagens(a,b,d,_trabalho),peso)
        else:pesos[chave]=peso
        arestas[chave]=dict(inicio=a,fim=b,elemento=i,natureza=d.get('natureza'),comprimento_m=comprimento)
    # Dijkstra único para todas as origens/destinos. Ordem estável dá desempate
    # reproduzível; não significa que a rota é única ou hidraulicamente preferível.
    passo('Calculando caminhos de menor custo a partir das origens')
    # Guarda um predecessor por nó, não listas de caminho para todos os nós:
    # memória linear mesmo em redes longas. Portas nunca são fundidas por ID.
    def buscar(inicios,alvos,bloqueio=None):
        ds={n:zero for n in inicios};ps={};seq=count();fila=[];fechados=set();pendentes=set(alvos)
        if not pendentes:return ds,ps
        for n in inicios:heappush(fila,(zero,next(seq),n))
        while fila:
            custo,_,a=heappop(fila)
            if a in fechados:continue
            fechados.add(a);pendentes.discard(a)
            if not pendentes:break
            if len(fechados)%1024==0:passo('Calculando rotas dirigidas',len(fechados),numero_nos)
            for b,paralelas in g[a].items():
                for k,d in paralelas.items():
                    if bloqueio==(d.get('natureza'),d['elemento']):continue
                    novo=somar(custo,pesos[a,b,k])
                    if b not in fechados and (b not in ds or novo<ds[b]):
                        ds[b]=novo;ps[b]=(a,b,k);heappush(fila,(novo,next(seq),b))
        return ds,ps
    dist,pais=buscar(fontes,destinos_validos)
    def reconstruir(destino,pais):
        ns=[destino];es=[];n=destino
        while n in pais:
            chave=pais[n];es.append(chave);n=chave[0];ns.append(n)
        return list(reversed(ns)),list(reversed(es))
    fracos={n:k for k,ns in enumerate(nx.weakly_connected_components(g)) for n in ns};avisos_comp=defaultdict(list);comp_elemento=defaultdict(set)
    for n,k in fracos.items():comp_elemento[n[0]].add(k)
    for d in r.get('diagnosticos',[]):
        ks=comp_elemento.get(d.get('id'),set())|comp_elemento.get(d.get('relacionado'),set())
        for k in ks:avisos_comp[k].append(d)
    rotas=[];alternativas_rotas=[];contagens=defaultdict(set);qrotas=defaultdict(set);disps=defaultdict(set);selecionado=nx.Graph()
    def rota(caminho,chaves,destino,numero,alternativa=False):
        es=[arestas[n] for n in chaves];tubos=list(dict.fromkeys(e['elemento'] for e in es if e['natureza']=='TUBULACAO'));dispositivos=sorted({e['elemento'] for e in es if e['natureza']=='DISPOSITIVO'}|{n[0] for n in caminho if el.get(n[0],{}).get('familia')=='DISPOSITIVO'})
        ls=[e['comprimento_m'] for e in es if e['natureza']=='TUBULACAO'];comprimento=sum(ls) if all(v is not None for v in ls) else None
        return dict(uid=str(numero),origem=caminho[0],destino=destino,tubulacoes=tubos,dispositivos=dispositivos,
            custo=sum(pesos_base[k] for k in chaves),custo_lexicografico=[sum(pesos[k][0] for k in chaves),sum(pesos_base[k] for k in chaves)] if lex else None,comprimento_m=comprimento,
            quantidade_arestas=len(es),portas=caminho,arestas=es,alternativa=alternativa)
    for pos,destino in enumerate(destinos_validos):
        passo('Organizando destinos e alternativas',pos,len(destinos_validos))
        if destino not in dist:
            # Apenas evidências do grafo, sem aproximação espacial inventada.
            codigos={'INATIVO','ATIVACAO_INDETERMINADA','JUSANTE_INVALIDO','JUSANTE_NAO_INFORMADO','VINCULO_AUSENTE','BOMBA_ESTADO_INDETERMINADO','DISPOSITIVO_NAO_INTERPRETADO','JUSANTE_INDISPONIVEL_NA_HIPOTESE','JUSANTE_ELEMENTO_INATIVO','JUSANTE_ELEMENTO_EXCLUIDO','JUSANTE_CONFLITO','NO_ORFAO'}
            limites=[d for d in avisos_comp[fracos[destino]] if d.get('codigo') in codigos]
            inalcancaveis.append(dict(destino=destino,motivo='Sem caminho dirigido desde as origens. Avisos do componente de destino são indícios, não causas comprovadas nem prova de ligação faltante',interrupcoes=limites[:100],avisos_omitidos=max(0,len(limites)-100)));continue
        nos,chaves=reconstruir(destino,pais);principal=rota(nos,chaves,destino,len(rotas)+1);rotas.append(principal)
        for i in principal['tubulacoes']:contagens[i].add(destino);qrotas[i].add(principal['uid']);disps[i].update(principal['dispositivos'])
        for e in principal['arestas']:selecionado.add_edge(e['inicio'],e['fim'])
        if not principal['arestas']:selecionado.add_node(destino)
        if alternativas:
            cortes=list(dict.fromkeys((e['natureza'],e['elemento']) for e in principal['arestas']));candidatas=[];vistos=set()
            if len(cortes)>8:cortes=[cortes[round(n*(len(cortes)-1)/7)] for n in range(8)]
            for corte in cortes:
                passo('Comparando alternativa de caminho')
                da,pa=buscar([principal['origem']],[destino],corte)
                if destino not in da:continue
                ns,chs=reconstruir(destino,pa);assinatura=tuple(chs)
                if assinatura in vistos:continue
                vistos.add(assinatura);alt=rota(ns,chs,destino,'',True);alt['exclusao_de_busca']=corte;alt['comparacao']='MESMO_CUSTO' if (alt['custo_lexicografico']==principal['custo_lexicografico'] if lex else math.isclose(alt['custo'],principal['custo'],rel_tol=1e-12,abs_tol=1e-9)) else 'CUSTO_MAIOR';candidatas.append(alt)
            for j,alt in enumerate(sorted(candidatas,key=lambda a:(a['custo_lexicografico'] if lex else a['custo'],repr(a['portas'])))[:alternativas],1):alt['uid']=f"{principal['uid']}.{j}";alternativas_rotas.append(alt)
    passo('Calculando participação no conjunto de rotas escolhido')
    metricas={};motivos={};vs=[];ids_alternativos={i for a in alternativas_rotas for i in a['tubulacoes']}
    for i in sorted(contagens):
        bruto=None
        for tabela,attrs in el[i].get('atributos',{}).items():
            if isinstance(attrs,dict) and 'Physical_PipeDiameter' in attrs:bruto=attrs['Physical_PipeDiameter']
        metricas[str(i)]=dict(rotas=len(qrotas[i]),destinos=len(contagens[i]),compartilhado=len(contagens[i])>1,
            classe='CORREDOR_COMPARTILHADO' if len(contagens[i])>1 else 'CAMINHO_ENTRE_PONTOS' if metodo=='CAMINHO' else 'RAMO_DESTINO',
            comprimento_m=comprimentos.get(i),diametro_bruto=bruto,unidade_diametro='NÃO CONFIRMADA',
            dispositivos=sorted(disps[i]),alternativas_avaliadas=alternativas,
            em_rota_alternativa=i in ids_alternativos)
        motivos[str(i)]=[f"{metodo}: {len(qrotas[i])} rota(s) selecionada(s), {len(contagens[i])} destino(s); contagens não são vazão/demanda"]
        v=vinculo_wg(pacote,i,'ALGORITMO');v['dados']['metricas']=metricas[str(i)];vs.append(v)
    componentes=[]
    for membros in nx.connected_components(selecionado):
        componentes.append(dict(origens=[n for n in fontes if n in membros],destinos=[t for t in destinos_validos if t in membros],portas=sorted(membros,key=repr)))
    return dict(metodo=metodo,modo=modo,criterio_caminho=criterio,alternativas_solicitadas=alternativas,pontes=False,origens=fontes,destinos=destinos_validos,
        universo=g.number_of_edges(),escopo='GRAFO_COMPLETO_DA_PERSPECTIVA',rotas=rotas,rotas_alternativas=alternativas_rotas,
        metricas=metricas,criterios=motivos,elementos=vs,componentes_selecionados=componentes,
        destinos_alcancados=[r['destino'] for r in rotas],destinos_inalcancaveis=inalcancaveis,
        alternativas_metodo='Até 8 exclusões temporárias distribuídas ao longo da rota principal; candidatos ordenados por custo. Não é enumeração exaustiva nem garantia das K menores rotas.',
        limitacoes='Origem é terminal escolhido, não fonte hidráulica comprovada. União das rotas de menor custo escolhidas por destino, com origem de menor custo. Empates têm desempate reproduzível; alternativas são limitadas e não exaustivas. Métricas de participação referem-se somente às rotas principais escolhidas, não ao grafo global. Comprimento não é perda de carga; direção cadastrada/hipotética não é vazão.')
