"""Investigação posterior ao grafo aprovado: inventário, fontes e relações locais.

Não cria arestas e não interpreta a ausência de fonte como falta de abastecimento.
"""
from collections import defaultdict,Counter
from itertools import combinations
from hashlib import sha256
import networkx as nx

VERSAO_REGRAS='investigacao-integrada-1'
DIRETA='CONEXAO_DIRETA_CONFIRMADA_NO_MODELO'
MESMO='MESMO_COMPONENTE_SEM_CONEXAO_DIRETA'
DIFERENTES='COMPONENTES_DIFERENTES'
AUSENTE='POSSIVEL_CONEXAO_AUSENTE'
INDEVIDA='CONEXAO_POTENCIALMENTE_INDEVIDA'
DISPOSITIVO='CONECTIVIDADE_DEPENDENTE_DE_DISPOSITIVO'
INSUFICIENTE='CORRESPONDENCIA_INSUFICIENTE'
PRIORIDADE=[INSUFICIENTE,INDEVIDA,AUSENTE,DIFERENTES,DISPOSITIVO,MESMO,DIRETA]


def checar_cancelamento(cancelar):
    if cancelar and cancelar():raise InterruptedError('Integração cancelada sem publicar resultado parcial')


def grafo_elementos(resultado):
    """Subdivide as arestas em vértices de tubo; conserva portas e direção."""
    g=nx.DiGraph()
    for n in sorted(resultado['grafo']):g.add_node(('N',n[0],n[1]))
    for a,b,d in resultado['grafo'].edges(data=True):
        na,nb=('N',a[0],a[1]),('N',b[0],b[1])
        if d['natureza']=='TUBULACAO':
            t=('T',d['elemento']);g.add_edge(na,t);g.add_edge(t,nb)
        else:g.add_edge(na,nb)
    return g


def inventariar_componentes(modelo,resultado,cancelar=None):
    elementos=modelo['elementos'];diags=defaultdict(list);incidencias=defaultdict(list)
    conexoes={c['id']:c for c in resultado['conexoes']}
    for d in resultado['diagnosticos']:diags[d['id']].append(d['codigo'])
    for c in resultado['conexoes']:
        for n in {c['inicio'],c['fim']}:incidencias[n].append(c['id'])
    inventario=[];membros=[];fontes=[]
    for c in resultado['componentes']:
        checar_cancelamento(cancelar)
        refs=[];ext=[];origens=Counter();bombas=[];reservatorios=[];tanques=[]
        for i in c['nos']+c['tubulacoes']:
            e=elementos[i];ds=diags[i]
            membros.append(dict(comp_uid=c['uid'],id=i,label=e['label'],tipo=e['tipo'],familia=e['familia'],
                ativo=e['ativo'],diagnosticos=ds,incidentes=incidencias[i]))
            if 'EXTREMIDADE' in ds:ext.append(i)
            refs.extend(dict(id=i,codigo=d) for d in ds if d in ('JUSANTE_NAO_INFORMADO','JUSANTE_INVALIDO','VINCULO_AUSENTE','JUSANTE_CONFLITO'))
            natureza=None
            if e['tipo']=='IdahoReservoir':reservatorios.append(i);natureza='RESERVATORIO_CARGA_CADASTRADA'
            elif e['tipo'] in ('IdahoTank','ConventionalTank'):tanques.append(i);natureza='TANQUE_ARMAZENAMENTO_CADASTRADO'
            elif e['tipo'] in ('StandardPump','VariableSpeedPumpBattery'):bombas.append(i);natureza='BOMBA_EQUIPAMENTO_DE_ENERGIA'
            if natureza:
                fontes.append(dict(comp_uid=c['uid'],id=i,label=e['label'],tipo=e['tipo'],natureza=natureza,
                    fonte_agua=e['tipo'] not in ('StandardPump','VariableSpeedPumpBattery'),ativo=e['ativo']))
        for i in c['tubulacoes']:
            t=conexoes[i]
            origens[t.get('inicio_fonte','NAO_DOCUMENTADA')+' → '+t.get('fim_fonte','NAO_DOCUMENTADA')]+=1
        inventario.append(dict(uid=c['uid'],numero=c['id'],porte=c['classe_tamanho'],nos=c['nos'],tubos=c['tubulacoes'],
            n_nos=c['n_nos'],n_dispositivos=c['n_dispositivos'],n_tubos=len(c['tubulacoes']),
            reservatorios=reservatorios,tanques=tanques,bombas=bombas,extremidades=sorted(ext),
            referencias_incompletas=refs,origens_conexoes=dict(origens),proporcao=c['proporcao_tubos'],
            caminho_estrutural_ate_fonte=bool(reservatorios or tanques),
            interpretacao_fonte='Possui reservatório/tanque no componente cadastrado' if reservatorios or tanques else
                ('Sem caminho estrutural cadastrado até reservatório/tanque; abastecimento real indeterminado' if resultado['resumo']['modo']=='ESTRUTURAL' else
                 'Sem reservatório/tanque neste componente da hipótese; não conclui desconexão na perspectiva estrutural nem falta real de água'),
            vizinhos=[],distancia_m=None,areas=[]))
    return inventario,membros,fontes


