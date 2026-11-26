"""Contrato do pacote ModelBuilder, derivado do cadastro GIS materializado."""

from collections import Counter, defaultdict
from math import dist, isfinite
from pathlib import Path
import json
import re

from auditoria_fronteiras.entradas import digest
from auditoria_fronteiras.modelos import verificar_cancelamento
from .investigacao_gis import geometria


VERSAO = 1
TIPOS_NOS = ('JUNCTION', 'RESERVOIR', 'TANK')
CAMPOS_PIPE = dict(mb_inicio='MB_INICIO', mb_fim='MB_FIM', mb_comp_h='MB_COMP_H', mb_hw_c='MB_HW_C')
CAMPOS_NO = dict(mb_x='MB_X', mb_y='MB_Y', mb_cota='MB_COTA', mb_carga='MB_CARGA',
                 mb_nmin='MB_NMIN', mb_nini='MB_NINI', mb_nmax='MB_NMAX', mb_diam='MB_DIAM')
CAMPOS_REAIS = set(CAMPOS_NO) | {'mb_comp_h', 'mb_hw_c'}
PROPRIEDADES = {
    'PIPE': {'mb_comp_h': ('Comprimento hidráulico (m)', 'm'), 'mb_hw_c': ('Coeficiente Hazen-Williams C', 'C')},
    'JUNCTION': {'mb_cota': ('Elevação (m)', 'm')},
    'RESERVOIR': {'mb_carga': ('Carga hidráulica do reservatório (m)', 'm')},
    'TANK': {'mb_cota': ('Elevação da base (m)', 'm'), 'mb_nmin': ('Nível mínimo (m acima da base)', 'm'),
             'mb_nini': ('Nível inicial (m acima da base)', 'm'), 'mb_nmax': ('Nível máximo (m acima da base)', 'm'),
             'mb_diam': ('Diâmetro cilíndrico (m)', 'm')},
}
ESCALAS = {'m': 1., 'cm': .01, 'mm': .001, 'km': 1000., 'ft': .3048, 'C': 1.}
DESTINOS = ('2020', '2026', 'OUTRA')
COLUNAS_ESPERADO = ('tipo','uid','label','gis_id','orig_uid','parte','inicio','fim','no_a','no_b',
                    'x','y','comprimento_geom_m','comprimento_hid_m','diametro_mm','atividade','assinatura_geometria')
COLUNAS_PENDENCIA = ('tipo','uid','motivo','classe')
COLUNAS_EVIDENCIA = ('tipo','uid','id_modelo','label','gis_id','no_a','no_b','x','y',
                     'comprimento_geom_m','comprimento_hid_m','diametro_mm','atividade')


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
                    valor.get('unidade') not in (('C',) if PROPRIEDADES[tipo][k][1]=='C' else ('m','cm','mm','km','ft'))):
                raise ValueError('Informe o campo de origem e a unidade compatível.')
    if p['modo']=='ATUALIZAR' and not str(p.get('modelo_destino','')).strip():
        raise ValueError('Identifique o modelo de destino para preparar uma atualização.')
    return p


def _numero(valor, fator=1.):
    if valor is None or isinstance(valor,bool):
        return None
    try:
        n=float(valor)*fator
    except (TypeError,ValueError,OverflowError):
        return None
    return n if isfinite(n) else None


def _atributos(tipo, atributos, perfil):
    return {k:_numero(atributos.get(regra['campo']), ESCALAS[regra['unidade']])
            for k,regra in perfil['campos'].get(tipo,{}).items()}


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


def _conferir_equipamentos(previa, nos, inventario, perfil, pendencias, tolerancia, cancelar):
    portas = _portas_equipamentos(previa)
    candidatos = defaultdict(list)
    for r in previa['equipamentos']:
        verificar_cancelamento(cancelar)
        t,u = r['categoria'],r['uid']
        if t not in ('RESERVOIR','TANK'):
            motivo='Requer mapeamento de tipo, portas, orientação e propriedades operacionais.'
        elif t not in perfil['tipos']:
            motivo='Tipo mantido no inventário por escolha do perfil.'
        else:
            ligado = portas[u]
            g = geometria(r.get('wkb'))
            n = nos.get(next(iter(ligado))) if len(ligado)==1 else None
            valores = _atributos(t,inventario.get(u,{}).get('atributos_originais') or {},perfil)
            if not n or not g or g.isMultipart() or g.type()!=0 or dist(n['xy'],(g.asPoint().x(),g.asPoint().y()))>tolerancia:
                motivo='A geometria pontual e o vínculo declarado precisam identificar o mesmo nó exportado.'
            elif any(valores.get(k) is None for k in PROPRIEDADES[t]):
                motivo='Atributos nativos pendentes: '+', '.join(PROPRIEDADES[t][k][0] for k in PROPRIEDADES[t] if valores.get(k) is None)
            elif t=='TANK' and not (0<=valores['mb_nmin']<=valores['mb_nini']<=valores['mb_nmax']
                                     and valores['mb_nmin']<valores['mb_nmax'] and valores['mb_diam']>0):
                motivo='Confira os níveis relativos e o diâmetro do tanque cilíndrico.'
            else:
                candidatos[n['uid']].append(dict(n,**valores,equipamento_uid=u, tipo_modelbuilder=t,
                    WNA_ORIG_UID=r['feicao'], WNA_ID_GIS=r.get('id'), WNA_PROCEDENCIA=r.get('procedencia','GIS_ORIGINAL'),
                    WNA_SITUACAO='EQUIPAMENTO_CADASTRADO'))
                continue
        pendencias.append(dict(tipo=t,uid=u,motivo=motivo,classe='EQUIPAMENTO'))
    saida={}
    for u,es in candidatos.items():
        if len(es)==1:
            saida[u]=es[0]
        else:
            pendencias.extend(dict(tipo=e['tipo_modelbuilder'],uid=e['equipamento_uid'],
                motivo='Mais de um equipamento disputando o mesmo nó.',classe='EQUIPAMENTO') for e in es)
    return saida


