"""Fotografia versionada no GPKG existente; extração somente de snapshot SQLite."""
from contextlib import closing
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
import time
from uuid import uuid4
from auditoria_fronteiras.versoes import abrir_ro
from .arquivos import hash_arquivo
from .leitura import Banco
from .topologia import analisar
from .saidas import serializavel,exportar_json,camadas,exportar_geografico

MODOS=('ESTRUTURAL','TODAS_VALVULAS_ABERTAS')
VERSAO=1
def texto(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,default=serializavel)
def decodificar(v):
    if isinstance(v,dict):
        if set(v)=={'wkb_hex','bytes'}:return bytes.fromhex(v['wkb_hex'])
        return {k:decodificar(x) for k,x in v.items()}
    if isinstance(v,list):return [decodificar(x) for x in v]
    return v
def verificar(cancelar):
    if cancelar and cancelar():raise InterruptedError('Operação cancelada; versões anteriores preservadas')


def cenarios_fonte(fonte):
    with abrir_ro(fonte) as con:
        con.row_factory=sqlite3.Row
        linhas=[dict(r) for r in con.execute('SELECT * FROM HMIScenario')]
        projeto=con.execute('SELECT ActiveScenarioID FROM HMIDomainDataSet').fetchall()
        ids=[r['ScenarioID'] for r in linhas];rotulos={}
        if ids:
            for i in range(0,len(ids),900):
                lote=ids[i:i+900]
                rotulos.update({r['ElementID']:r['Label'] for r in con.execute('SELECT ElementID,Label FROM HMIModelingElement WHERE ElementID IN ('+','.join('?' for _ in lote)+')',lote)})
    return [dict(id=r['ScenarioID'],nome=r.get('Name') or r.get('Label') or rotulos.get(r['ScenarioID']) or 'Cenário '+str(r['ScenarioID'])) for r in linhas if not r.get('IsDeleted')],projeto[0][0] if len(projeto)==1 else None


def snapshot(fonte,destino,cancelar=None,timeout=300):
    fonte=Path(fonte).resolve(strict=True);destino=Path(destino).resolve()
    if destino.exists() or fonte==destino:raise FileExistsError('Snapshot exige destino novo')
    if shutil.disk_usage(destino.parent).free<fonte.stat().st_size+256*1024**2:raise ValueError('Espaço insuficiente para snapshot consistente e reserva')
    inicio=time.monotonic()
    def progresso(status,restantes,total):
        verificar(cancelar)
        if time.monotonic()-inicio>timeout:raise TimeoutError('Fonte ocupada ou snapshot demorou além do limite; salve uma cópia consistente do modelo')
    with abrir_ro(fonte) as origem,closing(sqlite3.connect(destino)) as copia:
        origem.backup(copia,pages=256,progress=progresso,sleep=.02)
        if copia.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Snapshot SQLite não íntegro')
    return dict(fonte=str(fonte),snapshot=str(destino),sha256_snapshot=hash_arquivo(destino),metodo='SQLite backup API inclui estado comprometido do WAL; não inclui alterações não salvas no WaterGEMS')


def assinatura_modelo(modelo,modo):
    h=sha256();h.update(texto({k:v for k,v in modelo.items() if k not in ('banco','elementos','avisos','esquema')}).encode());h.update(modo.encode())
    for i,e in sorted(modelo['elementos'].items()):h.update(texto([i,e]).encode())
    return h.hexdigest()


