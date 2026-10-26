"""GeoPackage relacional, execuções imutáveis e revisões acrescentadas ao histórico."""
from contextlib import contextmanager,nullcontext
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
import struct
from uuid import uuid4

from qgis.core import (QgsVectorLayer,QgsVectorFileWriter,QgsProject,QgsField,
                       QgsCoordinateReferenceSystem,QgsGeometry)
from qgis.PyQt.QtCore import QVariant
from .apresentacao import CAMPOS_PRINCIPAIS,ponto_representativo
from .investigacao import CAMPOS_LOCAIS
from .inspecao import texto,restaurar

SITUACOES=('PENDENTE','EM_ANALISE','VERIFICADO','DESCARTADO','NECESSITA_CONFIRMACAO')
VERSAO=1


def _indices_e_restricoes(con):
    from .versoes import estrutura
    estrutura(con)
    for nome,tabela,colunas in [('vinculo_local','LOCAL_EVENTO','exe_uid,loc_uid'),
            ('vinculo_tubo','EVENTO_REDE','exe_uid,tubo_uid'),('revisao_local','REVISOES','exe_uid,loc_uid')]:
        con.execute(f'CREATE INDEX IF NOT EXISTS {nome} ON {tabela}({colunas})')
    for tabela,chave in [('EVENTOS_FRONTEIRAS','EVT_UID'),('PONTOS_INVESTIGACAO','LOC_UID')]:
        for acao,sufixo in [('INSERT','ins'),('UPDATE OF EXE_UID,'+chave,'upd')]:
            con.execute(f'''CREATE TRIGGER IF NOT EXISTS origem_{tabela}_{sufixo} BEFORE {acao} ON {tabela}
                WHEN NEW.EXE_UID IS NULL OR NEW.{chave} IS NULL OR NOT EXISTS
                    (SELECT 1 FROM EXECUCOES WHERE exe_uid=NEW.EXE_UID)
                BEGIN SELECT RAISE(ABORT,'Execução ou identidade técnica inexistente'); END''')


def _ancoras(local):
    # Apenas candidatos a reconciliação manual; IDs cadastrais nunca aprovam transferência.
    return {(r['origem'],texto(r.get('id_original'))) for r in local['tubulacoes']
            if r.get('id_original') not in (None,'',0,0.)}


def _indice_reconciliacao(antigos):
    registros={}
    por_evento=defaultdict(set)
    por_tubo=defaultdict(set)
    por_ancora=defaultdict(set)
    for exe,snapshot in antigos:
        for local in snapshot['locais']:
            chave=(exe,local['uid'])
            registros[chave]=local
            for uid in local['eventos']:
                por_evento[uid].add(chave)
            for tubo in local['tubulacoes']:
                por_tubo[tubo['chave']].add(chave)
            for ancora in _ancoras(local):
                por_ancora[ancora].add(chave)
    return registros,por_evento,por_tubo,por_ancora,{chave:n for n,chave in enumerate(registros)}


def _candidatos_reconciliacao(local,indice,distancia):
    registros,por_evento,por_tubo,por_ancora,ordem=indice
    candidatos=set()
    for uid in local['eventos']:
        candidatos.update(por_evento[uid])
    for tubo in local['tubulacoes']:
        candidatos.update(por_tubo[tubo['chave']])
    for ancora in _ancoras(local):
        candidatos.update(por_ancora[ancora])
    for chave in sorted(candidatos,key=ordem.get):
        velho=registros[chave]
        comuns=set(local['eventos']) & set(velho['eventos'])
        if not comuns:
            a,b=local['registro'],velho['registro']
            proximos=math.hypot(a['X']-b['X'],a['Y']-b['Y'])<=distancia
            fontes_a={p['origem'] for p in local['poligonos'].values()}
            fontes_b={p['origem'] for p in velho['poligonos'].values()}
            if not proximos or not (fontes_a & fontes_b):
                continue
        yield chave,velho


