"""Extensão aditiva do GPKG integrado: locais manuais e conjuntos de elementos.

Cada gravação acrescenta uma revisão imutável. Os arquivos de entrada nunca são
abertos para escrita. A identidade do objeto independe da revisão e da posição.
"""
import json
import math
import sqlite3
from pathlib import Path
from uuid import uuid4
from . import decisoes as db


def preparar(base, pacote):
    db.preparar_base(base, pacote)
    with db.abrir_ro(base) as c:
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='IGD_CONJUNTOS_SCHEMA'").fetchone():
            versao=c.execute('SELECT max(versao) FROM IGD_CONJUNTOS_SCHEMA').fetchone()[0]
            if versao not in (1,2):
                raise ValueError('Versão de locais/conjuntos não suportada')
            if versao==2:return
    backup = Path(base).with_name(Path(base).stem+'_antes_conjuntos_'+uuid4().hex[:12]+'.gpkg')
    db.exportar_gpkg(backup, pacote['dossie'], base_origem=base)
    with db.abrir_ro(backup) as c:
        if c.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or c.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Backup não íntegro; nenhuma alteração aplicada')
    with db.conectar(base) as c:
        c.execute('BEGIN IMMEDIATE')
        for nome, ddl in {
            'IGD_CONJUNTOS_SCHEMA': 'versao INTEGER PRIMARY KEY,backup TEXT NOT NULL,data_utc TEXT NOT NULL',
            'IGD_OBJETOS': 'uid TEXT PRIMARY KEY,ig_uid TEXT NOT NULL REFERENCES IG_EXECUCOES(ig_uid),tipo TEXT NOT NULL',
            'IGD_OBJ_HIST': '''uid TEXT PRIMARY KEY,obj_uid TEXT NOT NULL REFERENCES IGD_OBJETOS(uid),anterior TEXT REFERENCES IGD_OBJ_HIST(uid),topo_uid TEXT NOT NULL,modo TEXT NOT NULL,data_utc TEXT NOT NULL,excluido INTEGER NOT NULL CHECK(excluido IN (0,1)),dados TEXT NOT NULL''',
            'IGD_OBJ_VINCULOS': '''hist_uid TEXT NOT NULL REFERENCES IGD_OBJ_HIST(uid),ordem INTEGER NOT NULL,origem TEXT NOT NULL,chave TEXT NOT NULL,natureza TEXT NOT NULL,dados TEXT NOT NULL,PRIMARY KEY(hist_uid,ordem)'''
        }.items():
            c.execute(f'CREATE TABLE IF NOT EXISTS {nome}({ddl})')
            c.execute("INSERT OR IGNORE INTO gpkg_contents(table_name,data_type,identifier) VALUES(?,'attributes',?)", (nome,nome))
            for acao in ('UPDATE','DELETE'):
                c.execute(f"CREATE TRIGGER IF NOT EXISTS {nome}_{acao}_imutavel BEFORE {acao} ON {nome} BEGIN SELECT RAISE(ABORT,'Histórico imutável'); END")
        c.execute('CREATE INDEX IF NOT EXISTS igd_obj_exec ON IGD_OBJETOS(ig_uid,tipo)')
        c.execute('CREATE INDEX IF NOT EXISTS igd_obj_hist_obj_idx ON IGD_OBJ_HIST(obj_uid)')
        srs=c.execute("SELECT srs_id FROM gpkg_contents WHERE table_name='EVENTOS_FRONTEIRAS'").fetchone()[0]
        c.execute('''CREATE TABLE IF NOT EXISTS IGD_MANUAL_GEOM(fid INTEGER PRIMARY KEY AUTOINCREMENT,hist_uid TEXT UNIQUE NOT NULL REFERENCES IGD_OBJ_HIST(uid),obj_uid TEXT NOT NULL REFERENCES IGD_OBJETOS(uid),titulo TEXT,geom BLOB NOT NULL)''')
        c.execute('''CREATE VIEW IF NOT EXISTS IG_MANUAIS_ATUAIS AS SELECT g.* FROM IGD_MANUAL_GEOM g JOIN IGD_OBJ_HIST h ON h.uid=g.hist_uid WHERE h.excluido=0 AND NOT EXISTS(SELECT 1 FROM IGD_OBJ_HIST n WHERE n.obj_uid=h.obj_uid AND n.rowid>h.rowid)''')
        for nome in ('IGD_MANUAL_GEOM','IG_MANUAIS_ATUAIS'):
            c.execute("INSERT OR IGNORE INTO gpkg_contents(table_name,data_type,identifier,srs_id) VALUES(?,'features',?,?)",(nome,nome,srs))
            c.execute("INSERT OR IGNORE INTO gpkg_geometry_columns VALUES(?,'geom','POINT',?,0,0)",(nome,srs))
        for acao in ('UPDATE','DELETE'):c.execute(f"CREATE TRIGGER IF NOT EXISTS IGD_MANUAL_GEOM_{acao}_imutavel BEFORE {acao} ON IGD_MANUAL_GEOM BEGIN SELECT RAISE(ABORT,'Histórico imutável'); END")
        for h,obj,dados in c.execute("SELECT h.uid,h.obj_uid,h.dados FROM IGD_OBJ_HIST h JOIN IGD_OBJETOS o ON o.uid=h.obj_uid WHERE o.tipo='LOCAL_MANUAL' AND NOT EXISTS(SELECT 1 FROM IGD_MANUAL_GEOM g WHERE g.hist_uid=h.uid)").fetchall():_geometria(c,pacote,h,obj,json.loads(dados))
        c.execute('INSERT OR IGNORE INTO IGD_CONJUNTOS_SCHEMA VALUES(2,?,?)',(str(backup),db.agora()))


