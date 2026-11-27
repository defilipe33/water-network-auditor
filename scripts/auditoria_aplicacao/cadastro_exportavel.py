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
from . import conjuntos_modelagem as conjuntos
from .exportar_macro_origem import NOS, PIPES, REAIS, _csv, _vetor
from .topologia_derivada import preparar as materializar
from .publicar_pasta_gis import publicar
from .valores_exportacao_gis import normalizar


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
    pipes,nos,divisoes,pendencias=materializar(foto,cancelar,indices=indices,tolerar_pontas=True)
    no_por_uid={n['uid']:dict(n) for n in nos}
    ids_foto={n['uid'] for n in foto['nos']}
    topologia_incompleta=any(e.get('a') not in ids_foto or e.get('b') not in ids_foto for e in foto['arestas'])
    condicao={} if topologia_incompleta else _condicao(foto,origens,cancelar)
    if topologia_incompleta:
        pendencias.append(dict(motivo='Existem pontas sem nó na fotografia. A condição de alcance ficou indeterminada.'))
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
    junctions_cadastrais={j['uid']:j for j in junctions}
    for n in no_por_uid.values():
        verificar_cancelamento(cancelar)
        refs={p[1] for p in n['portas'] if p[0]=='J'}
        if len(refs)==1 and (j:=junctions_cadastrais.get(next(iter(refs)))):
            n.update(original=j['feicao'],gis_id=j.get('id'),label=j.get('label'),camada=j.get('camada'),
                     procedencia='GIS_ORIGINAL',situacao='EXISTENTE_CADASTRADO')
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
                   atividades_explicitas=atividades,
                   pendencias=pendencias,divisoes=divisoes,
                   lacunas=bool(avisos or pendencias or cobertura['originais_materializados']!=cobertura['pipes_originais']))
    eq_topologia={r['uid']:r for r in foto.get('equipamentos',())}
    eqs=[dict(r,declaracoes=eq_topologia.get(r['uid'],{}).get('declaracoes',[]),
              participacao='INCLUIDO' if r['uid'] in eq_topologia else 'NAO_INCLUIDO',
              atividade='A_DEFINIR',procedencia='GIS_ORIGINAL') for r in equipamentos]
    previa=dict(pipes=pipes,nos=list(no_por_uid.values()),cadastro=cadastro,operacoes=participantes,
                equipamentos=eqs,manifesto=manifesto)
    manifesto['assinatura_topologia_exportavel']=conjuntos.assinatura(previa)
    return previa


def validar_modelbuilder(previa,configuracao,*,selecoes=(),escopo=None,cancelar=None):
    from .modelbuilder_gis import preparar
    previa=_normalizar_previa(previa,cancelar)
    pipes,nos,_,associacoes=conjuntos.preparar_exportacao(previa,selecoes,escopo=escopo,cancelar=cancelar)
    _,_,_,pendencias,meta=preparar(previa,pipes,nos,associacoes,dict(configuracao,validar=True),cancelar)
    return pendencias,meta


def _normalizar_previa(previa,cancelar):
    pendencias=[]
    dados={}
    for k in ('cadastro','equipamentos','operacoes','nos','pipes'):
        dados[k]=[]
        for i,r in enumerate(previa[k]):
            verificar_cancelamento(cancelar)
            geom=r.get('wkb') if k=='pipes' else None
            d=normalizar({key:v for key,v in r.items() if key!='wkb' or k!='pipes'},
                         pendencias,f"{k}.{r.get('uid') or i}")
            if k=='pipes':d['wkb']=geom
            dados[k].append(d)
    m=normalizar(previa['manifesto'],pendencias,'manifesto')
    m['serializacao_pendencias']=pendencias
    return dict(previa,**dados,manifesto=m)