def preparar_contexto(modelo,resultado):
    g=grafo_elementos(resultado);componentes={}
    for c in resultado['componentes']:
        for i in c['tubulacoes']:componentes[i]=c['uid']
    sem_dispositivos=nx.subgraph_view(g,filter_node=lambda n:n[0]=='T' or modelo['elementos'][n[1]]['familia']!='DISPOSITIVO')
    return dict(resultado=resultado,g=g,sem_dispositivos=sem_dispositivos,componentes=componentes,
        conexoes={c['id']:c for c in resultado['conexoes']})


def caminho(g,a,b):
    if a not in g or b not in g:return None
    try:return nx.shortest_path(g,a,b)
    except nx.NetworkXNoPath:return None


def classificar_par(modelo,contexto,a,b,continuidade=False,distancia=None,limiar=5,restricoes=()):
    """a/b são correspondências GIS completas, com candidatos preservados."""
    r=dict(gis_a=a['gis_uid'],gis_b=b['gis_uid'],wg_a=a['candidatos'],wg_b=b['candidatos'],classes=[],
        nos_compartilhados=[],componentes=[],caminho_ab=None,caminho_ba=None,alternativa_sem_nos_compartilhados=None,
        dispositivos=[],dependencia_dispositivos=False,distancia_m=distancia,motivos=[])
    if any(x['situacao']!='INEQUIVOCA' or len(x['candidatos'])!=1 for x in (a,b)):
        r['classes']=[INSUFICIENTE];r['motivos']=['Correspondência não inequívoca; nenhum candidato foi escolhido'];return r
    ia,ib=a['candidatos'][0],b['candidatos'][0]
    if ia==ib:
        r['classes']=[INSUFICIENTE];r['motivos']=['Duas identidades GIS indicam a mesma tubulação WaterGEMS'];return r
    ca,cb=contexto['conexoes'].get(ia),contexto['conexoes'].get(ib)
    if ca is None or cb is None:
        r['classes']=[INSUFICIENTE];r['motivos']=['Tubulação não disponível nesta perspectiva (atividade/referência/dispositivo)'];return r
    compartilhados=sorted({ca['inicio'],ca['fim']}&{cb['inicio'],cb['fim']})
    r['nos_compartilhados']=compartilhados
    r['componentes']=[contexto['componentes'][ia],contexto['componentes'][ib]]
    pa,pb=('T',ia),('T',ib);g=contexto['g'];ab=caminho(g,pa,pb);ba=caminho(g,pb,pa)
    r['caminho_ab']=ab;r['caminho_ba']=ba
    if compartilhados:
        r['classes'].append(DIRETA)
        r['motivos'].append('Start/Stop compartilham nó(s) explícito(s); não é confirmação operacional')
        outro=nx.subgraph_view(g,filter_node=lambda n:n[0]=='T' or n[1] not in compartilhados)
        r['alternativa_sem_nos_compartilhados']=bool(caminho(outro,pa,pb) or caminho(outro,pb,pa))
    elif r['componentes'][0]==r['componentes'][1]:
        r['classes'].append(MESMO)
        r['motivos'].append('Mesmo componente fraco, sem nó comum; consultar alcance dirigido nas duas orientações')
    else:r['classes'].append(DIFERENTES)
    testemunha=ab or ba or []
    r['dispositivos']=sorted({n[1] for n in testemunha if n[0]=='N' and modelo['elementos'][n[1]]['familia']=='DISPOSITIVO'} |
        {n for n in compartilhados if modelo['elementos'][n]['familia']=='DISPOSITIVO'})
    if not ab and not ba and any(modelo['elementos'][n]['familia']=='DISPOSITIVO' for n in compartilhados):
        r['classes'].append(DISPOSITIVO)
        r['dependencia_dispositivos']=True
        r['motivos'].append('Nó-dispositivo compartilhado no cadastro, sem passagem disponível nesta hipótese')
    if ab or ba:
        livre=caminho(contexto['sem_dispositivos'],pa,pb) or caminho(contexto['sem_dispositivos'],pb,pa)
        r['dependencia_dispositivos']=not bool(livre)
        if not livre:
            r['classes'].append(DISPOSITIVO)
            r['motivos'].append('Não há caminho sem dispositivos; os listados pertencem a um exemplo, não são todos comprovadamente indispensáveis')
    if DIFERENTES in r['classes'] and continuidade and distancia is not None and distancia<=limiar:
        r['classes'].append(AUSENTE)
        r['motivos'].append('Continuidade potencial do núcleo + correspondência inequívoca + componentes distintos + proximidade métrica; não prova que conectar é correto')
    for regra in restricoes:
        if regra.get('confirmada') is True and regra.get('fonte') and regra.get('projeto')==modelo['projeto'] and set(regra.get('tubos',[]))=={ia,ib} and (ab or ba):
            r['classes'].append(INDEVIDA);r['motivos'].append('Restrição explicitamente confirmada para o par: '+regra['fonte'])
    return r


