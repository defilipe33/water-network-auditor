"""Corredores e dependências espaciais declaradas no grafo GIS resolvido."""

from collections import defaultdict
from datetime import datetime, timezone
from heapq import heappop, heappush
from math import inf
from uuid import uuid4

from auditoria_fronteiras.entradas import digest
from auditoria_fronteiras.modelos import verificar_cancelamento
from .dependencias_gis import RedeGIS, avaliar_cortes, simular


VERSAO='gis-estrutura-1'
LIMITE_CORTES=4_000_000
LIMITE_ROTAS=6_000_000
CATEGORIAS={
    'CORREDOR':'Corredor alimentador','CRITICA':'Ligação crítica',
    'REDUNDANCIA':'Alternativa verificada','PASSAGEM':'Rede de passagem',
    'LOCAL':'Distribuição local na rota','INDETERMINADA':'Função indeterminada',
}


def novo_destino(tipo,ref,*,no=None,zona=None,modo='DECLARADO',nome=None):
    if tipo not in ('NO','PIPE') or not ref or modo not in ('DECLARADO','ESPACIAL','AUTOMATICO'):
        raise ValueError('Defina um nó ou uma tubulação como destino.')
    return dict(uid=digest(['destino-gis',tipo,ref,no,zona,modo]),tipo=tipo,ref=ref,
                no=no,zona=zona,modo=modo,nome=nome or ref[:10])


def _buscar(rede,origens,cancelar,retiradas=(),destino=None,bloqueio_segmento=None):
    """Distância geométrica acumulada, com terminais independentes."""
    dist=[inf]*len(rede.nos)
    anteriores={}
    raiz={}
    fila=[]
    for u in sorted(origens):
        for no in rede.origens[u]:
            if dist[no]!=0:
                dist[no]=0.;raiz[no]=u
                heappush(fila,(0.,no))
    while fila:
        verificar_cancelamento(cancelar)
        custo,u=heappop(fila)
        if custo!=dist[u]:continue
        if u==destino:break
        for v,i in rede.adj[u]:
            _,_,pipe,metros=rede.arestas[i]
            if i==bloqueio_segmento or pipe in retiradas:continue
            passo=custo+metros
            if passo<dist[v]:
                dist[v]=passo;anteriores[v]=(u,i)
                heappush(fila,(passo,v))
    return dist,anteriores,raiz


def _rota(rede,busca,no,cancelar):
    dist,anteriores,raizes=busca
    if dist[no]==inf:return None
    tot=dist[no];ids=[];nos=[rede.uids[no]]
    while no in anteriores:
        verificar_cancelamento(cancelar)
        no,i=anteriores[no]
        ids.append(i);nos.append(rede.uids[no])
    ids.reverse();nos.reverse()
    return dict(origem=raizes[no],segmentos=ids,partes=list(dict.fromkeys(rede.foto['arestas'][i]['tubo'] for i in ids)),
                tubos=list(dict.fromkeys(rede.arestas[i][2] for i in ids)),nos=nos,comprimento_m=tot)


def _conexoes_no(rede):
    resolvidas=rede.foto.get('resolucoes_conexoes',{})
    por_porta={tuple(p):n['uid'] for n in rede.foto['nos'] for p in n['portas']}
    saida=defaultdict(list)
    for r in rede.foto['participantes']:
        if r['tipo']!='CONEXAO' or resolvidas.get(r['uuid'])!='APLICADA':continue
        grupos={por_porta.get(tuple(p)) for p in r['portas']}
        if len(grupos)==1 and None not in grupos:
            saida[next(iter(grupos))].append(dict(uuid=r['uuid'],rev=r['rev'],natureza=r['situacao']))
    return saida


def _usar_conexoes(rede,rota,conexoes):
    """Registra a evidência da passagem pelo nó. O nó pode ter outras uniões."""
    membros=[]
    for no in rota['nos'][1:-1]:
        for r in conexoes.get(no,()):
            membros.append(dict(r,no=no))
    return membros


