"""Andamento independente do resultado técnico no mesmo GPKG integrado/IGD."""
from pathlib import Path
from uuid import uuid4
from collections import defaultdict,Counter
import json,sqlite3
from . import decisoes as db

ESTADOS=('EM_ABERTO','RESOLVIDO','REAVALIACAO_NECESSARIA')
ROTULOS={'EM_ABERTO':'EM ABERTO','RESOLVIDO':'RESOLVIDO','REAVALIACAO_NECESSARIA':'REAVALIAÇÃO NECESSÁRIA'}


class Contexto:
    def __init__(self,pacote):
        self.p=pacote;self.portas={};self.cache={}
    def assinatura(self,caso,modo):
        if modo not in db.MODOS:raise ValueError('Perspectiva indisponível')
        m=self.p['topologia']['modelo'];g=self.p['topologia']['estrutural' if modo=='ESTRUTURAL' else 'potencial']['grafo'];ids=set(caso['wg_ids'])
        if modo not in self.portas:
            ns=defaultdict(list)
            for n in g:ns[n[0]].append(n)
            self.portas[modo]=ns
        ns={n for i in ids for n in self.portas[modo].get(i,())};arestas=set()
        for n in ns:
            for a,b,d in list(g.in_edges(n,data=True))+list(g.out_edges(n,data=True)):arestas.add((a,b,d.get('elemento'),d.get('natureza')))
        ref_ids=ids|{n[0] for a,b,i,t in arestas for n in (a,b)}
        refs=[]
        for i in sorted(ref_ids):
            chave=(modo,i)
            if chave not in self.cache:
                e=m['elementos'].get(i,{})
                self.cache[chave]=db.digest({k:e.get(k) for k in ('uid','tipo','label','familia','ativo','excluido','topologia','estados','atributos','geometria')})
            refs.append((i,self.cache[chave]))
        # Não inclui UUID da versão nem todos os elementos do componente: mudanças
        # distantes sem alteração do caso não reabrem indiscriminadamente a fila.
        return db.digest(dict(regras='acomp-1',modelo=m['projeto'],cenario=m['cenario'],modo=modo,tipo=caso['tipo'],chave=ancora(caso),refs=refs,arestas=sorted(arestas,key=repr),gis=sorted(caso['gis_uids']),areas=sorted(caso['area_uids']),evidencias=caso['evidencias'],perspectiva=caso['perspectivas'][modo],manual=caso.get('manual_posicao')))


def ancora(c):
    from .comparacao_decisoes import ancora as existente
    return (*existente(c),c.get('manual_uid') if c['tipo']=='MANUAL' else '')


def historico(base,ig=None,occ=None,modo=None):
    with db.abrir_ro(base) as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='IGD_ACOMPANHAMENTO'").fetchone():return []
        c.row_factory=sqlite3.Row;where=[];params=[]
        for campo,v in [('ig_uid',ig),('occ_uid',occ),('modo',modo)]:
            if v is not None:where.append(campo+'=?');params.append(v)
        return [dict(r) for r in c.execute('SELECT * FROM IGD_ACOMPANHAMENTO'+(' WHERE '+' AND '.join(where) if where else '')+' ORDER BY rowid',params)]


def indice(base,pacote):return {(h['occ_uid'],h['modo']):h for h in historico(base,pacote['resultado']['meta']['uid'])}


def estado(h,caso,pacote,modo,contexto=None):
    if not h:return 'EM_ABERTO'
    if h['estado']=='RESOLVIDO' and h['assinatura']!=(contexto or Contexto(pacote)).assinatura(caso,modo):return 'REAVALIACAO_NECESSARIA'
    return h['estado']


