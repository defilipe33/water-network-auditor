"""Configurações, comparação e regeneração independente; reutiliza núcleo/agrupador."""
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256

from .entradas import digest,valor_python
from .inspecao import construir_dossie,restaurar,texto
from .investigacao import analisar_investigacao,OpcoesLocais,instante_execucao
from .modelos import verificar_cancelamento


def perfil(dossie):
    if 'configuracao' in dossie:
        return deepcopy(dossie['configuracao'])
    return dict(fontes=deepcopy(dossie['contexto']['fontes']),
        geometria={k:v for k,v in dossie['contexto']['parametros'].items() if k!='distancia_agrupamento'},
        agrupamento=deepcopy(dossie['analise']['opcoes']),campos_interesse=deepcopy(dossie['campos_interesse']),
        funcionalidades=dict(auditoria_espacial=True),exportacao={},assinaturas_fontes={})


def inicializar(dossie,nome='',projeto='',origem=None,tipo='PROCESSAMENTO_COMPLETO',modo='NOVA'):
    agora=instante_execucao()
    dossie['configuracao']=perfil(dossie)
    dossie['controle_versao']=dict(nome=nome or 'Auditoria '+dossie['execucao_uid'][:8],
        projeto=projeto,data_criacao_utc=agora,data_processamento_utc=agora,
        execucao_origem=origem['execucao_uid'] if origem else None,
        base_origem=None,tipo_operacao=tipo,modo_salvamento=modo)
    return dossie


def assinatura_camada(camada,cancelar=None):
    valores=[]
    for f in camada.getFeatures():
        verificar_cancelamento(cancelar)
        attrs={c.name():valor_python(f[c.name()]) for c in camada.fields()}
        valores.append(digest([attrs,bytes(f.geometry().asWkb()).hex()]))
    return sha256(texto([camada.crs().toWkt(),[(f.name(),f.typeName()) for f in camada.fields()],sorted(valores)]).encode()).hexdigest()


def configuracao_proposta(redes,limites,parametros,opcoes,campos=None,exportacao=None,cancelar=None):
    fontes=[]
    assinaturas={}
    for configuracoes,poligonal in ((redes,False),(limites,True)):
        for c in configuracoes:
            camada=c.camada
            origem=c.chave_origem or digest([camada.providerType(),camada.source()])
            fontes.append(dict(origem=origem,camada=camada.name(),fonte=camada.source(),provedor=camada.providerType(),
                crs_origem=camada.crs().authid(),campo_id=c.campo_id,campo_nome=c.campo_nome,
                modo=c.modo.value if poligonal else None))
            assinaturas[origem]=assinatura_camada(camada,cancelar)
    return dict(fontes=fontes,geometria={k:v for k,v in asdict(parametros).items() if k!='distancia_agrupamento'},
        agrupamento=asdict(opcoes),campos_interesse=deepcopy(campos or {}),exportacao=deepcopy(exportacao or {}),
        funcionalidades=dict(auditoria_espacial=True),assinaturas_fontes=assinaturas)


def comparar_configuracoes(antes,depois):
    diferencas=[]
    af={f['origem']:f for f in antes['fontes']}
    df={f['origem']:f for f in depois['fontes']}
    for origem in sorted(set(af)|set(df)):
        for campo in sorted(set(af.get(origem,{}))|set(df.get(origem,{}))):
            a=af.get(origem,{}).get(campo);b=df.get(origem,{}).get(campo)
            if a!=b:
                diferencas.append(dict(categoria='ENTRADA',item=origem+': '+campo,antes=a,depois=b))
    for categoria in ('geometria','agrupamento','funcionalidades','campos_interesse','exportacao'):
        a=antes.get(categoria,{});b=depois.get(categoria,{})
        for k in sorted(set(a)|set(b)):
            if a.get(k)!=b.get(k):
                diferencas.append(dict(categoria=categoria.upper(),item=k,antes=a.get(k),depois=b.get(k)))
    verificacao=[]
    for origem in set(af)&set(df):
        a=antes.get('assinaturas_fontes',{}).get(origem)
        b=depois.get('assinaturas_fontes',{}).get(origem)
        if a and b and a!=b:
            diferencas.append(dict(categoria='CONTEUDO_GIS',item=origem,antes=a,depois=b))
        elif not a:
            verificacao.append(origem)
    geometricas=any(d['categoria'] in ('ENTRADA','GEOMETRIA','FUNCIONALIDADES','CONTEUDO_GIS',
        'CAMPOS_INTERESSE') for d in diferencas)
    return dict(diferencas=diferencas,requer_nucleo=geometricas,
        recomendar_regerar=not geometricas and not verificacao,fontes_sem_assinatura_anterior=sorted(verificacao))


