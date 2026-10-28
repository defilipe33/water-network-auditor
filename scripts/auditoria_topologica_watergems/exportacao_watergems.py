"""Fotografia de conjuntos e percursos cadastrados, sem escrita no WaterGEMS."""
from collections import Counter,defaultdict
import csv,json,math,os,re,tempfile
from pathlib import Path
from .decisoes import MODOS

FONTE_QUERY='https://bentleysystems.service-now.com/community?id=kb_article_view&sysparm_article=KB0014274'


def preparar(pacote,registro):
    modo=registro['modo'];meta=pacote['resultado']['meta'];topo=meta['topologia']['execucao_uid']
    if modo not in MODOS or registro['topo_uid']!=topo:raise ValueError('Conjunto pertence a outra versão/perspectiva; abra a fonte correspondente.')
    el=pacote['topologia']['modelo']['elementos'];g=pacote['topologia']['estrutural' if modo=='ESTRUTURAL' else 'potencial']['grafo']
    selecionados={};avisos=[];distintos={};ordens=[]
    for v in registro['vinculos']:
        i=int(v['chave']);e=el.get(i)
        if v['origem']!='WG' or not e or e.get('uid')!=v['dados'].get('uid') or e.get('excluido') is not False:raise ValueError('Identidade ausente/incompatível: '+str(i))
        if i in selecionados:raise ValueError('Identificador duplicado no conjunto: '+str(i))
        selecionados[i]=v.get('natureza','MANUAL')
    def incluir(i,origem):
        if i not in el:raise ValueError('Elemento do percurso não encontrado: '+str(i))
        e=el[i]
        if e.get('excluido') is not False:raise ValueError('Elemento excluído no percurso: '+str(i))
        r=distintos.setdefault(i,dict(DomainElementID=i,Label=e.get('label'),Tipo=e['tipo'],UID=e['uid'],Modelo=meta['topologia'].get('projeto'),Cenario=meta['topologia'].get('cenario'),Perspectiva=modo,Versao=topo,Conjunto=registro['obj_uid'],Origem=[],Correspondencia='IDENTIDADE_TECNICA'))
        if origem not in r['Origem']:r['Origem'].append(origem)
    endpoints=defaultdict(set)
    for a,b,d in g.edges(data=True):
        if d.get('natureza')=='TUBULACAO' and d['elemento'] in selecionados:endpoints[d['elemento']].add((tuple(a),tuple(b)))
    for i,origem in selecionados.items():
        if not endpoints[i]:raise ValueError('Tubulação ausente no grafo: '+str(i))
        incluir(i,origem)
        for a,b in endpoints[i]:
            incluir(a[0],'EXTREMIDADE_TOPOLOGICA');incluir(b[0],'EXTREMIDADE_TOPOLOGICA')
        unicos={frozenset((a,b)) for a,b in endpoints[i]}
        if len(unicos)>1:avisos.append(f'{i}: múltiplas extremidades cadastradas; não foi escolhida uma ligação arbitrária.')
    criterios=registro['dados'].get('criterios',{});criterios=criterios if isinstance(criterios,dict) else {}
    for rota in criterios.get('rotas',[])+criterios.get('rotas_alternativas',[]):
        es=rota.get('arestas',[]);segmento=0;acumulado=0.;ordem=0;ultimo=None
        # Arestas de dispositivos só entram entre tubos efetivamente mantidos da rota.
        mantidos=[k for k,e in enumerate(es) if e['natureza']=='TUBULACAO' and e['elemento'] in selecionados]
        permitidas=set(mantidos)
        for a,b in zip(mantidos,mantidos[1:]):
            if all(e['natureza']=='DISPOSITIVO' for e in es[a+1:b]):permitidas.update(range(a+1,b))
        for k,e in enumerate(es):
            if k not in permitidas:ultimo=None;continue
            a,b=tuple(e['inicio']),tuple(e['fim']);i=e['elemento']
            if not any(d.get('elemento')==i and d.get('natureza')==e['natureza'] for d in g.get_edge_data(a,b,default={}).values()):raise ValueError('Percurso incompatível com o grafo atual: '+str(i))
            if ultimo!=a:segmento+=1;acumulado=0.;ordem=0
            incluir(a[0],'ROTA');incluir(i,'ROTA_ALTERNATIVA' if rota.get('alternativa') else 'ROTA_PRINCIPAL');incluir(b[0],'ROTA')
            comp=e.get('comprimento_m');acumulado=acumulado+comp if acumulado is not None and comp is not None and math.isfinite(comp) else None
            ordem+=1;ordens.append(dict(Rota=rota['uid'],Segmento=segmento,Ordem=ordem,NoInicial=a[0],PortaInicial=a[1],Elemento=i,Label=el[i].get('label'),NoFinal=b[0],PortaFinal=b[1],Tipo=el[i]['tipo'],Direcao='ARESTA_DIRIGIDA_DA_PERSPECTIVA_NAO_VAZAO',ComprimentoAcumulado_m=acumulado,Dispositivo=i if e['natureza']=='DISPOSITIVO' else None,Caminho='ALTERNATIVO' if rota.get('alternativa') else 'PRINCIPAL'))
            ultimo=b
        if len(mantidos)!=len(rota.get('tubulacoes',[])):avisos.append('Rota '+str(rota['uid'])+': segmentos fora da seleção final omitidos; não se presume continuidade após edição.')
    if not ordens:avisos.append('Sem percurso ordenado persistido; extremidades vêm do grafo, sem sequência inventada.')
    for r in distintos.values():r['Origem']='; '.join(r['Origem'])
    return dict(elementos=list(distintos.values()),percursos=ordens,contagens=dict(Counter(r['Tipo'] for r in distintos.values())),avisos=avisos,conjunto=registro['obj_uid'],versao=topo,modo=modo)


