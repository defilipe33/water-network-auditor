"""Agrupa a união de percursos sobre as arestas da fotografia GIS."""

from collections import Counter, defaultdict
from math import isfinite
from uuid import NAMESPACE_URL, uuid5

from auditoria_fronteiras.modelos import verificar_cancelamento


VERSAO = 'corredores-agrupados-1'
FUNCOES = {
    'TRONCO': 'Tronco compartilhado', 'RAMAL': 'Ramal alimentador',
    'TERMINAL': 'Corredor terminal', 'ALTERNATIVO': 'Corredor alternativo',
    'CRITICO': 'Corredor crítico', 'INDETERMINADO': 'Função indeterminada',
}


def parametros(modo='MANUAL', maximo=24, minimo_m=0):
    if modo not in ('MANUAL', 'AUTOMATICO') or not 1 <= maximo <= 200:
        raise ValueError('Escolha o modo e um máximo entre 1 e 200 destinos.')
    if not isfinite(minimo_m) or minimo_m < 0:
        raise ValueError('A distância mínima deve ser finita e não negativa.')
    return dict(modo=modo, maximo=maximo, minimo_m=minimo_m)


def perifericos(rede, busca, opcoes, cancelar=None):
    """Uma amostra de folhas da floresta por ramo e faixa de distância."""
    dist, pais, _ = busca
    if not pais:
        return [], dict(folhas=0, elegiveis=0, grupos=0, faixa_m=0)
    filhos = Counter(pai for pai, _ in pais.values())
    folhas = [u for u in pais if u not in filhos]
    elegiveis = {u for u in folhas if dist[u] >= opcoes['minimo_m']}
    faixa = max(1e-6, max(dist[u] for u in pais) / max(3, min(12, opcoes['maximo'])))
    ordem = sorted(pais, key=lambda u: (dist[u], rede.uids[u]))
    ancoras, anteriores, raiz, grupos = {}, {}, {}, {}
    for u in ordem:
        verificar_cancelamento(cancelar)
        pai, _ = pais[u]
        raiz[u] = raiz.get(pai, pai)
        # A faixa anterior une pequenas pontas vizinhas na mesma ramificação.
        if pai not in pais or int(dist[u] / faixa) != int(dist[pai] / faixa):
            ancoras[u], anteriores[u] = u, ancoras.get(pai, pai)
        else:
            ancoras[u], anteriores[u] = ancoras[pai], anteriores[pai]
        if u not in elegiveis:
            continue
        pontas_proximas = filhos[pai]>1 and pai in pais and dist[u]-dist[pai]<=faixa
        chave = ('PONTAS',raiz[u],pai) if pontas_proximas else ('RAMO',raiz[u],anteriores[u],int(dist[u]/faixa))
        chave_folha = (-dist[u], len(rede.adj[u]) != 1, rede.uids[u])
        if chave not in grupos or chave_folha < grupos[chave][0]:
            grupos[chave] = chave_folha, u
    ordenados = [u for _, u in sorted(grupos.values())]
    # Representa cada raiz alcançável antes de preencher vagas na mesma árvore.
    por_raiz = {}
    for u in ordenados:
        por_raiz.setdefault(raiz[u], u)
    prioritarios = set(por_raiz.values())
    ordenados = [u for u in ordenados if u in prioritarios] + [u for u in ordenados if u not in prioritarios]
    amostra = [(rede.uids[u], dist[u]) for u in ordenados[:opcoes['maximo']]]
    return amostra, dict(folhas=len(folhas), elegiveis=len(elegiveis), grupos=len(grupos), faixa_m=faixa)


def sequencias(arestas, assinaturas, cancelar):
    """Particiona a união em cadeias máximas; nenhum segmento é duplicado."""
    adjacentes = defaultdict(list)
    for i in assinaturas:
        a, b = arestas[i]['a'], arestas[i]['b']
        adjacentes[a].append(i)
        adjacentes[b].append(i)

    def corte(no):
        vizinhos = adjacentes[no]
        return len(vizinhos) != 2 or assinaturas[vizinhos[0]] != assinaturas[vizinhos[1]]

    usados = set()

    def seguir(no, i):
        nos = [no]
        segmentos = []
        while i not in usados:
            verificar_cancelamento(cancelar)
            usados.add(i)
            segmentos.append(i)
            a, b = arestas[i]['a'], arestas[i]['b']
            no = b if no == a else a
            nos.append(no)
            if corte(no):
                break
            x, y = adjacentes[no]
            i = y if x == i else x
        return segmentos, nos

    for no in sorted(adjacentes):
        verificar_cancelamento(cancelar)
        if corte(no):
            for i in adjacentes[no]:
                if i not in usados:
                    yield seguir(no, i)
    for i in sorted(assinaturas):
        if i not in usados:
            yield seguir(min(arestas[i]['a'], arestas[i]['b']), i)


