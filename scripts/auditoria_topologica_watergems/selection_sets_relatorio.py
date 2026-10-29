"""Relatório de conjuntos pelo renderizador/cartografia já existentes."""
from pathlib import Path
from uuid import uuid4
from . import selection_sets_persistencia as store,decisoes as db


def casos(base,p,ids):
    snapshot=store.ultima(base,p) or {};nomes={r['id']:r['nome'] for r in snapshot.get('itens',[])};saida=[]
    for r in store.atuais(base,p):
        if r['dados']['id'] not in set(ids):continue
        d=r['dados'];membros=[int(v['chave']) for v in r['vinculos']];titulo=' / '.join([nomes.get(i,str(i)) for i in d['ancestrais']]+[d['nome']]);evidencias=['Selection Set cadastral, não diagnóstico hidráulico',d['situacao'],'Hierarquia '+d['hierarquia'],'Modelo '+d['modelo']+' · versão '+r['topo_uid']]
        saida.append(dict(uid=r['obj_uid'],chave=str(d['id']),tipo='SELECTION_SET_WG',titulo=titulo,resumo='Conjunto importado do WaterGEMS: '+str(len(membros))+' membros correspondentes nesta versão. Não implica conectividade ou limites oficiais.',wg_ids=membros,gis_uids=[],area_uids=[],componentes={m:[] for m in db.MODOS},fontes={m:False for m in db.MODOS},perspectivas={m:dict(texto='Composição cadastral',avisos=[]) for m in db.MODOS},evidencias=evidencias,local_uid=None,regioes=[],elementos=[str(v['dados'].get('label'))+' ['+v['chave']+']' for v in r['vinculos'][:30]]+(['Relação completa na exportação de metadados'] if len(membros)>30 else []),tubos_gis=[],prioridade='Baixa',tecnico=[('Definição e metadados',db.texto(d))]))
    return saida


def gerar(base,p,ids,pasta,basemaps=(),config=None,progresso=None,cancelado=None,comparacao=None,comparacao_versoes=None):
    from .relatorio_investigacao import gerar as gerar_existente
    cs=casos(base,p,ids)
    if not cs:raise ValueError('Escolha conjuntos importados para o relatório')
    if comparacao:
        c=dict(cs[0]);c.update(uid=uuid4().hex,chave='COMPARACAO',titulo='Comparação de conjuntos',wg_ids=[],resumo=str(len(comparacao['comuns']))+' elementos comuns; '+str(len(comparacao['somente_a']))+' exclusivos A; '+str(len(comparacao['somente_b']))+' exclusivos B. Sobreposição não é classificada como erro.',elementos=['Tipos: '+str(comparacao['por_tipo'])]);cs.append(c)
    if comparacao_versoes:
        for l in comparacao_versoes['linhas']:
            if l['mudancas'] or l['incluidos'] or l['retirados']:
                c=dict(cs[0]);c.update(uid=uuid4().hex,chave='DIFERENCA:'+str(l['id']),titulo='Mudanças — '+str(l['depois'] or l['antes']),wg_ids=[],resumo=str(l['mudancas'])+'; '+str(len(l['incluidos']))+' membros adicionados / '+str(len(l['retirados']))+' retirados. Não comprova alteração hidráulica.',elementos=[]);cs.append(c)
    cfg=dict(nome='Selection Sets WaterGEMS — mapas de conjuntos',imagens=True,xlsx=True,historico=False,tecnico=False,basemap_modo='NENHUM',escopo='TODOS',preservar_imagens=True);cfg.update(config or {})
    destino=Path(pasta)/('SelectionSets_relatorio_'+uuid4().hex[:10]);return gerar_existente(base,p,cs,'ESTRUTURAL',destino,cfg,basemaps=basemaps,progresso=progresso,cancelado=cancelado)
