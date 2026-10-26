"""Extensão do GeoPackage existente: linhagem, transações e substituição lógica."""
from copy import deepcopy
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .ciclo import inicializar,perfil,comparar_locais,regerar
from .inspecao import texto,restaurar
from .investigacao import instante_execucao

MODOS=('NOVA','RECONCILIAR','SUBSTITUIR')


def estrutura(con):
    # DDL idempotente; extensão compatível do esquema anterior, sem remover tabelas.
    con.execute('''CREATE TABLE IF NOT EXISTS AUDITORIA_VERSOES(
        exe_uid TEXT PRIMARY KEY REFERENCES EXECUCOES(exe_uid),nome TEXT,projeto TEXT,
        criacao TEXT,processamento TEXT,origem_exe TEXT,origem_base TEXT,operacao TEXT,modo TEXT,
        ativa INTEGER NOT NULL DEFAULT 1,substituida_por TEXT,configuracao TEXT,comparacao TEXT)''')
    con.execute('''CREATE TABLE IF NOT EXISTS AUDITORIA_LINHAGEM(
        exe_uid TEXT,loc_uid TEXT,origem_base TEXT,origem_exe TEXT,origem_local TEXT,tipo TEXT,
        PRIMARY KEY(exe_uid,loc_uid,origem_base,origem_exe,origem_local),
        FOREIGN KEY(exe_uid,loc_uid) REFERENCES PONTOS_INVESTIGACAO(EXE_UID,LOC_UID))''')
    con.execute('''CREATE TABLE IF NOT EXISTS AUDITORIA_LINHAGEM_EVENTOS(
        exe_uid TEXT,loc_uid TEXT,origem_base TEXT,origem_exe TEXT,origem_local TEXT,evt_uid TEXT,
        PRIMARY KEY(exe_uid,loc_uid,origem_base,origem_exe,origem_local,evt_uid),
        FOREIGN KEY(exe_uid,loc_uid,origem_base,origem_exe,origem_local) REFERENCES AUDITORIA_LINHAGEM,
        FOREIGN KEY(exe_uid,evt_uid) REFERENCES EVENTOS_FRONTEIRAS(EXE_UID,EVT_UID))''')
    con.execute('''CREATE TABLE IF NOT EXISTS AUDITORIA_PREFERENCIAS(
        exe_uid TEXT PRIMARY KEY REFERENCES EXECUCOES(exe_uid),dados TEXT,atualizacao TEXT)''')
    con.execute('''CREATE TABLE IF NOT EXISTS AUDITORIA_LINHAGEM_AVALIADA(
        rev_uid TEXT REFERENCES REVISOES,exe_uid TEXT,loc_uid TEXT,origem_base TEXT,origem_exe TEXT,origem_local TEXT,
        PRIMARY KEY(rev_uid,exe_uid,loc_uid,origem_base,origem_exe,origem_local),
        FOREIGN KEY(exe_uid,loc_uid,origem_base,origem_exe,origem_local) REFERENCES AUDITORIA_LINHAGEM)''')
    for nome in ('AUDITORIA_VERSOES','AUDITORIA_LINHAGEM','AUDITORIA_LINHAGEM_EVENTOS','AUDITORIA_PREFERENCIAS','AUDITORIA_LINHAGEM_AVALIADA'):
        con.execute("INSERT OR IGNORE INTO gpkg_contents(table_name,data_type,identifier) VALUES(?,'attributes',?)",(nome,nome))


def registrar_controle(con,d):
    c=d.get('controle_versao',{})
    agora=instante_execucao()
    con.execute('INSERT OR IGNORE INTO AUDITORIA_VERSOES VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (d['execucao_uid'],c.get('nome') or 'Auditoria '+d['execucao_uid'][:8],c.get('projeto',''),
         c.get('data_criacao_utc',agora),c.get('data_processamento_utc',d['analise']['metadados'].get('data_execucao_utc',agora)),
         c.get('execucao_origem'),c.get('base_origem'),c.get('tipo_operacao','PROCESSAMENTO_COMPLETO'),
         c.get('modo_salvamento','LEGADO'),1,None,texto(perfil(d)),texto(d.get('comparacao_versoes',{}))))