def _geometria(c,pacote,hist,obj,dados):
    from qgis.core import QgsGeometry,QgsCoordinateReferenceSystem,QgsCoordinateTransform,QgsProject
    from auditoria_fronteiras.persistencia import _geometria as blob
    destino=QgsCoordinateReferenceSystem(pacote['dossie']['contexto']['parametros']['crs']);origem=QgsCoordinateReferenceSystem(dados['crs'])
    g=QgsGeometry.fromWkt(f"POINT({dados['x']} {dados['y']})")
    if origem!=destino:g.transform(QgsCoordinateTransform(origem,destino,QgsProject.instance()))
    srs=c.execute("SELECT srs_id FROM gpkg_contents WHERE table_name='IGD_MANUAL_GEOM'").fetchone()[0]
    c.execute('INSERT INTO IGD_MANUAL_GEOM(hist_uid,obj_uid,titulo,geom) VALUES(?,?,?,?)',(hist,obj,dados.get('titulo',''),blob(g,srs)))


def historico(base, pacote, tipo=None):
    with db.abrir_ro(base) as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='IGD_OBJETOS'").fetchone():return []
        c.row_factory=sqlite3.Row
        rows=c.execute('''SELECT h.*,o.ig_uid,o.tipo FROM IGD_OBJ_HIST h JOIN IGD_OBJETOS o ON o.uid=h.obj_uid WHERE o.ig_uid=? ORDER BY h.rowid''',(pacote['resultado']['meta']['uid'],))
        result=[]
        for row in rows:
            r=dict(row)
            if tipo and r['tipo']!=tipo:continue
            r['dados']=json.loads(r['dados'])
            r['vinculos']=[dict(v, dados=json.loads(v['dados'])) for v in map(dict,c.execute('SELECT * FROM IGD_OBJ_VINCULOS WHERE hist_uid=? ORDER BY ordem',(r['uid'],)))]
            result.append(r)
        return result


def atuais(base,pacote,tipo=None,excluidos=False):
    ultimos={r['obj_uid']:r for r in historico(base,pacote,tipo)}
    return [r for r in ultimos.values() if excluidos or not r['excluido']]


