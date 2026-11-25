"""Componentes, origens e diagnósticos derivados de um grafo estrutural GIS."""

from collections import Counter, defaultdict
from math import isfinite

from auditoria_fronteiras.entradas import digest
from auditoria_fronteiras.modelos import verificar_cancelamento

from .grafo_gis import Uniao, _montar_segmentos


def _portas_validas(portas, tubos):
    if not portas:
        return False
    return all(uid in tubos and isinstance(pos, (int, float)) and isfinite(pos)
               and 0 <= pos <= 1 for uid, pos in portas)


def _diagnostico(tipo, tubos, **dados):
    return dict(uid=digest([tipo, sorted(tubos), dados.get('origem')]), tipo=tipo,
                tubos=sorted(tubos), situacao='A_REVISAR', **dados)


def _aplicar_conexoes(topologia, candidatos, conexoes, tubos, cancelar):
    indice = {c['uid']:c for c in candidatos}
    pendencias = []
    resolucoes = {}
    for regra in conexoes:
        verificar_cancelamento(cancelar)
        portas = [tuple(p) for p in regra['portas']]
        candidato = indice.get(regra.get('candidato'))
        if (len(set(portas)) < 2 or not _portas_validas(portas, tubos)
                or regra.get('candidato') and (candidato is None or portas != candidato['portas'])):
            resolucoes[regra['uuid']] = 'REFERENCIA_ALTERADA'
            pendencias.append(_diagnostico('EQUIPAMENTO_PENDENTE',
                                           {p[0] for p in portas if p[0] in tubos},
                                           origem=regra['uuid'], motivo='Conexão declarada com referência ausente ou alterada.'))
            continue
        decisao = regra.get('decisao', 'CONFIRMADA')
        resolucoes[regra['uuid']] = 'APLICADA' if decisao == 'CONFIRMADA' else decisao
        if candidato:
            candidato.update(situacao=decisao, revisao=regra['rev'])
        if decisao == 'CONFIRMADA':
            for porta in portas[1:]:
                topologia.unir(portas[0], porta)
            ids={p[0] for p in portas}
            setores={str(tubos[u]['setor_operacional']).strip() for u in ids
                     if tubos[u].get('setor_operacional') is not None}
            setores.discard('')
            if len({s.casefold() for s in setores})>1:
                pendencias.append(_diagnostico('MISTURA_SETORES', ids, origem=regra['uuid'],
                    setores_declarados=sorted(setores),
                    motivo='Conexão declarada na hipótese entre setores operacionais cadastrados distintos. '
                           'Verifique os controles de fronteira e as condições de operação.'))
    return pendencias, resolucoes


def _comprimentos(tubos, limite):
    faixas = {'Abaixo do limite':0., 'A partir do limite':0., 'Não informado':0.}
    diametros = set()
    for t in tubos:
        valor = t.get('diametro_mm')
        if valor is None:
            faixa = 'Não informado'
        else:
            diametros.add(valor)
            faixa = 'A partir do limite' if valor >= limite else 'Abaixo do limite'
        faixas[faixa] += t['comprimento_m']
    return faixas, sorted(diametros)


