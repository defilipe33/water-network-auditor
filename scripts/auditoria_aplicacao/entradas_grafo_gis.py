"""Adaptador do Modelo GIS. A leitura e a reprojeção acontecem sobre snapshots."""

from collections import defaultdict
from copy import deepcopy
from math import isfinite

from qgis.core import (QgsCoordinateTransform, QgsCoordinateTransformContext, QgsFeatureRequest,
                       QgsGeometry, QgsVectorLayerFeatureSource)

from auditoria_fronteiras import Parametros
from auditoria_fronteiras.entradas import crs_processamento, digest, valor_python
from auditoria_fronteiras.modelos import verificar_cancelamento

from .modelo_gis import identificar, descrever, expressao, assinatura_confere
from .grafo_gis import _indexar


AREAS = {'SETOR', 'ZONA', 'ZONA_VRP', 'ZONA_BOOSTER', 'LIMITE'}
ORIGENS = {'RESERVOIR', 'TANK', 'ENTRADA'}
EQUIPAMENTOS = ORIGENS | {'PRV', 'PSV', 'TCV', 'FCV', 'PBV', 'PUMP', 'BOOSTER',
                        'AIR_VALVE', 'HYDRANT', 'REGISTRO', 'DISPOSITIVO'}


def preparar(fontes, camadas, crs, contexto, redes=None, unidades=None, *, exigir_rede=True, inventario_completo=False):
    destino = crs_processamento(Parametros(crs=crs))
    omitir = []
    preparadas = []
    for f in fontes:
        categoria = f['categoria']
        if categoria == 'PIPE':
            if redes is not None and f['uid'] not in redes:
                continue
        elif categoria not in AREAS | EQUIPAMENTOS | {'JUNCTION'}:
            continue
        camada = identificar(f, camadas)
        if camada is None or not camada.crs().isValid():
            if categoria == 'PIPE' and not inventario_completo:
                raise ValueError(f"Rede selecionada indisponível ou sem CRS: {f['nome']}. Confira o Modelo GIS.")
            omitir.append(f"{f['nome']}: contexto indisponível ou sem CRS.")
            continue
        atual = descrever(camada)
        if not assinatura_confere(f,atual):
            if categoria == 'PIPE' and not inventario_completo:
                raise ValueError(f"Rede alterada: {f['nome']}. Atualize a fonte no Modelo GIS.")
            omitir.append(f"{f['nome']}: fonte alterada. Atualize o Modelo GIS.")
            continue
        fonte=deepcopy(f)
        if inventario_completo and categoria=='PIPE':
            fonte['filtro']=''
        if inventario_completo and camada.subsetString():
            omitir.append(f"{f['nome']}: subconjunto do provedor limita o universo visível.")
        expressao(fonte['filtro'], atual['campos'])
        preparadas.append((fonte, QgsVectorLayerFeatureSource(camada), camada.crs()))
    if exigir_rede and not any(f['categoria']=='PIPE' for f,_,_ in preparadas):
        raise ValueError('Cadastre e selecione ao menos uma fonte de tubulações.')
    return preparadas, destino, QgsCoordinateTransformContext(contexto), dict(unidades or {}), omitir


def _numero(valor, fator):
    if fator is None or isinstance(valor, bool):
        return None
    try:
        v = float(valor)*fator
        return v if isfinite(v) and v>0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def marca_feicao(origem, atributos, geom):
    return digest([origem,atributos,bytes(geom.asWkb()).hex()])


