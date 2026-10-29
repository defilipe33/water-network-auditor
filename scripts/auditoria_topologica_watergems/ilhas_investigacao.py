"""Candidatos, exportação e comparação conservadora de ilhas; não reconecta rede."""
from collections import defaultdict
from uuid import uuid4
from . import decisoes as db


class Candidatos:
    def __init__(self,p,r,visao=None):
        from qgis.core import QgsFeature,QgsSpatialIndex
        self.espacial=bool(p['resultado']['meta']['parametros'].get('espacial_habilitado'))
        from .corredores import comprimentos_metricos
        self.espacial=self.espacial and bool(comprimentos_metricos(p))
        self.p=p;self.r=r;self.index=QgsSpatialIndex();self.refs=[];visao=visao or ('RESTRITA' if 'RESTRITA' in r['alcance'] else 'ESTRUTURAL');self.visao=visao;g=p['topologia']['estrutural']['grafo']
        if visao=='RESTRITA':
            from .restricoes_percurso import grafo_trabalho,normalizar
            g=grafo_trabalho(p,'TODAS_VALVULAS_ABERTAS',normalizar(p,r.get('restricoes',{})))['grafo']
        portas={tuple(n) for n in r['portas_alcancadas'][visao]};ids={d['elemento'] for a,b,d in g.edges(data=True) if d['natureza']=='TUBULACAO' and a in portas and b in portas};self.portas=defaultdict(list);self.diagnosticos=defaultdict(list)
        for n in p['topologia']['estrutural']['grafo']:self.portas[n[0]].append(n)
        for modo in ('estrutural','potencial'):
            for d in p['topologia'][modo].get('diagnosticos',[]):self.diagnosticos[d['id']].append(d)
        for i in sorted(ids) if self.espacial else []:
            geom=(p.get('geometrias') or {}).get(i)
            if geom and not geom.isEmpty():f=QgsFeature(len(self.refs));f.setGeometry(geom);self.index.addFeature(f);self.refs.append((i,geom))
    def procurar(self,ilha,raio=10,limite=200,cancelado=None):
        from qgis.core import QgsGeometry,QgsPointXY
        if raio<=0 or limite<1:raise ValueError('Raio e limite devem ser positivos')
        saida=[];vistos=set();gs=self.p.get('geometrias') or {};el=self.p['topologia']['modelo']['elementos'];membros=set(ilha['membros']);omitidos=0
        def incluir(d):
            nonlocal omitidos
            u=db.digest(d)
            if u in vistos:return
            vistos.add(u);d['uid']=u;d['natureza']='CANDIDATO_A_INVESTIGACAO_NAO_CONEXAO';
            if len(saida)<limite:saida.append(d)
            else:omitidos+=1
        for i in ilha['tubos'] if self.espacial else []:
            if cancelado and cancelado():raise InterruptedError('Busca cancelada')
            g=gs.get(i)
            if not g or g.isEmpty():continue
            partes=g.asMultiPolyline() if g.isMultipart() else [g.asPolyline()]
            for pt in (pt for parte in partes if parte for pt in (parte[0],parte[-1])):
                ponto=QgsGeometry.fromPointXY(QgsPointXY(pt));box=ponto.boundingBox();box.grow(raio)
                for n in self.index.intersects(box):
                    j,outro=self.refs[n]
                    if j in membros:continue
                    d=ponto.distance(outro)
                    if d<=raio:incluir(dict(tipo='PROXIMIDADE_GEOMETRICA',ilha_elemento=i,outro=j,distancia_m=d,x=pt.x(),y=pt.y(),motivo='Extremidade próxima de tubulação ligada a origem; não comprova ligação faltante nem necessidade de conexão'))
        restricoes=self.r.get('restricoes',{});from .restricoes_percurso import resolver_regras
        regras,_=resolver_regras(self.p,restricoes) if restricoes else ({},{})
        sg=self.p['topologia']['estrutural']['grafo'];vizinhos=set()
        for i in membros:
            for n in self.portas[i]:
                vizinhos.update(b[0] for b in sg.successors(n));vizinhos.update(b[0] for b in sg.predecessors(n))
        for i in membros|vizinhos:
            e=el[i];tipo='BLOQUEIO_RESTRICAO' if regras.get(i)=='BLOQUEAR' else 'ELEMENTO_INATIVO' if e.get('ativo') is not True else None
            if tipo:
                geom=gs.get(i);pt=geom.centroid().asPoint() if self.espacial and geom and not geom.isEmpty() else None;incluir(dict(tipo=tipo,ilha_elemento=i,outro=None,distancia_m=None,x=pt.x() if pt else None,y=pt.y() if pt else None,motivo='Evidência de contexto; não é causa única comprovada'))
        for i in membros:
            for d in self.diagnosticos[i]:
                if d['codigo'].startswith('JUSANTE_') or d['codigo']=='VINCULO_AUSENTE':incluir(dict(tipo='REFERENCIA_INCOMPLETA',ilha_elemento=d['id'],outro=d.get('relacionado'),distancia_m=None,x=None,y=None,motivo=d['codigo']))
        return dict(candidatos=saida,omitidos=omitidos,raio_m=raio,espacial_disponivel=self.espacial,interpretacao='Apenas indícios; nenhuma aresta foi criada')


