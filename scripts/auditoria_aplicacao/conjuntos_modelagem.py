"""Composição versionada referenciada aos elementos da exportação GIS."""

from collections import defaultdict
import re

from auditoria_fronteiras.entradas import digest
from auditoria_fronteiras.modelos import verificar_cancelamento


VERSAO=1
CATEGORIAS=('CORREDORES','BLOCOS','INTERVENCOES','TOPOLOGIA','ATIVIDADE','AREAS','ORIGENS','PERSONALIZADOS')
TIPOS=('PIPE','JUNCTION')
CAMPOS={
    'WNA_UID':'WNA_UID','WNA_PROCEDENCIA':'WNA_PROCED','WNA_ORIG_UID':'WNA_ORIG',
    'WNA_ID_GIS':'WNA_ID_GIS','WNA_CORREDOR':'WNA_CORR','WNA_BLOCO':'WNA_BLOCO',
    'WNA_INTERV':'WNA_INTERV','WNA_SITUACAO':'WNA_SIT','WNA_ATIVO':'WNA_ATIVO',
    'WNA_HIPOTESE':'WNA_HIP','WNA_REVISAO':'WNA_REV','WNA_ESQUEMA':'WNA_ESQ',
    'WNA_LABEL':'WNA_LABEL',
}
COLUNAS=('elemento_uid','conjunto_uid','tipo_elemento','categoria','nome','hipotese','revisao',
         'revisao_conjunto','execucao','situacao_participacao','label_previsto','original_uid',
         'id_gis','parte_uid','inicio','fim','conexao_uid')
CATALOGO=('uuid','nome','categoria','subpasta','descricao','origem','topologia_uid','hipotese',
          'hipotese_rev','projeto_uid','analise_uid','assinatura_topologia_exportavel','versao',
          'data_criacao','data_utc','rev','criterio')


def _hip(m):
    h=m.get('hipotese') or {}
    return h.get('uuid'),h.get('rev')


def indice(previa):
    tipos={'PIPE':previa['pipes'],'JUNCTION':previa['nos']}
    elementos={(tipo,r['uid']):r for tipo in TIPOS for r in tipos[tipo]}
    if len(elementos)!=sum(map(len,tipos.values())):
        raise ValueError('A exportação contém identidades de elementos repetidas.')
    return elementos


def validar(d,p):
    if (d.get('projeto_uid')!=p or not d.get('topologia_uid') or d.get('versao')!=VERSAO
            or not str(d.get('nome','')).strip() or d.get('categoria') not in CATEGORIAS
            or d.get('origem') not in ('AUTOMATICA','MANUAL')):
        raise ValueError('Informe um nome, categoria e contexto válidos para o conjunto.')
    rs=d.get('membros')
    if not isinstance(rs,list) or not rs or any(
            not isinstance(r,dict) or r.get('tipo') not in TIPOS or
            not re.fullmatch('[0-9a-f]{24}',str(r.get('uid',''))) for r in rs):
        raise ValueError('A composição deve conter identidades materializadas de Pipes ou Junctions.')
    if len({(r['tipo'],r['uid']) for r in rs})!=len(rs):
        raise ValueError('A composição contém elementos repetidos.')


def membro(tipo,r):
    campos=('parte','original','inicio','fim','no_a','no_b') if tipo=='PIPE' else ('portas',)
    dados={k:r[k] for k in campos}
    if tipo=='JUNCTION':dados['portas']=[list(p) for p in r['portas']]
    return dict(dados,tipo=tipo,uid=r['uid'])


def assinatura(previa):
    dados=indice(previa)
    return digest([previa['manifesto']['crs'],[membro(k[0],dados[k]) for k in sorted(dados)]])


def compor(previa,chaves,**meta):
    m=previa['manifesto']
    por_id=indice(previa)
    ids=sorted(set(chaves))
    if set(ids)-por_id.keys():raise ValueError('Há membros que não pertencem a esta exportação.')
    h,rev=_hip(m)
    meta.setdefault('hipotese_nome',(m.get('hipotese') or {}).get('nome'))
    d=dict(meta,projeto_uid=m['projeto'],topologia_uid=m['execucao'],hipotese=h,hipotese_rev=rev,
           assinatura_topologia_exportavel=m['assinatura_topologia_exportavel'],
           versao=VERSAO,membros=[membro(t,por_id[t,u]) for t,u in ids])
    validar(d,m['projeto'])
    return d


