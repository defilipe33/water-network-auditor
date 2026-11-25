"""Mapa e arquivos autônomos de corredores agrupados e percursos."""

import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from qgis.PyQt.QtCore import QVariant
from qgis.core import (QgsCategorizedSymbolRenderer, QgsFeature, QgsField, QgsGeometry, QgsLineSymbol,
                       QgsProject, QgsRendererCategory, QgsVectorLayer)

from auditoria_fronteiras.modelos import verificar_cancelamento
from auditoria_fronteiras.organizacao_camadas import publicar
from .agrupamento_corredores_gis import FUNCOES
from .representacao_estrutura_gis import GeometriasEstrutura


CAMADA = 'Corredores estruturantes agrupados'
CORES = ('#087ba4', '#ba4429', '#7951a8', '#26714f', '#bd7711', '#ab3d82', '#4256a3', '#396647')


class CorredoresNoMapa:
    def __init__(self, geo, nomes=None):
        self.geo = geo
        self.dados = geo.d.get('agrupamento', {})
        nomes = nomes or {}
        self.corredores = {
            c['uid']: dict(c, nome=nomes[c['uid']]['nome']) if c['uid'] in nomes else c
            for c in self.dados.get('corredores', ())
        }
        self.percursos = {p['uid']: p for p in self.dados.get('percursos', ())}

    def via(self, p):
        rota = self.geo.rotas[p['rota']]
        return rota if p['papel']=='REFERENCIA' else rota['alternativa']

    def linha(self, indices):
        geometrias = [g for i in indices if (g := self.geo.trecho(i))]
        return QgsGeometry.collectGeometry(geometrias) if geometrias else None

    def destaque(self, c, ramais=False):
        indices = list(c['segmentos'])
        if ramais:
            relacionados = set()
            for p in c['percursos']:
                ordem = self.percursos[p]['corredores']
                relacionados.update(ordem[ordem.index(c['uid'])+1:])
            for u in sorted(relacionados):
                indices.extend(self.corredores[u]['segmentos'])
        pontos = [('inicio_corredor', self.geo.no(c['nos'][0])), ('fim_corredor', self.geo.no(c['nos'][-1]))]
        for no in {c['nos'][0], c['nos'][-1]}:
            if len(self.dados['encontros'].get(no, ())) > 2:
                pontos.append(('ramificacao', self.geo.no(no)))
        return [('tubo', self.linha(dict.fromkeys(indices))), *pontos]

    def destaque_percurso(self, p):
        via = self.via(p)
        origem = self.geo.referencia(self.geo.origens.get(p['origem'])) or self.geo.no(via['nos'][0])
        destino = self.geo.destino(self.geo.destinos[p['destino']])
        return [('tubo', self.linha(via['segmentos'])), ('equipamento', origem), ('evento', destino)]

    def preparar_camada(self, cancelar=None):
        """Produz WKB e atributos neutros na tarefa, antes de acessar a árvore QGIS."""
        registros = []
        for c in self.corredores.values():
            verificar_cancelamento(cancelar)
            linha = self.linha(c['segmentos'])
            if linha and not linha.isEmpty():
                registros.append((c, bytes(linha.asWkb())))
        return registros

    def publicar(self, registros):
        projeto = QgsProject.instance()
        camada = QgsVectorLayer('MultiLineString', CAMADA, 'memory')
        camada.setCrs(self.geo.crs)
        camada.setCustomProperty('skipMemoryLayersCheck', 1)
        camada.dataProvider().addAttributes([
            QgsField(k, QVariant.String) for k in ('UUID','Codigo','Nome','Funcoes')
        ])
        camada.updateFields()
        feicoes, categorias, paleta, cores_por_no = [], [], {}, {}
        for c, wkb in registros:
            u = c['uid']
            pontas = c['nos'][0], c['nos'][-1]
            usadas = set().union(*(cores_por_no.get(no, set()) for no in pontas))
            cor = next((v for v in CORES if v not in usadas), CORES[len(paleta) % len(CORES)])
            paleta[u] = cor
            for no in pontas:
                cores_por_no.setdefault(no, set()).add(cor)
            simbolo = QgsLineSymbol.createSimple({
                'line_color':cor, 'line_width':'0.72', 'line_style':'dash' if not c['referencias'] and c['percursos'] else 'solid'
            })
            categorias.append(QgsRendererCategory(u, simbolo, c['nome']))
            f = QgsFeature(camada.fields())
            f.setAttributes([u,c['codigo'],c['nome'],', '.join(FUNCOES[k] for k in c['funcoes'])])
            g = QgsGeometry()
            g.fromWkb(wkb)
            if g.isEmpty():
                raise ValueError('Geometria armazenada de corredor inválida.')
            f.setGeometry(g)
            feicoes.append(f)
        if not camada.dataProvider().addFeatures(feicoes)[0]:
            raise OSError('Falha ao montar a camada de corredores.')
        camada.setRenderer(QgsCategorizedSymbolRenderer('UUID', categorias))
        camada.setReadOnly(True)
        camada.updateExtents()
        return publicar(camada, projeto, 'estrutura', self.geo.d['uuid'], nome=self.geo.d['nome'])


