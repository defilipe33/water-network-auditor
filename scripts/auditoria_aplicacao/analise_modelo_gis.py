"""Adaptador de leitura: Modelo GIS → motor geométrico existente.

As únicas camadas QObject consultadas são resolvidas no thread principal.
O worker recebe snapshots e um contexto de transformação copiado.
"""
from copy import deepcopy
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import os
import sqlite3
from uuid import uuid4

from qgis.core import (Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsCoordinateTransformContext, QgsFeatureRequest, QgsGeometry,
                       QgsVectorLayerFeatureSource)
from auditoria_fronteiras import CamadaEntrada, Modo, Parametros, auditar
from auditoria_fronteiras.entradas import crs_processamento
from auditoria_fronteiras.modelos import verificar_cancelamento
from .modelo_gis import CATEGORIAS, descrever, identificar, expressao

AREAS = ('SETOR', 'ZONA_VRP', 'ZONA_BOOSTER', 'ZONA', 'LIMITE')
OBJETIVOS = {
    'verificar': ('Verificar rede GIS', Modo.PERIMETRO,
                  'Geometrias e ocorrências nas fronteiras cadastradas; não constrói conectividade.'),
    'fronteiras': ('Zonas e fronteiras', Modo.TRANSICAO,
                   'Transições geométricas entre regiões, preservando sobreposições e ambiguidades.'),
    'interferencias': ('Interferências espaciais', Modo.PERIMETRO,
                      'Travessias, tangências e coincidências com fronteiras. Não comprova interligação.'),
}


class FonteSnapshot:
    def __init__(self, fonte, camada, destino, contexto):
        self.fonte = deepcopy(fonte)
        self.snapshot = QgsVectorLayerFeatureSource(camada)
        self.origem_crs = QgsCoordinateReferenceSystem(camada.crs())
        self.destino = QgsCoordinateReferenceSystem(destino)
        self.contexto = QgsCoordinateTransformContext(contexto)
        self.wkb = camada.wkbType()
        self.erros = []

    def isValid(self): return True
    def name(self): return self.fonte['nome']
    def source(self): return self.fonte['uri']
    def providerType(self): return self.fonte['provedor']
    def crs(self): return self.destino
    def fields(self): return self.snapshot.fields()
    def wkbType(self): return self.wkb

    def getFeatures(self):
        request = QgsFeatureRequest()
        if self.fonte['filtro']: request.setFilterExpression(self.fonte['filtro'])
        trans = (QgsCoordinateTransform(self.origem_crs, self.destino, self.contexto)
                 if self.origem_crs != self.destino else None)
        for f in self.snapshot.getFeatures(request):
            if trans and f.hasGeometry():
                geom = QgsGeometry(f.geometry())
                try:
                    if geom.transform(trans) != Qgis.GeometryOperationResult.Success:
                        raise ValueError('Transformação não concluída')
                    f.setGeometry(geom)
                except Exception as e:
                    self.erros.append(dict(fid_diagnostico=f.id(), motivo=str(e)))
                    f.setGeometry(QgsGeometry())
            yield f


@dataclass
class PreparacaoGIS:
    redes: list
    limites: list
    parametros: Parametros
    proveniencia: dict
    avisos: list


def preparar(fontes, camadas, parametros, contexto, objetivo='verificar', areas=None,
             projeto_uid=None, revisao_uid=None):
    destino = crs_processamento(parametros)
    if objetivo not in OBJETIVOS: raise ValueError('Escolha uma análise GIS disponível.')
    areas = set(AREAS if areas is None else areas)
    fontes = deepcopy(fontes)
    camadas = list(camadas)
    redes, limites, metadados, avisos = [], [], [], []
    for f in fontes:
        if f['categoria'] != 'PIPE' and f['categoria'] not in areas: continue
        if f['categoria'] not in ('PIPE', *AREAS): continue
        c = identificar(f, camadas)
        if c is None: raise ValueError('Fonte indisponível: ' + f['nome'] + '. Localize-a no Modelo GIS.')
        atual = descrever(c)
        if atual['assinatura'] != f['assinatura']:
            raise ValueError('Fonte alterada: ' + f['nome'] + '. Confira e atualize sua configuração no Modelo GIS.')
        if atual['geometria'] not in CATEGORIAS[f['categoria']].geometrias:
            raise ValueError('Geometria incompatível: ' + f['nome'])
        mapa = f['campos_mapeados']
        if any(nome not in atual['campos'] for nome in mapa.values()):
            raise ValueError('Mapeamento ausente na fonte ' + f['nome'])
        expressao(f['filtro'], atual['campos'])
        if not mapa.get('id'):
            avisos.append(f['nome'] + ': sem ID mapeado; o motor preserva ID nulo e produz chave técnica.')
        s = FonteSnapshot(f, c, destino, contexto)
        config = CamadaEntrada(s, mapa.get('id'), mapa.get('label') or mapa.get('nome'),
                               OBJETIVOS[objetivo][1], f['uid'])
        (redes if f['categoria'] == 'PIPE' else limites).append(config)
        metadados.append(dict(uid=f['uid'], categoria=f['categoria'], origem=f['origem_estavel'],
                              assinatura=f['assinatura'], filtro=f['filtro'], campos=deepcopy(mapa),
                              classificacao=f['classificacao'], papel=f['papel'],
                              crs_original=atual['crs_wkt'], crs_processamento=destino.toWkt()))
    if not redes: raise ValueError('Cadastre ao menos uma fonte de Tubulações no Modelo GIS.')
    if not limites:
        raise ValueError('Esta análise geométrica precisa de áreas de referência. Cadastre setores, zonas ou limites. '
                         'Conectividade sem polígonos pertence à próxima etapa de topologia GIS.')
    referencias = [dict(uid=f['uid'], nome=f['nome'], categoria=f['categoria']) for f in fontes
                   if f['categoria'] not in ('PIPE', *AREAS)]
    return PreparacaoGIS(redes, limites, parametros,
        dict(contrato='modelo-gis-auditoria-1', projeto_uid=projeto_uid, revisao_uid=revisao_uid,
             objetivo=objetivo, fontes=metadados, referencias=referencias,
             limite='Equipamentos são contexto; não são associados por proximidade neste motor.'), avisos)