@contextmanager
def conectar(caminho):
    con=sqlite3.connect(str(caminho),timeout=15)
    con.execute('PRAGMA foreign_keys=ON')
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _iniciar(caminho,crs):
    caminho=Path(caminho)
    if caminho.suffix.lower()!='.gpkg' or not caminho.parent.is_dir():
        raise ValueError('Escolha um GeoPackage em uma pasta existente')
    if caminho.exists():
        with conectar(caminho) as con:
            try:
                versao=con.execute('SELECT versao FROM AUDITORIA_SCHEMA').fetchone()[0]
            except sqlite3.DatabaseError as erro:
                raise ValueError('GeoPackage não é uma base de revisão desta ferramenta; escolha outro arquivo') from erro
            if versao!=VERSAO:
                raise ValueError('Versão de base não suportada')
            _indices_e_restricoes(con)
        return
    for n,(nome,campos,chave) in enumerate([
        ('EVENTOS_FRONTEIRAS',CAMPOS_PRINCIPAIS,'EVT_UID'),
        ('PONTOS_INVESTIGACAO',CAMPOS_LOCAIS,'LOC_UID')]):
        camada=QgsVectorLayer('Point',nome,'memory')
        camada.setCrs(QgsCoordinateReferenceSystem(crs))
        esquema=[QgsField('EXE_UID',QVariant.String),QgsField(chave,QVariant.String)]
        for campo in campos:
            tipo=(QVariant.Double if campo in ('X','Y') else
                  QVariant.Int if campo in ('ID','N_EVENTOS','N_TUBOS') else QVariant.String)
            esquema.append(QgsField(campo,tipo))
        camada.dataProvider().addAttributes(esquema)
        camada.updateFields()
        op=QgsVectorFileWriter.SaveVectorOptions()
        op.driverName='GPKG'
        op.layerName=nome
        op.layerOptions=['SPATIAL_INDEX=NO']
        op.actionOnExistingFile=(QgsVectorFileWriter.CreateOrOverwriteFile if n==0 else
                                  QgsVectorFileWriter.CreateOrOverwriteLayer)
        erro=QgsVectorFileWriter.writeAsVectorFormatV3(camada,str(caminho),QgsProject.instance().transformContext(),op)
        if erro[0]!=QgsVectorFileWriter.NoError:
            raise RuntimeError('Falha ao inicializar GeoPackage: '+str(erro))
    with conectar(caminho) as con:
        con.executescript('''
        CREATE TABLE AUDITORIA_SCHEMA(versao INTEGER NOT NULL);
        INSERT INTO AUDITORIA_SCHEMA VALUES(1);
        CREATE TABLE EXECUCOES(exe_uid TEXT PRIMARY KEY, data_utc TEXT NOT NULL, crs TEXT NOT NULL,
                              metadados TEXT NOT NULL, snapshot TEXT NOT NULL);
        CREATE UNIQUE INDEX evento_uid ON EVENTOS_FRONTEIRAS(EXE_UID,EVT_UID);
        CREATE UNIQUE INDEX local_uid ON PONTOS_INVESTIGACAO(EXE_UID,LOC_UID);
        CREATE TABLE FONTES(exe_uid TEXT, origem TEXT, camada TEXT, dados TEXT,
            PRIMARY KEY(exe_uid,origem), FOREIGN KEY(exe_uid) REFERENCES EXECUCOES);
        CREATE TABLE TUBULACOES(exe_uid TEXT,tubo_uid TEXT,origem TEXT,id_bruto TEXT,id_exibido TEXT,dados TEXT,
            PRIMARY KEY(exe_uid,tubo_uid),FOREIGN KEY(exe_uid,origem) REFERENCES FONTES);
        CREATE TABLE POLIGONOS(exe_uid TEXT,pol_uid TEXT,origem TEXT,id_bruto TEXT,dados TEXT,
            PRIMARY KEY(exe_uid,pol_uid),FOREIGN KEY(exe_uid,origem) REFERENCES FONTES);
        CREATE TABLE EVENTOS_TECNICOS(exe_uid TEXT,evt_uid TEXT,dados TEXT,wkb BLOB,
            PRIMARY KEY(exe_uid,evt_uid),FOREIGN KEY(exe_uid,evt_uid) REFERENCES EVENTOS_FRONTEIRAS(EXE_UID,EVT_UID));
        CREATE TABLE LOCAIS_TECNICOS(exe_uid TEXT,loc_uid TEXT,dados TEXT,
            PRIMARY KEY(exe_uid,loc_uid),FOREIGN KEY(exe_uid,loc_uid) REFERENCES PONTOS_INVESTIGACAO(EXE_UID,LOC_UID));
        CREATE TABLE LOCAL_EVENTO(exe_uid TEXT,loc_uid TEXT,evt_uid TEXT,
            PRIMARY KEY(exe_uid,evt_uid),FOREIGN KEY(exe_uid,loc_uid) REFERENCES PONTOS_INVESTIGACAO(EXE_UID,LOC_UID),
            FOREIGN KEY(exe_uid,evt_uid) REFERENCES EVENTOS_FRONTEIRAS(EXE_UID,EVT_UID));
        CREATE TABLE EVENTO_REDE(exe_uid TEXT,evt_uid TEXT,tubo_uid TEXT,
            PRIMARY KEY(exe_uid,evt_uid,tubo_uid),FOREIGN KEY(exe_uid,evt_uid) REFERENCES EVENTOS_FRONTEIRAS(EXE_UID,EVT_UID),
            FOREIGN KEY(exe_uid,tubo_uid) REFERENCES TUBULACOES);
        CREATE TABLE EVENTO_POLIGONO(exe_uid TEXT,evt_uid TEXT,pol_uid TEXT,papel TEXT,
            PRIMARY KEY(exe_uid,evt_uid,pol_uid,papel),FOREIGN KEY(exe_uid,evt_uid) REFERENCES EVENTOS_FRONTEIRAS(EXE_UID,EVT_UID),
            FOREIGN KEY(exe_uid,pol_uid) REFERENCES POLIGONOS);
        CREATE TABLE REVISOES(rev_uid TEXT PRIMARY KEY,exe_uid TEXT,loc_uid TEXT,situacao TEXT NOT NULL,
            observacoes TEXT,responsavel TEXT,data_utc TEXT,anterior_uid TEXT,herdada_de TEXT,
            CHECK(situacao IN ('PENDENTE','EM_ANALISE','VERIFICADO','DESCARTADO','NECESSITA_CONFIRMACAO')),
            FOREIGN KEY(exe_uid,loc_uid) REFERENCES PONTOS_INVESTIGACAO(EXE_UID,LOC_UID),
            FOREIGN KEY(anterior_uid) REFERENCES REVISOES,FOREIGN KEY(herdada_de) REFERENCES REVISOES);
        CREATE TABLE REVISAO_EVENTO(rev_uid TEXT,exe_uid TEXT,evt_uid TEXT,
            PRIMARY KEY(rev_uid,exe_uid,evt_uid),FOREIGN KEY(rev_uid) REFERENCES REVISOES,
            FOREIGN KEY(exe_uid,evt_uid) REFERENCES EVENTOS_FRONTEIRAS(EXE_UID,EVT_UID));
        CREATE TABLE RECONCILIACOES(exe_uid TEXT,loc_uid TEXT,exe_anterior TEXT,local_anterior TEXT,
            tipo TEXT,decisao TEXT DEFAULT 'PENDENTE',PRIMARY KEY(exe_uid,loc_uid,exe_anterior,local_anterior),
            FOREIGN KEY(exe_uid,loc_uid) REFERENCES PONTOS_INVESTIGACAO(EXE_UID,LOC_UID),
            FOREIGN KEY(exe_anterior,local_anterior) REFERENCES PONTOS_INVESTIGACAO(EXE_UID,LOC_UID));
        CREATE TABLE RECONCILIACAO_AVALIADA(rev_uid TEXT,exe_uid TEXT,loc_uid TEXT,exe_anterior TEXT,local_anterior TEXT,
            PRIMARY KEY(rev_uid,exe_anterior,local_anterior),FOREIGN KEY(rev_uid) REFERENCES REVISOES,
            FOREIGN KEY(exe_uid,loc_uid,exe_anterior,local_anterior) REFERENCES RECONCILIACOES);
        CREATE TRIGGER revisao_imutavel_update BEFORE UPDATE ON REVISOES BEGIN
            SELECT RAISE(ABORT,'Histórico imutável; acrescente uma revisão'); END;
        CREATE TRIGGER revisao_imutavel_delete BEFORE DELETE ON REVISOES BEGIN
            SELECT RAISE(ABORT,'Histórico imutável'); END;
        ''')
        # Tabelas de atributos registradas para acesso pelo navegador QGIS.
        for nome in ('EXECUCOES','FONTES','TUBULACOES','POLIGONOS','EVENTOS_TECNICOS','LOCAIS_TECNICOS',
                     'LOCAL_EVENTO','EVENTO_REDE','EVENTO_POLIGONO','REVISOES','REVISAO_EVENTO','RECONCILIACOES','RECONCILIACAO_AVALIADA'):
            con.execute("INSERT INTO gpkg_contents(table_name,data_type,identifier) VALUES(?, 'attributes', ?)",(nome,nome))
        _indices_e_restricoes(con)


