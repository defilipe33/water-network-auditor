"""Extensão transacional do GPKG integrado; histórico anexado, nunca WaterGEMS."""
from collections import defaultdict
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from uuid import uuid4
from auditoria_fronteiras.persistencia import conectar,SITUACOES,exportar_gpkg
from auditoria_fronteiras.versoes import abrir_ro
from auditoria_fronteiras.inspecao import texto
from .diagnosticos import MODOS

CONCLUSOES=('NÃO AVALIADO','CONECTIVIDADE CORRETA','DESCONEXÃO INTENCIONAL',
    'CONEXÃO FALTANTE CONFIRMADA','CONEXÃO INDEVIDA CONFIRMADA','PROBLEMA CADASTRAL CONFIRMADO',
    'NECESSITA CONFIRMAÇÃO CADASTRAL','NECESSITA CONFIRMAÇÃO OPERACIONAL','NECESSITA VERIFICAÇÃO DE CAMPO','NÃO APLICÁVEL')
FONTES=('Análise do cadastro GIS','Análise do WaterGEMS','Projeto ou desenho técnico','Informação operacional','Verificação de campo','Outra fonte identificada')
NATUREZAS=('INDEFINIDO','DOCUMENTAL','OPERACIONAL','CAMPO','HIPOTESE')
TIPOS_PROPOSTA=('Conectar dois nós','Corrigir vínculo Start/Stop Node','Verificar ou eliminar nó duplicado',
    'Dividir tubulação para inserir conexão','Remover conexão indevida','Corrigir vínculo de válvula',
    'Corrigir vínculo de bomba','Alterar topologia ativa','Corrigir correspondência cadastral GIS × WaterGEMS','Outra intervenção')
ESTADOS_PROPOSTA=('RASCUNHO','AGUARDANDO_CONFIRMACAO','PROPOSTA_PARA_APROVACAO','APROVADA','REJEITADA',
    'APLICACAO_INFORMADA','VALIDACAO_PENDENTE','VALIDADA','VALIDACAO_FALHOU')
TRANSICOES={
    'RASCUNHO':{'RASCUNHO','AGUARDANDO_CONFIRMACAO','PROPOSTA_PARA_APROVACAO','REJEITADA'},
    'AGUARDANDO_CONFIRMACAO':{'RASCUNHO','AGUARDANDO_CONFIRMACAO','PROPOSTA_PARA_APROVACAO','REJEITADA'},
    'PROPOSTA_PARA_APROVACAO':{'PROPOSTA_PARA_APROVACAO','RASCUNHO','APROVADA','REJEITADA'},
    'APROVADA':{'APROVADA','REJEITADA','APLICACAO_INFORMADA'},
    'REJEITADA':{'REJEITADA','RASCUNHO'},
    'APLICACAO_INFORMADA':{'APLICACAO_INFORMADA','VALIDACAO_PENDENTE'},
    'VALIDACAO_PENDENTE':{'VALIDACAO_PENDENTE','VALIDADA','VALIDACAO_FALHOU'},
    'VALIDADA':{'VALIDADA','VALIDACAO_PENDENTE'},'VALIDACAO_FALHOU':{'VALIDACAO_FALHOU','RASCUNHO','VALIDACAO_PENDENTE'}}


def agora():return datetime.now(timezone.utc).isoformat(timespec='microseconds')
def digest(v):return sha256(texto(v).encode()).hexdigest()
def existe(con):return bool(con.execute("SELECT 1 FROM sqlite_master WHERE name='IGD_SCHEMA'").fetchone())


