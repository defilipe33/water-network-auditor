"""Importação atômica reutilizando IGD_OBJETOS e seu histórico versionado."""
from pathlib import Path
from uuid import uuid5,NAMESPACE_URL,uuid4
from . import conjuntos_investigacao as obj,decisoes as db
from .selection_sets import comparar


def identidade(p,modelo,id):return uuid5(NAMESPACE_URL,'WNA:SS:'+p['resultado']['meta']['uid']+':'+modelo+':'+str(id)).hex


def atuais(base,p):return obj.atuais(base,p,'SELECTION_SET_WG')


def ultima(base,p):
    rs=obj.atuais(base,p,'IMPORTACAO_SELECTION_WG');return rs[-1]['dados'] if rs else None


def importar(base,p,leitura,selecionados,cancelado=None):
    from .selection_sets import preparar
    leitura=preparar(p,leitura);selecionados=set(selecionados);obj.preparar(base,p);ig=p['resultado']['meta']['uid'];uid=identidade(p,leitura['modelo'],'IMPORTACAO')
    anteriores={r['obj_uid']:r for r in obj.atuais(base,p,'SELECTION_SET_WG',True)};cabecalhos=obj.historico(base,p);
    with db.abrir_ro(base) as c:esperadas={r[0] for r in c.execute('SELECT uid FROM IGD_OBJ_HIST')}
    anterior=ultima(base,p)
    if anterior:
        if leitura.get('regra')=='lista-csv-1':leitura['itens']=[r for r in anterior['itens'] if r['id'] not in {x['id'] for x in leitura['itens']}]+leitura['itens']
        else:leitura['itens']+= [r for r in anterior['itens'] if r.get('definicao',{}).get('origem')=='CSV_EXTERNO' and r['id'] not in {x['id'] for x in leitura['itens']}]
    if anterior and anterior.get('assinatura')==leitura['assinatura'] and selecionados<=set(anterior.get('selecionados',[])):return anterior
    tmp=Path(base).with_name(Path(base).stem+'_ss_trabalho_'+uuid4().hex+'.gpkg')
    try:
        db.exportar_gpkg(tmp,p['dossie'],base_origem=base)
        presentes={r['id'] for r in leitura['itens']};novos=[]
        for r in leitura['itens']:
            if cancelado and cancelado():raise InterruptedError('Importação cancelada; investigação anterior preservada')
            u=identidade(p,leitura['modelo'],r['id']);old=anteriores.get(u)
            if r['pasta'] or r['id'] not in selecionados:continue
            dados=dict(r,modelo=leitura['modelo'],assinatura_fonte=leitura['assinatura'],cenario=leitura['cenario'],alternativas=leitura['alternativas'],topo_uid=leitura['topo_uid'],data_importacao=leitura['data'],apresentacao_local=(old or {}).get('dados',{}).get('apresentacao_local'))
            vs=[obj.vinculo_wg(p,m['id'],'SELECTION_SET_WATERGEMS') for m in r['membros'] if m['situacao']=='CORRESPONDENCIA_VALIDA' and r['situacao']=='MEMBROS_EXPLICITOS']
            obj.salvar(tmp,p,'SELECTION_SET_WG',dados,vs,uid=u,esperada=old['uid'] if old else None);novos.append(r['id'])
        for u,old in anteriores.items():
            if old['dados']['modelo']==leitura['modelo'] and old['dados']['id'] not in presentes and not old['excluido']:obj.salvar(tmp,p,'SELECTION_SET_WG',dict(old['dados'],removido_na_fonte=leitura['assinatura']),old['vinculos'],uid=u,esperada=old['uid'],excluido=True)
        heads=obj.atuais(tmp,p,'IMPORTACAO_SELECTION_WG');old=next((r for r in heads if r['obj_uid']==uid),None)
        snapshot=dict(leitura,apresentacoes=(anterior or {}).get('apresentacoes',[]),nome='Importação Selection Sets',selecionados=sorted(set(novos)|set((anterior or {}).get('selecionados',[])),key=str))
        if anterior:snapshot['comparacao']=comparar(anterior,leitura)
        obj.salvar(tmp,p,'IMPORTACAO_SELECTION_WG',snapshot,uid=uid,esperada=old['uid'] if old else None)
        with db.abrir_ro(tmp) as c:
            if c.execute('PRAGMA quick_check').fetchone()[0]!='ok' or c.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Importação temporária não íntegra; destino preservado')
        if cancelado and cancelado():raise InterruptedError('Importação cancelada antes da publicação')
        with db.conectar(base) as c:
            c.execute('BEGIN IMMEDIATE')
            if {r[0] for r in c.execute('SELECT uid FROM IGD_OBJ_HIST')}!=esperadas:raise ValueError('Outra sessão alterou os objetos; recarregue antes de importar')
            c.execute('ATTACH DATABASE ? AS ss_importacao',(str(tmp),))
            for tabela,chave in [('IGD_OBJETOS','uid'),('IGD_OBJ_HIST','uid')]:c.execute(f'INSERT INTO {tabela} SELECT r.* FROM ss_importacao.{tabela} r WHERE NOT EXISTS(SELECT 1 FROM main.{tabela} m WHERE m.{chave}=r.{chave})')
            c.execute('INSERT INTO IGD_OBJ_VINCULOS SELECT r.* FROM ss_importacao.IGD_OBJ_VINCULOS r WHERE NOT EXISTS(SELECT 1 FROM main.IGD_OBJ_VINCULOS m WHERE m.hist_uid=r.hist_uid AND m.ordem=r.ordem)')
            if c.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Relações inconsistentes; transação revertida')
        return snapshot
    finally:
        if tmp.exists():tmp.unlink()


def escopo(base,p,ids):
    return {int(v['chave']) for r in atuais(base,p) if r['dados']['id'] in set(ids) for v in r['vinculos'] if v['origem']=='WG'}


def comparar_conjuntos(registros_a,registros_b):
    from collections import Counter
    def refs(rs):return {(v['dados']['uid'],v['dados']['tipo']) for r in rs for v in r['vinculos'] if v['origem']=='WG'}
    a=refs(registros_a);b=refs(registros_b)
    return dict(comuns=sorted(a&b),somente_a=sorted(a-b),somente_b=sorted(b-a),por_tipo=dict(Counter(t for u,t in a|b)),interpretacao='Sobreposição de seleções; não é erro hidráulico')


def comparar_versoes(fonte,p0,destino,p1):
    from uuid import uuid4
    from .comparacao_decisoes import salvar_comparacao
    a=ultima(fonte,p0);b=ultima(destino,p1)
    if not a or not b:raise ValueError('As duas investigações devem conter uma importação persistida')
    r=comparar(a,b);linhas=[]
    for l in r['linhas']:
        alterado=bool(l['mudancas'] or l['incluidos'] or l['retirados'] or not l['composicao_verificada']);linhas.append(dict(l,origem='SS:'+str(l['id']) if l['antes'] is not None else None,destinos=['SS:'+str(l['id'])] if l['depois'] is not None else [],classe='SELECTION_SET_ALTERADO' if alterado else 'PERMANECE',reavaliar=alterado))
    r.update(uid=uuid4().hex,origem=p0['resultado']['meta']['uid'],destino=p1['resultado']['meta']['uid'],modo='ESTRUTURAL',data_utc=db.agora(),natureza='COMPARACAO_SELECTION_SETS',linhas=linhas,cenarios_comparaveis=a.get('cenario')==b.get('cenario') and a.get('alternativas')==b.get('alternativas'))
    salvar_comparacao(destino,p1,r,fonte);return r
