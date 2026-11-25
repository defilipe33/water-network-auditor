"""GeoPackages próprios com resultados imutáveis e revisões anexadas."""

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from auditoria_fronteiras.versoes import abrir_ro
from auditoria_fronteiras.modelos import verificar_cancelamento

from .analise_modelo_gis import publicar


SITUACOES = {
    'CADASTRADA':'Origem cadastrada', 'INFORMADA':'Existente informado',
    'A_CONFIRMAR':'Existente a confirmar', 'PROPOSTA':'Proposto', 'HIPOTETICA':'Hipotético',
}
DECISOES = {'CONFIRMADA':'Conexão confirmada', 'SEPARADA':'Sem conexão',
            'CANDIDATA':'Conexão candidata', 'INDETERMINADA':'Indeterminado'}


def complemento_editavel(r):
    return r['tipo'] == 'CONEXAO' or (
        r['tipo'] == 'ORIGEM' and r.get('situacao') != 'CADASTRADA' and not r.get('equipamento'))


def alterar_exclusao(caminho, projeto_uid, registro, excluido):
    """Anexa uma revisão ao complemento e mantém o UUID e as fotos anteriores."""
    if not complemento_editavel(registro):
        raise ValueError('A origem cadastrada no GIS só pode ser retirada da hipótese.')
    if excluido == bool(registro.get('excluido')):
        raise ValueError('O complemento já está nesta situação.')
    dados=dict(registro,excluido=excluido)
    if excluido:
        dados['habilitado_antes_excluir']=registro.get('habilitado',True)
        dados['habilitado']=False
    else:
        dados['habilitado']=dados.pop('habilitado_antes_excluir',True)
    return salvar_revisao(caminho, projeto_uid, registro['tipo'], dados,
                          registro['uuid'], registro['rev'])


def _json(dados):
    return json.dumps(dados,ensure_ascii=False,allow_nan=False,default=str,separators=(',',':'))


def _agora():
    return datetime.now(timezone.utc).isoformat()


def _criar_gpkg(caminho):
    from osgeo import ogr
    driver=ogr.GetDriverByName('GPKG')
    ds=driver.CreateDataSource(str(caminho))
    if ds is None:
        raise OSError('Não foi possível criar o GeoPackage de topologia GIS.')
    try:
        if ds.CreateLayer('TG_CONTEXTO',geom_type=ogr.wkbNone) is None:
            raise OSError('Não foi possível inicializar o GeoPackage de topologia GIS.')
    finally:
        ds=None


def _registrar(con,nome):
    con.execute("INSERT INTO gpkg_contents(table_name,data_type,identifier) VALUES(?,'attributes',?)",(nome,nome))


def _verificar(con):
    if con.execute('PRAGMA quick_check').fetchone()[0]!='ok':
        raise ValueError('Integridade da base topológica não confirmada.')


def criar_complementos(caminho, projeto_uid):
    caminho=Path(caminho)
    temporario=caminho.with_name('.preparando_'+uuid4().hex+'.gpkg')
    try:
        _criar_gpkg(temporario)
        with closing(sqlite3.connect(temporario)) as con, con:
            con.execute('CREATE TABLE TG_PROJETO(projeto_uid TEXT PRIMARY KEY, schema INTEGER NOT NULL)')
            con.execute('INSERT INTO TG_PROJETO VALUES(?,1)',(projeto_uid,))
            con.execute('''CREATE TABLE TG_REVISOES(
                rev TEXT PRIMARY KEY, uuid TEXT NOT NULL, tipo TEXT NOT NULL, anterior TEXT REFERENCES TG_REVISOES(rev),
                data_utc TEXT NOT NULL, dados TEXT NOT NULL)''')
            con.execute('CREATE INDEX tg_revisao_uuid ON TG_REVISOES(uuid)')
            for acao in ('UPDATE','DELETE'):
                con.execute(f"CREATE TRIGGER tg_imutavel_{acao} BEFORE {acao} ON TG_REVISOES "
                            "BEGIN SELECT RAISE(ABORT,'Acrescente uma revisão para alterar o histórico'); END")
            _registrar(con,'TG_PROJETO');_registrar(con,'TG_REVISOES');_verificar(con)
        publicar(temporario,caminho)
    finally:
        temporario.unlink(missing_ok=True)


def _identidade(con, projeto_uid):
    if con.execute('SELECT projeto_uid,schema FROM TG_PROJETO').fetchone()!=(projeto_uid,1):
        raise ValueError('Identidade ou versão do cadastro complementar incompatível.')