class Contextos:
    def __init__(self,pacote):
        self.p=pacote;self.m=pacote['topologia']['modelo'];self.cache={}
        self.cs={modo:{c['uid']:c for c in pacote['resultado']['componentes' if modo==MODOS[0] else 'componentes_potenciais']} for modo in MODOS}
    def assinatura(self,caso,modo):
        if modo not in MODOS:raise ValueError('Perspectiva não validada')
        elementos=self.m['elementos'];componentes=[]
        def ref(i):
            e=elementos[i]
            return {k:e.get(k) for k in ('uid','label','tipo','familia','ativo','excluido','topologia','alternativas','estados','geometria')}
        for u in caso['componentes'][modo]:
            chave=(modo,u)
            if chave not in self.cache:
                c=self.cs[modo][u];self.cache[chave]=digest([ref(i) for i in sorted(set(c['nos']+c['tubos']))])
            componentes.append(self.cache[chave])
        contexto=dict(projeto=self.m['projeto'],cenario=self.m['cenario'],alternativas=self.m.get('alternativas',{}),
            modo=modo,elementos=[ref(i) for i in caso['wg_ids']],componentes=sorted(componentes),
            gis=caso['gis_uids'],evidencias=caso['evidencias'],perspectiva=caso['perspectivas'][modo],areas=caso['area_uids'])
        return digest(contexto)