def ler(preparacao, cancelar=None, etapa=lambda *_:None, *, cadastro=None):
    fontes, destino, contexto, unidades, avisos = preparacao
    tubos, junctions, equipamentos, areas = [], [], [], []
    inventarios = dict(PIPE=tubos, JUNCTION=junctions, EQUIPAMENTO=equipamentos, AREA=areas)
    existentes = {}
    for fonte, snapshot, crs in fontes:
        etapa(0, 'Lendo '+fonte['nome'])
        trans = QgsCoordinateTransform(crs,destino,contexto) if crs != destino else None
        req = QgsFeatureRequest()
        if fonte['filtro']:
            req.setFilterExpression(fonte['filtro'])
        duplicadas = defaultdict(int)
        categoria = fonte['categoria']
        mapeamento = fonte['campos_mapeados']
        inventario = inventarios.get(categoria, areas if categoria in AREAS else equipamentos)
        descartadas = 0
        for f in snapshot.getFeatures(req):
            verificar_cancelamento(cancelar)
            geom = f.geometry()
            if cadastro is not None:
                contagem=cadastro.setdefault(fonte['uid'],dict(lidas=0,descartes=[]))
                contagem['lidas']+=1
            if geom.isEmpty() or not geom.isGeosValid():
                descartadas += 1
                if cadastro is not None:contagem['descartes'].append(dict(fid=f.id(),motivo='Geometria inválida ou vazia'))
                continue
            atributos = {campo.name():valor_python(f[campo.name()]) for campo in snapshot.fields()}
            marca = marca_feicao(fonte['origem_estavel'],atributos,geom)
            duplicadas[marca] += 1
            feicao = f'{marca}_{duplicadas[marca]}'
            if trans and geom.transform(trans) != 0:
                raise ValueError(f"Reprojeção não concluída em {fonte['nome']}.")
            id_bruto = atributos.get(mapeamento.get('id'))
            nome = atributos.get(mapeamento.get('label') or mapeamento.get('nome'))
            unidades_mm = {'mm':1., 'cm':10., 'm':1000., 'pol':25.4}
            unidade = unidades.get(fonte['uid'])
            campo_diametro=mapeamento.get('diametro')
            bruto_diametro=atributos.get(campo_diametro)
            diametro = _numero(bruto_diametro, unidades_mm.get(unidade))
            if cadastro is not None and categoria=='PIPE':
                dx=contagem.setdefault('diametro',dict(campo=campo_diametro,unidade=unidade,contagens={}))
                motivo=('VALIDO' if diametro is not None else 'SEM_CAMPO' if not campo_diametro else
                        'SEM_UNIDADE' if unidade not in unidades_mm else 'SEM_VALOR' if bruto_diametro in (None,'') else
                        'VALOR_INVALIDO')
                dx['contagens'][motivo]=dx['contagens'].get(motivo,0)+1
            for i,g in enumerate(geom.asGeometryCollection() if geom.isMultipart() and categoria in ('PIPE','JUNCTION') else [geom]):
                if categoria=='PIPE' and g.length()<=0:
                    descartadas += 1
                    if cadastro is not None:contagem['descartes'].append(dict(fid=f.id(),motivo='Parte sem comprimento',parte=i))
                    continue
                uid = digest([categoria, feicao, i])
                if uid in existentes:
                    outro = existentes[uid]
                    if (outro['diametro_mm'],outro['classificacao']) != (diametro,fonte['classificacao']):
                        raise ValueError('A mesma feição foi selecionada com classificações ou diâmetros conflitantes.')
                    outro['fontes'].append(fonte['uid'])
                    continue
                caixa = g.boundingBox()
                item = dict(uid=uid, feicao=feicao, parte=i, geom=g, fontes=[fonte['uid']],
                            origem=fonte['origem_estavel'], camada=fonte['nome'], id=id_bruto,
                            label=nome, categoria=categoria, diametro_mm=diametro, unidade_diametro=unidade,
                            classificacao=fonte['classificacao'], origem_id=mapeamento.get('id'),
                            material=atributos.get(mapeamento.get('material')),
                            setor_operacional=atributos.get(mapeamento.get('setor_operacional')),
                            extensao=[caixa.xMinimum(),caixa.yMinimum(),caixa.xMaximum(),caixa.yMaximum()])
                if cadastro is not None:item['atributos_originais']=atributos
                existentes[uid] = item
                inventario.append(item)
        if descartadas:
            avisos.append(f"{fonte['nome']}: {descartadas} geometrias vazias, inválidas ou degeneradas ignoradas.")
    if areas:
        indice = _indexar([a['geom'] for a in areas])
        for t in tubos:
            verificar_cancelamento(cancelar)
            g = t['geom']
            relacionadas = [areas[i] for i in indice.intersects(g.boundingBox()) if g.intersects(areas[i]['geom'])]
            t['zonas'] = sorted({str(a['label'] or a['id'] or a['uid']) for a in relacionadas})
            t['zonas_uids'] = sorted(a['uid'] for a in relacionadas)
    def serializar(inventario):
        return [dict({k:v for k,v in r.items() if k!='geom'},wkb=bytes(r['geom'].asWkb()).hex())
                for r in inventario]
    return tubos, junctions, serializar(equipamentos), serializar(areas), avisos