def complementar(con,d):
    def legado():
        inicializar(d)
        data=con.execute('SELECT data_utc FROM EXECUCOES WHERE exe_uid=?',(d['execucao_uid'],)).fetchone()[0]
        d['controle_versao'].update(tipo_operacao='LEGADO',data_criacao_utc=data,data_processamento_utc=data)
    existe=con.execute("SELECT 1 FROM sqlite_master WHERE name='AUDITORIA_VERSOES'").fetchone()
    if not existe:
        # Bases legadas continuam legíveis; migração ocorre somente ao gravar.
        if 'controle_versao' not in d:
            legado()
        return d
    anterior_factory=con.row_factory
    con.row_factory=sqlite3.Row
    linha=con.execute('SELECT * FROM AUDITORIA_VERSOES WHERE exe_uid=?',(d['execucao_uid'],)).fetchone()
    if linha:
        r=dict(linha)
        d['controle_versao']=dict(nome=r['nome'],projeto=r['projeto'],data_criacao_utc=r['criacao'],
            data_processamento_utc=r['processamento'],execucao_origem=r['origem_exe'],base_origem=r['origem_base'],
            tipo_operacao=r['operacao'],modo_salvamento=r['modo'],ativa=bool(r['ativa']),substituida_por=r['substituida_por'])
        d['configuracao']=json.loads(r['configuracao'])
        d['comparacao_versoes']=json.loads(r['comparacao'])
    elif 'controle_versao' not in d:
        legado()
    pref=con.execute('SELECT dados,atualizacao FROM AUDITORIA_PREFERENCIAS WHERE exe_uid=?',(d['execucao_uid'],)).fetchone()
    if pref:
        d.setdefault('configuracao',perfil(d))['exportacao']=json.loads(pref[0])
        d['ultima_exportacao_utc']=pref[1]
    d['linhagem_locais']=[dict(r) for r in con.execute('SELECT * FROM AUDITORIA_LINHAGEM WHERE exe_uid=?',(d['execucao_uid'],))]
    conhecidos={(r['local_uid'],r['execucao_anterior'],r['local_anterior']) for r in d['reconciliacoes']}
    for r in d['linhagem_locais']:
        chave=(r['loc_uid'],r['origem_exe'],r['origem_local'])
        if chave not in conhecidos:
            avaliadas=con.execute("SELECT 1 FROM sqlite_master WHERE name='AUDITORIA_LINHAGEM_AVALIADA'").fetchone()
            avaliada=avaliadas and con.execute('SELECT 1 FROM AUDITORIA_LINHAGEM_AVALIADA WHERE exe_uid=? AND loc_uid=? AND origem_base=? AND origem_exe=? AND origem_local=?',
                (r['exe_uid'],r['loc_uid'],r['origem_base'],r['origem_exe'],r['origem_local'])).fetchone()
            d['reconciliacoes'].append(dict(local_uid=r['loc_uid'],execucao_anterior=r['origem_exe'],
                local_anterior=r['origem_local'],tipo=r['tipo'],decisao='AVALIADA_MANUALMENTE' if avaliada else 'PENDENTE',base_anterior=r['origem_base']))
    con.row_factory=anterior_factory
    return d


@contextmanager
def abrir_ro(caminho):
    p=Path(caminho).resolve(strict=True)
    con=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=15)
    con.execute('PRAGMA foreign_keys=ON')
    try:
        yield con
    finally:
        con.close()


