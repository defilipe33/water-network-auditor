"""Contexto indexado de atributos/relações; não produz diagnósticos nem arestas."""
from collections import defaultdict
from datetime import date,datetime,timezone
from decimal import Decimal,InvalidOperation
import json,math

AUSENTE=object()
OPERADORES={'numero':('IGUAL','DIFERENTE','MAIOR','MENOR','MAIOR_IGUAL','MENOR_IGUAL','ENTRE','NULO','NAO_NULO'),
 'texto':('IGUAL','DIFERENTE','CONTEM','COMECA','TERMINA','LISTA','NULO','VAZIO'),
 'booleano':('VERDADEIRO','FALSO','NULO'),'data':('ANTES','DEPOIS','ENTRE','NULO'),
 'indeterminado':('NULO','NAO_NULO')}
RELACOES=('RELACIONADO','DENTRO','INTERSECTA','NA_FRONTEIRA','LADOS_DISTINTOS','MESMA_REGIAO','REGIOES_DIFERENTES')

def tipo(v):
    if v is None:return None
    if isinstance(v,bool):return 'booleano'
    if isinstance(v,(int,float,Decimal)):return 'numero'
    if isinstance(v,(datetime,date)):return 'data'
    if isinstance(v,dict) and v.get('tipo') in ('QDate','QDateTime','date','datetime'):return 'data'
    return 'texto' if isinstance(v,str) else None

def folhas(d,prefixo=()):
    for k,v in d.items():
        p=prefixo+(str(k),)
        if isinstance(v,dict) and tipo(v)!='data':yield from folhas(v,p)
        elif tipo(v) is not None or v is None:yield p,v

def valor(d,path):
    for k in path:
        if not isinstance(d,dict) or k not in d:return AUSENTE
        d=d[k]
    return d

def combinar(valores,op):
    valores=list(valores)
    if op=='E':return False if False in valores else None if None in valores else True
    if op=='OU':return True if True in valores else None if None in valores else False
    raise ValueError('Combinação inválida')

def comparar(v,op,x=None,y=None):
    if v is AUSENTE:return None
    if op=='NULO':return v is None
    if op=='NAO_NULO':return v is not None
    if v is None:return None
    if op=='VAZIO':return v=='' if isinstance(v,str) else None
    if op in ('VERDADEIRO','FALSO'):return v is (op=='VERDADEIRO') if isinstance(v,bool) else None
    t=tipo(v)
    try:
        if t=='numero':
            if isinstance(x,bool) or isinstance(y,bool):return None
            a=Decimal(str(v));b=Decimal(str(x))
            if not a.is_finite() or not b.is_finite():return None
            c=Decimal(str(y)) if op=='ENTRE' else None
        elif t=='data':
            def parse(z):
                dt=datetime.fromisoformat(str(z.get('valor')) if isinstance(z,dict) else str(z))
                return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
            a=parse(v);b=parse(x);c=parse(y) if op=='ENTRE' else None
        elif t=='texto':
            if op=='LISTA':return v in x if isinstance(x,list) and all(isinstance(i,str) for i in x) else None
            if not isinstance(x,str):return None
            a,b,c=v,x,y
        else:return None
        if op=='IGUAL':return a==b
        if op=='DIFERENTE':return a!=b
        if op in ('MAIOR','DEPOIS'):return a>b if t in ('numero','data') else None
        if op in ('MENOR','ANTES'):return a<b if t in ('numero','data') else None
        if op=='MAIOR_IGUAL':return a>=b if t=='numero' else None
        if op=='MENOR_IGUAL':return a<=b if t=='numero' else None
        if op=='ENTRE':return b<=a<=c if t in ('numero','data') and b<=c else None
        if op=='CONTEM':return b in a if t=='texto' else None
        if op=='COMECA':return a.startswith(b) if t=='texto' else None
        if op=='TERMINA':return a.endswith(b) if t=='texto' else None
    except (ValueError,TypeError,InvalidOperation,OverflowError):return None
    return None

