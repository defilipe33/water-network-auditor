"""SHP como visão legível, CSVs relacionais e validação por reimportação PyQGIS."""
import csv
import json
from pathlib import Path

from qgis.core import (QgsVectorLayer,QgsFeature,QgsField,QgsGeometry,QgsPointXY,
                       QgsVectorFileWriter,QgsProject,QgsCoordinateReferenceSystem)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt import sip
from .apresentacao import CAMPOS_PRINCIPAIS,ponto_representativo
from .investigacao import CAMPOS_LOCAIS
from .inspecao import restaurar,texto


def _csv(caminho,campos,linhas):
    with Path(caminho).open('x',encoding='utf-8-sig',newline='') as arq:
        escritor=csv.writer(arq,delimiter=';')
        escritor.writerow(campos)
        escritor.writerows(linhas)


def exportar_shp(dossie,pasta):
    """Pasta deve ser nova. Valores DBF longos são sinalizados, nunca truncados."""
    pasta=Path(pasta)
    if pasta.exists():
        raise FileExistsError('Escolha uma subpasta nova para o conjunto SHP')
    if not pasta.parent.is_dir():
        raise ValueError('A pasta de destino não existe')
    resultado,_=restaurar(dossie)
    crs=QgsCoordinateReferenceSystem(resultado.parametros.crs)
    pontos={e.id:ponto_representativo(e)[0] for e in resultado.ocorrencias}
    pasta.mkdir()
    avisos=[]
    verificacoes=[]
    esquemas={}
    for nome,itens,campos,chave in [('EVENTOS_FRONTEIRAS',dossie['eventos'],CAMPOS_PRINCIPAIS,'EVT_UID'),
                                   ('PONTOS_INVESTIGACAO',dossie['locais'],CAMPOS_LOCAIS,'LOC_UID')]:
        camada=QgsVectorLayer('Point',nome,'memory')
        camada.setCrs(crs)
        nomes=['EXE_UID',chave]+list(campos)
        if any(len(n)>10 for n in nomes) or len({n.casefold() for n in nomes})!=len(nomes):
            raise ValueError('Nomes DBF inválidos ou colidentes')
        atributos=[]
        for n in nomes:
            tipo=(QVariant.Double if n in ('X','Y') else
                  QVariant.Int if n in ('ID','N_EVENTOS','N_TUBOS') else QVariant.String)
            largura=24 if tipo==QVariant.Double else 10 if tipo==QVariant.Int else 254
            atributos.append(QgsField(n,tipo,len=largura,
                                      prec=10 if tipo==QVariant.Double else 0))
        camada.dataProvider().addAttributes(atributos)
        camada.updateFields()
        esperados={}
        feicoes=[]
        for item in itens:
            r=item['registro']
            valores=[dossie['execucao_uid'],item['uid']]+[r[c] for c in campos]
            for n,v in enumerate(valores):
                if isinstance(v,str) and len(v.encode('utf-8'))>254:
                    avisos.append(dict(camada=nome,uid=item['uid'],campo=nomes[n],
                                       motivo='Excede 254 bytes DBF; valor integral na tabela ATRIBUTOS_'+nome+'.csv'))
                    valores[n]='[Consultar CSV de atributos]'
            f=QgsFeature(camada.fields())
            f.setAttributes(valores)
            geom=(pontos[item['uid']] if nome=='EVENTOS_FRONTEIRAS' else
                  QgsGeometry.fromPointXY(QgsPointXY(r['X'],r['Y'])))
            f.setGeometry(geom)
            feicoes.append(f)
            esperados[item['uid']]=(valores,QgsGeometry(geom))
        if feicoes and not camada.dataProvider().addFeatures(feicoes)[0]:
            raise RuntimeError('Falha ao preparar Shapefile')
        op=QgsVectorFileWriter.SaveVectorOptions()
        op.driverName='ESRI Shapefile'
        op.fileEncoding='UTF-8'
        op.layerOptions=['RESIZE=NO']
        arquivo=pasta/(nome+'.shp')
        erro=QgsVectorFileWriter.writeAsVectorFormatV3(camada,str(arquivo),QgsProject.instance().transformContext(),op)
        if erro[0]!=QgsVectorFileWriter.NoError:
            raise RuntimeError('Exportação SHP falhou: '+str(erro))
        for ext in ('.shp','.shx','.dbf','.prj','.cpg'):
            if not arquivo.with_suffix(ext).is_file():
                raise RuntimeError('Arquivo auxiliar ausente: '+ext)
        reimportada=QgsVectorLayer(str(arquivo),nome,'ogr')
        if not reimportada.isValid() or reimportada.featureCount()!=len(itens) or reimportada.crs()!=crs:
            raise ValueError('SHP reimportado diverge em contagem ou CRS')
        if reimportada.fields().names()!=nomes:
            raise ValueError('SHP alterou os nomes dos campos')
        for f in reimportada.getFeatures():
            uid=f[chave]
            attrs,geom=esperados[uid]
            if bytes(f.geometry().asWkb())!=bytes(geom.asWkb()):
                raise ValueError('SHP alterou a precisão geométrica')
            for n,valor in enumerate(attrs):
                lido=f[n]
                if nomes[n] in ('X','Y'):
                    if abs(lido-valor)>1e-8:
                        raise ValueError('Coordenada de atributo divergiu')
                elif valor not in ('',None) and lido!=valor:
                    raise ValueError('Valor DBF divergiu: '+nomes[n])
        esquemas[nome]={n:dict(nome_original=n,tipo=reimportada.fields()[k].typeName(),
            largura=reimportada.fields()[k].length(),precisao=reimportada.fields()[k].precision())
            for k,n in enumerate(nomes)}
        reimportada.dataProvider().invalidateConnections(str(arquivo))
        sip.delete(reimportada)  # Libera somente a conexão desta saída no Windows.
        verificacoes.append(dict(camada=nome,registros=len(itens),crs=crs.authid(),
                                 geometria_wkb_identica=True,campos_validos=True))
        _csv(pasta/('ATRIBUTOS_'+nome+'.csv'),['EXE_UID',chave]+list(campos),
             ([dossie['execucao_uid'],i['uid']]+[i['registro'][c] for c in campos] for i in itens))
    tubos={r['uid']:r for r in dossie['tubulacoes']}
    polis={p['chave']:p for p in dossie['poligonos']}
    _csv(pasta/'EVENTO_REDE.csv',['EXE_UID','EVT_UID','TUBO_UID','ORIGEM','CAMADA','ID_REDE','ID_BRUTO','TIPO_ID'],
        ([dossie['execucao_uid'],r['evento_uid'],r['tubo_uid'],tubos[r['tubo_uid']]['origem'],
          tubos[r['tubo_uid']]['camada'],tubos[r['tubo_uid']]['id_exibido'],
          texto(tubos[r['tubo_uid']]['id_bruto']),type(tubos[r['tubo_uid']]['id_bruto']).__name__]
         for r in dossie['evento_rede']))
    _csv(pasta/'LOCAL_EVENTO.csv',['EXE_UID','LOC_UID','EVT_UID'],
         ([dossie['execucao_uid'],r['local_uid'],r['evento_uid']] for r in dossie['local_evento']))
    _csv(pasta/'EVENTO_POLIGONO.csv',['EXE_UID','EVT_UID','POL_UID','PAPEL','ORIGEM','CAMADA','ID_BRUTO'],
         ([dossie['execucao_uid'],r['evento_uid'],r['pol_uid'],r['papel'],polis[r['pol_uid']]['origem'],
           polis[r['pol_uid']]['camada'],texto(polis[r['pol_uid']].get('id_original'))] for r in dossie['evento_poligono']))
    with (pasta/'DOSSIE_TECNICO.json').open('x',encoding='utf-8') as arq:
        arq.write(texto(dossie))
    validacao=dict(formato='SHP',validacoes=verificacoes,avisos=avisos,esquema=esquemas,
        uso='Auditoria espacial. Não são elementos hidráulicos nem intervenções topológicas aprovadas.',
        associacao='CSV UTF-8 separado por ponto e vírgula; importar IDs como texto. Chaves EXE_UID + EVT_UID/LOC_UID/TUBO_UID.',
        limitacoes='DBF não preserva todos os tipos/nulos; consultar JSON bruto e CSVs para atributos completos.')
    from .versoes import metadados_exportacao
    validacao['exportacao']=metadados_exportacao(dossie)
    with (pasta/'DICIONARIO_VALIDACAO.json').open('x',encoding='utf-8') as arq:
        json.dump(validacao,arq,ensure_ascii=False,indent=2)
    return dict(pasta=str(pasta),**validacao)


