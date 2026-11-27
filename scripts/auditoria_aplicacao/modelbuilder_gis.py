"""Contrato do pacote ModelBuilder, derivado do cadastro GIS materializado."""

from collections import Counter, defaultdict
from math import dist, isfinite
from pathlib import Path
import json
import re

from auditoria_fronteiras.entradas import digest
from auditoria_fronteiras.modelos import verificar_cancelamento
from .investigacao_gis import geometria
from . import labels_modelagem as labels
from .validacao_modelbuilder_gis import PendenciasCriticas, diagnosticar
from .tipos_modelbuilder import (CAMADAS, CAMPOS_EQUIPAMENTO, DIRECIONAIS, INVENTARIO,
    PROPRIEDADES, TIPOS_NOS, UNIDADES, atributos as _atributos, composicoes_booster, numero as _numero)


VERSAO = 1
CAMPOS_PIPE = dict(mb_inicio='MB_INICIO', mb_fim='MB_FIM', mb_tipo_a='MB_TIPO_A', mb_tipo_b='MB_TIPO_B',
                  label_no_A='label_no_A', label_no_B='label_no_B',
                  mb_comp_h='MB_COMP_H', mb_hw_c='MB_HW_C', segmento_anterior='SEG_ANT')
CAMPOS_NO = dict(mb_x='MB_X', mb_y='MB_Y', mb_cota='MB_COTA', mb_carga='MB_CARGA',
                 mb_nmin='MB_NMIN', mb_nini='MB_NINI', mb_nmax='MB_NMAX', mb_diam='MB_DIAM')
CAMPOS_REAIS = set(CAMPOS_NO) | {'mb_comp_h','mb_hw_c','mb_ajuste','posicao_pipe'}
DESTINOS = ('2020', '2026', 'OUTRA')
COLUNAS_ESPERADO = ('tipo','uid','label','gis_id','orig_uid','parte','inicio','fim','no_a','no_b',
                    'x','y','comprimento_geom_m','comprimento_hid_m','diametro_mm','atividade','assinatura_geometria')
COLUNAS_PENDENCIA = ('tipo','uid','motivo','classe','gravidade','codigo','gis_id','label_cadastral','camada',
                     'original','parte','inicio','fim','no_a','no_b','coordenadas','relacoes','solucao',
                     'comprimento_m','tolerancia_grafo_m')
COLUNAS_EVIDENCIA_LEGADO = ('tipo','uid','id_modelo','label','gis_id','no_a','no_b','x','y',
                     'comprimento_geom_m','comprimento_hid_m','diametro_mm','atividade')
COLUNAS_EVIDENCIA=(*COLUNAS_EVIDENCIA_LEGADO,'montante','jusante','pipe_associado')


def validar_perfil(p):
    if p.get('versao') != VERSAO or p.get('destino') not in DESTINOS or p.get('modo') not in ('NOVO','ATUALIZAR'):
        raise ValueError('Perfil ModelBuilder incompatível.')
    if not str(p.get('nome','')).strip() or not isinstance(p.get('campos'), dict):
        raise ValueError('Dê um nome ao perfil e confira os campos.')
    tipos = p.get('tipos', ())
    if not {'PIPE', 'JUNCTION'} <= set(tipos) <= set(PROPRIEDADES):
        raise ValueError('Selecione Pipes, Junctions e apenas tipos compatíveis.')
    for tipo, campos in p['campos'].items():
        if tipo not in PROPRIEDADES or not isinstance(campos,dict) or set(campos)-PROPRIEDADES[tipo].keys():
            raise ValueError('Há uma propriedade que não pertence ao tipo selecionado.')
        for k, valor in campos.items():
            if (not isinstance(valor,dict) or not str(valor.get('campo','')).strip() or
                    valor.get('unidade') not in UNIDADES[PROPRIEDADES[tipo][k][1]]):
                raise ValueError('Informe o campo de origem e a unidade compatível.')
    if p['modo']=='ATUALIZAR' and not str(p.get('modelo_destino','')).strip():
        raise ValueError('Identifique o modelo de destino para preparar uma atualização.')
    labels.validar_prefixos(p.get('prefixos',{}))
    return p