def por_segmentos(foto,indices):
    return {('PIPE',digest(['segmento_gis',e['tubo'],e['inicio'],e['fim']]))
            for i in indices for e in (foto['arestas'][i],)}


def da_conexao(previa,conexao):
    r=next((r for r in previa['operacoes'] if r['uuid']==conexao and r['tipo']=='CONEXAO'),None)
    if not r or r.get('resultado')!='APLICADA':
        raise ValueError('A conexão não foi aplicada nesta exportação.')
    portas={tuple(p) for p in r['portas']}
    nos={n['uid'] for n in previa['nos'] if portas.intersection(map(tuple,n['portas']))}
    candidatas={('PIPE',p['uid']) for p in previa['pipes'] for f in ('inicio','fim') if
                (p['parte'],p[f]) in portas and (p['no_a'] if f=='inicio' else p['no_b']) in nos}
    return candidatas|{('JUNCTION',u) for u in nos}


def reconciliar(d,previa,por_id=None):
    """Sugere apenas substituições que particionam exatamente a parte anterior."""
    m=previa['manifesto']
    if d['projeto_uid']!=m['projeto']:raise ValueError('O conjunto pertence a outro projeto.')
    atuais=indice(previa) if por_id is None else por_id
    por_parte=None
    saida=dict(preservados=[],divididos=[],novos=[],ausentes=[],ambiguos=[])
    for anterior in d['membros']:
        t,u=anterior['tipo'],anterior['uid']
        r=atuais.get((t,u))
        if r and anterior==membro(t,r):
            saida['preservados'].append((t,u))
        elif r:
            saida['ambiguos'].append((t,u))
        elif t=='JUNCTION':
            saida['ausentes'].append((t,u))
        else:
            if por_parte is None:
                por_parte=defaultdict(list)
                for (tipo,_),atual in atuais.items():
                    if tipo=='PIPE':por_parte[atual['parte']].append(atual)
            a,b=anterior['inicio'],anterior['fim']
            partes=[r for r in por_parte[anterior['parte']] if r['original']==anterior['original']
                    and a<=r['inicio']<r['fim']<=b]
            partes.sort(key=lambda r:r['inicio'])
            if (len(partes)>1 and partes[0]['inicio']==a and partes[-1]['fim']==b
                    and all(p['fim']==q['inicio'] and p['no_b']==q['no_a'] for p,q in zip(partes,partes[1:]))):
                saida['divididos'].append((u,[p['uid'] for p in partes]))
            elif por_parte[anterior['parte']]:
                saida['ambiguos'].append((t,u))
            else:
                saida['ausentes'].append((t,u))
    h,rev=_hip(m)
    saida['novos']=sorted({('PIPE',u) for _,us in saida['divididos'] for u in us})
    saida['compativel']=(d['topologia_uid']==m['execucao'] and d.get('hipotese')==h and d.get('hipotese_rev')==rev
                       and d.get('assinatura_topologia_exportavel')==m['assinatura_topologia_exportavel']
                       and len(saida['preservados'])==len(d['membros']))
    return saida


def selecionar(previa,chaves,*,tipo='TODOS',estado='TODOS',incluir_nos=False,atributo=None):
    por_id=indice(previa)
    ids=set(chaves)
    if ids-por_id.keys():raise ValueError('A seleção inclui elementos de outra exportação.')
    existentes={'EXISTENTE_CADASTRADO','EXISTENTE_INFORMADO','EXISTENTE_A_CONFIRMAR'}
    def elegivel(k):
        r=por_id[k]
        if atributo and str(r.get(atributo[0],''))!=atributo[1]:return False
        if estado=='ATIVO':return r.get('atividade')=='ATIVO'
        if estado=='PROPOSTO':return r.get('situacao') in ('PROPOSTO','HIPOTETICO')
        if estado=='EXISTENTE':return r.get('situacao') in existentes
        return True
    ids={k for k in ids if (tipo!='PIPE' or k[0]=='PIPE') and elegivel(k)}
    if incluir_nos and tipo!='PIPE':
        ids.update(('JUNCTION',por_id[k][campo]) for k in list(ids) if k[0]=='PIPE' for campo in ('no_a','no_b'))
    return ids


