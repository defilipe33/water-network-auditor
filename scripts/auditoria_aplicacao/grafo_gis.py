"""Grafo estrutural GIS. Geometria gera candidatos; somente regras explícitas unem portas."""

from collections import defaultdict
from itertools import combinations
from math import isfinite

from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsRectangle, QgsSpatialIndex

from auditoria_fronteiras.entradas import digest
from auditoria_fronteiras.modelos import verificar_cancelamento


VERSAO = 'gis-grafo-1'
ESTRATEGIAS = {'CADASTRADAS', 'INFERIR', 'COMBINAR'}
EPS = 1e-8
ROTULOS = {
    'COMPONENTE_INDEPENDENTE': 'Componente independente',
    'SEM_ORIGEM': 'Sem origem definida alcançável',
    'REDE_PRINCIPAL': 'Rede principal sem ligação conhecida',
    'CONEXAO_T': 'Possível conexão em T',
    'EXTREMIDADES_PROXIMAS': 'Extremidades próximas',
    'CRUZAMENTO': 'Cruzamento ambíguo',
    'SOBREPOSICAO': 'Sobreposição de tubulações',
    'EQUIPAMENTO_PENDENTE': 'Equipamento sem conexão definida',
    'MISTURA_SETORES': 'Possível mistura de setores',
}


class Uniao:
    def __init__(self):
        self.pais = {}
        self.tamanhos = {}

    def raiz(self, porta):
        if porta not in self.pais:
            self.pais[porta] = porta
            self.tamanhos[porta] = 1
        while self.pais[porta] != porta:
            self.pais[porta] = self.pais[self.pais[porta]]
            porta = self.pais[porta]
        return porta

    def unir(self, a, b):
        a, b = self.raiz(a), self.raiz(b)
        if a == b:
            return
        if self.tamanhos[a] < self.tamanhos[b]:
            a, b = b, a
        self.pais[b] = a
        self.tamanhos[a] += self.tamanhos[b]


def _indexar(geometrias, guardar_geometrias=False):
    indice = (QgsSpatialIndex(flags=QgsSpatialIndex.FlagStoreFeatureGeometries)
              if guardar_geometrias else QgsSpatialIndex())
    for i, g in enumerate(geometrias):
        f = QgsFeature(i)
        f.setGeometry(g)
        indice.addFeature(f)
    return indice


def _vizinhos(indice, geom, tolerancia):
    caixa = QgsRectangle(geom.boundingBox())
    caixa.grow(tolerancia)
    return indice.intersects(caixa)


def _partes(geom):
    if geom.isEmpty():
        return
    if geom.isMultipart():
        for parte in geom.asGeometryCollection():
            yield from _partes(parte)
    else:
        yield geom


def _candidato(tipo, portas, geom, **dados):
    chaves = sorted(tuple(p) for p in portas)
    return dict(uid=digest([tipo, chaves, geom.asWkt(9)]), tipo=tipo, portas=chaves,
                tubos=sorted({p[0] for p in chaves}), wkb=geom.asWkb().data().hex(),
                situacao='CANDIDATA', **dados)