def integrar_locais(dossie,modelo,estrutural,potencial,associacoes,geometrias=None,limiar=5,restricoes=(),cancelar=None):
    associacoes_por_uid={a['gis_uid']:a for a in associacoes}
    tubos={t['uid']:t for t in dossie['tubulacoes']};eventos={e['uid']:e for e in dossie['eventos']}
    por_local=defaultdict(set);eventos_tubos=defaultdict(set)
    for r in dossie['evento_rede']:eventos_tubos[r['evento_uid']].add(r['tubo_uid'])
    for r in dossie['local_evento']:por_local[r['local_uid']]|=eventos_tubos[r['evento_uid']]
    contextos={'ESTRUTURAL':preparar_contexto(modelo,estrutural),'TODAS_VALVULAS_ABERTAS':preparar_contexto(modelo,potencial)}
    saida=[];pares=[]
    for l in dossie['locais']:
        checar_cancelamento(cancelar);ids=sorted(por_local[l['uid']]);regs=[]
        for uid in ids:regs.append(associacoes_por_uid.get(uid,dict(gis_uid=uid,situacao='NAO_ENCONTRADA',candidatos=[],nos=[])))
        por_modo={}
        for modo,ctx in contextos.items():
            ps=[]
            for a,b in combinations(regs,2):
                ev_comuns=[eventos[e] for e in l['eventos'] if {a['gis_uid'],b['gis_uid']}<=eventos_tubos[e]]
                continuidade=any(e['tecnico']['classificacao']=='CONTINUIDADE_POTENCIAL' for e in ev_comuns)
                dist=None
                if geometrias and len(a['candidatos'])==len(b['candidatos'])==1:
                    ga,gb=geometrias.get(a['candidatos'][0]),geometrias.get(b['candidatos'][0])
                    if ga and gb:dist=ga.distance(gb)
                p=classificar_par(modelo,ctx,a,b,continuidade,dist,limiar,restricoes)
                p.update(local_uid=l['uid'],modo=modo,uid=sha256(repr((l['uid'],modo,a['gis_uid'],b['gis_uid'],VERSAO_REGRAS)).encode()).hexdigest())
                ps.append(p);pares.append(p)
            classes=sorted({c for p in ps for c in p['classes']})
            if not ps:
                classes=[INSUFICIENTE] if any(r['situacao']!='INEQUIVOCA' for r in regs) else []
            principal=next((c for c in PRIORIDADE if c in classes),'SEM_PAR_COMPARAVEL')
            por_modo[modo]=dict(classe=principal,classes=classes,n_pares=len(ps),pares=[p['uid'] for p in ps],
                componentes=sorted({ctx['componentes'][i] for r in regs for i in r['candidatos'] if i in ctx['componentes']}),
                escopo='TUBULACAO_UNICA' if len(regs)==1 else 'PARES_DE_TUBULACOES')
        saida.append(dict(uid=l['uid'],registro=l['registro'],eventos=l['eventos'],tubos_gis=ids,
            correspondencias=regs,tubos_wg=sorted({i for r in regs for i in r['candidatos']}),perspectivas=por_modo,
            pendencias=['Conferência WaterGEMS/Network Navigator pendente','Estados operacionais/controles não validados'],
            areas=[]))
    return saida,pares
