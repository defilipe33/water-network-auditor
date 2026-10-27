"""Projeção de apresentação dos resultados existentes; não recalcula diagnósticos."""
from collections import Counter, defaultdict
from hashlib import sha256

MODOS=('ESTRUTURAL','TODAS_VALVULAS_ABERTAS')
CATEGORIAS={
    'AUSENTE':'Possíveis conexões ausentes',
    'PEQUENO':'Componentes pequenos ou isolados',
    'REGIOES':'Conexões cadastradas entre regiões',
    'DISPOSITIVO':'Conectividade dependente de dispositivos',
    'GIS_INCONSISTENTE':'Correspondências GIS inconsistentes',
    'GIS_AUSENTE':'Correspondências GIS não encontradas',
    'REFERENCIA':'Referências topológicas incompletas',
    'OUTROS':'Outras situações investigáveis'}
CLASSES={
    'POSSIVEL_CONEXAO_AUSENTE':'Possível conexão ausente',
    'CONEXAO_DIRETA_CONFIRMADA_NO_MODELO':'Nó compartilhado no modelo',
    'MESMO_COMPONENTE_SEM_CONEXAO_DIRETA':'Mesmo componente, sem nó compartilhado',
    'COMPONENTES_DIFERENTES':'Componentes diferentes',
    'CONECTIVIDADE_DEPENDENTE_DE_DISPOSITIVO':'Caminho dependente de dispositivo',
    'CONEXAO_POTENCIALMENTE_INDEVIDA':'Conexão a conferir contra restrição confirmada',
    'CORRESPONDENCIA_INSUFICIENTE':'Correspondência insuficiente para concluir',
    'SEM_PAR_COMPARAVEL':'Um único tubo; não há par para comparar'}
TIPOS={'IdahoPipe':'Tubulação','IdahoJunction':'Nó','IdahoReservoir':'Reservatório',
    'ConventionalTank':'Tanque','IdahoTank':'Tanque','StandardPump':'Bomba',
    'AirValve':'Ventosa','PRV':'VRP','TCV':'Válvula TCV','CheckValve':'Válvula de retenção'}


