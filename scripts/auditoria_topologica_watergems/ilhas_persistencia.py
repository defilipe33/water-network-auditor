"""Resultados de ilhas na mesma base IGD; decisões usam as revisões já existentes."""
import json,sqlite3
from pathlib import Path
from uuid import uuid4
from . import decisoes as db


def preparar(base,p):
    db.preparar_base(base,p)
    with db.abrir_ro(base) as c:
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='IGD_ILHAS_SCHEMA'").fetchone():
            if c.execute('SELECT max(versao) FROM IGD_ILHAS_SCHEMA').fetchone()[0]!=1:raise ValueError('Esquema de ilhas não suportado')
            return
    backup=Path(base).with_name(Path(base).stem+'_antes_ilhas_'+uuid4().hex[:12]+'.gpkg');db.exportar_gpkg(backup,p['dossie'],base_origem=base)
    with db.abrir_ro(backup) as c:
        if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or c.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Backup não íntegro; base anterior preservada')
    with db.conectar(base) as c:
        c.execute('BEGIN IMMEDIATE')
        tabelas={
            'IGD_ILHAS_SCHEMA':'versao INTEGER PRIMARY KEY,backup TEXT NOT NULL,data_utc TEXT NOT NULL',
            'IGD_ILHAS_ANALISES':'uid TEXT PRIMARY KEY,ig_uid TEXT NOT NULL REFERENCES IG_EXECUCOES(ig_uid),topo_uid TEXT NOT NULL,assinatura TEXT NOT NULL,nome TEXT NOT NULL,data_utc TEXT NOT NULL,dados TEXT NOT NULL,UNIQUE(ig_uid,assinatura)',
            'IGD_ILHAS':'analise_uid TEXT NOT NULL REFERENCES IGD_ILHAS_ANALISES(uid),ilha_uid TEXT NOT NULL,dados TEXT NOT NULL,PRIMARY KEY(analise_uid,ilha_uid)',
            'IGD_ILHAS_MEMBROS':'analise_uid TEXT NOT NULL,ilha_uid TEXT NOT NULL,origem TEXT NOT NULL,chave TEXT NOT NULL,papel TEXT NOT NULL,dados TEXT NOT NULL,PRIMARY KEY(analise_uid,ilha_uid,origem,chave,papel),FOREIGN KEY(analise_uid,ilha_uid) REFERENCES IGD_ILHAS(analise_uid,ilha_uid)',
            'IGD_ILHAS_ATIVAS':'uid TEXT PRIMARY KEY,ig_uid TEXT NOT NULL REFERENCES IG_EXECUCOES(ig_uid),analise_uid TEXT NOT NULL REFERENCES IGD_ILHAS_ANALISES(uid),data_utc TEXT NOT NULL'}
        for t,ddl in tabelas.items():
            c.execute(f'CREATE TABLE IF NOT EXISTS {t}({ddl})');c.execute("INSERT OR IGNORE INTO gpkg_contents(table_name,data_type,identifier) VALUES(?,'attributes',?)",(t,t))
            for op in ('UPDATE','DELETE'):c.execute(f"CREATE TRIGGER IF NOT EXISTS {t}_{op}_imutavel BEFORE {op} ON {t} BEGIN SELECT RAISE(ABORT,'Histórico imutável'); END")
        c.execute('CREATE INDEX IF NOT EXISTS igd_ilhas_contexto ON IGD_ILHAS_ANALISES(ig_uid,topo_uid,assinatura)');c.execute('CREATE INDEX IF NOT EXISTS igd_ilhas_membro ON IGD_ILHAS_MEMBROS(analise_uid,origem,chave)');c.execute('INSERT OR IGNORE INTO IGD_ILHAS_SCHEMA VALUES(1,?,?)',(str(backup),db.agora()))


def listar(base,p):
    with db.abrir_ro(base) as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='IGD_ILHAS_ANALISES'").fetchone():return []
        c.row_factory=sqlite3.Row
        return [dict(r) for r in c.execute('SELECT uid,nome,topo_uid,assinatura,data_utc FROM IGD_ILHAS_ANALISES WHERE ig_uid=? ORDER BY rowid DESC',(p['resultado']['meta']['uid'],))]


