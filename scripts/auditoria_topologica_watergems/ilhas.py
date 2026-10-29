"""Alcançabilidade multi-origem e ilhas: evidência topológica, nunca desabastecimento."""
from collections import defaultdict,deque,Counter
from copy import deepcopy
import networkx as nx
from hashlib import sha256
from . import decisoes as db,restricoes_percurso as rp

ALGORITMO='ilhas-1.1'
RESERVATORIOS={'IdahoReservoir'}
TANQUES={'ConventionalTank','IdahoTank'}


def configuracao(c=None):
    c=deepcopy(c or {});c.setdefault('origens','RESERVOIRS');c.setdefault('selecionadas',[]);c.setdefault('incluir_tanks',False);c.setdefault('comparar_restricoes',True);c.setdefault('restricoes',{});c.setdefault('prioridade',{})
    if c['origens'] not in ('RESERVOIRS','RESERVOIRS_TANKS','SELECIONADAS','PERSONALIZADAS'):raise ValueError('Critério de origens inválido')
    if c['origens']=='RESERVOIRS_TANKS' and not c['incluir_tanks']:raise ValueError('Confirme a inclusão de Tanks como hipótese de análise; não são fontes permanentes comprovadas')
    pct=c['prioridade'].get('percentual_alta',1)
    if not isinstance(pct,(int,float)) or not 0<pct<=100:raise ValueError('Percentual de prioridade deve estar entre zero exclusivo e 100')
    for k in ('tubos_alta','comprimento_alta_m'):
        if k in c['prioridade'] and (not isinstance(c['prioridade'][k],(int,float)) or c['prioridade'][k]<=0):raise ValueError('Critério de prioridade deve ser positivo')
    return c


def buscar(g,inicios,dirigido=True,ponto=None):
    vistos=set(inicios);fila=deque(vistos);n=0
    while fila:
        a=fila.popleft();n+=1
        if ponto and n%1024==0:ponto('Buscando alcance multi-origem',n,None)
        vizinhos=g.successors(a) if dirigido else set(g.successors(a))|set(g.predecessors(a))
        for b in vizinhos:
            if b not in vistos:vistos.add(b);fila.append(b)
    return vistos


def origens(p,c,g):
    el=p['topologia']['modelo']['elementos'];achadas=[];usadas=[];avisos=[]
    if c['origens'] in ('RESERVOIRS','RESERVOIRS_TANKS'):
        tipos=RESERVATORIOS|(TANQUES if c['origens']=='RESERVOIRS_TANKS' else set())
        for i,e in sorted(el.items()):
            if e['tipo'] not in tipos or e.get('excluido') is not False:continue
            achadas.append(i)
            if e.get('ativo') is True and (i,'E') in g:usadas.append((i,'E'))
            else:avisos.append(f'{i}: origem não elegível por atividade indeterminada/inativa ou topologia indisponível')
    else:
        from .corredores import resolver_terminal
        for t in c['selecionadas']:
            i=int(t['id']);e=el.get(i);achadas.append(i)
            if not e or t.get('uid')!=e['uid'] or t.get('tipo')!=e['tipo']:raise ValueError('Identidade de origem incompatível: '+str(i))
            if e['tipo'] in TANQUES and not c['incluir_tanks']:raise ValueError('Confirme o Tank selecionado como hipótese de origem')
            usadas.append(resolver_terminal(g,el,t))
            if e.get('ativo') is not True:avisos.append(f'{i}: origem personalizada inativa/indeterminada no cadastro estrutural; não comprova disponibilidade')
    return sorted(set(usadas)),dict(encontradas=len(set(achadas)),utilizadas=len(set(usadas)),avisos=avisos,hipotese_tanks=c['incluir_tanks'])


