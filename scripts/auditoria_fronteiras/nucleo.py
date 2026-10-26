"""Detecção por posição ao longo de cada parte, sem alterar dados de origem.

Não usa união de polígonos: fronteiras internas, aninhadas e sobrepostas
permanecem independentes. Antes/depois segue a digitalização, não a vazão.
"""
from collections import defaultdict
from math import hypot
from time import perf_counter

from qgis.core import (Qgis, QgsFeature, QgsGeometry, QgsPointXY, QgsRectangle,
                       QgsSpatialIndex, QgsWkbTypes)
from .entradas import crs_processamento, digest, ler_camadas
from .modelos import (Cancelado, Modo, Ocorrencia, Parametros, Resultado,
                      verificar_cancelamento)


def _ponto(xy):
    return QgsGeometry.fromPointXY(QgsPointXY(xy))


def _partes(geom):
    return geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]


def _componentes(geom):
    if geom.isNull() or geom.isEmpty():
        return
    if geom.isMultipart() or QgsWkbTypes.flatType(geom.wkbType()) == QgsWkbTypes.GeometryCollection:
        for parte in geom.asGeometryCollection():
            yield from _componentes(parte)
    else:
        yield geom


def _unicos(valores, epsilon):
    saida = []
    for valor in sorted(valores):
        if not saida or valor - saida[-1] > epsilon:
            saida.append(valor)
    return saida


def _trecho(linha, a, b):
    vertices = linha.asPolyline()
    pontos = [linha.interpolate(a).asPoint()]
    distancia = 0.0
    for p, q in zip(vertices, vertices[1:]):
        distancia += hypot(q.x() - p.x(), q.y() - p.y())
        if a < distancia < b:
            pontos.append(q)
    pontos.append(linha.interpolate(b).asPoint())
    return QgsGeometry.fromPolylineXY([QgsPointXY(p) for p in pontos])


def _indice(elementos):
    indice = QgsSpatialIndex()
    mapa = {}
    for i, elemento in enumerate(elementos):
        f = QgsFeature(i)
        f.setGeometry(elemento.geometria)
        indice.addFeature(f)
        mapa[i] = elemento
    return indice, mapa


def _intersecoes(linha, fronteira, epsilon, cancelar=None):
    """Interseção por segmento preserva múltiplas visitas à mesma coordenada."""
    pontos, intervalos = [], []
    acumulado = 0.0
    vertices = linha.asPolyline()
    for a, b in zip(vertices, vertices[1:]):
        verificar_cancelamento(cancelar)
        comprimento = hypot(b.x() - a.x(), b.y() - a.y())
        if comprimento <= epsilon:
            acumulado += comprimento
            continue
        segmento = QgsGeometry.fromPolylineXY([a, b])
        inter = segmento.intersection(fronteira)
        if inter.lastError():
            raise ValueError(inter.lastError())
        def pos(p):
            # Projeção no segmento, não na linha completa (que pode se cruzar).
            fracao = ((p.x() - a.x()) * (b.x() - a.x())
                      + (p.y() - a.y()) * (b.y() - a.y())) / comprimento ** 2
            return acumulado + min(1., max(0., fracao)) * comprimento
        for componente in _componentes(inter):
            tipo = QgsWkbTypes.geometryType(componente.wkbType())
            if tipo == QgsWkbTypes.PointGeometry:
                pontos.append(pos(componente.asPoint()))
            elif tipo == QgsWkbTypes.LineGeometry:
                valores = [pos(p) for p in componente.asPolyline()]
                if valores:
                    intervalos.append((min(valores), max(valores)))
            else:
                raise ValueError("Interseção com dimensão não suportada")
        acumulado += comprimento
    unidos = []
    for a, b in sorted(intervalos):
        if b - a <= epsilon:
            pontos.append(a)
        elif unidos and a <= unidos[-1][1] + epsilon:
            unidos[-1] = (unidos[-1][0], max(b, unidos[-1][1]))
        else:
            unidos.append((a, b))
    pontos = [p for p in _unicos(pontos, epsilon)
              if not any(a - epsilon <= p <= b + epsilon for a, b in unidos)]
    if vertices and vertices[0] == vertices[-1]:
        pontos = _unicos([0. if abs(p - linha.length()) <= epsilon else p
                          for p in pontos], epsilon)
    return pontos, unidos