def _agrupar_portas(extremos, ancoras, estrategia, tolerancia, inferir_proximas, uniao, conexoes, cancelar):
    pontos = [r[1] for r in extremos]
    indice = _indexar(pontos)
    pontos_ancora = [a['geom'] for a in ancoras]
    indice_ancora = _indexar(pontos_ancora)
    vizinhos = [set() for _ in pontos]
    por_ancora = defaultdict(set)
    ancoras_por_extremo = {}
    bloqueios = defaultdict(set)
    for r in conexoes:
        if r.get('decisao')!='SEPARADA' or r.get('categoria_candidata')!='EXTREMIDADES_PROXIMAS':
            continue
        portas=[tuple(p) for p in r['portas']]
        if len(portas)==2 and all(p[1] in (0.,1.) for p in portas):
            a,b=portas
            bloqueios[a].add(b);bloqueios[b].add(a)

    def tem_separacao(indices):
        portas={extremos[k][0] for k in indices}
        return any(bloqueios.get(p,set()) & portas for p in portas)
    for i, ponto in enumerate(pontos):
        verificar_cancelamento(cancelar)
        vizinhos[i] = {j for j in _vizinhos(indice, ponto, tolerancia)
                       if i != j and 0 <= ponto.distance(pontos[j]) <= tolerancia}
        if estrategia != 'INFERIR':
            candidatas = {j for j in _vizinhos(indice_ancora, ponto, tolerancia)
                          if 0 <= ponto.distance(pontos_ancora[j]) <= tolerancia}
            ancoras_por_extremo[i] = candidatas
            for j in candidatas:
                por_ancora[j].add(i)

    for i, candidatas in ancoras_por_extremo.items():
        if len(candidatas) != 1:
            continue
        j = next(iter(candidatas))
        membros = por_ancora[j]
        if (not tem_separacao(membros)
                and all(len(ancoras_por_extremo[k]) == 1 and membros <= vizinhos[k] | {k} for k in membros)):
            uniao.unir(extremos[i][0], ('J', ancoras[j]['uid']))
    if estrategia != 'CADASTRADAS':
        visitados = set()
        for i, ponto in enumerate(pontos):
            if i in visitados or ancoras_por_extremo.get(i):
                continue
            grupo = {i} | vizinhos[i]
            if any(ancoras_por_extremo.get(k) or grupo != vizinhos[k] | {k} for k in grupo):
                continue
            visitados.update(grupo)
            if not tem_separacao(grupo) and (inferir_proximas or all(ponto.distance(pontos[k]) <= EPS for k in grupo)):
                for k in grupo:
                    uniao.unir(extremos[i][0], extremos[k][0])

    candidatos = []
    for i, (porta, ponto) in enumerate(extremos):
        for j in sorted(vizinhos[i]):
            outra, geom = extremos[j]
            if j <= i or outra[0] == porta[0] or uniao.raiz(porta) == uniao.raiz(outra):
                continue
            candidatos.append(_candidato(
                'EXTREMIDADES_PROXIMAS', [porta, outra], ponto,
                distancia_m=ponto.distance(geom), concorrentes=len((vizinhos[i] | vizinhos[j]) - {i,j}),
            ))
    return candidatos, indice_ancora, indice


def _fracao(linha, ponto, margem=EPS):
    medida = linha.lineLocatePoint(ponto)
    comprimento = linha.length()
    if margem < medida < comprimento - margem:
        return round(medida / comprimento, 12)
    return None


def _conexoes_geometricas(tubos, linhas, extremos, indice_extremos, ancoras, indice_ancora, tolerancia, cancelar):
    indice = _indexar(linhas)
    candidatos = []
    for porta, ponto in extremos:
        verificar_cancelamento(cancelar)
        possiveis = []
        for j in sorted(_vizinhos(indice, ponto, tolerancia)):
            receptor = tubos[j]['uid']
            if receptor == porta[0]:
                continue
            linha = linhas[j]
            distancia = linha.distance(ponto)
            if not 0 <= distancia <= tolerancia:
                continue
            fracao = _fracao(linha, ponto)
            if fracao is not None:
                projetado = linha.interpolate(fracao * linha.length())
                possiveis.append((receptor, fracao, projetado, distancia))
        for receptor, fracao, projetado, distancia in possiveis:
            nos_proximos = [ancoras[k]['uid'] for k in _vizinhos(indice_ancora, projetado, tolerancia)
                            if ancoras[k]['geom'].distance(projetado) <= tolerancia]
            pontas_proximas = [extremos[k][0] for k in _vizinhos(indice_extremos, projetado, tolerancia)
                               if extremos[k][0] != porta and extremos[k][1].distance(projetado) <= tolerancia]
            candidatos.append(_candidato('CONEXAO_T', [porta, (receptor, fracao)], projetado,
                                         distancia_m=distancia, concorrentes=len(possiveis)-1,
                                         tubulacao_termina=porta[0], tubulacao_receptora=receptor,
                                         outros_receptores=[u for u,_,_,_ in possiveis if u!=receptor],
                                         junctions_proximas=nos_proximos, pontas_proximas=pontas_proximas))
    for i, linha in enumerate(linhas):
        verificar_cancelamento(cancelar)
        for j in sorted(indice.intersects(linha.boundingBox())):
            if j <= i:
                continue
            verificar_cancelamento(cancelar)
            intersecao = linha.intersection(linhas[j])
            if intersecao.lastError():
                raise ValueError('Falha geométrica ao verificar duas tubulações do escopo.')
            for parte in _partes(intersecao):
                if parte.type() == 1 and parte.length() > EPS:
                    candidatos.append(_candidato('SOBREPOSICAO', [(tubos[i]['uid'], 0.), (tubos[j]['uid'], 0.)],
                                                  parte, comprimento_m=parte.length()))
                elif parte.type() == 0:
                    a, b = _fracao(linha, parte), _fracao(linhas[j], parte)
                    # Pontas no interior de outro Pipe já são representadas pelo detector em T.
                    if a is not None and b is not None:
                        candidatos.append(_candidato('CRUZAMENTO', [(tubos[i]['uid'], a), (tubos[j]['uid'], b)], parte))
    return candidatos


