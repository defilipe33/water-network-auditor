"""Resolução explícita e auditoria, confrontadas com o Composer no SHA documentado.

Start/Stop têm precedência. Um único proprietário Downstream pode suprir apenas
um Start nulo; nunca substitui referência preenchida, excluída ou contraditória.
Geometria não participa deste resolvedor.
"""
from collections import defaultdict,Counter
import hashlib


def resolver_extremidades(modelo):
    donos=defaultdict(list);resultado={}
    for i,e in modelo['elementos'].items():
        if e['excluido'] is False and e['familia']=='DISPOSITIVO':
            jus=e['topologia'].get('HMITopologyDownstreamLinkID')
            if jus is not None:donos[jus].append(i)
    for i,e in modelo['elementos'].items():
        if e['familia']!='LINK':continue
        t=e['topologia'];a=t.get('HMITopologyStartNodeID');b=t.get('HMITopologyStopNodeID')
        candidatos=sorted(donos.get(i,[]));fonte='BASELINK' if a is not None else 'NAO_RESOLVIDO'
        # Dois directed nodes podem apontar para o MESMO link, um em cada
        # extremidade explícita. Isso não é ambiguidade por si só.
        nao_cobertos=set(candidatos)-{a,b}
        conflito=bool(nao_cobertos and (a is not None or len(candidatos)>1))
        if a is None and len(candidatos)==1 and candidatos[0]!=b:
            a=candidatos[0];fonte='DIRECTED_DOWNSTREAM_EXPLICITO'
        resultado[i]=dict(inicio=a,fim=b,inicio_bruto=t.get('HMITopologyStartNodeID'),
            fim_bruto=b,inicio_fonte=fonte,fim_fonte='BASELINK' if b is not None else 'NAO_RESOLVIDO',
            candidatos_jusante=candidatos,conflito=conflito)
    return resultado


def auditar_jusantes(modelo):
    el=modelo['elementos'];ext=resolver_extremidades(modelo);incidencias=defaultdict(list)
    for i,r in ext.items():
        if el[i]['excluido'] is False:
            for n in set((r['inicio'],r['fim'])):incidencias[n].append(i)
    saida=[]
    for i,e in el.items():
        if e['familia']!='DISPOSITIVO' or e['excluido'] is not False:continue
        jus=e['topologia'].get('HMITopologyDownstreamLinkID');link=el.get(jus);r=ext.get(jus,{})
        flags=[]
        if jus is None:flags.append('REFERENCIA_NAO_INFORMADA')
        elif link is None:flags.append('REFERENCIA_INEXISTENTE')
        elif link['excluido'] is True:flags.append('ELEMENTO_EXCLUIDO')
        elif link['excluido'] is None:flags.append('EXCLUSAO_INDETERMINADA')
        elif link['familia']!='LINK':flags.append('TIPO_REFERENCIADO_INCOMPATIVEL')
        elif r.get('conflito') and len(r.get('candidatos_jusante',[]))>1:flags.append('RELACAO_AMBIGUA')
        elif i not in (r.get('inicio'),r.get('fim')):flags.append('POSSIVEL_INCONSISTENCIA_CADASTRAL')
        elif r.get('inicio_fonte')=='DIRECTED_DOWNSTREAM_EXPLICITO':flags.append('VALIDA_NAO_RESOLVIDA_PELO_LEITOR_ANTERIOR')
        else:flags.append('VALIDA_EXPLICITA')
        if link and link['ativo'] is False:flags.append('ELEMENTO_INATIVO')
        if e['ativo'] is False:flags.append('DISPOSITIVO_INATIVO')
        saida.append(dict(id=i,uid=e['uid'],label=e['label'],tipo=e['tipo'],jusante=jus,
            existe=link is not None,link_excluido=link['excluido'] if link else None,
            link_ativo=link['ativo'] if link else None,dispositivo_ativo=e['ativo'],
            cenario=modelo['cenario'],alternativa=e.get('alternativas',{}).get('topologia'),
            alternativa_link=(link or {}).get('alternativas',{}).get('topologia'),
            classificacao=flags[0],indicadores=flags,incidentes=sorted(incidencias.get(i,[])),
            resolucao=r,geometria_status='NAO_AVALIADA',hipotese_geometrica=False))
    return saida


def detalhar_componentes(modelo,resultado):
    el=modelo['elementos'];n_tubos=len(resultado['conexoes']);pendencias=defaultdict(int)
    for d in resultado['diagnosticos']:
        if d['codigo'] in ('JUSANTE_INVALIDO','JUSANTE_NAO_INFORMADO','VINCULO_AUSENTE','DISPOSITIVO_NAO_INTERPRETADO'):
            pendencias[d['id']]+=1
    for c in resultado['componentes']:
        ids=sorted(set(c['nos']+c['tubulacoes']))
        c['uid']=hashlib.sha256(repr((modelo['projeto'],modelo['cenario'],resultado['resumo']['modo'],
            c['membros_portas'],sorted(c['tubulacoes']))).encode()).hexdigest()
        c['n_nos']=sum(el[i]['familia']=='NO' for i in c['nos'])
        c['n_dispositivos']=sum(el[i]['familia']=='DISPOSITIVO' for i in c['nos'])
        c['fontes']=[i for i in c['nos'] if el[i]['tipo'] in ('IdahoReservoir','IdahoTank','ConventionalTank')]
        c['referencias_nao_resolvidas']=sum(pendencias[i] for i in ids)
        c['proporcao_tubos']=len(c['tubulacoes'])/n_tubos if n_tubos else 0
        c['classe_tamanho']=('TRIVIAL_SEM_TUBO' if not c['tubulacoes'] else 'UM_TUBO' if len(c['tubulacoes'])==1
            else 'REDE_EXTENSA_100_MAIS' if len(c['tubulacoes'])>=100 else 'REDE_2_A_99_TUBOS')
        c['representantes']=[dict(id=i,label=el[i]['label'],tipo=el[i]['tipo']) for i in ids[:5]]
    return resultado
