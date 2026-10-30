"""Evidência contextual de CRS/unidades; não infere EPSG nem altera o modelo fonte."""
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,timezone
import json
from math import isfinite,isclose
from pathlib import Path
from uuid import uuid4
from qgis.core import QgsCoordinateReferenceSystem,QgsUnitTypes,QgsGeometry
from . import bases
from .arquivos import hash_arquivo


def contexto_modelo(m):
    return bases.assinatura_modelo({k:v for k,v in m.items() if k!='referencia_espacial'},'ESTRUTURAL')


def unidade_fator(fator):
    if isclose(fator,1,rel_tol=0,abs_tol=1e-12):return 'METRO'
    if isclose(fator,.3048,rel_tol=0,abs_tol=1e-12):return 'PE_INTERNACIONAL'
    return 'OUTRA_DECLARADA'


def estado_referencia(ref,modelo=None):
    ref=ref or {};faltas=[];incomp=False
    crs=QgsCoordinateReferenceSystem(ref.get('crs',''))
    if not crs.isValid() or crs.isGeographic() or crs.mapUnits()!=QgsUnitTypes.DistanceMeters:faltas.append('CRS projetado em metros não confirmado')
    fator=ref.get('fator')
    if not isinstance(fator,(int,float)) or not isfinite(fator) or fator<=0:faltas.append('fator bruto → metro inválido ou ausente')
    if not str(ref.get('fonte','')).strip():faltas.append('fonte da evidência não informada')
    unidade=ref.get('unidade_bruta')
    if unidade in ('METRO','PE_INTERNACIONAL') and isinstance(fator,(int,float)) and isfinite(fator) and fator>0 and not isclose(fator,1 if unidade=='METRO' else .3048,rel_tol=0,abs_tol=1e-12):
        faltas.append('unidade bruta e fator se contradizem');incomp=True
    v=ref.get('validacao',{})
    if v and not unidade:faltas.append('unidade bruta não registrada')
    if v and not v.get('contexto_modelo'):faltas.append('validação sem vínculo à composição técnica do modelo')
    if modelo is not None and v.get('contexto_modelo') and v['contexto_modelo']!=contexto_modelo(modelo):faltas.append('evidência pertence a outra composição ou contexto do modelo');incomp=True
    if v and v.get('estado')!='VALIDADO':faltas.append('validação registrada não foi concluída')
    return dict(estado='INCOMPATIVEL' if incomp else 'PENDENTE' if faltas else 'VALIDADO',faltas=faltas,
        metodo=v.get('metodo','DECLARACAO_LEGADA' if ref else 'NAO_VALIDADO'),legada=bool(ref and not v))


def ler_evidencia(caminho):
    p=Path(caminho).resolve(strict=True);h=hash_arquivo(p)
    if p.suffix.lower()=='.gpkg':
        t=bases.restaurar(p);ref=deepcopy(t['meta_base'].get('referencia_espacial') or {})
        contexto=contexto_modelo(t['modelo']);modelo=t['modelo']['projeto'];cenario=t['modelo']['cenario']
    else:
        dados=json.loads(p.read_text(encoding='utf8'));m=dados.get('modelo',{})
        ref=deepcopy(m.get('referencia_espacial') or dados.get('referencia_espacial') or dados)
        contexto=ref.get('validacao',{}).get('contexto_modelo');modelo=m.get('projeto');cenario=m.get('cenario')
    if h!=hash_arquivo(p):raise ValueError('A evidência mudou durante a consulta; selecione novamente')
    return dict(referencia=ref,contexto=contexto,modelo=modelo,cenario=cenario,arquivo=str(p),sha256=h)


def compatibilidade(modelo,evidencia):
    if evidencia.get('modelo') and evidencia['modelo']!=modelo['projeto']:return dict(estado='INCOMPATIVEL',faltas=['identidade do modelo diferente'])
    if not evidencia.get('contexto'):return dict(estado='PENDENTE',faltas=['evidência anterior sem assinatura reproduzível; conferir amostras no modelo atual'])
    if evidencia['contexto']!=contexto_modelo(modelo):return dict(estado='INCOMPATIVEL',faltas=['geometrias, elementos, cenário ou alternativas mudaram; validar novamente'])
    return estado_referencia(evidencia['referencia'],modelo)


