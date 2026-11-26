"""Exportação autônoma dos segmentos e nós de um escopo da visão macro."""

import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from auditoria_fronteiras.modelos import verificar_cancelamento
from .macro_origem_gis import caminho
from .topologia_derivada import preparar


PIPES = dict(uid='seg_uid', original='pipe_uid', parte='parte_uid', gis_id='gis_id', label='label',
             no_a='no_a', no_b='no_b', inicio='inicio', fim='fim', comprimento_m='comp_m',
             diametro_mm='diam_mm', material='material', natureza='natureza', proposta='proposta',
             bloco='bloco', corredor='corredor', continuidade='continuid')
NOS = dict(uid='no_uid', natureza='natureza')
REAIS = {'inicio', 'fim', 'comprimento_m', 'diametro_mm'}


def _csv(saida, nome, colunas, linhas, cancelar):
    with (saida / (nome + '.csv')).open('w', newline='', encoding='utf-8-sig') as arq:
        w = csv.DictWriter(arq, colunas, extrasaction='ignore')
        w.writeheader()
        for r in linhas:
            verificar_cancelamento(cancelar)
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict, tuple)) else v
                        for k, v in r.items() if k in colunas})


def _vetor(saida, formato, nome, tipo, campos, linhas, crs, cancelar, ds=None, *, reais=REAIS):
    from osgeo import ogr

    shp = formato == 'ESRI Shapefile'
    proprio = shp and ds is None
    if proprio:
        ds = ogr.GetDriverByName(formato).CreateDataSource(str(saida / (nome + '.shp')))
    camada = f = None
    try:
        if ds is None:
            raise OSError('Falha ao criar a camada ' + nome)
        camada = ds.CreateLayer(nome, crs, tipo, options=['ENCODING=UTF-8'] if shp else [])
        if camada is None:
            raise OSError('Falha ao criar a camada ' + nome)
        nomes = campos if shp else {k: k for k in campos}
        for k, campo in nomes.items():
            if camada.CreateField(ogr.FieldDefn(campo, ogr.OFTReal if k in reais else ogr.OFTString)) != 0:
                raise OSError('Falha ao criar o campo ' + campo)
        if not shp and camada.StartTransaction() != 0:
            raise OSError('Falha ao iniciar a transação de exportação.')
        for r in linhas:
            verificar_cancelamento(cancelar)
            f = ogr.Feature(camada.GetLayerDefn())
            for k, campo in nomes.items():
                v = r.get(k)
                if v is not None:
                    f.SetField(campo, v if k in reais else str(v))
            g = ogr.CreateGeometryFromWkb(r['wkb']) if nome == 'pipes' else ogr.Geometry(ogr.wkbPoint)
            if nome != 'pipes':
                g.AddPoint_2D(*r['xy'])
            f.SetGeometry(g)
            if camada.CreateFeature(f) != 0:
                raise OSError('Falha ao gravar uma feição em ' + nome)
        if not shp and camada.CommitTransaction() != 0:
            raise OSError('Falha ao confirmar a transação de exportação.')
    finally:
        f = camada = None
        if proprio and ds is not None:
            ds.Destroy()


