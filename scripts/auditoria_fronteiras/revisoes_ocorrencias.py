"""Extensão aditiva de decisões individuais, sem reinterpretar revisões de locais."""
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from .persistencia import conectar, SITUACOES
from .versoes import abrir_ro, backup_verificado

TABELA = 'REVISOES_OCORRENCIAS'


def existe(con):
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABELA,)).fetchone())


def preparar(base, exe):
    with abrir_ro(base) as con:
        if existe(con):
            if con.execute('SELECT versao FROM REVISOES_OCORRENCIAS_SCHEMA').fetchone()[0] != 1:
                raise ValueError('Versão de decisões individuais não suportada.')
            return
    p = Path(base)
    backup_verificado(p, p.with_name(p.stem + '_antes_decisoes_ocorrencias_' + uuid4().hex[:12] + '.gpkg'), exe)
    with conectar(p) as con:
        con.execute('BEGIN IMMEDIATE')
        if existe(con): return
        con.execute('CREATE TABLE REVISOES_OCORRENCIAS_SCHEMA(versao INTEGER NOT NULL CHECK(versao=1))')
        con.execute('INSERT INTO REVISOES_OCORRENCIAS_SCHEMA VALUES(1)')
        con.execute('''CREATE TABLE REVISOES_OCORRENCIAS(
            rev_uid TEXT PRIMARY KEY,exe_uid TEXT NOT NULL,evt_uid TEXT NOT NULL,
            situacao TEXT NOT NULL CHECK(situacao IN ('PENDENTE','EM_ANALISE','VERIFICADO','DESCARTADO','NECESSITA_CONFIRMACAO')),
            observacoes TEXT NOT NULL,data_utc TEXT NOT NULL,anterior_uid TEXT,
            FOREIGN KEY(exe_uid,evt_uid) REFERENCES EVENTOS_FRONTEIRAS(EXE_UID,EVT_UID),
            FOREIGN KEY(anterior_uid) REFERENCES REVISOES_OCORRENCIAS(rev_uid))''')
        con.execute('CREATE INDEX revisao_ocorrencia ON REVISOES_OCORRENCIAS(exe_uid,evt_uid)')
        for acao in ('UPDATE','DELETE'):
            con.execute(f"CREATE TRIGGER ocorrencias_imutaveis_{acao} BEFORE {acao} ON REVISOES_OCORRENCIAS BEGIN SELECT RAISE(ABORT,'Histórico imutável; acrescente uma revisão'); END")
        for nome in (TABELA,'REVISOES_OCORRENCIAS_SCHEMA'):
            con.execute("INSERT INTO gpkg_contents(table_name,data_type,identifier) VALUES(?,'attributes',?)", (nome,nome))


def historico(base, exe, evento=None):
    with abrir_ro(base) as con:
        if not existe(con): return []
        con.row_factory = __import__('sqlite3').Row
        sql = 'SELECT * FROM REVISOES_OCORRENCIAS WHERE exe_uid=?'
        args = [exe]
        if evento is not None: sql += ' AND evt_uid=?'; args.append(evento)
        return [dict(r) for r in con.execute(sql + ' ORDER BY rowid', args)]


def atuais(base, exe):
    return {r['evt_uid']: r for r in historico(base, exe)}


def salvar(base, exe, evento, situacao, observacoes='', esperada=None):
    if situacao not in SITUACOES: raise ValueError('Situação inválida.')
    with abrir_ro(base) as con:
        if not con.execute('SELECT 1 FROM EVENTOS_FRONTEIRAS WHERE EXE_UID=? AND EVT_UID=?',(exe,evento)).fetchone():
            raise ValueError('Ocorrência não pertence à execução selecionada.')
    preparar(base, exe)
    with conectar(base) as con:
        con.execute('BEGIN IMMEDIATE')
        anterior = con.execute('SELECT rev_uid FROM REVISOES_OCORRENCIAS WHERE exe_uid=? AND evt_uid=? ORDER BY rowid DESC LIMIT 1',(exe,evento)).fetchone()
        anterior = anterior[0] if anterior else None
        if anterior != esperada: raise ValueError('Revisão alterada por outra sessão; recarregue antes de salvar.')
        r = dict(rev_uid=uuid4().hex, exe_uid=exe, evt_uid=evento, situacao=situacao,
                 observacoes=observacoes, data_utc=datetime.now(timezone.utc).isoformat(timespec='microseconds'), anterior_uid=anterior)
        con.execute('INSERT INTO REVISOES_OCORRENCIAS VALUES(?,?,?,?,?,?,?)',tuple(r.values()))
        return r