def _portas_equipamentos(previa):
    portas = {tuple(porta): n['uid'] for n in previa['nos'] for porta in n.get('portas', ())}
    resultado = defaultdict(set)
    for r in previa['operacoes']:
        if r['tipo']=='ORIGEM' and r.get('equipamento') and r['portas']:
            p = [portas.get(tuple(x)) for x in r['portas']]
            if all(p):
                resultado[r['equipamento']].update(p)
    for e in previa['equipamentos']:
        for relacao in e.get('declaracoes', ()):
            p = [portas.get(tuple(x)) for x in relacao.get('portas',())]
            if p and all(p):
                resultado[e['uid']].update(p)
    return resultado


def _conferir_equipamentos(previa,pipes,nos,inventario,perfil,pendencias,tolerancia,complementos,falhas_insercao,cancelar):
    portas = _portas_equipamentos(previa)
    candidatos = defaultdict(list)
    incidentes=defaultdict(set)
    por_uid={p['uid']:p for p in pipes}
    por_gis=defaultdict(list)
    anexos=[]
    bloqueados=set()
    for p in pipes:
        if p.get('gis_id') is not None:por_gis[str(p['gis_id'])].append(p)
        for u in (p['no_a'],p['no_b']):incidentes[u].add(p['uid'])

    def identificar(ref,autorizados=None):
        if ref in por_uid:
            return ref if autorizados is None or ref in autorizados else None
        candidatos=por_gis.get(ref,())
        if len({p['original'] for p in candidatos})!=1:
            return None
        ids=[p['uid'] for p in candidatos if autorizados is None or p['uid'] in autorizados]
        return ids[0] if len(ids)==1 else None

    for r in previa['equipamentos']:
        verificar_cancelamento(cancelar)
        t,u = r['categoria'],r['uid']
        n=None
        if u in falhas_insercao:
            motivo=falhas_insercao[u]
        elif t=='BOOSTER' and t in perfil['tipos']:
            continue
        elif t not in CAMADAS:
            motivo=INVENTARIO.get(t,'Categoria de inventário, sem representação nativa definida.')
        elif t not in perfil['tipos']:
            motivo='Tipo mantido no inventário por escolha do perfil.'
        else:
            preparado=complementos.get(u)
            ligado={preparado[0]} if preparado else portas[u]
            g = geometria(r.get('wkb'))
            n = nos.get(next(iter(ligado))) if len(ligado)==1 else None
            valores = _atributos(t,inventario.get(u,{}).get('atributos_originais') or {},perfil)
            ponto=g.asPoint() if g and g.type()==0 and not g.isMultipart() else None
            xy=(ponto.x(),ponto.y()) if ponto is not None else None
            if any(valores.get(k) is None for k in PROPRIEDADES[t]):
                motivo='Atributos nativos pendentes: '+', '.join(PROPRIEDADES[t][k][0] for k in PROPRIEDADES[t] if valores.get(k) is None)
            elif t=='REGISTRO':
                ref=identificar(valores['mb_pipe'])
                from .validacao_modelbuilder_gis import linha
                pipe=linha(por_uid[ref]) if ref else None
                if (not pipe or not xy or not 0<=pipe.distance(g)<=tolerancia
                        or valores['mb_estado']=='ATIVO'):
                    motivo='Confira o Pipe associado, a posição cadastrada e o estado aberto ou fechado.'
                else:
                    anexos.append(dict(r,**valores,xy=xy,tipo_modelbuilder=t,equipamento_uid=u,ref_pipe=ref,
                        posicao_pipe=pipe.lineLocatePoint(g)/pipe.length(),WNA_UID=u,WNA_ORIG_UID=r['feicao'],
                        WNA_ID_GIS=r.get('id'),WNA_PROCEDENCIA='GIS_ORIGINAL',WNA_SITUACAO='EQUIPAMENTO_CADASTRADO',
                        WNA_ATIVO=r.get('atividade','A_DEFINIR')))
                    continue
            elif not n or not xy or dist(n['xy'],xy)>tolerancia:
                motivo='A geometria pontual e as portas declaradas precisam identificar o mesmo nó exportado.'
            elif t=='TANK' and not (0<=valores['mb_nmin']<=valores['mb_nini']<=valores['mb_nmax']
                                     and valores['mb_nmin']<valores['mb_nmax'] and valores['mb_diam']>0):
                motivo='Confira os níveis relativos e o diâmetro do tanque cilíndrico.'
            elif t=='AIR_VALVE' and len(incidentes[n['uid']])!=2:
                motivo='Confira as duas tubulações incidentes à ventosa nesta representação.'
            elif t in DIRECIONAIS:
                adj=incidentes[n['uid']]
                lados=dict(zip(('PORTA_A','PORTA_B'),preparado[1:])) if preparado else {}
                mont=lados.get(valores['mb_mont']) or identificar(valores['mb_mont'],adj)
                jus=lados.get(valores['mb_jus']) or identificar(valores['mb_jus'],adj)
                if len(adj)!=2 or not mont or not jus or mont==jus:
                    motivo='Oriente explicitamente os dois Pipes incidentes. As referências precisam ser distintas e inequívocas.'
                elif (t=='PUMP' and valores['mb_estado']=='ATIVO' or t in ('PRV','PSV','FCV','PBV','TCV')
                      and (valores['mb_ajuste']<0 or t in ('PRV','PSV','FCV') and valores['mb_ajuste']==0)):
                    motivo='Confira o ajuste hidráulico e o estado inicial declarado.'
                else:
                    valores.update(ref_mont=mont,ref_jus=jus)
                    motivo=None
            else:
                motivo=None
            if motivo is None:
                candidatos[n['uid']].append(dict(n,**valores,equipamento_uid=u, tipo_modelbuilder=t,label=r.get('label'),
                    no_topologico=n['uid'],
                    WNA_ORIG_UID=r['feicao'], WNA_ID_GIS=r.get('id'), WNA_PROCEDENCIA=r.get('procedencia','GIS_ORIGINAL'),
                    WNA_SITUACAO='EQUIPAMENTO_CADASTRADO'))
                continue
        seguranca=n is not None and t in (*DIRECIONAIS,'HYDRANT','AIR_VALVE')
        if seguranca:bloqueados.add(n['uid'])
        pendencias.append(dict(tipo=t,uid=u,motivo=motivo,classe='EQUIPAMENTO',gravidade='CRITICA' if seguranca else 'HIDRAULICA',
            label_cadastral=r.get('label'),gis_id=r.get('id'),camada=r.get('camada'),relacoes=r.get('declaracoes',[]),
            codigo='EQUIPAMENTO_NO_NAO_PREPARADO' if seguranca else 'EQUIPAMENTO_INVENTARIO',
            solucao='Complete os atributos e vínculos no cadastro GIS e revalide.'))
    saida={}
    for u,es in candidatos.items():
        if len(es)==1:
            saida[u]=es[0]
        else:
            bloqueados.add(u)
            pendencias.extend(dict(tipo=e['tipo_modelbuilder'],uid=e['equipamento_uid'],
                motivo='Mais de um equipamento disputando o mesmo nó.',classe='EQUIPAMENTO',gravidade='CRITICA',
                codigo='EQUIPAMENTOS_NO_CONFLITANTES') for e in es)
    return saida,anexos,bloqueados


