"""Confronto de evidências de versões; ausência nunca equivale a correção."""
from collections import defaultdict,Counter
from uuid import uuid4
from pathlib import Path
from .diagnosticos import catalogar,MODOS
from .decisoes import Contextos,digest,agora,preparar_base,conectar,texto,existe
from .arquivos import hash_arquivo
from auditoria_fronteiras.versoes import abrir_ro


def contexto_cenario(p):
    m=p['topologia']['modelo'];return dict(projeto=m['projeto'],cenario=m['cenario'],alternativas=m.get('alternativas',{}))


def ancora(c):
    # Um tubo pode participar de vários locais físicos. A chave do local deriva
    # da composição técnica dos eventos, não de seu número legível L0001 etc.
    return (c['tipo'],tuple(sorted(c['gis_uids'])) if c['gis_uids'] else tuple(sorted(c['wg_ids'])),c['chave'] if c['tipo']=='LOCAL' else '')


def comparar(antigo,novo,modo='ESTRUTURAL',identidade_confirmada=False):
    if modo not in MODOS:raise ValueError('Perspectiva não validada')
    a,b=catalogar(antigo),catalogar(novo);ca,cb=Contextos(antigo),Contextos(novo)
    indice=defaultdict(list);por_elemento=defaultdict(set)
    for c in b:
        indice[ancora(c)].append(c)
        for i in c['wg_ids']:por_elemento[(c['tipo'],i)].add(c['uid'])
    mb={c['uid']:c for c in b};usados=set();linhas=[]
    identidade=antigo['topologia']['modelo']['projeto']==novo['topologia']['modelo']['projeto'] or identidade_confirmada
    cenarios=identidade and antigo['topologia']['modelo']['cenario']==novo['topologia']['modelo']['cenario'] and antigo['topologia']['modelo'].get('alternativas',{})==novo['topologia']['modelo'].get('alternativas',{})
    ea,eb=antigo['topologia']['modelo']['elementos'],novo['topologia']['modelo']['elementos']
    for c in a:
        candidatos=indice[ancora(c)]
        if not candidatos:
            us={u for i in c['wg_ids'] for u in por_elemento.get((c['tipo'],i),())};candidatos=[mb[u] for u in sorted(us)]
        usados.update(n['uid'] for n in candidatos)
        mesmas_ids=all(i in eb and ea[i]['tipo']==eb[i]['tipo'] and ea[i]['label']==eb[i]['label'] for i in c['wg_ids'])
        if not identidade or not mesmas_ids and candidatos:classe='CORRESPONDÊNCIA INCERTA'
        elif not candidatos:classe='NÃO OBSERVADA NA NOVA EXECUÇÃO'
        elif len(candidatos)!=1 or ancora(candidatos[0])!=ancora(c):classe='CORRESPONDÊNCIA INCERTA'
        elif not cenarios:classe='REQUER REAVALIAÇÃO'
        elif ca.assinatura(c,modo)==cb.assinatura(candidatos[0],modo):classe='PERMANECE'
        else:classe='ALTERADA'
        linhas.append(dict(origem=c['uid'],destinos=[n['uid'] for n in candidatos],titulo=c['titulo'],classe=classe,
            reavaliar=classe in ('ALTERADA','CORRESPONDÊNCIA INCERTA','REQUER REAVALIAÇÃO'),
            assinatura_anterior=ca.assinatura(c,modo),assinaturas_atuais=[cb.assinatura(n,modo) for n in candidatos],
            motivos='Não transfere conclusões nem confirma correção; conferir composição, grafo, cenário e evidências.'))
    for c in b:
        if c['uid'] not in usados:linhas.append(dict(origem=None,destinos=[c['uid']],titulo=c['titulo'],classe='NOVA OCORRÊNCIA',reavaliar=False,motivos='Ocorrência nova no catálogo; não é erro confirmado.'))
    return dict(uid=uuid4().hex,modo=modo,origem=antigo['resultado']['meta']['uid'],destino=novo['resultado']['meta']['uid'],
        identidade_confirmada=bool(identidade_confirmada),cenarios_comparaveis=cenarios,data_utc=agora(),
        contagens=dict(Counter(l['classe'] for l in linhas)),linhas=linhas)


