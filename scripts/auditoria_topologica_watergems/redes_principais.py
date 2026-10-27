"""Seleções cadastrais e indicadores estruturais sobre o grafo já resolvido.

Não altera arestas, não estima vazão e não calcula centralidade quadrática.
Pontes usam projeção não dirigida com multiplicidade; alcance usa grafo dirigido.
"""
from collections import defaultdict
import csv
import json
from pathlib import Path
import networkx as nx
from . import decisoes as db
from .conjuntos_investigacao import vinculo_wg


def identificar(pacote,modo='ESTRUTURAL',metodo='CADASTRAL',condicao=None,
                pontes=True,origens=(),destinos=(),combinacao='OU',escopo=None,
                progresso=None,cancelado=None):
    if modo not in db.MODOS:raise ValueError('Perspectiva indisponível')
    if metodo not in ('CADASTRAL','TOPOLOGICO','COMBINADO'):raise ValueError('Método inválido')
    if combinacao not in ('E','OU'):raise ValueError('Combinação inválida')
    def passo(etapa,n=None,total=None):
        if cancelado and cancelado():raise InterruptedError('Identificação cancelada; conjunto não publicado')
        if progresso:progresso(etapa,n,total)
    passo('Preparando grafo da perspectiva')
    resultado=pacote['topologia']['estrutural' if modo=='ESTRUTURAL' else 'potencial']
    g=resultado['grafo'];modelo=pacote['topologia']['modelo'];el=modelo['elementos']
    tubos={a['elemento'] for _,_,a in g.edges(data=True) if a.get('natureza')=='TUBULACAO'}
    if escopo is not None:
        # Escopo é explícito e altera as métricas; não se confunde com filtro visual.
        escopo=set(escopo)
        if not escopo<=tubos:raise ValueError('Escopo contém tubulações indisponíveis na perspectiva')
        g=nx.edge_subgraph(g,[(a,b,k) for a,b,k,d in g.edges(keys=True,data=True) if d.get('natureza')!='TUBULACAO' or d['elemento'] in escopo]).copy();tubos=escopo
    motivos=defaultdict(list);topologicos=set();cadastrais=set()
    if metodo in ('CADASTRAL','COMBINADO'):
        if not condicao:raise ValueError('Configure pelo menos uma condição cadastral; unidades são as da fonte')
        from .filtros import ContextoFiltros
        contexto=ContextoFiltros(pacote)
        gis_por_wg=defaultdict(set);areas_por_wg=defaultdict(set)
        for local in pacote['resultado']['locais']:
            for a in local['correspondencias']:
                if a['situacao']=='INEQUIVOCA' and len(a['candidatos'])==1:
                    i=a['candidatos'][0];gis_por_wg[i].add(a['gis_uid']);areas_por_wg[i].update(contexto.locais.get(local['uid'],{}));areas_por_wg[i].update(local['areas'])
        for n,i in enumerate(sorted(tubos)):
            if n%128==0:passo('Avaliando atributos',n,len(tubos))
            caso=dict(uid=str(i),wg_ids=[i],gis_uids=sorted(gis_por_wg[i]),area_uids=sorted(areas_por_wg[i]),local_uid=None)
            if contexto.avaliar(caso,condicao,modo) is True:
                cadastrais.add(i);motivos[i].append('Atende às condições cadastrais configuradas; unidade bruta da fonte')
    if metodo in ('TOPOLOGICO','COMBINADO'):
        passo('Identificando corredores e pontes topológicas')
        if pontes:
            h=nx.Graph();pares=defaultdict(set)
            for a,b,d in g.edges(data=True):
                h.add_edge(a,b);pares[frozenset((a,b))].add((d.get('natureza'),d.get('elemento')))
            for n,(a,b) in enumerate(nx.bridges(h)):
                if n%128==0:passo('Verificando pontes da projeção não dirigida')
                itens=pares[frozenset((a,b))]
                if len(itens)==1:
                    natureza,i=next(iter(itens))
                    if natureza=='TUBULACAO':
                        topologicos.add(i);motivos[i].append('Ponte na projeção não dirigida: remoção divide conectividade fraca; não mede importância hidráulica')
        fontes={i for i,e in el.items() if e['tipo'] in ('IdahoReservoir','ConventionalTank','IdahoTank') and e.get('excluido') is False}
        origens=set(origens);destinos=set(destinos)
        if origens and not origens<=fontes:raise ValueError('Origens devem ser reservatórios ou tanques identificados; bombas não são fontes de água')
        if destinos and not origens:raise ValueError('Selecione origens para calcular corredores dirigidos')
        for origem in sorted(origens):
            portas=[p for p in g if p[0]==origem]
            if not portas:raise ValueError('Origem indisponível na perspectiva')
            for destino in sorted(destinos):
                passo('Buscando corredor dirigido entre origem e destino')
                alvos=[p for p in g if p[0]==destino]
                if not alvos:raise ValueError('Destino indisponível na perspectiva')
                caminhos=[]
                for a in portas:
                    for b in alvos:
                        try:caminhos.append(nx.shortest_path(g,a,b))
                        except nx.NetworkXNoPath:pass
                if caminhos:
                    caminho=min(caminhos,key=lambda p:(len(p),repr(p)))
                    for a,b in zip(caminho,caminho[1:]):
                        # Todos os links paralelos são candidatos; nenhum escolhido por ID.
                        for d in g[a][b].values():
                            if d.get('natureza')=='TUBULACAO':
                                i=d['elemento'];topologicos.add(i);motivos[i].append(f'Corredor dirigido com menor número de arestas entre {origem} e {destino}; não representa vazão nem unicidade do caminho')
        if not pontes and not destinos:raise ValueError('Selecione pontes ou destinos para a análise topológica')
    ids=cadastrais if metodo=='CADASTRAL' else topologicos if metodo=='TOPOLOGICO' else cadastrais&topologicos if combinacao=='E' else cadastrais|topologicos
    passo('Preparando conjunto para revisão')
    return dict(metodo=metodo,modo=modo,condicao=condicao,combinacao=combinacao,
        escopo='GRAFO_COMPLETO_DA_PERSPECTIVA' if escopo is None else sorted(escopo),
        universo=len(tubos),origens=sorted(origens),destinos=sorted(destinos),pontes=pontes,
        criterios={str(i):list(dict.fromkeys(motivos[i])) for i in sorted(ids)},
        elementos=[vinculo_wg(pacote,i,'ALGORITMO') for i in sorted(ids)],
        limitacoes='Indicadores cadastrais/estruturais; não classificação hidráulica. Pontes usam conectividade fraca; corredores respeitam direção e barreiras da perspectiva. Sem centralidade exata.')