def _amostras(linha, posicao, cortes, epsilon):
    comprimento = linha.length()
    anteriores = [v for v in cortes if v < posicao - epsilon]
    posteriores = [v for v in cortes if v > posicao + epsilon]
    antes = (linha.interpolate((max(anteriores, default=0.) + posicao) / 2)
             if posicao > epsilon else None)
    depois = (linha.interpolate((min(posteriores, default=comprimento) + posicao) / 2)
              if posicao < comprimento - epsilon else None)
    vertices = linha.asPolyline()
    if vertices and vertices[0] == vertices[-1]:
        if antes is None:
            ultimo = max((v for v in cortes if v < comprimento - epsilon), default=0.)
            antes = linha.interpolate((ultimo + comprimento) / 2)
        if depois is None:
            primeiro = min((v for v in cortes if v > epsilon), default=comprimento)
            depois = linha.interpolate(primeiro / 2)
    return antes, depois


def _regioes(ponto, indice, mapa, fronteiras, tolerancia, permitidos=None):
    if ponto is None:
        return [], False
    caixa = ponto.boundingBox()
    caixa.grow(tolerancia)
    candidatos, incerto = [], False
    for fid in sorted(indice.intersects(caixa)):
        poligono = mapa[fid]
        if permitidos is not None and poligono.chave not in permitidos:
            continue
        distancia = fronteiras[poligono.chave].distance(ponto)
        if distancia < 0:
            raise ValueError("Falha ao medir distância à fronteira")
        sobre_borda = distancia <= tolerancia
        if poligono.geometria.contains(ponto) or sobre_borda:
            candidatos.append(poligono.referencia())
        incerto = incerto or sobre_borda
    return candidatos, incerto


def _emitir(resultado, tubo, parte, linha, pos, modo, poligonos, classe,
            antes=None, depois=None, candidatos_antes=None, candidatos_depois=None,
            incerto=False, intervalo=None, detalhes=None):
    refs = sorted((p.referencia() for p in poligonos), key=lambda r: r['chave'])
    ambigua = incerto or len(candidatos_antes or []) > 1 or len(candidatos_depois or []) > 1
    geometria = _trecho(linha, *intervalo) if intervalo else linha.interpolate(pos)
    identidade = [tubo.chave, parte, modo.value, [r['chave'] for r in refs],
                  pos, intervalo, classe, detalhes]
    observacoes = ["Auditoria espacial; não comprova conexão ou operação hidráulica.",
                   "Antes/depois segue a orientação geométrica da parte da tubulação."]
    if ambigua:
        observacoes.append("Candidatos múltiplos ou amostra próxima/sobre fronteira; revisar.")
    if antes is None or depois is None:
        observacoes.append("Lado ausente na extremidade não significa área sem cobertura.")
    resultado.ocorrencias.append(Ocorrencia(
        digest(identidade), classe, modo, geometria, [tubo.referencia()], refs,
        parte, pos, candidatos_antes or [], candidatos_depois or [],
        antes is not None, depois is not None, ambigua, observacoes,
        dict(detalhes or {}, **({'intervalo_m': list(intervalo)} if intervalo else {}))))


def _analisar_parte(tubo, parte, linha, poligonos, fronteiras, indices_origem, resultado, cancelar):
    epsilon = max(1e-9, linha.length() * 1e-12)
    tol = resultado.parametros.tolerancia_geometrica
    por_origem = defaultdict(list)
    dados = {}
    for poligono in poligonos:
        verificar_cancelamento(cancelar)
        pontos, intervalos = _intersecoes(linha, fronteiras[poligono.chave], epsilon, cancelar)
        if pontos or intervalos:
            dados[poligono.chave] = (pontos, intervalos)
            por_origem[poligono.origem].append(poligono)
    for origem, atingidos in por_origem.items():
        modo = atingidos[0].modo
        # Todas as regiões candidatas da camada, inclusive as que contêm a linha
        # sem cruzar seu perímetro, participam da leitura antes/depois.
        indice, mapa = indices_origem[origem]
        if modo == Modo.PERIMETRO:
            lotes = [[p] for p in atingidos]
        else:
            lotes = [atingidos]
        for lote in lotes:
            permitidos = {p.chave for p in lote} if modo == Modo.PERIMETRO else None
            pontos = [(m, p) for p in lote for m in dados[p.chave][0]]
            spans = [(a, b, p) for p in lote for a, b in dados[p.chave][1]]
            cortes = _unicos([0., linha.length()] + [m for m, _ in pontos]
                            + [v for a, b, _ in spans for v in (a, b)], epsilon)
            for m in _unicos([v for v, _ in pontos], epsilon):
                verificar_cancelamento(cancelar)
                envolvidos = [p for v, p in pontos if abs(v - m) <= epsilon]
                antes, depois = _amostras(linha, m, cortes, epsilon)
                ca, ia = _regioes(antes, indice, mapa, fronteiras, tol, permitidos)
                cd, id_ = _regioes(depois, indice, mapa, fronteiras, tol, permitidos)
                incerto = ia or id_
                if antes is None or depois is None:
                    classe = "EXTREMIDADE"
                elif incerto:
                    classe = "AMBIGUA"
                else:
                    # Classificação independente do conjunto de candidatos da camada.
                    atravessa = any(p.geometria.contains(antes) != p.geometria.contains(depois)
                                     for p in envolvidos)
                    classe = "TRAVESSIA" if atravessa else "TANGENCIA"
                _emitir(resultado, tubo, parte, linha, m, modo, envolvidos, classe,
                        antes, depois, ca if modo == Modo.TRANSICAO else [],
                        cd if modo == Modo.TRANSICAO else [], incerto,
                        detalhes={"x": linha.interpolate(m).asPoint().x(),
                                  "y": linha.interpolate(m).asPoint().y()})
            # Intervalos coincidentes em fronteiras compartilhadas tornam-se
            # intervalos atômicos únicos com todos os polígonos relacionados.
            limites = _unicos([v for a, b, _ in spans for v in (a, b)], epsilon)
            for a, b in zip(limites, limites[1:]):
                envolvidos = [p for x, y, p in spans if x <= (a+b)/2 <= y]
                if not envolvidos:
                    continue
                antes, _ = _amostras(linha, a, cortes, epsilon)
                _, depois = _amostras(linha, b, cortes, epsilon)
                ca, ia = _regioes(antes, indice, mapa, fronteiras, tol, permitidos)
                cd, id_ = _regioes(depois, indice, mapa, fronteiras, tol, permitidos)
                _emitir(resultado, tubo, parte, linha, a, modo, envolvidos, "COINCIDENCIA",
                        antes, depois, ca if modo == Modo.TRANSICAO else [],
                        cd if modo == Modo.TRANSICAO else [], ia or id_, (a, b))


