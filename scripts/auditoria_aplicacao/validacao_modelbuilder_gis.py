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


def no_ja_conectado(pipes,origem,destino):
    vizinhos=defaultdict(set)
    for p in pipes:
        a,b=p.get('no_a'),p.get('no_b')
        if a and b:
            vizinhos[a].add(b)
            vizinhos[b].add(a)
    fila=[origem]
    vistos={origem}
    for u in fila:
        if u==destino:return True
        novos=vizinhos[u]-vistos
        vistos.update(novos)
        fila.extend(novos)
    return False


def planejar_anel(p,no,fracao=.5,no_intermediario=None):
    """Planeja a divisão sem alterar a fotografia nem unir nós por proximidade."""
    g=linha(p)
    if (not g or g.type()!=QgsWkbTypes.LineGeometry or g.isMultipart() or not g.isSimple()
            or not no or p.get('no_a')!=p.get('no_b') or p['no_a']!=no['uid']
            or not isinstance(fracao,(int,float)) or not 0<fracao<1):
        raise ValueError('Confira a geometria do anel, o nó original e a posição interna do corte.')
    ps=g.asPolyline()
    ponta=(ps[0].x(),ps[0].y()) if ps else ()
    fim=(ps[-1].x(),ps[-1].y()) if ps else ()
    if len(ps)<4 or not g.isGeosValid() or dist(ponta,fim)>EPS or dist(ponta,no['xy'])>EPS:
        raise ValueError('O traçado não é um anel simples ancorado ao nó original.')
    comprimento=g.length()
    ponto=g.interpolate(comprimento*fracao).asPoint()
    meio=(ponto.x(),ponto.y())
    if min(fracao,1-fracao)*comprimento<=EPS or dist(meio,ponta)<=EPS:
        raise ValueError('O corte está muito perto da extremidade do anel.')
    corte=p['inicio']+(p['fim']-p['inicio'])*fracao
    u=digest(['no-exportacao-anel',p['parte'],corte])
    n=dict(no,uid=u,WNA_UID=u,xy=meio,portas=[[p['parte'],corte]],natureza='DIVISAO_EXPORTACAO_ANEL',
           original=None,label=None,gis_id=None,WNA_ORIG_UID=None,WNA_ID_GIS=None,WNA_PROCEDENCIA='DERIVADO',
           WNA_SITUACAO='DIVISAO_EXPORTACAO_ANEL')
    if no_intermediario:
        if (no_intermediario['uid']==no['uid'] or dist(meio,no_intermediario['xy'])>EPS or
                not any(u==p['parte'] and abs(f-corte)*comprimento<=EPS
                        for u,f in no_intermediario['portas'] if u!='J')):
            raise ValueError('O nó intermediário não possui porta verificada nessa posição do anel.')
        n=no_intermediario
        u=n['uid']
    trechos=[]
    for a,b,f0,f1,i,j in ((0,fracao,p['inicio'],corte,p['no_a'],u),(fracao,1,corte,p['fim'],u,p['no_b'])):
        geom=type(g)(g.constGet().curveSubstring(a*comprimento,b*comprimento))
        if not geom or geom.length()<=EPS:
            raise ValueError('O ponto escolhido produz um segmento degenerado.')
        uid=digest(['segmento_gis',p['parte'],f0,f1])
        trechos.append(dict(p,uid=uid,WNA_UID=uid,inicio=f0,fim=f1,no_a=i,no_b=j,
                            comprimento_m=geom.length(),wkb=bytes(geom.asWkb()),natureza='DIVISAO_EXPORTACAO_ANEL',
                            WNA_PROCEDENCIA='DERIVADO',segmento_anterior=p['uid']))
    if abs(sum(r['comprimento_m'] for r in trechos)-comprimento)>EPS:
        raise ValueError('A divisão não preserva o comprimento do anel.')
    return n,trechos