def _geometria(geom,srs):
    # GeoPackageBinary v0, little endian, sem envelope (flags=1), seguido de WKB.
    return struct.pack('<2sBBi',b'GP',0,1,srs)+bytes(geom.asWkb())


def _revisao(con,exe,local,situacao,observacoes,responsavel,esperada=None,herdada=None):
    if situacao not in SITUACOES:
        raise ValueError('Situação de revisão inválida')
    atual=con.execute('SELECT rev_uid FROM REVISOES WHERE exe_uid=? AND loc_uid=? ORDER BY rowid DESC LIMIT 1',
                      (exe,local)).fetchone()
    atual=atual[0] if atual else None
    if esperada!=atual:
        raise ValueError('Revisão alterada por outra sessão; recarregue antes de salvar')
    uid=uuid4().hex
    data=datetime.now(timezone.utc).isoformat(timespec='microseconds')
    con.execute('INSERT INTO REVISOES VALUES(?,?,?,?,?,?,?,?,?)',
        (uid,exe,local,situacao,observacoes,responsavel,data,atual,herdada))
    con.execute('INSERT INTO REVISAO_EVENTO SELECT ?,exe_uid,evt_uid FROM LOCAL_EVENTO WHERE exe_uid=? AND loc_uid=?',
                (uid,exe,local))
    con.execute('UPDATE PONTOS_INVESTIGACAO SET SITUACAO=? WHERE EXE_UID=? AND LOC_UID=?',(situacao,exe,local))
    return dict(situacao=situacao,observacoes=observacoes,responsavel=responsavel,data=data,uid=uid)


