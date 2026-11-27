"""Regressões dos dois erros de campo e do contrato de exportação da 1.19.1."""

from contextlib import closing
import csv
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from qgis.PyQt.QtCore import QByteArray, QDate, QDateTime, QTime, Qt, QVariant
from qgis.core import QgsCoordinateTransformContext, QgsFeature, QgsGeometry, QgsVectorLayer

from test_modelbuilder_119 import catalogo_sintetico, perfil
from auditoria_aplicacao import cadastro_exportavel as cadastro
from auditoria_aplicacao import conjuntos_modelagem as cm
from auditoria_aplicacao import entradas_grafo_gis as entradas
from auditoria_aplicacao import labels_modelagem as labels
from auditoria_aplicacao import modelbuilder_gis as mb
from auditoria_aplicacao import persistencia_grafo_gis as pg
from auditoria_aplicacao.seletor_multiplos import SeletorMultiplos, opcoes_corredores
from auditoria_aplicacao.validacao_modelbuilder_gis import PendenciasCriticas
from auditoria_aplicacao.valores_exportacao_gis import normalizar


def linhas(pasta,nome):
    with (pasta/nome).open(encoding='utf-8-sig',newline='') as arq:
        return list(csv.DictReader(arq))


def config(**opcoes):
    return dict(perfil=perfil(),escopo='COMPLETO',**opcoes)