def contexto_eventos(d):
    p=perfil(d)
    fontes=[{k:f.get(k) for k in ('origem','fonte','provedor','campo_id','campo_nome','modo','crs_origem')}
            for f in p['fontes']]
    # O caminho pode ser realocado sem mudar a identidade do cadastro. A origem
    # explícita e o conteúdo técnico dos eventos continuam obrigatórios.
    for f in fontes:
        f.pop('fonte',None)
    return digest([p['geometria'],sorted(fontes,key=lambda f:f['origem']),p['funcionalidades']])


def comparar_locais(antigo,novo,revisoes_por_local=None):
    antigos={l['uid']:l for l in antigo['locais']}
    novos={l['uid']:l for l in novo['locais']}
    por_evento=defaultdict(set)
    for uid,l in antigos.items():
        for evento in l['eventos']:
            por_evento[evento].add(uid)
    contexto_igual=contexto_eventos(antigo)==contexto_eventos(novo)
    eventos_a={e['uid']:e['tecnico'] for e in antigo['eventos']}
    eventos_b={e['uid']:e['tecnico'] for e in novo['eventos']}
    def bruto(e):
        e=e.copy();e.pop('apresentacao',None)
        return e
    ad=defaultdict(set);da=defaultdict(set)
    correspondencias=[]
    for uid,l in novos.items():
        membros=set(l['eventos'])
        candidatos=set().union(*(por_evento[e] for e in membros)) if membros else set()
        for anterior in sorted(candidatos):
            am=set(antigos[anterior]['eventos'])
            comuns=sorted(am&membros)
            exata=(contexto_igual and am==membros and anterior==uid and
                all(bruto(eventos_a[e])==bruto(eventos_b[e]) for e in membros))
            correspondencias.append(dict(anterior=anterior,novo=uid,eventos=comuns,tipo='EXATA' if exata else 'PARCIAL'))
            ad[anterior].add(uid);da[uid].add(anterior)
    exatos={c['novo'] for c in correspondencias if c['tipo']=='EXATA'}
    anteriores_exatos={c['anterior'] for c in correspondencias if c['tipo']=='EXATA'}
    afetados=set(antigos)-anteriores_exatos
    contagens=revisoes_por_local or {l['uid']:int(bool(l.get('revisao',{}).get('uid'))) for l in antigo['locais']}
    return dict(distancia_anterior=antigo['analise']['opcoes']['distancia'],
        distancia_nova=novo['analise']['opcoes']['distancia'],locais_antes=len(antigos),locais_depois=len(novos),
        mantidos=len(exatos),divididos=sum(len(v)>1 for v in ad.values()),fundidos=sum(len(v)>1 for v in da.values()),
        novos=len(set(novos)-exatos),sem_correspondencia=sum(not da[u] for u in novos),
        antigos_sem_sucessor=sum(not ad[u] for u in antigos),
        revisoes_afetadas=sum(contagens.get(u,0) for u in afetados),
        locais_revisados_afetados=sum(bool(contagens.get(u,0)) for u in afetados),
        correspondencias=correspondencias,locais_herdaveis=sorted(exatos))


def regerar(dossie,opcoes,cancelar=None):
    """Somente o agrupador aprovado. Nenhuma leitura das entradas ou chamada ao núcleo."""
    opcoes.validar()
    resultado,_=restaurar(dossie)
    analise=analisar_investigacao(resultado,opcoes,cancelar,
        dossie['analise']['metadados'].get('data_execucao_utc'))
    novo=construir_dossie(resultado,analise,dossie['campos_interesse'])
    for campo in ('eventos','contexto','tubulacoes','poligonos','evento_rede','evento_poligono'):
        novo[campo]=deepcopy(dossie[campo])
    inicializar(novo,dossie.get('controle_versao',{}).get('nome',''),
        dossie.get('controle_versao',{}).get('projeto',''),dossie,'REAGRUPAMENTO')
    novo['configuracao']=perfil(dossie)
    novo['configuracao']['agrupamento']=asdict(opcoes)
    if texto(novo['eventos'])!=texto(dossie['eventos']):
        raise ValueError('A regeneração alterou eventos')
    return novo,comparar_locais(dossie,novo)