def carregar(base,p,uid=None,assinatura=None):
    with db.abrir_ro(base) as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='IGD_ILHAS_ANALISES'").fetchone():return None
        ig=p['resultado']['meta']['uid'];topo=p['resultado']['meta']['topologia']['execucao_uid']
        if assinatura:row=c.execute('SELECT uid,dados FROM IGD_ILHAS_ANALISES WHERE ig_uid=? AND topo_uid=? AND assinatura=?',(ig,topo,assinatura)).fetchone()
        else:
            if uid is None:
                v=c.execute('SELECT analise_uid FROM IGD_ILHAS_ATIVAS WHERE ig_uid=? ORDER BY rowid DESC LIMIT 1',(ig,)).fetchone();uid=v[0] if v else None
            row=c.execute('SELECT uid,dados FROM IGD_ILHAS_ANALISES WHERE ig_uid=? AND topo_uid=? AND uid=?',(ig,topo,uid)).fetchone()
        if not row:return None
        r=json.loads(row[1]);r['uid']=row[0];r['ilhas']=[]
        for u,d in c.execute('SELECT ilha_uid,dados FROM IGD_ILHAS WHERE analise_uid=? ORDER BY ilha_uid',(row[0],)):
            v=json.loads(d);v['membros']=[int(m[0]) for m in c.execute("SELECT chave FROM IGD_ILHAS_MEMBROS WHERE analise_uid=? AND ilha_uid=? AND origem='WG' ORDER BY CAST(chave AS INTEGER)",(row[0],u))];r['ilhas'].append(v)
        return r


def ativar(base,p,uid):
    with db.conectar(base) as c:
        c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT ig_uid,topo_uid FROM IGD_ILHAS_ANALISES WHERE uid=?',(uid,)).fetchone()
        if not row or tuple(row)!=(p['resultado']['meta']['uid'],p['resultado']['meta']['topologia']['execucao_uid']):raise ValueError('Análise pertence a outra execução/versão')
        c.execute('INSERT INTO IGD_ILHAS_ATIVAS VALUES(?,?,?,?)',(uuid4().hex,row[0],uid,db.agora()))


def salvar(base,p,r,nome='Ilhas sem origem',cancelado=None):
    preparar(base,p);ig=p['resultado']['meta']['uid'];topo=p['resultado']['meta']['topologia']['execucao_uid'];uid=uuid4().hex
    with db.conectar(base) as c:
        c.execute('BEGIN IMMEDIATE');anterior=c.execute('SELECT uid FROM IGD_ILHAS_ANALISES WHERE ig_uid=? AND assinatura=?',(ig,r['assinatura'])).fetchone()
        if anterior:uid=anterior[0]
        else:
            c.execute('INSERT INTO IGD_ILHAS_ANALISES VALUES(?,?,?,?,?,?,?)',(uid,ig,topo,r['assinatura'],nome,db.agora(),db.texto({k:v for k,v in r.items() if k not in ('ilhas','uid')})))
            for v in r['ilhas']:
                if cancelado and cancelado():raise InterruptedError('Gravação de ilhas cancelada; transação revertida')
                c.execute('INSERT INTO IGD_ILHAS VALUES(?,?,?)',(uid,v['uid'],db.texto({k:d for k,d in v.items() if k!='membros'})))
                for i in v['membros']:
                    e=p['topologia']['modelo']['elementos'][i];c.execute('INSERT INTO IGD_ILHAS_MEMBROS VALUES(?,?,?,?,?,?)',(uid,v['uid'],'WG',str(i),e['familia'],db.texto(dict(uid=e['uid'],tipo=e['tipo'],label=e.get('label')))))
                for origem,k in [('GIS','gis'),('AREA','areas'),('LOCAL','locais')]:
                    for i in v[k]:c.execute('INSERT INTO IGD_ILHAS_MEMBROS VALUES(?,?,?,?,?,?)',(uid,v['uid'],origem,i,'RELACAO_PERSISTIDA','{}'))
        c.execute('INSERT INTO IGD_ILHAS_ATIVAS VALUES(?,?,?,?)',(uuid4().hex,ig,uid,db.agora()))
    return carregar(base,p,uid)


def casos_ativos(base,p):
    from .ilhas import casos
    r=carregar(base,p)
    return casos(p,r) if r else []


def resumo_ativo(base,p):
    with db.abrir_ro(base) as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='IGD_ILHAS_ATIVAS'").fetchone():return None
        r=c.execute('SELECT a.dados FROM IGD_ILHAS_ANALISES a JOIN IGD_ILHAS_ATIVAS v ON v.analise_uid=a.uid WHERE v.ig_uid=? AND a.topo_uid=? ORDER BY v.rowid DESC LIMIT 1',(p['resultado']['meta']['uid'],p['resultado']['meta']['topologia']['execucao_uid'])).fetchone()
        return json.loads(r[0]) if r else None
