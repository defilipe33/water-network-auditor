"""Snapshot de apresentação e PDF/XLSX ilustrados. Não recalcula diagnósticos."""
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,math,os,tempfile,shutil
from html import escape
from . import operacional as op
from . import decisoes as db


def selecionar(casos,analises,modo,escopo='TODOS',ids=()):
    if modo not in db.MODOS:raise ValueError('Perspectiva não disponível')
    if escopo not in ('TODOS','ANALISADOS','PENDENTES','CORRECAO','MANUAIS','SELECAO','FILTROS'):raise ValueError('Seleção inválida')
    ids=set(ids);saida=[]
    for c in casos:
        a=analises.get((c['uid'],modo),{});resultado=a.get('resultado') or 'PENDENTE';analisado=resultado not in ('PENDENTE','NECESSITA INVESTIGAÇÃO ADICIONAL')
        if escopo=='ANALISADOS' and not analisado or escopo=='PENDENTES' and analisado or escopo=='CORRECAO' and resultado!='CORREÇÃO NECESSÁRIA' or escopo=='MANUAIS' and c.get('origem')!='MANUAL' or escopo in ('SELECAO','FILTROS') and c['uid'] not in ids:continue
        saida.append((c,a))
    return saida


def snapshot(base,pacote,casos,modo,config):
    from .decisoes import propostas,registros
    ig=pacote['resultado']['meta']['uid'];hs=op.historico(base,ig);heads={(a['occ_uid'],a['modo']):a for a in hs};ps=propostas(base,ig);notas=registros(base,ig)
    from . import acompanhamento as ac
    acompanhamentos=ac.indice(base,pacote);ctx=ac.Contexto(pacote);estados={c['uid']:ac.estado(acompanhamentos.get((c['uid'],modo)),c,pacote,modo,ctx) for c in casos}
    meta=pacote['resultado']['meta'];linhas=[]
    for caso,a in selecionar(casos,heads,modo,config.get('escopo','TODOS'),config.get('ids',())):
        situacao=estados[caso['uid']];filtro_acomp=config.get('situacao_acompanhamento','TODAS')
        if filtro_acomp=='RESOLVIDAS' and situacao!='RESOLVIDO' or filtro_acomp=='EM_ABERTO' and situacao=='RESOLVIDO':continue
        man=caso.get('manual_registro',{}).get('dados',{});old=[n.get('observacao','') for n in notas if n['occ_uid']==caso['uid'] and n['modo']==modo]
        linhas.append(dict(acompanhamento=ac.ROTULOS[situacao],acomp_estado=situacao,acomp_uid=acompanhamentos.get((caso['uid'],modo),{}).get('uid'),historico_acomp=ac.historico(base,ig,caso['uid'],modo) if config.get('historico') else [],uid=caso['uid'],local=caso.get('local_uid') or caso.get('manual_uid') or caso['chave'],titulo=caso['titulo'],origem=caso.get('origem','AUTOMATICA'),diagnostico=caso.get('resumo',''),resultado=a.get('resultado') or 'PENDENTE',motivo=a.get('motivo',''),observacao=a.get('observacao','') or man.get('observacoes',''),anotacoes=old,prioridade=a.get('prioridade_trabalho') or caso.get('prioridade',''),regioes=caso.get('regioes',[]),elementos=caso.get('elementos',[]),gis=caso.get('tubos_gis',[]),wg_ids=caso.get('wg_ids',[]),data=a.get('data_utc',''),revisao_uid=a.get('uid'),propostas=[p for p in ps if p['occ_uid']==caso['uid'] and p['modo']==modo],historico=[h for h in hs if h['occ_uid']==caso['uid'] and h['modo']==modo] if config.get('historico') else [],tecnico=caso.get('tecnico',[]) if config.get('tecnico') else []))
    chave=config.get('ordenacao','titulo')
    if chave not in ('titulo','resultado','prioridade','origem'):raise ValueError('Ordenação inválida')
    linhas.sort(key=lambda r:(str(r[chave]),r['uid']))
    contagens={k:0 for k in op.RESULTADOS};contagens.update(Counter(r['resultado'] for r in linhas))
    return dict(nome=config.get('nome') or 'Relatório de investigação',meta=meta,modo=modo,data=datetime.now(timezone.utc).isoformat(),config=dict(config),ocorrencias=linhas,resolvidas=sum(r['acomp_estado']=='RESOLVIDO' for r in linhas),em_aberto=sum(r['acomp_estado']!='RESOLVIDO' for r in linhas),acompanhamento_contagens=dict(Counter(r['acompanhamento'] for r in linhas)),acompanhamento_global=dict(Counter(ac.ROTULOS[v] for v in estados.values())),total_disponivel=len(casos),contagens=contagens,origens=dict(Counter(r['origem'] for r in linhas)),propostas=sum(len(r['propostas']) for r in linhas),interpretacao='Resultados são interpretações investigativas; não comprovam operação hidráulica nem alteram o modelo.')


