"""Camadas próprias persistentes; organização local independente do WaterGEMS."""
from pathlib import Path
from uuid import uuid4
from . import selection_sets_persistencia as store
from . import decisoes as db


def camadas(base,p,pasta,ids,contorno=False,shp=False,progresso=None,cancelado=None):
    from qgis.core import QgsVectorLayer,QgsFeature,QgsField,QgsGeometry,QgsVectorFileWriter,QgsProject,QgsWkbTypes,QgsFillSymbol
    from qgis.PyQt.QtCore import QVariant
    if not p['resultado']['meta']['parametros'].get('espacial_habilitado'):raise ValueError('Valide CRS/unidades da base topológica antes de criar camadas; conjuntos e metadados permanecem disponíveis')
    pasta=Path(pasta);pasta.mkdir(parents=True,exist_ok=True);destino=pasta/('SelectionSets_'+uuid4().hex[:12]+'.gpkg');crs=p['dossie']['contexto']['parametros']['crs'];meta=p['resultado']['meta'];saida=[];omitidos=[];geoms=p.get('geometrias') or {};snapshot=store.ultima(base,p);regs=[r for r in store.atuais(base,p) if r['dados']['id'] in set(ids)]
    try:
        for numero,r in enumerate(regs):
            if cancelado and cancelado():raise InterruptedError('Representação cancelada; camadas anteriores preservadas')
            if progresso:progresso('Preparando '+r['dados']['nome'],numero,len(regs))
            grupos={};gs=[]
            for v in r['vinculos']:
                i=int(v['chave']);g=geoms.get(i)
                if not g or g.isEmpty():omitidos.append(dict(set_id=r['dados']['id'],elemento=i,motivo='SEM_GEOMETRIA_VALIDADA'));continue
                tipo=QgsWkbTypes.geometryType(g.wkbType());grupos.setdefault(tipo,[]).append((v,g));gs.append(g)
            for tipo,ms in grupos.items():
                gt={0:'MultiPoint',1:'MultiLineString',2:'MultiPolygon'}.get(tipo)
                if not gt:continue
                tecnico='SS_'+r['obj_uid'][:12]+'_'+r['uid'][:8]+'_'+str(tipo);l=QgsVectorLayer(gt+'?crs='+crs,tecnico,'memory');pr=l.dataProvider();pr.addAttributes([QgsField(n,t) for n,t in [('DE_ID',QVariant.LongLong),('LABEL',QVariant.String),('TIPO',QVariant.String),('SET_ID',QVariant.String),('SET_NOME',QVariant.String),('OBJ_UID',QVariant.String),('TOPO_UID',QVariant.String)]]);l.updateFields();fs=[]
                for numero_m,(v,g) in enumerate(ms):
                    if numero_m%500==0:
                        if cancelado and cancelado():raise InterruptedError('Representação cancelada')
                        if progresso:progresso('Copiando geometrias validadas',None,None)
                    f=QgsFeature(l.fields());gg=QgsGeometry(g);gg.convertToMultiType();f.setGeometry(gg);f.setAttributes([int(v['chave']),v['dados'].get('label'),v['dados'].get('tipo'),r['dados']['id'],r['dados']['nome'],r['obj_uid'],r['topo_uid']]);fs.append(f)
                pr.addFeatures(fs);l.updateExtents();o=QgsVectorFileWriter.SaveVectorOptions();o.driverName='GPKG';o.layerName=tecnico;o.actionOnExistingFile=QgsVectorFileWriter.CreateOrOverwriteLayer if destino.exists() else QgsVectorFileWriter.CreateOrOverwriteFile
                e=QgsVectorFileWriter.writeAsVectorFormatV3(l,str(destino),QgsProject.instance().transformContext(),o)
                if e[0]!=QgsVectorFileWriter.NoError:raise ValueError('Falha na camada persistente: '+str(e))
                saida.append(dict(tabela=tecnico,nome=r['dados']['nome']+' — '+{0:'nós e dispositivos',1:'tubulações',2:'áreas'}[tipo],set_id=r['dados']['id'],obj_uid=r['obj_uid'],tipo=tipo,quantidade=len(ms)))
            if contorno and gs:
                g=QgsGeometry.unaryUnion(gs).convexHull()
                if QgsWkbTypes.geometryType(g.wkbType())==2:
                    tecnico='ENV_'+r['obj_uid'][:12]+'_'+r['uid'][:8];l=QgsVectorLayer('Polygon?crs='+crs,tecnico,'memory');l.dataProvider().addAttributes([QgsField('METODO',QVariant.String),QgsField('OFICIAL',QVariant.String)]);l.updateFields();f=QgsFeature(l.fields());f.setGeometry(g);f.setAttributes(['CONVEX_HULL','NAO — envolvente derivada, não limite cadastral']);l.dataProvider().addFeatures([f]);o=QgsVectorFileWriter.SaveVectorOptions();o.driverName='GPKG';o.layerName=tecnico;o.actionOnExistingFile=QgsVectorFileWriter.CreateOrOverwriteLayer if destino.exists() else QgsVectorFileWriter.CreateOrOverwriteFile;e=QgsVectorFileWriter.writeAsVectorFormatV3(l,str(destino),QgsProject.instance().transformContext(),o)
                    if e[0]!=QgsVectorFileWriter.NoError:raise ValueError(str(e))
                    saida.append(dict(tabela=tecnico,nome=r['dados']['nome']+' — envolvente APROXIMADA',set_id=r['dados']['id'],obj_uid=r['obj_uid'],tipo=2,quantidade=1))
        if not saida:return dict(base=None,contexto_base=str(base),ig_uid=meta['uid'],topo_uid=meta['topologia']['execucao_uid'],importacao=snapshot,camadas=[],avisos=['Nenhuma geometria validada para os membros escolhidos'])
        manifesto=dict(omitidos=omitidos,contexto_base=str(base),base=str(destino),camadas=saida,importacao=snapshot,ig_uid=meta['uid'],topo_uid=meta['topologia']['execucao_uid']);destino.with_suffix('.json').write_text(db.texto(manifesto),encoding='utf8')
        if shp:
            for c in saida:
                l=QgsVectorLayer(str(destino)+'|layername='+c['tabela'],c['nome'],'ogr');o=QgsVectorFileWriter.SaveVectorOptions();o.driverName='ESRI Shapefile';o.fileEncoding='UTF-8';e=QgsVectorFileWriter.writeAsVectorFormatV3(l,str(pasta/(c['tabela']+'.shp')),QgsProject.instance().transformContext(),o)
                if e[0]!=QgsVectorFileWriter.NoError:raise ValueError('GPKG preservado; falha na cópia SHP: '+str(e))
        return manifesto
    except Exception:
        # Nunca substitui artefatos anteriores. Um arquivo novo incompleto não é
        # carregado como resultado validado; mantenha-o identificado para inspeção.
        if destino.exists():destino.rename(destino.with_suffix('.incompleto.gpkg'))
        raise