def preparar_base(base,pacote):
    """Extensão aditiva autorizada ao salvar; backup completo antes da primeira extensão."""
    with abrir_ro(base) as con:
        if not con.execute('SELECT 1 FROM IG_EXECUCOES WHERE ig_uid=?',(pacote['resultado']['meta']['uid'],)).fetchone():raise ValueError('Execução não pertence à base selecionada')
        if existe(con):
            if con.execute('SELECT versao FROM IGD_SCHEMA').fetchone()[0]!=1:raise ValueError('Versão de decisões não suportada')
            return
    backup=Path(base).with_name(Path(base).stem+'_antes_decisoes_'+uuid4().hex[:12]+'.gpkg')
    exportar_gpkg(backup,pacote['dossie'],base_origem=base)
    with abrir_ro(backup) as con:
        if con.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or con.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Backup não íntegro; extensão não aplicada')
    with conectar(base) as con:
        con.execute('BEGIN IMMEDIATE')
        for ddl in (
            'CREATE TABLE IF NOT EXISTS IGD_SCHEMA(versao INTEGER PRIMARY KEY,backup TEXT NOT NULL,data_utc TEXT NOT NULL)',
            '''CREATE TABLE IF NOT EXISTS IGD_OCORRENCIAS(ig_uid TEXT NOT NULL REFERENCES IG_EXECUCOES(ig_uid),occ_uid TEXT NOT NULL,modo TEXT NOT NULL,assinatura TEXT NOT NULL,tipo TEXT NOT NULL,chave TEXT NOT NULL,titulo TEXT NOT NULL,dados TEXT NOT NULL,PRIMARY KEY(ig_uid,occ_uid,modo))''',
            '''CREATE TABLE IF NOT EXISTS IGD_REVISOES(rev_uid TEXT PRIMARY KEY,ig_uid TEXT NOT NULL,occ_uid TEXT NOT NULL,modo TEXT NOT NULL,anterior TEXT REFERENCES IGD_REVISOES(rev_uid),situacao_anterior TEXT,situacao TEXT NOT NULL,conclusao TEXT NOT NULL,justificativa TEXT NOT NULL,responsavel TEXT NOT NULL,data_utc TEXT NOT NULL,fonte TEXT NOT NULL,natureza TEXT NOT NULL,evidencia TEXT NOT NULL,FOREIGN KEY(ig_uid,occ_uid,modo) REFERENCES IGD_OCORRENCIAS(ig_uid,occ_uid,modo))''',
            '''CREATE TABLE IF NOT EXISTS IGD_PROPOSTAS(prop_uid TEXT PRIMARY KEY,ig_uid TEXT NOT NULL,occ_uid TEXT NOT NULL,modo TEXT NOT NULL,data_utc TEXT NOT NULL,FOREIGN KEY(ig_uid,occ_uid,modo) REFERENCES IGD_OCORRENCIAS(ig_uid,occ_uid,modo))''',
            '''CREATE TABLE IF NOT EXISTS IGD_PROP_HIST(hist_uid TEXT PRIMARY KEY,prop_uid TEXT NOT NULL REFERENCES IGD_PROPOSTAS(prop_uid),anterior TEXT REFERENCES IGD_PROP_HIST(hist_uid),situacao_anterior TEXT,situacao TEXT NOT NULL,tipo TEXT NOT NULL,descricao TEXT NOT NULL,justificativa TEXT NOT NULL,requisitos TEXT NOT NULL,responsavel TEXT NOT NULL,data_utc TEXT NOT NULL,evidencia TEXT NOT NULL,incompleta INTEGER NOT NULL,elementos_confirmados INTEGER NOT NULL,confirmacao INTEGER NOT NULL,validacao_uid TEXT REFERENCES IGD_VALIDACOES(val_uid),validacao_manual INTEGER NOT NULL)''',
            '''CREATE TABLE IF NOT EXISTS IGD_PROP_ELEMENTOS(hist_uid TEXT NOT NULL REFERENCES IGD_PROP_HIST(hist_uid),ordem INTEGER NOT NULL,projeto TEXT NOT NULL,wg_id TEXT NOT NULL,label TEXT NOT NULL,tipo TEXT NOT NULL,PRIMARY KEY(hist_uid,ordem))''',
            '''CREATE TABLE IF NOT EXISTS IGD_COMPARACOES(comp_uid TEXT PRIMARY KEY,ig_origem TEXT NOT NULL,ig_destino TEXT NOT NULL REFERENCES IG_EXECUCOES(ig_uid),data_utc TEXT NOT NULL,dados TEXT NOT NULL)''',
            '''CREATE TABLE IF NOT EXISTS IGD_CORRESPONDENCIAS(comp_uid TEXT NOT NULL REFERENCES IGD_COMPARACOES(comp_uid),ordem INTEGER NOT NULL,occ_origem TEXT,occ_destino TEXT,classe TEXT NOT NULL,reavaliar INTEGER NOT NULL,dados TEXT NOT NULL,PRIMARY KEY(comp_uid,ordem))''',
            '''CREATE TABLE IF NOT EXISTS IGD_VALIDACOES(val_uid TEXT PRIMARY KEY,prop_uid TEXT NOT NULL REFERENCES IGD_PROPOSTAS(prop_uid),hist_uid TEXT NOT NULL REFERENCES IGD_PROP_HIST(hist_uid),ig_destino TEXT NOT NULL,data_utc TEXT NOT NULL,dados TEXT NOT NULL)''',
            '''CREATE TABLE IF NOT EXISTS IGD_RECONCILIACOES(rec_uid TEXT PRIMARY KEY,comp_uid TEXT NOT NULL,ordem INTEGER NOT NULL,occ_destino TEXT NOT NULL,rev_uid TEXT NOT NULL REFERENCES IGD_REVISOES(rev_uid),responsavel TEXT NOT NULL,justificativa TEXT NOT NULL,evidencia TEXT NOT NULL,data_utc TEXT NOT NULL,FOREIGN KEY(comp_uid,ordem) REFERENCES IGD_CORRESPONDENCIAS(comp_uid,ordem))'''):
            con.execute(ddl)
        con.execute('INSERT OR IGNORE INTO IGD_SCHEMA VALUES(1,?,?)',(str(backup),agora()))
        for tabela in ('IGD_SCHEMA','IGD_OCORRENCIAS','IGD_REVISOES','IGD_PROPOSTAS','IGD_PROP_HIST','IGD_PROP_ELEMENTOS','IGD_COMPARACOES','IGD_CORRESPONDENCIAS','IGD_VALIDACOES','IGD_RECONCILIACOES'):
            con.execute("INSERT OR IGNORE INTO gpkg_contents(table_name,data_type,identifier) VALUES(?,'attributes',?)",(tabela,tabela))
            for acao in ('UPDATE','DELETE'):
                con.execute(f"CREATE TRIGGER IF NOT EXISTS {tabela}_{acao}_imutavel BEFORE {acao} ON {tabela} BEGIN SELECT RAISE(ABORT,'Histórico imutável; acrescente registro'); END")
        con.execute('CREATE INDEX IF NOT EXISTS igd_revisoes_contexto ON IGD_REVISOES(ig_uid,occ_uid,modo)')
        con.execute('CREATE INDEX IF NOT EXISTS igd_propostas_contexto ON IGD_PROPOSTAS(ig_uid,occ_uid,modo)')


