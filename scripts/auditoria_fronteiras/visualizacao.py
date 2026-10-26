"""Adaptação dos resultados para camadas temporárias; não altera o núcleo."""
from collections import Counter
from dataclasses import asdict
from datetime import datetime
import json
import math

from qgis.PyQt.QtCore import QVariant, Qt
from qgis.core import (QgsCategorizedSymbolRenderer, QgsFeature, QgsField,
                       QgsGeometry, QgsMarkerSymbol, QgsLineSymbol,
                       QgsRendererCategory, QgsVectorLayer, QgsWkbTypes)
from .modelos import verificar_cancelamento
from .apresentacao import CAMPOS_PRINCIPAIS, preparar_apresentacao


MARCA_RESULTADO = 'auditoria_fronteiras/resultado'
ESTILOS = {
    'TRAVESSIA': ('#d73027', 'circle'),
    'TANGENCIA': ('#fdae61', 'triangle'),
    'EXTREMIDADE': ('#2c7bb6', 'square'),
    'COINCIDENCIA': ('#984ea3', 'diamond'),
    'CONTINUIDADE_POTENCIAL': ('#008837', 'cross2'),
    'AMBIGUA': ('#333333', 'star'),
}


def _normalizar(valor):
    """JSON sem truncamento; mantém números, strings com zeros e nulos distintos."""
    if valor is None or isinstance(valor, (str, bool, int)):
        return valor
    if isinstance(valor, float):
        return valor if math.isfinite(valor) else {'tipo': 'float', 'valor': repr(valor)}
    if isinstance(valor, dict):
        return {str(k): _normalizar(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_normalizar(v) for v in valor]
    if isinstance(valor, (bytes, bytearray)):
        return {'tipo': type(valor).__name__, 'hex': bytes(valor).hex()}
    if hasattr(valor, 'toString'):
        return {'tipo': type(valor).__name__, 'valor': valor.toString(Qt.ISODateWithMs)}
    return {'tipo': type(valor).__name__, 'valor': str(valor)}


def texto_json(valor):
    return json.dumps(_normalizar(valor), ensure_ascii=False, allow_nan=False,
                      separators=(',', ':'))


def resumir(resultado):
    classes = Counter(o.classificacao for o in resultado.ocorrencias)
    # Uma fronteira compartilhada conta uma vez por camada, não por polígono.
    camadas = {f['origem']: dict(camada=f['camada'], origem=f['origem'],
                                modo=f['modo'], total=0, classes=Counter())
               for f in resultado.fontes if f.get('modo')}
    for evento in resultado.ocorrencias:
        for origem in {p['origem'] for p in evento.poligonos}:
            if origem not in camadas:
                ref = next(p for p in evento.poligonos if p['origem'] == origem)
                camadas[origem] = dict(camada=ref['camada'], origem=origem,
                                     modo=evento.modo.value, total=0, classes=Counter())
            camadas[origem]['total'] += 1
            camadas[origem]['classes'][evento.classificacao] += 1
    apresentacao = preparar_apresentacao(resultado)
    areas = {}
    for item in apresentacao:
        for area in {a['chave']: a for a in item['areas']}.values():
            chave = (area['origem'], area['chave'])
            areas.setdefault(chave, dict(area, ocorrencias=set()))['ocorrencias'].add(item['uid'])
    return dict(total=len(resultado.ocorrencias), classes=dict(classes),
                camadas=[dict(c, classes=dict(c['classes'])) for c in camadas.values()],
                areas=[dict(camada=a['camada'], area=a['rotulo'], id_original=a['id_original'],
                            total=len(a['ocorrencias'])) for a in areas.values()],
                ambiguas=sum(a['registro']['AMBIGUO']=='Sim' for a in apresentacao),
                transicoes=sum(a['modo']=='TRANSICAO' for a in apresentacao),
                perimetros=sum(a['modo']=='PERIMETRO' for a in apresentacao),
                duracao_nucleo_s=resultado.ambiente.get('duracao_s', 0.),
                problemas=len(resultado.problemas), cancelado=resultado.cancelado)


def texto_resumo(resultado):
    resumo = resumir(resultado)
    estado = 'CANCELADO — resultado parcial, não carregado no mapa' if resultado.cancelado else 'CONCLUÍDO'
    linhas = [estado, f"Ocorrências: {resumo['total']}",
              f"Tempo do núcleo: {resumo['duracao_nucleo_s']:.3f} s",
              f"QGIS: {resultado.ambiente.get('qgis', '?')} | CRS: {resultado.parametros.crs}",
              'Parâmetros: ' + texto_json(asdict(resultado.parametros)), '', 'Por classificação:']
    linhas += [f'  {classe}: {resumo["classes"].get(classe, 0)}' for classe in ESTILOS]
    linhas += ['', 'Por camada de limite (uma transição compartilhada conta uma vez):']
    for c in resumo['camadas']:
        linhas.append(f"  {c['camada']} | {c['modo']} | total: {c['total']}")
        linhas.append('    ' + ', '.join(f'{k}: {v}' for k, v in sorted(c['classes'].items())))
    linhas += ['', f"Avisos/problemas: {len(resultado.problemas)}"]
    linhas += [f"Ocorrências com ambiguidade: {resumo['ambiguas']}"]
    linhas += [texto_json(p) for p in resultado.problemas]
    linhas += ['', 'Auditoria espacial: não comprova conexão, controle ou sentido hidráulico.']
    return '\n'.join(linhas)


def _camada(tipo, nome, resultado, tecnica=False):
    camada = QgsVectorLayer(tipo, nome, 'memory')
    from .entradas import crs_processamento
    camada.setCrs(crs_processamento(resultado.parametros))
    especificacao_tecnica = [
        ('ocorr_id', QVariant.String), ('classe', QVariant.String),
        ('modo', QVariant.String), ('lim_camada', QVariant.String),
        ('lim_origens', QVariant.String), ('pol_ids', QVariant.String),
        ('pol_chaves', QVariant.String), ('rede_camadas', QVariant.String),
        ('rede_ids', QVariant.String), ('rede_chaves', QVariant.String),
        ('parte', QVariant.Int), ('dist_linha_m', QVariant.Double),
        ('x_m', QVariant.Double), ('y_m', QVariant.Double),
        ('reg_antes', QVariant.String), ('reg_depois', QVariant.String),
        ('antes_disp', QVariant.Bool), ('depois_disp', QVariant.Bool),
        ('ambigua', QVariant.Bool), ('geom_repr', QVariant.String),
        ('evidencia', QVariant.String), ('observacoes', QVariant.String),
        ('refs_rede', QVariant.String), ('refs_lim', QVariant.String),
        ('detalhes', QVariant.String), ('parcial', QVariant.Bool),
        ('ID', QVariant.Int), ('registro', QVariant.String)]
    especificacao = (especificacao_tecnica if tecnica else
        [(n, QVariant.Int if n == 'ID' else QVariant.Double if n in ('X','Y')
          else QVariant.String) for n in CAMPOS_PRINCIPAIS] + [('EVT_UID', QVariant.String)])
    campos = [QgsField(n, t) for n, t in especificacao]
    if not camada.isValid() or not camada.dataProvider().addAttributes(campos):
        raise RuntimeError('Não foi possível criar a camada temporária')
    camada.updateFields()
    camada.setCustomProperty(MARCA_RESULTADO, True)
    camada.setCustomProperty('auditoria_fronteiras/parametros', texto_json(asdict(resultado.parametros)))
    camada.setCustomProperty('auditoria_fronteiras/ambiente', texto_json(resultado.ambiente))
    camada.setCustomProperty('auditoria_fronteiras/fontes', texto_json(resultado.fontes))
    camada.setCustomProperty('auditoria_fronteiras/papel', 'tecnica' if tecnica else 'apresentacao')
    if not tecnica:
        from qgis.core import QgsEditorWidgetSetup
        configuracao = camada.attributeTableConfig()
        colunas = configuracao.columns()
        for coluna in colunas:
            if coluna.name == 'EVT_UID':
                coluna.hidden = True
        configuracao.setColumns(colunas)
        camada.setAttributeTableConfig(configuracao)
        camada.setEditorWidgetSetup(camada.fields().indexFromName('EVT_UID'),
                                    QgsEditorWidgetSetup('Hidden', {}))
    return camada


def _simbolizar(camada, linha=False):
    categorias = []
    for classe, (cor, forma) in ESTILOS.items():
        simbolo = (QgsLineSymbol.createSimple({'line_color': cor, 'line_width': '0.8'})
                   if linha else QgsMarkerSymbol.createSimple({
                       'name': forma, 'color': cor, 'outline_color': '#ffffff',
                       'outline_width': '0.25', 'size': '3.2'}))
        categorias.append(QgsRendererCategory(classe, simbolo, classe))
    camada.setRenderer(QgsCategorizedSymbolRenderer('CLASSIF', categorias))


def _atributos(evento, ponto, representacao, resultado):
    p = ponto.asPoint()
    return [evento.id, evento.classificacao, evento.modo.value,
        ' | '.join(dict.fromkeys(r['camada'] for r in evento.poligonos)),
        texto_json(list(dict.fromkeys(r['origem'] for r in evento.poligonos))),
        texto_json([r['id_original'] for r in evento.poligonos]),
        texto_json([r['chave'] for r in evento.poligonos]),
        texto_json([r['camada'] for r in evento.tubulacoes]),
        texto_json([r['id_original'] for r in evento.tubulacoes]),
        texto_json([r['chave'] for r in evento.tubulacoes]),
        evento.parte, evento.distancia_linha, p.x(), p.y(),
        texto_json(evento.regiao_antes), texto_json(evento.regiao_depois),
        evento.lado_antes_disponivel, evento.lado_depois_disponivel,
        evento.ambigua, representacao, evento.evidencia,
        '\n'.join(evento.observacoes), texto_json(evento.tubulacoes),
        texto_json(evento.poligonos), texto_json(evento.detalhes), resultado.cancelado]


def criar_camadas_temporarias(resultado, cancelar=None, analise=None):
    """Um ponto por ocorrência; coincidências também mantêm seu trecho linear.

    Não registra no projeto nem altera o Resultado. Cancelamento descarta a
    preparação inteira. Resultados cancelados não são publicados como completos.
    """
    if resultado.cancelado:
        raise ValueError('Resultado cancelado é parcial e não será carregado no mapa')
    apresentacao = preparar_apresentacao(resultado, cancelar)
    pontos = _camada('Point', 'EVENTOS_FRONTEIRAS', resultado)
    tecnica = _camada('None', 'DETALHES_TECNICOS', resultado, tecnica=True)
    trechos = _camada('MultiLineString', 'TRECHOS_COINCIDENTES', resultado)
    lotes = {c.id(): [] for c in (pontos, tecnica, trechos)}
    def adicionar(camada, geom, attrs):
        f = QgsFeature(camada.fields())
        if geom is not None:
            f.setGeometry(geom)
        f.setAttributes(attrs)
        lote = lotes[camada.id()]
        lote.append(f)
        if len(lote) >= 500:
            gravar(camada)
    def gravar(camada):
        lote = lotes[camada.id()]
        if lote and not camada.dataProvider().addFeatures(lote)[0]:
            raise RuntimeError('Falha ao preencher a camada temporária')
        lote.clear()
    for item in apresentacao:
        evento = item['evento']
        verificar_cancelamento(cancelar)
        geom = QgsGeometry(evento.geometria)
        tipo = QgsWkbTypes.geometryType(geom.wkbType())
        if geom.isEmpty() or geom.isNull():
            raise ValueError(f'Ocorrência sem geometria: {evento.id}')
        if tipo == QgsWkbTypes.LineGeometry:
            ponto = geom.interpolate(geom.length() / 2.)
            representacao = 'MEIO_DO_TRECHO'
        elif tipo == QgsWkbTypes.PointGeometry and not geom.isMultipart():
            ponto = geom
            representacao = ('MEIO_DAS_EXTREMIDADES' if evento.classificacao == 'CONTINUIDADE_POTENCIAL'
                             else 'PONTO_DO_EVENTO')
        else:
            raise ValueError(f'Tipo geométrico inesperado na ocorrência {evento.id}')
        attrs = list(item['registro'].values()) + [item['uid']]
        adicionar(pontos, ponto, attrs)
        adicionar(tecnica, None, _atributos(evento, ponto, representacao, resultado)
                  + [item['registro']['ID'], texto_json(item['tecnico'])])
        if tipo == QgsWkbTypes.LineGeometry:
            geom.convertToMultiType()
            adicionar(trechos, geom, attrs)
    verificar_cancelamento(cancelar)
    saida = [pontos, tecnica]
    if trechos.featureCount() or lotes[trechos.id()]:
        saida.append(trechos)
    for camada in saida:
        gravar(camada)
        camada.updateExtents()
        camada.setReadOnly(True)
        if camada is not tecnica:
            _simbolizar(camada, camada is trechos)
    if analise is not None:
        from .visualizacao_locais import criar_camadas_locais
        saida.extend(criar_camadas_locais(resultado,analise,cancelar))
    return saida


def carregar_no_projeto(camadas, projeto):
    """Publica somente saídas prontas, em grupo novo por execução."""
    raiz = projeto.layerTreeRoot()
    base = 'AUDITORIA_FRONTEIRAS ' + datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    nome, numero = base, 2
    while raiz.findGroup(nome) is not None:
        nome, numero = f'{base} ({numero})', numero+1
    grupo = raiz.insertGroup(0, nome)
    adicionadas = []
    relacoes = []
    try:
        for camada in camadas:
            if projeto.mapLayer(camada.id()):
                continue
            if not projeto.addMapLayer(camada, False):
                raise RuntimeError('Falha ao registrar resultado no projeto')
            adicionadas.append(camada.id())
            grupo.addLayer(camada)
        tecnicas = [c for c in camadas if c.customProperty('auditoria_fronteiras/papel') == 'tecnica']
        if tecnicas:
            from qgis.core import QgsRelation, QgsRelationContext
            for camada in camadas:
                if camada is tecnicas[0] or camada.customProperty('auditoria_fronteiras/papel')!='apresentacao':
                    continue
                relacao = QgsRelation(QgsRelationContext(projeto))
                relacao.setId('auditoria_' + camada.id())
                if relacao.id() in projeto.relationManager().relations():
                    continue
                relacao.setName(camada.name() + ' — detalhes técnicos')
                relacao.setReferencingLayer(camada.id())
                relacao.setReferencedLayer(tecnicas[0].id())
                relacao.addFieldPair('EVT_UID', 'ocorr_id')
                if not relacao.isValid():
                    raise RuntimeError('Não foi possível relacionar eventos e detalhes técnicos')
                projeto.relationManager().addRelation(relacao)
                relacoes.append(relacao.id())
        locais=[c for c in camadas if c.customProperty('auditoria_fronteiras/papel')=='locais']
        vinculos=[c for c in camadas if c.customProperty('auditoria_fronteiras/papel')=='vinculos']
        eventos=[c for c in camadas if c.customProperty('auditoria_fronteiras/papel')=='apresentacao']
        if locais and vinculos and eventos:
            from qgis.core import QgsRelation,QgsRelationContext
            for alvo,campo in ((locais[0],'LOC_UID'),(eventos[0],'EVT_UID')):
                relacao=QgsRelation(QgsRelationContext(projeto))
                relacao.setId('vinculo_'+vinculos[0].id()+'_'+alvo.id())
                if relacao.id() in projeto.relationManager().relations():
                    continue
                relacao.setName('Local ↔ ocorrências: '+alvo.name())
                relacao.setReferencingLayer(vinculos[0].id())
                relacao.setReferencedLayer(alvo.id())
                relacao.addFieldPair(campo,campo)
                if not relacao.isValid():
                    raise RuntimeError('Relação local/evento inválida')
                projeto.relationManager().addRelation(relacao)
                relacoes.append(relacao.id())
    except Exception:
        # Reverte apenas saídas novas desta chamada, sem tocar nas entradas.
        for relacao_id in relacoes:
            projeto.relationManager().removeRelation(relacao_id)
        for camada_id in adicionadas:
            projeto.removeMapLayer(camada_id)
        projeto.layerTreeRoot().removeChildNode(grupo)
        raise
    if not adicionadas:
        raiz.removeChildNode(grupo)
        return None
    return grupo