def _continuidades(tubos, partes, poligonos, fronteiras, indice_pol, mapa_pol,
                   resultado, cancelar):
    raio = resultado.parametros.distancia_continuidade
    tol = resultado.parametros.tolerancia_geometrica
    extremos, indice = {}, QgsSpatialIndex()
    for tubo in tubos:
        for parte, linha in enumerate(partes.get(tubo.chave, [])):
            # Anéis fechados não possuem extremidades livres.
            vertices = linha.asPolyline()
            if len(vertices) < 2 or linha.length() <= 0 or vertices[0] == vertices[-1]:
                continue
            for lado, m in (("INICIO", 0.), ("FIM", linha.length())):
                ponto = linha.interpolate(m)
                i = len(extremos)
                extremos[i] = (tubo, parte, linha, lado, ponto)
                f = QgsFeature(i)
                f.setGeometry(ponto)
                indice.addFeature(f)
    for i, (tubo, parte, linha, lado, ponto) in extremos.items():
        verificar_cancelamento(cancelar)
        caixa = ponto.boundingBox()
        caixa.grow(raio)
        for j in sorted(indice.intersects(caixa)):
            if j <= i:
                continue
            outro, outra_parte, outra_linha, outro_lado, outro_ponto = extremos[j]
            if tubo.chave == outro.chave:
                continue
            distancia = ponto.distance(outro_ponto)
            if distancia > raio:
                continue
            busca = QgsRectangle(ponto.boundingBox())
            busca.combineExtentWith(outro_ponto.boundingBox())
            busca.grow(raio + tol)
            por_origem = defaultdict(list)
            lados = {}
            for fid in sorted(indice_pol.intersects(busca)):
                pol = mapa_pol[fid]
                borda = fronteiras[pol.chave]
                if max(borda.distance(ponto), borda.distance(outro_ponto)) > raio + tol:
                    continue
                def lado_interior(l, endpoint, extremo):
                    # Na borda, usar o primeiro intervalo livre de interseções.
                    if borda.distance(endpoint) > tol:
                        return pol.geometria.contains(endpoint)
                    eps = max(1e-9, l.length()*1e-12)
                    hits, spans = _intersecoes(l, borda, eps, cancelar)
                    cortes = _unicos([0., l.length()] + hits + [v for a,b in spans for v in (a,b)], eps)
                    amostra = _amostras(l, 0. if extremo == 'INICIO' else l.length(), cortes, eps)
                    q = amostra[1] if extremo == 'INICIO' else amostra[0]
                    if q is None or borda.distance(q) <= tol:
                        return None
                    return pol.geometria.contains(q)
                a = lado_interior(linha, ponto, lado)
                b = lado_interior(outra_linha, outro_ponto, outro_lado)
                if a is None or b is None or a == b:
                    continue
                # Exigir contato do conector com a fronteira para pares afastados.
                if distancia > tol:
                    conector = QgsGeometry.fromPolylineXY([QgsPointXY(ponto.asPoint()),
                                                          QgsPointXY(outro_ponto.asPoint())])
                    if not conector.intersects(borda):
                        continue
                por_origem[pol.origem].append(pol)
                lados[pol.chave] = [a, b]
            for origem, envolvidos in por_origem.items():
                lotes = [[p] for p in envolvidos] if envolvidos[0].modo == Modo.PERIMETRO else [envolvidos]
                for lote in lotes:
                    p, q = ponto.asPoint(), outro_ponto.asPoint()
                    meio = QgsPointXY((p.x()+q.x())/2, (p.y()+q.y())/2)
                    refs = [pol.referencia() for pol in lote]
                    detalhes = dict(distancia_extremidades_m=distancia,
                        extremidades=[dict(tubulacao=tubo.chave, parte=parte, lado=lado, x=p.x(), y=p.y()),
                                      dict(tubulacao=outro.chave, parte=outra_parte, lado=outro_lado, x=q.x(), y=q.y())],
                        lados_por_poligono={pol.chave: lados[pol.chave] for pol in lote})
                    resultado.ocorrencias.append(Ocorrencia(
                        digest(["CONTINUIDADE", detalhes, [r['chave'] for r in refs]]),
                        "CONTINUIDADE_POTENCIAL", lote[0].modo, _ponto(meio),
                        [tubo.referencia(), outro.referencia()], refs, parte,
                        0. if lado == 'INICIO' else linha.length(),
                        lado_antes_disponivel=False, lado_depois_disponivel=False,
                        observacoes=["Par de extremidades em lados opostos; nenhuma conexão criada.",
                                     "Geometria de saída é o ponto médio das extremidades, não uma conexão.",
                                     "Antes/depois não se aplica ao par; consultar lados_por_poligono e extremidades."],
                        detalhes=detalhes))


