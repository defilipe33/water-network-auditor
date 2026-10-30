"""Detecção para o assistente existente: declarações não são prova de datum ou unidade bruta."""
from collections import Counter,defaultdict
from contextlib import closing
from hashlib import sha256
import json
from math import dist,isfinite
from pathlib import Path
import re
from statistics import mean,median
import sqlite3
from qgis.core import (QgsCoordinateReferenceSystem,QgsUnitTypes,QgsVectorLayer,
                       QgsFeatureRequest,QgsGeometry,QgsProject)
from . import bases,referencia_espacial as ref
from .arquivos import hash_arquivo
from .leitura import identificador
from .gerenciamento import registros_gis
from auditoria_fronteiras.apresentacao import legivel
from auditoria_fronteiras.entradas import valor_python

REGRAS='referencia-assistida-2-sem-aprovacao-formal'

def metro(crs):
    c=QgsCoordinateReferenceSystem(crs or '')
    return c.isValid() and not c.isGeographic() and c.mapUnits()==QgsUnitTypes.DistanceMeters

def interpretar_crs(bruto):
    """Somente raiz horizontal: códigos de datum/elipsoide não são códigos de CRS."""
    if not isinstance(bruto,str) or not bruto.strip():return None
    if bruto.lstrip().startswith('{'):
        d=json.loads(bruto);h=d.get('horizontalCRS',{})
        codigos=[]
        if h.get('epsg'):codigos.append(str(h['epsg']))
        codigos+=re.findall(r'(\d+)\s*\[EPSG\]',h.get('source',''),re.I)
        if len(set(codigos))!=1:return None
        c=QgsCoordinateReferenceSystem('EPSG:'+codigos[0])
        if not c.isValid():return None
        p=h.get('projection',{});zona=p.get('zoneNumber')
        if zona is not None:
            proj=c.toProj()
            if f'+zone={zona}' not in proj or (p.get('hemisphere')=='South')!=('+south' in proj):raise ValueError('EPSG e projeção declarada se contradizem')
        unit=h.get('unit')
        if unit=='Meter' and c.mapUnits()!=QgsUnitTypes.DistanceMeters:raise ValueError('Unidade e EPSG declarados se contradizem')
        return dict(crs=c.authid() or c.toWkt(),unidade_crs=unit,descricao=h.get('description'),metodo='JSON horizontalCRS.source/epsg; sem interpretar códigos de datum')
    if not (re.fullmatch(r'EPSG:\d+',bruto.strip(),re.I) or bruto.lstrip().startswith(('PROJCRS[','PROJCS[','GEOGCRS[','GEOGCS['))):return None
    c=QgsCoordinateReferenceSystem(bruto)
    return dict(crs=c.authid() or c.toWkt(),unidade_crs=QgsUnitTypes.toString(c.mapUnits()),metodo='Definição EPSG/WKT explícita') if c.isValid() else None