def quantificar(values,modo):
    values=list(values)
    if not values:return None
    if modo=='TODOS':return combinar(values,'E')
    if modo not in ('QUALQUER','NENHUM'):raise ValueError('Quantificador inválido')
    r=combinar(values,'OU');return None if r is None else not r if modo=='NENHUM' else r

class ContextoFiltros:
    def __init__(self,pacote):
        self.p=pacote;self.ig=pacote['resultado']['meta']['uid'];self.camadas={};self.entidades={};self.areas={};self.relacoes=[];self._relkeys=set();self.locais=defaultdict(lambda:defaultdict(set));self._campos={};self._cache={};self.avisos=[]
        self.tubos={t['uid']:t for t in pacote['dossie']['tubulacoes']};self.elementos=pacote['topologia']['modelo']['elementos'];self._wg={};self._gis={};self._por_area=defaultdict(dict)
        def fonte(chave,origem,nome,natureza):self.camadas.setdefault(chave,dict(chave=chave,origem=origem,nome=nome,natureza=natureza));return chave
        for t in self.tubos.values():
            k=fonte('GIS_REDE:'+t['origem'],'GIS',t['camada'],'Tubulações');self._gis[t['uid']]=dict(uid=t['uid'],camada=k,dados=t['atributos'],proveniencia=dict(origem=t['origem'],execucao=pacote['dossie']['execucao_uid'],natureza='ATRIBUTOS_PRESERVADOS'))
        for i,e in self.elementos.items():
            k=fonte('WG:'+e['tipo'],'WATERGEMS',e['tipo'],'Elementos');data={a:e.get(a) for a in ('id','label','tipo','familia','ativo','excluido','uid','atributos','estados','cadastro_dominio','cadastro_modeling')}
            self._wg[i]=dict(uid=str(i),camada=k,dados=data,proveniencia=dict(execucao=pacote['resultado']['meta']['topologia']['execucao_uid'],cenario=pacote['topologia']['modelo']['cenario'],alternativas=e.get('alternativas',{}),natureza='VALORES_RESOLVIDOS_DO_CENARIO'))
        fontes={f['origem']:f for f in pacote['dossie']['contexto']['fontes']}
        for a in pacote['dossie']['poligonos']:
            u='GEO:'+a['chave'];k=fonte('GIS_AREA:'+a['origem'],'GIS',a['camada'],'Polígonos');self.areas[u]=dict(uid=u,chave=a['chave'],origem=a['origem'],camada=a['camada'],tipo=fontes.get(a['origem'],{}).get('modo',''),exibicao=a.get('nome'),dados=a.get('atributos_originais',{}),execucao=pacote['dossie']['execucao_uid'],crs=pacote['dossie']['contexto']['parametros']['crs'],geometria_wkb=None,fonte_filtro=k)
            self._por_area[k][u]=dict(uid=u,camada=k,dados=a.get('atributos_originais',{}),proveniencia=dict(origem=a['origem'],execucao=pacote['dossie']['execucao_uid'],natureza='POLIGONO_IDENTIFICADO_NO_DOSSIE'))
        elocal=defaultdict(set)
        for v in pacote['dossie']['local_evento']:elocal[v['evento_uid']].add(v['local_uid'])
        self.eventos={v['uid']:v for v in pacote['dossie']['eventos']};self.eventos_local=defaultdict(list)
        for eid,ls in elocal.items():
            for l in ls:self.eventos_local[l].append(self.eventos[eid])
        for r in pacote['dossie']['evento_poligono']:
            uid='GEO:'+r['pol_uid']
            if uid not in self.areas:continue
            for local in elocal.get(r['evento_uid'],()):self._rel(local,uid,r['papel'],r['evento_uid'],'AUDITORIA_GEOMETRICA')
        # Geometrias adicionais já harmonizadas/validadas no pacote integrado.
        from qgis.core import QgsGeometry,QgsSpatialIndex,QgsFeature
        areas_contexto=[];index=QgsSpatialIndex()
        for a in pacote.get('areas',[]):
            u='CTX:'+a['uid'];k=fonte('GIS_AREA_CTX:'+a['origem'],'GIS',a['camada'],'Polígonos de contexto');g=QgsGeometry(a['geometria']);self.areas[u]=dict(uid=u,chave=a['uid'],origem=a['origem'],camada=a['camada'],tipo=a['tipo'],exibicao=a['exibicao'],dados=a.get('atributos_originais',{a['campo_id']:a['id_original'],a['campo_nome']:a['exibicao']}),execucao=self.ig,crs=pacote['resultado']['meta']['parametros']['crs'],geometria_wkb=bytes(g.asWkb()).hex(),fonte_filtro=k)
            self._por_area[k][u]=dict(uid=u,camada=k,dados=self.areas[u]['dados'],proveniencia=dict(origem=a['origem'],execucao=self.ig,natureza='CONTEXTO_ESPACIAL_VALIDADO'))
            f=QgsFeature(len(areas_contexto));f.setGeometry(g);index.addFeature(f);areas_contexto.append((u,g))
        self._contexto_geometrico={u:g for u,g in areas_contexto}
        if pacote['resultado']['meta']['parametros'].get('espacial_habilitado'):
            for l in pacote['resultado']['locais']:
                r=l['registro'];p=QgsGeometry.fromWkt(f"POINT({r['X']} {r['Y']})")
                for i in index.intersects(p.boundingBox()):
                    u,g=areas_contexto[i]
                    if p.intersects(g):
                        self._rel(l['uid'],u,'INTERSECTA',None,'PONTO_LOCAL_EM_CONTEXTO')
                        if p.within(g):self._rel(l['uid'],u,'DENTRO',None,'PONTO_LOCAL_EM_CONTEXTO')
                        elif p.intersects(QgsGeometry(g.constGet().boundary())):self._rel(l['uid'],u,'NA_FRONTEIRA',None,'PONTO_LOCAL_EM_CONTEXTO')
        self._index_locais=QgsSpatialIndex();self._pontos_locais=[]
        for l in pacote['resultado']['locais']:
            rr=l['registro'];g=QgsGeometry.fromWkt(f"POINT({rr['X']} {rr['Y']})");f=QgsFeature(len(self._pontos_locais));f.setGeometry(g);self._index_locais.addFeature(f);self._pontos_locais.append((l['uid'],g))
        self._por_camada=defaultdict(list)
        for e in [*self._gis.values(),*self._wg.values(),*(e for rows in self._por_area.values() for e in rows.values())]:self._por_camada[e['camada']].append(e)
    def _rel(self,local,area,relacao,event,origem):
        key=(local,area,relacao,event,origem)
        if key in self._relkeys:return
        self._relkeys.add(key)
        self.locais[local][area].add(relacao);self.relacoes.append(dict(local=local,area=area,relacao=relacao,evento=event,origem=origem))
    def campos(self,camada):
        if camada not in self._campos:
            fields=defaultdict(set)
            for e in self._por_camada.get(camada,[]):
                for p,v in folhas(e['dados']):
                    fields[p].update([tipo(v)] if tipo(v) else [])
            self._campos[camada]=[dict(caminho=list(p),nome=' · '.join(p),tipo=next(iter(ts)) if len(ts)==1 else 'indeterminado',unidade='Unidade bruta da fonte; não convertida') for p,ts in sorted(fields.items())]
        return self._campos[camada]
    def entidades_caso(self,caso,camada):
        if camada.startswith('GIS_REDE:'):return [self._gis[u] for u in caso['gis_uids'] if u in self._gis and self._gis[u]['camada']==camada]
        if camada.startswith('WG:'):return [self._wg[i] for i in caso['wg_ids'] if i in self._wg and self._wg[i]['camada']==camada]
        rows=self._por_area.get(camada,{})
        return [e for u,e in rows.items() if u in self.locais.get(caso['local_uid'],{}) or u.removeprefix('CTX:') in caso['area_uids']]
    def relacao(self,caso,area,rel):
        if rel=='RELACIONADO':return True
        roles=self.locais.get(caso['local_uid'],{}).get(area,set())
        if rel in ('DENTRO','INTERSECTA','NA_FRONTEIRA'):
            if area in self._contexto_geometrico and self.p['resultado']['meta']['parametros'].get('espacial_habilitado'):
                if caso['local_uid']:return rel in roles
                if rel=='INTERSECTA' and area.removeprefix('CTX:') in caso['area_uids']:return True
                return None
            if rel=='NA_FRONTEIRA' and 'FRONTEIRA' in roles:
                evs=[e for e in self.eventos_local.get(caso['local_uid'],[]) if any('GEO:'+p['chave']==area for p in e['tecnico']['poligonos'])]
                return True if any(e['tecnico']['classificacao'] in ('TRAVESSIA','TANGENCIA','EXTREMIDADE','COINCIDENCIA') for e in evs) else None
            return None
        if area.startswith('CTX:'):return None
        results=[]
        for e in self.eventos_local.get(caso['local_uid'],[]):
            t=e['tecnico'];before={p['chave'] for p in t['regiao_antes']};after={p['chave'] for p in t['regiao_depois']}
            if area.removeprefix('GEO:') not in before|after|{p['chave'] for p in t['poligonos']}:continue
            if not t.get('lado_antes_disponivel') or not t.get('lado_depois_disponivel'):results.append(None);continue
            if len(before)>1 or len(after)>1:results.append(None);continue
            if rel in ('MESMA_REGIAO','REGIOES_DIFERENTES'):
                results.append((before==after if rel=='MESMA_REGIAO' else before!=after) if before and after else None)
            elif rel=='LADOS_DISTINTOS':
                key=area.removeprefix('GEO:');results.append((key in before)!=(key in after) if t['modo']=='TRANSICAO' else None)
        return quantificar(results,'QUALQUER')
    def avaliar(self,caso,condicao,modo='ESTRUTURAL',evidencias=None):
        if not condicao:return True
        if 'condicoes' in condicao:return combinar([self.avaliar(caso,c,modo,evidencias) for c in condicao['condicoes']],condicao.get('operador','E'))
        camada=condicao.get('camada');ents=self.entidades_caso(caso,camada);results=[]
        for e in ents:
            v=valor(e['dados'],condicao['campo']);r=comparar(v,condicao['operador'],condicao.get('valor'),condicao.get('valor2'))
            if camada.startswith('GIS_AREA') and condicao.get('relacao','RELACIONADO')!='RELACIONADO':r=combinar([r,self.relacao(caso,e['uid'],condicao['relacao'])],'E')
            results.append(r)
            if evidencias is not None:evidencias.append(dict(elemento=e['uid'],camada=self.camadas.get(camada),campo=condicao['campo'],valor=None if v is AUSENTE else v,campo_ausente=v is AUSENTE,atende=r,proveniencia=e['proveniencia']))
        return quantificar(results,condicao.get('quantificador','QUALQUER'))
    def filtrar(self,casos,condicao,modo):
        key=(modo,json.dumps(condicao,sort_keys=True,ensure_ascii=False))
        if key not in self._cache:
            if len(self._cache)>=8:self._cache.pop(next(iter(self._cache)))
            self._cache[key]={}
        for c in casos:
            if c['uid'] not in self._cache[key]:self._cache[key][c['uid']]=self.avaliar(c,condicao,modo)
        values=self._cache[key];return [c for c in casos if values.get(c['uid']) is True],sum(values.get(c['uid']) is None for c in casos)

    def _incorporar_geometria(self,area,g):
        from qgis.core import QgsGeometry
        if not self.p['resultado']['meta']['parametros'].get('espacial_habilitado'):raise ValueError('Relações espaciais bloqueadas: referência espacial não validada')
        self._contexto_geometrico[area]=g;self.areas[area]['geometria_wkb']=bytes(g.asWkb()).hex()
        for i in self._index_locais.intersects(g.boundingBox()):
            uid,p=self._pontos_locais[i]
            if p.intersects(g):
                self._rel(uid,area,'INTERSECTA',None,'PONTO_LOCAL_GEOMETRIA_VERIFICADA')
                self._rel(uid,area,'DENTRO' if p.within(g) else 'NA_FRONTEIRA',None,'PONTO_LOCAL_GEOMETRIA_VERIFICADA')
        self._cache.clear()

    def adicionar_poligonos(self,camada):
        if not self.p['resultado']['meta']['parametros'].get('espacial_habilitado'):raise ValueError('Referência espacial não validada: comparação bloqueada')
        from qgis.core import QgsWkbTypes,QgsCoordinateTransform,QgsCoordinateReferenceSystem,QgsProject,QgsGeometry,Qgis
        from auditoria_fronteiras.entradas import digest,valor_python
        from auditoria_fronteiras.visualizacao import _normalizar
        if not camada.isValid() or camada.geometryType()!=QgsWkbTypes.PolygonGeometry or not camada.crs().isValid():raise ValueError('Selecione uma camada poligonal válida com CRS declarado')
        crs=QgsCoordinateReferenceSystem(self.p['resultado']['meta']['parametros']['crs']);tr=QgsCoordinateTransform(camada.crs(),crs,QgsProject.instance().transformContext());origem=digest([camada.providerType(),camada.source()]);assinaturas=[];linhas=[]
        for f in camada.getFeatures():
            attrs={field.name():valor_python(f[field.name()]) for field in camada.fields()};g=QgsGeometry(f.geometry())
            if g.isEmpty() or not g.isGeosValid():self.avisos.append('Polígono vazio/inválido ignorado em '+camada.name());continue
            assinatura=digest([origem,attrs,bytes(g.asWkb()).hex()]);assinaturas.append(assinatura)
            if camada.crs()!=crs and g.transform(tr)!=Qgis.GeometryOperationResult.Success:raise ValueError('Falha na transformação explícita de CRS')
            linhas.append((assinatura,_normalizar(attrs),g))
        if not linhas:raise ValueError('Nenhum polígono válido disponível para filtrar')
        versao=digest(sorted(assinaturas));key='GIS_AREA_REF:'+origem+':'+versao
        if key in self.camadas:return key
        self.camadas[key]=dict(chave=key,origem='GIS',nome=camada.name(),natureza='Polígonos de referência')
        repetidos=defaultdict(int)
        for assinatura,attrs,g in linhas:
            repetidos[assinatura]+=1;uid='REF:'+versao+':'+assinatura+'_'+str(repetidos[assinatura]);self.areas[uid]=dict(uid=uid,chave=assinatura,origem=origem,camada=camada.name(),tipo='POLIGONO_REFERENCIA',exibicao=None,dados=attrs,execucao=self.ig,crs=crs.authid(),crs_origem=camada.crs().toWkt(),geometria_wkb=None,fonte_filtro=key,assinatura_fonte=versao)
            e=dict(uid=uid,camada=key,dados=attrs,proveniencia=dict(origem=origem,execucao=self.ig,natureza='REFERENCIA_GIS_ASSINADA',crs_origem=camada.crs().authid(),crs_comparacao=crs.authid()));self._por_area[key][uid]=e;self._por_camada[key].append(e);self._incorporar_geometria(uid,g)
        self._campos.pop(key,None);return key

    def recuperar_geometrias(self,projeto=None):
        from qgis.core import QgsVectorLayer,QgsProject,QgsCoordinateTransform,QgsCoordinateReferenceSystem,QgsGeometry,Qgis
        from auditoria_fronteiras.entradas import digest,valor_python
        from auditoria_fronteiras.visualizacao import _normalizar
        if not self.p['resultado']['meta']['parametros'].get('espacial_habilitado'):raise ValueError('Referência espacial não validada')
        projeto=projeto or QgsProject.instance();destino=QgsCoordinateReferenceSystem(self.p['resultado']['meta']['parametros']['crs']);n=0
        for fonte in self.p['dossie']['contexto']['fontes']:
            procuradas={a['chave']:u for u,a in self.areas.items() if a['origem']==fonte['origem'] and u.startswith('GEO:')}
            if not procuradas:continue
            c=next((c for c in projeto.mapLayers().values() if c.source()==fonte['fonte'] and c.providerType()==fonte['provedor']),None)
            if c is None:c=QgsVectorLayer(fonte['fonte'],fonte['camada'],fonte['provedor'])
            if not c.isValid() or not c.crs().isValid():self.avisos.append('Fonte de limites indisponível: '+fonte['camada']);continue
            counts=defaultdict(int);pendentes=set(procuradas);tr=QgsCoordinateTransform(c.crs(),destino,projeto.transformContext())
            for f in c.getFeatures():
                attrs={field.name():valor_python(f[field.name()]) for field in c.fields()};sig=digest([fonte['origem'],attrs,bytes(f.geometry().asWkb()).hex()]);counts[sig]+=1;key=sig+'_'+str(counts[sig])
                if key not in procuradas:continue
                g=QgsGeometry(f.geometry())
                if g.isEmpty() or not g.isGeosValid():continue
                if c.crs()!=destino and g.transform(tr)!=Qgis.GeometryOperationResult.Success:continue
                self.areas[procuradas[key]]['dados']=_normalizar(attrs)
                for rows in self._por_area.values():
                    if procuradas[key] in rows:rows[procuradas[key]]['dados']=_normalizar(attrs)
                self._campos.clear();self._incorporar_geometria(procuradas[key],g);pendentes.discard(key);n+=1
            if pendentes:self.avisos.append(f'{len(pendentes)} polígonos não recuperados por assinatura em '+fonte['camada']+'; origem ausente ou alterada')
        return n

    def restaurar_persistidas(self,base):
        from auditoria_fronteiras.versoes import abrir_ro
        from qgis.core import QgsGeometry
        with abrir_ro(base) as c:
            if not c.execute("select 1 from sqlite_master where name='IGD_AREAS_FILTRO'").fetchone():return
            linhas=c.execute('select dados from IGD_AREAS_FILTRO where ig_uid=?',(self.ig,)).fetchall()
            geoms=defaultdict(list)
            for u,crs,wkb,dados in c.execute('select area_uid,crs,wkb,dados from IGD_GEOMETRIAS_FILTRO where ig_uid=?',(self.ig,)):geoms[u].append((crs,wkb,dados))
        for (raw,) in linhas:
            a=json.loads(raw);u=a['uid'];key=a.get('fonte_filtro')
            if not key:continue
            if len(geoms[u])==1:a.update(json.loads(geoms[u][0][2]))
            if u not in self.areas:
                self.areas[u]=a;self.camadas.setdefault(key,dict(chave=key,origem='GIS',nome=a['camada'],natureza='Polígonos preservados'));e=dict(uid=u,camada=key,dados=a['dados'],proveniencia=dict(origem=a['origem'],execucao=a['execucao'],natureza='REFERENCIA_PRESERVADA_DA_EXECUCAO'));self._por_area[key][u]=e;self._por_camada[key].append(e)
            if len(geoms[u])==1:a['crs'],a['geometria_wkb']=geoms[u][0][:2]
            self.areas[u].update(a)
            if u in self._por_area[key]:self._por_area[key][u]['dados']=a['dados']
            if len(geoms[u])>1:self.avisos.append('Geometrias divergentes para a mesma identidade: '+u);a['geometria_wkb']=None
            if a.get('geometria_wkb') and a['crs']==self.p['resultado']['meta']['parametros']['crs']:
                g=QgsGeometry();g.fromWkb(bytes.fromhex(a['geometria_wkb']));self._incorporar_geometria(u,g)
