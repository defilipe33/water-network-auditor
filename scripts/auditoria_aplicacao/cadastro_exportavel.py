"""Inventário cadastral e prévia derivada para conferência antes do ModelBuilder."""

from collections import Counter
from contextlib import closing
from itertools import chain
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from uuid import uuid4

from auditoria_fronteiras.entradas import digest
from auditoria_fronteiras.modelos import verificar_cancelamento
from .dependencias_gis import RedeGIS
from .exportar_macro_origem import NOS, PIPES, _csv, _vetor
from .topologia_derivada import preparar as materializar


VERSAO=1
ATIVIDADES=('ATIVO','INATIVO','A_DEFINIR')
PIPE_CAMPOS={k:v for k,v in PIPES.items() if k not in ('bloco','corredor','continuidade')}
PIPE_CAMPOS.update(camada='camada', procedencia='proced', situacao='situacao',
                   participacao='particip', condicao_topologica='cond_topo', atividade='atividade')


def _condicao(foto,origens,cancelar):
    if not foto['arestas']:return {}
    r=RedeGIS(foto,origens,cancelar)
    etiquetas,grupos=r.componentes(cancelar=cancelar)
    maiores=max((len(nos) for nos,_ in grupos),default=0)
    por_parte={}
    for e,(a,_,_,_) in zip(foto['arestas'],r.arestas):
        i=etiquetas[a]
        ns,bits=grupos[i]
        por_parte.setdefault(e['tubo'],set()).add((
            'COM_ORIGEM' if bits else 'SEM_ORIGEM' if r.origens else 'INDETERMINADO',
            'ISOLADO' if len(ns)<maiores else 'COMPONENTE_PRINCIPAL'))
    return por_parte