def salvar_comparacao(base,pacote,resultado,base_anterior=None):
    if resultado['destino']!=pacote['resultado']['meta']['uid']:raise ValueError('Comparação pertence a outra execução de destino')
    if base_anterior:resultado=dict(resultado,base_anterior=str(Path(base_anterior).resolve()),sha256_anterior=hash_arquivo(base_anterior))
    resultado=dict(resultado,resumo_destino=resumo_revisoes(base,resultado['destino'],resultado['modo'],len(catalogar(pacote))))
    if base_anterior:resultado['resumo_origem']=resumo_revisoes(base_anterior,resultado['origem'],resultado['modo'],sum(l['origem'] is not None for l in resultado['linhas']))
    preparar_base(base,pacote)
    with conectar(base) as con:
        con.execute('BEGIN IMMEDIATE')
        con.execute('INSERT INTO IGD_COMPARACOES VALUES(?,?,?,?,?)',(resultado['uid'],resultado['origem'],resultado['destino'],resultado['data_utc'],texto(resultado)))
        for k,l in enumerate(resultado['linhas']):con.execute('INSERT INTO IGD_CORRESPONDENCIAS VALUES(?,?,?,?,?,?,?)',(resultado['uid'],k,l['origem'],';'.join(l['destinos']) or None,l['classe'],int(l['reavaliar']),texto(l)))
    return resultado['uid']


def resumo_revisoes(base,ig,modo,total):
    with abrir_ro(base) as con:
        if not existe(con):return dict(casos=total,revisados=0,pendentes=total,corretos=0,com_proposta=0)
        con.row_factory=__import__('sqlite3').Row
        hs={r['occ_uid']:dict(r) for r in con.execute('SELECT * FROM IGD_REVISOES WHERE ig_uid=? AND modo=? ORDER BY rowid',(ig,modo))}
        props=con.execute('SELECT count(DISTINCT occ_uid) FROM IGD_PROPOSTAS WHERE ig_uid=? AND modo=?',(ig,modo)).fetchone()[0]
        revisados=sum(h['situacao']!='PENDENTE' for h in hs.values())
        return dict(casos=total,revisados=revisados,pendentes=total-revisados,corretos=sum(h['conclusao']=='CONECTIVIDADE CORRETA' for h in hs.values()),com_proposta=props)


def avaliar_proposta(proposta,antigo,novo):
    h=proposta['atual'];ids=[int(e['wg_id']) for e in h['elementos']];ea=antigo['topologia']['modelo']['elementos'];eb=novo['topologia']['modelo']['elementos']
    iguais=all(i in ea and i in eb and (ea[i]['tipo'],ea[i]['label'])==(eb[i]['tipo'],eb[i]['label']) for i in ids)
    comparaveis=contexto_cenario(antigo)==contexto_cenario(novo)
    modo=proposta['modo'];ch='estrutural' if modo==MODOS[0] else 'potencial';a,b=antigo['topologia'][ch],novo['topologia'][ch]
    def diretas(r):return [v['id'] for v in r['conexoes'] if len(ids)==2 and {v['inicio'],v['fim']}==set(ids)]
    def composicao(r):return sorted([dict(nos=c['nos'],tubos=c['tubulacoes']) for c in r['componentes'] if set(ids)&set(c['nos']+c['tubulacoes'])],key=texto)
    da,db=diretas(a),diretas(b)
    codigo='INCONCLUSIVO'
    if not comparaveis or not iguais:codigo='CORRESPONDENCIA_OU_CENARIO_INSUFICIENTE'
    elif h['tipo']=='Conectar dois nós':codigo='LIGACAO_DIRETA_OBSERVADA' if db else 'LIGACAO_DIRETA_NAO_OBSERVADA'
    novos=[v for v in b['diagnosticos'] if v['id'] in ids and (v['codigo'],v['id'],v.get('relacionado')) not in {(x['codigo'],x['id'],x.get('relacionado')) for x in a['diagnosticos']}]
    return dict(uid=uuid4().hex,prop_uid=proposta['prop_uid'],hist_uid=h['hist_uid'],origem=antigo['resultado']['meta']['uid'],destino=novo['resultado']['meta']['uid'],modo=modo,
        cenarios_comparaveis=comparaveis,identidades_preservadas=iguais,resultado=codigo,
        conexoes_diretas_antes=da,conexoes_diretas_depois=db,composicao_antes=composicao(a),composicao_depois=composicao(b),
        novos_diagnosticos=novos,elementos_ausentes=[i for i in ids if i not in eb],
        conclusao='Evidências automáticas; confirmação final depende do engenheiro. Uma fusão de nós exige conferência adicional; o teste de ligação direta procura tubo explícito entre os dois nós.',data_utc=agora())