def geometrias_caso(pacote,caso,contexto=None):
    from qgis.core import QgsGeometry,QgsCoordinateReferenceSystem,QgsCoordinateTransform,QgsProject
    crs=pacote['dossie']['contexto']['parametros']['crs'];saida=[];ponto=None
    if caso.get('manual_posicao'):
        r=caso['manual_posicao'];ponto=QgsGeometry.fromWkt(f"POINT({r['x']} {r['y']})")
        if r['crs']!=crs:ponto.transform(QgsCoordinateTransform(QgsCoordinateReferenceSystem(r['crs']),QgsCoordinateReferenceSystem(crs),QgsProject.instance()))
        for v in caso['manual_registro']['vinculos']:
            w=v['dados'].get('geometria_wkb')
            if v['origem']=='GIS' and w:g=QgsGeometry();g.fromWkb(bytes.fromhex(w));saida.append((g,'GIS'))
    elif caso.get('local_uid'):
        l=next((l for l in pacote['resultado']['locais'] if l['uid']==caso['local_uid']),None)
        if l:ponto=QgsGeometry.fromWkt(f"POINT({l['registro']['X']} {l['registro']['Y']})")
    el=pacote['topologia']['modelo']['elementos']
    for i in caso.get('wg_ids',[]):
        g=(pacote.get('geometrias') or {}).get(i)
        if g and not g.isEmpty():saida.append((QgsGeometry(g),el[i]['familia']))
    tubos={t['uid']:t for t in pacote['dossie']['tubulacoes']}
    for u in caso.get('gis_uids',[]):
        t=tubos.get(u)
        if t:
            g=QgsGeometry.fromWkt(t['wkt']) if 'wkt' in t else None
            if g and not g.isEmpty():saida.append((g,'GIS'))
    if ponto:saida.append((ponto,'LOCAL'))
    for a in pacote.get('areas',[]):
        if a['uid'] in caso.get('area_uids',[]):saida.append((QgsGeometry(a['geometria']),'AREA'))
    if contexto:
        uids=set(caso.get('area_uids',[]))
        for u in contexto.locais.get(caso.get('local_uid'),{}):uids.add(u)
        for v in caso.get('manual_registro',{}).get('vinculos',[]):
            if v['origem']=='AREA':uids.add(v['chave'])
        for u in uids:
            a=contexto.areas.get(u,{})
            if a.get('geometria_wkb'):
                g=QgsGeometry();g.fromWkb(bytes.fromhex(a['geometria_wkb']));src=QgsCoordinateReferenceSystem(a['crs']);dst=QgsCoordinateReferenceSystem(crs)
                if src!=dst:g.transform(QgsCoordinateTransform(src,dst,QgsProject.instance()))
                saida.append((g,'AREA'))
    return saida,ponto


def enquadrar(geometrias,margem=.25,minimo=100,aspecto=1.6,centro=None,contexto=False):
    from qgis.core import QgsGeometry,QgsRectangle
    if not 0<=margem<=5 or minimo<=0:raise ValueError('Margem/extensão mínima inválida')
    gs=[g for g,t in geometrias if not g.isEmpty() and t!='AREA']
    if not gs:raise ValueError('Ocorrência sem geometria confiável; gere sem imagem.')
    r=QgsGeometry.collectGeometry(gs).boundingBox();ampla=max(r.width(),r.height())>2000
    if ampla and centro is not None and not contexto:r=centro.boundingBox()
    w=max(minimo,r.width()*(1+2*margem));h=max(minimo/aspecto,r.height()*(1+2*margem))
    if w/h<aspecto:w=h*aspecto
    else:h=w/aspecto
    c=r.center();r=QgsRectangle(c.x()-w/2,c.y()-h/2,c.x()+w/2,c.y()+h/2)
    return r,ampla