def vinculo_wg(pacote,i,natureza='MANUAL'):
    e=pacote['topologia']['modelo']['elementos'].get(i)
    if e is None or e.get('excluido') is not False:raise ValueError('Elemento WaterGEMS ausente ou excluído: '+str(i))
    return dict(origem='WG',chave=str(i),natureza=natureza,dados=dict(uid=e['uid'],label=e['label'],tipo=e['tipo'],assinatura=db.digest(e)))


def salvar(base,pacote,tipo,dados,vinculos=(),uid=None,esperada=None,modo='ESTRUTURAL',excluido=False):
    if tipo not in ('LOCAL_MANUAL','REDE_PRINCIPAL','PERFIL_RESTRICOES','SELECTION_SET_WG','IMPORTACAO_SELECTION_WG'):raise ValueError('Tipo de objeto inválido')
    if modo not in db.MODOS:raise ValueError('Perspectiva indisponível')
    dados=dict(dados)
    if tipo=='LOCAL_MANUAL':
        from qgis.core import QgsCoordinateReferenceSystem
        if not QgsCoordinateReferenceSystem(dados.get('crs','')).isValid():raise ValueError('CRS do local inválido')
        if not all(math.isfinite(float(dados.get(k,float('nan')))) for k in ('x','y')):raise ValueError('Coordenadas inválidas')
        dados['origem']='MANUAL'
    elif not str(dados.get('nome','')).strip():raise ValueError('Informe um nome para o conjunto')
    # Valida e captura os elementos antes de qualquer alteração persistente.
    vs=[];chaves=set()
    for v in vinculos:
        v=dict(v)
        if v['origem']=='WG' and v.get('natureza')!='REFERENCIA_HISTORICA':
            atual=vinculo_wg(pacote,int(v['chave']),v.get('natureza','MANUAL'))
            if v.get('dados',{}).get('uid',atual['dados']['uid'])!=atual['dados']['uid']:raise ValueError('Identidade WaterGEMS incompatível')
            v=dict(atual,dados=dict(atual['dados'],**{k:val for k,val in v.get('dados',{}).items() if k not in ('uid','label','tipo','assinatura')}))
        if v['origem'] not in ('WG','GIS','AREA','LOCAL'):raise ValueError('Origem de vínculo inválida')
        if tipo=='REDE_PRINCIPAL':
            if v['origem']!='WG' or v.get('natureza')=='REFERENCIA_HISTORICA' or pacote['topologia']['modelo']['elementos'][int(v['chave'])]['familia']!='LINK':raise ValueError('Conjunto de redes aceita somente tubulações WaterGEMS identificadas')
            grafo=pacote['topologia']['estrutural' if modo=='ESTRUTURAL' else 'potencial']['grafo']
            if not hasattr(grafo,'graph'):raise ValueError('Grafo da perspectiva indisponível')
        k=(v['origem'],v['chave'])
        if k in chaves:raise ValueError('Vínculo repetido')
        chaves.add(k);vs.append(v)
    if tipo=='REDE_PRINCIPAL':
        disponiveis={d['elemento'] for _,_,d in pacote['topologia']['estrutural' if modo=='ESTRUTURAL' else 'potencial']['grafo'].edges(data=True) if d.get('natureza')=='TUBULACAO'}
        if any(int(v['chave']) not in disponiveis for v in vs):raise ValueError('Tubulação não disponível no grafo da perspectiva; revise o conjunto')
    preparar(base,pacote);ig=pacote['resultado']['meta']['uid'];obj=uid or uuid4().hex;hist=uuid4().hex
    with db.conectar(base) as c:
        c.execute('BEGIN IMMEDIATE')
        antigo=c.execute('SELECT ig_uid,tipo FROM IGD_OBJETOS WHERE uid=?',(obj,)).fetchone()
        if antigo and tuple(antigo)!=(ig,tipo):raise ValueError('Objeto pertence a outra execução ou tipo')
        head=c.execute('SELECT uid FROM IGD_OBJ_HIST WHERE obj_uid=? ORDER BY rowid DESC LIMIT 1',(obj,)).fetchone()
        if (head[0] if head else None)!=esperada:raise ValueError('Objeto alterado em outra sessão; recarregue antes de salvar')
        c.execute('INSERT OR IGNORE INTO IGD_OBJETOS VALUES(?,?,?)',(obj,ig,tipo))
        c.execute('INSERT INTO IGD_OBJ_HIST VALUES(?,?,?,?,?,?,?,?)',(hist,obj,esperada,pacote['resultado']['meta']['topologia']['execucao_uid'],modo,db.agora(),int(excluido),db.texto(dados)))
        for n,v in enumerate(vs):c.execute('INSERT INTO IGD_OBJ_VINCULOS VALUES(?,?,?,?,?,?)',(hist,n,v['origem'],v['chave'],v.get('natureza','MANUAL'),db.texto(v.get('dados',{}))))
        if tipo=='LOCAL_MANUAL':_geometria(c,pacote,hist,obj,dados)
    return obj,hist


