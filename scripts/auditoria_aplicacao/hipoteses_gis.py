"""Revisões de hipóteses GIS fixadas por identidade e conteúdo das entradas."""

from collections import defaultdict

from auditoria_fronteiras.entradas import digest

from .grafo_gis import VERSAO


FORMATO = 2


def fontes(preparacao):
    return [
        {k:f[k] for k in ('uid','nome','categoria','assinatura','filtro','campos_mapeados','classificacao')}
        for f,_,_ in preparacao[0]
    ]


def configuracao(preparacao, modelo_rev, parametros):
    return dict(modelo_rev=modelo_rev, algoritmo=VERSAO, crs=preparacao[1].toWkt(),
                fontes=fontes(preparacao), unidades=dict(preparacao[3]), parametros=dict(parametros))


def assinatura_inventario(inventario):
    """Cada UID do inventário já inclui atributos e geometria originais."""
    return digest([sorted((r['uid'],sorted(r['fontes'])) for r in grupo) for grupo in inventario[:4]])


def dados_hipotese(nome, projeto, config, participantes, assinatura):
    return dict(formato=FORMATO, nome=nome, projeto_uid=projeto, configuracao=config,
                selecionados=[r['uuid'] for r in participantes],
                vinculos={r['uuid']:r['rev'] for r in participantes}, assinatura_inventario=assinatura)


def resolver_vinculos(hipotese, por_revisao):
    if hipotese.get('formato')!=FORMATO:
        raise ValueError('Hipótese da 1.16.0 sem revisões fixadas. Recupere uma execução antiga ou crie nova revisão explicitamente.')
    saida={}
    for uid,rev in hipotese['vinculos'].items():
        r=por_revisao.get(rev)
        if not r or r['uuid']!=uid or r['tipo'] not in ('ORIGEM','CONEXAO','PIPE') or not r.get('habilitado',True):
            raise ValueError('A revisão participante está indisponível ou diverge da hipótese.')
        saida[uid]=r
    return saida


def _grupos(d):
    por_tubo = {u:g['uid'] for g in d['componentes'] for u in g['tubos']}
    por_uid = {g['uid']:g for g in d['componentes']}
    return por_tubo,por_uid


def comparar_execucoes(a,b):
    """Compara registros publicados, sem atribuir causalidade quando há várias mudanças."""
    if a['projeto_uid']!=b['projeto_uid']:
        raise ValueError('Selecione duas execuções do mesmo projeto.')
    ta,ga=_grupos(a)
    tb,gb=_grupos(b)
    comuns=ta.keys() & tb.keys()
    destinos,origens=defaultdict(set),defaultdict(set)
    for uid in comuns:
        destinos[ta[uid]].add(tb[uid])
        origens[tb[uid]].add(ta[uid])
    difs=[]

    def incluir(tipo,nome,tubos=(),antes=None,depois=None):
        difs.append(dict(tipo=tipo,nome=nome,tubos=sorted(set(tubos)),antes=antes,depois=depois))

    for uid,grupo in sorted(destinos.items()):
        if len(grupo)>1:
            incluir('DIVIDIDO', 'Componente dividido',ga[uid]['tubos'],uid,', '.join(sorted(grupo)))
    for uid,grupo in sorted(origens.items()):
        if len(grupo)>1:
            incluir('UNIDO', 'Componentes unidos',gb[uid]['tubos'],', '.join(sorted(grupo)),uid)
    for tipo,nome,us in (
        ('MUDOU','Tubulações que mudaram de componente',[u for u in comuns if ta[u]!=tb[u]]),
        ('NOVO','Tubulações novas ou alteradas',tb.keys()-ta.keys()),
        ('AUSENTE','Tubulações retiradas ou alteradas',ta.keys()-tb.keys()),
        ('GANHOU','Tubulações que passaram a alcançar origem',[u for u in comuns if gb[tb[u]]['origens'] and not ga[ta[u]]['origens']]),
        ('PERDEU','Tubulações que deixaram de alcançar origem',[u for u in comuns if ga[ta[u]]['origens'] and not gb[tb[u]]['origens']]),
    ):
        if us:incluir(tipo,nome,us)

    ka={r['uuid']:r for r in a.get('participantes',[])}
    kb={r['uuid']:r for r in b.get('participantes',[])}
    for u in sorted(ka.keys()|kb.keys()):
        antigo,novo=ka.get(u),kb.get(u)
        r=novo or antigo
        if antigo and novo and antigo['rev']==novo['rev']:continue
        situacao='adicionada' if not antigo else 'retirada' if not novo else 'revisada'
        natureza='Origem' if r['tipo']=='ORIGEM' else 'Conexão'
        tubos=[t for item in (antigo,novo) if item for t,_ in item['portas']]
        ra=_estado_relacao(antigo)
        rb=_estado_relacao(novo)
        incluir(natureza.upper(),f"{natureza} {situacao} · {r.get('nome') or u[:8]}",tubos,ra,rb)
        difs[-1]['relacao']=u
        if r['tipo']=='CONEXAO' and len(set(tubos))>=2 and all(t in comuns for t in tubos):
            grupos_a=len({ta[t] for t in tubos})
            grupos_b=len({tb[t] for t in tubos})
            if grupos_a!=grupos_b:
                incluir('EFEITO','Conexão alterada com mudança observada nos componentes das portas',
                        tubos,grupos_a,grupos_b)

    def sem_origem(d):
        return (sum(g['comprimento_m'] for g in d['componentes'] if g['situacao']=='SEM_ORIGEM_ALCANCAVEL')
                if d.get('origens_validas') else None)

    compr_antes={t['uid']:t['comprimento_m'] for t in a['tubos']}
    compr_depois={t['uid']:t['comprimento_m'] for t in b['tubos']}
    return dict(componentes=[len(ga),len(gb)], sem_origem_m=[sem_origem(a),sem_origem(b)],
                passou_alcancar_m=sum(compr_depois[u] for r in difs if r['tipo']=='GANHOU' for u in r['tubos']),
                deixou_alcancar_m=sum(compr_antes[u] for r in difs if r['tipo']=='PERDEU' for u in r['tubos']),
                unioes=sum(r['tipo']=='UNIDO' for r in difs), divisoes=sum(r['tipo']=='DIVIDIDO' for r in difs),
                diferencas=difs)


def _estado_relacao(r):
    if r is None:return 'Fora da hipótese'
    return (r.get('decisao') or r['situacao']).replace('_',' ').capitalize()