def referencia_reutilizada(modelo,evidencia,responsavel=''):
    c=compatibilidade(modelo,evidencia)
    if c['estado']!='VALIDADO':raise ValueError('; '.join(c['faltas']))
    r=deepcopy(evidencia['referencia']);r['unidade_bruta']=r.get('unidade_bruta') or unidade_fator(r['fator'])
    anterior=deepcopy(r.get('validacao',{}))
    r['validacao']=dict(estado='VALIDADO',contexto_modelo=contexto_modelo(modelo),metodo='REUSO_CONTEXTUAL_CONFIRMADO',validacao_anterior=anterior,
        fonte_anterior=evidencia['arquivo'],sha256_anterior=evidencia['sha256'],responsavel=responsavel,data=datetime.now(timezone.utc).isoformat())
    return r


def previa(modelo,registros,ref=None,tolerancia=.01,cancelar=None):
    """Prévia cadastral não equivale a vínculo inequívoco sem prova espacial."""
    from .gerenciamento import provar_fontes
    if not isfinite(tolerancia) or tolerancia<0:raise ValueError('Tolerância deve ser finita e não negativa')
    wg=defaultdict(list)
    for i,e in modelo['elementos'].items():
        if e['familia']=='LINK' and e['excluido'] is False:wg[e['label']].append(i)
    cont=Counter(r['chave_cadastral'] for r in registros)
    c=QgsCoordinateReferenceSystem((ref or {}).get('crs',''))
    espacial=bool(ref and c.isValid() and not c.isGeographic() and c.mapUnits()==QgsUnitTypes.DistanceMeters and isinstance(ref.get('fator'),(float,int)) and isfinite(ref['fator']) and ref['fator']>0)
    if espacial:assocs,evidencia=provar_fontes(modelo,registros,ref['fator'],tolerancia,cancelar)
    else:
        assocs=[];evidencia={}
        for r in registros:
            k=r['chave_cadastral'];c=wg.get(k,[]) if k is not None and str(k).strip() else []
            s='NAO_ENCONTRADA' if not c else 'MULTIPLAS_CANDIDATAS' if len(c)>1 or cont[k]>1 else 'UNICA_CADASTRAL_SEM_PROVA_ESPACIAL'
            assocs.append(dict(gis_uid=r['uid'],candidatos=c,situacao=s,erro_xy_m=None,origem=r['origem']))
    regs={r['uid']:r for r in registros};linhas=[];camadas=[]
    for origem in sorted({r['origem'] for r in registros}):
        rs=[r for r in registros if r['origem']==origem];ids={r['uid'] for r in rs};aa=[a for a in assocs if a['gis_uid'] in ids]
        camadas.append(dict(camada=rs[0].get('camada',origem),campo=rs[0].get('campo'),campo_wg='Label',total=len(rs),nulos=sum(r.get('bruto',r['chave_cadastral']) is None for r in rs),
            vazios=sum(isinstance(r.get('bruto',r['chave_cadastral']),str) and not r.get('bruto',r['chave_cadastral']).strip() for r in rs),
            repetidos=sum(cont[r['chave_cadastral']]>1 for r in rs if r['chave_cadastral'] is not None and str(r['chave_cadastral']).strip()),
            unicas=sum(a['situacao'] in ('INEQUIVOCA','UNICA_CADASTRAL_SEM_PROVA_ESPACIAL') for a in aa),nao_encontradas=sum(not a['candidatos'] for a in aa),inconsistencias_geometricas=sum(a['situacao']=='INCONSISTENTE' and bool(a['candidatos']) for a in aa)))
    # Amostras representativas, inclusive pendências; a prova completa está em assocs.
    amostras=[]
    for codigo in sorted({a['situacao'] for a in assocs}):amostras.extend(sorted((a for a in assocs if a['situacao']==codigo),key=lambda a:a['gis_uid'])[:20])
    for a in amostras[:100]:
        r=regs[a['gis_uid']];g=r['geometria'];cg=g.centroid().asPoint() if not g.isEmpty() else None
        for i in a['candidatos'] or [None]:
            e=modelo['elementos'].get(i,{});gw=QgsGeometry()
            if e.get('geometria'):gw.fromWkb(bytes(e['geometria']))
            cw=gw.centroid().asPoint() if not gw.isEmpty() else None;f=ref['fator'] if espacial else 1
            linhas.append([r.get('camada'),r.get('campo'),r.get('bruto',r['chave_cadastral']),e.get('label'),i,a['situacao'],a['erro_xy_m'],
                cg.x() if cg else None,cg.y() if cg else None,cw.x()*f if cw else None,cw.y()*f if cw else None,
                g.asWkt(),gw.asWkt() if not gw.isEmpty() else None])
    return dict(camadas=camadas,amostras=linhas,associacoes=assocs,evidencia=evidencia,espacial=espacial)


