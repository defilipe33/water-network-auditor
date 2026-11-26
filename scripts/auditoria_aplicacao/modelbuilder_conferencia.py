"""Reconciliação por identificadores exportados do WaterGEMS."""

from collections import Counter, defaultdict
from contextlib import closing
import csv
from hashlib import sha256
from math import dist
from pathlib import Path
import sqlite3

from auditoria_fronteiras.modelos import verificar_cancelamento
from .modelbuilder_gis import COLUNAS_EVIDENCIA, TIPOS_NOS, _numero


def ler_evidencia(caminho):
    p=Path(caminho)
    with p.open(newline='',encoding='utf-8-sig') as arq:
        leitor=csv.DictReader(arq)
        if not leitor.fieldnames or set(leitor.fieldnames)!=set(COLUNAS_EVIDENCIA) or len(leitor.fieldnames)!=len(COLUNAS_EVIDENCIA):
            raise ValueError('Use as colunas do arquivo MODELO_CONFERENCIA_WATERGEMS.csv.')
        linhas=list(leitor)
    if any(None in r or None in r.values() for r in linhas):
        raise ValueError('Há linhas com quantidade de colunas inválida no CSV conferido.')
    if not linhas:
        raise ValueError('O CSV conferido precisa conter elementos do modelo.')
    return linhas


def conferir(meta, esperado, observado, modelo, versao, *, cenario='', cancelar=None):
    if not all(str(s).strip() for s in (modelo,versao)):
        raise ValueError('Identifique o modelo e a versão efetivamente conferidos.')
    tolerancia=meta['tolerancia_m']
    uids=Counter(r['uid'] for r in observado if r['uid'])
    ids=Counter(r['id_modelo'] for r in observado if r['id_modelo'])
    labels=Counter((r['tipo'],r['label'].casefold()) for r in observado if r['label'])
    exatos={r['uid']:r for r in observado if r['uid'] and uids[r['uid']]==1}
    por_uid={r['uid']:r for r in esperado}
    verificadas={}
    problemas=[]
    for a in esperado:
        verificar_cancelamento(cancelar)
        u,t=a['uid'],a['tipo']
        b=exatos.get(u)
        motivos=[]
        if b is None:
            motivos.append('WNA_UID repetido' if uids[u]>1 else 'Elemento ausente no modelo de destino')
        elif b['tipo']!=t or not b['id_modelo'] or ids[b['id_modelo']]!=1 or not b['label'] or labels[t,b['label'].casefold()]!=1:
            motivos.append('Tipo, ID efetivo ou Label sem correspondência unívoca')
        elif t in TIPOS_NOS:
            xy=_numero(b['x']),_numero(b['y'])
            if None in xy or dist(xy,(a['x'],a['y']))>tolerancia:
                motivos.append('Coordenadas ausentes ou divergentes no CRS do pacote')
        if motivos:
            problemas.extend(dict(uid=u,tipo=t,motivo=s) for s in motivos)
            continue
        verificadas[u]=b
    conexoes={}
    for a in esperado:
        verificar_cancelamento(cancelar)
        u=a['uid']
        b=verificadas.get(u)
        if b is None:
            continue
        if a['tipo']=='PIPE':
            esperados=[verificadas.get(a[k],{}).get('id_modelo') for k in ('no_a','no_b')]
            if list((b['no_a'],b['no_b']))!=esperados:
                problemas.append(dict(uid=u,tipo='PIPE',motivo='Start Node ou Stop Node divergente ou sem correspondência verificada'))
                continue
            for campo in ('comprimento_geom_m','comprimento_hid_m','diametro_mm'):
                if a.get(campo) is not None:
                    valor=_numero(b[campo])
                    limite=.01 if campo=='diametro_mm' else tolerancia
                    if valor is None or abs(valor-a[campo])>limite:
                        problemas.append(dict(uid=u,tipo='PIPE',motivo=f'{campo}: ausente ou divergente'))
        if a.get('atividade') in ('ATIVO','INATIVO') and (not cenario or b['atividade']!=a['atividade']):
            problemas.append(dict(uid=u,tipo=a['tipo'],motivo='Atividade não confirmada na alternativa indicada'))
        if a.get('gis_id') is not None and str(a['gis_id'])!=b['gis_id']:
            problemas.append(dict(uid=u,tipo=a['tipo'],motivo='GIS-ID original divergente ou ausente'))
        if b['label']!=a['label']:
            problemas.append(dict(uid=u,tipo=a['tipo'],motivo='Label efetivo diferente do Label de importação'))
        hip=meta.get('hipotese') or {}
        conexoes[u]=dict(projeto=meta['projeto'],uid=u,tipo=a['tipo'],orig_uid=a.get('orig_uid'),
                         label_importacao=a['label'],gis_id=a.get('gis_id'),id_modelo=b['id_modelo'],
                         label_modelo=b['label'],modelo=modelo,versao_modelo=versao,cenario=cenario,
                         execucao=meta['execucao'],hipotese=hip.get('uuid'),revisao=hip.get('rev'),
                         situacao='IDENTIDADE_E_TOPOLOGIA_CONFERIDAS')
    extras=[{k:r[k] for k in ('tipo','uid','id_modelo','label')} for r in observado if r['uid'] not in por_uid]
    return dict(estado='IMPORTADO_COM_PENDENCIAS' if problemas else 'IMPORTADO_E_CONFERIDO',
                modelo=modelo,versao_modelo=versao,cenario=cenario,problemas=problemas,
                extras_preservados=extras,correspondencias=list(conexoes.values()),
                esperado=dict(Counter(r['tipo'] for r in esperado)),encontrado=dict(Counter(r['tipo'] for r in observado)),
                conferidos=dict(Counter(r['tipo'] for r in conexoes.values())))


