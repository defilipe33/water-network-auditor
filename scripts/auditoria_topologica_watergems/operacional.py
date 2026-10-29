"""Resultados investigativos no mesmo GPKG/IGD; evolução aditiva e histórico imutável."""
from pathlib import Path
from uuid import uuid4
import json,sqlite3
from . import decisoes as db
from .filtros import ContextoFiltros
RESULTADOS=('PENDENTE','CONFIGURAÇÃO APARENTEMENTE ADEQUADA','MANTER CONFIGURAÇÃO ATUAL','CORREÇÃO NECESSÁRIA','NECESSITA INVESTIGAÇÃO ADICIONAL','NÃO SE APLICA')
MOTIVOS=('Separação intencional entre setores','Separação intencional por limite de VRP','Ponta seca prevista','Configuração adequada','Conexão existente correta','Conexão ausente','Conexão indevida','Inconsistência cadastral','Dispositivo associado incorretamente','Necessita informação operacional','Necessita conferência de campo','Outro')
PRIORIDADES=('Alta','Média','Baixa')
ESTADOS=('PENDENTE','EM ANÁLISE','ANALISADO — MANTER CONFIGURAÇÃO','ANALISADO — CORREÇÃO NECESSÁRIA','NECESSITA CONFERÊNCIA','NÃO SE APLICA')

def sugerir(caso,contexto=None):
    if caso.get('tipo')=='ILHA':return caso['prioridade'],caso['motivo_prioridade']
    if contexto and caso['local_uid']:
        for area in contexto.locais.get(caso['local_uid'],{}):
            if contexto.relacao(caso,area,'REGIOES_DIFERENTES') is True:
                return 'Alta','Transição geométrica inequívoca entre regiões cadastradas; útil à delimitação. Não comprova conexão indevida.'
        if contexto.locais.get(caso['local_uid']):return 'Média','Relação comprovada com limite: conferir separação intencional antes de propor ligação.'
    if 'REFERENCIA' in caso['categorias']:return 'Alta','Referência incompleta dificulta interpretar a topologia cadastrada; não comprova defeito hidráulico.'
    if any(c in caso['categorias'] for c in ('DISPOSITIVO','GIS_INCONSISTENTE','REGIOES')):return 'Média','Dispositivo, comunicação regional ou divergência cadastral exige investigação contextual.'
    if 'AUSENTE' in caso['categorias']:return 'Média','Proximidade e separação no grafo são indícios; podem representar pontas secas intencionais.'
    return ('Baixa','Componente isolado/pequeno sem evidência adicional de necessidade de intervenção.') if 'PEQUENO' in caso['categorias'] else ('Média','Triagem investigativa; dados insuficientes para elevar a prioridade.')

def estado(h):
    if not h:return 'PENDENTE'
    r=h.get('resultado')
    if r in RESULTADOS[1:3]:return ESTADOS[2]
    if r==RESULTADOS[3]:return ESTADOS[3]
    if r==RESULTADOS[4]:return ESTADOS[4]
    if r==RESULTADOS[5]:return ESTADOS[5]
    return 'EM ANÁLISE' if h.get('observacao') or h.get('motivo') else 'PENDENTE'

def pendente(h):return estado(h) in ESTADOS[:2]+(ESTADOS[4],)