def preparar(foto,inventario,*,modo_atividade='A_DEFINIR',atividades=None,contagem=None,origens=None,cancelar=None):
    """Relaciona o universo cadastral à fotografia somente por identidade de parte."""
    if modo_atividade not in ('A_DEFINIR','FORA_INATIVO','NA_HIPOTESE_ATIVO'):
        raise ValueError('Escolha uma regra de atividade pretendida compatível.')
    atividades=atividades or {}
    if set(atividades.values())-set(ATIVIDADES):
        raise ValueError('Há uma atividade pretendida desconhecida.')
    tubos,junctions,equipamentos,_,avisos=inventario
    originais={t['uid']:t for t in tubos}
    partes={t['uid']:t for t in foto['tubos']}
    resolucoes=foto.get('resolucoes_conexoes',{})
    propostas=set(foto.get('propostas_aplicadas',()))
    complementos={r['uuid']:r for r in foto.get('participantes',()) if r['tipo']=='PIPE'}
    indices=[i for i,e in enumerate(foto['arestas']) if e['tubo'] in originais
             or partes[e['tubo']].get('proposta_uid') in propostas]
    pipes,nos,divisoes,pendencias=materializar(foto,cancelar,indices=indices)
    no_por_uid={n['uid']:dict(n) for n in nos}
    condicao=_condicao(foto,origens,cancelar)
    usadas={p['parte'] for p in pipes}
    sem_inventario=sorted(set(partes)-usadas-set(originais))
    for u in sem_inventario:
        pendencias.append(dict(parte=u,motivo='Parte da fotografia sem identidade correspondente no inventário atual.'))
    for u,t in originais.items():
        verificar_cancelamento(cancelar)
        if u in usadas:continue
        g=t['geom']
        extremos=g.asPolyline()
        if len(extremos)<2:
            pendencias.append(dict(parte=u,motivo='Geometria sem início e fim materializáveis.'))
            continue
        ids=[]
        for lado,p in enumerate((extremos[0],extremos[-1])):
            no=digest(['no-cadastro-externo',u,lado])
            ids.append(no)
            no_por_uid[no]=dict(uid=no,xy=[p.x(),p.y()],portas=[[u,float(lado)]],natureza='EXTREMIDADE_NAO_ANALISADA')
        pipes.append(dict(uid=digest(['segmento_gis',u,0.,1.]),original=t['feicao'],parte=u,gis_id=t['id'],
                          no_a=ids[0],no_b=ids[1],inicio=0.,fim=1.,comprimento_m=g.length(),
                          diametro_mm=t.get('diametro_mm'),material=t.get('material'),fontes=t['fontes'],
                          proposta=None,natureza='CADASTRO',wkb=bytes(g.asWkb())))
    identidades=set()
    for r in pipes:
        verificar_cancelamento(cancelar)
        u=r['parte']
        t=originais.get(u,partes.get(u,{}))
        dentro=u in usadas
        alcance=condicao.get(u,())
        natureza=r['natureza']
        proposta=r.get('proposta')
        contexto=complementos.get(proposta,{})
        estado=contexto.get('situacao','PROPOSTA')
        prov=('CADASTRO_COMPLEMENTAR' if estado in ('INFORMADA','A_CONFIRMAR') else 'INTERVENCAO_USUARIO') if proposta else (
            'DERIVADO' if natureza=='DIVISAO_VIRTUAL' else 'GIS_ORIGINAL')
        situacao=({'INFORMADA':'EXISTENTE_INFORMADO','A_CONFIRMAR':'EXISTENTE_A_CONFIRMAR',
                   'HIPOTETICA':'HIPOTETICO'}.get(estado,'PROPOSTO') if proposta else 'EXISTENTE_CADASTRADO')
        estados={x[0] for x in alcance}
        topologia=('PARCIAL' if len(estados)>1 else next(iter(estados))) if dentro and estados else 'NAO_ANALISADO'
        regra=('INATIVO' if modo_atividade=='FORA_INATIVO' and not dentro else
               'ATIVO' if modo_atividade=='NA_HIPOTESE_ATIVO' and dentro else 'A_DEFINIR')
        r.update(label=t.get('label'),camada=t.get('camada'),procedencia=prov,
                 situacao=situacao,
                 participacao='INCLUIDO' if dentro else 'NAO_INCLUIDO',
                 condicao_topologica=topologia,componente=sorted({x[1] for x in alcance}) if dentro else [],
                 atividade=atividades.get(r['original'],regra),revisao_intervencao=contexto.get('rev'))
        if r['uid'] in identidades:raise ValueError('A prévia contém segmentos com identidade duplicada.')
        identidades.add(r['uid'])
    vinculadas={p[1] for n in no_por_uid.values() for p in n['portas'] if p[0]=='J'}
    for j in junctions:
        verificar_cancelamento(cancelar)
        if j['uid'] in vinculadas:continue
        p=j['geom'].asPoint()
        u=digest(['junction-cadastral-nao-analisada',j['uid']])
        no_por_uid[u]=dict(uid=u,xy=[p.x(),p.y()],portas=[['J',j['uid']]],natureza='JUNCTION_CADASTRADA')
    participantes=[dict(r,resultado=resolucoes.get(r['uuid'],'CONSIDERADO'))
                   for r in foto.get('participantes',()) if r['tipo'] in ('CONEXAO','PIPE','ORIGEM')]
    metr=dict(Counter(r['atividade'] for r in pipes))
    cobertura=dict(pipes_originais=len({t['feicao'] for t in tubos}),
                   originais_materializados=len({r['original'] for r in pipes if not r['proposta']}),
                   pipes_divididos=len({p['original'] for p in pipes if p['natureza']=='DIVISAO_VIRTUAL'}),
                   segmentos=len(pipes),segmentos_derivados=sum(r['natureza']=='DIVISAO_VIRTUAL' for r in pipes),
                   complementares=len({r['proposta'] for r in pipes if r['proposta']}),
                   fora_da_hipotese=sum(r['participacao']=='NAO_INCLUIDO' for r in pipes),
                   sem_origem=sum(r['condicao_topologica']=='SEM_ORIGEM' for r in pipes),
                   atividade=metr,junctions=len(no_por_uid),equipamentos=len(equipamentos),
                   conexoes_aplicadas=sum(x=='APLICADA' for x in resolucoes.values()),
                   conexoes_pendentes=sum(x not in ('APLICADA','SEPARADA') for x in resolucoes.values()),
                   sem_diametro=sum(r['diametro_mm'] is None for r in pipes))
    cadastro=[{k:t.get(k) for k in ('uid','feicao','categoria','id','label','fontes','camada','classificacao',
                                   'origem','atributos_originais')} for t in chain(tubos,junctions,equipamentos)]
    manifesto=dict(versao=VERSAO,escopo='CADASTRO_COMPLETO',projeto=foto['projeto_uid'],execucao=foto['uuid'],
                   hipotese=foto.get('hipotese'),crs=foto['crs'],unidades={'comprimento':'m','diametro':'mm'},
                   origens=foto['origens_validas'] if origens is None else origens,
                   regra_atividade=modo_atividade,contagens=cobertura,fontes=contagem or {},avisos=avisos,
                   pendencias=pendencias,divisoes=divisoes,
                   lacunas=bool(avisos or pendencias or cobertura['originais_materializados']!=cobertura['pipes_originais']))
    eq_topologia={r['uid']:r for r in foto.get('equipamentos',())}
    eqs=[dict(r,declaracoes=eq_topologia.get(r['uid'],{}).get('declaracoes',[]),
              participacao='INCLUIDO' if r['uid'] in eq_topologia else 'NAO_INCLUIDO',
              atividade='A_DEFINIR',procedencia='GIS_ORIGINAL') for r in equipamentos]
    return dict(pipes=pipes,nos=list(no_por_uid.values()),cadastro=cadastro,operacoes=participantes,
                equipamentos=eqs,manifesto=manifesto)