def reconciliar(registro,pacote):
    """Evidências para migração explícita; nunca transfere resultados de análise."""
    el=pacote['topologia']['modelo']['elementos'];por_uid={}
    for i,e in el.items():por_uid.setdefault(e['uid'],[]).append((i,e))
    saida=[]
    for v in registro['vinculos']:
        if v['origem']!='WG':
            conjunto={'GIS':{t['uid'] for t in pacote['dossie']['tubulacoes']},'AREA':{a['uid'] for a in pacote.get('areas',[])},'LOCAL':{l['uid'] for l in pacote['resultado']['locais']}}
            estado='IDENTIDADE_PRESENTE_REQUER_CONFERENCIA' if v['chave'] in conjunto.get(v['origem'],set()) else 'AUSENTE_OU_NAO_VERIFICAVEL'
        else:
            candidatos=por_uid.get(v['dados'].get('uid'),[])
            estado='AUSENTE' if not candidatos else 'AMBIGUO' if len(candidatos)>1 else 'IDENTICO' if db.digest(candidatos[0][1])==v['dados'].get('assinatura') else 'ALTERADO'
        saida.append(dict(origem=v['origem'],chave=v['chave'],situacao=estado))
    return saida


def importar(fonte,pacote_origem,destino,pacote):
    """Cópia explícita de manuais entre execuções; nunca herda conclusões."""
    if not atuais(fonte,pacote_origem,'LOCAL_MANUAL'):return dict(importados=0,ja_recuperados=0,vinculos_pendentes=0)
    preparar(destino,pacote)
    with db.abrir_ro(destino) as c:esperadas=c.execute('SELECT uid FROM IGD_OBJ_HIST ORDER BY rowid').fetchall()
    temporario=Path(destino).with_name(Path(destino).stem+'_importacao_'+uuid4().hex+'.gpkg')
    try:
        db.exportar_gpkg(temporario,pacote['dossie'],base_origem=destino)
        resultado=_importar(fonte,pacote_origem,temporario,pacote)
        with db.abrir_ro(temporario) as c:
            if c.execute('PRAGMA quick_check').fetchone()[0]!='ok' or c.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Importação temporária não íntegra; destino preservado')
        with db.conectar(destino) as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT uid FROM IGD_OBJ_HIST ORDER BY rowid').fetchall()!=esperadas:raise ValueError('Conjuntos alterados em outra sessão; importação não publicada')
            c.execute('ATTACH DATABASE ? AS recuperacao',(str(temporario),))
            for tabela,chaves in [('IGD_OBJETOS','uid'),('IGD_OBJ_HIST','uid')]:
                c.execute(f'INSERT INTO {tabela} SELECT r.* FROM recuperacao.{tabela} r WHERE NOT EXISTS(SELECT 1 FROM main.{tabela} t WHERE t.{chaves}=r.{chaves})')
            c.execute('''INSERT INTO IGD_OBJ_VINCULOS SELECT r.* FROM recuperacao.IGD_OBJ_VINCULOS r WHERE NOT EXISTS(SELECT 1 FROM main.IGD_OBJ_VINCULOS t WHERE t.hist_uid=r.hist_uid AND t.ordem=r.ordem)''')
            c.execute('''INSERT INTO IGD_MANUAL_GEOM(hist_uid,obj_uid,titulo,geom) SELECT r.hist_uid,r.obj_uid,r.titulo,r.geom FROM recuperacao.IGD_MANUAL_GEOM r WHERE NOT EXISTS(SELECT 1 FROM main.IGD_MANUAL_GEOM t WHERE t.hist_uid=r.hist_uid)''')
            if c.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Vínculos inválidos; importação revertida')
        return resultado
    finally:
        if temporario.exists():temporario.unlink()