def preparar(base,pacote):
    db.preparar_base(base,pacote)
    with db.abrir_ro(base) as c:
        if c.execute("select 1 from sqlite_master where name='IGD_OPERACIONAL_SCHEMA'").fetchone():
            if c.execute('select versao from IGD_OPERACIONAL_SCHEMA').fetchone()[0]!=1:raise ValueError('Extensão investigativa não suportada')
            return
    backup=Path(base).with_name(Path(base).stem+'_antes_operacional_'+uuid4().hex[:12]+'.gpkg')
    db.exportar_gpkg(backup,pacote['dossie'],base_origem=base)
    with db.abrir_ro(backup) as c:
        if c.execute('pragma integrity_check').fetchone()[0]!='ok' or c.execute('pragma foreign_key_check').fetchall():raise ValueError('Backup não íntegro; nenhuma migração aplicada')
    with db.conectar(base) as c:
        c.execute('BEGIN IMMEDIATE')
        ddls={
        'IGD_OPERACIONAL_SCHEMA':'versao INTEGER PRIMARY KEY,backup TEXT NOT NULL,data_utc TEXT NOT NULL',
        'IGD_ANALISES':'''uid TEXT PRIMARY KEY,ig_uid TEXT NOT NULL,occ_uid TEXT NOT NULL,modo TEXT NOT NULL,anterior TEXT REFERENCES IGD_ANALISES(uid),resultado TEXT NOT NULL,motivo TEXT NOT NULL,observacao TEXT NOT NULL,prioridade_auto TEXT NOT NULL,criterio_auto TEXT NOT NULL,prioridade_trabalho TEXT,assinatura TEXT NOT NULL,topo_uid TEXT NOT NULL,cenario TEXT NOT NULL,data_utc TEXT NOT NULL,metadados TEXT NOT NULL,FOREIGN KEY(ig_uid,occ_uid,modo) REFERENCES IGD_OCORRENCIAS(ig_uid,occ_uid,modo)''',
        'IGD_FILTROS':'''uid TEXT PRIMARY KEY,ig_uid TEXT NOT NULL REFERENCES IG_EXECUCOES(ig_uid),modo TEXT NOT NULL,nome TEXT NOT NULL,anterior TEXT REFERENCES IGD_FILTROS(uid),dados TEXT NOT NULL,topo_uid TEXT NOT NULL,data_utc TEXT NOT NULL''',
        'IGD_AREAS_FILTRO':'''ig_uid TEXT NOT NULL REFERENCES IG_EXECUCOES(ig_uid),area_uid TEXT NOT NULL,origem TEXT NOT NULL,camada TEXT NOT NULL,tipo TEXT,exe_origem TEXT NOT NULL,crs TEXT NOT NULL,geometria_wkb TEXT,dados TEXT NOT NULL,PRIMARY KEY(ig_uid,area_uid)''',
        'IGD_GEOMETRIAS_FILTRO':'''ig_uid TEXT NOT NULL,area_uid TEXT NOT NULL,assinatura TEXT NOT NULL,crs TEXT NOT NULL,wkb TEXT NOT NULL,dados TEXT NOT NULL,PRIMARY KEY(ig_uid,area_uid,assinatura),FOREIGN KEY(ig_uid,area_uid) REFERENCES IGD_AREAS_FILTRO(ig_uid,area_uid)''',
        'IGD_RELACOES_AREA':'''ig_uid TEXT NOT NULL,rel_uid TEXT NOT NULL,local_uid TEXT NOT NULL,area_uid TEXT NOT NULL,evento_uid TEXT,relacao TEXT NOT NULL,origem TEXT NOT NULL,dados TEXT NOT NULL,PRIMARY KEY(ig_uid,rel_uid),FOREIGN KEY(ig_uid,area_uid) REFERENCES IGD_AREAS_FILTRO(ig_uid,area_uid),FOREIGN KEY(ig_uid,local_uid) REFERENCES IG_LOCAIS(ig_uid,loc_uid)'''}
        for tabela,ddl in ddls.items():
            c.execute('CREATE TABLE IF NOT EXISTS '+tabela+'('+ddl+')');c.execute("INSERT OR IGNORE INTO gpkg_contents(table_name,data_type,identifier) VALUES(?,'attributes',?)",(tabela,tabela))
            for acao in ('UPDATE','DELETE'):c.execute(f"CREATE TRIGGER IF NOT EXISTS {tabela}_{acao}_imutavel BEFORE {acao} ON {tabela} BEGIN SELECT RAISE(ABORT,'Histórico imutável; acrescente registro'); END")
        c.execute('INSERT OR IGNORE INTO IGD_OPERACIONAL_SCHEMA VALUES(1,?,?)',(str(backup),db.agora()))
        c.execute('CREATE INDEX IF NOT EXISTS igd_analises_contexto ON IGD_ANALISES(ig_uid,modo,occ_uid)')
        c.execute('CREATE INDEX IF NOT EXISTS igd_filtros_contexto ON IGD_FILTROS(ig_uid,modo,nome)')
        c.execute('CREATE INDEX IF NOT EXISTS igd_relacoes_local ON IGD_RELACOES_AREA(ig_uid,local_uid,area_uid,relacao)')

def historico(base,ig,occ=None,modo=None):
    with db.abrir_ro(base) as c:
        if not c.execute("select 1 from sqlite_master where name='IGD_ANALISES'").fetchone():return []
        c.row_factory=sqlite3.Row;sql='SELECT * FROM IGD_ANALISES WHERE ig_uid=?';params=[ig]
        if occ is not None:sql+=' AND occ_uid=?';params.append(occ)
        if modo is not None:sql+=' AND modo=?';params.append(modo)
        return [dict(r) for r in c.execute(sql+' ORDER BY rowid',params)]

def indice(base,ig):return {(r['occ_uid'],r['modo']):r for r in historico(base,ig)}