def camadas_relatorio(gs,crs):
    from qgis.core import QgsVectorLayer,QgsFeature,QgsFillSymbol,QgsLineSymbol,QgsMarkerSymbol
    cores={'LINK':'#1464dc','GIS':'#008db8','NO':'#008a69','DISPOSITIVO':'#b817c8','AREA':'#997700','LOCAL':'#e66100'};grupos={};layers=[]
    for g,t in gs:grupos.setdefault((t,g.type()),[]).append(g)
    for (tipo,geom),geoms in grupos.items():
        if geom not in (0,1,2):continue
        c=QgsVectorLayer(('MultiPoint','MultiLineString','MultiPolygon')[geom]+'?crs='+crs,tipo,'memory');fs=[]
        for g in geoms:
            g=type(g)(g);g.convertToMultiType();f=QgsFeature();f.setGeometry(g);fs.append(f)
        c.dataProvider().addFeatures(fs);c.updateExtents();cor=cores[tipo]
        if geom==2:s=QgsFillSymbol.createSimple(dict(color='transparent',outline_color=cor,outline_width='.5'))
        elif geom==1:s=QgsLineSymbol.createSimple(dict(line_color=cor,line_width='.8'))
        else:s=QgsMarkerSymbol.createSimple(dict(name='circle',color=cor,size='3'))
        c.renderer().setSymbol(s);layers.append(c)
    return sorted(layers,key=lambda c:0 if c.geometryType()==0 else 1 if c.geometryType()==1 else 2)


def renderizar_imagem(layers,crs,caixa,config):
    from qgis.core import QgsMapSettings,QgsMapRendererParallelJob,QgsCoordinateReferenceSystem,QgsProject
    from qgis.PyQt.QtCore import QSize,QEventLoop,QTimer
    from qgis.PyQt.QtGui import QColor
    st=QgsMapSettings();st.setLayers(layers);st.setDestinationCrs(QgsCoordinateReferenceSystem(crs));st.setTransformContext(QgsProject.instance().transformContext());st.setExtent(caixa);st.setOutputSize(QSize(1440,900));st.setOutputDpi(160);st.setBackgroundColor(QColor('white'))
    job=QgsMapRendererParallelJob(st);loop=QEventLoop();timer=QTimer();timer.setSingleShot(True);expirou=[]
    def timeout():expirou.append(True);job.cancel()
    timer.timeout.connect(timeout);job.finished.connect(loop.quit);timer.start(config.get('timeout_ms',15000));job.start()
    if job.isActive():loop.exec_()
    timer.stop()
    return job.renderedImage(),bool(expirou),[e.message for e in job.errors()],st.visibleExtent()