class Contexto:
    def __init__(self,p,checkpoint=None):
        self.p=p;self.el=p['topologia']['modelo']['elementos'];self.sg=p['topologia']['estrutural']['grafo'];self._comprimentos=None
        h=sha256(db.texto([p['resultado']['meta']['uid'],rp.contexto(p),p['topologia']['modelo'].get('alternativas'),[(l['uid'],l.get('tubos_wg'),l.get('areas'),l.get('correspondencias')) for l in p['resultado'].get('locais',[])]]).encode())
        for n,i in enumerate(sorted(self.el)):
            if checkpoint and n%2048==0:checkpoint('Conferindo identidade dos elementos',n,None)
            h.update(db.texto([i,self.el[i]]).encode())
        for nome in ('estrutural','potencial'):
            g=p['topologia'][nome]['grafo'];h.update(nome.encode())
            for n,(a,b,k) in enumerate(sorted(g.edges(keys=True),key=repr)):
                if checkpoint and n%2048==0:checkpoint('Conferindo assinatura do grafo',n,None)
                h.update(db.texto([a,b,k,g[a][b][k]]).encode())
        self.assinatura_base=h.hexdigest()
        self.wg_gis=defaultdict(set);self.wg_locais=defaultdict(set);self.locais={l['uid']:l for l in p.get('resultado',{}).get('locais',[])};self.comps={}
        for l in self.locais.values():
            for a in l.get('correspondencias',[]):
                if a['situacao']=='INEQUIVOCA' and len(a['candidatos'])==1:
                    i=a['candidatos'][0];self.wg_gis[i].add(a['gis_uid']);self.wg_locais[i].add(l['uid'])
        for modo,k in [('ESTRUTURAL','componentes'),('TODAS_VALVULAS_ABERTAS','componentes_potenciais')]:
            self.comps[modo]=defaultdict(set)
            for co in p.get('resultado',{}).get(k,[]):
                for i in co['nos']+co['tubos']:self.comps[modo][i].add(co['uid'])
    def assinatura(self,c):return db.digest([ALGORITMO,self.assinatura_base,configuracao(c)])
    def comprimentos(self):
        if self._comprimentos is None:
            from .corredores import comprimentos_metricos
            self._comprimentos=comprimentos_metricos(self.p)
        return self._comprimentos