def ler_metadados_sqlite(caminho,cancelar=None):
    p=Path(caminho).resolve(strict=True);antes=hash_arquivo(p);registros=[];declarados=[];problemas=[];versao=[];esquema={}
    with closing(sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)) as con:
        con.execute('PRAGMA query_only=ON')
        for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            bases.verificar(cancelar);cols=[r[1] for r in con.execute('PRAGMA table_info('+identificador(t)+')')]
            candidatos=[c for c in cols if re.search('spatial.*reference|coordinate.*reference|epsg|projection|coordinate.*unit',c,re.I)]
            if candidatos:esquema[t]=candidatos
            if t=='HMISchemaVersionInfo':versao=[list(r) for r in con.execute('SELECT Name,Type,Value FROM '+identificador(t))]
            for campo in candidatos:
                # Valores desconhecidos são candidatos, nunca declarações confiáveis.
                for (v,) in con.execute('SELECT '+identificador(campo)+' FROM '+identificador(t)+' LIMIT 5'):
                    bruto=v if isinstance(v,(str,int,float,type(None))) else '<BLOB não decodificado>'
                    r=dict(tabela=t,campo=campo,bruto=bruto,interpretacao=None,confiabilidade='NAO_INTERPRETADO')
                    if t=='IdahoDataSet' and campo in ('HmiModelCoordinateReference','HMIDataSetGeometrySpatialReference') and isinstance(v,str) and len(v)<1_000_000:
                        try:
                            r['interpretacao']=interpretar_crs(v)
                            if r['interpretacao']:r['confiabilidade']='DECLARACAO_EXPLICITA';declarados.append(r['interpretacao']['crs'])
                        except (ValueError,TypeError,KeyError) as e:problemas.append(str(e));r['confiabilidade']='INCONSISTENTE'
                    if campo=='HMIDataSetGeometrySpatialReferenceConversionFactor':r['interpretacao']='Campo legado: zero/sem semântica validada não comprova conversão bruta'
                    registros.append(r)
    if antes!=hash_arquivo(p):raise ValueError('Fonte WaterGEMS mudou durante a leitura; salve snapshot consistente')
    unicos=set(declarados)
    if len(unicos)>1:problemas.append('Declarações de CRS conflitantes')
    crs=next(iter(unicos)) if len(unicos)==1 and not problemas else None
    return dict(crs=crs,estado='INCOMPATIVEL' if problemas else 'DECLARADO' if crs else 'PENDENTE',
        mensagem='CRS declarado nos metadados WaterGEMS.' if crs else 'CRS NÃO IDENTIFICADO NOS METADADOS WATERGEMS.',
        unidade_bruta=None,unidade_exibida=None,registros=registros,problemas=problemas,versao=versao,esquema=esquema,sha256=antes,arquivo=str(p))

def metadados_base(t,cancelar=None):
    meta=t['meta_base'];contexto=ref.contexto_modelo(t['modelo']);cache=meta.get('metadados_espaciais')
    if cache and cache.get('contexto_modelo')==contexto:return cache
    o=meta.get('origem',{});esperado=o.get('sha256_snapshot')
    for nome in ('snapshot','fonte'):
        p=Path(o.get(nome) or '__fonte_ausente__')
        wal=Path(str(p)+'-wal')
        if esperado and p.is_file() and not (wal.exists() and wal.stat().st_size) and hash_arquivo(p)==esperado:
            return dict(ler_metadados_sqlite(p,cancelar),contexto_modelo=contexto)
    return dict(crs=None,estado='PENDENTE',mensagem='CRS NÃO IDENTIFICADO NOS METADADOS WATERGEMS. Snapshot compatível indisponível; os dados persistidos continuam consultáveis.',registros=[],problemas=[],unidade_bruta=None,unidade_exibida=None,contexto_modelo=contexto)

def inventario_gis(d,projeto_crs=None,cancelar=None):
    linhas=[]
    for f in d['contexto']['fontes']:
        if f.get('modo'):continue
        bases.verificar(cancelar);c=QgsVectorLayer(f['fonte'],f['camada'],f['provedor']);crs=c.crs()
        linhas.append(dict(origem=f['origem'],camada=f['camada'],crs=crs.authid() or crs.toWkt(),unidade=QgsUnitTypes.toString(crs.mapUnits()),
            origem_informacao='Provedor QGIS '+f['provedor']+' (.prj/metadados espaciais da fonte)',estado='LIDO' if c.isValid() and crs.isValid() else 'PENDENTE',
            crs_registrado=f.get('crs_origem'),inconsistencia=bool(f.get('crs_origem') and f['crs_origem']!=crs.authid())))
    return dict(camadas=linhas,crs_projeto=projeto_crs,crs_auditoria=d['contexto']['parametros']['crs'])

def chave(v):
    return v if isinstance(v,str) else legivel(v) if v is not None else None