def renderizar(gs,crs,destino,config,basemaps=(),centro=None,contexto=False,ao_falhar_basemap=None):
    """QgsMapRendererParallelJob: camadas temporárias próprias, timeout e falha explícita."""
    from qgis.core import QgsMapSettings,QgsMapRendererParallelJob,QgsCoordinateReferenceSystem,QgsProject,QgsUnitTypes
    from qgis.PyQt.QtCore import QSize,QEventLoop,QTimer,Qt
    from qgis.PyQt.QtGui import QPainter,QColor,QFont
    from .localizacao_relatorio import sanear_fonte
    src=QgsCoordinateReferenceSystem(crs)
    if not src.isValid() or src.mapUnits()!=QgsUnitTypes.DistanceMeters:raise ValueError('Mapa métrico bloqueado: CRS não validado em metros.')
    caixa,ampla=enquadrar(gs,config.get('margem',.25),config.get('minimo_m',100),centro=centro,contexto=contexto)
    if config.get('extensao') and not contexto:
        from qgis.core import QgsRectangle
        caixa=QgsRectangle(*config['extensao'])
        if caixa.isEmpty() or not all(math.isfinite(v) for v in config['extensao']):raise ValueError('Extensão manual inválida')
    from .fontes_relatorio import resolver,FalhaBasemap
    basemaps,config=resolver(basemaps,config,1)
    layers=camadas_relatorio(gs,crs);avisos=list(config.get('avisos_basemap',[]));fontes=[];clones=[]
    for b in basemaps:
        if not b.isValid():avisos.append('Mapa-base indisponível: '+b.name());continue
        c=b.clone();c.setOpacity(config.get('opacidade',.65))
        if config.get('cinza') and hasattr(c,'pipe'):
            f=c.pipe().hueSaturationFilter()
            if f:f.setGrayscaleMode(1)
        if hasattr(c,'brightnessFilter'):
            c.brightnessFilter().setBrightness(config.get('brilho',0));c.brightnessFilter().setContrast(config.get('contraste',0))
        clones.append(c);fontes.append(sanear_fonte(b))
    img,timeout,erros,ext=renderizar_imagem(layers+clones,crs,caixa,config)
    if clones and (timeout or erros):
        motivo='Tempo de carregamento excedido' if timeout else 'Falha de autenticação no mapa-base' if any('401' in e or '403' in e or 'auth' in e.lower() for e in erros) else 'Mapa-base indisponível ou incompleto (rede/provedor)'
        if ao_falhar_basemap is None:raise FalhaBasemap(motivo+'. Você pode continuar sem mapa-base ou cancelar.')
        if not ao_falhar_basemap(motivo):raise InterruptedError('Relatório cancelado pelo usuário após falha do mapa-base.')
        avisos.append(motivo+'. Mapa-base não utilizado por escolha do usuário; rede e limites mantidos.')
        img,timeout,erros,ext=renderizar_imagem(layers,crs,caixa,config);fontes=[]
    if timeout or img.isNull():raise RuntimeError('Falha/timeout de renderização; relatório não publicado.')
    avisos+=erros
    if ampla:avisos.append('Elementos distantes: detalhe e contexto têm enquadramentos diferentes; conferir mapa de contexto.')
    metros=ext.width()/5;pixel=1440/5
    if not img.save(str(destino),'PNG'):raise OSError('Não foi possível salvar o mapa renderizado')
    # A fonte Vera distribuída pelo ReportLab torna legenda e escala reproduzíveis
    # também em QgsApplication headless, cujo catálogo Qt de fontes pode ser vazio.
    import reportlab
    from PIL import Image,ImageDraw,ImageFont
    with Image.open(destino) as im:
        d=ImageDraw.Draw(im);font=ImageFont.truetype(str(Path(reportlab.__file__).parent/'fonts/Vera.ttf'),22);d.rectangle((0,0,1440,46),fill='white');d.text((18,10),'Rede: azul | Nós: verde | Dispositivos: magenta | Limites: ocre | Local: laranja',fill='#163047',font=font);d.text((1370,50),'N',fill='#163047',font=font);d.polygon([(1380,78),(1368,112),(1392,112)],fill='#163047');d.rectangle((30,850,30+pixel,858),fill='#163047');d.text((30,815),f'{metros:.0f} m · CRS {src.authid()}',fill='#163047',font=font);im.save(destino)
    return dict(avisos=avisos,fontes=fontes,extensao=[ext.xMinimum(),ext.yMinimum(),ext.xMaximum(),ext.yMaximum()],atribuicao=config.get('atribuicao','') if fontes else '',data=datetime.now(timezone.utc).isoformat())


def salvar_config(base,ig,config):
    """Preferências no índice auxiliar, sem modificar a investigação histórica."""
    from qgis.PyQt.QtCore import QSettings
    seguro={k:v for k,v in config.items() if k not in ('endpoint','authcfg','ids','extensao')}
    QSettings().setValue('WaterNetworkAuditor/relatorios/'+db.digest([str(Path(base).resolve()),ig]),json.dumps(seguro,ensure_ascii=False))


def carregar_config(base,ig):
    from qgis.PyQt.QtCore import QSettings
    try:return json.loads(QSettings().value('WaterNetworkAuditor/relatorios/'+db.digest([str(Path(base).resolve()),ig]),'{}'))
    except (ValueError,TypeError):return {}