def exportar(previa,pasta,formato,cancelar=None,etapa=lambda *_:None,*,selecoes=(),somente_conjuntos=False,
             modelbuilder=None,escopo=None,base_labels=None):
    from osgeo import ogr, osr

    if formato not in ('GPKG','ESRI Shapefile') and not (modelbuilder and formato=='CSV'):
        raise ValueError('Escolha GeoPackage ou Shapefile.')
    previa=_normalizar_previa(previa,cancelar)
    m=dict(previa['manifesto'])
    crs=osr.SpatialReference()
    if crs.SetFromUserInput(m['crs'])!=0:raise ValueError('CRS de exportação inválido.')
    pipes,nos,catalogo,associacoes=conjuntos.preparar_exportacao(
        previa,selecoes,somente_conjuntos=somente_conjuntos,escopo=escopo,cancelar=cancelar)
    catalogo=normalizar(catalogo,m['serializacao_pendencias'],'conjuntos')
    pipe_campos={**PIPE_CAMPOS,**conjuntos.CAMPOS}
    no_campos={**NOS,**conjuntos.CAMPOS}
    pontos={'junctions':nos}
    reais=REAIS
    if modelbuilder:
        from . import modelbuilder_gis as mb
        etapa(0,'Conferindo integridade e referências Start e Stop Node')
        pipes,tipos,esperado,pendencias,manifesto_mb=mb.preparar(
            previa,pipes,nos,associacoes,dict(modelbuilder,base_labels=base_labels),cancelar)
        pontos={nome:tipos[tipo] for nome,tipo in (('junctions','JUNCTION'),('reservoirs','RESERVOIR'),('tanks','TANK'))
                if tipos[tipo] or tipo=='JUNCTION'}
        pipe_campos.update(mb.CAMPOS_PIPE)
        no_campos.update(mb.CAMPOS_NO)
        reais=REAIS | mb.CAMPOS_REAIS
        if formato=='CSV':
            from .investigacao_gis import geometria
            pipe_campos['mb_wkt']='MB_WKT'
            for r in pipes:
                verificar_cancelamento(cancelar)
                r['mb_wkt']=geometria(r['wkb'].hex()).asWkt()
    else:
        from .labels_modelagem import reservar
        rotulos=reservar([dict(uid=r['uid'],tipo=t,label=r.get('label'),original=r.get('WNA_ORIG_UID'))
                        for t,rs in (('PIPE',pipes),('JUNCTION',nos)) for r in rs],m['projeto'],m['execucao'],
                        base=base_labels,gravar=True,cancelar=cancelar)
        for r in chain(pipes,nos):r['WNA_LABEL']=rotulos[r['uid']]
        for a in associacoes:a['label_previsto']=rotulos[a['elemento_uid']]
    m.update(esquema_wna=conjuntos.VERSAO,conjuntos=len(catalogo),associacoes=len(associacoes),
             exportacao='SELECOES' if somente_conjuntos else 'CADASTRO_COMPLETO',
             elementos_exportados={'PIPE':len(pipes),'JUNCTION':len(nos)})
    if modelbuilder:
        m.update(exportacao=modelbuilder['escopo'],elementos_exportados=manifesto_mb['quantidades'],
                 incompleto=manifesto_mb['incompleto'],excluidos=manifesto_mb['excluidos'])
    destino=Path(pasta)/('Cadastro_modelagem_'+m['execucao'][:8]+'_'+uuid4().hex[:8])
    etapa(0,'Gravando cadastro, derivados e tabelas de procedência')
    with TemporaryDirectory(prefix='.cadastro_',dir=pasta) as arq:
        saida=Path(arq)/'saida'
        saida.mkdir()
        gpkg=saida/'cadastro_modelagem.gpkg'
        ds=None
        try:
            if formato=='GPKG':ds=ogr.GetDriverByName(formato).CreateDataSource(str(gpkg))
            if formato!='CSV':
                _vetor(saida,formato,'pipes',ogr.wkbLineString,pipe_campos,pipes,crs,cancelar,ds,reais=reais)
                for nome,linhas in pontos.items():
                    _vetor(saida,formato,nome,ogr.wkbPoint,no_campos,linhas,crs,cancelar,ds,reais=reais)
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
        if somente_conjuntos:
            originais={r['original'] for r in pipes}|{r['WNA_ORIG_UID'] for r in nos}
            refs={a['conexao_uid'] for a in associacoes if a['conexao_uid']}
            tabelas['inventario_cadastral']=[r for r in previa['cadastro'] if r['feicao'] in originais or r['uid'] in originais]
            tabelas['operacoes_topologicas']=[r for r in previa['operacoes'] if r['uuid'] in refs]
            tabelas['equipamentos_inventariados']=[]
        if formato=='GPKG':
            with closing(sqlite3.connect(gpkg)) as con, con:
                for nome,rs in tabelas.items():
                    con.execute(f'CREATE TABLE {nome} (fid INTEGER PRIMARY KEY, uid TEXT, dados_json TEXT NOT NULL)')
                    con.execute('INSERT INTO gpkg_contents (table_name,data_type,identifier) VALUES (?,?,?)',
                                (nome,'attributes',nome))
                    for r in rs:
                        verificar_cancelamento(cancelar)
                        con.execute(f'INSERT INTO {nome} (uid,dados_json) VALUES (?,?)',
                                    (r.get('uid',r.get('uuid')),json.dumps(r,ensure_ascii=False,allow_nan=False)))
                _tabela_associacoes(con,catalogo,associacoes,cancelar)
        _csv(saida,'pipes',(*pipe_campos,'fontes','componente'),pipes,cancelar)
        for nome,linhas in pontos.items():
            _csv(saida,nome,(*no_campos,'xy','portas','equipamento_uid'),linhas,cancelar)
        _csv(saida,'inventario_cadastral',('uid','feicao','id','label','categoria','fontes','camada','atributos_originais'),
             tabelas['inventario_cadastral'],cancelar)
        (saida/'operacoes_topologicas.json').write_text(json.dumps(tabelas['operacoes_topologicas'],ensure_ascii=False),encoding='utf-8')
        _csv(saida,'WNA_CONJUNTOS',conjuntos.CATALOGO,catalogo,cancelar)
        _csv(saida,'WNA_ELEMENTO_CONJUNTO',conjuntos.COLUNAS,associacoes,cancelar)
        fontes_diametro=[]
        for u,r in m.get('fontes',{}).items():
            d=r.get('diametro')
            if d:fontes_diametro.append(dict(fonte_uid=u,fonte=r.get('nome'),campo=d['campo'],unidade=d['unidade'],**d['contagens']))
        _csv(saida,'WNA_DIAMETROS_POR_FONTE',('fonte_uid','fonte','campo','unidade','VALIDO','SEM_CAMPO','SEM_UNIDADE',
            'SEM_VALOR','VALOR_INVALIDO'),fontes_diametro,cancelar)
        if catalogo:
            m['consultas']='MINUTAS_CONDICIONADAS_A_CORRESPONDENCIA_E_VALIDACAO_NO_WATERGEMS'
            _consultas(saida,catalogo,associacoes,cancelar)
        if modelbuilder:
            if modelbuilder['perfil']['modo']=='ATUALIZAR':
                from .modelbuilder_conferencia import plano_atualizacao
                if not modelbuilder.get('componentes_anteriores'):
                    raise ValueError('Confira o pacote de referência para preparar a atualização.')
                plano=plano_atualizacao(modelbuilder['componentes_anteriores'],esperado,cancelar,
                                        observado=modelbuilder.get('observado',()))
                _csv(saida,'WNA_PLANO_ATUALIZACAO',('acao','uid','tipo','novos_segmentos','id_modelo','label_modelo',
                    'situacao_destino'),plano,cancelar)
                manifesto_mb.update(atualizacao='PREVIA_EXIGE_CONFERENCIA_DO_MODELO_DESTINO',
                                    referencia_anterior=modelbuilder.get('referencia_anterior'))
            mb.arquivos(saida,esperado,pendencias,manifesto_mb,_csv,cancelar)
            _csv(saida,'WNA_EQUIPAMENTOS_INVENTARIO',('uid','categoria','id','label','wkb','declaracoes','atributos_originais'),
                 previa['equipamentos'],cancelar)
        if formato=='ESRI Shapefile':
            m=dict(m,dicionario_shp={'pipes':pipe_campos,**{k:no_campos for k in pontos}})
        (saida/'validacao.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
        publicar(saida,destino,cancelar)
    return destino


def _tabela_associacoes(con,catalogo,associacoes,cancelar):
    for nome,colunas,dados,chave in (
            ('WNA_CONJUNTOS',conjuntos.CATALOGO,catalogo,('uuid',)),
            ('WNA_ELEMENTO_CONJUNTO',conjuntos.COLUNAS,associacoes,('tipo_elemento','elemento_uid','conjunto_uid'))):
        campos=','.join(k+(' REAL' if k in ('inicio','fim') else ' TEXT') for k in colunas)
        con.execute(f"CREATE TABLE {nome} (fid INTEGER PRIMARY KEY, {campos}, UNIQUE ({','.join(chave)}))")
        con.execute('INSERT INTO gpkg_contents (table_name,data_type,identifier) VALUES (?,?,?)',
                    (nome,'attributes',nome))
        sql=f"INSERT INTO {nome} ({','.join(colunas)}) VALUES ({','.join('?' for _ in colunas)})"
        for r in dados:
            verificar_cancelamento(cancelar)
            con.execute(sql,[json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list,tuple)) else v
                             for k in colunas for v in (r.get(k),)])
    con.execute('CREATE INDEX wna_associacao_conjunto ON WNA_ELEMENTO_CONJUNTO(conjunto_uid)')