def registro_exportacao(p,r,v):
    from .conjuntos_investigacao import vinculo_wg
    return dict(obj_uid=v['uid'],topo_uid=p['resultado']['meta']['topologia']['execucao_uid'],ig_uid=p['resultado']['meta']['uid'],modo='ESTRUTURAL' if v['visao']=='ESTRUTURAL' else 'TODAS_VALVULAS_ABERTAS',dados=dict(nome=v['nome'],tipo_conjunto='ILHA',ilha=v,analise=r),vinculos=[vinculo_wg(p,i,'MEMBRO_ILHA') for i in v['membros']])


def preparar_exportacao(p,registro):
    m=p['resultado']['meta'];el=p['topologia']['modelo']['elementos'];v=registro['dados']['ilha'];r=registro['dados']['analise']
    if registro['topo_uid']!=m['topologia']['execucao_uid'] or registro['ig_uid']!=m['uid']:raise ValueError('Ilha de outra execução/versão')
    distintos=[]
    for ref in registro['vinculos']:
        i=int(ref['chave']);e=el.get(i)
        if not e or e.get('uid')!=ref['dados'].get('uid') or e.get('excluido') is not False:raise ValueError('Membro incompatível com o modelo selecionado')
        distintos.append(dict(DomainElementID=i,Label=e.get('label'),Tipo=e['tipo'],UID=e['uid'],Modelo=m['topologia'].get('projeto'),Cenario=m['topologia'].get('cenario'),Perspectiva=registro['modo'],Versao=registro['topo_uid'],Conjunto=v['uid'],Origem='MEMBRO_ILHA_'+v['visao'],Correspondencia='IDENTIDADE_TECNICA'))
    from collections import Counter
    return dict(elementos=distintos,percursos=[],contagens=dict(Counter(e['Tipo'] for e in distintos)),avisos=['Conjunto de membros da ilha; não é percurso ordenado nem prova de desabastecimento.'],conjunto=v['uid'],versao=registro['topo_uid'],modo=registro['modo'],restricoes=r.get('restricoes'),comparacao_restricoes=dict(origens=r['origens'],ilha=v['uid'],visao=v['visao']))


