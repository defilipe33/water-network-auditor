"""Grafo explícito; os diagnósticos espaciais nunca adicionam arestas.

Estrutural e válvulas abertas usam incidência única por dispositivo. Retenções e
bombas no modo potencial usam portas somente quando incidentes. Jusante não
resolvido isola incidências direcionais, sem portas vazias artificiais. Componentes
são fracos; alcance é dirigido e não representa vazão.
"""
from collections import Counter
import networkx as nx

MODOS = ('ESTRUTURAL', 'TODAS_VALVULAS_ABERTAS', 'ESTADOS_DO_CENARIO')
VALVULAS = {'TCV','FCV','PRV','PBV','PSV','GPV'}
BOMBAS = {'StandardPump','VariableSpeedPumpBattery'}


def analisar(modelo, modo='ESTRUTURAL', perfil_estados=None):
    if modo not in MODOS:
        raise ValueError('Hipótese desconhecida')
    # Enumerações variam; um perfil deve documentar campo/tipo/código e fonte.
    # Nesta entrega não se aceita converter códigos sem validação independente.
    if modo == 'ESTADOS_DO_CENARIO':
        raise ValueError('ESTADOS_DO_CENARIO indisponível: códigos de estado e controles ainda não validados no WaterGEMS')
    elementos = modelo['elementos']
    from .resolucao import resolver_extremidades,detalhar_componentes,auditar_jusantes
    extremidades=resolver_extremidades(modelo)
    grafo = nx.MultiDiGraph()
    diagnosticos = []

    def aviso(codigo, i, relacionado=None, texto=''):
        diagnosticos.append(dict(codigo=codigo,id=i,relacionado=relacionado,descricao=texto))

    vivos = {}
    for i,e in elementos.items():
        if e['excluido'] is not False:
            if e['excluido'] is None:
                aviso('EXCLUSAO_INDETERMINADA',i)
            continue
        if e['familia'] == 'CONSUMIDOR':
            continue
        if modo != 'ESTRUTURAL' and e['ativo'] is not True:
            aviso('INATIVO' if e['ativo'] is False else 'ATIVACAO_INDETERMINADA',i)
            continue
        vivos[i]=e
        if e['familia'] == 'NO':
            grafo.add_node((i,'E'), elemento=i)
    conexoes=[]
    incidentes={}
    # Incidência explícita no cenário, antes de criar portas. Jusante ausente
    # não invalida Start/Stop nem cria uma porta desconectada artificial.
    referencias={}
    for i,e in vivos.items():
        if e['familia']=='LINK':
            for campo in ('inicio','fim'):
                referencias.setdefault(extremidades[i][campo],set()).add(i)

    def porta(n,link):
        ne=vivos[n]
        if ne['familia']!='DISPOSITIVO' or modo=='ESTRUTURAL' or ne['tipo'] in VALVULAS:
            return (n,'E')
        jus=ne['topologia'].get('HMITopologyDownstreamLinkID')
        if jus not in referencias.get(n,set()):
            # Sem orientação de bomba/retenção: cada incidência fica separada.
            # Nunca conectar duas tubulações passando por uma direção ignorada.
            return (n,'L:'+str(link))
        return (n,'S' if jus==link else 'E')
    for i,e in vivos.items():
        if e['familia']!='LINK':
            continue
        t=extremidades[i];a=t['inicio'];b=t['fim']
        if t['conflito']:aviso('JUSANTE_CONFLITO',i,texto='Referências explícitas contraditórias/múltiplas; nenhum endpoint preenchido foi substituído')
        valido=True
        for n in (a,b):
            if n not in vivos or vivos[n]['familia']=='LINK':
                aviso('VINCULO_AUSENTE',i,n,'Nó ausente, excluído, inativo ou referência inválida');valido=False
        if not valido:
            continue
        pa,pb=porta(a,i),porta(b,i)
        grafo.add_node(pa,elemento=a);grafo.add_node(pb,elemento=b)
        grafo.add_edge(pa,pb,key=('tubo',i),elemento=i,natureza='TUBULACAO')
        grafo.add_edge(pb,pa,key=('tubo',i),elemento=i,natureza='TUBULACAO')
        conexoes.append(dict(id=i,**t))
        for n in {a,b}:
            incidentes.setdefault(n,set()).add(i)
    for i,e in vivos.items():
        if e['familia']=='LINK':
            continue
        grau=len(incidentes.get(i,set()))
        if grau==0:grafo.add_node((i,'E'),elemento=i)
        if grau==0: aviso('NO_ORFAO',i,texto='Sem vínculos validados no grafo; consultar também VINCULO_AUSENTE')
        elif grau==1: aviso('EXTREMIDADE',i)
        if e['familia']!='DISPOSITIVO':
            continue
        jus=e['topologia'].get('HMITopologyDownstreamLinkID')
        if jus not in incidentes.get(i,set()):
            codigo='JUSANTE_NAO_INFORMADO' if jus is None else 'JUSANTE_INVALIDO'
            if jus in elementos and i in (extremidades.get(jus,{}).get('inicio'),extremidades.get(jus,{}).get('fim')):
                if elementos[jus]['excluido'] is True:codigo='JUSANTE_ELEMENTO_EXCLUIDO'
                elif modo!='ESTRUTURAL' and elementos[jus]['ativo'] is False:codigo='JUSANTE_ELEMENTO_INATIVO'
                else:codigo='JUSANTE_INDISPONIVEL_NA_HIPOTESE'
            aviso(codigo,i,jus)
            continue
        if modo=='ESTRUTURAL' or e['tipo'] in VALVULAS:
            continue  # Nó estrutural / válvula hipoteticamente aberta: incidência E.
        if modo!='ESTRUTURAL':
            if e['tipo'] in BOMBAS:
                aviso('BOMBA_ESTADO_INDETERMINADO',i, texto='Passagem não habilitada na hipótese; estado bruto preservado');continue
            if e['tipo'] not in VALVULAS | {'CheckValve'}:
                aviso('DISPOSITIVO_NAO_INTERPRETADO',i);continue
        # Não criar uma entrada fictícia se não há tubulação daquele lado.
        if (i,'E') not in grafo or (i,'S') not in grafo:continue
        grafo.add_edge((i,'E'),(i,'S'),key=('disp',i),elemento=i,natureza='DISPOSITIVO')
        # Apenas retenção/bomba possuem restrição direcional aqui. VRP aberta é
        # uma hipótese de passagem, sem inferir manutenção de pressão/setpoint.
        if modo=='ESTRUTURAL' or e['tipo'] not in BOMBAS|{'CheckValve'}:
            grafo.add_edge((i,'S'),(i,'E'),key=('disp',i),elemento=i,natureza='DISPOSITIVO')
    grupos=sorted(nx.weakly_connected_components(grafo),key=lambda s:sorted(s)[0])
    componentes=[]
    for k,g in enumerate(grupos,1):
        nos={n[0] for n in g}
        componentes.append(dict(id=k,nos=sorted(nos),tubulacoes=[],portas=len(g),membros_portas=sorted(g)))
    # Uma passagem bloqueada pode distribuir portas do mesmo dispositivo por
    # componentes distintos. A associação é por porta, não por ID deduplicado.
    mapa={n:k for k,g in enumerate(grupos,1) for n in g}
    for c in componentes: c['tubulacoes']=[]
    for c in conexoes:
        componentes[mapa[porta(c['inicio'],c['id'])]-1]['tubulacoes'].append(c['id'])
    resumo=dict(elementos=len(elementos),excluidos=sum(e['excluido'] is True for e in elementos.values()),
        inventario=dict(Counter(e['tipo'] for e in elementos.values() if e['excluido'] is False)),
        componentes=len(componentes),conexoes=len(conexoes),
        diagnosticos=dict(Counter(d['codigo'] for d in diagnosticos)),
        modo=modo,cenario=modelo['cenario'])
    resumo['validacao']='PARCIAL — leitura SQL validada; interpretação desktop pendente'
    resumo['restricoes']='Bombas sem estado comprovado bloqueadas; controles e PipeStatus não interpretados' if modo!='ESTRUTURAL' else 'Estrutural inclui elementos inativos; não representa disponibilidade'
    return detalhar_componentes(modelo,dict(resumo=resumo,componentes=componentes,conexoes=conexoes,
                auditoria_jusantes=auditar_jusantes(modelo),
                diagnosticos=diagnosticos,grafo=grafo,
                aviso='Conectividade cadastrada/hipotética; não representa vazão nem operação real.'))


def alcancaveis(resultado, elemento):
    g=resultado['grafo']
    inicio=(elemento,'E')
    return sorted({n[0] for n in nx.descendants(g,inicio)}|{elemento}) if inicio in g else []


def corresponder(modelo, registros_gis, campo_modelo, campo_gis):
    """Prova por atributo explícito, nunca pelo Label ou proximidade.

    Exige que o chamador delimite a fonte GIS ao mesmo projeto. Não cria vínculos
    operacionais; resultados múltiplos permanecem candidatos.
    """
    indice={}
    for i,e in modelo['elementos'].items():
        if e['excluido'] is not False: continue
        valores=set()
        for r in e['atributos'].values():
            v=r.get(campo_modelo)
            if v is not None and str(v).strip(): valores.add(str(v))
        for v in valores: indice.setdefault(v,[]).append(i)
    saida=[]
    for r in registros_gis:
        v=r.get(campo_gis);c=indice.get(str(v),[]) if v is not None else []
        saida.append(dict(gis=r['uid'],valor_bruto=v,candidatos=c,
            situacao='INEQUIVOCA_POR_ATRIBUTO' if len(c)==1 else 'MULTIPLA' if c else 'SEM_CORRESPONDENCIA'))
    return saida
