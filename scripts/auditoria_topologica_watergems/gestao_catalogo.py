"""Gestão do mesmo índice operacional; nenhuma edição nos GPKGs catalogados."""
from pathlib import Path
from datetime import datetime,timezone
from uuid import uuid4
import json,os,sqlite3
from contextlib import closing
from .arquivos import hash_arquivo


def _schema(cat):
    with closing(cat._abrir_ro()) as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='gestao_bases'").fetchone():cat.backup()
    with cat.conectar() as c,c:
        c.execute('CREATE TABLE IF NOT EXISTS gestao_bases(uuid TEXT,tipo TEXT,base TEXT,nome TEXT,estado TEXT NOT NULL,alteracao TEXT NOT NULL,dados TEXT NOT NULL,PRIMARY KEY(uuid,tipo,base))')
        c.execute('CREATE TABLE IF NOT EXISTS gestao_historico(uid TEXT PRIMARY KEY,data TEXT NOT NULL,acao TEXT NOT NULL,dados TEXT NOT NULL)')


def apresentar(cat,itens):
    # Leitura de catálogos antigos ou somente leitura não força migração.
    with closing(cat._abrir_ro()) as c:
        existe=c.execute("SELECT 1 FROM sqlite_master WHERE name='gestao_bases'").fetchone()
        gestao={(u,t,b):dict(nome=n,estado=s,alteracao=d,gestao=json.loads(j)) for u,t,b,n,s,d,j in c.execute('SELECT * FROM gestao_bases')} if existe else {}
    saida=[]
    for item in itens:
        r=dict(item);info=gestao.get((r['uuid'],r['tipo'],r['base']),{})
        if info.get('estado')=='RETIRADA':continue
        if info.get('nome'):r['nome']=info['nome']
        r.update(estado_catalogo=info.get('estado','ATIVA'),ultima_alteracao=info.get('alteracao') or r.get('data',''))
        if not r.get('disponivel',Path(r['base']).is_file()):classe='INDISPONIVEL'
        elif '_antes_' in Path(r['base']).stem:
            classe='BACKUP_TECNICO' if r.get('backup_identidade_compartilhada') else 'BACKUP_CANDIDATO';r['criterio_classe']='Padrão de backup técnico e identidade interna compartilhada quando disponível. Conferir proveniência antes de restaurar; identidade nunca vem do nome.'
        elif r.get('conflito_identidade'):classe='COPIA_DIVERGENTE'
        elif len(r.get('caminhos',[]))>1:classe='COPIA_IDENTICA'
        elif r.get('anterior'):classe='VERSAO_REAL_COM_ORIGEM'
        else:classe='INVESTIGACAO_ATIVA'
        r['classe_arquivo']=classe;r['uuid_curto']=r['uuid'][:12];saida.append(r)
    return saida


def alterar(cat,r,acao,nome=None):
    if acao not in ('RENOMEAR','ARQUIVAR','RESTAURAR','RETIRAR'):raise ValueError('Ação inválida')
    if acao=='RENOMEAR' and not str(nome or '').strip():raise ValueError('Informe o nome de exibição')
    _schema(cat);chave=(r['uuid'],r['tipo'],str(Path(r['base']).resolve()));data=datetime.now(timezone.utc).isoformat()
    with cat.conectar() as c,c:
        c.execute('BEGIN IMMEDIATE');old=c.execute('SELECT nome,estado,dados FROM gestao_bases WHERE uuid=? AND tipo=? AND base=?',chave).fetchone()
        estado={'ARQUIVAR':'ARQUIVADA','RESTAURAR':'ATIVA','RETIRAR':'RETIRADA'}.get(acao,old[1] if old else 'ATIVA')
        n=nome.strip() if acao=='RENOMEAR' else old[0] if old else None
        c.execute('INSERT OR REPLACE INTO gestao_bases VALUES(?,?,?,?,?,?,?)',(*chave,n,estado,data,old[2] if old else '{}'))
        c.execute('INSERT INTO gestao_historico VALUES(?,?,?,?)',(uuid4().hex,data,acao,json.dumps(dict(chave=chave,nome=n,estado=estado),ensure_ascii=False)))


def adicionar(cat,base):
    itens=cat.registrar(base);_schema(cat)
    with cat.conectar() as c,c:
        for r in itens:c.execute("UPDATE gestao_bases SET estado='ATIVA' WHERE uuid=? AND tipo=? AND base=?",(r['uuid'],r['tipo'],r['base']))
    return itens