def comparar(p0,r0,p1,r1):
    envelope=dict(uid=uuid4().hex,origem=p0['resultado']['meta']['uid'],destino=p1['resultado']['meta']['uid'],data_utc=db.agora(),modo='ESTRUTURAL',natureza='COMPARACAO_ILHAS',analise_origem=r0.get('uid'),analise_destino=r1.get('uid'),assinaturas=[r0['assinatura'],r1['assinatura']])
    if r0['estado']!='CONCLUIDO' or r1['estado']!='CONCLUIDO':return dict(envelope,estado='INCONCLUSIVO',motivo='Uma análise não possui origens suficientes',linhas=[])
    def ident(p,i):
        e=p['topologia']['modelo']['elementos'].get(i,{});return e.get('uid'),e.get('tipo')
    e0=p0['topologia']['modelo']['elementos'];e1=p1['topologia']['modelo']['elementos'];cnt=defaultdict(int)
    for e in e1.values():cnt[e.get('uid'),e.get('tipo')]+=1
    def semantica(r):
        c=dict(r['config']);c.pop('prioridade',None);c['selecionadas']=[{k:t.get(k) for k in ('uid','tipo','porta')} for t in c['selecionadas']];rr=dict(c.get('restricoes',{}))
        for k in ('contexto','perfil','versao_regras'):rr.pop(k,None)
        for k in ('excecoes','estados'):rr[k]=[{a:v for a,v in t.items() if a not in ('id','label','assinatura')} for t in rr.get(k,[])]
        c['restricoes']=rr;return c
    contexto_igual=bool(p0['topologia']['modelo'].get('projeto')) and semantica(r0)==semantica(r1) and p0['topologia']['modelo'].get('projeto')==p1['topologia']['modelo'].get('projeto') and p0['topologia']['modelo'].get('cenario')==p1['topologia']['modelo'].get('cenario') and p0['topologia']['modelo'].get('alternativas')==p1['topologia']['modelo'].get('alternativas')
    def incidencias(p):
        indice=defaultdict(set);elementos=p['topologia']['modelo']['elementos']
        for modo in ('estrutural','potencial'):
            for a,b,d in p['topologia'][modo]['grafo'].edges(data=True):
                rel=(modo,ident(p,a[0]),a[1],ident(p,b[0]),b[1],ident(p,d['elemento']),d.get('natureza'))
                for i in (a[0],b[0],d['elemento']):indice[ident(p,i)].add(rel)
        return {ident(p,i):db.digest([sorted(indice[ident(p,i)],key=repr),e.get('ativo'),e.get('excluido'),e.get('topologia')]) for i,e in elementos.items()}
    inc0,inc1=incidencias(p0),incidencias(p1)
    novos=[(v,{ident(p1,i) for i in v['membros']}) for v in r1['ilhas']];linhas=[];atingidos=set()
    for antigo in r0['ilhas']:
        chaves={ident(p0,i) for i in antigo['membros']};matches=[(v,ns) for v,ns in novos if v['visao']==antigo['visao'] and chaves&ns]
        for v,ns in matches:atingidos.add(v['uid'])
        classe='CORRESPONDENCIA_INCERTA' if not contexto_igual or any(cnt[k]>1 for k in chaves) else 'NAO_OBSERVADA_NA_NOVA_EXECUCAO' if not matches else 'PERMANECE' if len(matches)==1 and chaves==matches[0][1] else 'ALTERADA_COMPOSICAO'
        if classe=='PERMANECE' and any(inc0.get(k)!=inc1.get(k) for k in chaves):classe='REQUER_REAVALIACAO'
        linhas.append(dict(anterior=antigo['uid'],atuais=[v['uid'] for v,ns in matches],classe=classe,tubos_antes=len(antigo['tubos']),tubos_depois=sum(len(v['tubos']) for v,ns in matches),nos_antes=antigo['nos'],nos_depois=sum(v['nos'] for v,ns in matches),interpretacao='Ausência não é correção comprovada; conferir origens, regras e composição'))
    for v,ns in novos:
        if v['uid'] not in atingidos:linhas.append(dict(anterior=None,atuais=[v['uid']],classe='NOVA_ILHA'))
    a0={ident(p0,i) for i in r0['alcance'].get('RESTRITA',r0['alcance']['ESTRUTURAL'])};a1={ident(p1,i) for i in r1['alcance'].get('RESTRITA',r1['alcance']['ESTRUTURAL'])};comuns={ident(p0,i) for i in e0}&{ident(p1,i) for i in e1}
    for l in linhas:l.update(origem=l.get('anterior'),destinos=l['atuais'],reavaliar=l['classe']!='PERMANECE')
    return dict(envelope,estado='COMPARAVEL' if contexto_igual else 'CONTEXTO_DIFERENTE',linhas=linhas,passaram_a_ter_caminho=[list(k) for k in (a1-a0)&comuns],perderam_caminho=[list(k) for k in (a0-a1)&comuns],origens_anteriores=r0['origens'],origens_atuais=r1['origens'],sem_transferencia_automatica_de_revisoes=True)


def registro_alcancaveis(p,r,visao='RESTRITA'):
    if visao not in r['alcance']:raise ValueError('Alcance não concluído para esta perspectiva')
    modo='ESTRUTURAL' if visao=='ESTRUTURAL' else 'TODAS_VALVULAS_ABERTAS';g=p['topologia']['estrutural' if modo=='ESTRUTURAL' else 'potencial']['grafo']
    if modo!='ESTRUTURAL':
        from .restricoes_percurso import normalizar,grafo_trabalho
        g=grafo_trabalho(p,modo,normalizar(p,r.get('restricoes',{})))['grafo']
    portas={tuple(n) for n in r['portas_alcancadas'][visao]};ids={n[0] for n in portas};ids.update(d['elemento'] for a,b,d in g.edges(data=True) if a in portas and b in portas and d['natureza']=='TUBULACAO')
    v=dict(uid=db.digest([r['assinatura'],'ALCANCAVEIS',visao]),nome='Elementos alcançáveis — '+visao,visao=visao,membros=sorted(ids));return registro_exportacao(p,r,v)