def gerar_pdf(destino,dados,imagens,progresso=None,cancelado=None):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Image,PageBreak,Table,TableStyle,KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4,landscape
    from reportlab.platypus.tableofcontents import TableOfContents
    styles=getSampleStyleSheet();styles['BodyText'].fontSize=9;styles['BodyText'].leading=11;styles['Heading1'].fontSize=16;styles['Heading1'].leading=20;styles['Heading2'].fontSize=11;styles['Heading2'].leading=13;styles['Heading2'].spaceBefore=8;styles['Heading2'].spaceAfter=4;styles['Heading1'].textColor=colors.HexColor('#163047')
    def par(s,style='BodyText'):return Paragraph(escape(str(s or '—')).replace('\n','<br/>'),styles[style])
    class Documento(SimpleDocTemplate):
        def afterFlowable(self,f):
            if isinstance(f,Paragraph) and f.style.name=='Heading1' and hasattr(f,'indice_texto'):self.notify('TOCEntry',(0,f.indice_texto,self.page))
    doc=Documento(str(destino),pagesize=landscape(A4) if dados['config'].get('paisagem') else A4,rightMargin=36,leftMargin=36,topMargin=38,bottomMargin=38,title=dados['nome'],author='Water Network Auditor')
    largura=doc.width;story=[Spacer(1,55),par('WATER NETWORK AUDITOR','Title'),Spacer(1,20),par(dados['nome'],'Title'),Spacer(1,30)]
    meta=dados['meta']
    for s in [meta.get('projeto','Projeto'),meta.get('nome','Investigação'),f"Investigação {meta['uid']} · versão {meta.get('versao',1)}",f"WaterGEMS {meta['topologia']['execucao_uid']}",f"Cenário {meta['topologia'].get('cenario')} · {dados['modo']}",dados['data'],dados['interpretacao']]:story.extend([par(s),Spacer(1,10)])
    story+=[PageBreak(),par('Resumo','Heading1')]
    for s in [f"{len(dados['ocorrencias'])} ocorrências nesta seleção / {dados.get('total_disponivel',len(dados['ocorrencias']))} disponíveis na investigação",*['%s: %s'%(k,v) for k,v in dados['contagens'].items()],*['%s: %s'%(k,v) for k,v in dados['origens'].items()],f"Propostas relacionadas: {dados['propostas']}",f"Acompanhamento nesta seleção: {dados['resolvidas']} resolvidas · {dados['em_aberto']} em aberto (inclui reavaliações)",'Acompanhamento na investigação: '+str(dados['acompanhamento_global']),f"Escopo: {dados['config'].get('escopo','TODOS')}"] :story.extend([par(s),Spacer(1,5)])
    story+=[PageBreak(),par('Índice de ocorrências','Title')];toc=TableOfContents();toc.levelStyles=[styles['BodyText']];story+=[toc]
    for r in dados['ocorrencias']:
        if cancelado and cancelado():raise InterruptedError('Composição PDF cancelada; nada publicado.')
        titulo=par(r['titulo'],'Heading1');titulo.indice_texto=escape(r['titulo']+' | '+'; '.join(r['regioes'])+' | '+str(r['prioridade'])+' | '+r['localizacao']['texto'])
        story+=[PageBreak(),titulo,par('Acompanhamento: '+r['acompanhamento']+' · Resultado técnico: '+r['resultado']),par('Região: '+'; '.join(r['regioes'])+' · Prioridade: '+str(r['prioridade'])),par(r['localizacao']['texto'])]
        for im in imagens.get(r['uid'],[]):
            story+=[Spacer(1,7),Image(str(im),width=largura,height=largura*900/1440)]
        if r.get('mapa_meta'):
            for m in r['mapa_meta']:
                if m['atribuicao']:story.append(par('Referência cartográfica: '+m['atribuicao']))
                for aviso in m['avisos']:story.append(par('Aviso: '+aviso))
        for titulo,chave in [('Diagnóstico','diagnostico'),('Motivo','motivo'),('Observações','observacao')]:story+=[Spacer(1,6),par(titulo,'Heading2'),par(r[chave])]
        for titulo,chave in [('Elementos WaterGEMS','elementos'),('Cadastro GIS','gis'),('Anotações anteriores','anotacoes')]:
            if r[chave]:story+=[par(titulo,'Heading2')]+[par(v) for v in r[chave]]
        story.append(par('Origem: '+r['origem']+' · Última análise: '+r['data']+' · UUID: '+r['uid']))
        if r['propostas']:
            story+=[par('Intervenções propostas','Heading2')]+[par(str(v.get('tipo','Proposta'))+' · '+str(v.get('atual',{}).get('situacao',''))+' · '+str(v.get('atual',{}).get('descricao',''))) for v in r['propostas']]
        if r['historico_acomp']:
            story+=[par('Histórico de acompanhamento','Heading2')]+[par(v['data_utc']+' · '+v['estado_anterior']+' → '+v['estado']+'\n'+v['observacao']) for v in r['historico_acomp']]
        if r['historico']:
            story+=[par('Histórico','Heading2')]+[par(str(v.get('data_utc',''))+' · '+str(v.get('resultado',''))+'\n'+str(v.get('motivo',''))+'\n'+str(v.get('observacao',''))) for v in r['historico']]
        if dados['config'].get('tecnico') and r.get('coordenadas'):story.append(par('Coordenadas de referência: '+str(r['coordenadas'])))
        if r['tecnico']:story+=[par('Informações técnicas','Heading2')]+[par(json.dumps(v,ensure_ascii=False,default=str)) for v in r['tecnico']]
    def rodape(canvas,doc):
        if cancelado and cancelado():raise InterruptedError('Paginação PDF cancelada; nada publicado.')
        if progresso:progresso('Compondo página '+str(doc.page),None,None)
        canvas.saveState();canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#536776'));canvas.drawString(36,22,'Water Network Auditor · referência visual não comprova conectividade');canvas.drawRightString(doc.pagesize[0]-36,22,str(doc.page));canvas.restoreState()
    doc.multiBuild(story,onFirstPage=rodape,onLaterPages=rodape)


