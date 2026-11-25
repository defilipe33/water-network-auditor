"""Formato portátil do projeto existente, sem copiar bases ou fontes GIS."""

from copy import deepcopy
import json
import os
from pathlib import Path
from uuid import uuid4


FORMATO = 'water-network-auditor/projeto'
VERSAO = 1


def _caminhos(objeto, pasta, resolver):
    if isinstance(objeto, list):
        for item in objeto:
            _caminhos(item,pasta,resolver)
    elif isinstance(objeto, dict):
        for chave, valor in list(objeto.items()):
            if chave in ('base', 'arquivo_complementos') and isinstance(valor, str) and valor:
                caminho = Path(valor)
                if resolver:
                    objeto[chave] = str((pasta / caminho).resolve())
                elif caminho.is_absolute():
                    objeto[chave] = caminho.relative_to(pasta).as_posix() if caminho.is_relative_to(pasta) else str(caminho)
            else:
                _caminhos(valor,pasta,resolver)


def ler(caminho):
    caminho = Path(caminho).resolve()
    d = json.loads(caminho.read_text(encoding='utf-8'))
    p = d.get('projeto') if isinstance(d, dict) else None
    if (not isinstance(p, dict) or d.get('formato') != FORMATO or d.get('versao') != VERSAO
            or not isinstance(p.get('uuid'), str) or not p['uuid']
            or not isinstance(p.get('nome'), str) or not p['nome']
            or not isinstance(p.get('bases'), list)
            or any(not isinstance(r,dict) or not all(isinstance(r.get(k),str) and r[k] for k in ('uuid','tipo','base'))
                   for r in p['bases'])):
        raise ValueError('Arquivo .wna inválido ou versão incompatível.')
    _caminhos(p,caminho.parent,True)
    p['manifesto_wna'] = str(caminho)
    return p


def gravar_json(caminho, dados, exclusivo=False):
    caminho = Path(caminho)
    temporario = caminho.with_name('.'+caminho.name+'.'+uuid4().hex+'.tmp')
    try:
        with temporario.open('x', encoding='utf-8') as f:
            json.dump(dados,f,indent=2,ensure_ascii=False,allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        if exclusivo:
            # No Windows, rename falha se o destino já existe.
            if os.name=='nt':
                temporario.rename(caminho)
            else:
                os.link(temporario,caminho)
        else:
            os.replace(temporario,caminho)
    finally:
        temporario.unlink(missing_ok=True)


def gravar(caminho, projeto, exclusivo=False):
    caminho = Path(caminho).resolve()
    dados = deepcopy(projeto)
    dados.pop('manifesto_wna',None)
    _caminhos(dados,caminho.parent,False)
    gravar_json(caminho, dict(formato=FORMATO,versao=VERSAO,projeto=dados),exclusivo)


def recuperar_camadas_locais(projeto):
    """Abre somente arquivos locais reconhecidos quando o usuário abre o projeto."""
    from qgis.core import QgsProject, QgsProviderRegistry, QgsVectorLayer, QgsRasterLayer
    from .modelo_gis import revisoes, origem_camada

    r=next(reversed(revisoes(projeto)),{})
    q=QgsProject.instance()
    avisos=[]
    tipos={'ogr':(QgsVectorLayer,{'.shp','.gpkg','.geojson','.json','.sqlite','.fgb'}),
           'gdal':(QgsRasterLayer,{'.tif','.tiff','.img'})}
    camadas=list(q.mapLayers().values())
    por_origem={origem_camada(c) for c in camadas if c.isValid()}
    for f in r.get('fontes',[]):
        if f['origem'] in por_origem or f['provedor'] not in tipos:
            continue
        classe, extensoes=tipos[f['provedor']]
        uri=f['uri']
        dados=QgsProviderRegistry.instance().decodeUri(f['provedor'],uri)
        arq=dados.get('path')
        if not arq or any(c in uri for c in ('://','/vsi')) or arq.startswith(('\\\\','//')):
            continue
        caminho=Path(arq)
        if not caminho.is_absolute() or caminho.suffix.lower() not in extensoes or not caminho.is_file():
            avisos.append(f["nome"]+': fonte ausente. Use relocalizar no Modelo GIS.')
            continue
        camada=classe(uri,f['nome'],f['provedor'])
        if not camada.isValid():
            avisos.append(f["nome"]+': fonte indisponível no QGIS.')
            continue
        if isinstance(camada,QgsVectorLayer):
            camada.setReadOnly(True)
            if f.get('filtro_provedor'):
                camada.setSubsetString(f['filtro_provedor'])
        if origem_camada(camada)!=f['origem']:
            avisos.append(f["nome"]+': identidade da fonte diverge. Relocalize e confira o cadastro.')
            continue
        q.addMapLayer(camada)
        por_origem.add(f['origem'])
    return avisos