def preparar(base,pacote):
    db.preparar_base(base,pacote)
    with db.abrir_ro(base) as c:
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='IGD_ACOMP_SCHEMA'").fetchone():
            if c.execute('SELECT max(versao) FROM IGD_ACOMP_SCHEMA').fetchone()[0]!=1:raise ValueError('Versão de acompanhamento não suportada')
            return
    backup=Path(base).with_name(Path(base).stem+'_antes_acompanhamento_'+uuid4().hex[:12]+'.gpkg');db.exportar_gpkg(backup,pacote['dossie'],base_origem=base)
    with db.abrir_ro(backup) as c:
        if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or c.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Backup de acompanhamento inválido; nenhuma migração aplicada')
    with db.conectar(base) as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('CREATE TABLE IF NOT EXISTS IGD_ACOMP_SCHEMA(versao INTEGER PRIMARY KEY,backup TEXT NOT NULL,data_utc TEXT NOT NULL)')
        c.execute('''CREATE TABLE IF NOT EXISTS IGD_ACOMPANHAMENTO(uid TEXT PRIMARY KEY,ig_uid TEXT NOT NULL,occ_uid TEXT NOT NULL,modo TEXT NOT NULL,anterior TEXT REFERENCES IGD_ACOMPANHAMENTO(uid),estado_anterior TEXT NOT NULL,estado TEXT NOT NULL CHECK(estado IN ('EM_ABERTO','RESOLVIDO','REAVALIACAO_NECESSARIA')),observacao TEXT NOT NULL,data_utc TEXT NOT NULL,topo_uid TEXT NOT NULL,assinatura TEXT NOT NULL,dados TEXT NOT NULL,FOREIGN KEY(ig_uid,occ_uid,modo) REFERENCES IGD_OCORRENCIAS(ig_uid,occ_uid,modo))''')
        c.execute('INSERT OR IGNORE INTO IGD_ACOMP_SCHEMA VALUES(1,?,?)',(str(backup),db.agora()))
        for tabela in ('IGD_ACOMP_SCHEMA','IGD_ACOMPANHAMENTO'):
            c.execute("INSERT OR IGNORE INTO gpkg_contents(table_name,data_type,identifier) VALUES(?,'attributes',?)",(tabela,tabela))
            for acao in ('UPDATE','DELETE'):c.execute(f"CREATE TRIGGER IF NOT EXISTS {tabela}_{acao}_imutavel BEFORE {acao} ON {tabela} BEGIN SELECT RAISE(ABORT,'Histórico imutável'); END")
        c.execute('CREATE INDEX IF NOT EXISTS igd_acomp_contexto ON IGD_ACOMPANHAMENTO(ig_uid,modo,occ_uid)')


def salvar(base,pacote,caso,modo,novo,observacao='',esperada=None,origem=None):
    if modo not in db.MODOS or novo not in ESTADOS:raise ValueError('Situação ou perspectiva inválida')
    assinatura=Contexto(pacote).assinatura(caso,modo);preparar(base,pacote);uid=uuid4().hex;meta=pacote['resultado']['meta']
    with db.conectar(base) as c:
        c.execute('BEGIN IMMEDIATE');ig=db._registrar(c,pacote,caso,modo);c.row_factory=sqlite3.Row
        h=c.execute('SELECT * FROM IGD_ACOMPANHAMENTO WHERE ig_uid=? AND occ_uid=? AND modo=? ORDER BY rowid DESC LIMIT 1',(ig,caso['uid'],modo)).fetchone()
        if (h['uid'] if h else None)!=esperada:raise ValueError('Situação alterada em outra sessão; recarregue antes de salvar.')
        anterior=estado(dict(h),caso,pacote,modo) if h else 'EM_ABERTO'
        c.execute('INSERT INTO IGD_ACOMPANHAMENTO VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(uid,ig,caso['uid'],modo,esperada,anterior,novo,observacao,db.agora(),meta['topologia']['execucao_uid'],assinatura,db.texto(dict(cenario=pacote['topologia']['modelo']['cenario'],origem=origem,sem_escrita_watergems=True,natureza='ACOMPANHAMENTO_NAO_COMPROVACAO_HIDRAULICA'))))
    return uid


def comparar(base_antigo,antigo,casos_antigos,novo,casos_novos,modo):
    heads=indice(base_antigo,antigo);ca,cb=Contexto(antigo),Contexto(novo);por_ancora=defaultdict(list)
    for c in casos_novos:por_ancora[ancora(c)].append(c)
    linhas=[]
    for c in casos_antigos:
        h=heads.get((c['uid'],modo))
        if not h or estado(h,c,antigo,modo,ca)!='RESOLVIDO':continue
        candidatos=por_ancora[ancora(c)];igual=len(candidatos)==1 and ca.assinatura(c,modo)==cb.assinatura(candidatos[0],modo)
        linhas.append(dict(ig_origem=antigo['resultado']['meta']['uid'],base_origem=str(Path(base_antigo).resolve()),origem=c['uid'],registro=h['uid'],destinos=[n['uid'] for n in candidatos],classe='EQUIVALENTE' if igual else 'REAVALIACAO_NECESSARIA' if len(candidatos)==1 else 'CORRESPONDENCIA_INCERTA',observacao=h['observacao'],topo_origem=h['topo_uid']))
    return dict(linhas=linhas,contagens=dict(Counter(l['classe'] for l in linhas)))


def aplicar_comparacao(base,pacote,casos,modo,resultado):
    mapa={c['uid']:c for c in casos};heads=indice(base,pacote)
    for r in resultado['linhas']:
        if len(r['destinos'])!=1:continue
        uid=r['destinos'][0]
        if uid not in mapa or (uid,modo) in heads:continue  # nunca sobrescreve trabalho novo
        salvar(base,pacote,mapa[uid],modo,'RESOLVIDO' if r['classe']=='EQUIVALENTE' else 'REAVALIACAO_NECESSARIA',observacao=r['observacao'],origem=r)