def extrair(fonte,cenario,modo,pasta,nome,projeto,anterior=None,referencia=None,cancelar=None):
    if modo not in MODOS:raise ValueError('Hipótese não validada')
    pasta=Path(pasta);pasta.mkdir(parents=True,exist_ok=False);verificar(cancelar)
    origem=snapshot(fonte,pasta/'fonte_consistente.sqlite',cancelar)
    banco=Banco(pasta/'fonte_consistente.sqlite')
    try:modelo=banco.ler(cenario)
    finally:banco.close()
    modelo['banco']=origem['fonte']
    if referencia:modelo['referencia_espacial']=dict(referencia)
    verificar(cancelar);assinatura=assinatura_modelo(modelo,modo)
    antes=metadados(anterior) if anterior else None
    if antes and antes['modelo_uid']!=modelo['projeto']:raise ValueError('A fonte pertence a outro modelo; crie uma base independente')
    if antes and antes['assinatura']==assinatura:
        (pasta/'SEM_ALTERACAO.json').write_text(texto(dict(origem=origem,base_reutilizada=str(anterior),assinatura=assinatura)),encoding='utf8')
        return dict(sem_alteracao=True,base=str(Path(anterior).resolve()),meta=antes)
    estrutural=analisar(modelo);verificar(cancelar);potencial=analisar(modelo,MODOS[1]);verificar(cancelar)
    meta=dict(uuid=uuid4().hex,tipo='TOPOLOGIA_WG',nome=nome,projeto=projeto,modelo_uid=modelo['projeto'],
        versao=antes['versao']+1 if antes else 1,anterior=antes['uuid'] if antes else None,
        base_anterior=str(Path(anterior).resolve()) if anterior else None,data=datetime.now(timezone.utc).isoformat(),
        cenario=cenario,hipotese=modo,assinatura=assinatura,origem=origem,crs=(referencia or {}).get('crs'),
        referencia_espacial=referencia or {},extrator='Banco.ler / snapshot-1',regras='grafo validado; sem interpretação de estados efetivos',
        codigo={n:hash_arquivo(Path(__file__).with_name(n+'.py')) for n in ('leitura','resolucao','topologia')},
        resumo=estrutural['resumo'],resumo_potencial=potencial['resumo'],situacao='CONCLUIDA')
    return dict(sem_alteracao=False,meta=meta,modelo=modelo,estrutural=estrutural,potencial=potencial,pasta=str(pasta))


def persistir(preparada,destino,cancelar=None):
    if preparada['sem_alteracao']:return Path(preparada['base'])
    destino=Path(destino).resolve()
    if destino.exists():raise FileExistsError('Versão anterior não será substituída')
    meta=preparada['meta'];m=preparada['modelo'];r=preparada['estrutural'];pasta=Path(preparada['pasta']);verificar(cancelar)
    gs=None
    if meta['referencia_espacial']:
        from .espacial import geometrias
        ref=meta['referencia_espacial'];gs,_=geometrias(m,ref['crs'],ref['fator'],ref['fonte'])
    exportar_geografico(camadas(m,r,gs,meta['crs']),pasta/'camadas','GPKG')
    parcial=pasta/'camadas/TOPOLOGIA.gpkg'
    with closing(sqlite3.connect(parcial)) as con,con:
        con.execute('PRAGMA foreign_keys=ON')
        con.execute('CREATE TABLE WB_BASE(uuid TEXT PRIMARY KEY,meta TEXT NOT NULL,modelo TEXT NOT NULL)')
        con.execute('CREATE TABLE WB_ELEMENTOS(id INTEGER PRIMARY KEY,uid TEXT UNIQUE NOT NULL,tipo TEXT NOT NULL,familia TEXT NOT NULL,ativo INTEGER,excluido INTEGER,dados TEXT NOT NULL,geometria BLOB)')
        con.execute('CREATE INDEX wb_tipo ON WB_ELEMENTOS(tipo)');con.execute('CREATE INDEX wb_familia ON WB_ELEMENTOS(familia)')
        con.execute('CREATE TABLE WB_RESULTADOS(modo TEXT PRIMARY KEY,dados TEXT NOT NULL)')
        con.execute('INSERT INTO WB_BASE VALUES(?,?,?)',(meta['uuid'],texto(meta),texto({k:v for k,v in m.items() if k!='elementos'})))
        for i,e in m['elementos'].items():
            verificar(cancelar);con.execute('INSERT INTO WB_ELEMENTOS VALUES(?,?,?,?,?,?,?,?)',(i,e['uid'],e['tipo'],e['familia'],e['ativo'],e['excluido'],texto({k:v for k,v in e.items() if k!='geometria'}),e['geometria']))
        for modo,res in [(MODOS[0],r),(MODOS[1],preparada['potencial'])]:con.execute('INSERT INTO WB_RESULTADOS VALUES(?,?)',(modo,texto({k:v for k,v in res.items() if k!='grafo'})))
        for t in ('WB_BASE','WB_ELEMENTOS','WB_RESULTADOS'):con.execute("INSERT INTO gpkg_contents(table_name,data_type,identifier) VALUES(?,'attributes',?)",(t,t))
        if con.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or con.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Base parcial não íntegra')
    # Intermediário preservado e gerenciado; não exige seleção manual.
    j=pasta/'AUDITORIA.json';exportar_json(m,r,j,completo=False)
    dados=json.loads(j.read_text(encoding='utf8'));dados['execucao_uid']=meta['uuid'];j.write_text(texto(dados),encoding='utf8')
    # O pool OGR pode manter aberto o GPKG validado no Windows. Publicar uma
    # cópia SQLite fechada evita mover esse handle sem alterar o pool global.
    publicacao=destino.with_name(destino.stem+'.preparando_'+uuid4().hex+'.gpkg')
    snapshot(parcial,publicacao,cancelar)
    verificar(cancelar);publicacao.rename(destino)
    (pasta/'MANIFESTO.json').write_text(texto(dict(base=str(destino),uuid=meta['uuid'],meta=meta)),encoding='utf8')
    return destino