def analisar(p,c=None,contexto=None,progresso=None,cancelado=None):
    c=configuracao(c);ctx=contexto or Contexto(p);el=ctx.el;sg=ctx.sg;assinatura=ctx.assinatura(c)
    def ponto(t,n=None,total=None):
        if cancelado and cancelado():raise InterruptedError('Análise de ilhas cancelada; nada publicado')
        if progresso:progresso(t,n,total)
    ponto('Identificando origens elegíveis');fontes,orig_info=origens(p,c,sg)
    r=dict(algoritmo=ALGORITMO,assinatura=assinatura,config=c,contexto=rp.contexto(p),origens=[dict(id=n[0],porta=n[1],uid=el[n[0]]['uid'],label=el[n[0]].get('label'),tipo=el[n[0]]['tipo']) for n in fontes],origens_info=orig_info,ilhas=[],estado='CONCLUIDO',avisos=[],alcance={},portas_alcancadas={},fora_perspectiva=[],sem_topologia=[],fronteiras=[])
    if not fontes:r.update(estado='SEM_ORIGENS',motivo='Nenhuma origem elegível utilizada: não é possível concluir ausência de caminho. A rede não foi classificada como defeituosa.');return r
    alcance_s=buscar(sg,fontes,False,ponto);r['alcance']['ESTRUTURAL']=sorted({n[0] for n in alcance_s});r['portas_alcancadas']['ESTRUTURAL']=sorted(alcance_s,key=repr);vistas=[]
    # Componentes de portas não alcançáveis; nenhuma busca independente por tubo.
    def grupos(g,alcance,visao,excluir_ids=()):
        excluir_ids=set(excluir_ids);alcance_ids={a[0] for a in alcance};nao={n for n in g if n not in alcance and n[0] not in excluir_ids};h=nx.subgraph_view(g,filter_node=lambda n:n in nao)
        pares={};por_no=defaultdict(list)
        for n,(a,b,d) in enumerate(g.edges(data=True)):
            if n%2048==0:ponto('Agrupando tubulações não alcançáveis',n,None)
            if d.get('natureza')=='TUBULACAO':pares.setdefault(d['elemento'],set()).update((a,b));por_no[a].append(d['elemento']);por_no[b].append(d['elemento'])
        tubos_atribuidos=set()
        for ns in nx.weakly_connected_components(h):
            ids={n[0] for n in ns}-alcance_ids;tubos={i for n in ns for i in por_no[n] if i not in tubos_atribuidos and not any(a in alcance for a in pares[i])}
            tubos_atribuidos.update(tubos);ids.update(tubos)
            if not ids:continue
            vistas.append(dict(visao=visao,portas=sorted(ns,key=repr),membros=sorted(ids),tubos=sorted(tubos)))
        return tubos_atribuidos
    tubos_s=grupos(sg,alcance_s,'ESTRUTURAL');ids_s={i for v in vistas for i in v['membros']}
    if c['comparar_restricoes']:
        ponto('Aplicando Active Topology e restrições da hipótese de válvulas abertas')
        rc=rp.normalizar(p,c['restricoes']);t=rp.grafo_trabalho(p,'TODAS_VALVULAS_ABERTAS',rc,cancelado);g=t['grafo'];r['restricoes']=rc
        for n in fontes:
            if t['regras'].get(n[0])=='BLOQUEAR':raise ValueError('Origem bloqueada pelas restrições: '+str(n[0])+'. Escolha outra origem ou altere explicitamente a regra.')
        efetivas=[n for n in fontes if n in g];r['origens_info']['utilizadas_restrita']=len(efetivas)
        if efetivas:
            alcance_r=buscar(g,efetivas,True,ponto);r['alcance']['RESTRITA']=sorted({n[0] for n in alcance_r});r['portas_alcancadas']['RESTRITA']=sorted(alcance_r,key=repr)
            parciais=defaultdict(set)
            for a in g:parciais[a[0]].add(a in alcance_r)
            r['dispositivos_parcialmente_alcancados']=sorted(i for i,estados in parciais.items() if len(estados)>1 and el[i]['familia']=='DISPOSITIVO')
            # Tubo junto à válvula bloqueada pode estar ligado pela outra ponta.
            # Essas fronteiras são inventariadas, sem chamar o tubo inteiro de ilha.
            bg=p['topologia']['potencial']['grafo'];alca_s_ids={n[0] for n in alcance_s};alca_r_ids=set(r['alcance']['RESTRITA']);pares=defaultdict(set)
            for a,b,d in bg.edges(data=True):
                if d.get('natureza')=='TUBULACAO':pares[d['elemento']].update((a,b))
            fronteiras={i for i,ns in pares.items() if any(n in alcance_r for n in ns) and any(n not in g for n in ns)};r['fronteiras']=sorted(fronteiras)
            usados=grupos(g,alcance_r,'RESTRITA',ids_s)
            # Tubos incidentes a um equipamento removido precisam de seus nós
            # restantes para integrar a ilha, sem unir ramos pelo nó bloqueado.
            grupos_por_porta={tuple(n):v for v in vistas if v['visao']=='RESTRITA' for n in v['portas']}
            for i,ns in pares.items():
                if i in usados or i in tubos_s or i in fronteiras or any(n in alcance_r for n in ns):continue
                vivos={n for n in ns if n in g and n[0] in alca_s_ids}
                if not vivos:continue
                v=next((grupos_por_porta[n] for n in sorted(vivos,key=repr) if n in grupos_por_porta),None)
                if v is None:v=dict(visao='RESTRITA',portas=sorted(vivos,key=repr),membros=[],tubos=[]);vistas.append(v)
                grupos_por_porta.update({n:v for n in vivos})
                v['tubos']=sorted(set(v['tubos'])|{i});v['membros']=sorted(set(v['membros'])|{i}|({n[0] for n in vivos}-alca_r_ids))
            presentes={d['elemento'] for _,_,d in bg.edges(data=True) if d.get('natureza')=='TUBULACAO'};r['fora_perspectiva']=sorted({d['elemento'] for _,_,d in sg.edges(data=True) if d.get('natureza')=='TUBULACAO'}-presentes)
        else:r['avisos'].append('Sem origens disponíveis na hipótese restrita: essa parte da análise é inconclusiva; não foi classificada toda a rede como ilha restrita.')
    resolvidos={d['elemento'] for _,_,d in sg.edges(data=True) if d.get('natureza')=='TUBULACAO'};r['sem_topologia']=sorted(i for i,e in el.items() if e.get('familia')=='LINK' and e.get('excluido') is False and i not in resolvidos)
    comprimentos=ctx.comprimentos();tot=len(resolvidos);areas={a['uid']:a for a in p.get('areas',[])};geoms=p.get('geometrias') or {};espacial=p.get('resultado',{}).get('meta',{}).get('parametros',{}).get('espacial_habilitado',False)
    for n,v in enumerate(sorted(vistas,key=lambda v:(v['visao'],repr(v['membros']))),1):
        ponto('Montando inventário das ilhas',n,len(vistas));ids=set(v['membros']);locs=sorted({l for i in ids for l in ctx.wg_locais[i]});aa=sorted({a for l in locs for a in ctx.locais[l].get('areas',[])})
        ls=[comprimentos.get(i) for i in v['tubos']];compr=sum(ls) if comprimentos and all(a is not None for a in ls) else None;ext=None
        if espacial:
            for i in ids:
                geom=geoms.get(i)
                if geom and not geom.isEmpty():
                    b=geom.boundingBox();lim=[b.xMinimum(),b.yMinimum(),b.xMaximum(),b.yMaximum()];ext=lim if ext is None else [min(ext[0],lim[0]),min(ext[1],lim[1]),max(ext[2],lim[2]),max(ext[3],lim[3])]
        q=len(v['tubos']);alto=q>0 and (q>=c['prioridade'].get('tubos_alta',float('inf')) or compr is not None and compr>=c['prioridade'].get('comprimento_alta_m',float('inf')) or q/max(tot,1)*100>=c['prioridade'].get('percentual_alta',1))
        motivo=('Sem ligação estrutural cadastrada até as origens escolhidas.' if v['visao']=='ESTRUTURAL' else 'Ligação estrutural existe, mas não há alcance dirigido na hipótese com Active Topology e restrições. Não é comprovação de desabastecimento.')
        v.update(uid=db.digest([assinatura,v['visao'],v['portas'],v['tubos']]),nome=f'ILHA {n:04d}',junctions=sum(el[i]['tipo']=='IdahoJunction' for i in ids),dispositivos=sum(el[i]['familia']=='DISPOSITIVO' for i in ids),nos=sum(el[i]['familia']=='NO' for i in ids),comprimento_m=compr,comprimento_unidade='m' if compr is not None else 'INDETERMINADA',customer_meters=None,demanda=None,pendencia_demanda='Relação de consumidores e unidades de demanda não validadas pelo leitor.',extensao=ext,areas=aa,regioes=[areas[a]['exibicao'] for a in aa if a in areas],locais=locs,gis=sorted({u for i in ids for u in ctx.wg_gis[i]}),componentes={m:sorted({u for i in ids for u in ctx.comps[m][i]}) for m in db.MODOS},prioridade='Alta' if alto else 'Média' if q else 'Baixa',criterio_prioridade=f'{q} de {tot} tubulações ({100*q/max(tot,1):.2f}%); limiar relativo {c["prioridade"].get("percentual_alta",1)}%, ou limites absolutos configurados {c["prioridade"]}. Prioridade investigativa, não defeito comprovado.',motivo=motivo)
        r['ilhas'].append(v)
    r['contagens']=dict(ilhas_estruturais=sum(v['visao']=='ESTRUTURAL' for v in r['ilhas']),ilhas_restritas=sum(v['visao']=='RESTRITA' for v in r['ilhas']),tubos_estruturais=sum(len(v['tubos']) for v in r['ilhas'] if v['visao']=='ESTRUTURAL'),tubos_restritos=sum(len(v['tubos']) for v in r['ilhas'] if v['visao']=='RESTRITA'),fronteiras=len(r['fronteiras']),fora_perspectiva=len(r['fora_perspectiva']),sem_topologia=len(r['sem_topologia']),redes_estruturais=sum(v['visao']=='ESTRUTURAL' and bool(v['tubos']) for v in r['ilhas']),grupos_estruturais_sem_tubos=sum(v['visao']=='ESTRUTURAL' and not v['tubos'] for v in r['ilhas']),redes_restritas=sum(v['visao']=='RESTRITA' and bool(v['tubos']) for v in r['ilhas']),grupos_restritos_sem_tubos=sum(v['visao']=='RESTRITA' and not v['tubos'] for v in r['ilhas']))
    return r


