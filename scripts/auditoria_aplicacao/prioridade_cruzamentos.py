"""Classifica a relevância de revisão sem modificar a topologia ou vereditos."""

from bisect import bisect_left, bisect_right
from collections import defaultdict
from math import isfinite

from auditoria_fronteiras.modelos import verificar_cancelamento


FILTROS = {
    'PRIORITARIOS': 'Prioritários', 'TODOS': 'Todos os cruzamentos',
    'ALTA': 'Prioridade alta', 'INTERMEDIARIA': 'Prioridade intermediária', 'BAIXA': 'Prioridade baixa',
    'ISOLADOS': 'Componentes independentes', 'PONTAS': 'Próximos às extremidades',
    'REVISADOS': 'Já revisados', 'NAO_REVISADOS': 'Ainda não revisados',
}
ROTULOS = {'ALTA': 'Alta', 'INTERMEDIARIA': 'Intermediária', 'BAIXA': 'Baixa'}
ORDEM = {nivel: i for i, nivel in enumerate(ROTULOS)}


def posicoes(r, comprimentos):
    ps = sorted(r.get('portas', ()))
    if len(ps) != 2 or ps[0][0] == ps[1][0]:
        return ()
    metros = []
    for u, f in ps:
        comp = comprimentos.get(u)
        if comp is None or not isfinite(comp) or comp <= 0 or not isinstance(f, (float, int)) or not 0 <= f <= 1:
            return ()
        metros.append((u, f * comp))
    return tuple(metros)


def classificar(foto, limiar=None, cancelar=None, *, tolerancia=None):
    tol = foto.get('parametros', {}).get('tolerancia', .2) if tolerancia is None else tolerancia
    limite = tol if limiar is None else limiar
    if not all(isinstance(v, (int, float)) and isfinite(v) and v >= 0 for v in (tol, limite)):
        raise ValueError('Informe distâncias finitas e não negativas em metros.')
    diagn = foto['diagnosticos']
    tubos = {t['uid']: t for t in foto['tubos']}
    comprimentos = {u: t.get('comprimento_m') for u, t in tubos.items()}
    componentes = {t: g for g in foto['componentes'] for t in g['tubos']}
    principal = foto['componentes'][0]['uid'] if foto['componentes'] else None
    conexoes_t = defaultdict(list)
    cruzamentos = {}
    for r in diagn:
        verificar_cancelamento(cancelar)
        if r['tipo'] not in ('CONEXAO_T', 'CRUZAMENTO'):
            continue
        ps = posicoes(r, comprimentos)
        if r['tipo'] == 'CONEXAO_T' and ps:
            conexoes_t[ps[0][0], ps[1][0]].append((ps[0][1], ps[1][1], r['uid']))
        elif r['tipo'] == 'CRUZAMENTO':
            cruzamentos[r['uid']] = (r, ps)
    for candidatos in conexoes_t.values():
        candidatos.sort()
    encontrados = {}
    reverso = defaultdict(list)
    saida = {}
    for u, (r, ps) in cruzamentos.items():
        verificar_cancelamento(cancelar)
        cs = [componentes[t] for t in r['tubos'] if t in componentes]
        grupos = {g['uid']: g for g in cs}
        diferentes = len(grupos) > 1
        proximidade = min((min(m, comprimentos[t] - m) for t, m in ps), default=None)
        isolado = diferentes and any(k != principal for k in grupos)
        sem_origem = diferentes and any(g['situacao'] == 'SEM_ORIGEM_ALCANCAVEL' for g in cs)
        if not ps or len(cs) != 2:
            nivel, motivo = 'INTERMEDIARIA', 'Posições ou componentes incompletos.'
        elif proximidade <= limite:
            nivel, motivo = 'ALTA', f'Extremidade a {proximidade:.3f} m do cruzamento.'
        elif sem_origem:
            nivel, motivo = 'ALTA', 'O cruzamento envolve componentes distintos e um deles está sem origem alcançável.'
        elif isolado and any(g['quantidade_tubos'] == 1 for g in cs):
            nivel, motivo = 'ALTA', 'O cruzamento envolve uma tubulação isolada de outro componente.'
        elif diferentes:
            nivel, motivo = 'INTERMEDIARIA', 'Os Pipes pertencem a componentes distintos e cruzam em trechos intermediários.'
        else:
            nivel, motivo = 'BAIXA', 'Os Pipes já pertencem ao mesmo componente e cruzam em trechos intermediários.'
        if ps:
            (a, x), (b, y) = ps
            possiveis = conexoes_t[a, b]
            inicio = bisect_left(possiveis, (x - tol, -float('inf')))
            fim = bisect_right(possiveis, (x + tol, float('inf')))
            ties = [v for _, ny, v in possiveis[inicio:fim] if abs(ny - y) <= tol]
            if len(ties) == 1:
                encontrados[u] = ties[0]
                reverso[ties[0]].append(u)
        saida[u] = dict(nivel=nivel, motivo=motivo, extremidade_m=proximidade, limiar_m=limite,
                       ponta=proximidade is not None and proximidade <= limite, isolado=isolado,
                       acessos={k: g['situacao'] for k, g in sorted(grupos.items())}, referencia_t=None)
    for u, t in encontrados.items():
        if len(reverso[t]) == 1:
            r = saida[u]
            r['referencia_t'] = t
            r['motivo'] += f' A situação também é representada pela conexão em T {t[:10]}.'
    return saida


def atende(d, filtro, revisado=False):
    if filtro == 'REVISADOS':
        return revisado
    if filtro == 'NAO_REVISADOS':
        return not revisado
    if filtro == 'TODOS' or not d:
        return True
    if filtro == 'PRIORITARIOS':
        return d['nivel'] != 'BAIXA' and not d['referencia_t']
    if filtro in ('ISOLADOS', 'PONTAS'):
        return d['isolado' if filtro == 'ISOLADOS' else 'ponta']
    return d['nivel'] == filtro