def criar(fonte,destino,cenario=1,modo=MODOS[1],nome='Modelo',projeto='',anterior=None,referencia=None,cancelar=None):
    destino=Path(destino).resolve()
    if destino.exists():raise FileExistsError(destino)
    pasta=destino.parent/'_tecnicos'/uuid4().hex;pasta.parent.mkdir(parents=True,exist_ok=True)
    return persistir(extrair(fonte,cenario,modo,pasta,nome,projeto,anterior,referencia,cancelar),destino,cancelar)


def metadados(base):
    with abrir_ro(base) as con:
        row=con.execute('SELECT meta FROM WB_BASE').fetchone()
        if not row:raise ValueError('Base topológica sem identificação')
        return json.loads(row[0])


def elementos(base,limite=200,offset=0):
    if limite<0 or limite>1000 or offset<0:raise ValueError('Paginação inválida')
    with abrir_ro(base) as con:
        return [json.loads(r[0]) for r in con.execute('SELECT dados FROM WB_ELEMENTOS ORDER BY id LIMIT ? OFFSET ?',(limite,offset))]


def restaurar(base,cancelar=None):
    meta=metadados(base)
    with abrir_ro(base) as con:
        m=decodificar(json.loads(con.execute('SELECT modelo FROM WB_BASE').fetchone()[0]));m['elementos']={}
        for i,d,g in con.execute('SELECT id,dados,geometria FROM WB_ELEMENTOS'):
            verificar(cancelar);e=decodificar(json.loads(d));e['geometria']=g;m['elementos'][i]=e
        salvos={modo:json.loads(d) for modo,d in con.execute('SELECT modo,dados FROM WB_RESULTADOS')}
    r=analisar(m);p=analisar(m,MODOS[1])
    for modo,atual in [(MODOS[0],r),(MODOS[1],p)]:
        for campo in ('conexoes','componentes','resumo','diagnosticos'):
            presente,anterior=atual[campo],salvos[modo][campo]
            # SQLite ordena PKs; a ordem de emissão de diagnósticos não é sua
            # identidade. Comparar multiconjuntos conserva inclusive repetições.
            if isinstance(presente,list):presente=sorted(map(texto,presente));anterior=sorted(map(texto,anterior))
            if texto(presente)!=texto(anterior):raise ValueError('Regras atuais não reproduzem o snapshot persistido: '+campo)
    from qgis.core import QgsCoordinateReferenceSystem,QgsGeometry
    gs={};crs=QgsCoordinateReferenceSystem()
    if meta['referencia_espacial']:
        from .espacial import geometrias
        ref=meta['referencia_espacial'];gs,_=geometrias(m,ref['crs'],ref['fator'],ref['fonte']);crs=QgsCoordinateReferenceSystem(ref['crs'])
    json_path=Path(base).parent/'_tecnicos'/meta['uuid']/'AUDITORIA.json'
    # O caminho de extração não é identidade. Intermediários são materializados
    # novamente, apenas se necessários à integração, a partir deste GPKG.
    return dict(modelo=m,estrutural=r,potencial=p,geometrias=gs,crs=crs,metrica=bool(meta['referencia_espacial']),meta_base=meta,persistido=dict(modelo={k:v for k,v in m.items() if k!='elementos'},resultado=salvos[MODOS[0]],execucao_uid=meta['uuid']))


def comparar(antes,depois):
    a=restaurar(antes);b=restaurar(depois)
    return comparar_contextos(a,b)