def agrupar(trabalho, opcoes, amostra=None, cancelar=None):
    foto = trabalho['foto']
    arestas = foto['arestas']
    tubos = {p['uid']: p for p in foto['tubos']}
    por_pipe = {p['uid']: p for p in trabalho['tubulacoes']}
    destinos = {d['uid']: d for d in trabalho['destinos']}
    rotas = {r['uid']: r for r in trabalho['rotas']}
    usos = defaultdict(list)
    percursos = []
    for u, r in rotas.items():
        for papel, via in (('REFERENCIA', r), ('ALTERNATIVA', r.get('alternativa'))):
            verificar_cancelamento(cancelar)
            if via is None:
                continue
            p = dict(uid=f'{u}:{papel}', rota=u, papel=papel, origem=r['origem'], destino=r['destino'],
                     estado=r['alternativa_estado'], comprimento_m=via['comprimento_m'])
            percursos.append(p)
            for i in via['segmentos']:
                usos[i].append(p['uid'])
    por_percurso = {p['uid']: p for p in percursos}
    sem_orientacao = not trabalho['fontes']
    if sem_orientacao:
        usos.update((i, []) for i in range(len(arestas)))
    assinaturas = {i: tuple(sorted(v)) for i, v in sorted(usos.items())}
    terminais = {d['no_alvo'] for d in destinos.values() if d.get('no_alvo')}
    corredores, por_aresta = {}, {}
    transicoes = defaultdict(set)
    ids_hip = trabalho.get('hipotese') or {}
    for ordem, (indices, nos) in enumerate(sequencias(arestas, assinaturas, cancelar), 1):
        verificar_cancelamento(cancelar)
        uid = str(uuid5(NAMESPACE_URL, f"wna:{trabalho['uuid']}:{VERSAO}:{min(indices)}"))
        ps = [por_percurso[p] for p in assinaturas[indices[0]]]
        ds = sorted({p['destino'] for p in ps})
        fontes = sorted({p['origem'] for p in ps})
        refs = sum(p['papel']=='REFERENCIA' for p in ps)
        partes = list(dict.fromkeys(arestas[i]['tubo'] for i in indices))
        pipes = list(dict.fromkeys(tubos[u].get('feicao', u) for u in partes))
        conjunto_pipes = set(pipes)
        dependentes = [d for d in ds if conjunto_pipes.intersection(destinos[d]['criticas'])]
        funcoes = []
        if refs:
            funcoes.append('TRONCO' if refs > 1 else 'RAMAL')
            if nos[0] in terminais or nos[-1] in terminais:
                funcoes.append('TERMINAL')
        if len(ps) > refs:
            funcoes.append('ALTERNATIVO')
        if dependentes:
            funcoes.append('CRITICO')
        if not funcoes:
            funcoes.append('INDETERMINADO')
        exclusivos = {destinos[d]['origens'][0] for d in ds if len(destinos[d]['origens']) == 1}
        todos = {f for d in ds for f in destinos[d]['origens']}
        alternativas = {p['estado'] for p in ps}
        corredores[uid] = dict(uid=uid, codigo=f'C{ordem:04}', nome=f'C{ordem:04} · {FUNCOES[funcoes[0]]}',
            funcoes=funcoes, origens=fontes, fontes_alcancaveis=sorted(todos), fontes_exclusivas=sorted(exclusivos),
            destinos=ds, dependentes=dependentes, segmentos=indices, nos=nos, tubos=pipes, partes=partes,
            comprimento_m=sum(arestas[i]['comprimento_m'] for i in indices),
            diametros_mm=sorted({tubos[p]['diametro_mm'] for p in partes if tubos[p].get('diametro_mm') is not None}),
            percursos=[p['uid'] for p in ps], referencias=refs, alternativas=sorted(alternativas),
            estado='CIRCUITO' if nos[0] == nos[-1] else 'SEM_ORIENTACAO' if sem_orientacao else 'CONTINUO',
            topologia_uid=trabalho['topologia_uid'], hipotese_rev=ids_hip.get('rev'),
            cortes_indeterminados=sum(por_pipe[u]['estado']=='INDETERMINADA_LIMITE' for u in pipes),
            anteriores=[], posteriores=[])
        por_aresta.update((i, uid) for i in indices)
        transicoes[nos[0]].add(uid)
        transicoes[nos[-1]].add(uid)

    antes, depois = defaultdict(set), defaultdict(set)
    for p in percursos:
        verificar_cancelamento(cancelar)
        r = rotas[p['rota']]
        via = r if p['papel']=='REFERENCIA' else r['alternativa']
        ordem = []
        for i in via['segmentos']:
            u = por_aresta[i]
            if not ordem or ordem[-1] != u:
                ordem.append(u)
        p['corredores'] = ordem
        for anterior, posterior in zip(ordem, ordem[1:]):
            antes[posterior].add(anterior)
            depois[anterior].add(posterior)
    pares = Counter(tuple(sorted((c['nos'][0],c['nos'][-1]))) for c in corredores.values())
    for u, c in corredores.items():
        a, b = c['nos'][0], c['nos'][-1]
        c['conectados_n'] = (len(transicoes[a]) if a==b else
                             len(transicoes[a])+len(transicoes[b])-pares[tuple(sorted((a,b)))]) - 1
        c['anteriores'] = sorted(antes[u])
        c['posteriores'] = sorted(depois[u])
    return dict(analise_uid=trabalho['uuid'], algoritmo=VERSAO, parametros=opcoes, amostra=amostra,
                orientacao='PERCURSOS_DE_REFERENCIA' if not sem_orientacao else 'NAO_ORIENTADA',
                corredores=list(corredores.values()), percursos=percursos,
                encontros={no:sorted(ids) for no,ids in transicoes.items() if len(ids)>1})
