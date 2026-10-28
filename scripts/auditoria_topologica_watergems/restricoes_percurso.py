"""Regras investigativas sobre uma cópia do grafo; sem escrita no modelo fonte."""
from copy import deepcopy
from collections import defaultdict,deque
import networkx as nx
from . import decisoes as db

ACOES=('PERMITIR','EVITAR','BLOQUEAR')
ESTADOS=('ABERTO','FECHADO','INDISPONIVEL','DESCONHECIDO')


def contexto(p):
    m=p['topologia']['modelo'];meta=p.get('resultado',{}).get('meta',{})
    return dict(modelo=m.get('projeto'),cenario=m.get('cenario'),topo_uid=meta.get('topologia',{}).get('execucao_uid'))


def categorias(p):
    return sorted({e['tipo'] for e in p['topologia']['modelo']['elementos'].values() if e.get('familia')=='DISPOSITIVO' and e.get('excluido') is False})


def referencia(p,i):
    if isinstance(i,bool) or not (isinstance(i,int) or isinstance(i,str) and i.isdigit()):raise ValueError('DomainElementID inválido')
    e=p['topologia']['modelo']['elementos'].get(int(i))
    if not e or e.get('familia')!='DISPOSITIVO' or e.get('excluido') is not False:raise ValueError('Equipamento ausente, excluído ou de tipo incompatível: '+str(i))
    return dict(id=int(i),uid=e['uid'],tipo=e['tipo'],label=e.get('label'),assinatura=db.digest(e))


def normalizar(p,config):
    if config is not None and not isinstance(config,dict):raise ValueError('O perfil deve ser um objeto JSON com regras e exceções')
    c=deepcopy(config or {});c.setdefault('regras',{});c.setdefault('excecoes',[]);c.setdefault('estados',[]);c.setdefault('otimizacao','LEXICOGRAFICA');c.setdefault('bloquear_indisponiveis',False)
    if not isinstance(c['regras'],dict) or not isinstance(c['excecoes'],list) or not isinstance(c['estados'],list) or not isinstance(c['bloquear_indisponiveis'],bool):raise ValueError('Perfil inválido: regras devem ser um objeto, exceções/estados listas e bloqueio um booleano')
    if (c['excecoes'] or c['estados']) and c.get('contexto',{}).get('modelo') is not None and c['contexto']['modelo']!=contexto(p)['modelo']:raise ValueError('Exceções de outro modelo: remova ou selecione novamente os equipamentos explicitamente')
    if c['estados'] and c.get('contexto',{}).get('cenario') is not None and c['contexto']['cenario']!=contexto(p)['cenario']:raise ValueError('Hipóteses de estado pertencem a outro cenário; confirme os equipamentos novamente')
    if c['otimizacao'] not in ('LEXICOGRAFICA','CUSTO'):raise ValueError('Critério de otimização desconhecido')
    if any(a not in ACOES for a in c['regras'].values()):raise ValueError('Regra de percurso inválida')
    for campo in ('excecoes','estados'):
        vistos=set()
        for r in c[campo]:
            atual=referencia(p,r['id']);i=atual['id']
            if i in vistos:raise ValueError('Regra individual duplicada: '+str(i))
            vistos.add(i)
            if any(r.get(k)!=atual[k] for k in ('uid','tipo','assinatura')):raise ValueError('Exceção/estado incompatível com a versão selecionada: '+str(i)+'. Confira ou remova a regra; nenhum ID será associado por Label ou proximidade.')
            if campo=='excecoes' and r.get('acao') not in ACOES:raise ValueError('Exceção inválida')
            if campo=='estados':
                if r.get('estado') not in ESTADOS:raise ValueError('Estado desconhecido')
                if r.get('origem')!='MANUAL':raise ValueError('Use hipótese manual ou registro cadastral validado pelo leitor; códigos brutos não são estados comprovados')
                r['natureza']='HIPOTESE_DE_INVESTIGACAO'
    # Regras de tipos ausentes são conservadas no perfil, sem criar equipamentos.
    c['contexto']=contexto(p);c['versao_regras']='restricoes-1'
    return c


def resolver_regras(p,c):
    regras={i:c['regras'].get(e['tipo'],'PERMITIR') for i,e in p['topologia']['modelo']['elementos'].items() if e.get('familia')=='DISPOSITIVO' and e.get('excluido') is False}
    for r in c['excecoes']:regras[int(r['id'])]=r['acao']
    estados={int(r['id']):dict(r) for r in c['estados']}
    # Somente contrato explícito de estados já validados, nunca Initial Settings/UDE.
    for r in p['topologia']['modelo'].get('estados_validados',[]):
        atual=referencia(p,r['id'])
        if r.get('validado') is True and r.get('contexto')==contexto(p) and r.get('fonte') and r.get('assinatura')==atual['assinatura'] and r.get('estado') in ESTADOS:
            estados.setdefault(atual['id'],dict(atual,estado=r['estado'],origem='CADASTRO_VALIDADO',fonte=r['fonte']))
    if c['bloquear_indisponiveis']:
        for i,r in estados.items():
            if r['estado'] in ('FECHADO','INDISPONIVEL'):regras[i]='BLOQUEAR'
    return regras,estados