def preparar_exportacao(previa,conjuntos,*,somente_conjuntos=False,escopo=None,cancelar=None):
    m=previa['manifesto']
    por_id=indice(previa)
    hip,rev=_hip(m)
    associacoes=[]
    principais=defaultdict(dict)
    catalogo=[]
    for s in sorted(conjuntos,key=lambda r:(r['nome'].casefold(),r['uuid'])):
        verificar_cancelamento(cancelar)
        if s.get('arquivado'):raise ValueError('Recupere o conjunto arquivado antes de exportar.')
        if not reconciliar(s,previa,por_id)['compativel']:
            raise ValueError(f"Conjunto incompatível com a fotografia exportada ({s['nome']}). Confira a composição.")
        catalogo.append({k:s.get(k) for k in CATALOGO})
        for r in s['membros']:
            verificar_cancelamento(cancelar)
            t,u=r['tipo'],r['uid']
            e=por_id[t,u]
            principais[t,u].setdefault(s['categoria'],s['uuid'])
            associacoes.append(dict(elemento_uid=u,conjunto_uid=s['uuid'],tipo_elemento=t,categoria=s['categoria'],
                nome=s['nome'],hipotese=hip,revisao=rev,revisao_conjunto=s.get('rev'),execucao=m['execucao'],
                situacao_participacao=e.get('atividade','A_DEFINIR'),label_previsto='WNA_'+u[:24],
                original_uid=e.get('original'),id_gis=e.get('gis_id'),parte_uid=e.get('parte'),
                inicio=e.get('inicio'),fim=e.get('fim'),conexao_uid=(s.get('criterio') or {}).get('conexao')))
    if somente_conjuntos and not catalogo:raise ValueError('Escolha ao menos um conjunto para preparar.')
    selecionados=(set(principais) if somente_conjuntos else set(por_id)) if escopo is None else set(escopo)
    if selecionados-por_id.keys():raise ValueError('O escopo contém elementos ausentes do cadastro exportável.')
    # Junctions necessárias à geometria exportável permanecem disponíveis como contexto.
    selecionados.update(('JUNCTION',no) for t,u in list(selecionados) if t=='PIPE' for k in ('no_a','no_b')
                        if ('JUNCTION',no:=por_id[t,u].get(k)) in por_id)
    if principais.keys()-selecionados:raise ValueError('Um conjunto selecionado possui membros fora do escopo de exportação.')
    pipes,nos,rotulos=([],[],set())
    for (t,u),r in por_id.items():
        verificar_cancelamento(cancelar)
        if (t,u) not in selecionados:continue
        categorias=principais[t,u]
        label='WNA_'+u
        if label in rotulos:raise ValueError('Colisão de Labels de preparação. As identidades devem ser conferidas.')
        rotulos.add(label)
        origem=next((p[1] for p in r.get('portas',()) if p[0]=='J'),None)
        elementos=pipes if t=='PIPE' else nos
        elementos.append(dict(r,WNA_UID=u,WNA_LABEL=label,WNA_PROCEDENCIA=r.get('procedencia') or
            ('GIS_ORIGINAL' if origem else 'DERIVADO'),WNA_ORIG_UID=r.get('original') or origem,WNA_ID_GIS=r.get('gis_id'),
            WNA_CORREDOR=categorias.get('CORREDORES'),WNA_BLOCO=categorias.get('BLOCOS'),
            WNA_INTERV=categorias.get('INTERVENCOES'),WNA_SITUACAO=r.get('situacao') or r.get('natureza'),
            WNA_ATIVO=r.get('atividade','A_DEFINIR'),WNA_HIPOTESE=hip,WNA_REVISAO=rev,WNA_ESQUEMA=str(VERSAO)))
    return pipes,nos,catalogo,associacoes
