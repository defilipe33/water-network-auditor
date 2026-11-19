"""Recuperação conservadora de tubos antigos, por fonte + assinatura, sem proximidade."""
from qgis.core import (QgsVectorLayer,QgsVectorLayerFeatureSource,QgsFeatureRequest,QgsExpression,
                       QgsGeometry,QgsCoordinateReferenceSystem,QgsCoordinateTransform,QgsCoordinateTransformContext)
from auditoria_fronteiras.entradas import digest,valor_python


def preparar(dossie,tubos,projeto):
    fontes={f['origem']:f for f in dossie['contexto']['fontes']}
    buscas=[]; avisos=[]; por_origem={}
    for t in tubos:por_origem.setdefault(t['origem'],[]).append(t)
    for origem,refs in por_origem.items():
        f=fontes.get(origem,{})
        cs=[c for c in projeto.mapLayers().values() if isinstance(c,QgsVectorLayer) and c.isValid()
            and c.providerType()==f.get('provedor') and c.source()==f.get('fonte')]
        if len(cs)!=1:
            avisos.append(f.get('camada',origem)+': fonte ausente ou ambígua; geometria da tubulação indisponível.');continue
        c=cs[0]
        if not c.crs().isValid():avisos.append(c.name()+': CRS ausente.');continue
        original=QgsCoordinateReferenceSystem(f.get('crs_origem',''))
        if not original.isValid() or original!=c.crs():
            avisos.append(c.name()+': CRS original indisponível ou alterado; destaque da tubulação bloqueado.');continue
        buscas.append((origem,refs,f,QgsVectorLayerFeatureSource(c),QgsCoordinateReferenceSystem(c.crs())))
    return buscas,avisos,QgsCoordinateTransformContext(projeto.transformContext())


def localizar(preparacao,crs,cancelar=lambda:False):
    buscas,avisos,ctx=preparacao;avisos=list(avisos);encontrados={}
    destino=QgsCoordinateReferenceSystem(crs)
    for origem,refs,fonte,snapshot,origem_crs in buscas:
        campo=fonte.get('campo_id'); nomes=snapshot.fields().names()
        for t in refs:
            req=QgsFeatureRequest().setLimit(1001)
            cond=[]
            if campo in nomes:cond.append(QgsExpression.createFieldEqualityExpression(campo,t['id_bruto']))
            if fonte.get('filtro_modelo_gis'):cond.append(fonte['filtro_modelo_gis'])
            if cond:req.setFilterExpression(' AND '.join('('+e+')' for e in cond))
            candidatos=[];lidas=0
            for f in snapshot.getFeatures(req):
                if cancelar():raise InterruptedError('Destaque cancelado.')
                lidas+=1; attrs={n:valor_python(f[n]) for n in nomes}; bruto=QgsGeometry(f.geometry()); g=QgsGeometry(bruto)
                if origem_crs!=destino:
                    try:
                        if g.transform(QgsCoordinateTransform(origem_crs,destino,ctx))!=0:continue
                    except Exception:continue
                # O adaptador 1.15 assinava cópias no CRS de análise; o legado assinava geometria bruta.
                chave=t['uid'].rsplit('_',1)[0]
                chaves={digest([origem,attrs,bytes(g.asWkb()).hex()])}
                if not fonte.get('filtro_modelo_gis') and not fonte.get('crs_processamento'):
                    chaves.add(digest([origem,attrs,bytes(bruto.asWkb()).hex()]))
                if chave in chaves and not g.isNull() and not g.isEmpty():candidatos.append(bytes(g.asWkb()))
            if lidas<=1000 and len(candidatos)==1:encontrados[t['uid']]=candidatos[0]
            else:avisos.append(t['camada']+' / '+str(t.get('id_exibido'))+': geometria ausente, alterada, ambígua ou busca limitada; nenhuma feição aproximada utilizada.')
    return encontrados,avisos