def candidatos_campos(d,modelo,cancelar=None,progresso=None):
    wg=Counter(e['label'] for e in modelo['elementos'].values() if e['familia']=='LINK' and e['excluido'] is False)
    saida=[]
    fontes=[f for f in d['contexto']['fontes'] if not f.get('modo')]
    for n,f in enumerate(fontes):
        c=QgsVectorLayer(f['fonte'],f['camada'],f['provedor'])
        if not c.isValid():continue
        nomes=[v.name() for v in c.fields()];cont={k:Counter() for k in nomes}
        for i,feat in enumerate(c.getFeatures(QgsFeatureRequest().setFlags(QgsFeatureRequest.NoGeometry))):
            if i%256==0:bases.verificar(cancelar)
            for k in nomes:cont[k][chave(valor_python(feat[k]))]+=1
        for k,co in cont.items():
            bons={v:n for v,n in co.items() if v is not None and str(v).strip()}
            saida.append(dict(origem=f['origem'],camada=f['camada'],campo=k,total=sum(co.values()),preenchidos=sum(bons.values()),nulos=co[None],vazios=sum(n for v,n in co.items() if isinstance(v,str) and not v.strip()),
                repetidos=sum(n for n in bons.values() if n>1),exatas=sum(n for v,n in bons.items() if wg[v]),unicas=sum(1 for v,n in bons.items() if n==1 and wg[v]==1),
                multiplas=sum(n for v,n in bons.items() if wg[v] and (n>1 or wg[v]>1)),nao_encontradas=sum(n for v,n in co.items() if not wg[v] or v is None or not str(v).strip()),exemplos=[dict(valor=v,quantidade=co[v]) for v in list(co)[:5]]))
        if progresso:progresso(int((n+1)*100/max(1,len(fontes))),'Analisando colunas GIS')
    for f in fontes:
        linhas=[r for r in saida if r['origem']==f['origem']];melhor=max((r['unicas'] for r in linhas),default=0)
        empate=sum(r['unicas']==melhor for r in linhas)>1
        for r in linhas:r['recomendacao']='RECOMENDADO; revisar se necessário' if melhor and r['unicas']==melhor and not empate else 'EMPATE; escolher explicitamente' if melhor and r['unicas']==melhor else ''
    return saida

def percentil(v,p):
    if not v:return None
    i=(len(v)-1)*p;lo=int(i);hi=min(lo+1,len(v)-1)
    return v[lo]+(v[hi]-v[lo])*(i-lo)

