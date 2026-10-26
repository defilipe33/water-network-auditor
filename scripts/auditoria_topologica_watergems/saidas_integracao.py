"""Persistência integrada como extensão da base geométrica copiada; origens ro."""
from collections import Counter
from datetime import datetime,timezone
import json
from pathlib import Path
from hashlib import sha256
import sqlite3
from contextlib import closing
from qgis.core import QgsVectorLayer,QgsVectorFileWriter,QgsProject,QgsField,QgsFeature,QgsGeometry,QgsCoordinateReferenceSystem
from qgis.PyQt.QtCore import QVariant
from auditoria_fronteiras.persistencia import exportar_gpkg
from auditoria_fronteiras.versoes import abrir_ro
from .saidas import serializavel,exportar_tabelas_xlsx
from .investigacao import checar_cancelamento


def _camada(tipo,nome,crs,campos,linhas):
    campos=list(campos)+[('FEAT_UID',QVariant.String,80)]
    c=QgsVectorLayer(tipo+(f'?crs={crs}' if crs and tipo!='None' else ''),nome,'memory')
    c.dataProvider().addAttributes([QgsField(n,t,len=l) for n,t,l in campos]);c.updateFields();fs=[]
    for geometria,valores in linhas:
        f=QgsFeature(c.fields());f.setAttributes(list(valores)+[sha256(repr((nome,valores)).encode()).hexdigest()])
        if geometria is not None:f.setGeometry(geometria)
        fs.append(f)
    if fs and not c.dataProvider().addFeatures(fs)[0]:raise RuntimeError('Falha na camada integrada '+nome+': '+c.dataProvider().lastError())
    c.updateExtents();return c


def camadas_integradas(pacote):
    r=pacote['resultado'];crs=r['meta']['parametros']['crs'];uid=r['meta']['uid'];saida=[]
    for modo,sufixo in [('ESTRUTURAL','ESTRUTURAL'),('TODAS_VALVULAS_ABERTAS','POTENCIAL')]:
        campos=[('IG_UID',QVariant.String,40),('LOC_UID',QVariant.String,80),('LOCAL',QVariant.String,30),
            ('CLASSE',QVariant.String,65),('N_GIS',QVariant.Int,0),('N_WG',QVariant.Int,0),('N_PARES',QVariant.Int,0),('N_COMP',QVariant.Int,0)]
        linhas=[]
        for l in r['locais']:
            p=l['perspectivas'][modo];registro=l['registro']
            g=QgsGeometry.fromWkt(f"POINT({registro['X']} {registro['Y']})")
            linhas.append((g,[uid,l['uid'],registro['LOCAL'],p['classe'],len(l['tubos_gis']),len(l['tubos_wg']),p['n_pares'],len(p['componentes'])]))
        c=_camada('Point','IG_LOCAIS_'+sufixo,crs,campos,linhas);c.setCustomProperty('integracao/papel','locais');saida.append(c)
    # Geometrias dos 14 pendentes e dos seus candidatos, sem associação por proximidade.
    campos=[('IG_UID',QVariant.String,40),('GIS_UID',QVariant.String,80),('WG_ID',QVariant.String,30),
        ('PAPEL',QVariant.String,25),('SITUACAO',QVariant.String,35),('ORIGEM',QVariant.String,80)]
    linhas=[]
    for p in r['pendencias']:
        if p['geometria_wkb']:
            g=QgsGeometry();g.fromWkb(bytes.fromhex(p['geometria_wkb']));g.convertToMultiType()
            g.get().dropZValue();g.get().dropMValue()  # Visão XY; WKB preservado no snapshot técnico.
            linhas.append((g,[uid,p['gis_uid'],None,'GIS_ORIGINAL',p['situacao'],p['origem']]))
        for i in p['candidatos']:
            g=(pacote.get('geometrias') or {}).get(i)
            if g:
                copia=QgsGeometry(g);copia.convertToMultiType();linhas.append((copia,[uid,p['gis_uid'],str(i),'WG_CANDIDATO',p['situacao'],p['origem']]))
    saida.append(_camada('MultiLineString','IG_PENDENCIAS_GIS',crs,campos,linhas))
    campos=[('IG_UID',QVariant.String,40),('AREA_UID',QVariant.String,80),('TIPO',QVariant.String,254),('CAMADA',QVariant.String,254),('ID_AREA',QVariant.String,80),('EXIBICAO',QVariant.String,254)]
    linhas=[]
    from auditoria_fronteiras.apresentacao import legivel
    for a in pacote['areas']:
        g=QgsGeometry(a['geometria']);g.convertToMultiType();g.get().dropZValue();g.get().dropMValue()
        linhas.append((g,[uid,a['uid'],a['tipo'],a['camada'],legivel(a['id_original']),a['exibicao']]))
    saida.append(_camada('MultiPolygon','IG_LIMITES_CONTEXTO',crs,campos,linhas))
    for c in saida:
        c.setCustomProperty('integracao/uid',uid);c.setCustomProperty('auditoria_fronteiras/resultado',True)
    return saida


