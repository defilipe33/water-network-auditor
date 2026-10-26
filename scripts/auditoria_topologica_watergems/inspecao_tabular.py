"""Projeção tabular sem modificar os diagnósticos, os casos ou suas identidades."""
def elementos_caso(pacote,caso,modo,revisao):
    elementos=pacote['topologia']['modelo']['elementos'];d=pacote['dossie'];r=pacote['resultado']
    tubos={t['uid']:t for t in d['tubulacoes']}
    comps=r['componentes' if modo=='ESTRUTURAL' else 'componentes_potenciais']
    from collections import defaultdict
    mapa=defaultdict(set)
    for c in comps:
        for i in c['tubos']+c['nos']:mapa[i].add(c['numero'])
    def componentes(i):return '; '.join(map(str,sorted(mapa[i]))) or None
    assocs={}
    for local in r['locais']:
        if caso.get('local_uid') and local['uid']!=caso['local_uid']:continue
        for a in local['correspondencias']:assocs[a['gis_uid']]=a
    linhas=[];representados=set()
    for uid in caso['gis_uids']:
        t=tubos.get(uid,{});a=assocs.get(uid,{})
        for i in a.get('candidatos') or [None]:
            e=elementos.get(i,{})
            linhas.append([e.get('tipo','Tubulação GIS'),t.get('id_exibido'),t.get('camada'),e.get('label'),i,componentes(i),a.get('situacao','NAO_ENCONTRADA'),caso['resumo'],revisao,t.get('id_bruto'),uid,e.get('uid')])
            representados.add(i)
    for i in caso['wg_ids']:
        if i in representados:continue
        e=elementos.get(i,{})
        linhas.append([e.get('tipo'),None,None,e.get('label'),i,componentes(i),'TOPOLOGIA_CADASTRADA',caso['resumo'],revisao,None,None,e.get('uid')])
    return linhas