def auditar(redes, limites, parametros=None, cancelar=None, progresso=None):
    """Retorna Resultado em memória. progresso(concluidas, total), cancelar()->bool.

    Erros estruturais de configuração levantam ValueError. Feições inválidas
    são relatadas e ignoradas. Cancelamento devolve resultado parcial marcado.
    """
    inicio = perf_counter()
    parametros = parametros or Parametros()
    resultado = Resultado(parametros)
    resultado.ambiente = dict(qgis=Qgis.QGIS_VERSION, crs=parametros.crs)
    try:
        crs = crs_processamento(parametros)
        redes, limites = list(redes), list(limites)
        if not redes or not limites:
            raise ValueError("Selecionar ao menos uma rede e uma camada de limites")
        tubos = ler_camadas(redes, QgsWkbTypes.LineGeometry, crs, resultado, cancelar)
        poligonos = ler_camadas(limites, QgsWkbTypes.PolygonGeometry, crs, resultado, cancelar)
        resultado.contadores.update(tubulacoes_validas=len(tubos), poligonos_validos=len(poligonos))
        indice, mapa = _indice(poligonos)
        por_origem = defaultdict(list)
        for poligono in poligonos:
            por_origem[poligono.origem].append(poligono)
        indices_origem = {origem: _indice(ps) for origem, ps in por_origem.items()}
        fronteiras = {p.chave: QgsGeometry(p.geometria.constGet().boundary()) for p in poligonos}
        partes = {}
        for n, tubo in enumerate(tubos):
            verificar_cancelamento(cancelar)
            partes[tubo.chave] = []
            for parte, vertices in enumerate(_partes(tubo.geometria)):
                linha = QgsGeometry.fromPolylineXY(vertices)
                partes[tubo.chave].append(linha)
                if len(vertices) < 2 or linha.length() <= 0:
                    resultado.problemas.append(dict(tubulacao=tubo.chave, parte=parte, mensagem="Parte degenerada"))
                    continue
                try:
                    candidatos = [mapa[i] for i in sorted(indice.intersects(linha.boundingBox()))]
                    _analisar_parte(tubo, parte, linha, candidatos, fronteiras, indices_origem, resultado, cancelar)
                except Cancelado:
                    raise
                except Exception as erro:
                    resultado.problemas.append(dict(tubulacao=tubo.chave, parte=parte, mensagem=str(erro)))
            if progresso:
                progresso(n+1, len(tubos))
        _continuidades(tubos, partes, poligonos, fronteiras, indice, mapa, resultado, cancelar)
    except Cancelado:
        resultado.cancelado = True
    resultado.contadores['ocorrencias'] = len(resultado.ocorrencias)
    resultado.ambiente['duracao_s'] = perf_counter() - inicio
    return resultado