def comparar_hipoteses(modelo,regs,crs,tolerancia=.01,fatores=(1.,.3048),controles=(),cancelar=None,progresso=None):
    if not metro(crs):raise ValueError('A comparação exige CRS projetado métrico, obtido de fonte identificada')
    resultados=[];por_uid={r['uid']:r for r in regs};wg=modelo['elementos'];contexto=ref.contexto_modelo(modelo)
    for h,fator in enumerate(dict.fromkeys(fatores)):
        if not isfinite(fator) or fator<=0:raise ValueError('Fator de hipótese inválido')
        bases.verificar(cancelar)
        # O comparador validado continua sendo a autoridade da classificação.
        p=ref.previa(modelo,regs,dict(crs=crs,fator=fator),tolerancia,cancelar)
        erros=[];divergencias=[];pares=0
        for i,a in enumerate(p['associacoes']):
            if i%128==0:
                bases.verificar(cancelar)
                if progresso:progresso(int((h+i/max(1,len(regs)))*100/len(fatores)),'Comparando todos os vértices')
            if a['erro_xy_m'] is None or len(a['candidatos'])!=1:continue
            r=por_uid[a['gis_uid']];g=QgsGeometry();g.fromWkb(wg[a['candidatos'][0]]['geometria'])
            av=[(v.x()*fator,v.y()*fator) for v in g.vertices()];bv=[(v.x(),v.y()) for v in r['geometria'].vertices()]
            if len(av)!=len(bv) or not av:continue
            direto=[dist(x,y) for x,y in zip(av,bv)];inverso=[dist(x,y) for x,y in zip(av,reversed(bv))];ee=direto if max(direto)<=max(inverso) else inverso
            erros.extend(ee);pares+=1
            if a['situacao']!='INEQUIVOCA':
                centro=r['geometria'].centroid().asPoint();divergencias.append(dict(gis_uid=a['gis_uid'],wg_id=a['candidatos'][0],erro_m=a['erro_xy_m'],x=centro.x(),y=centro.y()))
        erros.sort();n=sum(a['situacao']=='INEQUIVOCA' for a in p['associacoes'])
        resultados.append(dict(fator=fator,unidade=ref.unidade_fator(fator),compativeis=n,geometrias_comparadas=pares,vertices_comparados=len(erros),
            media_m=mean(erros) if erros else None,mediana_m=median(erros) if erros else None,maximo_m=max(erros) if erros else None,p95_m=percentil(erros,.95),p99_m=percentil(erros,.99),
            inconsistencias=sum(a['situacao']=='INCONSISTENTE' for a in p['associacoes']),divergencias=divergencias,prova=p,
            junctions=[verificar_junction(modelo,c,fator,contexto) for c in controles]))
    melhor=max((r['compativeis'] for r in resultados),default=0);candidatos=[r for r in resultados if r['compativeis']==melhor and melhor>0]
    return dict(contexto_modelo=contexto,crs=crs,tolerancia_m=tolerancia,hipoteses=resultados,fator_recomendado=candidatos[0]['fator'] if len(candidatos)==1 else None,
        criterio='Sem transformação arbitrária: chaves bilaterais únicas, todos os vértices XY, tolerância definida pelo usuário; hipóteses de metro e pé internacional',
        gis_examinadas=len(regs),wg_examinadas=sum(e['familia']=='LINK' and e['excluido'] is False for e in wg.values()))

def verificar_junction(modelo,controle,fator,contexto=None):
    r=dict(controle,fator=fator,estado='NAO_ENCONTRADA',x_bruto=None,y_bruto=None,erro_m=None)
    if controle.get('contexto_modelo')!=(contexto or ref.contexto_modelo(modelo)):r['estado']='CONTEXTO_INCOMPATIVEL';return r
    e=modelo['elementos'].get(controle['id'])
    if not e or e['tipo']!='IdahoJunction' or e['label']!=controle['label'] or e['excluido'] is not False:return r
    g=QgsGeometry();g.fromWkb(e['geometria'] or b'')
    if g.isEmpty() or g.type()!=0:r['estado']='SEM_GEOMETRIA_PONTUAL';return r
    p=g.asPoint();dx=p.x()*fator-controle['x'];dy=p.y()*fator-controle['y'];limite=.5*10**(-controle.get('decimais',2))+1e-8
    r.update(x_bruto=p.x(),y_bruto=p.y(),x_convertido=p.x()*fator,y_convertido=p.y()*fator,dx=dx,dy=dy,erro_m=dist((0,0),(dx,dy)),ativo=e['ativo'],
        estado='COMPATIVEL' if abs(dx)<=limite and abs(dy)<=limite else 'INCOMPATIVEL',limite_por_eixo_m=limite)
    return r