def grafo_trabalho(p,modo,c,cancelado=None):
    if modo not in db.MODOS:raise ValueError('Perspectiva indisponível; ESTADOS_DO_CENARIO não validado')
    base=p['topologia']['estrutural' if modo=='ESTRUTURAL' else 'potencial']['grafo'];el=p['topologia']['modelo']['elementos'];regras,estados=resolver_regras(p,c)
    def passo(n):
        if n%1024==0 and cancelado and cancelado():raise InterruptedError('Preparação cancelada; grafo original preservado')
    # Retenções estruturais têm incidência única no contrato histórico. Para rotas
    # restritas, separa incidências pela mesma referência explícita de jusante usada
    # pelo resolvedor validado. Não adiciona comunicação quando a direção é incerta.
    incidentes=defaultdict(set)
    for n,(a,b,d) in enumerate(base.edges(data=True)):
        passo(n)
        if d.get('natureza')=='TUBULACAO':
            for v in (a,b):
                if el.get(v[0],{}).get('tipo')=='CheckValve':incidentes[v[0]].add(d['elemento'])
    portas=defaultdict(set)
    for n in base:portas[n[0]].add(n[1])
    reter={i for i in incidentes if portas[i]=={'E'}};incertos=[]
    def porta(n,d):
        i=n[0]
        if i not in reter or d.get('natureza')!='TUBULACAO':return n
        jus=el[i].get('topologia',{}).get('HMITopologyDownstreamLinkID')
        return (i,'S' if jus==d['elemento'] else 'E') if jus in incidentes[i] else (i,'L:'+str(d['elemento']))
    g=nx.MultiDiGraph()
    for n,attrs in base.nodes(data=True):
        if n[0] not in reter:g.add_node(n,**deepcopy(attrs))
    for n,(a,b,k,d) in enumerate(base.edges(keys=True,data=True)):
        passo(n);g.add_edge(porta(a,d),porta(b,d),key=k,**deepcopy(d))
    for i in reter:
        jus=el[i].get('topologia',{}).get('HMITopologyDownstreamLinkID')
        if jus in incidentes[i] and (i,'E') in g and (i,'S') in g:g.add_edge((i,'E'),(i,'S'),key=('disp',i),elemento=i,natureza='DISPOSITIVO')
        else:incertos.append(i)
    portas=defaultdict(set)
    for n in g:portas[n[0]].add(n[1])
    unicos={i for i,ps in portas.items() if ps=={'E'}}
    g.remove_nodes_from([n for n in g if regras.get(n[0])=='BLOQUEAR'])
    return dict(grafo=g,regras=regras,estados=estados,direcao_indeterminada=incertos,lexicografica=c['otimizacao']=='LEXICOGRAFICA',unicos=unicos)


def passagens(a,b,d,trabalho):
    i=d['elemento'] if d.get('natureza')=='DISPOSITIVO' else b[0] if b[0] in trabalho['unicos'] and a[0]!=b[0] else None
    return int(trabalho['regras'].get(i)=='EVITAR')


def resumo(r,comprimentos):
    ids={int(v['chave']) for v in r['elementos']};ds={i for rota in r['rotas'] for i in rota['dispositivos']};ls=[comprimentos.get(i) for i in ids]
    return dict(tubulacoes=len(ids),dispositivos=len(ds),comprimento_m=sum(ls) if all(v is not None for v in ls) else None,destinos_alcancados=len(r['destinos_alcancados']),destinos_inalcancaveis=len(r['destinos_inalcancaveis']),componentes=len(r['componentes_selecionados']))