def _corte_no_destino(rede,dfs,corte,pipe,d,no):
    if corte['estado']!='AVALIADA':return None
    if d['tipo']=='PIPE' and rede.por_parte[d['ref']]==pipe:return None
    if len(rede.pipes[pipe])!=1:
        return corte.get('perdas_destino',{}).get(d['uid'])
    if not corte['ponte']:return None
    filho=dfs.pontes[rede.pipes[pipe][0]]
    dentro=dfs.inicio[filho]<=dfs.inicio[no]<dfs.fim[filho]
    return corte['lados'][0 if dentro else 1]


def _travessias(rede,cancelar):
    """Dados métricos em um CRS comum na fotografia. Contato simples fica separado."""
    from .investigacao_gis import geometria
    areas={a['uid']:geometria(a.get('wkb')) for a in rede.foto.get('areas',[])}
    por_parte={}
    for uid,t in rede.tubos.items():
        verificar_cancelamento(cancelar)
        if not t.get('zonas_uids'):continue
        g=geometria(t.get('wkb'))
        if g:
            por_parte[uid]=sorted(u for u in t['zonas_uids'] if areas.get(u) and g.crosses(areas[u]))
    return por_parte


def _mapa_rotas(rede,destinos,cortes,dfs,base,cancelar,etapa,limite,busca=None):
    etapa(0,'Rastreando fontes, trajetos e alternativas')
    grupos,componentes=base
    conexoes=_conexoes_no(rede)
    conectados={}
    rotas={}
    usados=0;segmentos_emitidos=0
    limite_segmentos=max(2048,limite//4)
    custo=len(rede.nos)+len(rede.arestas)
    if busca is None and destinos and rede.origens:
        busca=_buscar(rede,rede.origens,cancelar)
    # As árvores por fonte são calculadas de uma vez para todo o conjunto de destinos.
    por_fonte={}
    for uid in sorted(rede.origens) if destinos and len(rede.origens)>1 else ():
        if usados+custo>limite or len(por_fonte)>=4:break
        por_fonte[uid]=_buscar(rede,[uid],cancelar)
        usados+=custo
    for uid,(d,no) in destinos.items():
        verificar_cancelamento(cancelar)
        fontes=rede.nomes_origens(componentes[grupos[no]][1])
        info=dict(d,no_alvo=rede.uids[no],origens=fontes,rotas=[],criticas=[],dependencias_fontes={},
                  estado='ALCANCAVEL' if fontes else 'SEM_CAMINHO' if rede.origens else 'SEM_ORIGENS')
        conectados[uid]=info
        if not fontes:continue
        if segmentos_emitidos>=limite_segmentos:
            info.update(fontes_sem_rota_detalhada=fontes,detalhe='LIMITE_SEGMENTOS')
            continue
        principal=_rota(rede,busca,no,cancelar)
        alternativas=[principal]
        # Uma rota por origem avaliada. A disponibilidade de todas as demais é mantida na tabela.
        for origem in fontes:
            if origem!=principal['origem'] and origem in por_fonte:
                alternativas.append(_rota(rede,por_fonte[origem],no,cancelar))
        criticas=set()
        for caminho in alternativas:
            verificar_cancelamento(cancelar)
            if segmentos_emitidos>=limite_segmentos:break
            origem=caminho['origem']
            segmentos_emitidos+=len(caminho['segmentos'])
            obrigatorios=[]
            for f in caminho['tubos']:
                restantes=_corte_no_destino(rede,dfs,cortes[f],f,d,no)
                if restantes is not None and origem not in restantes:
                    obrigatorios.append(f)
                    if not restantes:criticas.add(f)
            rid=digest(['rota',uid,origem])
            caminho.update(uid=rid,destino=uid,conexoes_no=_usar_conexoes(rede,caminho,conexoes),
                           principal=caminho is principal)
            info['dependencias_fontes'][origem]=obrigatorios
            if not caminho['tubos']:
                caminho['alternativa_estado']='NO_DA_ORIGEM'
            elif len(rede.origens[origem])==1 and all(e in dfs.pontes for e in caminho['segmentos']):
                caminho['alternativa_estado']='CAMINHO_UNICO'
            else:
                bloqueios=set(caminho['tubos'])
                via=None
                if obrigatorios:
                    caminho['alternativa_estado']='PIPE_OBRIGATORIO'
                elif usados+custo<=limite:
                    usados+=custo
                    via=_rota(rede,_buscar(rede,[origem],cancelar,bloqueios,no),no,cancelar)
                    caminho['alternativa_estado']='DISJUNTA_VERIFICADA' if via else 'SEM_DISJUNTA_DA_ROTA_ESCOLHIDA'
                else:caminho['alternativa_estado']='NAO_TESTADA_LIMITE'
                if via:
                    via['conexoes_no']=_usar_conexoes(rede,via,conexoes)
                    caminho['alternativa']=via
                else:
                    sondas=(e for e in caminho['segmentos'] if e not in dfs.pontes)
                    e=next(sondas,None)
                    if e is not None and usados+custo<=limite:
                        usados+=custo
                        via=_rota(rede,_buscar(rede,[origem],cancelar,destino=no,bloqueio_segmento=e),no,cancelar)
                        if via:
                            via['conexoes_no']=_usar_conexoes(rede,via,conexoes)
                            caminho['alternativa_estado']='PARCIAL_VERIFICADA' if set(via['tubos']) & bloqueios else 'DISJUNTA_VERIFICADA'
                            caminho['alternativa']=via
                if via:segmentos_emitidos+=len(via['segmentos'])
            rotas[rid]=caminho;info['rotas'].append(rid)
        info['criticas']=sorted(criticas)
        info['fontes_sem_rota_detalhada']=sorted(set(fontes)-{rotas[r]['origem'] for r in info['rotas']})
    return conectados,rotas,usados


def _classificar(rede,cortes,destinos,rotas,travessias,cancelar):
    from qgis.core import QgsGeometry
    from .investigacao_gis import geometria
    funcoes=defaultdict(set);alvos=defaultdict(set);fontes=defaultdict(set)
    passagem=defaultdict(set);equip=defaultdict(set)
    areas={a['uid']:geometria(a.get('wkb')) for a in rede.foto.get('areas',[])}
    geometrias={}
    def geometria_segmento(indice):
        if indice not in geometrias:
            e=rede.foto['arestas'][indice]
            linha=geometria(rede.tubos[e['tubo']].get('wkb'))
            if linha is None:return None
            g=linha.constGet()
            m=linha.length()
            ini,fim=e.get('inicio',0.),e.get('fim',1.)
            geometrias[indice]=linha if (ini,fim)==(0.,1.) else QgsGeometry(g.curveSubstring(m*ini,m*fim))
        return geometrias[indice]
    for r in rotas.values():
        d=destinos[r['destino']];zona=d.get('zona')
        for trecho in [r,*([r['alternativa']] if r.get('alternativa') else [])]:
            segmentos=defaultdict(list)
            if zona and d['modo']=='DECLARADO':
                for i in trecho['segmentos']:
                    parte=rede.foto['arestas'][i]['tubo']
                    if rede.tubos[parte].get('zonas_uids'):
                        g=geometria_segmento(i)
                        if g:segmentos[parte].append(g)
            for parte in trecho['partes']:
                verificar_cancelamento(cancelar)
                f=rede.por_parte[parte]
                funcoes[f].add('CORREDOR')
                alvos[f].add(d['uid']);fontes[f].add(r['origem'])
                if r['alternativa_estado']=='DISJUNTA_VERIFICADA':
                    funcoes[f].add('REDUNDANCIA')
                if segmentos.get(parte):
                    g=QgsGeometry.collectGeometry(segmentos[parte])
                    outras={u for u in rede.tubos[parte]['zonas_uids'] if u!=zona and areas.get(u) and g.crosses(areas[u])}
                    if outras:
                        passagem[f].update(outras);funcoes[f].add('PASSAGEM')
                    if areas.get(zona) and g.intersection(areas[zona]).length()>1e-8:
                        funcoes[f].add('LOCAL')
                equip[f].update(v['uuid'] for v in trecho.get('conexoes_no',()))
    linhas=[]
    for f,partes in rede.partes.items():
        verificar_cancelamento(cancelar)
        corte=cortes[f]
        if corte.get('afetadas') or corte.get('destinos_afetados'):funcoes[f].add('CRITICA')
        if not funcoes[f] or corte['estado']=='INDETERMINADA_LIMITE':funcoes[f].add('INDETERMINADA')
        ts=[rede.tubos[u] for u in partes]
        d=max((t['diametro_mm'] for t in ts if t.get('diametro_mm') is not None),default=None)
        a=ts[0]
        linhas.append(dict(uid=f,partes=partes,id=a.get('id'),nome=a.get('label'),camada=a.get('camada',''),
                           comprimento_m=sum(t['comprimento_m'] for t in ts),diametro_mm=d,
                           funcoes=sorted(funcoes[f]),origens=sorted(fontes[f]),destinos=sorted(alvos[f]),
                           zonas_passagem=sorted(passagem[f]),conexoes_no=sorted(equip[f]),
                           travessias=sorted({z for u in partes for z in travessias.get(u,())}),**corte))
    return linhas


def analisar(foto,origens=None,destinos=(),*,nome='Redes estruturantes',associacoes=(),
             limite_cortes=LIMITE_CORTES,limite_rotas=LIMITE_ROTAS,cancelar=None,etapa=lambda *_:None,
             agrupamento=None):
    if limite_cortes<0 or limite_rotas<0:raise ValueError('Os limites de cálculo devem ser não negativos.')
    rede=RedeGIS(foto,origens,cancelar)
    busca=amostra=None
    if agrupamento is not None:
        from . import agrupamento_corredores_gis as macro
        agrupamento=macro.parametros(**agrupamento)
        if agrupamento['modo']=='AUTOMATICO':
            etapa(0,'Selecionando destinos periféricos pelo grafo')
            busca=_buscar(rede,rede.origens,cancelar)
            selecao,amostra=macro.perifericos(rede,busca,agrupamento,cancelar)
            destinos=[dict(novo_destino('NO',no,modo='AUTOMATICO',nome='Nó periférico '+no[:8]),
                           distancia_origem_m=distancia) for no,distancia in selecao]
            associacoes=()
    destinos=rede.destinos(destinos)
    zonas={a['uid']:a for a in foto.get('areas',[])}
    if any(d.get('zona') and d['zona'] not in zonas for d,_ in destinos.values()):
        raise ValueError('Uma associação de zona não pertence à execução escolhida.')
    cortes,dfs,base=avaliar_cortes(rede,destinos,cancelar,etapa,limite_cortes)
    relacionados,rotas,usados=_mapa_rotas(rede,destinos,cortes,dfs,base,cancelar,etapa,limite_rotas,busca)
    travessias=_travessias(rede,cancelar)
    linhas=_classificar(rede,cortes,relacionados,rotas,travessias,cancelar)
    area_por_destino=defaultdict(list)
    for d in relacionados.values():
        if d.get('zona'):area_por_destino[d['zona']].append(d)
    naturezas={r['uuid']:r['situacao'] for r in foto['participantes'] if r['tipo']=='ORIGEM'}
    dependencia=[]
    for uid,area in zonas.items():
        verificar_cancelamento(cancelar)
        ds=area_por_destino[uid]
        fontes=sorted({f for d in ds for f in d['origens']})
        ids=sorted({r for d in ds for r in d['rotas']})
        dependencia.append(dict(uid=uid,nome=str(area.get('label') or area.get('id') or uid[:8]),
            destinos=[d['uid'] for d in ds],origens=fontes,rotas=ids,
            complementares=[f for f in fontes if naturezas.get(f)!='CADASTRADA'],
            destinos_so_complementares=[d['uid'] for d in ds if d['origens'] and
                                        all(naturezas.get(f)!='CADASTRADA' for f in d['origens'])],
            origens_exclusivas=sorted({d['origens'][0] for d in ds if len(d['origens'])==1}),
            criticas=sorted({f for d in ds for f in d['criticas']}),
            maior_perda_m=max((cortes[f]['perda_m'] for d in ds for f in d['criticas']),default=None),
            alternativas=sum(rotas[r]['alternativa_estado']=='DISJUNTA_VERIFICADA' for r in ids),
            conexoes_no=sorted({v['uuid'] for i in ids for v in rotas[i]['conexoes_no']}),
            estado='SEM_DESTINO' if not ds else 'SEM_ORIGENS' if not rede.origens else
            'ALCANCAVEL' if all(d['origens'] for d in ds) else 'PARCIAL' if fontes else 'SEM_CAMINHO',
            evidencia='DECLARADA' if ds and all(d['modo']=='DECLARADO' for d in ds) else 'ESPACIAL_OU_MISTA'))
    resultado=dict(uuid=uuid4().hex,nome=nome,projeto_uid=foto['projeto_uid'],topologia_uid=foto['uuid'],
                foto=foto,hipotese=foto.get('hipotese'),data_utc=datetime.now(timezone.utc).isoformat(),
                algoritmo=VERSAO,fontes=rede.ids_origens,destinos=list(relacionados.values()),
                zonas=dependencia,rotas=list(rotas.values()),tubulacoes=linhas,
                articulacoes=sorted(rede.uids[i] for i in dfs.articulacoes),pontes_segmentos=len(dfs.pontes),
                parametros=dict(limite_cortes=limite_cortes,limite_rotas=limite_rotas,extra_rotas_usado=usados),
                associacoes=list(associacoes))
    if agrupamento is not None:
        etapa(0,'Agrupando segmentos contínuos e percursos')
        resultado['agrupamento']=macro.agrupar(resultado,agrupamento,amostra,cancelar)
    return resultado


def testar_interrupcao(trabalho,retiradas,cancelar=None,etapa=lambda *_:None):
    etapa(0,'Calculando componentes remanescentes')
    rede=RedeGIS(trabalho['foto'],trabalho['fontes'],cancelar)
    ds=rede.destinos(trabalho['destinos'])
    resultado=simular(rede,retiradas,ds,cancelar)
    excluidas=set(resultado['retiradas'])
    resultado['rotas_intactas']=[r['uid'] for r in trabalho['rotas'] if not excluidas.intersection(r['tubos'])]
    resultado['alternativas_intactas']=[r['uid'] for r in trabalho['rotas']
                                       if r.get('alternativa') and not excluidas.intersection(r['alternativa']['tubos'])]
    buscar_nova=[d['uid'] for d in resultado['destinos'] if d['depois'] and not d['direto']]
    resultado['novas_rotas']={}
    resultado['rotas_omitidas']=0
    if buscar_nova:
        etapa(0,'Encontrando trajetos após a interrupção')
        foto=_buscar(rede,rede.origens,cancelar,excluidas)
        segmentos=0
        for u in buscar_nova[:250]:
            via=_rota(rede,foto,ds[u][1],cancelar)
            if segmentos+len(via['segmentos'])>max(250_000,len(rede.arestas)):break
            segmentos+=len(via['segmentos'])
            resultado['novas_rotas'][u]=dict(via,uid=u,destino=u)
        resultado['rotas_omitidas']=len(buscar_nova)-len(resultado['novas_rotas'])
    return resultado


def comparar_estruturas(a,b):
    if a['projeto_uid']!=b['projeto_uid']:
        raise ValueError('Escolha duas investigações estruturais do mesmo projeto.')
    difs=[]

    def mapas(campo):
        return ({r['uid']:r for r in d[campo]} for d in (a,b))

    def diferenca(tipo,uid,antes,depois,**refs):
        difs.append(dict(uid=digest([tipo,uid]),tipo=tipo,ref=uid,antes=antes,depois=depois,**refs))

    pa,pb=mapas('tubulacoes')
    for u in sorted(pa.keys()|pb.keys()):
        x,y=pa.get(u),pb.get(u)
        if not x or not y:
            diferenca('PIPE_AUSENTE' if x else 'PIPE_NOVO',u,bool(x),bool(y),tubos=[u])
        elif x['funcoes']!=y['funcoes']:
            ambos=bool(a['fontes'] and b['fontes']) and x['estado']==y['estado']=='AVALIADA'
            ganhou='CRITICA' in y['funcoes'] and 'CRITICA' not in x['funcoes']
            perdeu='CRITICA' in x['funcoes'] and 'CRITICA' not in y['funcoes']
            tipo='TORNOU_CRITICA' if ambos and ganhou else 'DEIXOU_CRITICA' if ambos and perdeu else 'FUNCAO'
            diferenca(tipo,u,x['funcoes'],y['funcoes'],tubos=[u])
        elif abs((x.get('perda_m') or 0)-(y.get('perda_m') or 0))>1e-6:
            diferenca('IMPACTO',u,x.get('perda_m'),y.get('perda_m'),tubos=[u])
    za,zb=mapas('zonas')
    for u in sorted(za.keys()|zb.keys()):
        x,y=za.get(u),zb.get(u)
        def dependencias(z):
            return {k:z[k] for k in ('estado','evidencia','origens','destinos','criticas','alternativas')} if z else None
        v,w=dependencias(x),dependencias(y)
        if v!=w:
            conhecido=v and w and v['destinos']==w['destinos'] and v['estado'] not in ('SEM_ORIGENS','SEM_DESTINO') and w['estado'] not in ('SEM_ORIGENS','SEM_DESTINO')
            tipo='ZONA_GANHOU' if conhecido and not v['origens'] and w['origens'] else (
                'ZONA_PERDEU' if conhecido and v['origens'] and not w['origens'] else 'ZONA_DEPENDENCIAS')
            diferenca(tipo,u,v,w,zona=u)
    da,db=mapas('destinos')
    for u in sorted(da.keys() & db.keys()):
        x,y=da[u],db[u]
        if x['origens']!=y['origens']:
            diferenca('DESTINO_FONTES',u,x['origens'],y['origens'],destino=u)
    ra,rb=mapas('rotas')
    for u in sorted(ra.keys()|rb.keys()):
        x,y=ra.get(u,{}),rb.get(u,{})
        def alternativa(r):
            return (r.get('alternativa_estado'),r.get('alternativa',{}).get('tubos',[]))
        if alternativa(x)!=alternativa(y):
            diferenca('ALTERNATIVA',u,alternativa(x),alternativa(y),rota=u)
        if x.get('tubos')!=y.get('tubos'):
            diferenca('TRAJETO',u,x.get('comprimento_m'),y.get('comprimento_m'),rota=u)
    fontes_a,fontes_b=set(a['fontes']),set(b['fontes'])
    for u in sorted(fontes_a^fontes_b):
        diferenca('ORIGEM_CONSIDERADA',u,u in fontes_a,u in fontes_b,origem=u)
    def conexoes(d):
        foto=d['foto']
        return {r['uuid']:r['rev'] for r in foto['participantes'] if r['tipo']=='CONEXAO'
                and foto.get('resolucoes_conexoes',{}).get(r['uuid'])=='APLICADA'}
    ca,cb=conexoes(a),conexoes(b)
    for u in sorted(ca.keys()|cb.keys()):
        if ca.get(u)!=cb.get(u):
            diferenca('CONEXAO_APLICADA',u,ca.get(u),cb.get(u),conexao=u)
    return difs
