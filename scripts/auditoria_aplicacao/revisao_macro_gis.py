"""Revisões verificáveis da apresentação macro sem editar o grafo."""

from collections import defaultdict

from auditoria_fronteiras.modelos import verificar_cancelamento
from .macro_origem_gis import organizar_grupos, trabalho


def _continuo(foto,segmentos,cancelar):
    por_no=defaultdict(list)
    for i in segmentos:
        e=foto['arestas'][i]
        por_no[e['a']].append(i)
        por_no[e['b']].append(i)
    if not segmentos:return False
    estado={min(segmentos)}
    visitados=set()
    fila=list(estado)
    for i in fila:
        verificar_cancelamento(cancelar)
        e=foto['arestas'][i]
        for u in (e['a'],e['b']):
            if u in visitados:continue
            visitados.add(u)
            for j in por_no[u]:
                if j not in estado:
                    estado.add(j)
                    fila.append(j)
    return estado==segmentos


def revisar(d,acao,uid,valor,cancelar=None):
    m=dict(d['macro_origem'])
    foto=d['foto']
    if acao=='RENOMEAR_CORREDOR':
        nome=str(valor).strip()
        if not nome or all(c['uid']!=uid for c in m['corredores']):
            raise ValueError('Escolha um corredor e informe seu nome.')
        m['corredores']=[dict(c,nome=nome) if c['uid']==uid else c for c in m['corredores']]
    else:
        grupos={b['uid']:dict(b) for b in m['blocos']}
        if uid not in grupos:raise ValueError('O bloco não pertence à investigação.')
        bloco=grupos[uid]
        es=set(bloco['segmentos'])
        if acao=='RENOMEAR_BLOCO':
            nome=str(valor).strip()
            if not nome:raise ValueError('Informe um nome.')
            bloco['nome']=nome
        elif acao=='ASSOCIAR_AREA':
            if all(a['uid']!=valor for a in foto.get('areas',())):
                raise ValueError('Escolha uma área da fotografia.')
            bloco['areas_declaradas']=sorted(set(bloco['areas_declaradas'])|{valor})
        elif acao=='AGRUPAR':
            if valor==uid or valor not in grupos:
                raise ValueError('Escolha outro bloco adjacente.')
            outro=grupos.pop(valor)
            uniao=es|set(outro['segmentos'])
            if not _continuo(foto,uniao,cancelar):
                raise ValueError('Os blocos selecionados não formam um conjunto topologicamente contínuo.')
            bloco.update(segmentos=sorted(uniao),criterio='AGRUPADO',
                         areas_declaradas=sorted(set(bloco['areas_declaradas'])|set(outro['areas_declaradas'])))
        elif acao=='DIVIDIR':
            escolhido=set(valor)
            if (not escolhido<es or not _continuo(foto,es-escolhido,cancelar)
                    or not _continuo(foto,escolhido,cancelar)):
                raise ValueError('Selecione segmentos que produzam dois conjuntos topologicamente contínuos.')
            bloco.update(segmentos=sorted(es-escolhido),criterio='DIVIDIDO')
            grupos['novo']=dict(bloco,nome=bloco['nome']+' · divisão',segmentos=sorted(escolhido))
        else:raise ValueError('Ajuste de agrupamento não reconhecido.')
        m['blocos'],m['ligacoes']=organizar_grupos(foto,m,grupos.values(),cancelar)
    anterior=d['uuid']
    original=d.get('automatico_macro',anterior)
    return dict(trabalho(foto,m,d['nome']),referencia=anterior,automatico_macro=original,
                ajuste_macro=dict(acao=acao,alvo=uid,valor=valor))
