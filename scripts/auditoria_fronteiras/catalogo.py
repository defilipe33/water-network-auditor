"""Catálogo local, identidade das camadas publicadas e resolução de fontes."""
import json
import os
from pathlib import Path
from .inspecao import texto,restaurar

PREFIXO='auditoria_fronteiras/'
CATALOGO_APLICACAO=None


def caminho_catalogo():
    if CATALOGO_APLICACAO is not None:return Path(CATALOGO_APLICACAO)
    return Path(__file__).resolve().parents[2]/'resultados'/'auditorias_recentes.json'


def recentes(caminho=None):
    p=Path(caminho or caminho_catalogo())
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding='utf-8'))


def lembrar(base,exe,caminho=None):
    from .versoes import listar
    registro=next(r for r in listar(base) if r['execucao_uid']==exe)
    p=Path(caminho or caminho_catalogo())
    itens=[r for r in recentes(p) if (r['base'],r['execucao_uid'])!=(registro['base'],exe)]
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.tmp')
    tmp.write_text(json.dumps([registro]+itens,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(tmp,p)
    return registro


def carregadas(projeto):
    """Metadados de resultados ou EXE_UID de um GPKG completo, nunca só o nome."""
    from .versoes import listar
    encontradas={};avisos=[]
    for c in projeto.mapLayers().values():
        base=c.customProperty(PREFIXO+'base','')
        if not base and hasattr(c,'source'):
            candidato=c.source().split('|')[0]
            if candidato.lower().endswith('.gpkg'):
                base=candidato
        if not base:
            if hasattr(c,'fields') and 'EVT_UID' in c.fields().names():
                avisos.append(c.name()+': resultado sem base relacional; selecione o GPKG completo.')
            continue
        try:
            identidades=json.loads(c.customProperty(PREFIXO+'execucoes','[]'))
            if not identidades and hasattr(c,'fields') and 'EXE_UID' in c.fields().names():
                identidades=list(c.uniqueValues(c.fields().indexFromName('EXE_UID')))
            for r in listar(base):
                if r['execucao_uid'] in identidades:
                    encontradas[(r['base'],r['execucao_uid'])]=r
        except (OSError,ValueError,RuntimeError) as erro:
            avisos.append(c.name()+': '+str(erro))
    return list(encontradas.values()),avisos


def publicar(d,base,projeto,camadas=None):
    from .visualizacao import criar_camadas_temporarias,carregar_no_projeto
    from .painel import aplicar_revisoes
    import hashlib
    assinatura=hashlib.sha256(texto(d['eventos']).encode()).hexdigest()
    uid=d['execucao_uid']
    existentes=list(projeto.mapLayers().values())
    r,a=restaurar(d)
    novas=camadas if camadas is not None else criar_camadas_temporarias(r,analise=a)
    saida=[]
    for c in novas:
        papel=c.customProperty(PREFIXO+'papel','')
        encontrados=[]
        for x in existentes:
            if x.customProperty(PREFIXO+'papel','')!=papel or not x.isValid() or x.wkbType()!=c.wkbType():
                continue
            ids=json.loads(x.customProperty(PREFIXO+'execucoes','[]'))
            mesma=uid in ids
            compartilhavel=(str(x.customProperty(PREFIXO+'base',''))==str(base or '') and
                papel in ('apresentacao','tecnica') and
                x.customProperty(PREFIXO+'assinatura_eventos','')==assinatura)
            if (mesma or compartilhavel) and x.featureCount()==c.featureCount() and x.fields().names()==c.fields().names():
                encontrados.append(x)
        escolhido=encontrados[0] if encontrados else c
        ids=json.loads(escolhido.customProperty(PREFIXO+'execucoes','[]'))
        escolhido.setCustomProperty(PREFIXO+'execucoes',json.dumps(sorted(set(ids+[uid]))))
        escolhido.setCustomProperty(PREFIXO+'base',str(base or ''))
        escolhido.setCustomProperty(PREFIXO+'assinatura_eventos',assinatura)
        saida.append(escolhido)
    aplicar_revisoes(saida,d)
    carregar_no_projeto(saida,projeto)
    return r,a,saida


def resolver_fontes(config,projeto,realocar=None,permitir_campos_ausentes=False):
    """Realocação explícita preserva origem técnica; campos ausentes são erro."""
    from qgis.core import QgsVectorLayer
    resolvidas={};avisos=[]
    for f in config['fontes']:
        candidatas=[c for c in projeto.mapLayers().values() if isinstance(c,QgsVectorLayer)
            and c.isValid() and c.providerType()==f['provedor'] and c.source()==f['fonte']]
        if len(candidatas)>1:
            raise ValueError('Múltiplas fontes carregadas para '+f['camada']+'; remova a duplicidade antes de reprocessar.')
        c=candidatas[0] if candidatas else QgsVectorLayer(f['fonte'],f['camada'],f['provedor'])
        if not c.isValid() and realocar:
            uri=realocar(f)
            if uri:
                if '|' in f['fonte'] and '|' not in uri:
                    uri+='|'+f['fonte'].split('|',1)[1]
                c=QgsVectorLayer(uri,f['camada'],f['provedor'])
        if not c.isValid():
            raise ValueError('Fonte indisponível: '+f['camada']+' — '+f['fonte'])
        extras=config.get('campos_interesse',{}).get(f['origem'],{})
        for campo in [f.get('campo_id'),f.get('campo_nome')]+list(extras.values()):
            if campo and campo not in c.fields().names():
                mensagem='Campo ausente em '+c.name()+': '+campo
                if not permitir_campos_ausentes:
                    raise ValueError(mensagem)
                avisos.append(mensagem+'; escolha novamente no formulário antes de executar.')
        if not projeto.mapLayer(c.id()):
            projeto.addMapLayer(c)
        resolvidas[f['origem']]=c
    return resolvidas,avisos