def _tabela(pasta, nome, registros, colunas):
    with (pasta/(nome+'.csv')).open('x', encoding='utf-8-sig', newline='') as f:
        escritor = csv.DictWriter(f, colunas)
        escritor.writeheader()
        for r in registros:
            escritor.writerow({
                k:json.dumps(r.get(k), ensure_ascii=False) if isinstance(r.get(k), (list, dict)) else r.get(k)
                for k in colunas
            })


def exportar_tracado(d, tipo, uid, pasta, formato, geometria_modo='SEGMENTOS', cancelar=None, etapa=lambda *_:None,
                    *, nomes=None):
    """Exporta somente a identidade selecionada, mantendo a ordem em tabela própria."""
    from osgeo import ogr, osr
    if tipo not in ('CORREDOR','PERCURSO') or formato not in ('GPKG','ESRI Shapefile','CSV'):
        raise ValueError('Escolha corredor ou percurso e um formato suportado.')
    if geometria_modo not in ('SEGMENTOS','PIPES'):
        raise ValueError('Escolha segmentos usados ou Pipes físicos completos.')
    geo = GeometriasEstrutura(d)
    macro = CorredoresNoMapa(geo, nomes)
    percurso = macro.percursos.get(uid) if tipo=='PERCURSO' else None
    if percurso:
        via = macro.via(percurso)
        segmentos, nos = via['segmentos'], via['nos']
        corredores = [macro.corredores[u] for u in dict.fromkeys(percurso['corredores'])]
        codigo = percurso['rota'][:8]
    elif tipo=='CORREDOR' and uid in macro.corredores:
        c = macro.corredores[uid]
        segmentos, nos = c['segmentos'], c['nos']
        corredores = [c]
        codigo = c['codigo']
    else:
        raise ValueError('O elemento selecionado não pertence à investigação.')
    por_segmento = {i:c['uid'] for c in corredores for i in c['segmentos']}
    origens = {percurso['origem']} if percurso else {u for c in corredores for u in c['origens']}
    hipotese = {k:v for k,v in (d['hipotese'] or {}).items() if k in ('uuid','rev','nome')}
    metadados = dict(tipo=tipo, uid=uid, investigacao=d['uuid'], projeto=d['projeto_uid'], topologia=d['topologia_uid'],
        hipotese=hipotese, algoritmo=macro.dados['algoritmo'], parametros=macro.dados['parametros'],
        geometria=geometria_modo, crs=geo.crs.authid() or geo.crs.toWkt(), percurso=percurso,
        fontes=[{k:v for k,v in r.items() if k in ('uuid','nome','rev','categoria','situacao')}
                for r in d['foto']['participantes'] if r['tipo']=='ORIGEM' and r['uuid'] in origens],
        destinos=[geo.destinos[u] for u in (sorted({u for c in corredores for u in c['destinos']})
                                           if not percurso else [percurso['destino']])])
    por_pipe, ordem = {}, []
    for pos, i in enumerate(segmentos, 1):
        verificar_cancelamento(cancelar)
        e = geo.arestas[i]
        p = geo.partes[e['tubo']]
        pipe = p.get('feicao', p['uid'])
        por_pipe.setdefault(pipe, []).append(pos)
        ordem.append(dict(ordem=pos, segmento=i, corredor=por_segmento[i], pipe=pipe,
            id_gis=p.get('id'), parte=p['uid'], fontes_gis=p.get('fontes',[]), camada=p.get('camada',''),
            no_inicio=nos[pos-1], no_fim=nos[pos], comprimento_m=e['comprimento_m'],
            diametro_mm=p.get('diametro_mm'), fracao_a=e.get('inicio',0), fracao_b=e.get('fim',1),
            orientacao='A_B' if nos[pos-1]==e['a'] else 'B_A'))
    pipes = [dict(geo.pipes[u], ordens=posicoes, corredores=sorted({ordem[i-1]['corredor'] for i in posicoes}))
             for u,posicoes in por_pipe.items()]
    destino = Path(pasta)/f'{tipo.title()}_{codigo}_{geometria_modo}_{uuid4().hex[:8]}'
    with TemporaryDirectory(prefix='.tracado_', dir=pasta) as tmp:
        saida = Path(tmp)/'saida'
        saida.mkdir()
        etapa(0,'Gravando relações e geometria selecionada')
        _tabela(saida,'segmentos',ordem,('ordem','segmento','corredor','pipe','id_gis','parte','fontes_gis',
            'camada','no_inicio','no_fim','comprimento_m','diametro_mm','fracao_a','fracao_b','orientacao'))
        _tabela(saida,'pipes',pipes,('uid','id','nome','camada','partes','comprimento_m','diametro_mm','ordens','corredores'))
        _tabela(saida,'corredores',corredores,('uid','codigo','nome','funcoes','origens','destinos',
            'comprimento_m','diametros_mm','dependentes','anteriores','posteriores'))
        (saida/'execucao.json').write_text(json.dumps(metadados, ensure_ascii=False, indent=2),encoding='utf-8')
        if formato!='CSV':
            epsg=osr.SpatialReference()
            if epsg.ImportFromWkt(geo.crs.toWkt())!=0:
                raise ValueError('CRS inválido na investigação.')
            completo=geometria_modo=='PIPES'
            caminho=saida/('tracado.gpkg' if formato=='GPKG' else 'tracado.shp')
            ds=ogr.GetDriverByName(formato).CreateDataSource(str(caminho))
            if not ds:
                raise OSError('Não foi possível criar o arquivo cartográfico.')
            camada=ds.CreateLayer('tracado',epsg,ogr.wkbMultiLineString if completo else ogr.wkbLineString,
                                  options=['ENCODING=UTF-8'] if formato!='GPKG' else [])
            if camada is None:
                raise OSError('Não foi possível criar a camada de saída.')
            for k,t in [('ORDEM',ogr.OFTInteger),('PIPE_UID',ogr.OFTString),('ID_GIS',ogr.OFTString),
                        ('CORR_UID',ogr.OFTString),('COMP_M',ogr.OFTReal),('DIAM_MM',ogr.OFTReal),
                        ('TRAC_UID',ogr.OFTString),('NOME',ogr.OFTString),('FUNCOES',ogr.OFTString)]:
                campo=ogr.FieldDefn(k,t)
                if t==ogr.OFTString:campo.SetWidth(128)
                if camada.CreateField(campo)!=0:raise OSError('Falha ao criar atributo '+k)
            geometrias=((r,geo.tubo(r['uid'])) for r in pipes) if completo else (
                (r,geo.trecho(r['segmento'])) for r in ordem)
            for r,g in geometrias:
                verificar_cancelamento(cancelar)
                if not g or g.isEmpty():continue
                f=ogr.Feature(camada.GetLayerDefn())
                corredor_uid = (r['corredores'][0] if len(r['corredores'])==1 else None) if completo else r['corredor']
                info = macro.corredores.get(corredor_uid,{})
                vals=(None,r['uid'],r.get('id'),corredor_uid,r['comprimento_m'],r.get('diametro_mm')) if completo else (
                    r['ordem'],r['pipe'],r['id_gis'],corredor_uid,r['comprimento_m'],r['diametro_mm'])
                vals+=uid, info.get('nome'), ', '.join(FUNCOES[k] for k in info.get('funcoes',()))
                for i,v in enumerate(vals):
                    if v is not None:f.SetField(i,str(v) if i==2 else v)
                f.SetGeometry(ogr.CreateGeometryFromWkb(bytes(g.asWkb())))
                if camada.CreateFeature(f)!=0:raise OSError('Falha ao gravar a geometria exportada.')
            camada=None
            ds=None
        verificar_cancelamento(cancelar)
        saida.rename(destino)
    return destino
