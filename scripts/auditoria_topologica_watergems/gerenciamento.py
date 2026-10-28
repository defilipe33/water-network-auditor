"""Catálogo de metadados e integração gerenciada; nomes nunca são identidades."""
from contextlib import closing
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
from uuid import uuid4
from auditoria_fronteiras.versoes import abrir_ro
from auditoria_fronteiras.persistencia import carregar_execucao
from auditoria_fronteiras.entradas import digest,valor_python
from . import bases
from .arquivos import hash_arquivo
from .indice_bases import IndiceSQLite,ErroCatalogo


def sugestao(pasta,projeto,tipo,versao=None):
    slug=re.sub(r'[^a-zA-Z0-9_-]+','_',unicodedata.normalize('NFKD',projeto).encode('ascii','ignore').decode()).strip('_') or 'Projeto'
    slug=slug[:64]
    raiz=Path(pasta)/slug;raiz.mkdir(parents=True,exist_ok=True);n=versao or 1
    while (raiz/f'{slug}_{tipo}_v{n:03}.gpkg').exists():n+=1
    return raiz/f'{slug}_{tipo}_v{n:03}.gpkg'


def identificar(base):
    p=Path(base).resolve(strict=True);saida=[]
    with abrir_ro(p) as con:
        nomes={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'WB_BASE' in nomes:
            m=bases.metadados(p);saida.append(dict(m,base=str(p)))
        if 'IG_EXECUCOES' in nomes:
            for uid,data,meta in con.execute('SELECT ig_uid,data_utc,meta FROM IG_EXECUCOES'):
                m=json.loads(meta);saida.append(dict(uuid=uid,tipo='INTEGRADA',nome=m.get('nome','Investigação integrada'),projeto=m.get('projeto',''),modelo_uid=m['topologia']['projeto'],
                    versao=m.get('versao',1),anterior=m.get('anterior'),data=data,cenario=m['topologia']['cenario'],hipotese=m.get('hipotese','ESTRUTURAL + POTENCIAL'),base=str(p),situacao='CONCLUIDA'))
        if 'EXECUCOES' in nomes:
            for uid,data,s in con.execute("SELECT exe_uid,data_utc,json_extract(snapshot,'$.controle_versao') FROM EXECUCOES"):
                c=json.loads(s) if s else {}
                eventos=con.execute('SELECT count(*) FROM EVENTOS_FRONTEIRAS WHERE EXE_UID=?',(uid,)).fetchone()[0];locais=con.execute('SELECT count(*) FROM PONTOS_INVESTIGACAO WHERE EXE_UID=?',(uid,)).fetchone()[0]
                saida.append(dict(uuid=uid,tipo='AUDITORIA_GIS',nome=c.get('nome','Auditoria '+uid[:8]),projeto=c.get('projeto',''),modelo_uid='',versao=c.get('versao',1),data=data,cenario=None,hipotese='',base=str(p),situacao='CONCLUIDA',eventos=eventos,locais=locais))
        if not saida and 'WG_TUBULACOES' in nomes:
            saida.append(dict(uuid='legado:'+hash_arquivo(p),tipo='TOPOLOGIA_WG',nome='Topologia legada — importação necessária',projeto='',modelo_uid='',versao=0,data='',cenario=None,hipotese='',base=str(p),situacao='LEGADO_PARCIAL'))
    if not saida:raise ValueError('Arquivo sem metadados de auditoria reconhecidos')
    return saida


class Catalogo(IndiceSQLite):
    def registrar(self,base):
        itens=identificar(base)
        try:
            with self.conectar() as con,con:
                for m in itens:
                    st=Path(m['base']).stat();m['_indice_fonte']=dict(tamanho=st.st_size,mtime_ns=st.st_mtime_ns)
                    con.execute('INSERT OR REPLACE INTO bases VALUES(?,?,?,?)',(m['uuid'],m['tipo'],m['base'],json.dumps(m,ensure_ascii=False)))
        except (sqlite3.Error,OSError) as e:raise self.traduzir(e) from e
        return itens
    def listar(self,**filtros):
        self.garantir()
        with closing(self._abrir_ro()) as con:vazio=con.execute('SELECT count(*) FROM bases').fetchone()[0]==0
        if (self._reconstruir or vazio and not self._reconstrucao_tentada) and not self._varrendo:
            self._reconstruir=False;self._varrendo=True;self._reconstrucao_tentada=True
            try:
                for aviso in self.varrer():self.advertir(aviso)
            finally:self._varrendo=False
        itens=[]
        with closing(self._abrir_ro()) as con:
            for uid,tipo,base,bruto in con.execute('SELECT uuid,tipo,base,dados FROM bases ORDER BY rowid DESC'):
                try:
                    d=json.loads(bruto)
                    if not isinstance(d,dict):raise ValueError('metadados não são objeto')
                    d.update(uuid=uid,tipo=tipo,base=base);itens.append(d)
                except (ValueError,TypeError):self.advertir('Registro com metadados inválidos preservado no catálogo: '+str(uid))
        for r in itens:
            p=Path(r['base']);r['disponivel']=p.is_file()
            if not r['disponivel']:self.advertir('Base movida/ausente; use Adicionar arquivo ou relocalizar por UUID: '+str(p))
            elif r.get('_indice_fonte'):
                st=p.stat();r['indice_desatualizado']=r['_indice_fonte']!=dict(tamanho=st.st_size,mtime_ns=st.st_mtime_ns)
                if r['indice_desatualizado']:self.advertir('Base alterada desde a indexação; use Reexaminar pasta: '+str(p))
        grupos={}
        for r in itens:grupos.setdefault((r['uuid'],r['tipo']),[]).append(r)
        itens=[]
        for grupo in grupos.values():
            vistos={}
            for r in sorted(grupo,key=lambda r:('_antes_' in Path(r['base']).stem,r['base'])):
                p=Path(r['base']);wal=Path(str(p)+'-wal');assinatura=None
                if len(grupo)>1 and r['disponivel'] and not (wal.exists() and wal.stat().st_size):
                    antes=p.stat();assinatura=hash_arquivo(p);depois=p.stat()
                    if (antes.st_size,antes.st_mtime_ns)!=(depois.st_size,depois.st_mtime_ns):assinatura=None
                if assinatura and assinatura in vistos:
                    vistos[assinatura].setdefault('caminhos',[vistos[assinatura]['base']]).append(r['base']);continue
                if assinatura:vistos[assinatura]=r
                itens.append(r)
            assinaturas_ativas={ass for ass,r in vistos.items() if '_antes_' not in Path(r['base']).stem}
            if len(assinaturas_ativas)>1:
                for r in grupo:r['conflito_identidade']=True
                self.advertir('Mesma identidade em arquivos com conteúdo diferente; nenhuma versão escolhida automaticamente: '+grupo[0]['uuid'])
            for r in grupo:
                if '_antes_' in Path(r['base']).stem:r['backup_identidade_compartilhada']=len(grupo)>1
        from .gestao_catalogo import apresentar
        itens=apresentar(self,itens)
        return [r for r in itens if all(v in (None,'') or str(r.get(k,''))==str(v) for k,v in filtros.items())]
    def localizar(self,uuid,tipo,novo_caminho):
        itens=identificar(novo_caminho)
        if not any(m['uuid']==uuid and m['tipo']==tipo for m in itens):raise ValueError('Arquivo não contém a identidade selecionada')
        # O registro antigo permanece como histórico; a nova localização é incluída.
        return self.registrar(novo_caminho)
    def varrer(self):
        avisos=[]
        for p in self.raiz.rglob('*.gpkg'):
            if '_tecnicos' in p.parts or 'RECUPERACAO' in p.parts or 'preparando' in p.name:continue
            try:self.registrar(p)
            except (ValueError,sqlite3.DatabaseError,ErroCatalogo,OSError) as e:avisos.append(str(p)+': '+str(e))
        return avisos


def provar_fontes(modelo,registros,fator,tolerancia,cancelar=None):
    from .validacao import provar_correspondencia
    assocs,e=provar_correspondencia(modelo,registros,fator,tolerancia,cancelar)
    for a in assocs:
        if not a['candidatos'] and a['situacao']=='INCONSISTENTE':
            a['classificacao_bruta']=a['situacao'];a['situacao']='NAO_ENCONTRADA'
            a['indicadores']=a.get('indicadores',[])+['CHAVE_GIS_AUSENTE']
    return assocs,e


def registros_gis(d,mapeamento,crs_destino=None,cancelar=None,registrar_operacoes=False):
    from qgis.core import QgsVectorLayer,QgsGeometry,QgsCoordinateTransform,QgsCoordinateReferenceSystem,QgsProject
    registros=[];avisos=[];mapeamento=mapeamento or {}
    for f in d['contexto']['fontes']:
        if f.get('modo'):continue
        campo=mapeamento.get(f['origem'])
        if not campo:avisos.append('Sem mapeamento explícito para '+f['camada']);continue
        camada=QgsVectorLayer(f['fonte'],f['camada'],f['provedor'])
        if not camada.isValid() or camada.fields().indexFromName(campo)<0:raise ValueError('Fonte/campo indisponível: '+f['camada'])
        crs=camada.crs()
        if not crs.isValid():raise ValueError('Fonte GIS sem CRS')
        destino=QgsCoordinateReferenceSystem(crs_destino) if crs_destino else crs
        if not destino.isValid():raise ValueError('Escolha um CRS de processamento válido antes de comparar coordenadas')
        transformacao=QgsCoordinateTransform(crs,destino,QgsProject.instance().transformContext());regs=[];repetidos={}
        for feat in camada.getFeatures():
            bases.verificar(cancelar);g=QgsGeometry(feat.geometry());attrs={c.name():valor_python(feat[c.name()]) for c in camada.fields()}
            chave=digest([f['origem'],attrs,bytes(g.asWkb()).hex()]);repetidos[chave]=repetidos.get(chave,0)+1
            if crs!=destino:
                if g.transform(transformacao)!=0:raise ValueError('Não foi possível reprojetar a fonte GIS: '+f['camada'])
            valor=attrs[campo]
            from auditoria_fronteiras.apresentacao import legivel
            chave_id=valor if isinstance(valor,str) else legivel(valor) if valor is not None else None
            regs.append(dict(uid=chave+'_'+str(repetidos[chave]),origem=f['origem'],camada=f['camada'],campo=campo,bruto=valor,crs=destino.authid(),chave_cadastral=chave_id,geometria=g))
        if registrar_operacoes:
            operacao=dict(origem=f['origem'],de=crs.toWkt(),para=destino.toWkt(),metodo='IDENTIDADE' if crs==destino else 'QgsCoordinateTransform',
                pipeline=transformacao.instantiatedCoordinateOperationDetails().proj if crs!=destino and regs else None)
            for r in regs:r['operacao_crs']=operacao
        registros+=regs
    return registros,avisos


def preparar_integracao(geo,exe,base_wg,pasta,mapeamento=None,tolerancia=.01,limiar=5,areas=(),cancelar=None):
    from .integracao import preparar
    from .saidas import exportar_json
    from .referencia_espacial import estado_referencia
    t=bases.restaurar(base_wg,cancelar);meta=t['meta_base']
    with abrir_ro(geo) as con:d=carregar_execucao(geo,exe,conexao=con)
    projeto=d.get('controle_versao',{}).get('projeto','')
    if projeto and meta['projeto'] and projeto.casefold().strip()!=meta['projeto'].casefold().strip():raise ValueError('Município/projeto incompatível; confira as identidades e fontes antes de integrar')
    estado=estado_referencia(meta.get('referencia_espacial'),t['modelo'])
    if not t['metrica'] or estado['estado']!='VALIDADO':
        raise ValueError('Integração espacial ainda não liberada: '+'; '.join(estado['faltas'])+'. Abra Verificar evidência existente ou Validar correspondência espacial. Você pode continuar na consulta somente topológica; nenhuma integração foi publicada.')
    pasta=Path(pasta);pasta.mkdir(parents=True,exist_ok=False)
    registros,avisos=registros_gis(d,mapeamento,t['crs'],cancelar)
    # Unicidade bilateral sobre TODAS as fontes escolhidas, inclusive IDs
    # repetidos entre camadas diferentes, conforme prova validada do piloto.
    assocs,e=provar_fontes(t['modelo'],registros,meta['referencia_espacial']['fator'],tolerancia)
    e['mapeamento']=mapeamento
    (pasta/'PROVA_CORRESPONDENCIA.json').write_text(json.dumps(e,ensure_ascii=False,indent=2),encoding='utf8')
    t['estrutural']['associacoes']=assocs
    j=pasta/'AUDITORIA.json';exportar_json(t['modelo'],t['estrutural'],j,completo=False)
    dados=json.loads(j.read_text(encoding='utf8'));dados['execucao_uid']=meta['uuid'];j.write_text(bases.texto(dados),encoding='utf8')
    t['persistido']=dados;t['origem']=dict(execucao_uid=meta['uuid'],data=meta['data'],json=str(j.resolve()),gpkg=str(Path(base_wg).resolve()),json_sha256=hash_arquivo(j),gpkg_sha256=hash_arquivo(base_wg),cenario=meta['cenario'],projeto=meta['modelo_uid'],base_uid=meta['uuid'])
    (pasta/'ASSOCIACOES_GIS_COMPLETAS.json').write_text(json.dumps(assocs,ensure_ascii=False,indent=2),encoding='utf8')
    p=preparar(geo,exe,j,base_wg,limiar,areas,cancelar=cancelar,topologia_pronta=t)
    p['resultado']['meta'].update(projeto=projeto or meta['projeto'],base_watergems=meta['uuid'],hipotese=meta['hipotese'],avisos_integracao=avisos)
    return p
