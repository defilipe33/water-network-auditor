"""Executa uma hipótese rastreável sobre o cadastro GIS selecionado."""

from collections import defaultdict
from datetime import datetime, timezone
from uuid import uuid4
from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsGeometry, QgsPointXY

from .associacoes_gis import vigentes, pendencias
from .entradas_grafo_gis import ler
from .grafo_gis import VERSAO, construir, _indexar
from .investigacao_gis import geometria
from auditoria_fronteiras.modelos import verificar_cancelamento


def _chaves(elementos):
    chaves=defaultdict(lambda:defaultdict(list))
    for item in elementos:
        for fonte in item['fontes']:
            chaves[(fonte,item['origem_id'],type(item['id']).__name__,str(item['id']))][item['feicao']].append(item)
    return chaves


def _identificar(chaves,ref):
    encontrados=chaves[(ref['fonte_uid'],ref['campo'],ref['tipo'],str(ref['valor']))]
    return next(iter(encontrados.values())) if len(encontrados)==1 else []


def _declaracoes_existentes(fontes,tubos,equipamentos):
    tubos_ref=_chaves(tubos)
    equipamentos_ref=_chaves(equipamentos)
    declaracoes=[]
    for fonte in fontes:
        for a in vigentes(fonte):
            eq=_identificar(equipamentos_ref,a['equipamento'])
            if len(eq)!=1 or pendencias(a,fontes):
                continue
            posicoes={'INICIO':0.,'FIM':1.}
            possiveis=[_identificar(tubos_ref,t) for t in a['tubulacoes']]
            portas=[(ts[0]['uid'],posicoes[a['posicao']]) for ts in possiveis
                    if len(ts)==1 and a['posicao'] in posicoes]
            if len(portas)!=len(a['tubulacoes']):
                portas=[]
            eq[0].setdefault('declaracoes',[]).append(dict(uuid=a['uuid'],portas=portas,posicao=a['posicao']))
            declaracoes.append(eq[0]['uid'])
    return set(declaracoes)


def _distancias_origens(resultado, tubos, origens, destino, transformacoes, cancelar):
    ids, geometrias = [], []
    validas=set(resultado['origens_validas'])
    for r in origens:
        if r['uuid'] not in validas or not r.get('crs'):
            continue
        g=geometria(r.get('wkb'))
        if g is None and r.get('xy'):
            g=QgsGeometry.fromPointXY(QgsPointXY(*r['xy']))
        origem=QgsCoordinateReferenceSystem(r['crs'])
        if g is None or not origem.isValid():
            continue
        if origem!=destino:
            try:
                if g.transform(QgsCoordinateTransform(origem,destino,transformacoes))!=0:continue
            except RuntimeError:
                continue
        ids.append(r['uuid'])
        geometrias.append(g)
    if not ids:
        return
    indice=_indexar(geometrias,guardar_geometrias=True)
    por_uid={t['uid']:t['geom'] for t in tubos}
    for c in resultado['componentes']:
        if c['situacao']!='SEM_ORIGEM_ALCANCAVEL':continue
        melhor=None
        for uid in c['tubos']:
            verificar_cancelamento(cancelar)
            linha=por_uid[uid]
            for i in indice.nearestNeighbor(linha,1):
                medida=linha.distance(geometrias[i])
                if medida>=0 and (melhor is None or (medida,ids[i])<melhor):
                    melhor=medida,ids[i]
        if melhor is not None:
            c['origem_mais_proxima']=dict(distancia_m=melhor[0],uuid=melhor[1])


def executar(prep, contexto, parametros, participantes, cancelar=None, etapa=lambda *_:None, inventario=None):
    tubos,junctions,equipamentos,areas,avisos = inventario if inventario is not None else ler(prep,cancelar,etapa)
    fontes=[f for f,_,_ in prep[0]]
    declarados=_declaracoes_existentes(fontes,tubos,equipamentos)
    origens=[r for r in participantes if r['tipo']=='ORIGEM']
    conexoes=[r for r in participantes if r['tipo']=='CONEXAO']
    por_equipamento={e['uid']:e for e in equipamentos}
    # Um cadastro movido/alterado precisa ser explicitamente reconciliado.
    candidatas=[]
    for r in origens:
        if r.get('equipamento'):
            e=por_equipamento.get(r['equipamento'])
            candidatas.append(dict(r,wkb=e['wkb'],crs=prep[1].toWkt()) if e else dict(r,portas=[]))
        else:
            candidatas.append(r)
    resultado=construir(tubos,junctions,origens=candidatas,conexoes=conexoes,cancelar=cancelar,
                         etapa=etapa,**parametros)
    _distancias_origens(resultado,tubos,candidatas,prep[1],prep[2],cancelar)
    equipamentos_ligados={r['equipamento'] for r in candidatas if r.get('equipamento')
                          and r['uuid'] in resultado['origens_validas']}
    for e in equipamentos:
        if e['uid'] in equipamentos_ligados:
            continue
        if e['uid'] in declarados and any(d['portas'] for d in e['declaracoes']):
            continue
        resultado['diagnosticos'].append(dict(uid=e['uid'],tipo='EQUIPAMENTO_PENDENTE',
            equipamento=e['uid'],tubos=[],situacao='A_REVISAR',wkb=e['wkb'],
            motivo='Equipamento cadastrado com associação topológica ausente ou não determinada.'))
    resultado.update(contexto,uuid=uuid4().hex,data_utc=datetime.now(timezone.utc).isoformat(),
                     algoritmo=VERSAO,crs=prep[1].toWkt(),parametros=parametros,
                     fontes=[{k:f[k] for k in ('uid','nome','categoria','assinatura','filtro','campos_mapeados','classificacao')}
                             for f in fontes],unidades=prep[3],participantes=[*candidatas,*conexoes],
                     equipamentos=equipamentos,areas=areas,avisos=avisos)
    return resultado