def salvar_validacao(base,pacote,proposta,resultado,base_posterior=None):
    if proposta['atual']['situacao'] not in ('APLICACAO_INFORMADA','VALIDACAO_PENDENTE','VALIDACAO_FALHOU'):raise ValueError('Informe a aplicação externa antes de confrontar versões')
    if resultado['origem']!=pacote['resultado']['meta']['uid'] or resultado['prop_uid']!=proposta['prop_uid']:raise ValueError('Evidência de validação incompatível com a proposta de origem')
    if base_posterior:resultado=dict(resultado,base_posterior=str(Path(base_posterior).resolve()),sha256_posterior=hash_arquivo(base_posterior))
    preparar_base(base,pacote)
    with conectar(base) as con:
        con.execute('BEGIN IMMEDIATE')
        atual=con.execute('SELECT hist_uid FROM IGD_PROP_HIST WHERE prop_uid=? ORDER BY rowid DESC LIMIT 1',(proposta['prop_uid'],)).fetchone()
        if not atual or atual[0]!=proposta['atual']['hist_uid'] or resultado['hist_uid']!=atual[0]:raise ValueError('Proposta mudou durante a verificação; recarregue')
        con.execute('INSERT INTO IGD_VALIDACOES VALUES(?,?,?,?,?,?)',(resultado['uid'],proposta['prop_uid'],atual[0],resultado['destino'],resultado['data_utc'],texto(resultado)))
    return resultado['uid']


def selecionar_integracao(caminho,parent=None):
    """Reutiliza snapshots; seleção explícita quando há múltiplas integrações."""
    from qgis.PyQt.QtWidgets import QInputDialog
    from .saidas_integracao import reabrir
    with abrir_ro(caminho) as con:vs=con.execute('SELECT ig_uid,data_utc FROM IG_EXECUCOES ORDER BY data_utc DESC').fetchall()
    if not vs:raise ValueError('Arquivo sem execução integrada')
    if len(vs)==1:return reabrir(caminho,vs[0][0])
    nomes=[f'{data} · {uid}' for uid,data in vs]
    nome,ok=QInputDialog.getItem(parent,'Versão integrada','Selecione a versão:',nomes,0,False)
    return reabrir(caminho,vs[nomes.index(nome)][0]) if ok else None


def reconciliar(base,comp_uid,ordem,occ_destino,rev_uid,responsavel,justificativa,evidencia):
    """Vínculo confirmado pelo engenheiro, sem copiar decisão da execução anterior."""
    if not all(t.strip() for t in (responsavel,justificativa,evidencia)):raise ValueError('Reconciliação exige responsável, justificativa e evidência')
    import json
    with conectar(base) as con:
        con.execute('BEGIN IMMEDIATE')
        c=con.execute('SELECT ig_destino,dados FROM IGD_COMPARACOES WHERE comp_uid=?',(comp_uid,)).fetchone()
        r=con.execute('SELECT dados FROM IGD_CORRESPONDENCIAS WHERE comp_uid=? AND ordem=?',(comp_uid,ordem)).fetchone()
        h=con.execute('SELECT ig_uid,occ_uid,modo FROM IGD_REVISOES WHERE rev_uid=?',(rev_uid,)).fetchone()
        if not c or not r or h!=(c[0],occ_destino,json.loads(c[1])['modo']) or occ_destino not in json.loads(r[0])['destinos']:raise ValueError('Correspondência ou revisão de destino incompatível')
        uid=uuid4().hex
        con.execute('INSERT INTO IGD_RECONCILIACOES VALUES(?,?,?,?,?,?,?,?,?)',(uid,comp_uid,ordem,occ_destino,rev_uid,responsavel,justificativa,evidencia,agora()))
        return uid