def casos(p,r):
    el=p['topologia']['modelo']['elementos'];saida=[]
    for v in r['ilhas']:
        modo='ESTRUTURAL' if v['visao']=='ESTRUTURAL' else 'TODAS_VALVULAS_ABERTAS';evidencias=[v['motivo'],v['criterio_prioridade'],'Origens: '+str(r['origens']),'Hipótese de Tanks: '+str(r['origens_info']['hipotese_tanks'])]
        if len(v['membros'])>200 or len(v['gis'])>200:evidencias.append('O quadro Elementos e vínculos mostra até 200 elementos de cada origem; o inventário e a exportação conservam todos os membros.')
        if v['visao']=='RESTRITA':evidencias.append('Restrições: '+db.texto(r.get('restricoes',{})))
        c=dict(uid=v['uid'],tipo='ILHA',chave=v['uid'],categorias=['SEM_CAMINHO_ATE_ORIGEM'],titulo=v['nome']+' — rede sem caminho até origem',resumo=v['motivo'],wg_ids=v['membros'],gis_uids=v['gis'],area_uids=v['areas'],local_uid=None,regioes=v['regioes'],elementos=[str(el[i].get('label'))+' ['+str(i)+']' for i in v['membros'][:30]]+(['Lista de apresentação limitada a 30; membros completos no inventário/exportação.'] if len(v['membros'])>30 else []),tubos_gis=[],evidencias=evidencias,proxima='Conferir origens, incidências, dispositivos e candidatos. Ausência de caminho não comprova falta de abastecimento.',tecnico=[('Inventário da ilha',db.texto({k:x for k,x in v.items() if k not in ('portas','membros','tubos')}))],componentes=v['componentes'],fontes={m:False for m in db.MODOS},prioridade=v['prioridade'],motivo_prioridade=v['criterio_prioridade'],revisao='SEM_REVISAO_POR_OCORRENCIA',perspectivas={m:dict(texto=v['visao']+' · sem caminho topológico',avisos=[]) for m in db.MODOS},modo_exclusivo=modo,ilha=dict(v,origens_consideradas=r['origens'],restricoes_utilizadas=r.get('restricoes'),analise_uid=r.get('uid'),analise_assinatura=r['assinatura']),analise_ilhas=r['assinatura'],busca=' '.join([v['nome'],v['motivo'],*v['regioes'],*map(str,v['membros'])]).casefold())
        saida.append(c)
    return saida