def revisoes(caminho, projeto_uid, uid=None):
    if caminho is None:
        return []
    with abrir_ro(caminho) as con:
        _identidade(con,projeto_uid)
        cond=' WHERE uuid=?' if uid else ''
        linhas=con.execute('SELECT rev,uuid,tipo,anterior,data_utc,dados FROM TG_REVISOES'+cond+
                           ' ORDER BY rowid',(uid,) if uid else ())
        return [dict(json.loads(dados),rev=rev,uuid=u,tipo=tipo,anterior=ant,data_utc=data)
                for rev,u,tipo,ant,data,dados in linhas]


def vigentes(caminho, projeto_uid):
    return {r['uuid']:r for r in revisoes(caminho,projeto_uid)}


def salvar_revisao(caminho, projeto_uid, tipo, dados, uid=None, esperada=None):
    if tipo not in ('ORIGEM','CONEXAO','HIPOTESE','DECISAO'):
        raise ValueError('Tipo de revisão inválido.')
    dados={k:v for k,v in dados.items() if k not in ('uuid','rev','tipo','anterior','data_utc')}
    if tipo in ('ORIGEM','CONEXAO') and dados.get('situacao') not in SITUACOES:
        raise ValueError('Informe a natureza do complemento.')
    if tipo=='CONEXAO' and dados.get('decisao') not in DECISOES:
        raise ValueError('Defina a interpretação da conexão.')
    if tipo=='HIPOTESE' and not str(dados.get('nome','')).strip():
        raise ValueError('Dê um nome à hipótese.')
    if dados.get('excluido') and not complemento_editavel(dict(dados,tipo=tipo)):
        raise ValueError('Somente elementos complementares podem ser excluídos.')
    uid, rev=uid or uuid4().hex,uuid4().hex
    with closing(sqlite3.connect(caminho)) as con, con:
        con.execute('PRAGMA foreign_keys=ON')
        con.execute('BEGIN IMMEDIATE')
        _identidade(con,projeto_uid)
        r=con.execute('SELECT rev,tipo FROM TG_REVISOES WHERE uuid=? ORDER BY rowid DESC LIMIT 1',(uid,)).fetchone()
        if (r[0] if r else None)!=esperada or r and r[1]!=tipo:
            raise ValueError('Revisão alterada por outra sessão. Reabra antes de salvar.')
        data=_agora()
        con.execute('INSERT INTO TG_REVISOES VALUES(?,?,?,?,?,?)',(rev,uid,tipo,esperada,data,_json(dados)))
    return dict(dados,uuid=uid,rev=rev,tipo=tipo,anterior=esperada,data_utc=data)


def selecionar(registros, ids):
    """A execução recebe a revisão exata de cada relação explicitamente marcada."""
    ativos=[]
    for uid in ids:
        r=registros.get(uid)
        if not r or r['tipo'] not in ('ORIGEM','CONEXAO') or not r.get('habilitado',True) or r.get('excluido'):
            raise ValueError('Uma relação selecionada foi removida ou desabilitada. Revise a hipótese.')
        ativos.append(r)
    return ativos


def salvar_execucao(caminho, resultado, cancelar=None):
    caminho=Path(caminho)
    temporario=caminho.with_name('.preparando_'+uuid4().hex+'.gpkg')
    try:
        verificar_cancelamento(cancelar)
        _criar_gpkg(temporario)
        with closing(sqlite3.connect(temporario)) as con, con:
            con.execute('''CREATE TABLE TG_EXECUCAO(uuid TEXT PRIMARY KEY,projeto_uid TEXT NOT NULL,
                nome TEXT NOT NULL,data_utc TEXT NOT NULL,schema INTEGER NOT NULL,snapshot TEXT NOT NULL)''')
            meta=resultado['uuid'],resultado['projeto_uid'],resultado['nome'],resultado['data_utc'],1
            con.execute('INSERT INTO TG_EXECUCAO VALUES(?,?,?,?,?,?)',(*meta,_json(resultado)))
            _registrar(con,'TG_EXECUCAO');_verificar(con)
        verificar_cancelamento(cancelar)
        publicar(temporario,caminho)
    finally:
        temporario.unlink(missing_ok=True)


def carregar(caminho, uid, projeto_uid):
    with abrir_ro(caminho) as con:
        r=con.execute('SELECT uuid,projeto_uid,schema,snapshot FROM TG_EXECUCAO').fetchone()
        if r is None or r[:3]!=(uid,projeto_uid,1):
            raise ValueError('A execução pertence a outro projeto ou usa versão incompatível.')
        d=json.loads(r[3])
        if (d.get('uuid'),d.get('projeto_uid'))!=(uid,projeto_uid):
            raise ValueError('O conteúdo do trabalho diverge da sua identidade.')
        return d