def carregar(p,manifesto):
    from qgis.core import QgsProject,QgsVectorLayer,QgsLayerTreeGroup,QgsFillSymbol
    from auditoria_fronteiras.organizacao_camadas import grupo,publicar
    projeto=QgsProject.instance();base=manifesto.get('base')
    contexto_base=manifesto.get('contexto_base') or base
    uid=manifesto['topo_uid'];root=grupo(projeto,'ss',uid,contexto_base,p['resultado']['meta'].get('projeto') or 'Modelo WaterGEMS');itens={r['id']:r for r in manifesto['importacao']['itens']};pastas={}
    for r in sorted((x for x in itens.values() if x['pasta']),key=lambda x:len(x['ancestrais'])):
        if r['hierarquia']!='RECUPERADA':continue
        pai=pastas.get(r.get('pai'),root);g=next((g for g in root.findGroups(True) if g.customProperty('ss/pasta_id')==r['id']),None)
        if g is None:
            g=pai.addGroup(r['nome']);g.setCustomProperty('ss/pasta_id',r['id']);g.setCustomProperty('ss/nome_original',r['nome']);g.setCustomProperty('ss/pai_original',r.get('pai') or 0)
        else:
            if g.name()==g.customProperty('ss/nome_original'):g.setName(r['nome'])
            pai_antigo=g.customProperty('ss/pai_original',0);pai_atual=g.parent().customProperty('ss/pasta_id',0)
            if g.parent()!=pai and pai_antigo==pai_atual:
                copia=g.clone();pai.addChildNode(copia);g.parent().removeChildNode(g);g=copia
            g.setCustomProperty('ss/nome_original',r['nome']);g.setCustomProperty('ss/pai_original',r.get('pai') or 0)
        pastas[r['id']]=g
    resultado=[]
    for c in manifesto['camadas']:
        existentes=[l for l in projeto.mapLayers().values() if l.customProperty('wna/uid')==uid and l.customProperty('wna/tecnico')==c['tabela']]
        if existentes:
            if not existentes[0].isValid():raise ValueError('Camada existente inválida; localize novamente a fonte sem substituição silenciosa')
            resultado.extend(existentes);continue
        l=QgsVectorLayer(base+'|layername='+c['tabela'],c['nome'],'ogr')
        if not l.isValid():raise ValueError('Fonte indisponível: '+base)
        l.setCustomProperty('wna/tecnico',c['tabela']);l=publicar(l,projeto,'ss',uid,contexto_base,p['resultado']['meta'].get('projeto') or 'Modelo WaterGEMS');l.setName(c['nome']);l.setCustomProperty('ss/artefato',base);l.setCustomProperty('ss/set_id',c['set_id']);l.setCustomProperty('ss/obj_uid',c['obj_uid']);l.setCustomProperty('ss/original_pai',itens[c['set_id']].get('pai'))
        pai=pastas.get(itens[c['set_id']].get('pai'),root);node=projeto.layerTreeRoot().findLayer(l.id())
        if node.parent()!=pai:copia=node.clone();pai.addChildNode(copia);node.parent().removeChildNode(node)
        # Cores iniciais distintas; o projeto QGIS conserva as edições posteriores.
        from qgis.PyQt.QtGui import QColor
        if c['tipo']==2:l.renderer().setSymbol(QgsFillSymbol.createSimple({'color':'transparent','outline_style':'dash','outline_color':'200,110,0'}))
        else:l.renderer().symbol().setColor(QColor.fromHsv(int(db.digest(str(c['set_id']))[:8],16)%360,180,190))
        resultado.append(l)
    return resultado