def exportar_csv(destino,pacote,registro):
    """Lista interoperável; não é arquivo de importação nativa de Selection Set."""
    destino=Path(destino)
    meta=pacote['resultado']['meta']
    if registro.get('topo_uid')!=meta['topologia']['execucao_uid'] or registro.get('ig_uid')!=meta['uid']:raise ValueError('Conjunto pertence a outra investigação/versão; reconcilie explicitamente antes de exportar')
    if destino.exists():raise FileExistsError('Escolha um arquivo novo; conjunto anterior preservado')
    el=pacote['topologia']['modelo']['elementos'];linhas=[];labels=defaultdict(list)
    for i,e in el.items():
        if e.get('excluido') is False:labels[(e['tipo'],e['label'])].append(i)
    for v in registro['vinculos']:
        if v['origem']!='WG':continue
        i=int(v['chave']);e=el.get(i)
        if e is None or e.get('excluido') is not False or e['uid']!=v['dados']['uid'] or db.digest(e)!=v['dados'].get('assinatura'):raise ValueError('Elemento ausente/incompatível; reconcilie antes de exportar')
        linhas.append((str(i),e['label'],e['tipo'],e['uid'],db.texto(pacote['topologia']['modelo']['projeto']),db.texto(pacote['topologia']['modelo']['cenario']),registro['topo_uid'],registro['modo'],registro['obj_uid'],v['natureza'],'LABEL_REPETIDO' if len(labels[(e['tipo'],e['label'])])>1 else 'IDENTIDADE_PRESENTE'))
    if len({r[0] for r in linhas})!=len(linhas):raise ValueError('Elementos duplicados no conjunto')
    temporario=destino.with_name(destino.name+'.'+__import__('uuid').uuid4().hex+'.tmp')
    try:
        with temporario.open('x',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f);w.writerow(('DomainElementID','Label','Tipo','UID','Modelo','Cenario','Versao','Perspectiva','ConjuntoUUID','OrigemInclusao','Conferencia'));w.writerows(linhas)
        temporario.rename(destino)
    finally:
        if temporario.exists():temporario.unlink()
    return destino
