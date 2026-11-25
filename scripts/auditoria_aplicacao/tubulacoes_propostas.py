"""Validação e inclusão explícita de propostas na fotografia topológica."""

from math import isfinite

from qgis.core import QgsCoordinateReferenceSystem, QgsGeometry, QgsPointXY

from auditoria_fronteiras.modelos import verificar_cancelamento
from .investigacao_gis import geometria


UNIDADES_DIAMETRO = {'mm':1, 'cm':10, 'm':1000, 'pol':25.4}


def validar(dados):
    crs = QgsCoordinateReferenceSystem(dados.get('crs') or '')
    from auditoria_fronteiras.entradas import crs_processamento
    from auditoria_fronteiras import Parametros
    crs_processamento(Parametros(crs=crs.toWkt()))
    portas = dados.get('portas') or []
    if (len(portas)!=2 or any(not isinstance(u,str) or not u or
                             not isinstance(f,(float,int)) or not 0<=f<=1 for u,f in portas)
            or tuple(portas[0])==tuple(portas[1])):
        raise ValueError('Escolha dois pontos de ligação distintos.')
    vertices = dados.get('vertices') or []
    if len(vertices)<2 or any(len(p)!=2 or not all(isinstance(x,(int,float)) and isfinite(x) for x in p)
                              for p in vertices):
        raise ValueError('Informe um traçado com coordenadas válidas.')
    pontos = [QgsPointXY(*p) for p in vertices]
    if any(a.distance(b)<=1e-8 for a,b in zip(pontos,pontos[1:])):
        raise ValueError('O traçado contém um trecho de comprimento nulo.')
    linha = QgsGeometry.fromPolylineXY(pontos)
    diametro = dados.get('diametro')
    unidade = dados.get('unidade_diametro')
    if diametro is not None and (unidade not in UNIDADES_DIAMETRO or
                                not isinstance(diametro,(int,float)) or not isfinite(diametro) or diametro<=0):
        raise ValueError('Informe um diâmetro positivo e sua unidade, ou deixe em branco.')
    return linha


def preparar_propostas(registros, tubos, crs, contexto, cancelar=None, *, validar_projecao=True):
    """Retorna tubos derivados e somente as duas ligações explicitamente escolhidas."""
    from qgis.core import QgsCoordinateTransform
    por_uid = {t['uid']:t for t in tubos}
    derivados, ligacoes, rejeitadas = [], [], []
    for r in registros:
        verificar_cancelamento(cancelar)
        uid = 'proposta:'+r['uuid']
        try:
            linha = validar(r)
            origem = QgsCoordinateReferenceSystem(r['crs'])
            if origem!=crs:
                if linha.transform(QgsCoordinateTransform(origem,crs,contexto))!=0:
                    raise ValueError('Não foi possível transformar o traçado.')
            pontos = linha.asPolyline()
            for i,(t,f) in enumerate(r['portas']):
                if t not in por_uid:
                    raise ValueError('Uma tubulação vinculada está fora do escopo.')
                g = por_uid[t]['geom']
                porta = g.interpolate(g.length()*f).asPoint()
                if validar_projecao and pontos[i*(len(pontos)-1)].distance(porta)>0.001:
                    raise ValueError('A posição da ligação mudou desde a revisão da proposta.')
            caixa = linha.boundingBox()
            comprimento = linha.length()
            diam = r.get('diametro')
            derivados.append(dict(uid=uid,feicao=uid,id=r.get('nome') or r['uuid'],geom=linha,
                camada='Tubulações propostas',fontes=[],proposta_uid=r['uuid'],proposta_rev=r['rev'],
                situacao=r['situacao'],material=r.get('material'),classificacao=r.get('classificacao') or 'COMPLEMENTAR',
                extensao=[caixa.xMinimum(),caixa.yMinimum(),caixa.xMaximum(),caixa.yMaximum()],
                comprimento_m=comprimento,diametro_mm=diam*UNIDADES_DIAMETRO[r['unidade_diametro']] if diam is not None else None))
            for i,porta in enumerate(r['portas']):
                ligacoes.append(dict(uuid=uid+f':{i}',rev=r['rev'],portas=[(uid,float(i)),tuple(porta)],
                                    decisao='CONFIRMADA',proposta_uid=r['uuid']))
        except (TypeError,ValueError,RuntimeError) as erro:
            rejeitadas.append((r,str(erro)))
    return derivados, ligacoes, rejeitadas


def posicao(tubo, fracao):
    linha = tubo.get('geom') or geometria(tubo.get('wkb'))
    if linha is None or linha.isEmpty():
        raise ValueError('Geometria da tubulação indisponível.')
    p = linha.interpolate(linha.length()*fracao).asPoint()
    return [p.x(),p.y()]