def exportar(d, pasta, formato, segmentos, *, tipo, alvo=None, incluir_referencia=False, origem=None,
             cancelar=None, etapa=lambda *_: None):
    from osgeo import ogr, osr

    if formato not in ('GPKG', 'ESRI Shapefile', 'CSV'):
        raise ValueError('Formato de exportação desconhecido.')
    m, foto = d['macro_origem'], d['foto']
    selecionados = set(segmentos)
    if not selecionados or not selecionados <= set(m['alcancaveis']):
        raise ValueError('O escopo precisa conter segmentos alcançáveis desta fotografia.')
    etapa(0, 'Conferindo continuidade e materializando Pipes e Junctions')
    referencia = set(caminho(foto, m, selecionados, origem, cancelar))
    extras = referencia - selecionados
    indices = sorted(selecionados | extras if incluir_referencia else selecionados)
    tubos, nos, divisoes, pendencias = preparar(foto, cancelar, indices=indices)
    blocos = {i: b for b in m['blocos'] for i in b['segmentos']}
    corredores = {i: c['uid'] for c in m['corredores'] for i in c['segmentos']}
    if origem is not None:
        corredores.update({i: c['uid'] for c in m['referencias_por_origem'][origem]['corredores'] for i in c['segmentos']})
    partes = {t['uid']: t for t in foto['tubos']}
    fontes = {f['uid']: f for f in foto.get('fontes', ())}
    for i, r in zip(indices, tubos):
        p = partes[r['parte']]
        r.update(bloco=blocos[i]['uid'], corredor=corredores.get(i), label=p.get('label'),
                 continuidade='REFERENCIA_ADICIONAL' if i in extras else 'SELECIONADO',
                 origens=m['componentes'][m['componente_segmento'][i]]['origens'],
                 camadas=[fontes.get(u, {}).get('nome', u) for u in r['fontes']],
                 areas=m['areas_segmentos'].get(str(i), {}))
    nos_exportados = {n['uid'] for n in nos}
    portas_usadas = {(r['parte'], r[k]) for r in tubos for k in ('inicio', 'fim')}
    portas_no = {tuple(p): n['uid'] for n in nos for p in n['portas']}
    conexoes = []
    for r in foto.get('participantes', ()):
        ps = {tuple(p) for p in r.get('portas', ())}
        if (r['tipo'] == 'CONEXAO' and foto.get('resolucoes_conexoes', {}).get(r['uuid']) == 'APLICADA'
                and ps and ps <= portas_no.keys()):
            conexoes.append(dict(uuid=r['uuid'], revisao=r.get('rev'), situacao=r['situacao'],
                                 portas=sorted(ps), nos=sorted({portas_no[p] for p in ps} & nos_exportados),
                                 todas_partes_exportadas=all(p in portas_usadas or p[0] == 'J' for p in ps)))
    crs = osr.SpatialReference()
    if crs.SetFromUserInput(foto['crs']) != 0:
        raise ValueError('CRS de exportação inválido.')
    pasta = Path(pasta)
    destino = pasta / ('Visao_macro_' + d['uuid'][:8] + '_' + uuid4().hex[:8])
    with TemporaryDirectory(prefix='.macro_', dir=pasta) as temp:
        saida = Path(temp) / 'saida'
        saida.mkdir()
        if formato != 'CSV':
            ds = None
            try:
                if formato == 'GPKG':
                    ds = ogr.GetDriverByName(formato).CreateDataSource(str(saida / 'rede_macro.gpkg'))
                _vetor(saida, formato, 'pipes', ogr.wkbLineString, PIPES, tubos, crs, cancelar, ds)
                _vetor(saida, formato, 'junctions', ogr.wkbPoint, NOS, nos, crs, cancelar, ds)
            finally:
                if ds is not None:
                    ds.Destroy()
        else:
            for r in tubos:
                verificar_cancelamento(cancelar)
                r['wkt'] = ogr.CreateGeometryFromWkb(r['wkb']).ExportToWkt()
            nos = [dict(n, wkt=f"POINT ({n['xy'][0]} {n['xy'][1]})") for n in nos]
        _csv(saida, 'pipes', (*PIPES, 'fontes', 'camadas', 'origens', 'areas', 'wkt'), tubos, cancelar)
        _csv(saida, 'junctions', (*NOS, 'portas', 'xy', 'wkt'), nos, cancelar)
        manifesto = dict(projeto=d['projeto_uid'], trabalho=d['uuid'], execucao=foto['uuid'],
                         hipotese=foto.get('hipotese'), algoritmo=m['algoritmo'], parametros=m['parametros'],
                         origens=[origem] if origem else m['origens'], escopo=tipo, alvo=alvo,
                         crs=foto['crs'], unidades={'comprimento': 'm', 'diametro': 'mm'},
                         segmentos=len(tubos), pipes_distintos=len({r['original'] for r in tubos}),
                         junctions=len(nos), divisoes=divisoes, conexoes=conexoes, pendencias=pendencias,
                         segmentos_referencia_externos=sorted(extras),
                         referencia_incluida=incluir_referencia,
                         conjunto_parcial=bool(extras and not incluir_referencia),
                         dicionario_shp={'pipes': PIPES, 'junctions': NOS} if formato == 'ESRI Shapefile' else {},
                         finalidade='Prévia de topologia GIS. Confira as conexões antes de importar no WaterGEMS.')
        (saida / 'validacao.json').write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding='utf-8')
        verificar_cancelamento(cancelar)
        saida.rename(destino)
    return destino