def diagnosticar(previa,pipes,nos,tolerancia,*,segmentar=False,correcoes=None,cancelar=None):
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
                operacoes[u].append({k:r.get(k) for k in ('uuid','rev','nome','decisao','resultado','candidato','portas')})
    preparados=[]
    novos={}
    substituidos={}
    excluidos=set(invalidos)
    ids={r['uid'] for r in pipes}
    correcoes=correcoes or {}
    for p in pipes:
        verificar_cancelamento(cancelar)
        u=p['uid']
        a,b=p.get('no_a'),p.get('no_b')
        g=linha(p)
        vertices=g.asPolyline() if g and g.type()==QgsWkbTypes.LineGeometry and not g.isMultipart() else []
        ps=[(v.x(),v.y()) for v in (vertices[0],vertices[-1])] if vertices else []
        ref=dict(tipo='PIPE',uid=u,gis_id=p.get('gis_id'),label_cadastral=p.get('label'),camada=p.get('camada'),
                 original=p.get('original'),parte=p.get('parte'),inicio=p.get('inicio'),fim=p.get('fim'),
                 no_a=a,no_b=b,coordenadas=ps,classe='TOPOLOGIA',relacoes=operacoes.get(p.get('parte'),[]),
                 comprimento_m=p.get('comprimento_m'),tolerancia_grafo_m=previa['manifesto'].get('tolerancia_grafo_m'))
        causas=[]
        if not a or a not in por_no or a in invalidos:causas.append(('NO_INICIAL_INDISPONIVEL','Nó inicial ausente ou inválido.'))
        if not b or b not in por_no or b in invalidos:causas.append(('NO_FINAL_INDISPONIVEL','Nó final ausente ou inválido.'))
        erro=p.get('erro_materializacao')
        if erro or not g or len(vertices)<2 or not g.isGeosValid() or not isfinite(g.length()) or g.length()<=EPS:
            causas.append(('GEOMETRIA_INVALIDA',erro or 'Geometria vazia, inválida ou degenerada.'))
        elif a and a==b:
            fechado=dist(*ps)<=EPS
            correcao=correcoes.get(u)
            d=None
            if fechado and not causas and (segmentar and not correcao or correcao and correcao['estado']=='APLICADA'):
                try:
                    fracao=.5
                    intermediario=None
                    if correcao:
                        from .correcao_modelbuilder import assinatura_pipe
                        if assinatura_pipe(p)!=correcao['assinatura']:
                            raise ValueError('O segmento mudou desde a revisão da correção.')
                        fracao=correcao['fracao']
                        u_no=correcao.get('no_intermediario')
                        if u_no and (u_no not in por_no or u_no in invalidos):
                            raise ValueError('O nó escolhido está ausente no escopo atual.')
                        if u_no and not no_ja_conectado(pipes,a,u_no):
                            raise ValueError('O nó escolhido pertence a outro componente. Revise a conexão na hipótese.')
                        intermediario=por_no.get(u_no)
                    d=planejar_anel(p,por_no[a],fracao,intermediario)
                    no_novo,trechos=d
                    if ((not intermediario and no_novo['uid'] in por_no) or no_novo['uid'] in novos
                            or any(t['uid'] in ids for t in trechos)):
                        raise ValueError('A divisão proposta reutilizaria uma identidade incompatível.')
                except ValueError as erro:
                    d=None
                    if correcao:causas.append(('CORRECAO_NAO_APLICADA',str(erro)))
            if d:
                n,trechos=d
                if n['uid'] not in por_no:novos[n['uid']]=n
                ids.update(t['uid'] for t in trechos)
                preparados.extend(trechos)
                substituidos[u]=trechos
                problemas.append(dict(ref,codigo='ANEL_SEGMENTADO',gravidade='INFORMACAO',
                    motivo='Anel simples segmentado na posição validada.',solucao='Confira os dois segmentos na saída.'))
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
        tol_grafo=ref['tolerancia_grafo_m']
        if tol_grafo and 0<p.get('comprimento_m',0)<=tol_grafo and len(ref['relacoes'])>=2:
            problemas.append(dict(ref,codigo='SEGMENTO_CURTO_LIGACOES',gravidade='INFORMACAO',
                motivo=f"Segmento de {p['comprimento_m']:.6g} m abaixo ou igual à tolerância do grafo. As pontas usam nós distintos.",
                solucao='Confirme a representação se as ligações precisarem de revisão. O segmento foi preservado.'))
        if any(dist(x,por_no[i]['xy'])>tolerancia for x,i in zip(ps,(a,b))):
            problemas.append(dict(ref,codigo='PONTA_DESLOCADA',gravidade='AVISO',
                motivo='Ponta geométrica deslocada do nó esperado.',solucao='Confira as referências explícitas Start/Stop.'))
    return preparados,[n for n in nos if n['uid'] not in invalidos]+list(novos.values()),problemas,excluidos,substituidos