def persistir_relacoes(c,pacote,contexto):
    ig=pacote['resultado']['meta']['uid']
    for uid,a in contexto.areas.items():c.execute('INSERT OR IGNORE INTO IGD_AREAS_FILTRO VALUES(?,?,?,?,?,?,?,?,?)',(ig,uid,a['origem'],a['camada'],a['tipo'],a['execucao'],a['crs'],a['geometria_wkb'],db.texto(a)))
    for uid,a in contexto.areas.items():
        if a.get('geometria_wkb'):c.execute('INSERT OR IGNORE INTO IGD_GEOMETRIAS_FILTRO VALUES(?,?,?,?,?,?)',(ig,uid,db.digest([a['crs'],a['geometria_wkb']]),a['crs'],a['geometria_wkb'],db.texto(a)))
    for r in contexto.relacoes:c.execute('INSERT OR IGNORE INTO IGD_RELACOES_AREA VALUES(?,?,?,?,?,?,?,?)',(ig,db.digest(r),r['local'],r['area'],r['evento'],r['relacao'],r['origem'],db.texto(r)))

def salvar(base,pacote,caso,modo,resultado=None,motivo='',observacao='',prioridade=None,esperada=None,contexto=None):
    if modo not in db.MODOS or resultado is not None and resultado not in RESULTADOS:raise ValueError('Resultado ou perspectiva inválidos')
    if prioridade is not None and prioridade not in PRIORIDADES:raise ValueError('Prioridade de trabalho inválida')
    if resultado is None and not motivo.strip() and not observacao.strip() and prioridade is None:raise ValueError('Selecione um resultado ou escreva uma observação.')
    preparar(base,pacote);contexto=contexto or ContextoFiltros(pacote);sugestao,criterio=sugerir(caso,contexto)
    with db.conectar(base) as c:
        c.execute('BEGIN IMMEDIATE');ig=db._registrar(c,pacote,caso,modo);c.row_factory=sqlite3.Row
        h=c.execute('SELECT * FROM IGD_ANALISES WHERE ig_uid=? AND occ_uid=? AND modo=? ORDER BY rowid DESC LIMIT 1',(ig,caso['uid'],modo)).fetchone()
        if (h['uid'] if h else None)!=esperada:raise ValueError('Análise alterada em outra sessão; recarregue antes de salvar. Seus textos foram preservados.')
        assinatura=db.Contextos(pacote).assinatura(caso,modo)
        if h and h['assinatura']!=assinatura:raise ValueError('Contexto técnico alterado; nova versão requer reavaliação')
        if h:sugestao,criterio=h['prioridade_auto'],h['criterio_auto']
        r=resultado if resultado is not None else h['resultado'] if h else 'PENDENTE';uid=uuid4().hex;meta=pacote['resultado']['meta']
        c.execute('INSERT INTO IGD_ANALISES VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(uid,ig,caso['uid'],modo,esperada,r,motivo,observacao,sugestao,criterio,prioridade,assinatura,meta['topologia']['execucao_uid'],db.texto(pacote['topologia']['modelo']['cenario']),db.agora(),db.texto(dict(natureza='INTERPRETACAO_INVESTIGATIVA',comprovacao_hidraulica=False,alterou_modelo=False,regras_prioridade='triagem-2',prioridade_anterior=caso['prioridade']))))
        persistir_relacoes(c,pacote,contexto)
        return uid

def salvar_filtros(base,pacote,modo,dados,nome='Trabalho',contexto=None):
    if modo not in db.MODOS:raise ValueError('Perspectiva inválida')
    preparar(base,pacote);ig=pacote['resultado']['meta']['uid'];contexto=contexto or ContextoFiltros(pacote)
    with db.conectar(base) as c:
        c.execute('BEGIN IMMEDIATE');anterior=c.execute('SELECT uid FROM IGD_FILTROS WHERE ig_uid=? AND modo=? AND nome=? ORDER BY rowid DESC LIMIT 1',(ig,modo,nome)).fetchone();uid=uuid4().hex
        c.execute('INSERT INTO IGD_FILTROS VALUES(?,?,?,?,?,?,?,?)',(uid,ig,modo,nome,anterior[0] if anterior else None,db.texto(dados),pacote['resultado']['meta']['topologia']['execucao_uid'],db.agora()));persistir_relacoes(c,pacote,contexto);return uid

def carregar_filtros(base,pacote,modo,nome='Trabalho'):
    with db.abrir_ro(base) as c:
        if not c.execute("select 1 from sqlite_master where name='IGD_FILTROS'").fetchone():return None
        row=c.execute('SELECT dados,topo_uid FROM IGD_FILTROS WHERE ig_uid=? AND modo=? AND nome=? ORDER BY rowid DESC LIMIT 1',(pacote['resultado']['meta']['uid'],modo,nome)).fetchone()
        return json.loads(row[0]) if row and row[1]==pacote['resultado']['meta']['topologia']['execucao_uid'] else None
