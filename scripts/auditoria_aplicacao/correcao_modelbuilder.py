"""Planos de correção vinculados a fotografias e operações de materialização."""

from math import dist, isfinite

from auditoria_fronteiras.entradas import digest
from .validacao_modelbuilder_gis import EPS, linha, planejar_anel


TIPO='MODELBUILDER_CORRECAO'
ESTADOS={'APLICADA','PENDENTE','REVERTIDA'}


def assinatura_pipe(p):
    wkb=p.get('wkb')
    return digest([p['uid'],p['parte'],p['inicio'],p['fim'],p.get('no_a'),p.get('no_b'),
                   wkb.hex() if isinstance(wkb,bytes) else wkb])


def identidade(execucao,pendencia):
    return digest([TIPO,execucao,pendencia['tipo'],pendencia.get('uid'),pendencia.get('codigo')])


def validar(dados,projeto):
    if (dados.get('projeto_uid')!=projeto or not dados.get('topologia_uid') or not dados.get('elemento_uid')
            or not dados.get('codigo') or dados.get('estado') not in ESTADOS):
        raise ValueError('A decisão precisa indicar a execução, o elemento e o estado.')
    if dados['estado']=='APLICADA':
        if dados.get('operacao')=='ANEL':
            f=dados.get('fracao')
            if not isinstance(f,(int,float)) or not isfinite(f) or not 0<f<1 or not dados.get('assinatura'):
                raise ValueError('A correção do anel perdeu a referência ao segmento ou à posição do corte.')
        elif dados.get('operacao')!='SEPARACAO' or not dados.get('nova_hipotese'):
            raise ValueError('Uma separação precisa de uma hipótese derivada.')


def do_pacote(registros,execucao):
    return {r['elemento_uid']:r for r in registros.values() if r['topologia_uid']==execucao
            and r.get('codigo')=='ANEL_MESMO_NO' and r['estado']!='REVERTIDA'}


def anel(pipe,nos,fracao=.5,uid_no=None):
    original=nos.get(pipe.get('no_a'))
    meio=nos.get(uid_no) if uid_no else None
    if uid_no and meio is None:
        raise ValueError('O nó intermediário não está disponível na execução.')
    n,segmentos=planejar_anel(pipe,original,fracao,meio)
    return dict(operacao='ANEL',fracao=fracao,no_intermediario=uid_no,assinatura=assinatura_pipe(pipe),
                no_novo=n,segmentos=segmentos,nos_antes=[original],nos_depois=[original,n],
                impacto='A divisão conserva o componente e o comprimento geométrico do Pipe.')


def separacao(pipe,foto,no):
    """Aceita apenas uma separação de duas portas sem terceiros ligados ao nó."""
    p0,p1=(pipe['parte'],0.),(pipe['parte'],1.)
    portas={p0,p1}
    if (pipe['inicio'],pipe['fim'])!=(0.,1.) or not no or {tuple(p) for p in no['portas']}!=portas:
        raise ValueError('Há outras portas ou divisões associadas. Revise as relações na conectividade.')
    g=linha(pipe)
    ps=g.asPolyline() if g else ()
    if len(ps)<2:
        raise ValueError('A geometria da tubulação precisa ser conferida.')
    coords=[(p.x(),p.y()) for p in (ps[0],ps[-1])]
    if dist(*coords)<=EPS:
        raise ValueError('As pontas coincidem. Examine a divisão do anel.')
    relacionados=[r for r in foto.get('participantes',()) if portas.intersection(map(tuple,r.get('portas',())))]
    exclusiva=None
    if len(relacionados)==1:
        r=relacionados[0]
        if (r['tipo']=='CONEXAO' and r.get('decisao')=='CONFIRMADA'
                and foto.get('resolucoes_conexoes',{}).get(r['uuid'])=='APLICADA'
                and {tuple(p) for p in r['portas']}==portas and r.get('rev')):
            exclusiva={'uuid':r['uuid'],'rev':r['rev']}
    if relacionados and not exclusiva or any(portas.intersection(map(tuple,r.get('portas',())))
                            for e in foto.get('equipamentos',()) for r in e.get('declaracoes',())):
        raise ValueError('Existem relações declaradas, equipamentos ou origens nessas portas. Revise os vínculos na conectividade.')
    arestas=[e for e in foto['arestas'] if no['uid'] in (e['a'],e['b'])]
    if (len(arestas)!=1 or arestas[0]['tubo']!=pipe['parte'] or arestas[0]['a']!=arestas[0]['b']
            or not (foto.get('hipotese') or {}).get('rev')):
        raise ValueError('Abra uma execução de hipótese salva cujo nó pertença somente a esse Pipe.')
    relacao=dict(nome='Separar extremidades do Pipe',situacao='INFORMADA',decisao='SEPARADA',
                 categoria_candidata='EXTREMIDADES_PROXIMAS',portas=[list(p0),list(p1)],
                 acompanhamento='VERIFICADO',habilitado=True)
    if exclusiva:
        relacao['substitui_na_derivacao']=exclusiva
    return dict(operacao='SEPARACAO',assinatura=assinatura_pipe(pipe),relacao=relacao,
                nos_antes=[no],nos_depois=[dict(xy=p,portas=[porta]) for p,porta in zip(coords,relacao['portas'])],
                segmentos=[pipe],impacto='O Pipe permanece no mesmo componente. O nó comum dará lugar a dois nós de extremidade.'
                +(' A relação exclusiva será substituída apenas na hipótese derivada.' if exclusiva else ''))