class Pacotes(unittest.TestCase):
    def setUp(self):
        f,inv=catalogo_sintetico()
        self.foto,self.inventario=f,inv
        self.previa=cadastro.preparar(f,inv)

    def conjunto(self,p):
        return dict(cm.compor(self.previa,{('PIPE',p['uid'])},nome='Ensaios 1.19.1',
                             categoria='PERSONALIZADOS',origem='MANUAL'),uuid='set-teste')

    def anel(self,p,cruzado=False):
        a=next(n for n in self.previa['nos'] if n['uid']==p['no_a'])
        x,y=a['xy']
        coords=((0,0),(4,4),(4,0),(0,4),(0,0)) if cruzado else ((0,0),(4,0),(4,4),(0,4),(0,0))
        geom=QgsGeometry.fromWkt('LINESTRING('+','.join(f'{x+dx} {y+dy}' for dx,dy in coords)+')')
        p.update(no_b=p['no_a'],wkb=bytes(geom.asWkb()),comprimento_m=geom.length())

    def test_relata_todas_as_pontas_e_geometrias_e_exige_opcao_parcial(self):
        a,b,c,d,ok=self.previa['pipes']
        a['no_a']=None
        b['no_b']='final_ausente'
        c['no_b']=c['no_a']
        d['wkb']=bytes(QgsGeometry.fromWkt('LINESTRING(0 0,0 0)').asWkb())
        s=self.conjunto(a)
        ps,m=cadastro.validar_modelbuilder(self.previa,config(),selecoes=[s])
        self.assertEqual(set(m['excluidos']),{p['uid'] for p in (a,b,c,d)})
        codigos={r['codigo'] for r in ps if r['gravidade']=='CRITICA'}
        self.assertEqual(codigos,{'NO_INICIAL_INDISPONIVEL','NO_FINAL_INDISPONIVEL',
                                  'MESMO_NO_PONTAS_DISTINTAS','GEOMETRIA_INVALIDA'})
        with TemporaryDirectory() as t:
            with self.assertRaises(PendenciasCriticas):
                cadastro.exportar(self.previa,t,'CSV',modelbuilder=config(),selecoes=[s])
            self.assertEqual(list(Path(t).iterdir()),[])
            dst=cadastro.exportar(self.previa,t,'CSV',modelbuilder=config(parcial=True),selecoes=[s])
            meta,regs=mb.ler_pacote(dst)
            self.assertEqual(meta['estado'],'EXPORTACAO_PARCIAL')
            self.assertTrue(meta['incompleto'])
            self.assertEqual([r['uid'] for r in regs if r['tipo']=='PIPE'],[ok['uid']])
            self.assertEqual(linhas(dst,'WNA_ELEMENTO_CONJUNTO.csv')[0]['situacao_participacao'],'EXCLUIDO_EXPORTACAO')
            rel=linhas(dst,'WNA_PENDENCIAS_MODELBUILDER.csv')
            self.assertEqual({r['codigo'] for r in rel if r['gravidade']=='CRITICA'},codigos)
            self.assertTrue(all(r['parte'] and r['solucao'] for r in rel if r['gravidade']=='CRITICA'))

    def test_anel_simples_divide_no_pacote_e_mantem_conjunto_e_identidade(self):
        p=self.previa['pipes'][0]
        self.anel(p)
        anterior=p.copy()
        s=self.conjunto(p)
        ps,_=cadastro.validar_modelbuilder(self.previa,config())
        self.assertIn('ANEL_MESMO_NO',{r.get('codigo') for r in ps})
        with TemporaryDirectory() as t:
            dst=cadastro.exportar(self.previa,t,'CSV',modelbuilder=config(segmentar_aneis=True),selecoes=[s])
            meta,regs=mb.ler_pacote(dst)
            self.assertEqual(meta['aneis_segmentados'],[p['uid']])
            novos=[r for r in linhas(dst,'pipes.csv') if r['segmento_anterior']==p['uid']]
            self.assertEqual(len(novos),2)
            self.assertEqual(p,anterior)
            self.assertAlmostEqual(sum(float(r['comprimento_m']) for r in novos),p['comprimento_m'])
            self.assertEqual({r['original'] for r in novos},{p['original']})
            self.assertEqual({r['elemento_uid'] for r in linhas(dst,'WNA_ELEMENTO_CONJUNTO.csv')},
                             {r['WNA_UID'] for r in novos})
            for r in novos:
                self.assertNotEqual(r['mb_inicio'],r['mb_fim'])
                self.assertEqual({r['mb_inicio'],r['mb_fim']},
                                 {n['label'] for n in regs if n['uid'] in (r['no_a'],r['no_b'])})

    def test_anel_autointersectado_exige_revisao(self):
        p=self.previa['pipes'][0]
        self.anel(p,cruzado=True)
        ps,m=cadastro.validar_modelbuilder(self.previa,config(segmentar_aneis=True))
        self.assertEqual(m['excluidos'],[p['uid']])
        self.assertIn('ANEL_MESMO_NO',{r.get('codigo') for r in ps})
        self.assertFalse(m['aneis_segmentados'])

    def test_leitura_tolerante_preserva_aresta_com_intervalo_invalido_e_no_ausente(self):
        e=self.foto['arestas'][0]
        e.update(fim=2.,a='NO-AUSENTE')
        p=cadastro.preparar(self.foto,self.inventario)
        ps,_=cadastro.validar_modelbuilder(p,config())
        cs={r.get('codigo') for r in ps}
        self.assertTrue({'GEOMETRIA_INVALIDA','NO_INICIAL_INDISPONIVEL'}<=cs)

    def test_campos_reais_de_data_nos_tres_formatos_e_selection_sets(self):
        camada=QgsVectorLayer('LineString?crs=EPSG:31983&field=obra:date&field=visita:datetime&field=hora:time',
                             'Rede com datas','memory')
        f=QgsFeature(camada.fields())
        f.setGeometry(QgsGeometry.fromWkt('LINESTRING(0 0,10 0)'))
        instante=QDateTime(QDate(2026,11,27),QTime(8,10,12),Qt.OffsetFromUTC,-10800)
        f.setAttributes([QDate(2026,11,27),instante,QTime(14,25,33,4)])
        self.assertTrue(camada.dataProvider().addFeatures([f])[0])
        f=next(camada.getFeatures())
        self.assertIsInstance(f['obra'],QDate)
        r=self.previa['cadastro'][0]
        r['atributos_originais'].update(zip(f.fields().names(),f.attributes()))
        r['atributos_originais']['aninhado']=[{'fim':date(2026,11,28),'teste':QVariant()}]
        p=next(p for p in self.previa['pipes'] if p['original']==r['feicao'])
        s=self.conjunto(p)
        with TemporaryDirectory() as t:
            for fmt in ('GPKG','ESRI Shapefile','CSV'):
                op={'modelbuilder':config()} if fmt=='CSV' else {'somente_conjuntos':True}
                dst=cadastro.exportar(self.previa,t,fmt,selecoes=[s],**op)
                dados=next(r for r in linhas(dst,'inventario_cadastral.csv') if r['feicao']==p['original'])
                attrs=json.loads(dados['atributos_originais'])
                self.assertEqual(attrs['obra'],'2026-11-27')
                self.assertIn('2026-11-27T',attrs['visita'])
                self.assertEqual(attrs['hora'],'14:25:33.004')
                self.assertEqual(attrs['aninhado'],[{'fim':'2026-11-28','teste':None}])
                self.assertEqual(len(linhas(dst,'WNA_ELEMENTO_CONJUNTO.csv')),1)
                if fmt=='GPKG':
                    with closing(sqlite3.connect(dst/'cadastro_modelagem.gpkg')) as con:
                        self.assertEqual(con.execute('PRAGMA integrity_check').fetchone(),('ok',))
                        cadastral=con.execute('SELECT dados_json FROM inventario_cadastral WHERE uid=?',(p['parte'],)).fetchone()
                        self.assertEqual(json.loads(cadastral[0])['atributos_originais'],attrs)
                elif fmt=='ESRI Shapefile':
                    self.assertTrue(all((dst/('pipes'+x)).exists() for x in ('.shp','.shx','.dbf','.prj','.cpg')))

    def test_diametro_por_fonte_e_unidade(self):
        fontes=[]
        unidades={}
        for i,(nome,campo,unidade,valor) in enumerate((
            ('metros','diam_m','m',.2),('milimetros','dn','mm',200.),('sem_mapa',None,'mm',200.),
            ('sem_unidade','dn',None,200.),('sem_valor','dn','mm',None),('invalido','dn','mm',-1.),
        )):
            c=QgsVectorLayer(f'LineString?crs=EPSG:31983&field={campo or "dn"}:double',nome,'memory')
            f=QgsFeature(c.fields())
            f.setGeometry(QgsGeometry.fromWkt(f'LINESTRING({i*20} 0,{i*20+10} 0)'))
            f.setAttributes([valor])
            self.assertTrue(c.dataProvider().addFeatures([f])[0])
            fonte=dict(uid=nome,nome=nome,origem_estavel=nome,categoria='PIPE',classificacao='DISTRIBUICAO',
                       filtro='',campos_mapeados={'diametro':campo})
            fontes.append((fonte,c,c.crs()))
            unidades[nome]=unidade
        cache={}
        tubos,*_=entradas.ler((fontes,fontes[0][2],QgsCoordinateTransformContext(),unidades,[]),cadastro=cache)
        self.assertEqual([r['diametro_mm'] for r in tubos],[200.,200.,None,None,None,None])
        self.assertEqual([next(iter(d['diametro']['contagens'])) for d in cache.values()],
                         ['VALIDO','VALIDO','SEM_CAMPO','SEM_UNIDADE','SEM_VALOR','VALOR_INVALIDO'])