def plano_atualizacao(anteriores, atuais, cancelar=None, *, observado=()):
    """Descreve delta do cadastro, exigindo conferência antes de substituir."""
    antes={r['uid']:r for r in anteriores}
    depois={r['uid']:r for r in atuais}
    por_parte=defaultdict(list)
    for r in atuais:
        if r['tipo']=='PIPE':
            por_parte[r['parte']].append(r)
    deltas=[]
    novos_divisao=set()
    by_uid=defaultdict(list)
    ids=Counter(r['id_modelo'] for r in observado if r['id_modelo'])
    for b in observado:
        by_uid[b['uid']].append(b)
    for u,r in antes.items():
        verificar_cancelamento(cancelar)
        atual=depois.get(u)
        if atual:
            a='MANTER' if r==atual else 'ATUALIZAR_COM_CONFERENCIA'
        else:
            a='PRESERVAR_AUSENTE_NA_FONTE'
            if r['tipo']=='PIPE':
                candidatas=sorted((x for x in por_parte[r['parte']] if x['orig_uid']==r['orig_uid']
                    and r['inicio']<=x['inicio']<x['fim']<=r['fim']),key=lambda x:x['inicio'])
                if (len(candidatas)>1 and candidatas[0]['inicio']==r['inicio'] and candidatas[-1]['fim']==r['fim']
                        and all(x['fim']==y['inicio'] and x['no_b']==y['no_a'] for x,y in zip(candidatas,candidatas[1:]))):
                    a='DIVISAO_SUBSTITUICAO_MANUAL'
                    membros=[x['uid'] for x in candidatas]
                    novos_divisao.update(membros)
                    deltas.append(dict(acao=a,uid=u,tipo=r['tipo'],novos_segmentos=membros))
                    continue
        deltas.append(dict(acao=a,uid=u,tipo=r['tipo']))
    for u,r in depois.items():
        verificar_cancelamento(cancelar)
        if u not in antes and u not in novos_divisao:
            deltas.append(dict(acao='NOVO_CONFERIR_DUPLICIDADE',uid=u,tipo=r['tipo']))
    for linha in deltas:
        verificaveis=by_uid[linha['uid']]
        if (len(verificaveis)==1 and (r:=verificaveis[0])['tipo']==linha['tipo']
                and r['id_modelo'] and ids[r['id_modelo']]==1):
            linha.update(id_modelo=r['id_modelo'],label_modelo=r['label'],
                         situacao_destino='VINCULO_POR_UID_A_CONFERIR')
        elif verificaveis:
            linha['situacao_destino']='AMBIGUIDADE_BLOQUEIA_SINCRONIZACAO'
        else:
            linha['situacao_destino']='AUSENTE_NO_CSV' if observado else 'SEM_EVIDENCIA'
    for r in observado:
        verificar_cancelamento(cancelar)
        if r['uid'] not in antes and r['uid'] not in depois:
            deltas.append(dict(acao='PRESERVAR_SOMENTE_NO_DESTINO',uid=r['uid'],tipo=r['tipo'],
                              id_modelo=r['id_modelo'],label_modelo=r['label'],situacao_destino='PRESERVAR'))
    return deltas


def salvar_tabela(caminho, resultado, modelo_csv, data):
    """Grava um banco próprio somente com os vínculos conferidos."""
    from .persistencia_grafo_gis import _criar_gpkg, _registrar
    campos=('projeto','uid','tipo','orig_uid','label_importacao','gis_id','id_modelo','label_modelo','modelo',
            'versao_modelo','cenario','execucao','hipotese','revisao','situacao','data_importacao')
    arquivo=Path(caminho)
    if arquivo.exists():
        raise FileExistsError(arquivo)
    _criar_gpkg(arquivo)
    with closing(sqlite3.connect(arquivo)) as con, con:
        colunas=','.join(c+' TEXT' for c in campos)
        con.execute(f'CREATE TABLE WNA_ELEMENTO_WATERGEMS (fid INTEGER PRIMARY KEY,{colunas},UNIQUE(modelo,tipo,uid))')
        _registrar(con,'WNA_ELEMENTO_WATERGEMS')
        registros=[dict(r,data_importacao=data) for r in resultado['correspondencias']]
        marcadores=','.join('?' for _ in campos)
        con.executemany(f"INSERT INTO WNA_ELEMENTO_WATERGEMS ({','.join(campos)}) VALUES ({marcadores})",
                        ([r[k] for k in campos] for r in registros))
    return sha256(Path(modelo_csv).read_bytes()).hexdigest()