def salvar_execucao(caminho,dossie,conexao=None,reconciliar=None,origens_reconciliacao=None,locais_herdaveis=None):
    """Acrescenta uma execução; mesma UUID é idempotente. Não substitui outra base."""
    resultado,_=restaurar(dossie)
    if conexao is None:
        _iniciar(caminho,dossie['contexto']['parametros']['crs'])
    if reconciliar is None:
        reconciliar=dossie.get('controle_versao',{}).get('modo_salvamento','LEGADO') in ('LEGADO','RECONCILIAR')
    exe=dossie['execucao_uid']
    with (conectar(caminho) if conexao is None else nullcontext(conexao)) as con:
        if con.execute('SELECT 1 FROM EXECUCOES WHERE exe_uid=?',(exe,)).fetchone():
            return carregar_execucao(caminho,exe,conexao=con)
        srs=con.execute("SELECT srs_id FROM gpkg_contents WHERE table_name='EVENTOS_FRONTEIRAS'").fetchone()[0]
        crs_existente=QgsVectorLayer(str(caminho)+'|layername=EVENTOS_FRONTEIRAS','crs','ogr').crs()
        if crs_existente!=QgsCoordinateReferenceSystem(resultado.parametros.crs):
            raise ValueError('CRS diferente da base existente; escolha outro GeoPackage')
        antigos=[(r[0],json.loads(r[1])) for r in con.execute('SELECT exe_uid,snapshot FROM EXECUCOES ORDER BY rowid DESC')]
        if origens_reconciliacao is not None:
            antigos=[r for r in antigos if r[0] in origens_reconciliacao]
        indice_reconciliacao=_indice_reconciliacao(antigos)
        con.execute('INSERT INTO EXECUCOES VALUES(?,?,?,?,?)',(exe,datetime.now(timezone.utc).isoformat(),
            resultado.parametros.crs,texto(dossie['analise']['metadados']),texto(dossie)))
        for f in resultado.fontes:
            con.execute('INSERT INTO FONTES VALUES(?,?,?,?)',(exe,f['origem'],f['camada'],texto(f)))
        for r in dossie['tubulacoes']:
            con.execute('INSERT INTO TUBULACOES VALUES(?,?,?,?,?,?)',(exe,r['uid'],r['origem'],texto(r['id_bruto']),r['id_exibido'],texto(r)))
        for p in dossie['poligonos']:
            con.execute('INSERT INTO POLIGONOS VALUES(?,?,?,?,?)',(exe,p['chave'],p['origem'],texto(p.get('id_original')),texto(p)))
        geometrias={e.id:ponto_representativo(e)[0] for e in resultado.ocorrencias}
        for nome,registros,chave,campos in [('EVENTOS_FRONTEIRAS',dossie['eventos'],'uid',CAMPOS_PRINCIPAIS),
                ('PONTOS_INVESTIGACAO',dossie['locais'],'uid',CAMPOS_LOCAIS)]:
            colunas=['EXE_UID','EVT_UID' if nome=='EVENTOS_FRONTEIRAS' else 'LOC_UID','geom']+list(campos)
            sql=f'INSERT INTO {nome}('+','.join('"'+c+'"' for c in colunas)+') VALUES('+','.join('?' for c in colunas)+')'
            for item in registros:
                r=item['registro']
                geom=geometrias[item[chave]] if nome=='EVENTOS_FRONTEIRAS' else QgsGeometry.fromWkt(f"POINT({r['X']} {r['Y']})")
                con.execute(sql,[exe,item[chave],_geometria(geom,srs)]+[r[c] for c in campos])
        for e in dossie['eventos']:
            con.execute('INSERT INTO EVENTOS_TECNICOS VALUES(?,?,?,?)',(exe,e['uid'],texto(e['tecnico']),bytes.fromhex(e['tecnico']['geometria_wkb_hex'])))
        for l in dossie['locais']:
            con.execute('INSERT INTO LOCAIS_TECNICOS VALUES(?,?,?)',(exe,l['uid'],texto(l)))
        for tabela,registros,campos in [
            ('LOCAL_EVENTO',dossie['local_evento'],('local_uid','evento_uid')),
            ('EVENTO_REDE',dossie['evento_rede'],('evento_uid','tubo_uid')),
            ('EVENTO_POLIGONO',dossie['evento_poligono'],('evento_uid','pol_uid','papel'))]:
            con.executemany(f'INSERT INTO {tabela} VALUES('+','.join('?' for _ in range(len(campos)+1))+')',
                            ([exe]+[r[c] for c in campos] for r in registros))
        for l in dossie['locais']:
            novos=set(l['eventos'])
            exata=None
            distancia=max(dossie['analise']['opcoes']['distancia'],dossie['analise']['opcoes']['extensao_maxima'],
                resultado.parametros.tolerancia_geometrica)
            for (anterior,_),velho in _candidatos_reconciliacao(l,indice_reconciliacao,distancia):
                membros=set(velho['eventos'])
                tipo='EXATA' if membros==novos and velho['uid']==l['uid'] and (
                    locais_herdaveis is None or l['uid'] in locais_herdaveis) else 'PARCIAL'
                decisao=('PRESERVADA' if reconciliar else 'HISTORICO') if tipo=='EXATA' else 'PENDENTE'
                con.execute('INSERT INTO RECONCILIACOES VALUES(?,?,?,?,?,?)',
                    (exe,l['uid'],anterior,velho['uid'],tipo,decisao))
                if tipo=='EXATA' and exata is None:
                    exata=con.execute('SELECT rev_uid,situacao,observacoes,responsavel FROM REVISOES '
                        'WHERE exe_uid=? AND loc_uid=? ORDER BY rowid DESC LIMIT 1',(anterior,velho['uid'])).fetchone()
            if exata and reconciliar and (locais_herdaveis is None or l['uid'] in locais_herdaveis):
                _revisao(con,exe,l['uid'],exata[1],exata[2],exata[3],herdada=exata[0])
        from .versoes import registrar_controle
        registrar_controle(con,dossie)
        if con.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Falha de integridade referencial')
    return carregar_execucao(caminho,exe,conexao=conexao)


