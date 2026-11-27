"""Cópia independente de trabalhos GIS e fontes locais explicitamente escolhidas."""

from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
from uuid import uuid4

from auditoria_fronteiras.versoes import abrir_ro
from auditoria_fronteiras.modelos import verificar_cancelamento
from . import estado_projeto as estado, persistencia_grafo_gis as pg, trabalhos_projeto as tp
from .manifesto_projeto import gravar_json, organizar


NATIVOS={'TOPOLOGIA_GIS':(pg.carregar,pg.salvar_execucao),
         'ESTRUTURA_GIS':(pg.carregar_estrutura,pg.salvar_estrutura)}


def copiar(projeto,destino,modo,*,incorporar=False,cancelar=None,etapa=lambda *_:None,extras=()):
    if modo not in ('INDEPENDENTE','MOVER','PORTATIL'):
        raise ValueError('Modo de cópia desconhecido.')
    if modo=='INDEPENDENTE':
        externos={r['tipo'] for r in projeto['bases'] if r['tipo'] not in NATIVOS}
        if externos:
            raise ValueError('A cópia independente requer trabalhos GIS com identidade remapeável. '
                             'Use a cópia portátil para estes tipos: '+', '.join(sorted(externos)))
    def preparar(novo,pasta):
        if modo=='INDEPENDENTE':
            _independente(novo,pasta,cancelar,etapa)
        else:
            _copiar_pacotes_modelbuilder(projeto,pasta,cancelar,etapa)
        _copiar_fontes(novo,pasta,cancelar,etapa,apenas_internas=not incorporar)
    return organizar(projeto,destino,True,cancelar,etapa,extras,preparar_copia=preparar)


def _copiar_pacotes_modelbuilder(projeto,pasta,cancelar,etapa):
    from .modelbuilder_gis import ler_pacote
    arq=projeto.get('arquivo_complementos')
    manifesto=projeto.get('manifesto_wna')
    if not arq or not manifesto or not Path(arq).is_file():
        return
    raiz=Path(manifesto).parent.resolve()
    formatos={'.shp','.shx','.dbf','.prj','.cpg','.gpkg','.csv','.json','.txt'}
    arquivos={'MODELBUILDER.json','validacao.json','operacoes_topologicas.json','cadastro_modelagem.gpkg',
              'inventario_cadastral.csv','IMPORTAR_NO_MODELBUILDER.txt','CRIAR_SELECTION_SETS.txt',
              'MODELO_CONFERENCIA_WATERGEMS.csv','INDICE_QUERIES.csv','reconciliacao.json','correspondencias.gpkg'}
    from .tipos_modelbuilder import CAMADAS
    prefixos=('WNA_','MINUTA_ATIVIDADE_','pipes.','inventario_','referencia_',
              *(n+'.' for n in CAMADAS.values()))
    for r in pg.revisoes(arq,projeto['uuid'],tipo='MODELBUILDER_EXPORTACAO'):
        verificar_cancelamento(cancelar)
        if not r.get('relativo'):
            continue
        pacote=(raiz/r['pasta']).resolve()
        if not pacote.is_relative_to(raiz) or not pacote.is_dir():
            continue
        m,_=ler_pacote(pacote)
        if m['projeto']!=projeto['uuid'] or m['assinatura_csv']!=r['assinatura']:
            raise ValueError('O pacote ModelBuilder não corresponde à referência arquivada.')
        etapa(0,'Copiando pacote ModelBuilder confirmado')
        subs=[pacote,*[d for d in pacote.iterdir() if d.is_dir() and
                       (d.name=='MINUTAS_QUERIES' or d.name.startswith('Conferencia_'))]]
        for f in (f for d in subs for f in d.iterdir() if d.resolve().is_relative_to(pacote) and not d.is_symlink()):
            verificar_cancelamento(cancelar)
            if not f.is_file() or f.is_symlink() or not f.resolve().is_relative_to(pacote) or f.suffix.lower() not in formatos:
                continue
            if f.name not in arquivos and not f.name.startswith(prefixos) and not (
                    f.parent.name=='MINUTAS_QUERIES' and f.suffix.lower()=='.txt'):
                continue
            alvo=pasta/f.relative_to(raiz)
            alvo.parent.mkdir(parents=True,exist_ok=True)
            if not alvo.exists():
                shutil.copyfile(f,alvo)


def _trocar(d,ids):
    if isinstance(d,dict):
        campos={'uuid','projeto_uid','topologia_uid','referencia','analise_uid',
                'execucao','execucao_uid','estrutura_uid','comparacao','automatico_macro'}
        return {k:ids.get(v,v) if isinstance(v,str) and k in campos else _trocar(v,ids) for k,v in d.items()}
    if isinstance(d,list):
        return [_trocar(v,ids) for v in d]
    return d


