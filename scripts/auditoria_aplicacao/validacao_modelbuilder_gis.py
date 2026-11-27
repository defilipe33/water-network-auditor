"""Diagnóstico e tratamento restrito de pontas do pacote ModelBuilder."""

from collections import defaultdict
from math import dist, isfinite

from qgis.core import QgsWkbTypes

from auditoria_fronteiras.entradas import digest
from auditoria_fronteiras.modelos import verificar_cancelamento
from .investigacao_gis import geometria


EPS=1e-6


class PendenciasCriticas(ValueError):
    def __init__(self,pendencias):
        self.pendencias=pendencias
        n=sum(r.get('gravidade')=='CRITICA' for r in pendencias)
        super().__init__(f'{n} pendência(s) crítica(s). Confira o relatório ou autorize a exportação parcial.')


def linha(p):
    wkb=p.get('wkb')
    return geometria(wkb.hex() if isinstance(wkb,bytes) else wkb)


def _dividir_anel(p,g,pontos,no):
    """Mantém a mesma união das pontas, criando uma porta interna apenas na saída."""
    if g.isMultipart() or not g.isSimple() or not no or dist(pontos[0],no['xy'])>EPS:
        return None
    comprimento=g.length()
    ponto=g.interpolate(comprimento/2).asPoint()
    meio=(ponto.x(),ponto.y())
    if dist(meio,pontos[0])<=EPS:
        return None
    corte=(p['inicio']+p['fim'])/2
    u=digest(['no-exportacao-anel',p['parte'],corte])
    n=dict(no,uid=u,WNA_UID=u,xy=meio,portas=[[p['parte'],corte]],natureza='DIVISAO_EXPORTACAO_ANEL',
           original=None,label=None,gis_id=None,WNA_ORIG_UID=None,WNA_ID_GIS=None,WNA_PROCEDENCIA='DERIVADO',
           WNA_SITUACAO='DIVISAO_EXPORTACAO_ANEL')
    trechos=[]
    for a,b,f0,f1,i,j in ((0,.5,p['inicio'],corte,p['no_a'],u),(.5,1,corte,p['fim'],u,p['no_b'])):
        geom=type(g)(g.constGet().curveSubstring(a*comprimento,b*comprimento))
        if not geom or geom.length()<=EPS:return None
        uid=digest(['segmento_gis',p['parte'],f0,f1])
        trechos.append(dict(p,uid=uid,WNA_UID=uid,inicio=f0,fim=f1,no_a=i,no_b=j,
                            comprimento_m=geom.length(),wkb=bytes(geom.asWkb()),natureza='DIVISAO_EXPORTACAO_ANEL',
                            WNA_PROCEDENCIA='DERIVADO',segmento_anterior=p['uid']))
    if abs(sum(r['comprimento_m'] for r in trechos)-comprimento)>EPS:return None
    return n,trechos


def diagnosticar(previa,pipes,nos,tolerancia,*,segmentar=False,cancelar=None):
    problemas=[]
    por_no={}
    invalidos=set()
    for n in nos:
        verificar_cancelamento(cancelar)
        u=n['uid']
        xy=n.get('xy') or ()
        codigo=('NO_DUPLICADO' if u in por_no else 'COORDENADA_NO_INVALIDA' if
                len(xy)!=2 or not all(isinstance(x,(int,float)) and isfinite(x) for x in xy) else None)
        if codigo:
            invalidos.add(u)
            problemas.append(dict(tipo='JUNCTION',uid=u,codigo=codigo,classe='TOPOLOGIA',gravidade='CRITICA',
                motivo='Nó duplicado na preparação.' if codigo=='NO_DUPLICADO' else 'Nó sem coordenadas válidas.',
                solucao='Confira a execução e a origem do nó.'))
        por_no[u]=n
    operacoes=defaultdict(list)
    for r in previa['operacoes']:
        if r['tipo']=='CONEXAO':
            for u in {p[0] for p in r.get('portas',())}:
                operacoes[u].append({k:r.get(k) for k in ('uuid','rev','nome','decisao','resultado','candidato')})
    preparados=[]
    novos={}
    substituidos={}
    excluidos=set(invalidos)
    for p in pipes:
        verificar_cancelamento(cancelar)
        u=p['uid']
        a,b=p.get('no_a'),p.get('no_b')
        g=linha(p)
        vertices=g.asPolyline() if g and g.type()==QgsWkbTypes.LineGeometry and not g.isMultipart() else []
        ps=[(v.x(),v.y()) for v in (vertices[0],vertices[-1])] if vertices else []
        ref=dict(tipo='PIPE',uid=u,gis_id=p.get('gis_id'),label_cadastral=p.get('label'),camada=p.get('camada'),
                 original=p.get('original'),parte=p.get('parte'),inicio=p.get('inicio'),fim=p.get('fim'),
                 no_a=a,no_b=b,coordenadas=ps,classe='TOPOLOGIA',relacoes=operacoes.get(p.get('parte'),[]))
        causas=[]
        if not a or a not in por_no or a in invalidos:causas.append(('NO_INICIAL_INDISPONIVEL','Nó inicial ausente ou inválido.'))
        if not b or b not in por_no or b in invalidos:causas.append(('NO_FINAL_INDISPONIVEL','Nó final ausente ou inválido.'))
        erro=p.get('erro_materializacao')
        if erro or not g or len(vertices)<2 or not g.isGeosValid() or not isfinite(g.length()) or g.length()<=EPS:
            causas.append(('GEOMETRIA_INVALIDA',erro or 'Geometria vazia, inválida ou degenerada.'))
        elif a and a==b:
            fechado=dist(*ps)<=EPS
            d=(_dividir_anel(p,g,ps,por_no[a]) if fechado and segmentar and not causas else None)
            if d and d[0]['uid'] not in por_no and d[0]['uid'] not in novos:
                n,trechos=d
                novos[n['uid']]=n
                preparados.extend(trechos)
                substituidos[u]=trechos
                problemas.append(dict(ref,codigo='ANEL_SEGMENTADO',gravidade='INFORMACAO',
                    motivo='Anel simples segmentado no ponto médio da linha.',solucao='Confira os dois segmentos na saída.'))
                continue
            causas.append(('ANEL_MESMO_NO' if fechado else 'MESMO_NO_PONTAS_DISTINTAS',
                           'Anel geométrico com o mesmo nó nas duas pontas.' if fechado else
                           'Pontas geometricamente distintas convergem ao mesmo nó topológico.'))
        if causas:
            excluidos.add(u)
            for codigo,motivo in causas:
                problemas.append(dict(ref,codigo=codigo,motivo=motivo,gravidade='CRITICA',solucao=(
                    'Valide a opção de segmentação do anel simples ou revise o traçado e as portas.'
                    if codigo=='ANEL_MESMO_NO' else 'Localize o elemento e confira as portas e decisões na conectividade.')))
            continue
        preparados.append(p)
        if any(dist(x,por_no[i]['xy'])>tolerancia for x,i in zip(ps,(a,b))):
            problemas.append(dict(ref,codigo='PONTA_DESLOCADA',gravidade='AVISO',
                motivo='Ponta geométrica deslocada do nó esperado.',solucao='Confira as referências explícitas Start/Stop.'))
    return preparados,[n for n in nos if n['uid'] not in invalidos]+list(novos.values()),problemas,excluidos,substituidos