def listar_execucoes(caminho):
    with conectar(caminho) as con:
        return con.execute('SELECT exe_uid,data_utc FROM EXECUCOES ORDER BY rowid DESC').fetchall()


def carregar_execucao(caminho,exe,conexao=None):
    if conexao is None and not Path(caminho).is_file():
        raise FileNotFoundError(caminho)
    with (conectar(caminho) if conexao is None else nullcontext(conexao)) as con:
        linha=con.execute('SELECT snapshot FROM EXECUCOES WHERE exe_uid=?',(exe,)).fetchone()
        if not linha:
            raise ValueError('Execução inexistente')
        d=json.loads(linha[0])
        for l in d['locais']:
            rev=con.execute('SELECT situacao,observacoes,responsavel,data_utc,rev_uid FROM REVISOES '
                'WHERE exe_uid=? AND loc_uid=? ORDER BY rowid DESC LIMIT 1',(exe,l['uid'])).fetchone()
            if rev:
                l['revisao']=dict(zip(('situacao','observacoes','responsavel','data','uid'),rev))
                l['registro']['SITUACAO']=rev[0]
        d['reconciliacoes']=[dict(zip(('local_uid','execucao_anterior','local_anterior','tipo','decisao'),r))
            for r in con.execute('SELECT loc_uid,exe_anterior,local_anterior,tipo,decisao FROM RECONCILIACOES WHERE exe_uid=?',(exe,))]
        for r in d['reconciliacoes']:
            if con.execute('SELECT 1 FROM RECONCILIACAO_AVALIADA WHERE exe_uid=? AND loc_uid=? AND exe_anterior=? AND local_anterior=?',
                (exe,r['local_uid'],r['execucao_anterior'],r['local_anterior'])).fetchone():
                r['decisao']='AVALIADA_MANUALMENTE'
        from .versoes import complementar
        return complementar(con,d)