def calcular(p,modo,origens,destinos,criterio,alternativas,metodo,comprimentos,progresso,cancelado,config):
    from .corredores import calcular as caminhos,resolver_terminal
    c=normalizar(p,config);livre=grafo_trabalho(p,modo,normalizar(p,dict(otimizacao='CUSTO')),cancelado);regras,estados=resolver_regras(p,c)
    bloqueados={i for i,a in regras.items() if a=='BLOQUEAR'};t=dict(livre,regras=regras,estados=estados,lexicografica=c['otimizacao']=='LEXICOGRAFICA',grafo=nx.subgraph_view(livre['grafo'],filter_node=lambda n:n[0] not in bloqueados))
    for papel,termos in [('Origem',origens),('Destino',destinos)]:
        for termo in termos:
            i=int(termo['id'] if isinstance(termo,dict) else termo)
            if t['regras'].get(i)=='BLOQUEAR':raise ValueError(f'{papel} {i} está bloqueado. Escolha outro terminal ou altere explicitamente a regra/estado individual antes de calcular.')
    if comprimentos is None:
        from .corredores import comprimentos_metricos
        comprimentos=comprimentos_metricos(p)
    # Referência comparável: mesmas regras físicas/direcionais e perspectiva,
    # sem bloqueios/preferências adicionais definidos pelo usuário.
    def rodar(trabalho):return caminhos(p,modo,origens,destinos,criterio,alternativas,metodo,comprimentos,progresso,cancelado,_trabalho=trabalho)
    if progresso:progresso('Calculando referência sem restrições adicionais',None,None)
    antes=rodar(livre)
    if progresso:progresso('Calculando corredor com restrições',None,None)
    depois=rodar(t);antes_por={tuple(r['destino']):r for r in antes['rotas']}
    # Alcance estrutural multi-origem: indício separado, nunca prova de operação.
    sg=p['topologia']['estrutural']['grafo'];orig_ids={int(o['id'] if isinstance(o,dict) else o) for o in origens};visitados={n for n in sg if n[0] in orig_ids};fila=deque(visitados)
    iteracao=0
    while fila:
        iteracao+=1
        if iteracao%1024==0 and cancelado and cancelado():raise InterruptedError('Comparação cancelada')
        for n in sg[fila.popleft()]:
            if n not in visitados:visitados.add(n);fila.append(n)
    alcancados={n[0] for n in visitados}
    for falha in depois['destinos_inalcancaveis']:
        dest=falha['destino'];i=int(dest.get('id') if isinstance(dest,dict) else dest[0] if isinstance(dest,(tuple,list)) else dest);rota=antes_por.get(tuple(dest)) if isinstance(dest,(tuple,list)) else None
        barreiras=sorted({n[0] for n in rota['portas'] if t['regras'].get(n[0])=='BLOQUEAR'}) if rota else []
        falha.update(conexao_estrutural=i in alcancados,barreiras=barreiras,barreiras_nao_exaustivas=True,direcao_indeterminada=t['direcao_indeterminada'])
        falha['motivo']=('Caminho da referência impedido por restrições; equipamentos naquela rota: '+str(barreiras)+'. Não é uma lista exaustiva de barreiras.' if rota else 'Sem conexão estrutural dirigida desde as origens.' if i not in alcancados else 'Há alcance estrutural cadastrado, mas não há caminho nesta perspectiva/regras direcionais; atividade, portas ou disponibilidade podem limitar a passagem. Nenhuma causa única comprovada.')
    a={int(v['chave']) for v in antes['elementos']};b={int(v['chave']) for v in depois['elementos']};da={i for r in antes['rotas'] for i in r['dispositivos']};dd={i for r in depois['rotas'] for i in r['dispositivos']}
    for rota in depois['rotas']+depois['rotas_alternativas']:
        rota['equipamentos_evitados_utilizados']=sorted(i for i in rota['dispositivos'] if t['regras'].get(i)=='EVITAR')
    depois.update(restricoes=c,comparacao_restricoes=dict(sem_restricoes=resumo(antes,comprimentos),com_restricoes=resumo(depois,comprimentos),adicionados=sorted(b-a),removidos=sorted(a-b),comuns=sorted(a&b),equipamentos_evitados=sorted(da-dd),evitados_utilizados=sorted(i for i in dd if t['regras'].get(i)=='EVITAR'),dispositivos_atravessados=sorted(dd),bloqueados=sorted(i for i,v in t['regras'].items() if v=='BLOQUEAR'),estados_usados=list(t['estados'].values()),estado_desconhecido=sorted(dd-set(t['estados'])),direcao_indeterminada=t['direcao_indeterminada'],unidade_comprimento='m; união de tubos distintos, não soma de rotas repetidas'))
    depois['limitacoes']+=' Restrições investigativas em cópia do grafo. EVITAR lexicográfico conta entradas em nó único ou travessias de portas; não é custo hidráulico. Estados manuais são hipóteses; estados efetivos/controles não validados. A comparação sem restrições conserva direção obrigatória das retenções.'
    return depois


def salvar_perfil(base,pacote,nome,config,registro=None,excluido=False,modo='ESTRUTURAL'):
    from . import conjuntos_investigacao as st
    c=deepcopy(config) if excluido else normalizar(pacote,config)
    return st.salvar(base,pacote,'PERFIL_RESTRICOES',dict(nome=nome,restricoes=c),uid=registro['obj_uid'] if registro else None,esperada=registro['uid'] if registro else None,modo=modo,excluido=excluido)


def validar_selecao(p,modo,c,vinculos):
    t=grafo_trabalho(p,modo,normalizar(p,c));ids={d['elemento'] for _,_,d in t['grafo'].edges(data=True) if d.get('natureza')=='TUBULACAO'}
    invalidos=[v['chave'] for v in vinculos if v.get('origem')!='WG' or int(v['chave']) not in ids]
    if invalidos:raise ValueError('Tubulações indisponíveis sob as restrições: '+str(invalidos)+'. Remova-as ou altere explicitamente as regras e recalcule; nenhuma restrição será ignorada na exportação.')
    return t