def _montar_segmentos(tubos, linhas, uniao):
    portas = defaultdict(list)
    for uid, pos in uniao.pais:
        if uid != 'J':
            portas[uid].append(pos)
    for t in tubos:
        u=t['uid']
        acumuladas=[]
        for p in sorted(portas[u]):
            if acumuladas and (p-acumuladas[-1])*t['comprimento_m']<=EPS and (p,acumuladas[-1])!=(1.,0.):
                uniao.unir((u,acumuladas[-1]),(u,p))
                if p==1.:acumuladas[-1]=p
            else:acumuladas.append(p)
        portas[u]=acumuladas
    membros = defaultdict(list)
    for porta in uniao.pais:
        membros[uniao.raiz(porta)].append(porta)
    nos, no_por_porta = {}, {}
    geometrias = {t['uid']: g for t,g in zip(tubos, linhas)}
    for membros_no in membros.values():
        uid = digest(['no', sorted(membros_no, key=str)])
        p = min((p for p in membros_no if p[0] != 'J'), default=None)
        if p is None:
            continue
        linha = geometrias[p[0]]
        coord = linha.interpolate(linha.length() * p[1]).asPoint()
        nos[uid] = dict(uid=uid, xy=[coord.x(),coord.y()], portas=sorted(membros_no, key=str),
                        natureza='JUNCTION_CADASTRADA' if any(p[0]=='J' for p in membros_no)
                        else 'NO_TOPOLOGICO_GIS')
        for porta in membros_no:
            no_por_porta[porta] = uid
    arestas = []
    for t in tubos:
        p = sorted(portas[t['uid']])
        arestas.extend(dict(tubo=t['uid'], inicio=p1, fim=p2, a=no_por_porta[(t['uid'], p1)],
                            b=no_por_porta[(t['uid'], p2)], comprimento_m=t['comprimento_m']*(p2-p1))
                       for p1,p2 in zip(p,p[1:]))
    return nos, no_por_porta, arestas


def construir(tubos, junctions=(), *, tolerancia=.20, estrategia='COMBINAR',
              inferir_proximas=False, conexoes=(), origens=(), limite_mm=200.,
              cancelar=None, etapa=lambda *_:None):
    """Recebe geometrias métricas copiadas. Toda linha mantém identidade e comprimento originais."""
    if not isfinite(tolerancia) or not 0 <= tolerancia <= 100 or estrategia not in ESTRATEGIAS:
        raise ValueError('Confira a tolerância em metros e a estratégia de Junctions.')
    if not isfinite(limite_mm) or limite_mm <= 0:
        raise ValueError('Informe um limite de diâmetro positivo em milímetros.')
    tubos = sorted(tubos, key=lambda t:t['uid'])
    if not tubos or len({t['uid'] for t in tubos}) != len(tubos):
        raise ValueError('São necessárias tubulações com identidades distintas.')
    linhas = [t['geom'] for t in tubos]
    tubos = [dict({k:v for k,v in t.items() if k!='geom'}, comprimento_m=g.length(),
                  wkb=g.asWkb().data().hex()) for t,g in zip(tubos,linhas)]
    cadastrados = [(t,g) for t,g in zip(tubos,linhas) if not t.get('proposta_uid')]
    extremos = [((t['uid'],pos), g.interpolate(pos*t['comprimento_m'])) for t,g in cadastrados
                for pos in (0.,1.)]
    topologia = Uniao()
    for t in tubos:
        for pos in (0.,1.):topologia.raiz((t['uid'],pos))
    etapa(0, 'Conferindo extremidades e Junctions')
    candidatos, indice_ancora, indice_extremos = _agrupar_portas(
        extremos, junctions, estrategia, tolerancia, inferir_proximas, topologia, conexoes, cancelar)
    etapa(0, 'Identificando conexões em T, cruzamentos e sobreposições')
    candidatos.extend(_conexoes_geometricas([t for t,_ in cadastrados], [g for _,g in cadastrados], extremos, indice_extremos, junctions,
                                           indice_ancora, tolerancia, cancelar))
    etapa(0, 'Aplicando as relações selecionadas e verificando componentes')
    from .diagnosticos_grafo_gis import concluir
    resultado = concluir(tubos, linhas, topologia, candidatos, conexoes, origens, limite_mm, cancelar)
    from .prioridade_cruzamentos import classificar
    for r in resultado['diagnosticos']:
        if r['tipo'] == 'CRUZAMENTO':
            break
    else:
        return resultado
    prioridade = classificar(resultado, cancelar=cancelar, tolerancia=tolerancia)
    for r in resultado['diagnosticos']:
        if r['uid'] in prioridade:
            r['prioridade_cruzamento'] = prioridade[r['uid']]
    return resultado