def confirmar_prova(modelo,ref,prova,responsavel=''):
    r=deepcopy(ref);estado=estado_referencia(r)
    if estado['estado']!='VALIDADO':raise ValueError('; '.join(estado['faltas']))
    if not r.get('unidade_bruta'):raise ValueError('Identifique a unidade bruta, sem deduzi-la do município')
    minimos=min(3,sum(e['familia']=='LINK' and e['excluido'] is False for e in modelo['elementos'].values()))
    n=sum(a['situacao']=='INEQUIVOCA' for a in prova['associacoes'])
    if not prova['espacial'] or minimos==0 or n<minimos:raise ValueError(f'Amostras insuficientes: {n} pares compatíveis; são necessários ao menos {max(1,minimos)}. Continue topologicamente ou obtenha evidência independente.')
    r['validacao']=dict(estado='VALIDADO',contexto_modelo=contexto_modelo(modelo),metodo='VERTICES_E_CONFIRMACAO_DOCUMENTAL',responsavel=responsavel,
        data=datetime.now(timezone.utc).isoformat(),evidencia=prova['evidencia'],camadas=prova['camadas'],amostras=prova['amostras'])
    return r


def salvar_referencia(base,destino,ref,cancelar=None):
    """Nova versão a partir do snapshot, sem reextrair o SQLite ou mudar arestas."""
    t=bases.restaurar(base,cancelar);estado=estado_referencia(ref,t['modelo'])
    if estado['estado']!='VALIDADO' or not ref.get('validacao'):raise ValueError('Confirme uma evidência compatível antes de gravar a versão espacial')
    if Path(destino).exists():raise FileExistsError('Escolha destino novo; a versão anterior não será substituída')
    ref=deepcopy(ref)
    pasta=Path(destino).resolve().parent/'_tecnicos'/uuid4().hex;pasta.mkdir(parents=True,exist_ok=False)
    anexo=ref['validacao'].get('anexo')
    if anexo:
        import shutil
        origem=Path(anexo['arquivo']);bases.verificar(cancelar)
        if hash_arquivo(origem)!=anexo['sha256']:raise ValueError('Documento de evidência mudou; anexe novamente')
        evidencias=pasta/'evidencias';evidencias.mkdir();copia=evidencias/origem.name
        shutil.copyfile(origem,copia)
        if hash_arquivo(copia)!=anexo['sha256']:raise ValueError('Cópia da evidência não íntegra')
        anexo['copia_controlada']=str(copia)
    (pasta/'EVIDENCIA_REFERENCIA.json').write_text(bases.texto(ref),encoding='utf8')
    m=t['modelo'];m['referencia_espacial']=deepcopy(ref);meta=deepcopy(t['meta_base'])
    if ref['validacao'].get('metadados'):meta['metadados_espaciais']=deepcopy(ref['validacao']['metadados'])
    meta.update(uuid=uuid4().hex,versao=meta['versao']+1,anterior=meta['uuid'],base_anterior=str(Path(base).resolve()),
        referencia_espacial=deepcopy(ref),crs=ref['crs'],assinatura=bases.assinatura_modelo(m,meta['hipotese']),data=datetime.now(timezone.utc).isoformat(),operacao='VALIDACAO_REFERENCIA_ESPACIAL')
    return bases.persistir(dict(sem_alteracao=False,meta=meta,modelo=m,estrutural=t['estrutural'],potencial=t['potencial'],pasta=str(pasta)),destino,cancelar)