def avaliar(t,relatorio,metadados,crs_documental=None):
    if relatorio.get('contexto_modelo')!=ref.contexto_modelo(t['modelo']):return dict(estado='INCOMPATIVEL',faltas=['Comparação pertence a outra versão ou composição do modelo'])
    motivos=[];crs=relatorio['crs'];fator=relatorio['fator_recomendado'];hs=[h for h in relatorio['hipoteses'] if h['fator']==fator]
    if not metro(crs):return dict(estado='INCOMPATIVEL',faltas=['Escolha um CRS projetado em metros; a referência não foi salva'])
    tolerancia=relatorio.get('tolerancia_m')
    if not isinstance(tolerancia,(int,float)) or not isfinite(tolerancia) or tolerancia<0:return dict(estado='INCOMPATIVEL',faltas=['Tolerância inválida; execute novamente a comparação'])
    if metadados.get('estado')=='INCOMPATIVEL':return dict(estado='INCOMPATIVEL',faltas=metadados['problemas'])
    declarado=metadados.get('crs') or crs_documental
    if not declarado:motivos.append('CRS WaterGEMS não identificado: consulte as propriedades do modelo e informe o CRS observado nas opções avançadas, ou reutilize uma referência compatível. A coincidência geométrica sozinha não determina o datum.')
    elif QgsCoordinateReferenceSystem(declarado)!=QgsCoordinateReferenceSystem(crs):return dict(estado='INCOMPATIVEL',faltas=['CRS WaterGEMS declarado difere do CRS da comparação; não aplicar transformação sem definição confiável'])
    if len(hs)!=1:motivos.append('Unidade bruta inconclusiva: nenhuma hipótese vencedora única')
    else:
        h=hs[0];minimo=min(3,relatorio['wg_examinadas'])
        if not isinstance(fator,(int,float)) or not isfinite(fator) or fator<=0 or h['unidade']!=ref.unidade_fator(fator):return dict(estado='INCOMPATIVEL',faltas=['Unidade e conversão incompatíveis; compare novamente'])
        if not minimo or h['compativeis']<minimo:motivos.append('Correspondências geométricas insuficientes')
        if h['geometrias_comparadas'] and h['compativeis']/h['geometrias_comparadas']<.95:motivos.append('Menos de 95% dos pares comparáveis concordam; investigue as divergências antes de salvar')
        if any(c['estado']!='COMPATIVEL' for c in h['junctions']):motivos.append('Controle Junction ausente, alterado ou incompatível')
    return dict(estado='PENDENTE' if motivos else 'APTO_PARA_CONFIRMACAO',faltas=motivos)

def confirmar_assistida(t,relatorio,metadados,aprovacao=False,responsavel='',documento=None):
    """Contrato técnico; argumentos administrativos antigos são opcionais.

    `aprovacao` permanece aceito para compatibilidade de chamadas, sem efeito.
    Um nome ou aceite nunca substitui CRS, unidades, contexto e geometria.
    """
    documento=documento or {};a=avaliar(t,relatorio,metadados,documento.get('crs'))
    if a['estado']!='APTO_PARA_CONFIRMACAO':raise ValueError('; '.join(a['faltas']))
    h=next(h for h in relatorio['hipoteses'] if h['fator']==relatorio['fator_recomendado'])
    fonte='Metadados SQLite '+str(metadados.get('sha256','')) if metadados.get('crs') else documento.get('fonte') or 'CRS complementar observado nas propriedades WaterGEMS e informado no assistente'
    r=ref.confirmar_prova(t['modelo'],dict(crs=relatorio['crs'],fator=h['fator'],unidade_bruta=h['unidade'],fonte=fonte),h['prova'],responsavel)
    r['validacao'].update(metodo='ASSISTENTE_METADADOS_E_VERTICES',base_origem=t['meta_base']['uuid'],assinatura_base=t['meta_base']['assinatura'],
        extrator=t['meta_base'].get('extrator'),regras=REGRAS,metadados=metadados,documento=documento,
        contrato='VERIFICACAO_TECNICA_SEM_APROVACAO_FORMAL',origem_crs='METADADOS_WATERGEMS' if metadados.get('crs') else 'REFERENCIA_ANTERIOR' if documento.get('base_evidencia') else 'CRS_COMPLEMENTAR_INFORMADO',
        estatisticas={k:v for k,v in relatorio.items() if k!='hipoteses'},hipoteses=[{k:v for k,v in hh.items() if k!='prova'} for hh in relatorio['hipoteses']])
    return r
