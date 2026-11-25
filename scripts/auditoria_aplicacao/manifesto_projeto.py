"""Formato portátil do projeto existente, sem copiar bases ou fontes GIS."""

from copy import deepcopy
import json
import os
from pathlib import Path
import re
from uuid import uuid4


FORMATO = 'water-network-auditor/projeto'
VERSAO = 1
PASTAS = {
    'TOPOLOGIA_GIS':'analises/conectividade', 'ESTRUTURA_GIS':'analises/estruturantes',
    'AUDITORIA_GIS':'analises/auditorias', 'INTEGRADA':'analises/integradas',
    'TOPOLOGIA_WG':'analises/watergems', 'MODELO':'modelo', 'EXPORTACOES':'exportacoes',
}


def nome_arquivo(nome):
    n=re.sub(r'[^\w-]+','_',nome,flags=re.UNICODE).strip('_')[:64]
    if not n:return 'Projeto'
    if n.upper() in {'CON','PRN','AUX','NUL',*(f'{p}{i}' for p in ('COM','LPT') for i in range(1,10))}:
        return 'Projeto_'+n
    return n


def pasta_projeto(projeto,tipo,alternativa):
    raiz=projeto.get('manifesto_wna')
    if raiz and projeto.get('layout')==1:
        return Path(raiz).parent/PASTAS[tipo]
    return Path(alternativa)


def organizar(projeto, destino, copiar=False, cancelar=None, etapa=lambda *_:None, extras=()):
    """Prepara um manifesto independente. Só copia bancos vinculados e verificados."""
    from contextlib import closing, nullcontext
    from tempfile import TemporaryDirectory
    from auditoria_fronteiras.modelos import verificar_cancelamento
    from auditoria_fronteiras.versoes import abrir_ro
    from .trabalhos_projeto import conferir, chave, referencia
    import shutil
    import sqlite3

    def backup_sqlite(origem, alvo):
        with abrir_ro(origem) as fonte, closing(sqlite3.connect(alvo)) as salvo:
            fonte.backup(salvo,pages=256,progress=lambda *_:verificar_cancelamento(cancelar))
            if salvo.execute('PRAGMA quick_check').fetchone()[0]!='ok':
                raise ValueError(f'Falha ao verificar a cópia de {origem}.')

    destino=Path(destino).resolve().with_suffix('.wna')
    raiz=destino.parent
    if copiar and raiz.exists():
        raise FileExistsError(f'Escolha uma pasta nova para a cópia portátil: {raiz}')
    mesmo=not copiar and bool(projeto.get('manifesto_wna')) and Path(projeto['manifesto_wna']).resolve()==destino
    if destino.exists() and not mesmo:
        raise FileExistsError(f'O manifesto já existe: {destino}')
    contexto=TemporaryDirectory(prefix='.wna_',dir=raiz.parent) if copiar else nullcontext(str(raiz))
    with contexto as temp:
        pasta=Path(temp)/'projeto' if copiar else Path(temp)
        pasta.mkdir(parents=True,exist_ok=True)
        novo=deepcopy(projeto)
        novo['layout']=1
        avisos=[]
        copias={}
        for r in novo.get('bases',()):
            verificar_cancelamento(cancelar)
            etapa(0,'Conferindo '+Path(r['base']).name)
            try:
                confirmado=conferir(projeto['uuid'],r)
            except (ValueError,OSError,sqlite3.Error) as e:
                if copiar and Path(r['base']).exists():
                    raise ValueError(f'A cópia portátil foi interrompida. {e}') from e
                avisos.append(f'{r["base"]} · {e}')
                continue
            r.update(referencia(confirmado))
            if copiar:
                fonte=Path(r['base'])
                if fonte not in copias:
                    alvo=pasta/PASTAS.get(r['tipo'],'analises')/f'{uuid4().hex[:10]}_{fonte.name}'
                    alvo.parent.mkdir(parents=True,exist_ok=True)
                    backup_sqlite(fonte,alvo)
                    copias[fonte]=alvo
                alvo=copias[fonte]
                conferir(projeto['uuid'],r,alvo)
                r['base']=str(alvo)
        complemento=novo.get('arquivo_complementos')
        if complemento:
            try:
                from .persistencia_grafo_gis import identidade
                identidade(complemento,projeto['uuid'])
                if copiar:
                    alvo=pasta/PASTAS['MODELO']/'complementos.gpkg'
                    alvo.parent.mkdir(parents=True,exist_ok=True)
                    backup_sqlite(complemento,alvo)
                    identidade(alvo,projeto['uuid'])
                    novo['arquivo_complementos']=str(alvo)
            except (ValueError,OSError,sqlite3.Error) as e:
                if copiar and Path(complemento).exists():raise
                avisos.append(f'{complemento} · {e}')
        if novo.get('ultima'):
            novo['ultima']=next((r for r in novo['bases'] if chave(r)==chave(novo['ultima'])),novo['ultima'])
        for origem, relativo in extras:
            if Path(origem).is_file() and (pasta/relativo).resolve()!=Path(origem).resolve():
                alvo=pasta/relativo
                alvo.parent.mkdir(parents=True,exist_ok=True)
                if not alvo.exists():
                    # Estados de visualização e rascunhos usam o mesmo escritor atômico.
                    gravar_json(alvo,json.loads(Path(origem).read_text(encoding='utf-8')),exclusivo=True)
        verificar_cancelamento(cancelar)
        backup=pasta/'backups'/('referencias_'+uuid4().hex[:8]+'.wna')
        backup.parent.mkdir(parents=True,exist_ok=True)
        gravar(backup,projeto,exclusivo=True)
        if mesmo:
            return destino,avisos,novo
        arq=pasta/destino.name
        gravar(arq,novo,exclusivo=True)
        if ler(arq)['uuid']!=projeto['uuid']:
            raise ValueError('A identidade do manifesto preparado diverge do projeto.')
        if copiar:
            verificar_cancelamento(cancelar)
            if raiz.exists():
                raise FileExistsError(f'A pasta foi criada por outra sessão: {raiz}')
            pasta.rename(raiz)
    return destino, avisos, None


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