def preparar(previa, pipes, nos, associacoes, configuracao, cancelar=None):
    perfil=validar_perfil(configuracao['perfil'])
    m=previa['manifesto']
    tol=configuracao.get('tolerancia_m', .001)
    if _numero(tol) is None or not 0<=tol<=1:
        raise ValueError('Informe uma tolerância de conferência entre 0 e 1 m.')
    inventario={r['uid']:r for r in previa['cadastro']}
    por_no={n['uid']:n for n in nos}
    if not pipes or len(por_no)!=len(nos):
        raise ValueError('O pacote precisa de Pipes e identidades de nós distintas.')
    pendencias=[]
    equipamentos=_conferir_equipamentos(previa,por_no,inventario,perfil,pendencias,tol,cancelar)
    tipos={t:[] for t in TIPOS_NOS}
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
        r.update(mb_x=g[0],mb_y=g[1])
        t=r['tipo_modelbuilder']
        tipos[t].append(r)
        esperado.append(dict(tipo=t,uid=r['uid'],label=r['WNA_LABEL'],x=g[0],y=g[1],
            gis_id=r.get('WNA_ID_GIS'),orig_uid=r.get('WNA_ORIG_UID'),atividade=r['WNA_ATIVO'],
            assinatura_geometria=digest(g)))
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
        g=geometria(p['wkb'].hex())
        pontos=g.asPolyline() if g else []
        if len(pontos)<2 or not g.isGeosValid() or not isfinite(g.length()) or g.length()<=0:
            raise ValueError(f"O Pipe {p['uid']} tem geometria inválida.")
        for pt,u in ((pontos[0],a),(pontos[-1],b)):
            if dist((pt.x(),pt.y()),por_no[u]['xy'])>tol:
                pendencias.append(dict(tipo='PIPE',uid=p['uid'],motivo='Ponta geométrica deslocada da Junction esperada.',
                                       classe='TOPOLOGIA'))
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
        preparados.append(dict(p,**adicionais,mb_inicio=por_no[a]['WNA_LABEL'],mb_fim=por_no[b]['WNA_LABEL']))
        esperado.append(dict(tipo='PIPE',uid=p['uid'],label=p['WNA_LABEL'],gis_id=p.get('gis_id'),orig_uid=p['original'],
            parte=p['parte'],inicio=p['inicio'],fim=p['fim'],no_a=a,no_b=b,
            comprimento_geom_m=p['comprimento_m'],comprimento_hid_m=adicionais.get('mb_comp_h'),diametro_mm=p.get('diametro_mm'),
            atividade=p['atividade'],assinatura_geometria=digest(p['wkb'].hex())))
    chaves={r['uid'] for r in esperado}
    labels={r['label'].casefold() for r in esperado}
    if len(chaves)!=len(esperado) or len(labels)!=len(esperado):
        raise ValueError('Elementos materializados com chave ou Label repetido.')
    if m.get('lacunas'):
        pendencias.append(dict(tipo='CADASTRO',uid=None,motivo='Há lacunas no inventário. Consulte validacao.json.',classe='COBERTURA'))
    # Preserva a associação pelo mesmo UID e muda somente o tipo nativo efetivamente preparado.
    tipo_por_uid={r['uid']:r['tipo'] for r in esperado}
    for a in associacoes:
        a['tipo_elemento']=tipo_por_uid[a['elemento_uid']]
    meta=dict(versao=VERSAO, projeto=m['projeto'],execucao=m['execucao'],hipotese=m.get('hipotese'),
              crs=m['crs'],tolerancia_m=tol,perfil=perfil,escopo=configuracao['escopo'],origens=m.get('origens',()),
              cadastro_rev=m.get('modelo_cadastral_rev'),assinatura_topologia=m['assinatura_topologia_exportavel'],
              quantidades=dict(Counter(r['tipo'] for r in esperado)),pendencias=dict(Counter(p['classe'] for p in pendencias)),
              estado='EXPORTADO_COM_PENDENCIAS' if pendencias else 'EXPORTADO',
              conectividade='REFERENCIAS_START_STOP',aceita_exclusao=False,
              assinatura=digest(esperado))
    return preparados,tipos,esperado,pendencias,meta


def arquivos(pasta, esperado, pendencias, meta, csv, cancelar):
    import csv as leitor

    csv(pasta,'WNA_TOPOLOGIA_ESPERADA',COLUNAS_ESPERADO,esperado,cancelar)
    with (pasta/'WNA_TOPOLOGIA_ESPERADA.csv').open(newline='',encoding='utf-8-sig') as arq:
        assinatura_csv=digest(list(leitor.DictReader(arq)))
    csv(pasta,'WNA_PENDENCIAS_MODELBUILDER',COLUNAS_PENDENCIA,pendencias,cancelar)
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
        'pipe':{'inicio':'MB_INICIO','fim':'MB_FIM','diametro':'diametro_mm / diam_mm', 'comprimento_geometrico':'comprimento_m / comp_m',
                'comprimento_informado':'mb_comp_h / MB_COMP_H','rugosidade_hw_c':'mb_hw_c / MB_HW_C'},
        'nos':{'coordenadas':'MB_X / MB_Y em metros','elevação':'MB_COTA', 'reservoir':'MB_CARGA',
               'tank':'MB_COTA, MB_NMIN, MB_NINI, MB_NMAX, MB_DIAM'},
        'ude':{'WNA_UID':'Texto; 24 caracteres hexadecimais','WNA_LABEL':'Texto; 28 caracteres',
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