def validar_gpkg(caminho,dossie):
    from .persistencia import conectar
    resultado,_=restaurar(dossie)
    geometrias={e.id:ponto_representativo(e)[0] for e in resultado.ocorrencias}
    saida=[]
    for nome,itens,chave in [('EVENTOS_FRONTEIRAS',dossie['eventos'],'EVT_UID'),
                              ('PONTOS_INVESTIGACAO',dossie['locais'],'LOC_UID')]:
        camada=QgsVectorLayer(str(caminho)+'|layername='+nome,nome,'ogr')
        if not camada.isValid() or camada.crs()!=QgsCoordinateReferenceSystem(resultado.parametros.crs):
            raise ValueError('Camada GPKG inválida ou CRS divergente')
        feicoes={f[chave]:f for f in camada.getFeatures() if f['EXE_UID']==dossie['execucao_uid']}
        if set(feicoes)!={i['uid'] for i in itens}:
            raise ValueError('IDs ou contagens GPKG divergentes')
        for i in itens:
            r=i['registro']
            geom=(geometrias[i['uid']] if nome=='EVENTOS_FRONTEIRAS' else
                  QgsGeometry.fromPointXY(QgsPointXY(r['X'],r['Y'])))
            f=feicoes[i['uid']]
            if bytes(geom.asWkb())!=bytes(f.geometry().asWkb()):
                raise ValueError('Geometria GPKG divergente')
            from .entradas import valor_python
            for campo,valor in r.items():
                lido=valor_python(f[campo])
                igual=(lido in ('',None)) if valor=='' else lido==valor
                if not igual:
                    raise ValueError('Atributo GPKG divergente: '+campo)
        saida.append(dict(camada=nome,registros=len(itens),geometria_wkb_identica=True))
        camada.dataProvider().invalidateConnections(str(caminho))
        sip.delete(camada)
    with conectar(caminho) as con:
        if con.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Integridade referencial GPKG inválida')
        for tabela,lista in [('LOCAL_EVENTO','local_evento'),('EVENTO_REDE','evento_rede'),('EVENTO_POLIGONO','evento_poligono')]:
            total=con.execute(f'SELECT count(*) FROM {tabela} WHERE exe_uid=?',(dossie['execucao_uid'],)).fetchone()[0]
            if total!=len(dossie[lista]):
                raise ValueError('Relações divergentes: '+tabela)
    return dict(valido=True,camadas=saida,integridade_referencial=True)