def _dependencias_excluidas(pipes,equipamentos,anexos,bloqueados,pendencias):
    incidentes=defaultdict(list)
    dependentes=defaultdict(list)
    for p in pipes:
        for u in (p['no_a'],p['no_b']):incidentes[u].append(p)
    for u,e in equipamentos.items():
        for k in ('ref_mont','ref_jus'):
            if e.get(k):dependentes[e[k]].append(u)
    fila=list(bloqueados)
    retirados=set()
    for u in fila:
        for p in incidentes[u]:
            if p['uid'] in retirados:continue
            retirados.add(p['uid'])
            pendencias.append(dict(tipo='PIPE',uid=p['uid'],codigo='NO_HIDRAULICO_PENDENTE',
                gis_id=p.get('gis_id'),camada=p.get('camada'),original=p['original'],parte=p['parte'],
                no_a=p['no_a'],no_b=p['no_b'],
                classe='EQUIPAMENTO',gravidade='CRITICA',motivo='O nó hidráulico exigido pelo Pipe não está preparado.',
                solucao='Confira os atributos, as portas e a orientação do equipamento.'))
            for v in dependentes[p['uid']]:
                if v not in bloqueados:
                    bloqueados.add(v)
                    fila.append(v)
    for e in anexos:
        if e['ref_pipe'] in retirados:
            pendencias.append(dict(tipo=e['tipo_modelbuilder'],uid=e['uid'],classe='EQUIPAMENTO',gravidade='HIDRAULICA',
                codigo='PIPE_ASSOCIADO_EXCLUIDO',motivo='O Pipe associado ao equipamento foi excluído do pacote.'))
    return retirados