def salvar_revisao(caminho,exe,local,situacao,observacoes='',responsavel='',esperada=None):
    with conectar(caminho) as con:
        return _revisao(con,exe,local,situacao,observacoes,responsavel,esperada)


def historico(caminho,exe,local):
    with conectar(caminho) as con:
        con.row_factory=sqlite3.Row
        return [dict(r) for r in con.execute('SELECT * FROM REVISOES WHERE exe_uid=? AND loc_uid=? ORDER BY rowid',(exe,local))]


def avaliar_reconciliacoes(caminho,exe,local,rev_uid):
    """Registro explícito do engenheiro, associado a uma revisão já salva."""
    with conectar(caminho) as con:
        if not con.execute('SELECT 1 FROM REVISOES WHERE rev_uid=? AND exe_uid=? AND loc_uid=?',(rev_uid,exe,local)).fetchone():
            raise ValueError('Revisão não pertence ao local informado')
        con.execute('INSERT INTO RECONCILIACAO_AVALIADA SELECT ?,exe_uid,loc_uid,exe_anterior,local_anterior '
                    "FROM RECONCILIACOES WHERE exe_uid=? AND loc_uid=? AND tipo='PARCIAL'",(rev_uid,exe,local))
        from .versoes import estrutura
        estrutura(con)
        con.execute('INSERT OR IGNORE INTO AUDITORIA_LINHAGEM_AVALIADA '
            'SELECT ?,exe_uid,loc_uid,origem_base,origem_exe,origem_local FROM AUDITORIA_LINHAGEM '
            "WHERE exe_uid=? AND loc_uid=? AND tipo='PARCIAL'",(rev_uid,exe,local))


def exportar_gpkg(caminho,dossie,base_origem=None):
    """Nova entrega; backup SQLite preserva todo o histórico quando já existe base."""
    destino=Path(caminho)
    if destino.exists():
        raise FileExistsError('Escolha um novo arquivo GeoPackage')
    if base_origem:
        execucoes={e for e,_ in listar_execucoes(base_origem)}
        if dossie['execucao_uid'] in execucoes:
            with destino.open('xb'):
                pass
            with conectar(base_origem) as origem,conectar(destino) as copia:
                origem.backup(copia)
            return carregar_execucao(destino,dossie['execucao_uid'])
    atual=salvar_execucao(destino,dossie)
    for l in dossie['locais']:
        rev=l['revisao']
        if rev.get('uid') or rev['situacao']!='PENDENTE' or rev['observacoes']:
            salvar_revisao(destino,dossie['execucao_uid'],l['uid'],rev['situacao'],rev['observacoes'],rev['responsavel'])
    return carregar_execucao(destino,dossie['execucao_uid'])