def xlsx(destino,dados):
    from .saidas import exportar_tabelas_xlsx
    campos=('UUID','LOCAL','ORIGEM','DIAGNOSTICO','RESULTADO','MOTIVO','OBSERVACOES','REGIOES','PRIORIDADE','LOCALIZACAO','DATA','REVISAO_UID','ACOMPANHAMENTO','ACOMP_UID')
    linhas=[(r['uid'],r['local'],r['origem'],r['diagnostico'],r['resultado'],r['motivo'],r['observacao'],'; '.join(r['regioes']),r['prioridade'],r['localizacao']['texto'],r['data'],r['revisao_uid'],r['acompanhamento'],r['acomp_uid']) for r in dados['ocorrencias']]
    # Exportador existente divide textos longos na aba técnica; este relatório não
    # trunca silenciosamente: recusa célula além do limite e mantém snapshot JSON.
    if any(len(str(v))>32767 for linha in linhas for v in linha):raise ValueError('Texto excede uma célula Excel; reduza o escopo ou exporte PDF/JSON sem XLSX.')
    exportar_tabelas_xlsx({'OCORRENCIAS':(campos,linhas),'RESUMO':(('INDICADOR','VALOR'),list(dados['contagens'].items())+[('Acompanhamento - resolvidas',dados['resolvidas']),('Acompanhamento - em aberto',dados['em_aberto'])])},destino)