def consultas(dados,modelo,campo='Label',campo_id=None,validado=False,max_itens=100,max_caracteres=4000):
    """IN documentado pela Bentley; nome do campo ID exige validação local explícita.

    Limites são lotes conservadores configuráveis, não limites declarados do produto.
    """
    if max_itens<1 or max_caracteres<40:raise ValueError('Limites de lote inválidos')
    if campo not in ('Label','ID'):raise ValueError('Campo de consulta inválido')
    if campo=='ID' and (not validado or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',campo_id or '')):raise ValueError('Confirme o campo ID real no Query Builder antes de usá-lo.')
    todos=defaultdict(Counter)
    for e in modelo['elementos'].values():
        if e.get('excluido') is False:todos[e['tipo']][e.get('label')]+=1
    grupos=defaultdict(list)
    for e in dados['elementos']:
        valor=e['DomainElementID'] if campo=='ID' else e['Label']
        if campo=='Label' and (not isinstance(valor,str) or not valor or todos[e['Tipo']][valor]!=1):raise ValueError('Label nulo, vazio ou repetido no tipo '+e['Tipo']+': '+str(valor)+'. Confirme o campo ID no Query Builder.')
        literal=str(int(valor)) if campo=='ID' else "'"+valor.replace("'","''")+"'"
        if any(c in literal for c in ('\n','\r','\x00')):raise ValueError('Label contém caractere de controle; use ID validado.')
        grupos[e['Tipo']].append(literal)
    saida=[];nome=campo_id if campo=='ID' else 'Label'
    for tipo,vals in sorted(grupos.items()):
        lote=[]
        def emitir():
            saida.append(dict(tipo=tipo,lote=1+sum(r['tipo']==tipo for r in saida),quantidade=len(lote),expressao=nome+' IN ('+','.join(lote)+')',estado='SINTAXE_DOCUMENTADA_CONFERIR_NO_QUERY_BUILDER',fonte=FONTE_QUERY))
        for v in vals:
            if len(nome)+7+len(v)>max_caracteres:raise ValueError('Valor excede o tamanho de lote; aumente o limite, sem truncar.')
            if lote and (len(lote)>=max_itens or len(nome)+7+sum(len(x)+1 for x in lote)+len(v)>max_caracteres):emitir();lote=[]
            lote.append(v)
        if lote:emitir()
    return saida


def conferir(dados,selecionados,versao):
    if versao!=dados['versao']:raise ValueError('Versão WaterGEMS incompatível')
    esperados={(str(e['DomainElementID']),e['Tipo']):e for e in dados['elementos']};vistos=Counter((str(e['DomainElementID']),e['Tipo']) for e in selecionados)
    return dict(ausentes=[list(k) for k in esperados.keys()-vistos.keys()],adicionais=[list(k) for k in vistos.keys()-esperados.keys()],duplicados=[list(k) for k,n in vistos.items() if n>1],labels_divergentes=[list(k) for e in selecionados if (k:=(str(e['DomainElementID']),e['Tipo'])) in esperados and e.get('Label')!=esperados[k]['Label']],esperados=len(esperados),selecionados=len(vistos))


def csv_novo(path,linhas):
    with Path(path).open('x',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(linhas[0]) if linhas else ['SEM_REGISTROS'],delimiter=';');w.writeheader();w.writerows(linhas)


def exportar(pasta,pacote,registro,opcoes=None):
    import shutil
    pasta=Path(pasta);opcoes=opcoes or {};dados=preparar(pacote,registro)
    if pasta.exists():raise FileExistsError('Escolha uma pasta nova; exportações anteriores são preservadas.')
    pasta.parent.mkdir(parents=True,exist_ok=True);tmp=Path(tempfile.mkdtemp(prefix='.exportacao_',dir=pasta.parent))
    try:
        if opcoes.get('lista',True):csv_novo(tmp/'ELEMENTOS.csv',dados['elementos'])
        if opcoes.get('percursos',True):csv_novo(tmp/'PERCURSOS.csv',dados['percursos'])
        if opcoes.get('queries',True):
            qs=consultas(dados,pacote['topologia']['modelo'],opcoes.get('campo','Label'),opcoes.get('campo_id'),opcoes.get('id_validado',False),opcoes.get('max_itens',100),opcoes.get('max_caracteres',4000));csv_novo(tmp/'CONSULTAS.csv',qs)
            for n,q in enumerate(qs,1):(tmp/f'QUERY_{n:04}.txt').write_text(q['expressao'],encoding='utf8')
        if opcoes.get('conferencia',True):(tmp/'CONFERENCIA.json').write_text(json.dumps(dados,ensure_ascii=False,indent=2),encoding='utf8')
        if opcoes.get('instrucoes',True):(tmp/'LEIA_ME.txt').write_text('Abra o mesmo modelo, cenário e perspectiva. No Query Manager crie uma consulta por tipo e lote; confirme o campo e a sintaxe no Query Builder. IN é documentado pela Bentley: '+FONTE_QUERY+'\nOs limites de lote são conservadores configuráveis, sem limite máximo comprovado do produto. Reúna as seleções com adição, confira por ID/tipo/Label com ELEMENTOS.csv e salve um Selection Set ESTÁTICO. Consulta dinâmica pode mudar com o modelo. Selection by Query não importa CSV. Find Adjacent Nodes só ajuda na seleção: confira os nós contra a lista, sem incluir ramificações/dispositivos vizinhos. Sintaxe local e criação nativa ainda requerem conferência no WaterGEMS desktop. Nenhum SQLite original foi alterado.\n',encoding='utf8')
        os.rename(tmp,pasta)
    finally:
        if tmp.exists():shutil.rmtree(tmp)
    return dados