def _snapshot(pacote):
    r=pacote['resultado'];t=pacote['topologia']
    return dict(resultado=r,dossie=pacote['dossie'],modelo=t['modelo'],topologia_origem=t['origem'],
        crs_topologico=t['crs'].toWkt(),metrica=t['metrica'],
        geometrias={str(i):bytes(g.asWkb()).hex() for i,g in (pacote.get('geometrias') or {}).items()},
        areas=[dict({k:v for k,v in a.items() if k!='geometria'},geometria_wkb=bytes(a['geometria'].asWkb()).hex()) for a in pacote['areas']])


def salvar_gpkg(pacote,destino,cancelar=None):
    destino=Path(destino).resolve();r=pacote['resultado'];uid=r['meta']['uid']
    if destino.exists():raise FileExistsError('Crie uma nova versão; destino já existe')
    parcial=destino.with_name(destino.stem+'_'+uid[:8]+'_preparando.gpkg')
    if parcial.exists():raise FileExistsError(parcial)
    # Infraestrutura existente: clone completo incluindo versões, vínculos e revisões.
    exportar_gpkg(parcial,pacote['dossie'],base_origem=r['meta']['geo']['base'])
    for c in camadas_integradas(pacote):
        checar_cancelamento(cancelar)
        with closing(sqlite3.connect(parcial)) as con:existe=con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(c.name(),)).fetchone()
        o=QgsVectorFileWriter.SaveVectorOptions();o.driverName='GPKG';o.layerName=c.name()
        o.actionOnExistingFile=QgsVectorFileWriter.AppendToLayerNoNewFields if existe else QgsVectorFileWriter.CreateOrOverwriteLayer
        erro=QgsVectorFileWriter.writeAsVectorFormatV3(c,str(parcial),QgsProject.instance().transformContext(),o)
        if erro[0]!=QgsVectorFileWriter.NoError:raise RuntimeError(str(erro))
    with closing(sqlite3.connect(parcial)) as con,con:
        con.execute('PRAGMA foreign_keys=ON')
        con.executescript('''
        CREATE TABLE IG_EXECUCOES(ig_uid TEXT PRIMARY KEY,geo_uid TEXT NOT NULL REFERENCES EXECUCOES(exe_uid),topo_uid TEXT NOT NULL,data_utc TEXT NOT NULL,regras TEXT NOT NULL,meta TEXT NOT NULL);
        CREATE TABLE IG_SNAPSHOT(ig_uid TEXT PRIMARY KEY REFERENCES IG_EXECUCOES(ig_uid),dados TEXT NOT NULL);
        CREATE TABLE IG_LOCAIS(ig_uid TEXT NOT NULL REFERENCES IG_EXECUCOES(ig_uid),loc_uid TEXT NOT NULL,geo_uid TEXT NOT NULL,classe_estr TEXT NOT NULL,classe_pot TEXT NOT NULL,dados TEXT NOT NULL,PRIMARY KEY(ig_uid,loc_uid),FOREIGN KEY(geo_uid,loc_uid) REFERENCES PONTOS_INVESTIGACAO(EXE_UID,LOC_UID));
        CREATE TABLE IG_PARES(ig_uid TEXT NOT NULL,par_uid TEXT NOT NULL,loc_uid TEXT NOT NULL,modo TEXT NOT NULL,gis_a TEXT NOT NULL,gis_b TEXT NOT NULL,dados TEXT NOT NULL,PRIMARY KEY(ig_uid,par_uid),FOREIGN KEY(ig_uid,loc_uid) REFERENCES IG_LOCAIS(ig_uid,loc_uid));
        CREATE TABLE IG_COMPONENTES(ig_uid TEXT NOT NULL REFERENCES IG_EXECUCOES(ig_uid),modo TEXT NOT NULL,comp_uid TEXT NOT NULL,dados TEXT NOT NULL,PRIMARY KEY(ig_uid,modo,comp_uid));
        CREATE TABLE IG_MEMBROS(ig_uid TEXT NOT NULL,modo TEXT NOT NULL,comp_uid TEXT NOT NULL,wg_id TEXT NOT NULL,familia TEXT NOT NULL,dados TEXT NOT NULL,PRIMARY KEY(ig_uid,modo,comp_uid,wg_id,familia),FOREIGN KEY(ig_uid,modo,comp_uid) REFERENCES IG_COMPONENTES(ig_uid,modo,comp_uid));
        CREATE TABLE IG_ASSOC(ig_uid TEXT NOT NULL REFERENCES IG_EXECUCOES(ig_uid),gis_uid TEXT NOT NULL,wg_id TEXT,situacao TEXT NOT NULL,dados TEXT NOT NULL);
        CREATE TABLE IG_LOCAL_TUBO(ig_uid TEXT NOT NULL,loc_uid TEXT NOT NULL,gis_uid TEXT NOT NULL,PRIMARY KEY(ig_uid,loc_uid,gis_uid),FOREIGN KEY(ig_uid,loc_uid) REFERENCES IG_LOCAIS(ig_uid,loc_uid));
        CREATE TABLE IG_AREAS(ig_uid TEXT NOT NULL REFERENCES IG_EXECUCOES(ig_uid),area_uid TEXT NOT NULL,dados TEXT NOT NULL,PRIMARY KEY(ig_uid,area_uid));
        CREATE TABLE IG_COMP_AREA(ig_uid TEXT NOT NULL,modo TEXT NOT NULL,comp_uid TEXT NOT NULL,area_uid TEXT NOT NULL,PRIMARY KEY(ig_uid,modo,comp_uid,area_uid),FOREIGN KEY(ig_uid,modo,comp_uid) REFERENCES IG_COMPONENTES(ig_uid,modo,comp_uid),FOREIGN KEY(ig_uid,area_uid) REFERENCES IG_AREAS(ig_uid,area_uid));
        CREATE TABLE IG_LOCAL_AREA(ig_uid TEXT NOT NULL,loc_uid TEXT NOT NULL,area_uid TEXT NOT NULL,PRIMARY KEY(ig_uid,loc_uid,area_uid),FOREIGN KEY(ig_uid,loc_uid) REFERENCES IG_LOCAIS(ig_uid,loc_uid),FOREIGN KEY(ig_uid,area_uid) REFERENCES IG_AREAS(ig_uid,area_uid));
        CREATE TABLE IG_COMP_GIS(ig_uid TEXT NOT NULL,modo TEXT NOT NULL,comp_uid TEXT NOT NULL,wg_id TEXT NOT NULL,gis_uid TEXT NOT NULL,origem TEXT NOT NULL,chave TEXT,FOREIGN KEY(ig_uid,modo,comp_uid) REFERENCES IG_COMPONENTES(ig_uid,modo,comp_uid));
        CREATE TABLE IG_FONTES(ig_uid TEXT NOT NULL,modo TEXT NOT NULL,comp_uid TEXT NOT NULL,wg_id TEXT NOT NULL,tipo TEXT NOT NULL,natureza TEXT NOT NULL,fonte_agua INTEGER NOT NULL,FOREIGN KEY(ig_uid,modo,comp_uid) REFERENCES IG_COMPONENTES(ig_uid,modo,comp_uid));
        CREATE TABLE IG_PENDENCIAS(ig_uid TEXT NOT NULL REFERENCES IG_EXECUCOES(ig_uid),gis_uid TEXT NOT NULL,situacao TEXT NOT NULL,dados TEXT NOT NULL,PRIMARY KEY(ig_uid,gis_uid));
        CREATE TABLE IG_LOCAL_CLASSES(ig_uid TEXT NOT NULL,loc_uid TEXT NOT NULL,modo TEXT NOT NULL,classe TEXT NOT NULL,PRIMARY KEY(ig_uid,loc_uid,modo,classe),FOREIGN KEY(ig_uid,loc_uid) REFERENCES IG_LOCAIS(ig_uid,loc_uid));
        '''.replace('CREATE TABLE IG_','CREATE TABLE IF NOT EXISTS IG_'))
        texto=lambda x:json.dumps(x,ensure_ascii=False,default=serializavel)
        meta=r['meta'];con.execute('INSERT INTO IG_EXECUCOES VALUES(?,?,?,?,?,?)',(uid,meta['geo']['execucao_uid'],meta['topologia']['execucao_uid'],meta['data'],meta['regras'],texto(meta)))
        con.execute('INSERT INTO IG_SNAPSHOT VALUES(?,?)',(uid,texto(_snapshot(pacote))))
        for l in r['locais']:
            con.execute('INSERT INTO IG_LOCAIS VALUES(?,?,?,?,?,?)',(uid,l['uid'],meta['geo']['execucao_uid'],l['perspectivas']['ESTRUTURAL']['classe'],l['perspectivas']['TODAS_VALVULAS_ABERTAS']['classe'],texto(l)))
            con.executemany('INSERT INTO IG_LOCAL_TUBO VALUES(?,?,?)',[(uid,l['uid'],t) for t in l['tubos_gis']])
        for p in r['pares']:con.execute('INSERT INTO IG_PARES VALUES(?,?,?,?,?,?,?)',(uid,p['uid'],p['local_uid'],p['modo'],p['gis_a'],p['gis_b'],texto(p)))
        for modo,cs,ms in [('ESTRUTURAL',r['componentes'],r['membros']),('TODAS_VALVULAS_ABERTAS',r['componentes_potenciais'],r['membros_potenciais'])]:
            con.executemany('INSERT INTO IG_COMPONENTES VALUES(?,?,?,?)',[(uid,modo,c['uid'],texto(c)) for c in cs])
            con.executemany('INSERT INTO IG_MEMBROS VALUES(?,?,?,?,?,?)',[(uid,modo,m['comp_uid'],str(m['id']),m['familia'],texto(m)) for m in ms])
        associacoes={a['gis_uid']:a for l in r['locais'] for a in l['correspondencias']}
        for a in associacoes.values():
            for i in a['candidatos'] or [None]:con.execute('INSERT INTO IG_ASSOC VALUES(?,?,?,?,?)',(uid,a['gis_uid'],None if i is None else str(i),a['situacao'],texto(a)))
        for a in r['associacoes_componentes']:con.execute('INSERT INTO IG_COMP_GIS VALUES(?,?,?,?,?,?,?)',(uid,'ESTRUTURAL',a['comp_uid'],str(a['wg_id']),a['gis_uid'],a['origem'],str(a['chave'])))
        for modo,fs in [('ESTRUTURAL',r['fontes']),('TODAS_VALVULAS_ABERTAS',r['fontes_potenciais'])]:
            con.executemany('INSERT INTO IG_FONTES VALUES(?,?,?,?,?,?,?)',[(uid,modo,f['comp_uid'],str(f['id']),f['tipo'],f['natureza'],int(f['fonte_agua'])) for f in fs])
        for p in r['pendencias']:con.execute('INSERT INTO IG_PENDENCIAS VALUES(?,?,?,?)',(uid,p['gis_uid'],p['situacao'],texto(p)))
        for l in r['locais']:
            for modo,v in l['perspectivas'].items():con.executemany('INSERT INTO IG_LOCAL_CLASSES VALUES(?,?,?,?)',[(uid,l['uid'],modo,c) for c in v['classes'] or ['SEM_PAR_COMPARAVEL']])
        for a in pacote['areas']:
            d={k:v for k,v in a.items() if k!='geometria'};d['geometria_wkb']=bytes(a['geometria'].asWkb()).hex()
            con.execute('INSERT INTO IG_AREAS VALUES(?,?,?)',(uid,a['uid'],texto(d)))
        for c in r['componentes']:
            con.executemany('INSERT INTO IG_COMP_AREA VALUES(?,?,?,?)',[(uid,'ESTRUTURAL',c['uid'],a) for a in set(c['areas'])])
        for l in r['locais']:con.executemany('INSERT INTO IG_LOCAL_AREA VALUES(?,?,?)',[(uid,l['uid'],a) for a in set(l['areas'])])
        for tabela in ('IG_EXECUCOES','IG_LOCAIS','IG_PARES','IG_COMPONENTES','IG_MEMBROS','IG_ASSOC','IG_LOCAL_TUBO','IG_AREAS','IG_COMP_AREA','IG_LOCAL_AREA','IG_COMP_GIS','IG_FONTES','IG_PENDENCIAS','IG_LOCAL_CLASSES'):
            con.execute("INSERT OR IGNORE INTO gpkg_contents(table_name,data_type,identifier,description,last_change) VALUES(?,'attributes',?,'Investigação integrada',?)",(tabela,tabela,datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')))
        if con.execute('PRAGMA foreign_key_check').fetchall():raise RuntimeError('Relacionamentos integrados inválidos')
    checar_cancelamento(cancelar)
    with closing(sqlite3.connect(parcial)) as con:
        if con.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Base parcial inválida; origens preservadas')
    parcial.rename(destino)
    return destino


def reabrir(gpkg,ig_uid=None):
    with abrir_ro(gpkg) as con:
        if ig_uid is None:
            ids=con.execute('SELECT ig_uid FROM IG_EXECUCOES').fetchall()
            if len(ids)!=1:raise ValueError('Selecione explicitamente a versão integrada')
            ig_uid=ids[0][0]
        row=con.execute('SELECT dados FROM IG_SNAPSHOT WHERE ig_uid=?',(ig_uid,)).fetchone()
        if not row:raise ValueError('Versão integrada inexistente')
        s=json.loads(row[0])
    m=s['modelo'];m['elementos']={int(i):e for i,e in m['elementos'].items()}
    for e in m['elementos'].values():e['geometria']=bytes.fromhex(e['geometria']['wkb_hex']) if isinstance(e['geometria'],dict) else None
    from .topologia import analisar
    geoms={}
    for i,wkb in s['geometrias'].items():g=QgsGeometry();g.fromWkb(bytes.fromhex(wkb));geoms[int(i)]=g
    areas=[]
    for a in s['areas']:
        g=QgsGeometry();g.fromWkb(bytes.fromhex(a.pop('geometria_wkb')));areas.append(dict(a,geometria=g))
    from auditoria_fronteiras.persistencia import carregar_execucao
    with abrir_ro(gpkg) as con:d=carregar_execucao(gpkg,s['resultado']['meta']['geo']['execucao_uid'],conexao=con)
    t=dict(modelo=m,estrutural=analisar(m),potencial=analisar(m,'TODAS_VALVULAS_ABERTAS'),origem=s['topologia_origem'],crs=QgsCoordinateReferenceSystem(s['crs_topologico']),metrica=s['metrica'])
    return dict(resultado=s['resultado'],dossie=d,topologia=t,geometrias=geoms or None,areas=areas)


def tabelas_integracao(pacote):
    r=pacote['resultado'];modelo=pacote['topologia']['modelo'];el=modelo['elementos']
    def comp_linhas(cs):
        return [(c['numero'],c['uid'],c['porte'],c['n_nos'],c['n_tubos'],c['n_dispositivos'],
            '; '.join(map(str,c['reservatorios'])),'; '.join(map(str,c['tanques'])),'; '.join(map(str,c['bombas'])),
            len(c['extremidades']),len(c['referencias_incompletas']),c['distancia_m'],c.get('n_tubos_gis_validados',0),c['interpretacao_fonte']) for c in cs]
    campos=('NUMERO','COMP_UID','PORTE','NOS','TUBOS','DISPOSITIVOS','RESERVATORIOS','TANQUES','BOMBAS','EXTREMIDADES','REF_PEND','DISTANCIA_M','GIS_VALIDADOS','INTERPRETACAO')
    abas={'RESUMO':(('INDICADOR','VALOR'),[('Integração',r['meta']['uid']),('Geo origem',r['meta']['geo']['execucao_uid']),('Topologia origem',r['meta']['topologia']['execucao_uid']),
        ('Componentes estruturais',len(r['componentes'])),('Locais',len(r['locais'])),('Tubos GIS pendentes',len(r['pendencias'])),('Conferência WaterGEMS','PENDENTE'),
        ('Perspectivas','Estrutural inclui inativos; hipótese aberta respeita atividade e bloqueia bombas de estado desconhecido. Diferença não é diagnóstico de válvula fechada.')]),
        'COMPONENTES':(campos,comp_linhas(r['componentes'])),
        'NOS_ISOLADOS':(campos,comp_linhas([c for c in r['componentes'] if not c['n_tubos']])),
        'UMA_TUBULACAO':(campos,comp_linhas([c for c in r['componentes'] if c['n_tubos']==1])),
        'PEQUENAS_REDES':(campos,comp_linhas([c for c in r['componentes'] if 2<=c['n_tubos']<100])),
        'GRANDES_REDES':(campos,comp_linhas([c for c in r['componentes'] if c['n_tubos']>=100])),
        'MEMBROS':(('COMP_UID','WG_ID','LABEL','TIPO','FAMILIA','ATIVO','DIAGNOSTICOS'),[(m['comp_uid'],str(m['id']),m['label'],m['tipo'],m['familia'],m['ativo'],'; '.join(m['diagnosticos'])) for m in r['membros']]),
        'FONTES_E_BOMBAS':(('COMP_UID','WG_ID','LABEL','TIPO','NATUREZA','FONTE_AGUA','ATIVO'),[(f['comp_uid'],str(f['id']),f['label'],f['tipo'],f['natureza'],f['fonte_agua'],f['ativo']) for f in r['fontes']]),
        'GIS_PENDENTES':(('GIS_UID','CAMADA','ID_ORIGINAL','CHAVE_CORRELACAO','SITUACAO','CANDIDATOS','ERRO_M','MOTIVOS','GEOMETRIA'),[(p['gis_uid'],p['camada'],p['id_exibido'],p['chave_correlacao'],p['situacao'],'; '.join(map(str,p['candidatos'])),p['erro_xy_m'],'; '.join(p['motivos']),p['geometria_status']) for p in r['pendencias']]),
        'VINCULOS_PENDENTES':(('GIS_UID','EVENTO_UID','LOCAL_UID','SITUACAO'),[(p['gis_uid'],e,l,p['situacao']) for p in r['pendencias'] for e in p['eventos'] for l in p['locais'] if any(v['evento_uid']==e and v['local_uid']==l for v in pacote['dossie']['local_evento'])]),
        'LOCAIS':(('LOCAL','LOC_UID','N_GIS','N_WG','ESTRUTURAL','POTENCIAL','PENDENCIAS'),[(l['registro']['LOCAL'],l['uid'],len(l['tubos_gis']),len(l['tubos_wg']),l['perspectivas']['ESTRUTURAL']['classe'],l['perspectivas']['TODAS_VALVULAS_ABERTAS']['classe'],'; '.join(l['pendencias'])) for l in r['locais']]),
        'PROXIMIDADES':(('COMP_UID','VIZINHO_UID','DISTANCIA_M','CRITERIO'),[(v['comp_uid'],v['vizinho_uid'],v['distancia_m'],v['criterio']) for v in r['vizinhos']]),
        'CONFERENCIA_MANUAL':(('TIPO','COMP_UID','LOCAL_UID','WG_ID','LABEL','ESPERADO'),[(m['tipo'],m['comp_uid'],m['local_uid'],str(m['wg_id']) if m['wg_id'] is not None else None,m['label'],m['esperado']) for m in r['manual']]),
        'AREAS':(('AREA_UID','TIPO','CAMADA','ID_AREA','EXIBICAO','CAMPO_ID','CAMPO_EXIB'),[(a['uid'],a['tipo'],a['camada'],str(a['id_original']),a['exibicao'],a['campo_id'],a['campo_nome']) for a in pacote['areas']]),
        'COMPONENTE_AREA':(('COMP_UID','AREA_UID','CRITERIO'),[(c['uid'],a,'INTERSECAO_ESPACIAL_SEM_PRECEDENCIA') for c in r['componentes'] for a in c['areas']]),
        'LOCAL_AREA':(('LOCAL_UID','AREA_UID','CRITERIO'),[(l['uid'],a,'INTERSECAO_ESPACIAL_SEM_PRECEDENCIA') for l in r['locais'] for a in l['areas']]),
        'COMPONENTE_GIS':(('COMP_UID','WG_ID','GIS_UID','ORIGEM','CHAVE','SITUACAO'),[(a['comp_uid'],str(a['wg_id']),a['gis_uid'],a['origem'],a['chave'],a['situacao']) for a in r['associacoes_componentes']]),
        'ORIGENS_CONEXOES':(('WG_ID','LABEL','NO_INICIO','NO_FIM','FONTE_INICIO','FONTE_FIM','CENARIO'),[(str(c['id']),el[c['id']]['label'],str(c['inicio']),str(c['fim']),c['inicio_fonte'],c['fim_fonte'],str(modelo['cenario'])) for c in pacote['topologia']['estrutural']['conexoes']])}
    for modo,nome in [('ESTRUTURAL','PARES_ESTRUTURAIS'),('TODAS_VALVULAS_ABERTAS','PARES_POTENCIAIS')]:
        abas[nome]=(('LOCAL_UID','GIS_A','GIS_B','WG_A','WG_B','CLASSES','NOS_COMUNS','CAMINHO_AB','CAMINHO_BA','ALTERNATIVA','DISPOSITIVOS','MOTIVOS'),[
            (p['local_uid'],p['gis_a'],p['gis_b'],'; '.join(map(str,p['wg_a'])),'; '.join(map(str,p['wg_b'])),'; '.join(p['classes']),'; '.join(map(str,p['nos_compartilhados'])),
             p['caminho_ab'] is not None,p['caminho_ba'] is not None,p['alternativa_sem_nos_compartilhados'],'; '.join(map(str,p['dispositivos'])),'; '.join(p['motivos'])) for p in r['pares'] if p['modo']==modo])
    return abas


def exportar_relatorios(pacote,pasta,xlsx=True,shp=True):
    import csv
    pasta=Path(pasta);pasta.mkdir(parents=True,exist_ok=False)
    abas=tabelas_integracao(pacote)
    if xlsx:exportar_tabelas_xlsx(abas,pasta/'INVESTIGACAO_INTEGRADA.xlsx',larguras={
        'COMP_UID':65,'LOC_UID':65,'LOCAL_UID':65,'GIS_UID':65,'ESTRUTURAL':65,'POTENCIAL':65,'CLASSES':70,'MOTIVOS':80,'INTERPRETACAO':80,'ESPERADO':80})
    if shp:
        from .saidas import exportar_geografico
        exportar_geografico(camadas_integradas(pacote),pasta/'SHP','SHP',campo_chave='FEAT_UID')
        dicionario={
            'FEAT_UID':'Chave da representação exportada; não é identificador hidráulico.',
            'IG_UID':'Execução integrada. Relaciona todas as tabelas deste pacote.',
            'LOC_UID':'Chave técnica do local na auditoria geométrica de origem.',
            'LOCAL':'Identificador legível do local; não usar sozinho como chave.',
            'CLASSE':'Classificação investigativa principal nesta perspectiva.',
            'N_GIS':'Quantidade de tubulações GIS distintas no local.',
            'N_WG':'Quantidade de candidatos WaterGEMS preservados.',
            'N_PARES':'Quantidade de pares analisados nesta perspectiva.',
            'N_COMP':'Quantidade de componentes envolvidos nesta perspectiva.',
            'GIS_UID':'Chave técnica da tubulação GIS, preservando sua origem.',
            'WG_ID':'DomainElementID do candidato WaterGEMS; texto preservado.',
            'PAPEL':'GIS_ORIGINAL ou WG_CANDIDATO; não comprova correspondência.',
            'SITUACAO':'Situação da correspondência cadastral.',
            'ORIGEM':'Referência técnica da fonte GIS.',
            'AREA_UID':'Chave técnica do polígono contextual consultado.',
            'TIPO':'Tipo de limite configurado pelo usuário.',
            'CAMADA':'Camada de origem do polígono.',
            'ID_AREA':'Identificador original do polígono, apresentado como texto.',
            'EXIBICAO':'Valor do campo de exibição escolhido pelo usuário.'}
        with (pasta/'SHP'/'DICIONARIO_INTEGRACAO.json').open('x',encoding='utf8') as f:
            json.dump(dict(campos=dicionario,relacoes='Consultar CSVs LOCAL_AREA, COMPONENTE_AREA, COMPONENTE_GIS, VINCULOS_PENDENTES e o GPKG completo. Não reconstruir vínculos por listas textuais.',
                geometria='Visão XY no CRS registrado; WKB original preservado no GPKG. Arquivos de auditoria, sem criação de elementos hidráulicos.'),f,ensure_ascii=False,indent=2)
    for nome,(campos,linhas) in abas.items():
        with (pasta/(nome+'.csv')).open('x',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f,delimiter=';');w.writerow(campos);w.writerows(linhas)
    with (pasta/'INVESTIGACAO_TECNICA.json').open('x',encoding='utf8') as f:json.dump(pacote['resultado'],f,ensure_ascii=False,default=serializavel)
    return pasta