def concluir(tubos, linhas, topologia, candidatos, conexoes, origens, limite, cancelar):
    inventario = {t['uid']:t for t in tubos}
    diagn, resolucoes = _aplicar_conexoes(topologia, candidatos, conexoes, inventario, cancelar)
    origens_validas = {}
    for origem in origens:
        verificar_cancelamento(cancelar)
        portas = [tuple(p) for p in origem['portas']]
        if _portas_validas(portas, inventario):
            origens_validas[origem['uuid']] = portas
            for p in portas:
                topologia.raiz(p)
        else:
            diagn.append(_diagnostico('EQUIPAMENTO_PENDENTE', {p[0] for p in portas if p[0] in inventario},
                                      origem=origem['uuid'], motivo='Origem habilitada sem portas válidas no escopo.'))
    nos, no_por_porta, arestas = _montar_segmentos(tubos, linhas, topologia)
    componentes = Uniao()
    for a in arestas:
        verificar_cancelamento(cancelar)
        componentes.unir(a['a'], a['b'])
    grupos = defaultdict(list)
    for id_no in nos:
        grupos[componentes.raiz(id_no)].append(id_no)
    origens_por_grupo = defaultdict(set)
    for uid, portas in origens_validas.items():
        for p in portas:
            origens_por_grupo[componentes.raiz(no_por_porta[p])].add(uid)
    tubos_por_grupo = defaultdict(list)
    for t in tubos:
        tubos_por_grupo[componentes.raiz(no_por_porta[(t['uid'], 0.)])].append(t)
    conexoes_por_tubo = defaultdict(set)
    for c in candidatos:
        if c['situacao'] == 'CANDIDATA':
            for uid in c['tubos']:
                conexoes_por_tubo[uid].add(c['uid'])
    grupos_resultado = []
    for raiz, ts in tubos_por_grupo.items():
        verificar_cancelamento(cancelar)
        ids = [t['uid'] for t in ts]
        cands = set().union(*(conexoes_por_tubo[u] for u in ids))
        faixas, diametros = _comprimentos(ts, limite)
        alcancadas = sorted(origens_por_grupo[raiz])
        caixas = [t['extensao'] for t in ts if t.get('extensao')]
        grupo = dict(uid=digest(['componente', ids]), tubos=ids, nos=sorted(grupos[raiz]),
                     quantidade_tubos=len({t.get('feicao',t['uid']) for t in ts}),
                     comprimento_m=sum(t['comprimento_m'] for t in ts), diametros_mm=diametros,
                     max_mm=max(diametros,default=None), faixas_m=faixas, origens=alcancadas,
                     candidatas=sorted(cands), zonas=sorted({z for t in ts for z in t.get('zonas',())}),
                     zonas_uids=sorted({z for t in ts for z in t.get('zonas_uids',())}),
                     extensao=[min(v[0] for v in caixas), min(v[1] for v in caixas),
                               max(v[2] for v in caixas), max(v[3] for v in caixas)] if caixas else None,
                     situacao='ALCANCAVEL' if alcancadas else 'SEM_ORIGEM_ALCANCAVEL' if origens_validas else 'SEM_ORIGENS_VALIDAS')
        grupos_resultado.append(grupo)
    grupos_resultado.sort(key=lambda g:(-g['comprimento_m'],g['uid']))
    grupos_por_tubo={uid:g['uid'] for g in grupos_resultado for uid in g['tubos']}
    por_grupo=defaultdict(set)
    for c in candidatos:
        c['componentes']=sorted({grupos_por_tubo[t] for t in c['tubos']})
        if c['situacao']=='CANDIDATA':
            for uid in c['componentes']:
                por_grupo[uid].update(g for g in c['componentes'] if g!=uid)
    for i,g in enumerate(grupos_resultado):
        g['componentes_candidatos']=sorted(por_grupo[g['uid']])
        ref = dict(componente=g['uid'], comprimento_m=g['comprimento_m'], max_mm=g['max_mm'])
        if i:
            diagn.append(_diagnostico('COMPONENTE_INDEPENDENTE', g['tubos'], **ref))
        if g['situacao']=='SEM_ORIGEM_ALCANCAVEL':
            diagn.append(_diagnostico('SEM_ORIGEM', g['tubos'], **ref))
        if i or g['candidatas'] or g['situacao']=='SEM_ORIGEM_ALCANCAVEL':
            relevantes = [u for u in g['tubos'] if (inventario[u].get('diametro_mm') or 0)>=limite
                          or inventario[u].get('classificacao')=='ADUCAO']
            if relevantes:
                diagn.append(_diagnostico('REDE_PRINCIPAL', relevantes, componente=g['uid'],
                                           comprimento_m=sum(inventario[u]['comprimento_m'] for u in relevantes),
                                           max_mm=max((inventario[u].get('diametro_mm') or 0 for u in relevantes),default=0) or None,
                                           criterio=f'Diâmetro ≥ {limite:g} mm ou classificação cadastrada como adução.'))
    return dict(tubos=tubos, nos=list(nos.values()), arestas=arestas, componentes=grupos_resultado,
                diagnosticos=candidatos+diagn, origens_validas=sorted(origens_validas),
                resolucoes_conexoes=resolucoes,
                ramos=sorted(u for u,n in Counter(v for a in arestas for v in (a['a'],a['b'])).items() if n>=3))


def comparar(a, b):
    if a['projeto_uid'] != b['projeto_uid']:
        raise ValueError('Escolha dois resultados do mesmo projeto.')
    def indexar(d):
        return {t:g for g in d['componentes'] for t in g['tubos']}
    x, y = indexar(a), indexar(b)
    comuns = x.keys() & y.keys()
    return dict(adicionadas=sorted(y.keys()-x.keys()), ausentes=sorted(x.keys()-y.keys()),
                ganhou_origem=sorted(t for t in comuns if not x[t]['origens'] and y[t]['origens']),
                perdeu_origem=sorted(t for t in comuns if x[t]['origens'] and not y[t]['origens']),
                mudaram_componente=sorted(t for t in comuns if x[t]['uid'] != y[t]['uid']))
