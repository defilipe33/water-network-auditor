"""Sugestões e operações de edição do cadastro; os registros da versão 1.13.0 são preservados."""
from math import isfinite
from qgis.core import Qgis, QgsExpression, QgsExpressionContext, QgsFeatureRequest, QgsVariantUtils

from .modelo_gis import CATEGORIAS, _normalizar, configurar, descrever, expressao

SINONIMOS = {
    'id': ('gis id', 'id gis', 'objectid', 'id pde', 'id', 'identificador', 'codigo'),
    'gis_id': ('gis id', 'id gis'),
    'label': ('label', 'rotulo'),
    'diametro': ('diametro', 'diameter', 'dn'),
    'comprimento': ('comprimento', 'length', 'extensao'),
    'rugosidade': ('rugosidade', 'roughness', 'hazen williams'),
    'ano': ('ano instalacao', 'ano de instalacao', 'ano'),
    'elevacao': ('elevacao', 'elevation', 'cota'),
    'material': ('material',),
    'nome': ('nome', 'name'),
    'tipo': ('tipo', 'type'),
    'situacao': ('situacao', 'situacao cadastral'),
}
NUMERICOS = {'diametro', 'comprimento', 'rugosidade', 'elevacao', 'carga', 'nivel',
             'nivel_minimo', 'nivel_maximo', 'volume', 'ano'}


def familia(tipo):
    tipo = _normalizar(tipo)
    if tipo.startswith(('int', 'uint', 'bigint', 'smallint', 'integer', 'long', 'qlong', 'qulong', 'short', 'serial', 'mediumint')):
        return 'inteiro'
    if tipo.startswith(('float', 'double', 'real', 'numeric', 'decimal', 'number')):
        return 'real'
    if tipo.startswith(('text', 'string', 'qstring', 'varchar', 'nvarchar', 'char')):
        return 'texto'
    if tipo in ('bool', 'boolean'):
        return 'booleano'
    return tipo


def sugerir_campos(campos, categoria):
    mapa, ambiguos = {}, {}
    for papel in ('id', 'label', *CATEGORIAS[categoria].campos):
        aceitos = {'inteiro', 'real'} if papel in NUMERICOS else {'inteiro', 'texto'}
        aliases = SINONIMOS.get(papel, (papel.replace('_', ' '),))
        candidatos = [nome for nome, tipo in campos.items()
                      if _normalizar(nome) in aliases and familia(tipo) in aceitos]
        if len(candidatos) == 1:
            mapa[papel] = candidatos[0]
        elif candidatos:
            ambiguos[papel] = candidatos
    return mapa, ambiguos


def incluir_fontes(fontes, categoria, camadas):
    existentes = {f['origem'] for f in fontes if f['categoria'] == categoria}
    novas, avisos, detalhes = [], [], {}
    for camada in camadas:
        try:
            meta = descrever(camada)
            if meta['origem'] in existentes:
                avisos.append(f'{camada.name()} — já cadastrada nesta categoria.')
                continue
            mapa, ambiguos = sugerir_campos(meta['campos'], categoria)
            nova = configurar(meta, categoria, 'EXISTENTE', '', mapa)
        except ValueError as e:
            avisos.append(f'{camada.name()} — {e}')
            continue
        existentes.add(meta['origem'])
        novas.append(nova)
        detalhes[nova['uid']] = ambiguos
    return novas, avisos, detalhes


def copiar_mapeamento(origem, destino, meta):
    if origem['categoria'] != destino['categoria']:
        raise ValueError('Escolha fontes da mesma categoria.')
    mapa = dict(destino['campos_mapeados'])
    alvo = destino['alvo_wg']
    pendencias = []
    for papel, nome in origem['campos_mapeados'].items():
        tipo = meta['campos'].get(nome)
        if tipo is None or familia(origem['campos'][nome]) != familia(tipo):
            pendencias.append((papel, nome, 'ausente' if tipo is None else 'tipo incompatível'))
            continue
        mapa[papel] = nome
        if papel == 'wg':
            alvo = origem['alvo_wg']
    nova = configurar(meta, destino['categoria'], destino['papel'], destino['classificacao'],
                      mapa, destino['filtro'], alvo, destino)
    if 'relocalizacao' in destino:
        nova['relocalizacao'] = destino['relocalizacao']
    return nova, pendencias


OPERADORES = {'=': 'Igual a', '<>': 'Diferente de', '>': 'Maior que', '<': 'Menor que',
              'IS NULL': 'Está vazio (nulo)', 'IS NOT NULL': 'Está preenchido (não nulo)'}


def filtro_simples(campo, tipo, operador, valor):
    if not campo or operador not in OPERADORES:
        raise ValueError('Escolha um campo e um operador.')
    coluna = QgsExpression.quotedColumnRef(campo)
    if operador.startswith('IS '):
        return f'{coluna} {operador}'
    tipo = familia(tipo)
    try:
        if tipo == 'inteiro':
            literal = str(int(valor))
        elif tipo == 'real':
            numero = float(valor.replace(',', '.'))
            if not isfinite(numero):
                raise ValueError()
            literal = repr(numero)
        elif tipo == 'booleano':
            literal = {'true': 'TRUE', 'false': 'FALSE', '1': 'TRUE', '0': 'FALSE',
                       'sim': 'TRUE', 'não': 'FALSE'}[valor.casefold().strip()]
        elif tipo == 'texto':
            literal = QgsExpression.quotedString(valor)
        else:
            raise ValueError('Para este tipo de campo, use a expressão avançada.')
    except (ValueError, KeyError) as e:
        if tipo in ('inteiro', 'real', 'booleano'):
            raise ValueError('Informe um valor compatível com o tipo do campo.') from e
        raise
    return f'{coluna} {operador} {literal}'


def amostra(fonte, campos, texto, cancelar=lambda: False, limite=250, tamanho=5):
    expr = expressao(texto, fonte.fields().names())
    ref = set(campos) | (expr.referencedColumns() if expr is not None else set())
    req = QgsFeatureRequest().setFlags(Qgis.FeatureRequestFlag.NoGeometry).setLimit(limite + 1)
    req.setSubsetOfAttributes(sorted(ref), fonte.fields())
    ctx = QgsExpressionContext()
    linhas, encontrados, completa = [], 0, True
    for i, feicao in enumerate(fonte.getFeatures(req)):
        if cancelar():
            raise InterruptedError('Prévia cancelada.')
        if i == limite:
            completa = False
            break
        if expr is not None:
            ctx.setFeature(feicao)
            valor = expr.evaluate(ctx)
            if expr.hasEvalError():
                raise ValueError('Filtro inválido para os valores da camada. ' + expr.evalErrorString())
            if QgsVariantUtils.isNull(valor) or not valor:
                continue
        encontrados += 1
        if len(linhas) < tamanho:
            linhas.append([None if QgsVariantUtils.isNull(feicao[c]) else str(feicao[c]) for c in campos])
    return linhas, encontrados, completa