def _consultas(saida,catalogo,associacoes,cancelar):
    from collections import defaultdict

    grupos=defaultdict(list)
    for r in associacoes:
        if r['situacao_participacao']!='EXCLUIDO_EXPORTACAO':
            grupos[r['conjunto_uid'],r['tipo_elemento']].append(r['elemento_uid'])
    pasta=saida/'MINUTAS_QUERIES'
    pasta.mkdir()
    indice=[]
    for (uid,tipo),ids in sorted(grupos.items()):
        nome=next(r['nome'] for r in catalogo if r['uuid']==uid)
        ids=sorted(ids)
        for i in range(0,len(ids),100):
            verificar_cancelamento(cancelar)
            lote=ids[i:i+100]
            arquivo=f'{uid}_{tipo}_LOTE_{i//100+1:03d}.txt'
            expr='WNA_UID IN ('+', '.join("'"+u+"'" for u in lote)+')'
            (pasta/arquivo).write_text(expr+'\n',encoding='utf-8')
            indice.append(dict(conjunto_uid=uid,nome=nome,tipo=tipo,arquivo=arquivo,lote=i//100+1,
                               quantidade=len(lote),total=len(ids),validacao='PENDENTE_NO_MODELO_DE_DESTINO'))
    _csv(pasta,'INDICE_QUERIES',('conjunto_uid','nome','tipo','arquivo','lote','quantidade','total','validacao'),
         indice,cancelar)
    (saida/'CRIAR_SELECTION_SETS.txt').write_text(
        'Pacote de preparação de Selection Sets\n\n'
        '1. Abra uma cópia do modelo de destino e confira a execução e a revisão em validacao.json.\n'
        '2. No ModelBuilder, confira o vínculo unívoco entre os elementos de destino e os registros exportados. '
        'Crie um User Data Extension de texto WNA_UID por tipo de elemento e mapeie explicitamente o campo. '
        'A coluna WNA_LABEL é um Label previsto para preparação. Preserve Labels existentes quando houver uma chave confiável.\n'
        '3. Exporte uma FlexTable de cada tipo. Compare WNA_UID e tipo com WNA_ELEMENTO_CONJUNTO.csv. '
        'Resolva chaves ausentes, duplicadas, incompatíveis ou ligadas ao elemento errado antes de continuar.\n'
        '4. No Query Builder, selecione o tipo correspondente e insira o campo pela lista do próprio editor. '
        'Ajuste a minuta se o editor usar outro identificador. Valide a expressão e confira a quantidade de cada lote.\n'
        '5. Crie um Selection Set estático com o primeiro lote conferido e use Add to Selection Set para os seguintes, '
        'quando disponível. Reexecutar uma consulta pode substituir a seleção atual.\n'
        '6. Confira o total de elementos distintos por tipo e seus WNA_UIDs. Reconstrua as pastas usando a categoria '
        'e a subpasta do catálogo, se a sua versão permitir.\n\n'
        'Os arquivos de MINUTAS_QUERIES dependem do campo e da correspondência no modelo de destino.\n'
        'Referência Bentley KB0059255, KB0015896 e KB0014413.\n',encoding='utf-8')