def executar(preparacao, nome, projeto, cancelar=lambda: False, progresso=lambda *_: None):
    from auditoria_fronteiras.investigacao import analisar_investigacao, OpcoesLocais
    from auditoria_fronteiras.inspecao import construir_dossie
    from auditoria_fronteiras.ciclo import inicializar, configuracao_proposta
    verificar_cancelamento(cancelar)
    r = auditar(preparacao.redes, preparacao.limites, preparacao.parametros, cancelar,
                lambda n, total: progresso(0, f'Analisando tubulações: {n}/{total}'))
    if r.cancelado: verificar_cancelamento(lambda: True)
    verificar_cancelamento(cancelar)
    por_origem = {c.chave_origem: c.camada for c in preparacao.redes + preparacao.limites}
    for f in r.fontes:
        s = por_origem[f['origem']]
        f.update(crs_origem=s.origem_crs.authid() or s.origem_crs.toWkt(),
                 crs_processamento=s.destino.authid() or s.destino.toWkt(), filtro_modelo_gis=s.fonte['filtro'])
    progresso(0, 'Organizando locais de investigação')
    opcoes = OpcoesLocais(True, preparacao.parametros.distancia_agrupamento,
                         preparacao.parametros.distancia_agrupamento)
    a = analisar_investigacao(r, opcoes, cancelar)
    campos = {c.chave_origem: {k: c.camada.fonte['campos_mapeados'].get(k)
                              for k in ('diametro', 'material')} for c in preparacao.redes}
    d = construir_dossie(r, a, campos)
    inicializar(d, nome, projeto)
    d['configuracao'] = configuracao_proposta(preparacao.redes, preparacao.limites,
        preparacao.parametros, opcoes, campos, cancelar=cancelar)
    for f in d['configuracao']['fontes']:
        s = por_origem[f['origem']]
        f.update(crs_origem=s.origem_crs.authid() or s.origem_crs.toWkt(),
                 filtro_modelo_gis=s.fonte['filtro'])
    d['configuracao']['modelo_gis'] = deepcopy(preparacao.proveniencia)
    d['configuracao']['modelo_gis']['avisos'] = list(preparacao.avisos)
    d['configuracao']['modelo_gis']['erros_transformacao'] = [
        dict(fonte=c.chave_origem, **e) for c in preparacao.redes + preparacao.limites for e in c.camada.erros]
    verificar_cancelamento(cancelar)
    return d


def reservar(pasta, crs):
    """Inicialização Qt/GPKG no thread principal; nenhuma fonte original é escrita."""
    from auditoria_fronteiras.persistencia import _iniciar
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    uid = uuid4().hex
    temporario, destino = pasta / ('.gis_' + uid + '.gpkg'), pasta / ('GIS_' + uid[:12] + '.gpkg')
    _iniciar(temporario, crs)
    return temporario, destino


def persistir(temporario, dossie, cancelar=lambda: False):
    from auditoria_fronteiras.persistencia import salvar_execucao
    verificar_cancelamento(cancelar)
    salvar_execucao(temporario, dossie)
    verificar_cancelamento(cancelar)
    with closing(sqlite3.connect(temporario)) as c:
        if c.execute('PRAGMA quick_check').fetchone()[0] != 'ok': raise ValueError('Integridade do resultado não confirmada.')
        if not c.execute('SELECT 1 FROM EXECUCOES WHERE exe_uid=?', (dossie['execucao_uid'],)).fetchone():
            raise ValueError('Execução não encontrada após gravação.')


def publicar(temporario, destino):
    # No Windows, rename falha se o destino existe. Em POSIX, link é exclusivo.
    if os.name == 'nt': Path(temporario).rename(destino)
    else:
        os.link(temporario, destino)
        Path(temporario).unlink()


def conferir_contexto(preparacao, fontes, camadas, projeto_uid, revisao_uid):
    p = preparacao.proveniencia
    if (p['projeto_uid'], p['revisao_uid']) != (projeto_uid, revisao_uid):
        raise ValueError('O projeto ou a revisão mudou. Resultado não publicado; execute novamente no contexto correto.')
    por_uid = {f['uid']: f for f in fontes}
    for m in p['fontes']:
        f = por_uid.get(m['uid'])
        c = identificar(f, camadas) if f else None
        if c is None or descrever(c)['assinatura'] != m['assinatura'] or f['filtro'] != m['filtro'] or f['campos_mapeados'] != m['campos']:
            raise ValueError('Uma fonte ou configuração mudou durante a análise. Resultado não publicado.')