def catalogar(pacote):
    """Uma ocorrência por contexto de origem; categorias são etiquetas não aditivas."""
    r=pacote['resultado'];d=pacote['dossie'];m=pacote['topologia']['modelo'];el=m['elementos']
    comps={modo:{c['uid']:c for c in r['componentes' if modo==MODOS[0] else 'componentes_potenciais']} for modo in MODOS}
    tubo_comp={modo:{i:c['uid'] for c in cs.values() for i in c['tubos']} for modo,cs in comps.items()}
    no_comp={modo:defaultdict(set) for modo in MODOS}
    for modo,cs in comps.items():
        for c in cs.values():
            for i in c['nos']:no_comp[modo][i].add(c['uid'])
    pares={p['uid']:p for p in r['pares']};eventos={e['uid']:e for e in d['eventos']}
    tubos={t['uid']:t for t in d['tubulacoes']};areas={a['uid']:a for a in pacote['areas']}
    rev={l['uid']:l['revisao']['situacao'] for l in d['locais']}
    saida=[]

    def novo(tipo,chave,cats,titulo,resumo,ids,gis=(),area_ids=(),local=None,evidencias=(),proxima='',tecnico=(),prioridade='Média'):
        ids=set(ids);componentes={modo:sorted({tubo_comp[modo][i] for i in ids if i in tubo_comp[modo]} |
            {u for i in ids for u in no_comp[modo].get(i,())}) for modo in MODOS}
        fontes={modo:any(comps[modo][u]['reservatorios'] or comps[modo][u]['tanques'] for u in us) if us else None for modo,us in componentes.items()}
        reg=[areas[a]['exibicao'] for a in area_ids if a in areas]
        if local and not reg:
            registro=next(l['registro'] for l in r['locais'] if l['uid']==local)
            reg=[v.strip() for v in registro.get('AREAS','').split(';') if v.strip()]
        rotulos=[f"{TIPOS.get(el[i]['tipo'],el[i]['tipo'])} {el[i]['label']}" for i in sorted(ids) if i in el]
        gs=[f"{tubos[u]['id_exibido']} — {tubos[u]['camada']}" for u in gis if u in tubos]
        uid=sha256(repr((r['meta']['uid'],tipo,chave,'diagnosticos-1')).encode()).hexdigest()
        caso=dict(uid=uid,tipo=tipo,chave=chave,categorias=cats,titulo=titulo,resumo=resumo,
            wg_ids=sorted(ids),gis_uids=list(gis),area_uids=list(area_ids),local_uid=local,
            regioes=sorted(set(reg)),elementos=rotulos,tubos_gis=gs,evidencias=list(evidencias),
            proxima=proxima,tecnico=list(tecnico),componentes=componentes,fontes=fontes,
            prioridade=prioridade,revisao=rev.get(local,'SEM_REVISAO_POR_OCORRENCIA'),perspectivas={})
        for modo in MODOS:
            indisponiveis=[i for i in ids if i in el and el[i].get('ativo') is not True]
            bombas=[i for i in ids if el.get(i,{}).get('tipo') in ('StandardPump','VariableSpeedPumpBattery')]
            avisos=[]
            if modo==MODOS[1]:
                if indisponiveis:avisos.append(f'{len(indisponiveis)} elemento(s) inativo(s) ou com atividade indeterminada; fora da hipótese quando não ativos')
                if bombas:avisos.append(f'{len(bombas)} bomba(s): passagem sem disponibilidade comprovada não habilitada')
            caso['perspectivas'][modo]=dict(texto=f"{len(componentes[modo])} componente(s) envolvido(s)",avisos=avisos)
        caso['busca']=' '.join([titulo,resumo,*gs,*rotulos,*map(str,ids),*gis,*reg]).casefold()
        saida.append(caso);return caso

    for l in r['locais']:
        classes={c for p in l['perspectivas'].values() for c in p['classes']}
        cats=[]
        if 'POSSIVEL_CONEXAO_AUSENTE' in classes:cats.append('AUSENTE')
        if 'CONECTIVIDADE_DEPENDENTE_DE_DISPOSITIVO' in classes:cats.append('DISPOSITIVO')
        trans=[]
        validados={a['gis_uid'] for a in l['correspondencias'] if a['situacao']=='INEQUIVOCA' and len(a['candidatos'])==1}
        for u in l['eventos']:
            e=eventos[u]['tecnico'];a=e.get('regiao_antes',[]);b=e.get('regiao_depois',[])
            participantes={t['chave'] for t in e.get('tubulacoes',[])}
            if e['modo']=='TRANSICAO' and e['classificacao']=='TRAVESSIA' and len(a)==len(b)==1 and a[0]['chave']!=b[0]['chave'] and participantes and participantes<=validados:
                trans.append(eventos[u]['registro'])
        if trans and any(a['situacao']=='INEQUIVOCA' for a in l['correspondencias']):cats.append('REGIOES')
        if 'CORRESPONDENCIA_INSUFICIENTE' in classes or 'CONEXAO_POTENCIALMENTE_INDEVIDA' in classes or 'COMPONENTES_DIFERENTES' in classes:cats.append('OUTROS')
        if not cats:continue
        reg=l['registro'];ps=[pares[u] for p in l['perspectivas'].values() for u in p['pares']]
        ids=set(l['tubos_wg']) | {i for p in ps for i in p['dispositivos']} | {i for p in ps for i in p['nos_compartilhados']}
        for a in l['correspondencias']:
            for n in a.get('nos',[]):ids.update((n['inicio'],n['fim']))
        nome=CATEGORIAS[cats[0]]
        evidencias=list(dict.fromkeys(t for p in ps for t in p['motivos']))
        for t in trans:evidencias.append(f"Travessia geométrica: {t['REG_ANTES']} → {t['REG_DEPOIS']}; orientação não é sentido de fluxo")
        tecnico=[('Par '+p['modo'],f"Tubos {p['wg_a']} / {p['wg_b']} | Nós compartilhados {p['nos_compartilhados']} | Distância {p['distancia_m']} m | Caminho A→B {p['caminho_ab'] is not None} | B→A {p['caminho_ba'] is not None} | Alternativa {p['alternativa_sem_nos_compartilhados']} | Par UID {p['uid']}") for p in ps]
        caso=novo('LOCAL',l['uid'],cats,f"{reg['LOCAL']} — {nome.lower()}",
            f"{reg['N_EVENTOS']} evento(s), {reg['N_TUBOS']} tubulação(ões). {reg['AREAS']}. As evidências não confirmam operação hidráulica.",
            ids,l['tubos_gis'],l['areas'],l['uid'],evidencias,
            'Conferir Start/Stop no WaterGEMS e cadastro; verificar em campo se a separação ou passagem é intencional.',tecnico,'Alta' if 'AUSENTE' in cats else 'Média')
        for modo in MODOS:caso['perspectivas'][modo]['texto']=CLASSES.get(l['perspectivas'][modo]['classe'],l['perspectivas'][modo]['classe'])
        caso['categorias_por_modo']={}
        for modo in MODOS:
            cc=l['perspectivas'][modo]['classes'];etiquetas=[]
            if 'POSSIVEL_CONEXAO_AUSENTE' in cc:etiquetas.append('AUSENTE')
            if 'CONECTIVIDADE_DEPENDENTE_DE_DISPOSITIVO' in cc:etiquetas.append('DISPOSITIVO')
            if 'REGIOES' in cats:etiquetas.append('REGIOES')
            if any(c in cc for c in ('CORRESPONDENCIA_INSUFICIENTE','CONEXAO_POTENCIALMENTE_INDEVIDA','COMPONENTES_DIFERENTES')):etiquetas.append('OUTROS')
            caso['categorias_por_modo'][modo]=etiquetas
    for c in r['componentes']:
        if c['n_tubos']>=100:continue
        n=c['n_tubos'];ids=c['nos']+c['tubos']
        titulo=('Elemento isolado' if not n else 'Rede de uma tubulação' if n==1 else f"Pequena rede de {n} tubulações")
        evidencias=[f"{n} tubo(s), {c['n_nos']} nó(s) regular(es), {c['n_dispositivos']} dispositivo(s).",c['interpretacao_fonte']]
        if c['distancia_m'] is not None:evidencias.append(f"Outro componente mais próximo a {c['distancia_m']:.2f} m; distância não é proposta de conexão")
        novo('COMPONENTE',c['uid'],['PEQUENO'],f"{titulo} — componente {c['numero']}",
            'A incidência cadastrada forma um componente pequeno. Pode representar cadastro incompleto, elemento auxiliar ou separação intencional.',
            ids,area_ids=c['areas'],evidencias=evidencias,
            proxima='Localizar os elementos e conferir incidência, tipo, atividade e dispositivos no Network Navigator. Não concluir falta de abastecimento.',
            tecnico=[('Componente estrutural',c['uid']),('Origem das conexões',str(c['origens_conexoes'])),('Referências incompletas',str(c['referencias_incompletas']))],
            prioridade='Média' if c['referencias_incompletas'] else 'Baixa')
    for numero,p in enumerate(sorted(r['pendencias'],key=lambda p:p['gis_uid']),1):
        cats=['GIS_INCONSISTENTE' if p['situacao']=='INCONSISTENTE' else 'GIS_AUSENTE']
        aa={a for l in r['locais'] if l['uid'] in p['locais'] for a in l['areas']}
        exibicao=p['id_exibido'] if p['id_bruto'] is not None else f'Sem ID · caso cadastral {numero}'
        novo('GIS',p['gis_uid'],cats,f"{exibicao} — {CATEGORIAS[cats[0]].lower()}",
            f"Origem: {p['camada']}. Não há correspondência validada que permita concluir a conectividade desta identidade GIS.",
            p['candidatos'],[p['gis_uid']],aa,evidencias=p['motivos'],
            proxima='Comparar identificador cadastral, origem e geometrias; preservar candidatos até confirmação, sem escolher por proximidade.',
            tecnico=[('GIS UID',p['gis_uid']),('Situação',p['situacao']),('Geometria preservada',p['geometria_status'])])
    ds=defaultdict(list)
    for modo in MODOS:
        for v in pacote['topologia']['estrutural' if modo==MODOS[0] else 'potencial']['diagnosticos']:
            if v['codigo'].startswith('JUSANTE_') or v['codigo']=='VINCULO_AUSENTE':ds[v['id']].append((modo,v))
    for i,refs in ds.items():
        novo('REFERENCIA',str(i),['REFERENCIA'],f"Referência incompleta — {el[i]['tipo']} {el[i]['label']}",
            'O leitor preservou uma referência ausente ou indisponível. Geometria não foi usada para ocultar a pendência.',[i],
            evidencias=sorted({v['codigo'].replace('_',' ').capitalize() for _,v in refs}),
            proxima='Conferir jusante, Start/Stop, exclusão e Active Topology no cenário selecionado.',
            tecnico=[(modo,f"{v['codigo']} | ID {i} | Referência {v.get('relacionado')} | {v.get('descricao','')}") for modo,v in refs])
    return sorted(saida,key=lambda c:({'Alta':0,'Média':1,'Baixa':2}[c['prioridade']],c['titulo'],c['uid']))


def filtrar(casos,categoria=None,componente=None,regiao=None,revisao=None,modo='ESTRUTURAL',elemento='',fonte=None,prioridade=None):
    return [c for c in casos if (not categoria or categoria in c.get('categorias_por_modo',{}).get(modo,c['categorias']))
        and (not componente or componente in c['componentes'][modo]) and (not regiao or regiao in c['regioes'])
        and (not revisao or revisao==c['revisao']) and (not elemento or elemento.casefold() in c['busca'])
        and (fonte is None or c['fontes'][modo] is fonte) and (not prioridade or prioridade==(c.get('prioridade_trabalho') or c.get('prioridade_sugerida',c['prioridade'])))]


def contagens(casos):
    return dict(total=len(casos),categorias=dict(Counter(cat for c in casos for cat in c['categorias'])))