def validar_base(caminho):
    with abrir_ro(caminho) as con:
        tabelas={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        necessarias={'EXECUCOES','EVENTOS_FRONTEIRAS','PONTOS_INVESTIGACAO','LOCAL_EVENTO','EVENTO_REDE','EVENTO_POLIGONO','REVISOES','AUDITORIA_SCHEMA'}
        if not necessarias<=tabelas or con.execute('SELECT versao FROM AUDITORIA_SCHEMA').fetchone()[0]!=1:
            raise ValueError('Arquivo não contém uma auditoria completa compatível')
        if con.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or con.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Base de auditoria falhou na verificação de integridade')
    return True


def listar(caminho):
    from .persistencia import carregar_execucao
    validar_base(caminho)
    with abrir_ro(caminho) as con:
        execucoes=con.execute('SELECT exe_uid,data_utc FROM EXECUCOES ORDER BY rowid DESC').fetchall()
        saida=[]
        for uid,data in execucoes:
            d=carregar_execucao(caminho,uid,conexao=con)
            c=d.get('controle_versao',{})
            ultima=con.execute('SELECT max(data_utc) FROM REVISOES WHERE exe_uid=?',(uid,)).fetchone()[0]
            saida.append(dict(execucao_uid=uid,nome=c.get('nome','Auditoria '+uid[:8]),projeto=c.get('projeto',''),
                data=c.get('data_processamento_utc',data),eventos=len(d['eventos']),locais=len(d['locais']),
                ultima_revisao=ultima,base=str(Path(caminho).resolve()),ativa=c.get('ativa',True),
                operacao=c.get('tipo_operacao','LEGADO'),origem=c.get('execucao_origem'),
                agrupamento=perfil(d)['agrupamento']))
        return saida


def token(con,exe):
    linha=con.execute('SELECT snapshot FROM EXECUCOES WHERE exe_uid=?',(exe,)).fetchone()
    if not linha:
        raise ValueError('Execução de origem inexistente')
    revisoes=con.execute('SELECT * FROM REVISOES WHERE exe_uid=? ORDER BY rev_uid',(exe,)).fetchall()
    controle=con.execute("SELECT 1 FROM sqlite_master WHERE name='AUDITORIA_VERSOES'").fetchone()
    estado=con.execute('SELECT ativa,substituida_por FROM AUDITORIA_VERSOES WHERE exe_uid=?',(exe,)).fetchone() if controle else None
    return sha256(texto([linha[0],[tuple(r) for r in revisoes],tuple(estado) if estado else None]).encode()).hexdigest()


def preparar_regeneracao(base,exe,opcoes,cancelar=None):
    from .persistencia import carregar_execucao
    validar_base(base)
    with abrir_ro(base) as con:
        con.execute('BEGIN')
        origem=carregar_execucao(base,exe,conexao=con)
        esperado=token(con,exe)
        contagens=dict(con.execute('SELECT loc_uid,count(*) FROM REVISOES WHERE exe_uid=? GROUP BY loc_uid',(exe,)))
    novo,_=regerar(origem,opcoes,cancelar)
    comparacao=comparar_locais(origem,novo,contagens)
    novo['controle_versao']['base_origem']=str(Path(base).resolve())
    novo['comparacao_versoes']=comparacao
    return dict(origem=origem,novo=novo,comparacao=comparacao,token_origem=esperado)


def _resumo_logico(con):
    objetos=con.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
    linhas=[]
    for nome,sql in con.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
        q='"'+nome.replace('"','""')+'"'
        hashes=sorted(sha256(repr(tuple(r)).encode()).hexdigest() for r in con.execute('SELECT * FROM '+q))
        linhas.append((nome,sql,len(hashes),sha256(texto(hashes).encode()).hexdigest()))
    return objetos,linhas


def backup_verificado(base,destino,exe=None):
    from .persistencia import carregar_execucao
    validar_base(base)
    destino=Path(destino).resolve()
    if destino.exists() or not destino.parent.is_dir():
        raise ValueError('Backup precisa de caminho novo em pasta existente')
    with destino.open('xb'):
        pass
    with abrir_ro(base) as origem,sqlite3.connect(destino) as copia:
        origem.execute('BEGIN')
        origem.backup(copia)
        if _resumo_logico(origem)!=_resumo_logico(copia):
            raise ValueError('Backup não preservou todas as tabelas/dados')
    validar_base(destino)
    if exe:
        restaurar(carregar_execucao(destino,exe))
    evidencias=dict(backup=str(destino),origem=str(Path(base).resolve()),
        sha256=sha256(destino.read_bytes()).hexdigest(),estrutura_dados_iguais=True,recuperacao_verificada=True)
    with destino.with_suffix('.verificacao.json').open('x',encoding='utf-8') as arq:
        json.dump(evidencias,arq,ensure_ascii=False,indent=2)
    return evidencias


def gravar_versao(base,exe,novo,modo='NOVA',destino=None,confirmado=False,backup_pasta=None,
                  token_origem=None,interromper=None):
    """Substituição troca a versão ativa; nunca destrói snapshots/revisões anteriores."""
    from .persistencia import carregar_execucao,conectar,_iniciar,salvar_execucao
    if modo not in MODOS:
        raise ValueError('Modo de salvamento inválido')
    if modo=='SUBSTITUIR' and not confirmado:
        raise ValueError('Substituição exige confirmação explícita')
    validar_base(base)
    destino=Path(destino or base).resolve()
    base=Path(base).resolve()
    origem=carregar_execucao(base,exe)
    restaurar(novo)
    if novo['execucao_uid']==exe:
        raise ValueError('Cada versão deve possuir identidade própria')
    if novo['controle_versao']['tipo_operacao']=='REAGRUPAMENTO' and texto(origem['eventos'])!=texto(novo['eventos']):
        raise ValueError('Regeneração não pode modificar eventos')
    if modo=='SUBSTITUIR' and destino!=base:
        raise ValueError('Substituição deve ocorrer na base selecionada; use nova versão para outro CRS/base')
    esperado=token_origem
    if esperado is None:
        raise ValueError('Token da execução de origem é obrigatório; prepare novamente a operação')
    with abrir_ro(base) as con:
        if token(con,exe)!=esperado:
            raise ValueError('Origem/revisões mudaram após a prévia; recalcule a comparação')
        contagens=dict(con.execute('SELECT loc_uid,count(*) FROM REVISOES WHERE exe_uid=? GROUP BY loc_uid',(exe,)))
    d=deepcopy(novo)
    cmp=comparar_locais(origem,d,contagens)
    d['comparacao_versoes']=cmp
    c=d['controle_versao']
    c.update(execucao_origem=exe,base_origem=str(base),modo_salvamento=modo)
    if modo=='SUBSTITUIR':
        c['tipo_operacao']='SUBSTITUICAO_'+c['tipo_operacao']
    _iniciar(destino,d['contexto']['parametros']['crs'])
    evidencia=None
    if modo=='SUBSTITUIR':
        pasta=Path(backup_pasta or base.parent/'backups')
        pasta.mkdir(parents=True,exist_ok=True)
        evidencia=backup_verificado(base,pasta/(base.stem+'_'+uuid4().hex+'.gpkg'),exe)
    if interromper:
        interromper('ANTES_TRANSACAO')
    # Uma transação publica dados, vínculos, linhagem e ponteiro ativo conjuntamente.
    with conectar(destino) as con:
        con.execute('BEGIN IMMEDIATE')
        if destino==base and token(con,exe)!=esperado:
            raise ValueError('Origem mudou durante a preparação; operação cancelada')
        if con.execute('SELECT 1 FROM EXECUCOES WHERE exe_uid=?',(d['execucao_uid'],)).fetchone():
            raise ValueError('Esta versão já foi gravada')
        if destino==base:
            registrar_controle(con,origem)
        salvar_execucao(destino,d,conexao=con,reconciliar=modo=='RECONCILIAR',
            origens_reconciliacao=[exe],locais_herdaveis=set(cmp['locais_herdaveis']))
        for r in cmp['correspondencias']:
            chave=(d['execucao_uid'],r['novo'],str(base),exe,r['anterior'])
            con.execute('INSERT INTO AUDITORIA_LINHAGEM VALUES(?,?,?,?,?,?)',chave+(r['tipo'],))
            con.executemany('INSERT INTO AUDITORIA_LINHAGEM_EVENTOS VALUES(?,?,?,?,?,?)',
                (chave+(evento,) for evento in r['eventos']))
        if modo=='SUBSTITUIR':
            con.execute('UPDATE AUDITORIA_VERSOES SET ativa=0,substituida_por=? WHERE exe_uid=?',(d['execucao_uid'],exe))
        if destino!=base:
            with abrir_ro(base) as fonte:
                if token(fonte,exe)!=esperado:
                    raise ValueError('Origem mudou durante a gravação; operação revertida')
        if interromper:
            interromper('ANTES_COMMIT')
        if con.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Integridade referencial inválida; operação revertida')
    return dict(dossie=carregar_execucao(destino,d['execucao_uid']),comparacao=cmp,backup=evidencia,base=str(destino))


def salvar_preferencias(base,exe,preferencias):
    from .persistencia import conectar
    with conectar(base) as con:
        estrutura(con)
        con.execute('INSERT OR REPLACE INTO AUDITORIA_PREFERENCIAS VALUES(?,?,?)',
                    (exe,texto(preferencias),instante_execucao()))


def metadados_exportacao(d):
    return dict(execucao_uid=d['execucao_uid'],versao=deepcopy(d.get('controle_versao',{})),
        gerado_utc=instante_execucao(),ultima_revisao_incluida=max(
            (l['revisao'].get('data') or '' for l in d['locais']),default='') or None,
        parametros=deepcopy(perfil(d)))
