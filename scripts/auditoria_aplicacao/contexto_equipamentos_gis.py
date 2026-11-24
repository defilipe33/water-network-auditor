"""Consulta opcional e cancelável; proximidade nunca se torna conexão."""
from copy import deepcopy
from qgis.core import (QgsFeature, QgsGeometry, QgsSpatialIndex, QgsFeatureRequest,
                       QgsExpression, QgsCoordinateReferenceSystem)
from .analise_modelo_gis import FonteSnapshot
from .modelo_gis import identificar, descrever
from .associacoes_gis import vigentes, pendencias, verificar_referencia
from auditoria_fronteiras.entradas import digest, valor_python

EQUIPAMENTOS = frozenset(('PRV','TCV','FCV','PBV','AIR_VALVE','PUMP','BOOSTER',
                         'RESERVOIR','TANK','HYDRANT','REGISTRO','DISPOSITIVO','ENTRADA'))


def preparar(fontes, camadas, crs, contexto):
    from auditoria_fronteiras import Parametros
    from auditoria_fronteiras.entradas import crs_processamento
    destino=crs_processamento(Parametros(crs=crs))
    snapshots = {}; avisos = []
    for f in fontes:
        if f['categoria'] not in EQUIPAMENTOS and f['categoria'] != 'PIPE': continue
        c = identificar(f, camadas)
        if c is None or not c.crs().isValid() or descrever(c)['assinatura'] != f['assinatura']:
            avisos.append(f['nome']+': fonte indisponível ou alterada; contexto não recuperado.'); continue
        snapshots[f['uid']] = FonteSnapshot(f,c,destino,contexto)
    return snapshots, deepcopy(fontes), avisos


def ler(preparacao, dossie, cancelar=lambda:False, raio=20):
    snapshots,fontes,avisos=preparacao;avisos=list(avisos);registros=[];por_ref={}
    for uid,s in snapshots.items():
        f=s.fonte
        if f['categoria'] not in EQUIPAMENTOS:continue
        campo=f['campos_mapeados'].get('id');label=f['campos_mapeados'].get('label') or f['campos_mapeados'].get('nome')
        for feat in s.getFeatures():
            if cancelar():raise InterruptedError('Consulta de equipamentos cancelada.')
            valor=valor_python(feat[campo]) if campo else None
            g=QgsGeometry(feat.geometry()) if feat.hasGeometry() else None
            r=dict(indice=len(registros),fonte_uid=uid,categoria=f['categoria'],camada=f['nome'],id=valor,
                   nome=str(feat[label]) if label else '',geometria=g,tubos=set(),declaracoes=[])
            registros.append(r);por_ref.setdefault((uid,type(valor).__name__,str(valor)),[]).append(r)
        avisos.extend(f['nome']+': '+e['motivo'] for e in s.erros)
    tubos={}
    for t in dossie['tubulacoes']:tubos.setdefault(t['uid'].rsplit('_',1)[0],set()).add(t['uid'])
    for f in fontes:
        for a in vigentes(f):
            if cancelar():raise InterruptedError('Consulta de equipamentos cancelada.')
            erros=pendencias(a,fontes)
            if erros:avisos.extend(erros);continue
            ref=a['equipamento'];rs=por_ref.get((ref['fonte_uid'],ref['tipo'],str(ref['valor'])),[])
            if len(rs)!=1:
                avisos.append('Equipamento declarado ausente ou com ID repetido; relação não destacada.');continue
            try:
                associados=set()
                for t in a['tubulacoes']:
                    s=snapshots.get(t['fonte_uid'])
                    if s is None:raise ValueError('Fonte da tubulação declarada indisponível.')
                    verificar_referencia(t,s.fonte,s.snapshot,cancelar)
                    eq=QgsExpression.createFieldEqualityExpression(t['campo'],t['valor'])
                    expr='('+eq+')'+(' AND ('+s.fonte['filtro']+')' if s.fonte['filtro'] else '')
                    req=QgsFeatureRequest().setFilterExpression(expr).setLimit(2)
                    # Validação por assinatura da feição no CRS da execução, não somente por ID.
                    for feat in s.snapshot.getFeatures(req):
                        if type(valor_python(feat[t['campo']])).__name__!=t['tipo']:continue
                        from qgis.core import QgsCoordinateTransform
                        g=QgsGeometry(feat.geometry())
                        if s.origem_crs!=s.destino and g.transform(QgsCoordinateTransform(s.origem_crs,s.destino,s.contexto))!=0:continue
                        attrs={n:valor_python(feat[n]) for n in s.snapshot.fields().names()}
                        chave=digest([t['fonte_uid'],attrs,bytes(g.asWkb()).hex()])
                        associados.update(tubos.get(chave,set()))
                rs[0]['tubos'].update(associados)
                rs[0]['declaracoes'].append(a['uuid'])
            except ValueError as e:avisos.append(str(e))
    contexto=ContextoEquipamentos(registros);contexto.por_evento={}
    from .investigacao_gis import geometria
    from collections import defaultdict
    vinculos=defaultdict(set)
    for r in dossie['evento_rede']:vinculos[r['evento_uid']].add(r['tubo_uid'])
    for e in dossie['eventos']:
        if cancelar():raise InterruptedError('Consulta de equipamentos cancelada.')
        contexto.por_evento[e['uid']]=contexto.consultar([geometria(e['tecnico'].get('geometria_wkb_hex'))],vinculos[e['uid']],raio)
    return contexto,avisos


class ContextoEquipamentos:
    def __init__(self, registros):
        from collections import defaultdict
        self.registros=registros;self.indice=QgsSpatialIndex();self.por_tubo=defaultdict(set)
        for i,r in enumerate(registros):
            for tubo in r['tubos']:self.por_tubo[tubo].add(i)
            g=r['geometria']
            if g is not None and not g.isEmpty():
                f=QgsFeature(i);f.setGeometry(g);self.indice.addFeature(f)

    def consultar(self, geometrias, tubos, raio):
        candidatos=set()
        for g in geometrias:
            if g is None:continue
            caixa=g.boundingBox();caixa.grow(raio);candidatos.update(self.indice.intersects(caixa))
        for tubo in tubos:candidatos.update(self.por_tubo.get(tubo,()))
        saida=[]
        for i in sorted(candidatos):
            r=self.registros[i];g=r['geometria'];declarada=bool(r['tubos'].intersection(tubos))
            distancias=[g.distance(e) for e in geometrias if e is not None] if g is not None and not g.isEmpty() else []
            distancias=[d for d in distancias if d>=0];distancia=min(distancias) if distancias else None
            if declarada or (distancia is not None and distancia<=raio):
                saida.append(dict(r,relacao='Associação declarada' if declarada else 'Proximidade geométrica apenas',distancia=distancia))
        return saida