class ValoresRotulosSeletores(unittest.TestCase):
    def test_conversao_preserva_tipos_fuso_e_indica_valor_inesperado(self):
        problemas=[]
        dados=normalizar({'n':0,'d':2.5,'b':True,'utc':datetime(2026,11,27,tzinfo=timezone.utc),
            'qt':QDateTime(QDate(2026,11,27),QTime(8,0),Qt.OffsetFromUTC,-10800),
            'binario':QByteArray(b'\xff'),'var':QVariant(QDate(2026,11,27)),'desconhecido':[object()]},problemas,'atributos')
        self.assertEqual((dados['n'],dados['d'],dados['b']),(0,2.5,True))
        self.assertTrue(dados['utc'].endswith('+00:00'))
        self.assertTrue(dados['qt'].endswith('-03:00'))
        self.assertEqual(dados['var'],'2026-11-27')
        self.assertEqual(dados['binario'],{'codificacao':'hex','bytes':'ff'})
        self.assertEqual(dados['desconhecido'],[None])
        self.assertEqual(problemas[0]['campo'],'atributos.desconhecido[0]')

    def test_reserva_persistida_unica_por_identidade_e_compatibilidade_com_1190(self):
        regs=[dict(uid='1',tipo='JUNCTION',label='Centro'),dict(uid='2',tipo='PIPE',label='Igual'),
              dict(uid='3',tipo='PIPE',label='IGUAL'),dict(uid='4',tipo='TANK',label=None)]
        with TemporaryDirectory() as t:
            raiz=Path(t)
            base=raiz/'topo.gpkg'
            pg.criar_complementos(base,'projeto')
            r=labels.reservar(regs,'projeto','execucao1',base=base,gravar=True,prefixos={'PIPE':'TP'})
            self.assertEqual(r,{'1':'Centro','2':'TP-000001','3':'TP-000002','4':'T-000001'})
            self.assertEqual(labels.reservar(regs[::-1],'projeto','execucao2',base=base),r)
            self.assertEqual(labels.reservar(regs[1:2],'projeto','execucao2',base=base),{'2':r['2']})
            self.assertEqual(len(list((raiz/'backups').glob('*.gpkg'))),1)
            with self.assertRaisesRegex(ValueError,'diverge'):
                labels.reservar(regs,'projeto','execucao2',base=base,anteriores={'2':'WNA_legado'})
        novos=labels.reservar(regs,'projeto','execucao1',anteriores={'2':'WNA_legacy','removido':'P-000001'})
        self.assertEqual(novos['2'],'WNA_legacy')
        self.assertEqual(novos['3'],'P-000002')

    def test_seletor_agrupa_ramais_com_evidencia_e_busca_preserva_marcas(self):
        rs=[dict(uid='t',nome='Rio',tipo='TRONCO'),dict(uid='a',nome='Avenida',tipo='RAMAL',pai='t'),
            dict(uid='b',nome='Bairro',tipo='RAMAL',pai='a'),dict(uid='i',nome='Sem classe')]
        d=SeletorMultiplos(None,'Corredores',opcoes_corredores(rs),['t'])
        self.addCleanup(d.deleteLater)
        d.categoria.setCurrentIndex(d.categoria.findData('@RAMAIS'))
        d.alterar('VISIVEIS')
        self.assertEqual(d.selecionados(),['t','a','b'])
        d.alterar('LIMPAR')
        d.busca.setText('Avenida')
        d.alterar('VISIVEIS')
        self.assertEqual(d.selecionados(),['a'])
        d.alterar('INVERTER')
        self.assertEqual(d.selecionados(),['t','b','i'])
        d.alterar('TODOS')
        self.assertEqual(d.selecionados(),['t','a','b','i'])