def _independente(novo,pasta,cancelar,etapa):
    antigo=novo['uuid']
    ids={antigo:uuid4().hex}
    for r in novo['bases']:ids[r['uuid']]=uuid4().hex
    alterado=_trocar(novo,ids)
    alterado['procedencia_wna']=dict(projeto=antigo, trabalhos={k:v for k,v in ids.items() if k!=antigo},
                                    data=tp.agora())
    for r in novo['bases']:
        verificar_cancelamento(cancelar)
        abrir,salvar=NATIVOS[r['tipo']]
        p=Path(r['base'])
        if not p.is_relative_to(pasta):
            raise ValueError('A cópia independente precisa conter todos os trabalhos. Arquivo ausente: '+str(p))
        etapa(0,'Remapeando a identidade de '+r['nome'])
        dados=_trocar(abrir(p,r['uuid'],antigo),ids)
        tmp=p.with_name('.independente_'+uuid4().hex+'.gpkg')
        salvar(tmp,dados,cancelar)
        tmp.replace(p)
        tp.conferir(alterado['uuid'],dict(r,uuid=dados['uuid']))
    if arq:=novo.get('arquivo_complementos'):
        if not Path(arq).is_relative_to(pasta):
            raise ValueError('A cópia independente precisa do banco de complementos.')
        with closing(sqlite3.connect(arq)) as con,con:
            con.execute('BEGIN IMMEDIATE')
            pg._identidade(con,antigo)
            con.execute('UPDATE TG_PROJETO SET projeto_uid=?',(alterado['uuid'],))
            tr=con.execute("SELECT sql FROM sqlite_master WHERE name='tg_imutavel_UPDATE'").fetchone()[0]
            con.execute('DROP TRIGGER tg_imutavel_UPDATE')
            for rev,txt in con.execute('SELECT rev,dados FROM TG_REVISOES'):
                verificar_cancelamento(cancelar)
                novo_txt=pg._json(_trocar(json.loads(txt),ids))
                if novo_txt!=txt:con.execute('UPDATE TG_REVISOES SET dados=? WHERE rev=?',(novo_txt,rev))
            con.execute(tr)
        pg.identidade(arq,alterado['uuid'])
    for tipo in (estado.RASCUNHO,estado.VISUAL):
        a=pasta/estado.caminho_relativo(novo,tipo)
        if not a.is_file():continue
        d=json.loads(a.read_text(encoding='utf-8'))
        d=_trocar(d,ids)
        if tipo==estado.VISUAL:
            d['dados']={k.split(':',1)[0]+':'+ids.get(k.split(':',1)[1],k.split(':',1)[1]):v
                        for k,v in d['dados'].items() if ':' in k}
        destino=pasta/estado.caminho_relativo(alterado,tipo)
        destino.parent.mkdir(parents=True,exist_ok=True)
        gravar_json(destino,d,exclusivo=True)
        a.unlink()
    novo.clear()
    novo.update(alterado)


def _copiar_fontes(projeto,pasta,cancelar,etapa,*,apenas_internas):
    from .modelo_gis import revisoes
    copias={}
    externas=[]
    for rev in revisoes(projeto):
        for f in rev.get('fontes',()):
            verificar_cancelamento(cancelar)
            if f.get('arquivo_portatil'):
                origem=Path(projeto['manifesto_wna']).parent/f['arquivo_portatil']
                sufixo=f.get('opcoes_portateis','')
            else:
                caminho,separador,opcoes=f['uri'].partition('|')
                origem=Path(caminho)
                sufixo=separador+opcoes
                if apenas_internas:
                    externas.append(f['nome'])
                    continue
            if (f['provedor']!='ogr' or not origem.is_absolute() or str(origem).startswith(('\\','//'))
                    or origem.suffix.lower() not in ('.shp','.gpkg','.geojson','.fgb')
                    or not origem.is_file()):
                externas.append(f['nome'])
                continue
            destino=copias.get(origem)
            if destino is None:
                etapa(0,'Copiando fonte GIS '+f['nome'])
                destino=pasta/'fontes_gis'/uuid4().hex[:10]/origem.name
                destino.parent.mkdir(parents=True,exist_ok=False)
                if origem.suffix.lower()=='.gpkg':
                    with abrir_ro(origem) as con,closing(sqlite3.connect(destino)) as ds:
                        con.backup(ds,pages=256,progress=lambda *_:verificar_cancelamento(cancelar))
                        if ds.execute('PRAGMA quick_check').fetchone()[0]!='ok':
                            raise ValueError('A cópia da fonte GeoPackage falhou na conferência.')
                else:
                    shutil.copy2(origem,destino)
                    if origem.suffix.lower()=='.shp':
                        for ext in ('.dbf','.shx','.prj','.cpg','.qpj'):
                            a=origem.with_suffix(ext)
                            if a.is_file():shutil.copy2(a,destino.with_suffix(ext))
                            elif ext in ('.dbf','.shx'):raise ValueError('Shapefile incompleto: '+str(origem))
                copias[origem]=destino
            f['arquivo_portatil']=destino.relative_to(pasta).as_posix()
            f['opcoes_portateis']=sufixo
            f['marca_portatil']={}
            for a in destino.parent.iterdir():
                m=a.stat()
                f['marca_portatil'][a.name[len(destino.stem):].lower()]=[m.st_size,m.st_mtime_ns]
    projeto['fontes_externas_na_copia']=sorted(set(externas))
