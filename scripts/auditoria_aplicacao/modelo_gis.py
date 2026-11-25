"""Cadastro versionado de fontes GIS, separado das geometrias e do grafo."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from os.path import abspath, normcase
from pathlib import Path
import re
import unicodedata
from uuid import uuid4

from qgis.core import (
    Qgis, QgsExpression, QgsExpressionContext, QgsFeatureRequest, QgsProviderRegistry,
    QgsVariantUtils, QgsVectorLayer, QgsVectorLayerFeatureSource, QgsWkbTypes,
)

from auditoria_fronteiras.entradas import digest


@dataclass(frozen=True)
class Categoria:
    grupo: str
    nome: str
    geometrias: tuple
    campos: tuple


def _categoria(grupo, nome, geometria, campos=''):
    return Categoria(grupo, nome, tuple(geometria.split()), tuple(campos.split()))


CATEGORIAS = {
    'PIPE': _categoria('Redes', 'Tubulações', 'Line', 'gis_id diametro material comprimento rugosidade ano situacao setor_operacional'),
    'JUNCTION': _categoria('Nós', 'Junctions / nós GIS', 'Point', 'elevacao'),
    'RESERVOIR': _categoria('Reservatórios e bombas', 'Reservoirs', 'Point', 'elevacao carga nivel'),
    'TANK': _categoria('Reservatórios e bombas', 'Tanks', 'Point', 'elevacao nivel nivel_minimo nivel_maximo diametro volume'),
    'ENTRADA': _categoria('Reservatórios e bombas', 'Pontos de entrada', 'Point', 'nome'),
    'PUMP': _categoria('Reservatórios e bombas', 'Bombas', 'Point', 'nome tipo instalacao'),
    'BOOSTER': _categoria('Reservatórios e bombas', 'Boosters / instalações', 'Point Polygon', 'nome tipo instalacao'),
    **{
        codigo: _categoria('Válvulas e equipamentos', nome, 'Point', 'nome tipo diametro situacao' if codigo == 'PRV' else 'tipo diametro situacao')
        for codigo, nome in (
            ('PRV', 'PRVs'), ('TCV', 'TCVs'), ('FCV', 'FCVs'), ('PBV', 'PBVs'),
            ('AIR_VALVE', 'Ventosas'), ('HYDRANT', 'Hidrantes'),
            ('REGISTRO', 'Registros de bloqueio'), ('DISPOSITIVO', 'Outros dispositivos'),
        )
    },
    **{
        codigo: _categoria('Zonas e setores', nome, 'Polygon', 'nome tipo equipamento')
        for codigo, nome in (
            ('SETOR', 'Setores de abastecimento'), ('ZONA_VRP', 'Zonas de VRP'),
            ('ZONA_BOOSTER', 'Zonas de booster'), ('ZONA', 'Outras zonas de distribuição'),
        )
    },
    'INTERVENCAO': _categoria('Intervenções', 'Referências de intervenção', 'Point Line Polygon Table', 'nome tipo situacao'),
    'RUA': _categoria('Camadas auxiliares', 'Arruamento', 'Line', 'nome'),
    'LIMITE': _categoria('Camadas auxiliares', 'Limites administrativos', 'Polygon', 'nome'),
    'ORTOFOTO': _categoria('Camadas auxiliares', 'Ortofotos', 'Raster'),
    'AUXILIAR': _categoria('Camadas auxiliares', 'Outras camadas', 'Point Line Polygon Table Raster', 'nome'),
}

ESTRATEGIAS = {
    'CADASTRADAS': 'Usar Junctions cadastradas',
    'INFERIR': 'Inferir nós a partir das tubulações',
    'COMBINAR': 'Combinar Junctions cadastradas e inferidas',
}
PAPEIS = {
    'EXISTENTE': 'Cadastro existente', 'PROJETADO': 'Cadastro projetado',
    'PROPOSTO': 'Proposta', 'REFERENCIA': 'Referência',
}
CLASSIFICACOES = {
    '': 'Sem classificação', 'DISTRIBUICAO': 'Distribuição', 'ADUCAO': 'Adução',
    'COMPLEMENTAR': 'Complementar', 'OUTRA': 'Outra',
}
VINCULOS_WG = ('Label', 'GIS-ID', 'DomainElementID')
ROTULOS = {
    'id': 'ID da feição', 'label': 'Nome exibido', 'wg': 'Campo de correspondência WaterGEMS',
    'gis_id': 'GIS-ID', 'diametro': 'Diâmetro', 'comprimento': 'Comprimento',
    'setor_operacional': 'Setor operacional declarado',
    'rugosidade': 'Rugosidade', 'elevacao': 'Elevação', 'ano': 'Ano de instalação',
    'situacao': 'Situação cadastral', 'nivel': 'Nível', 'nivel_minimo': 'Nível mínimo',
    'nivel_maximo': 'Nível máximo', 'instalacao': 'Instalação', 'equipamento': 'Equipamento associado',
}


def geometria(camada):
    if camada.type() == Qgis.LayerType.Raster:
        return 'Raster'
    if not isinstance(camada, QgsVectorLayer):
        return ''
    return {
        Qgis.GeometryType.Point: 'Point', Qgis.GeometryType.Line: 'Line',
        Qgis.GeometryType.Polygon: 'Polygon', Qgis.GeometryType.Null: 'Table',
    }.get(camada.geometryType(), '')


def origem_camada(camada, registro=None):
    provedor, uri = camada.providerType(), camada.source()
    if registro is None:
        registro = QgsProviderRegistry.instance().decodeUri(provedor, uri)
    caminho = registro.get('path')
    referencia = {**registro, 'path': normcase(abspath(caminho))} if caminho and Path(caminho).is_absolute() else uri
    filtro = camada.subsetString() if isinstance(camada, QgsVectorLayer) else ''
    return digest([provedor, referencia, filtro, camada.id() if provedor == 'memory' else ''])


def descrever(camada):
    tipo = geometria(camada)
    if not tipo or not camada.isValid():
        raise ValueError('A camada não está disponível ou o tipo não é suportado.')
    provedor, uri = camada.providerType(), camada.source()
    if re.search(r'(?i)(?:\b(?:password|passwd|pwd|token|api[_-]?key|access[_-]?key|secret)\s*=|://[^/\s@]+:[^/\s@]+@)', uri):
        raise ValueError('Use uma conexão configurada na autenticação do QGIS para cadastrar esta fonte.')
    registro = QgsProviderRegistry.instance().decodeUri(provedor, uri)
    arquivo = registro.get('path')
    marca = {}
    if arquivo:
        caminho = Path(arquivo)
        arquivos = [caminho]
        if caminho.suffix.lower() == '.shp':
            arquivos.extend(caminho.with_suffix(ext) for ext in ('.dbf', '.shx', '.prj', '.cpg', '.qpj'))
        elif caminho.suffix.lower() in ('.gpkg', '.sqlite'):
            arquivos.append(caminho.with_name(caminho.name + '-wal'))
        for item in arquivos:
            try:
                stat = item.stat()
            except OSError:
                continue
            marca[item.name[len(caminho.stem):].lower()] = [
                stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns,
            ]
    vetor = isinstance(camada, QgsVectorLayer)
    campos = {f.name(): f.typeName() for f in camada.fields()} if vetor else {}
    crs = camada.crs()
    perfil = dict(geometria=tipo, wkb=QgsWkbTypes.displayString(camada.wkbType()) if vetor else tipo,
                  crs=crs.authid(), crs_wkt=crs.toWkt(), campos=campos,
                  filtro_provedor=camada.subsetString() if vetor else '',
                  conjunto=str(registro.get('layerName') or registro.get('layerId') or ''))
    identidade = origem_camada(camada, registro)
    return dict(nome=camada.name(), camada_id=camada.id(), uri=uri, provedor=provedor,
                origem=identidade, assinatura=digest([identidade, perfil, marca]), marca_arquivo=marca, **perfil)


def identificar(fonte, camadas):
    """Resolve a fonte pelo provedor e URI; o ID do projeto desambigua visualizações."""
    camadas = list(camadas)
    if uri:=fonte.get('uri_portatil'):
        provedor=fonte['provedor']
        decodificar=QgsProviderRegistry.instance().decodeUri
        ref=decodificar(provedor,uri)
        return next((c for c in camadas if c.isValid() and c.providerType()==provedor
                     and decodificar(provedor,c.source())==ref
                     and c.subsetString()==fonte.get('filtro_provedor','')),None)
    # O ID só é atalho quando a identidade da fonte também confere.
    for c in camadas:
        if c.id() == fonte['camada_id'] and c.isValid() and c.providerType() == fonte['provedor'] and origem_camada(c) == fonte['origem']:
            return c
    if fonte['provedor'] == 'memory':
        return None
    candidatas = [
        c for c in camadas if c.isValid() and c.providerType() == fonte['provedor']
        and origem_camada(c) == fonte['origem']
    ]
    for camada in candidatas:
        if camada.id() == fonte['camada_id']:
            return camada
    if fonte['provedor'] == 'memory':
        return None
    return candidatas[0] if len(candidatas) == 1 else None


def assinatura_confere(fonte,atual):
    if not fonte.get('uri_portatil'):return fonte['assinatura']==atual['assinatura']
    if any(fonte.get(k)!=atual.get(k) for k in ('geometria','wkb','crs_wkt','campos','filtro_provedor','conjunto')):
        return False
    return fonte.get('marca_portatil')=={k:m[2:] for k,m in atual['marca_arquivo'].items()}


def _normalizar(texto):
    ascii_ = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode()
    return re.sub('[^a-z0-9]+', ' ', ascii_.casefold()).strip()


def sugerir(camada):
    """Sugestões por geometria e metadados; o cadastro exige escolha de categoria."""
    meta = camada.metadata()
    palavras_meta = [palavra for lista in meta.keywords().values() for palavra in lista]
    nome = _normalizar(' '.join([camada.name(), meta.title(), *palavras_meta]))
    pistas = [
        ('ZONA_VRP', 'zona vrp|zona de vrp|zona pressao'), ('ZONA_BOOSTER', 'zona booster|zona de booster'),
        ('PIPE', 'tubo|tubul|distribuicao|aducao|rede'), ('JUNCTION', 'junction|nos|no gis'),
        ('RESERVOIR', 'reservoir'), ('TANK', 'tank|tanque'), ('PUMP', 'bomba|pump'),
        ('BOOSTER', 'booster'), ('PRV', 'prv|vrp'), ('TCV', 'tcv'), ('FCV', 'fcv'),
        ('PBV', 'pbv'), ('AIR_VALVE', 'ventosa'), ('HYDRANT', 'hidrante'),
        ('REGISTRO', 'registro'), ('SETOR', 'setor'), ('RUA', 'rua|arruamento|logradouro'),
        ('LIMITE', 'limite'), ('ORTOFOTO', 'ortofoto'),
    ]
    tipo = geometria(camada)
    categorias = [k for k, palavras in pistas if tipo in CATEGORIAS[k].geometrias and re.search(palavras, nome)]
    campos = {_normalizar(f.name()): f.name() for f in camada.fields()} if isinstance(camada, QgsVectorLayer) else {}
    aliases = dict(id=('id gis', 'gis id', 'objectid', 'id pde', 'id'), label=('label', 'rotulo'),
                   gis_id=('id gis', 'gis id'), diametro=('diametro', 'diameter', 'dn'),
                   material=('material',), comprimento=('comprimento', 'length'),
                   elevacao=('elevacao', 'cota'), nome=('nome', 'name'), tipo=('tipo', 'type'))
    mapeamento = {k: next((campos[a] for a in opcoes if a in campos), '') for k, opcoes in aliases.items()}
    # Variantes de nomes são genéricas e nenhuma associação com WaterGEMS é aplicada.
    return categorias, {k: v for k, v in mapeamento.items() if v}


def expressao(texto, campos):
    if not texto.strip():
        return None
    expr = QgsExpression(texto)
    if expr.hasParserError():
        raise ValueError('Filtro inválido. Confira a expressão de atributos.')
    # Mantém o filtro reprodutível fora do mapa e evita referências a outras fontes.
    permitidas = {'lower', 'upper', 'trim', 'length', 'abs', 'round', 'coalesce', 'to_int', 'to_real', 'to_string', 'to_date', 'to_datetime'}
    if expr.needsGeometry() or expr.referencedVariables() or not expr.referencedFunctions() <= permitidas:
        raise ValueError('Use comparações de atributos e funções locais no filtro.')
    faltam = expr.referencedColumns() - set(campos)
    if faltam:
        raise ValueError('Campos do filtro ausentes: ' + ', '.join(sorted(faltam)))
    return expr


def configurar(meta, categoria, papel, classificacao, campos, filtro='', alvo_wg='', anterior=None):
    tipo = CATEGORIAS[categoria]
    if meta['geometria'] not in tipo.geometrias:
        raise ValueError('Geometria incompatível com ' + tipo.nome + '.')
    if papel not in PAPEIS or classificacao not in CLASSIFICACOES:
        raise ValueError('Selecione um papel e uma classificação válidos.')
    if meta['geometria'] != 'Table' and not meta['crs_wkt']:
        raise ValueError('A camada precisa de um CRS válido. Confira as propriedades no QGIS.')
    mapeados = {k: v for k, v in campos.items() if v}
    if set(mapeados) - {'id', 'label', 'wg', *tipo.campos}:
        raise ValueError('Há atributos incompatíveis com a categoria.')
    if set(mapeados.values()) - meta['campos'].keys():
        raise ValueError('Um ou mais campos mapeados estão ausentes.')
    if bool(alvo_wg) != bool(mapeados.get('wg')) or alvo_wg and alvo_wg not in VINCULOS_WG:
        raise ValueError('Informe o campo GIS e o atributo WaterGEMS da associação, ou deixe ambos vazios.')
    expressao(filtro, meta['campos'])
    extensoes = {k: deepcopy(anterior[k]) for k in ('associacoes_rede',) if anterior and k in anterior}
    return dict(**meta, **extensoes, uid=anterior['uid'] if anterior else uuid4().hex,
                origem_estavel=anterior['origem_estavel'] if anterior else meta['origem'],
                categoria=categoria, papel=papel, classificacao=classificacao, campos_mapeados=mapeados,
                filtro=filtro.strip(), alvo_wg=alvo_wg)


def relocalizar(fonte, meta):
    requeridos = ('provedor', 'wkb', 'crs_wkt', 'campos', 'filtro_provedor', 'conjunto')
    if any(fonte[k] != meta[k] for k in requeridos):
        raise ValueError('A fonte candidata diverge em provedor, geometria, CRS, campos ou filtro do provedor.')
    if fonte['origem'] == meta['origem']:
        return 'MESMA_REFERENCIA'
    if (fonte['marca_arquivo'] and all(m[1] for m in fonte['marca_arquivo'].values())
            and fonte['marca_arquivo'] == meta['marca_arquivo']):
        return 'MESMO_ARQUIVO'
    return 'COMPATIVEL_IDENTIDADE_PENDENTE'


def estado_fonte(fonte, camada):
    if camada is None:
        return 'Localizar / carregar no QGIS'
    try:
        atual = descrever(camada)
        if not assinatura_confere(fonte,atual):
            return 'Fonte alterada — conferir'
        if fonte.get('relocalizacao') == 'COMPATIVEL_IDENTIDADE_PENDENTE':
            return 'Compatível — identidade por conferir'
    except ValueError:
        return 'Fonte incompatível'
    return 'Disponível'


def chave_feicao(fonte, valor):
    """Chave candidata; só é inequívoca após verificar a unicidade cadastral."""
    campo = fonte['campos_mapeados'].get('id')
    if not campo or QgsVariantUtils.isNull(valor) or isinstance(valor, str) and not valor.strip():
        return None
    return fonte['origem_estavel'], campo, type(valor).__name__, str(valor)


def preparar_conferencia(fontes, camadas):
    """Captura metadados e snapshots de leitura no thread da interface."""
    grupos = {}
    resultados = {}
    for fonte in fontes:
        camada = identificar(fonte, camadas)
        estado = estado_fonte(fonte, camada)
        r = dict(estado=estado, total=None, ausentes=0, repetidos=0, exemplos=[])
        resultados[fonte['uid']] = r
        if estado == 'Disponível' and isinstance(camada, QgsVectorLayer):
            chave = camada.id() if camada.isModified() else fonte['assinatura']
            if chave not in grupos:
                grupos[chave] = camada.name(), QgsVectorLayerFeatureSource(camada), []
            grupos[chave][2].append(deepcopy(fonte))
    return list(grupos.values()), resultados


def conferir(preparacao, ponto=lambda: False, etapa=lambda _: None):
    """Uma leitura por camada, usando a mesma feição para aferir sobreposições."""
    grupos, resultados = preparacao
    pares = {}
    for nome, camada, grupo in grupos:
        etapa('Conferindo atributos de ' + nome)
        contexto = QgsExpressionContext()
        filtros = [expressao(f['filtro'], f['campos']) for f in grupo]
        ids = [f['campos_mapeados'].get('id') for f in grupo]
        vistos = [set() for f in grupo]
        contadores = [resultados[f['uid']] for f in grupo]
        for r in contadores:
            r['total'] = 0
        campos = {c for c in ids if c}
        for filtro in filtros:
            if filtro is not None:
                campos.update(filtro.referencedColumns())
        req = QgsFeatureRequest().setFlags(Qgis.FeatureRequestFlag.NoGeometry)
        req.setSubsetOfAttributes(sorted(campos), camada.fields())
        for i, feicao in enumerate(camada.getFeatures(req)):
            if i % 256 == 0 and ponto():
                raise InterruptedError('Conferência cancelada.')
            contexto.setFeature(feicao)
            ativos = []
            for pos, filtro in enumerate(filtros):
                if contadores[pos].get('erro'):
                    continue
                if filtro is not None:
                    valor = filtro.evaluate(contexto)
                    if filtro.hasEvalError():
                        contadores[pos].update(erro='Filtro inválido para os valores da camada',
                                               total=None, ausentes=0, repetidos=0, exemplos=[])
                        continue
                    if QgsVariantUtils.isNull(valor) or not valor:
                        continue
                ativos.append(pos)
                r = contadores[pos]
                r['total'] += 1
                if ids[pos]:
                    chave = chave_feicao(grupo[pos], feicao[ids[pos]])
                    if chave is None:
                        r['ausentes'] += 1
                    else:
                        if chave in vistos[pos]:
                            r['repetidos'] += 1
                            if len(r['exemplos']) < 5 and chave[-1] not in r['exemplos']:
                                r['exemplos'].append(chave[-1])
                        vistos[pos].add(chave)
            for indice, a in enumerate(ativos):
                for b in ativos[indice + 1:]:
                    par = (grupo[a]['uid'], grupo[b]['uid'])
                    pares[par] = pares.get(par, 0) + 1
        if ponto():
            raise InterruptedError('Conferência cancelada.')
    return resultados, {par: n for par, n in pares.items()
                        if not any(resultados[uid].get('erro') for uid in par)}


def revisoes(projeto):
    return (projeto or {}).get('modelo_gis', {}).get('revisoes', [])


def salvar_modelo(projetos, projeto_uid, anterior, fontes, estrategia):
    if estrategia not in ESTRATEGIAS:
        raise ValueError('Estratégia de Junctions desconhecida.')
    da_vez = projetos.ler()
    projeto = next((p for p in da_vez['projetos'] if p['uuid'] == projeto_uid), None)
    if projeto is None or da_vez['ativo'] != projeto_uid:
        raise ValueError('O projeto ativo mudou. Reabra o Modelo GIS.')
    modelo = projeto.setdefault('modelo_gis', dict(schema=1, uuid=uuid4().hex, revisoes=[]))
    if modelo['schema'] != 1:
        raise ValueError('Versão do cadastro incompatível.')
    historico = modelo['revisoes']
    ultima = historico[-1] if historico else {}
    if ultima.get('uuid') != anterior:
        raise ValueError('O cadastro mudou desde a abertura. Consulte a revisão mais recente antes de editar.')
    if ultima.get('fontes') == fontes and ultima.get('estrategia') == estrategia:
        return ultima
    uids = {f['uid'] for f in fontes}
    if len(fontes) != len(uids):
        raise ValueError('Há identidades de configuração repetidas.')
    antigas = {f['uid']: f for f in ultima.get('fontes', [])}
    atuais = {f['uid']: f for f in fontes}
    alteradas = sorted(k for k in antigas.keys() | atuais.keys() if antigas.get(k) != atuais.get(k))
    afetadas = [dict(r) for r in projeto.get('bases', []) if r['tipo'] in ('AUDITORIA_GIS', 'INTEGRADA')] if ultima else []
    nova = dict(uuid=uuid4().hex, anterior=anterior, versao=len(historico) + 1,
                data_utc=datetime.now(timezone.utc).isoformat(), fontes=deepcopy(fontes),
                estrategia=estrategia, fontes_alteradas=alteradas, referencias_para_conferir=afetadas)
    historico.append(nova)
    projetos.gravar(da_vez)
    return nova