def comparar_contextos(a,b):
    if a['meta_base']['modelo_uid']!=b['meta_base']['modelo_uid']:raise ValueError('São modelos distintos; correspondência não estabelecida')
    ea,eb=a['modelo']['elementos'],b['modelo']['elementos'];comuns=set(ea)&set(eb)
    alterados={campo:sorted(i for i in comuns if ea[i].get(campo)!=eb[i].get(campo)) for campo in ('geometria','topologia','ativo','excluido','tipo','atributos','estados','alternativas')}
    def links(t):return {(c['id'],c['inicio'],c['fim']) for c in t['estrutural']['conexoes']}
    def grupos(t):return [set(c['nos'])|set(c['tubulacoes']) for c in t['estrutural']['componentes']]
    ga,gb=grupos(a),grupos(b)
    def multiplos(origens,destinos):
        indice={e:i for i,g in enumerate(destinos) for e in g}
        return sum(len({indice[e] for e in g if e in indice})>1 for g in origens)
    da={(d['codigo'],d['id'],d.get('relacionado')) for d in a['estrutural']['diagnosticos']};db={(d['codigo'],d['id'],d.get('relacionado')) for d in b['estrutural']['diagnosticos']}
    detalhes_a={(d['codigo'],d['id'],d.get('relacionado')):texto(d) for d in a['estrutural']['diagnosticos']};detalhes_b={(d['codigo'],d['id'],d.get('relacionado')):texto(d) for d in b['estrutural']['diagnosticos']}
    return dict(origem=a['meta_base']['uuid'],destino=b['meta_base']['uuid'],adicionados=sorted(set(eb)-set(ea)),removidos=sorted(set(ea)-set(eb)),alterados=alterados,
        conexoes_adicionadas=sorted(links(b)-links(a)),conexoes_removidas=sorted(links(a)-links(b)),
        componentes_divididos=multiplos(ga,gb),componentes_fundidos=multiplos(gb,ga),
        contexto_anterior={k:a['meta_base'].get(k) for k in ('cenario','hipotese','assinatura')},contexto_atual={k:b['meta_base'].get(k) for k in ('cenario','hipotese','assinatura')},
        diagnosticos_alterados=sorted((k for k in da&db if detalhes_a[k]!=detalhes_b[k]),key=str),
        diagnosticos_novos=sorted(db-da,key=str),diagnosticos_nao_observados=sorted(da-db,key=str),aviso='Não observado não significa corrigido; validar conforme decisões e propostas.')


def importar_legado(origem,destino,nome,projeto,hipotese=MODOS[1],ig_uid=None):
    """Cópia explícita; não afirma recuperar campos ausentes de exportação antiga."""
    destino=Path(destino).resolve()
    if destino.exists():raise FileExistsError(destino)
    pasta=destino.parent/'_tecnicos'/uuid4().hex;pasta.mkdir(parents=True,exist_ok=False)
    prova=snapshot(origem,pasta/'legado_consistente.gpkg')
    with abrir_ro(prova['snapshot']) as con:integrada=bool(con.execute("SELECT 1 FROM sqlite_master WHERE name='IG_SNAPSHOT'").fetchone())
    if integrada:
        from .saidas_integracao import reabrir
        p=reabrir(prova['snapshot'],ig_uid);t=p['topologia'];m=t['modelo'];gs=p.get('geometrias') or {};crs=p['resultado']['meta']['parametros']['crs'] if gs else None
    else:
        from .contexto_integrado import carregar_topologica
        candidatos=[]
        for j in list(Path(origem).parent.glob('*.json'))+list(Path(origem).parent.parent.glob('*.json')):
            try:
                d=json.loads(j.read_text(encoding='utf8'))
                if not isinstance(d,dict) or not {'modelo','resultado','execucao_uid'}<=set(d):continue
                t=carregar_topologica(j,prova['snapshot']);candidatos.append(t)
            except (ValueError,KeyError,TypeError):continue
        if len(candidatos)!=1:raise ValueError('Pacote legado sem execução JSON única compatível; abra uma investigação integrada completa ou reextraia o SQLite')
        t=candidatos[0];m=t['modelo'];gs=t['geometrias'] if t['metrica'] else {};crs=t['crs'].authid() if gs else None
    ref={}
    if gs:
        ref=dict(crs=crs,fator=1,fonte='Representação métrica preservada na auditoria legada; não representa recuperação das coordenadas brutas originais')
        for i,e in m['elementos'].items():
            e['geometria_legada']=e.get('geometria');e['geometria']=bytes(gs[i].asWkb()) if i in gs else None
        m['referencia_espacial']=ref
    r=analisar(m);p=analisar(m,MODOS[1]);meta=dict(uuid=uuid4().hex,tipo='TOPOLOGIA_WG',nome=nome,projeto=projeto,modelo_uid=m['projeto'],versao=1,anterior=None,base_anterior=None,data=datetime.now(timezone.utc).isoformat(),cenario=m['cenario'],hipotese=hipotese,assinatura=assinatura_modelo(m,hipotese),origem=prova,crs=crs,referencia_espacial=ref,extrator='Importação de snapshot legado',regras='Grafo validado; campos não preservados continuam ausentes',codigo={},resumo=r['resumo'],resumo_potencial=p['resumo'],situacao='CONCLUIDA',escopo='LEGADO_PARCIAL — somente dados efetivamente preservados')
    return persistir(dict(sem_alteracao=False,meta=meta,modelo=m,estrutural=r,potencial=p,pasta=str(pasta)),destino)