def preparar(previa, pipes, nos, associacoes, configuracao, cancelar=None):
    perfil=validar_perfil(configuracao['perfil'])
    m=previa['manifesto']
    tol=configuracao.get('tolerancia_m', .001)
    if _numero(tol) is None or not 0<=tol<=1:
        raise ValueError('Informe uma tolerância de conferência entre 0 e 1 m.')
    inventario={r['uid']:r for r in previa['cadastro']}
    pipes,nos,pendencias,excluidos,substituidos=diagnosticar(previa,pipes,nos,tol,
        segmentar=configuracao.get('segmentar_aneis',False),correcoes=configuracao.get('correcoes'),cancelar=cancelar)
    aneis_segmentados=sorted(substituidos)
    from .inserir_equipamentos_modelbuilder import inserir
    pipes,complementos,falhas_insercao=inserir(previa,pipes,nos,perfil,tol,substituidos,cancelar)
    por_no={n['uid']:n for n in nos}
    equipamentos,anexos,bloqueados=_conferir_equipamentos(previa,pipes,por_no,inventario,perfil,pendencias,tol,
                                                         complementos,falhas_insercao,cancelar)
    if bloqueados:
        retirados=_dependencias_excluidas(pipes,equipamentos,anexos,bloqueados,pendencias)
        excluidos.update(bloqueados|retirados)
        excluidos.update(e['equipamento_uid'] for u,e in equipamentos.items() if u in bloqueados)
        for u,segmentos in list(substituidos.items()):
            if any(s['uid'] in retirados for s in segmentos):
                # Os membros de um anel no conjunto precisam permanecer coerentes.
                if not all(s['uid'] in retirados for s in segmentos):
                    raise ValueError('Uma correção de anel conflita com a dependência de um equipamento. Revise antes de exportar.')
                excluidos.add(u)
                del substituidos[u]
        pipes=[p for p in pipes if p['uid'] not in retirados]
        nos=[n for n in nos if n['uid'] not in bloqueados]
        por_no={n['uid']:n for n in nos}
        equipamentos={u:e for u,e in equipamentos.items() if u not in bloqueados}
        anexos=[e for e in anexos if e['ref_pipe'] not in retirados]
    if excluidos and not (configuracao.get('parcial') or configuracao.get('validar')):
        raise PendenciasCriticas(pendencias)
    if not pipes and not configuracao.get('validar'):
        raise ValueError('Nenhum Pipe válido no escopo. Consulte as pendências antes de exportar.')
    nodais={u:equipamentos.get(u,n) for u,n in por_no.items()}
    tipos_no={u:r.get('tipo_modelbuilder','JUNCTION') for u,r in nodais.items()}
    rotulos=labels.reservar(
        [dict(uid=r['uid'],tipo='PIPE',label=r.get('label'),original=r['original']) for r in pipes]+
        [dict(uid=u,tipo=tipos_no[u],label=r.get('label'),original=r.get('WNA_ORIG_UID')) for u,r in nodais.items()]+
        [dict(uid=r['uid'],tipo=r['tipo_modelbuilder'],label=r.get('label'),original=r.get('WNA_ORIG_UID')) for r in anexos],
        m['projeto'],m['execucao'],base=configuracao.get('base_labels'),gravar=not configuracao.get('validar'),
        prefixos=perfil.get('prefixos'),preservar=perfil.get('preservar_label',True),
        anteriores={r['uid']:r['label'] for r in configuracao.get('componentes_anteriores',())},cancelar=cancelar)
    tipos={t:[] for t in CAMADAS}
    esperado=[]
    geometrias_nos=defaultdict(list)
    for n in nos:
        verificar_cancelamento(cancelar)
        g=n['xy']
        if len(g)!=2 or not all(map(isfinite,g)):
            raise ValueError('Há nós sem coordenadas métricas válidas.')
        geometrias_nos[tuple(g)].append(n['uid'])
        if n['uid'] in equipamentos:
            r=equipamentos[n['uid']]
        else:
            referencias={p[1] for p in n['portas'] if p[0]=='J'}
            ref=next(iter(referencias)) if len(referencias)==1 else None
            r=dict(n,**_atributos('JUNCTION',inventario.get(ref,{}).get('atributos_originais') or {},perfil),
                   tipo_modelbuilder='JUNCTION')
            if r.get('mb_cota') is None:
                pendencias.append(dict(tipo='JUNCTION',uid=n['uid'],motivo='Elevação não informada.',classe='ATRIBUTO'))
        r.update(mb_x=g[0],mb_y=g[1],WNA_LABEL=rotulos[r['uid']])
        t=r['tipo_modelbuilder']
        for k,ref in (('mb_mont','ref_mont'),('mb_jus','ref_jus')):
            if r.get(ref):r[k]=rotulos[r[ref]]
        tipos[t].append(r)
        esperado.append(dict(tipo=t,uid=r['uid'],label=r['WNA_LABEL'],x=g[0],y=g[1],
            gis_id=r.get('WNA_ID_GIS'),orig_uid=r.get('WNA_ORIG_UID'),atividade=r['WNA_ATIVO'],
            assinatura_geometria=digest(g)))
    for r in anexos:
        x,y=r['xy']
        r.update(mb_x=x,mb_y=y,WNA_LABEL=rotulos[r['uid']],mb_pipe=rotulos[r['ref_pipe']],
                 WNA_HIPOTESE=(m.get('hipotese') or {}).get('uuid'),WNA_REVISAO=(m.get('hipotese') or {}).get('rev'))
        tipos[r['tipo_modelbuilder']].append(r)
        esperado.append(dict(tipo=r['tipo_modelbuilder'],uid=r['uid'],label=r['WNA_LABEL'],x=x,y=y,
            gis_id=r.get('WNA_ID_GIS'),orig_uid=r.get('WNA_ORIG_UID'),atividade=r['WNA_ATIVO'],
            assinatura_geometria=digest([r['xy'],r['ref_pipe'],r['posicao_pipe']])))
    for us in geometrias_nos.values():
        if len(us)>1:
            pendencias.extend(dict(tipo='NO',uid=u,motivo='Coordenada compartilhada por identidades distintas. Use referências explícitas.',
                                   classe='TOPOLOGIA') for u in us)
    preparados=[]
    for p in pipes:
        verificar_cancelamento(cancelar)
        a,b=p['no_a'],p['no_b']
        if a not in por_no or b not in por_no or a==b:
            raise ValueError(f"O Pipe {p['uid']} possui nós ausentes ou o mesmo nó nas duas pontas.")
        attrs=inventario.get(p['parte'],{}).get('atributos_originais') or {}
        adicionais=_atributos('PIPE',attrs,perfil)
        for k,valor in list(adicionais.items()):
            if valor is None or valor<=0:
                adicionais[k]=None
                pendencias.append(dict(tipo='PIPE',uid=p['uid'],motivo=PROPRIEDADES['PIPE'][k][0]+' ausente ou inválido.',
                                       classe='ATRIBUTO'))
        if adicionais.get('mb_comp_h') is not None and (p['inicio'],p['fim'])!=(0.,1.):
            adicionais['mb_comp_h']=None
            pendencias.append(dict(tipo='PIPE',uid=p['uid'],motivo='Comprimento hidráulico original requer atribuição aos segmentos.',
                                   classe='ATRIBUTO'))
        if p.get('diametro_mm') is None:
            pendencias.append(dict(tipo='PIPE',uid=p['uid'],motivo='Diâmetro ou unidade de origem não informada.',classe='ATRIBUTO'))
        preparados.append(dict(p,**adicionais,WNA_LABEL=rotulos[p['uid']],mb_inicio=rotulos[a],mb_fim=rotulos[b],
                              label_no_A=rotulos[a],label_no_B=rotulos[b],
                              mb_tipo_a=tipos_no[a],mb_tipo_b=tipos_no[b]))
        esperado.append(dict(tipo='PIPE',uid=p['uid'],label=rotulos[p['uid']],gis_id=p.get('gis_id'),orig_uid=p['original'],
            parte=p['parte'],inicio=p['inicio'],fim=p['fim'],no_a=a,no_b=b,
            comprimento_geom_m=p['comprimento_m'],comprimento_hid_m=adicionais.get('mb_comp_h'),diametro_mm=p.get('diametro_mm'),
            atividade=p['atividade'],assinatura_geometria=digest(p['wkb'].hex())))
    chaves={r['uid'] for r in esperado}
    chaves_labels={r['label'].casefold() for r in esperado}
    if len(chaves)!=len(esperado) or len(chaves_labels)!=len(esperado):
        raise ValueError('Elementos materializados com chave ou Label repetido.')
    if m.get('lacunas'):
        pendencias.append(dict(tipo='CADASTRO',uid=None,motivo='Há lacunas no inventário. Consulte validacao.json.',classe='COBERTURA'))
    for r in m.get('serializacao_pendencias',()):
        pendencias.append(dict(tipo='CADASTRO',uid=None,motivo=r['campo']+' · '+r['motivo'],classe='ATRIBUTO',gravidade='AVISO'))
    for r in previa['operacoes']:
        if r['tipo']=='CONEXAO' and r.get('resultado') not in ('APLICADA','SEPARADA'):
            pendencias.append(dict(tipo='CONEXAO',uid=r['uuid'],motivo='Relação sem aplicação na execução: '+str(r.get('resultado')),
                classe='TOPOLOGIA',relacoes=[{k:r.get(k) for k in ('uuid','rev','candidato','decisao')}],
                solucao='Abra a revisão correspondente e confira as portas.'))
    # Preserva a associação pelo mesmo UID e muda somente o tipo nativo efetivamente preparado.
    tipo_por_uid={r['uid']:r['tipo'] for r in esperado}
    assoc=[]
    por_equipamento={r['equipamento_uid']:r for r in [*equipamentos.values(),*anexos]}
    for a in associacoes:
        u=a['elemento_uid']
        if u in substituidos:
            for trecho in substituidos[u]:
                novo=trecho['uid']
                assoc.append(dict(a,elemento_uid=novo,label_previsto=rotulos[novo],inicio=trecho['inicio'],fim=trecho['fim']))
        elif a['tipo_elemento']=='EQUIPAMENTO':
            e=por_equipamento.get(u)
            if e is None:
                assoc.append(dict(a,situacao_participacao='SOMENTE_INVENTARIO',label_previsto=None))
            else:
                eq=e['uid']
                assoc.append(dict(a,elemento_uid=eq,tipo_elemento=tipo_por_uid[eq],label_previsto=rotulos[eq]))
        elif u in excluidos:
            assoc.append(dict(a,situacao_participacao='EXCLUIDO_EXPORTACAO',label_previsto=None))
        else:
            assoc.append(dict(a,tipo_elemento=tipo_por_uid[u],label_previsto=rotulos[u]))
    unicas={}
    for a in assoc:
        k=(a['conjunto_uid'],a['tipo_elemento'],a['elemento_uid'])
        if k in unicas:
            unicas[k]['membros_origem']=sorted(set(unicas[k]['membros_origem'])|set(a['membros_origem']))
        else:
            unicas[k]=a
    associacoes[:]=unicas.values()
    for r in pendencias:
        r.setdefault('gravidade','HIDRAULICA' if r['classe'] in ('ATRIBUTO','EQUIPAMENTO') else 'AVISO')
    vinculos=[dict(tipo=e['tipo_modelbuilder'],uid=u,no=u,montante=e['ref_mont'],jusante=e['ref_jus'])
              for u,e in equipamentos.items() if e.get('ref_jus')]
    vinculos.extend(dict(tipo=e['tipo_modelbuilder'],uid=e['uid'],pipe_associado=e['ref_pipe'],
                         fracao=e['posicao_pipe']) for e in anexos)
    composicoes=list(composicoes_booster(previa['equipamentos'],perfil,esperado,vinculos)) if 'BOOSTER' in perfil['tipos'] else []
    for r in composicoes:
        if r['situacao']=='COMPOSICAO_PENDENTE':
            pendencias.append(dict(tipo='BOOSTER',uid=r['uid'],classe='EQUIPAMENTO',gravidade='HIDRAULICA',
                codigo='COMPOSICAO_PENDENTE',motivo='A composição não identifica uma sucção, um recalque e as bombas do pacote.',
                solucao='Confira os componentes declarados pelos seus WNA_UIDs.'))
    quantidades=dict(Counter(r['tipo'] for r in esperado))
    cadastrados=Counter(r['categoria'] for r in previa['cadastro'])
    inventario_pendencias=defaultdict(set)
    for r in pendencias:
        if r['gravidade'] in ('CRITICA','AVISO','HIDRAULICA'):
            inventario_pendencias[r['tipo']].add(r.get('uid') or r['motivo'])
    cobertura=[dict(tipo=t,cadastrados=cadastrados[t],preparados=quantidades.get(t,0),
                    pendentes=len(inventario_pendencias[t]),
                    exportados=0 if configuracao.get('validar') else quantidades.get(t,0),
                    situacao='PREPARACAO_GIS' if t in PROPRIEDADES and t!='BOOSTER' else 'INVENTARIO')
              for t in dict.fromkeys([*PROPRIEDADES,*INVENTARIO,*cadastrados,*inventario_pendencias])]
    meta=dict(versao=VERSAO, projeto=m['projeto'],execucao=m['execucao'],hipotese=m.get('hipotese'),
              crs=m['crs'],tolerancia_m=tol,perfil=perfil,escopo=configuracao['escopo'],origens=m.get('origens',()),
              cadastro_rev=m.get('modelo_cadastral_rev'),assinatura_topologia=m['assinatura_topologia_exportavel'],
              quantidades=quantidades,pendencias=dict(Counter(p['classe'] for p in pendencias)),
              cobertura=cobertura,vinculos_equipamentos=vinculos,composicoes_booster=composicoes,
              validacao_nativa='PENDENTE_NO_WATERGEMS',
              correcoes=[{k:r.get(k) for k in ('uuid','rev','elemento_uid','estado','operacao','fracao','no_intermediario')}
                         for r in (configuracao.get('correcoes') or {}).values()],
              estado='EXPORTACAO_PARCIAL' if excluidos else 'EXPORTADO_COM_PENDENCIAS' if pendencias else 'EXPORTADO',
              incompleto=bool(excluidos or m.get('lacunas')),excluidos=sorted(excluidos),
              aneis_segmentados=aneis_segmentados,segmentos_substituidos=sorted(substituidos),
              gravidades=dict(Counter(r['gravidade'] for r in pendencias)),
              conectividade='REFERENCIAS_START_STOP',aceita_exclusao=False,
              assinatura=digest(esperado))
    return preparados,tipos,esperado,pendencias,meta


