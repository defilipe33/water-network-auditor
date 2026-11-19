"""Condições tipadas e agrupadas; a expressão continua sendo o contrato persistido."""
from datetime import date, datetime
import json
from math import isfinite
from qgis.core import QgsExpression
from .cadastro_gis import familia
from .modelo_gis import expressao


def operadores(tipo):
    f = familia(tipo)
    comum = {'=': 'Igual a', '<>': 'Diferente de'}
    if f == 'texto':
        return {**comum, 'CONTEM': 'Contém', 'NAO_CONTEM': 'Não contém',
                'INICIA': 'Começa com', 'TERMINA': 'Termina com', 'VAZIO': 'Está vazio',
                'NAO_VAZIO': 'Não está vazio', 'LISTA': 'Está em uma lista', 'IS NULL': 'É nulo'}
    if f in ('inteiro', 'real'):
        return {**comum, '>': 'Maior que', '<': 'Menor que', '>=': 'Maior ou igual',
                '<=': 'Menor ou igual', 'ENTRE': 'Entre dois valores', 'IS NULL': 'Está vazio (nulo)'}
    if f in ('date', 'datetime', 'qdate', 'qdatetime'):
        return {'=': 'Igual a', '<': 'Antes de', '>': 'Depois de', 'ENTRE': 'Entre datas', 'IS NULL': 'Está vazio (nulo)'}
    if f == 'booleano':
        return {**comum, 'IS NULL': 'Está vazio (nulo)'}
    return {'IS NULL': 'Está vazio (nulo)'}


def literal(valor, tipo):
    f = familia(tipo)
    s = str(valor)
    try:
        if f == 'inteiro': return str(int(s))
        if f == 'real':
            n = float(s.replace(',', '.'))
            if not isfinite(n): raise ValueError()
            return repr(n)
        if f == 'booleano':
            return {'true': 'TRUE', 'false': 'FALSE', 'sim': 'TRUE', 'não': 'FALSE', '1': 'TRUE', '0': 'FALSE'}[s.strip().casefold()]
        if f in ('date', 'qdate'):
            return 'to_date(' + QgsExpression.quotedString(date.fromisoformat(s).isoformat()) + ')'
        if f in ('datetime', 'qdatetime'):
            return 'to_datetime(' + QgsExpression.quotedString(datetime.fromisoformat(s).isoformat()) + ')'
        if f == 'texto': return QgsExpression.quotedString(s)
    except (ValueError, KeyError) as e:
        raise ValueError('Informe um valor compatível. Datas: AAAA-MM-DD; data e hora: AAAA-MM-DDTHH:MM:SS.') from e
    raise ValueError('Tipo não suportado para esta condição.')


def gerar(arvore, campos):
    """Cada grupo tem um conectivo explícito; nunca depende da precedência implícita."""
    if 'grupo' in arvore:
        if arvore['grupo'] not in ('AND', 'OR') or not arvore.get('itens'):
            raise ValueError('Adicione condições ao grupo e escolha E ou OU.')
        texto = '(' + (' ' + arvore['grupo'] + ' ').join(gerar(n, campos) for n in arvore['itens']) + ')'
    else:
        campo, op = arvore['campo'], arvore['operador']
        if campo not in campos or op not in operadores(campos[campo]):
            raise ValueError('Campo ou operador incompatível com a camada.')
        c = QgsExpression.quotedColumnRef(campo)
        # No QGIS 3.44, OR de igualdades repetidas sobre um nome com espaços
        # pode retornar NULL. A conversão textual explícita preserva texto/nulos
        # e impede essa simplificação do nó, sem converter identificadores em números.
        if familia(campos[campo]) == 'texto' and any(ch.isspace() for ch in campo):
            c = 'to_string(' + c + ')'
        v, v2 = arvore.get('valor', ''), arvore.get('valor2', '')
        if op == 'IS NULL': texto = c + ' IS NULL'
        elif op == 'VAZIO': texto = f'({c} IS NULL OR {c} = \'\')'
        elif op == 'NAO_VAZIO': texto = f'({c} IS NOT NULL AND {c} <> \'\')'
        elif op in ('CONTEM', 'NAO_CONTEM', 'INICIA', 'TERMINA'):
            # LIKE exige escapar seus curingas; apóstrofos são tratados pelo QGIS.
            s = str(v).replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            s = ('%' if op in ('CONTEM', 'NAO_CONTEM', 'TERMINA') else '') + s
            s += '%' if op in ('CONTEM', 'NAO_CONTEM', 'INICIA') else ''
            texto = c + (' NOT LIKE ' if op == 'NAO_CONTEM' else ' LIKE ') + QgsExpression.quotedString(s)
        elif op == 'LISTA':
            # JSON evita ambiguidades quando valores contêm vírgulas/ponto e vírgula.
            try: valores = json.loads(v) if isinstance(v, str) else v
            except (ValueError, TypeError) as e: raise ValueError('Informe uma lista JSON, por exemplo ["PRV", "TCV"].') from e
            if not isinstance(valores, list) or not valores or any(not isinstance(x, str) for x in valores):
                raise ValueError('A lista deve conter um ou mais textos.')
            texto = c + ' IN (' + ', '.join(literal(x, campos[campo]) for x in valores) + ')'
        elif op == 'ENTRE':
            a, b = literal(v, campos[campo]), literal(v2, campos[campo])
            texto = f'({c} >= {a} AND {c} <= {b})'
        else: texto = c + ' ' + op + ' ' + literal(v, campos[campo])
    expressao(texto, campos)
    return texto


def valores_amostrados(fonte, campo, cancelar=lambda: False, limite=250):
    from qgis.core import QgsFeatureRequest, QgsVariantUtils, Qgis
    if campo not in fonte.fields().names(): raise ValueError('Campo ausente.')
    req = QgsFeatureRequest().setFlags(Qgis.FeatureRequestFlag.NoGeometry)
    req.setSubsetOfAttributes([campo], fonte.fields()).setLimit(limite)
    valores = set()
    for f in fonte.getFeatures(req):
        if cancelar(): raise InterruptedError('Consulta cancelada.')
        if not QgsVariantUtils.isNull(f[campo]): valores.add(str(f[campo]))
    return sorted(valores)