def dependencias(cat,r,ativas=()):
    p=Path(r['base']).resolve();bloqueios=[]
    if r['tipo']!='INTEGRADA':bloqueios.append('Esta ação física é exclusiva de investigações integradas, não de bases compartilhadas.')
    if str(p) in {str(Path(x).resolve()) for x in ativas if x}:bloqueios.append('Investigação aberta/ativa: feche-a antes da operação física.')
    for sufixo in ('-wal','-shm','-journal'):
        f=Path(str(p)+sufixo)
        if f.exists() and f.stat().st_size:bloqueios.append('Arquivo em uso ou com transação pendente: '+f.name)
    if p.exists():
        from .gerenciamento import identificar
        if len(identificar(p))>2:bloqueios.append('Arquivo contém outras execuções: não será removido por uma única investigação.')
    vistos=set()
    for item in cat.listar():
        outro=Path(item['base']).resolve()
        if outro==p and (item['uuid'],item['tipo'])!=(r['uuid'],r['tipo']) and item['tipo']!='AUDITORIA_GIS':bloqueios.append('Outra identidade catalogada compartilha o arquivo.')
        if outro!=p and str(p).casefold() in json.dumps(item,ensure_ascii=False).replace('\\\\','\\').casefold():bloqueios.append('Referência catalogada por '+item['nome'])
        if outro!=p and outro.is_file() and outro not in vistos:
            vistos.add(outro)
            try:
                with closing(sqlite3.connect(outro.as_uri()+'?mode=ro',uri=True)) as c:
                    if c.execute("SELECT 1 FROM sqlite_master WHERE name='IG_EXECUCOES'").fetchone():
                        for (bruto,) in c.execute('SELECT meta FROM IG_EXECUCOES'):
                            def caminhos(v):
                                if isinstance(v,dict):return [s for x in v.values() for s in caminhos(x)]
                                if isinstance(v,list):return [s for x in v for s in caminhos(x)]
                                return [v] if isinstance(v,str) and v.lower().endswith('.gpkg') else []
                            if any(Path(s).resolve()==p for s in caminhos(json.loads(bruto))):bloqueios.append('Investigação depende deste arquivo: '+str(outro))
            except (sqlite3.Error,ValueError,OSError):bloqueios.append('Não foi possível verificar dependências em '+str(outro))
    return dict(arquivos=[str(p)],bloqueios=sorted(set(bloqueios)),preservados='Auditorias GIS externas, bases WaterGEMS e backups não selecionados não serão movidos.')


def recuperar_arquivo(cat,r,ativas=(),confirmado=False):
    """Move somente o GPKG explicitamente confirmado. Não segue links nem inclui fontes."""
    plano=dependencias(cat,r,ativas)
    if not confirmado:raise ValueError('É necessária confirmação explícita da lista de arquivos.')
    if plano['bloqueios']:raise ValueError('\n'.join(plano['bloqueios']))
    origem=Path(r['base'])
    if origem.is_symlink():raise ValueError('Link não será movido')
    p=origem.resolve(strict=True)
    if p.is_symlink() or p.suffix.lower()!='.gpkg':raise ValueError('Fonte física não suportada')
    area=cat.raiz/'RECUPERACAO';area.mkdir(exist_ok=True);destino=area/(uuid4().hex+'_'+p.name)
    # Mesma unidade: rename atômico, sem intervalo de arquivo parcial.
    if p.drive.casefold()!=destino.drive.casefold():raise ValueError('Escolha uma recuperação na mesma unidade; arquivo preservado.')
    with closing(sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)) as c:
        if c.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Arquivo não íntegro; preserve-o para recuperação especializada.')
    assinatura=hash_arquivo(p);_schema(cat)
    manifesto=destino.with_suffix('.recuperacao.json');dados=dict(origem=str(p),recuperacao=str(destino),sha256=assinatura,uuid=r['uuid'],tipo=r['tipo'])
    manifesto.write_text(json.dumps(dados,ensure_ascii=False,indent=2),encoding='utf8')
    os.rename(p,destino)
    try:
        if hash_arquivo(destino)!=assinatura:raise ValueError('Assinatura divergente')
        alterar(cat,r,'RETIRAR')
    except Exception:os.rename(destino,p);raise
    return dados


def restaurar_arquivo(cat,manifesto):
    d=json.loads(Path(manifesto).read_text(encoding='utf8'));p=Path(d['origem']);s=Path(d['recuperacao'])
    if not s.resolve().is_relative_to((cat.raiz/'RECUPERACAO').resolve()) or s.suffix.lower()!='.gpkg' or p.suffix.lower()!='.gpkg':raise ValueError('Manifesto fora da área de recuperação desta pasta')
    if p.exists():raise FileExistsError('Destino original ocupado; nada foi substituído.')
    if hash_arquivo(s)!=d['sha256']:raise ValueError('Arquivo de recuperação foi alterado')
    os.rename(s,p)
    try:adicionar(cat,p)
    except Exception:os.rename(p,s);raise
    return p