def _registrar(con,pacote,caso,modo):
    ig=pacote['resultado']['meta']['uid'];assinatura=Contextos(pacote).assinatura(caso,modo)
    atual=con.execute('SELECT assinatura FROM IGD_OCORRENCIAS WHERE ig_uid=? AND occ_uid=? AND modo=?',(ig,caso['uid'],modo)).fetchone()
    if atual and atual[0]!=assinatura:raise ValueError('Contexto técnico mudou; crie nova execução e reavalie a decisão')
    con.execute('INSERT OR IGNORE INTO IGD_OCORRENCIAS VALUES(?,?,?,?,?,?,?,?)',(ig,caso['uid'],modo,assinatura,caso['tipo'],caso['chave'],caso['titulo'],texto(caso)))
    return ig


def historico(base,ig,occ,modo):
    with abrir_ro(base) as con:
        if not existe(con):return []
        con.row_factory=sqlite3.Row
        return [dict(r) for r in con.execute('SELECT * FROM IGD_REVISOES WHERE ig_uid=? AND occ_uid=? AND modo=? ORDER BY rowid',(ig,occ,modo))]


def salvar_decisao(base,pacote,caso,modo,situacao='PENDENTE',conclusao='NÃO AVALIADO',justificativa='',responsavel='',fonte='',natureza='INDEFINIDO',evidencia='',esperada=None):
    if modo not in MODOS:raise ValueError('Perspectiva não validada')
    if situacao not in SITUACOES or conclusao not in CONCLUSOES or natureza not in NATUREZAS or (fonte and fonte not in FONTES):raise ValueError('Opção de revisão inválida')
    definitiva=conclusao in CONCLUSOES[1:6] or conclusao=='NÃO APLICÁVEL'
    if definitiva and not all(str(v).strip() for v in (justificativa,responsavel,fonte,evidencia)):raise ValueError('Conclusão definitiva exige justificativa, responsável, fonte e evidência identificada')
    if definitiva and natureza in ('INDEFINIDO','HIPOTESE'):raise ValueError('Hipótese ou fonte indefinida não comprova conclusão definitiva')
    preparar_base(base,pacote)
    with conectar(base) as con:
        con.execute('BEGIN IMMEDIATE');ig=_registrar(con,pacote,caso,modo)
        anterior=con.execute('SELECT rev_uid,situacao FROM IGD_REVISOES WHERE ig_uid=? AND occ_uid=? AND modo=? ORDER BY rowid DESC LIMIT 1',(ig,caso['uid'],modo)).fetchone()
        if (anterior[0] if anterior else None)!=esperada:raise ValueError('Revisão alterada por outra sessão; recarregue antes de salvar')
        uid=uuid4().hex
        con.execute('INSERT INTO IGD_REVISOES VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(uid,ig,caso['uid'],modo,esperada,anterior[1] if anterior else 'PENDENTE',situacao,conclusao,justificativa,responsavel,agora(),fonte,natureza,evidencia))
        return uid


def propostas(base,ig,occ=None,modo=None):
    with abrir_ro(base) as con:
        if not existe(con):return []
        con.row_factory=sqlite3.Row;res=[]
        for p in con.execute('SELECT * FROM IGD_PROPOSTAS WHERE ig_uid=?',(ig,)):
            p=dict(p)
            if (occ and p['occ_uid']!=occ) or (modo and p['modo']!=modo):continue
            hs=[dict(r) for r in con.execute('SELECT * FROM IGD_PROP_HIST WHERE prop_uid=? ORDER BY rowid',(p['prop_uid'],))]
            for h in hs:h['elementos']=[dict(r) for r in con.execute('SELECT * FROM IGD_PROP_ELEMENTOS WHERE hist_uid=? ORDER BY ordem',(h['hist_uid'],))]
            p['historico']=hs;p['atual']=hs[-1];res.append(p)
        return res


def salvar_proposta(base,pacote,caso,modo,tipo,descricao='',justificativa='',requisitos='',responsavel='',evidencia='',elementos=(),elementos_confirmados=False,situacao='RASCUNHO',prop_uid=None,esperada=None,confirmacao=False,validacao_uid=None,validacao_manual=False):
    if modo not in MODOS:raise ValueError('Perspectiva não validada')
    if tipo not in TIPOS_PROPOSTA or situacao not in ESTADOS_PROPOSTA:raise ValueError('Tipo ou situação de proposta inválidos')
    if len(set(elementos))!=len(elementos):raise ValueError('Elementos repetidos na proposta')
    el=pacote['topologia']['modelo']['elementos'];ids=list(elementos)
    if any(not isinstance(i,int) or isinstance(i,bool) for i in ids):raise ValueError('DomainElementID deve ser inteiro explícito, sem arredondamento')
    if any(i not in el for i in ids):raise ValueError('DomainElementID inexistente nesta execução')
    completa=bool(ids and elementos_confirmados and descricao.strip() and justificativa.strip() and requisitos.strip() and responsavel.strip() and evidencia.strip())
    if tipo=='Conectar dois nós':completa=completa and len(ids)==2 and all(el[i]['familia']=='NO' for i in ids)
    if tipo=='Corrigir vínculo Start/Stop Node':completa=completa and any(el[i]['familia']=='LINK' for i in ids) and any(el[i]['familia']=='NO' for i in ids)
    if tipo=='Corrigir vínculo de válvula':completa=completa and any(el[i]['familia']=='DISPOSITIVO' and el[i]['tipo'] not in ('StandardPump','VariableSpeedPumpBattery') for i in ids) and any(el[i]['familia']=='LINK' for i in ids)
    if tipo=='Corrigir vínculo de bomba':completa=completa and any(el[i]['tipo'] in ('StandardPump','VariableSpeedPumpBattery') for i in ids) and any(el[i]['familia']=='LINK' for i in ids)
    if tipo=='Verificar ou eliminar nó duplicado':completa=completa and sum(el[i]['familia']=='NO' for i in ids)>=2
    if tipo=='Dividir tubulação para inserir conexão':completa=completa and any(el[i]['familia']=='LINK' for i in ids)
    if tipo=='Remover conexão indevida':completa=completa and (any(el[i]['familia']=='LINK' for i in ids) or sum(el[i]['familia']=='NO' for i in ids)>=2)
    if tipo=='Corrigir correspondência cadastral GIS × WaterGEMS':completa=completa and bool(caso['gis_uids'])
    avancada=situacao not in ('RASCUNHO','AGUARDANDO_CONFIRMACAO','REJEITADA')
    if avancada and not completa:raise ValueError('Proposta incompleta: identifique e confirme elementos, descrição, justificativa e requisitos')
    if situacao in ('APROVADA','APLICACAO_INFORMADA','VALIDADA','VALIDACAO_FALHOU') and (not confirmacao or not responsavel.strip() or not evidencia.strip()):raise ValueError('Ação exige confirmação humana, responsável e evidência identificada')
    preparar_base(base,pacote)
    with conectar(base) as con:
        con.execute('BEGIN IMMEDIATE');ig=_registrar(con,pacote,caso,modo)
        if prop_uid:
            p=con.execute('SELECT ig_uid,occ_uid,modo FROM IGD_PROPOSTAS WHERE prop_uid=?',(prop_uid,)).fetchone()
            if p!=(ig,caso['uid'],modo):raise ValueError('Proposta não pertence à ocorrência/perspectiva selecionada')
            atual=con.execute('SELECT hist_uid,situacao,tipo,descricao,justificativa,requisitos,elementos_confirmados FROM IGD_PROP_HIST WHERE prop_uid=? ORDER BY rowid DESC LIMIT 1',(prop_uid,)).fetchone()
            if not atual or atual[0]!=esperada:raise ValueError('Proposta alterada por outra sessão; recarregue')
            anterior=atual[1]
            if situacao not in TRANSICOES[anterior]:raise ValueError('Transição não permitida: '+anterior+' → '+situacao)
            if anterior in ('APROVADA','APLICACAO_INFORMADA','VALIDACAO_PENDENTE','VALIDADA','VALIDACAO_FALHOU') and situacao!='RASCUNHO':
                prev=[int(r[0]) for r in con.execute('SELECT wg_id FROM IGD_PROP_ELEMENTOS WHERE hist_uid=? ORDER BY ordem',(esperada,))]
                if (tipo,descricao,justificativa,requisitos,elementos_confirmados,ids)!=(atual[2],atual[3],atual[4],atual[5],bool(atual[6]),prev):raise ValueError('Escopo aprovado não pode mudar; retorne a rascunho e submeta novamente')
        else:
            if situacao not in ('RASCUNHO','AGUARDANDO_CONFIRMACAO'):raise ValueError('Uma nova proposta começa como rascunho ou aguardando confirmação')
            prop_uid=uuid4().hex;anterior=None
            con.execute('INSERT INTO IGD_PROPOSTAS VALUES(?,?,?,?,?)',(prop_uid,ig,caso['uid'],modo,agora()))
        if situacao=='VALIDADA':
            v=con.execute('SELECT hist_uid,dados FROM IGD_VALIDACOES WHERE val_uid=? AND prop_uid=?',(validacao_uid,prop_uid)).fetchone()
            if not v or v[0]!=esperada or not all(json.loads(v[1]).get(k) for k in ('cenarios_comparaveis','identidades_preservadas')):raise ValueError('Validação exige confronto técnico atual, cenários comparáveis e identidades preservadas, antes da confirmação humana')
            resultado=json.loads(v[1])['resultado']
            if resultado=='LIGACAO_DIRETA_NAO_OBSERVADA':raise ValueError('Ligação direta não observada; registre falha ou obtenha nova evidência de modelo')
            if resultado=='INCONCLUSIVO' and not validacao_manual:raise ValueError('Tipo sem verificador automático: exige declaração explícita de verificação técnica adicional e evidência identificada')
        uid=uuid4().hex
        con.execute('INSERT INTO IGD_PROP_HIST VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(uid,prop_uid,esperada,anterior,situacao,tipo,descricao,justificativa,requisitos,responsavel,agora(),evidencia,int(not completa),int(elementos_confirmados),int(confirmacao),validacao_uid,int(validacao_manual)))
        for k,i in enumerate(ids):con.execute('INSERT INTO IGD_PROP_ELEMENTOS VALUES(?,?,?,?,?,?)',(uid,k,pacote['topologia']['modelo']['projeto'],str(i),str(el[i]['label']),el[i]['tipo']))
        return prop_uid,uid


def validacoes(base,prop_uid,hist_uid=None):
    with abrir_ro(base) as con:
        if not existe(con):return []
        return [json.loads(r[0]) for r in con.execute('SELECT dados FROM IGD_VALIDACOES WHERE prop_uid=? '+('AND hist_uid=? ' if hist_uid else '')+'ORDER BY rowid',(prop_uid,hist_uid) if hist_uid else (prop_uid,))]


def indice_revisoes(base,ig):
    with abrir_ro(base) as con:
        if not existe(con):return {}
        con.row_factory=sqlite3.Row
        return {(r['occ_uid'],r['modo']):dict(r) for r in con.execute('SELECT * FROM IGD_REVISOES WHERE ig_uid=? ORDER BY rowid',(ig,))}