def arquivos(pasta, esperado, pendencias, meta, csv, cancelar):
    import csv as leitor

    csv(pasta,'WNA_TOPOLOGIA_ESPERADA',COLUNAS_ESPERADO,esperado,cancelar)
    with (pasta/'WNA_TOPOLOGIA_ESPERADA.csv').open(newline='',encoding='utf-8-sig') as arq:
        assinatura_csv=digest(list(leitor.DictReader(arq)))
    csv(pasta,'WNA_PENDENCIAS_MODELBUILDER',COLUNAS_PENDENCIA,pendencias,cancelar)
    csv(pasta,'WNA_COBERTURA_MODELBUILDER',('tipo','cadastrados','preparados','pendentes','exportados','situacao'),
        meta.get('cobertura',()),cancelar)
    csv(pasta,'WNA_VINCULOS_EQUIPAMENTOS',('tipo','uid','no','montante','jusante','pipe_associado','fracao'),
        meta.get('vinculos_equipamentos',()),cancelar)
    csv(pasta,'WNA_COMPOSICOES_BOOSTER',('uid','id_gis','label','composicao','situacao'),meta.get('composicoes_booster',()),cancelar)
    csv(pasta,'MODELO_CONFERENCIA_WATERGEMS',COLUNAS_EVIDENCIA,(),cancelar)
    csv(pasta,'WNA_ATIVIDADE_PRETENDIDA',('tipo','uid','label','atividade'),
        (r for r in esperado if r['tipo']=='PIPE'),cancelar)
    ativos=defaultdict(list)
    for r in esperado:
        verificar_cancelamento(cancelar)
        if r['tipo']=='PIPE' and r['atividade'] in ('ATIVO','INATIVO'):
            ativos[r['atividade']].append(r['uid'])
    for estado,ids in ativos.items():
        for i in range(0,len(ids),100):
            verificar_cancelamento(cancelar)
            texto='WNA_UID IN ('+', '.join("'"+u+"'" for u in ids[i:i+100])+')'
            (pasta/f'MINUTA_ATIVIDADE_{estado}_{i//100+1:03d}.txt').write_text(texto+'\n',encoding='utf-8')
    meta=dict(meta,assinatura_csv=assinatura_csv,ficha={
        'chave':'WNA_LABEL por Label na criação; WNA_UID também deve ser gravado como UDE textual.',
        'sincronizacao':'Em atualização confira o plano e a correspondência; desative remoção e inclusão automática de nós.',
        'pipe':{'inicio':'MB_INICIO / label_no_A','fim':'MB_FIM / label_no_B','diametro':'diametro_mm / diam_mm', 'comprimento_geometrico':'comprimento_m / comp_m',
                'comprimento_informado':'mb_comp_h / MB_COMP_H','rugosidade_hw_c':'mb_hw_c / MB_HW_C'},
        'nos':{'coordenadas':'MB_X / MB_Y em metros','elevação':'MB_COTA', 'reservoir':'MB_CARGA',
               'tank':'MB_COTA, MB_NMIN, MB_NINI, MB_NMAX, MB_DIAM'},
        'equipamentos':{'camadas':CAMADAS,'propriedades':PROPRIEDADES,'campos':CAMPOS_EQUIPAMENTO,
            'orientacao':'Após as conexões estarem criadas, confira o campo nativo Downstream Pipe usando MB_JUS. '
                         'MB_MONT identifica o lado de entrada declarado. Confira a sucção da bomba e sua definição no destino.',
            'isolamento':'Use MB_PIPE para conferir Referenced Pipe. A válvula associada não divide o Pipe.',
            'validacao':'Preparação GIS. Confira os campos e domínios nativos da versão usada antes da sincronização.'},
        'ude':{'WNA_UID':'Texto; 24 caracteres hexadecimais','WNA_LABEL':'Texto; até 32 caracteres',
               'WNA_ID_GIS':'Texto; preserve zero, vazio e zeros à esquerda'},
        'opcoes':{'criar_nos_ausentes':False,'conectividade_espacial':False,'remover_ausentes':False},
        'atividade':'Utilize uma alternativa explícita. WNA_ATIVO é atividade pretendida.',
    })
    (pasta/'MODELBUILDER.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    (pasta/'IMPORTAR_NO_MODELBUILDER.txt').write_text(
        'Importação assistida em uma cópia do modelo\n\n'
        '1. Confira a cobertura e as pendências. Para o ensaio em ModelBuilder standalone, use os Shapefiles '
        'em um único vínculo de fonte com todas as camadas de nós e Pipes. GeoPackage é o produto GIS.\n'
        '2. Na criação, mapeie WNA_LABEL como Label/chave de cada tipo e MB_INICIO/MB_FIM como Start Node/Stop Node. '
        'Use as unidades indicadas em MODELBUILDER.json. Desative conexão espacial, criação de nós ausentes e exclusão.\n'
        '3. Valide as opções na sua versão. Importe WNA_UID em UDE de texto. Preserve o GIS-ID de origem em WNA_ID_GIS.\n'
        '4. Na atualização, compare a FlexTable completa e o plano antes de criar ou atualizar. Resolva divisões '
        'e colisões com os elementos anteriores na cópia. Se um Label mudou, configure o vínculo antes de repetir.\n'
        '5. Exporte as FlexTables com os IDs, Labels, WNA_UID, Start/Stop Node e demais atributos. Preencha '
        'MODELO_CONFERENCIA_WATERGEMS.csv conforme o guia e use Conferir importação no WNA.\n'
        '6. Aplique a atividade em alternativa explícita e confira a seleção e os IDs de cada conjunto.\n',encoding='utf-8')


def ler_pacote(pasta):
    import csv
    p=Path(pasta)
    m=json.loads((p/'MODELBUILDER.json').read_text(encoding='utf-8'))
    with (p/'WNA_TOPOLOGIA_ESPERADA.csv').open(newline='',encoding='utf-8-sig') as arq:
        reader=csv.DictReader(arq)
        if tuple(reader.fieldnames or ())!=COLUNAS_ESPERADO:
            raise ValueError('Esquema da topologia esperada incompatível.')
        rs=list(reader)
    def tipar(r):
        numericas={'inicio','fim','x','y','comprimento_geom_m','comprimento_hid_m','diametro_mm'}
        return {k:(_numero(v) if k in numericas else v or None) for k,v in r.items()}
    if (m.get('versao')!=VERSAO or any(None in r or None in r.values() or
            not re.fullmatch('[a-f0-9]{24}',r.get('uid') or '') for r in rs)
            or m.get('assinatura_csv')!=digest(rs)):
        raise ValueError('Assinatura ou esquema das tabelas esperadas incompatível.')
    return m,[tipar(r) for r in rs]