def exportar(previa,pasta,formato,cancelar=None,etapa=lambda *_:None):
    from osgeo import ogr, osr

    if formato not in ('GPKG','ESRI Shapefile'):raise ValueError('Escolha GeoPackage ou Shapefile.')
    m=previa['manifesto']
    crs=osr.SpatialReference()
    if crs.SetFromUserInput(m['crs'])!=0:raise ValueError('CRS de exportação inválido.')
    pipes,nos=previa['pipes'],previa['nos']
    destino=Path(pasta)/('Cadastro_modelagem_'+m['execucao'][:8]+'_'+uuid4().hex[:8])
    etapa(0,'Gravando cadastro, derivados e tabelas de procedência')
    with TemporaryDirectory(prefix='.cadastro_',dir=pasta) as arq:
        saida=Path(arq)/'saida'
        saida.mkdir()
        gpkg=saida/'cadastro_modelagem.gpkg'
        ds=None
        try:
            if formato=='GPKG':ds=ogr.GetDriverByName(formato).CreateDataSource(str(gpkg))
            _vetor(saida,formato,'pipes',ogr.wkbLineString,PIPE_CAMPOS,pipes,crs,cancelar,ds)
            _vetor(saida,formato,'junctions',ogr.wkbPoint,NOS,nos,crs,cancelar,ds)
        finally:
            if ds is not None:ds.Destroy()
        tabelas={
            'inventario_cadastral':previa['cadastro'],
            'operacoes_topologicas':previa['operacoes'],
            'estado_pipe':[{k:v for k,v in r.items() if k!='wkb'} for r in pipes],
            'portas_junction':nos,
            'equipamentos_inventariados':previa['equipamentos'],
            'validacao': [m],
        }
        if formato=='GPKG':
            with closing(sqlite3.connect(gpkg)) as con, con:
                for nome,rs in tabelas.items():
                    con.execute(f'CREATE TABLE {nome} (fid INTEGER PRIMARY KEY, uid TEXT, dados_json TEXT NOT NULL)')
                    con.execute('INSERT INTO gpkg_contents (table_name,data_type,identifier) VALUES (?,?,?)',
                                (nome,'attributes',nome))
                    for r in rs:
                        verificar_cancelamento(cancelar)
                        con.execute(f'INSERT INTO {nome} (uid,dados_json) VALUES (?,?)',
                                    (r.get('uid',r.get('uuid')),json.dumps(r,ensure_ascii=False)))
        _csv(saida,'pipes',(*PIPE_CAMPOS,'fontes','componente'),pipes,cancelar)
        _csv(saida,'junctions',(*NOS,'xy','portas'),nos,cancelar)
        _csv(saida,'inventario_cadastral',('uid','feicao','id','label','categoria','fontes','camada','atributos_originais'),
             previa['cadastro'],cancelar)
        (saida/'operacoes_topologicas.json').write_text(json.dumps(previa['operacoes'],ensure_ascii=False),encoding='utf-8')
        if formato=='ESRI Shapefile':
            m=dict(m,dicionario_shp={'pipes':PIPE_CAMPOS,'junctions':NOS})
        (saida/'validacao.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
        verificar_cancelamento(cancelar)
        saida.rename(destino)
    return destino