def _importar(fonte,pacote_origem,destino,pacote):
    registros=atuais(fonte,pacote_origem,'LOCAL_MANUAL');existentes=atuais(destino,pacote,'LOCAL_MANUAL',True)
    hs_por_obj={}
    for h in historico(fonte,pacote_origem,'LOCAL_MANUAL'):hs_por_obj.setdefault(h['obj_uid'],[]).append(h)
    ja={v for r in existentes for v in (r['uid'],r['dados'].get('origem_hist'))};contagem=dict(importados=0,ja_recuperados=0,vinculos_pendentes=0)
    mesmo_modelo=db.digest(pacote_origem['topologia']['modelo']['projeto'])==db.digest(pacote['topologia']['modelo']['projeto'])
    por_uid={}
    for i,e in pacote['topologia']['modelo']['elementos'].items():por_uid.setdefault(e['uid'],[]).append((i,e))
    for r in registros:
        if r['uid'] in ja:contagem['ja_recuperados']+=1;continue
        estados=reconciliar(r,pacote);vs=[]
        for v,estado in zip(r['vinculos'],estados):
            v=dict(v,dados=dict(v['dados'],reconciliacao=estado['situacao']))
            if v['origem']=='WG':
                cand=por_uid.get(v['dados'].get('uid'),[])
                if mesmo_modelo and estado['situacao']=='IDENTICO' and len(cand)==1:v=dict(v,chave=str(cand[0][0]))
                else:v['natureza']='REFERENCIA_HISTORICA';contagem['vinculos_pendentes']+=1
            vs.append(v)
        hs=[];vistos=set();fila=list(hs_por_obj[r['obj_uid']])
        while fila:
            h=fila.pop(0)
            if h['uid'] in vistos:continue
            vistos.add(h['uid']);dados=dict(h['dados']);fila.extend(dados.pop('historico_origem',[]));hs.append(dict(h,dados=dados))
        d=dict(r['dados'],origem_hist=r['uid'],origem_local=r['obj_uid'],origem_execucao=r['ig_uid'],historico_origem=hs,reconciliacao=estados,reavaliacao=True)
        # Mesmo banco pode conter várias execuções: preserva proveniência e cria
        # nova identidade contextual sem disputar a chave da execução anterior.
        uid=r['obj_uid']
        with db.abrir_ro(destino) as c:
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='IGD_OBJETOS'").fetchone() and c.execute('SELECT 1 FROM IGD_OBJETOS WHERE uid=?',(uid,)).fetchone():uid=None
        salvar(destino,pacote,'LOCAL_MANUAL',d,vs,uid=uid,modo=r['modo']);contagem['importados']+=1
    return contagem


def comparar_conjuntos(a,b):
    sa={(v['origem'],v['dados'].get('uid',v['chave'])) for v in a['vinculos']}
    sb={(v['origem'],v['dados'].get('uid',v['chave'])) for v in b['vinculos']}
    return dict(mantidos=sorted(sa&sb),incluidos=sorted(sb-sa),removidos=sorted(sa-sb),mesma_versao=a['topo_uid']==b['topo_uid'])