def gerar(base,pacote,casos,modo,pasta,config,basemaps=(),ruas=None,progresso=None,cancelado=None,ao_falhar_basemap=None):
    from qgis.core import QgsApplication
    from qgis.PyQt.QtCore import QThread
    if QgsApplication.instance() and QThread.currentThread()!=QgsApplication.instance().thread():raise RuntimeError('Renderização QGIS deve ocorrer no thread principal.')
    destino=Path(pasta)
    if destino.exists():raise FileExistsError('Escolha uma pasta nova; relatório anterior preservado.')
    destino.parent.mkdir(parents=True,exist_ok=True);tmp=Path(tempfile.mkdtemp(prefix='.relatorio_',dir=destino.parent));dados=snapshot(base,pacote,casos,modo,config);mapa={};por_uid={c['uid']:c for c in casos}
    from .filtros import ContextoFiltros
    contexto=ContextoFiltros(pacote);contexto.restaurar_persistidas(base)
    try:
        if config.get('imagens',True) and pacote['resultado']['meta']['parametros'].get('espacial_habilitado'):
            # Leitor existente confere origem + atributos + WKB contra assinaturas
            # preservadas; não relaciona limites apenas pelo texto do diagnóstico.
            contexto.recuperar_geometrias()
            dados['avisos_limites']=list(contexto.avisos)
        from .fontes_relatorio import resolver
        basemaps,config=resolver(basemaps,config,len(dados['ocorrencias']));dados['config']=dict(config);base_falhou=[]
        def decidir_falha(motivo):
            if ao_falhar_basemap is None:return False
            if ao_falhar_basemap(motivo):
                base_falhou.append(motivo);basemaps.clear();return True
            return False
        for n,r in enumerate(dados['ocorrencias']):
            if cancelado and cancelado():raise InterruptedError('Relatório cancelado; nada publicado.')
            if progresso:progresso('Preparando ocorrência '+r['titulo'],n,len(dados['ocorrencias']))
            gs,centro=geometrias_caso(pacote,por_uid[r['uid']],contexto)
            r['coordenadas']=dict(x=centro.asPoint().x(),y=centro.asPoint().y(),crs=pacote['dossie']['contexto']['parametros']['crs']) if centro else None
            r['localizacao']=dict(texto='Localização não identificada',fonte='INDEFINIDA')
            if config.get('localizacao',True):
                from .localizacao_relatorio import referencia_automatica
                cadastro=referencia_automatica(pacote,por_uid[r['uid']],config.get('referencia_cadastral',{}))
                rua=ruas.consultar(centro,config.get('raio_ruas',100)) if cadastro is None and centro and ruas else None
                externa=config.get('localizacoes_externas',{}).get(r['uid'])
                if cadastro:r['localizacao']=cadastro
                elif rua and rua.get('candidatos'):r['localizacao']=rua
                elif externa:r['localizacao']=externa
                elif config.get('localizacao_manual'):r['localizacao']=dict(texto=config['localizacao_manual'],fonte='MANUAL')
            if config.get('imagens',True) and gs:
                if not pacote['resultado']['meta']['parametros'].get('espacial_habilitado'):r['mapa_meta']=[dict(avisos=['Mapa omitido: referência espacial não validada'],atribuicao='')];continue
                fn=tmp/f'mapa_{n:05}.png';m=renderizar(gs,pacote['dossie']['contexto']['parametros']['crs'],fn,config,basemaps,centro,ao_falhar_basemap=decidir_falha);r['mapa_meta']=[m];mapa[r['uid']]=[fn]
                if base_falhou and not m['fontes'] and not any('escolha do usuário' in a for a in m['avisos']):m['avisos'].append('Mapa-base não utilizado após falha anterior; rede e limites preservados.')
                if contexto.avisos:m['avisos'].append('Limites/contexto parcialmente disponíveis; confira as fontes. '+ '; '.join(contexto.avisos[:3]))
                if config.get('contexto',False) or any('distantes' in s for s in m['avisos']):
                    fn=tmp/f'contexto_{n:05}.png';r['mapa_meta'].append(renderizar(gs,pacote['dossie']['contexto']['parametros']['crs'],fn,config,basemaps,centro,True,ao_falhar_basemap=decidir_falha));mapa[r['uid']].append(fn)
            elif config.get('imagens',True):r['mapa_meta']=[dict(avisos=['Sem geometria disponível; localização não inventada'],atribuicao='')]
        if cancelado and cancelado():raise InterruptedError('Relatório cancelado antes da publicação.')
        if progresso:progresso('Compondo documento e verificando publicação',None,None)
        gerar_pdf(tmp/'INVESTIGACAO.pdf',dados,mapa,progresso,cancelado)
        from pypdf import PdfReader
        pdf=PdfReader(tmp/'INVESTIGACAO.pdf')
        if not pdf.pages:raise ValueError('PDF vazio; publicação bloqueada')
        if config.get('xlsx',False):xlsx(tmp/'ACOMPANHAMENTO.xlsx',dados)
        (tmp/'SNAPSHOT.json').write_text(json.dumps(dados,ensure_ascii=False,indent=2,default=str),encoding='utf8')
        if cancelado and cancelado():raise InterruptedError('Relatório cancelado; destino preservado.')
        if not config.get('preservar_imagens',False):
            for fn in tmp.glob('*.png'):fn.unlink()
        manifesto={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in tmp.iterdir() if f.is_file()};(tmp/'MANIFESTO.json').write_text(json.dumps(manifesto,indent=2),encoding='utf8');os.rename(tmp,destino);return dados
    finally:
        if tmp.exists():shutil.rmtree(tmp)
