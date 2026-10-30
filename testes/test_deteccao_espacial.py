"""Metadados e validação assistida exclusivamente com dados sintéticos."""
import copy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from test_auditoria_fronteiras import APP,camada
from test_topologia_watergems import modelo
from test_usabilidade_crs import registros,REF
from test_bases_plugin import banco_nativo
from qgis.core import QgsProject,QgsCoordinateReferenceSystem,QgsVectorFileWriter,QgsCoordinateTransformContext,QgsGeometry,QgsVectorLayer
from qgis.PyQt.QtGui import QTransform
from auditoria_topologica_watergems import deteccao_espacial as det,referencia_espacial as ref,bases
from auditoria_topologica_watergems.arquivos import hash_arquivo
from auditoria_aplicacao.assistente_espacial import assinatura_gis,Trabalho,AssistenteEspacial
from qgis.PyQt.QtWidgets import QMessageBox

def metadados(crs='EPSG:31983'):return dict(crs=crs,estado='DECLARADO',problemas=[],registros=[],sha256='sintetico')
def topologia(m=None):
    m=m or modelo()
    return dict(modelo=m,meta_base=dict(nome='Modelo sintético',uuid='base-sintetica',assinatura=bases.assinatura_modelo(m,'ESTRUTURAL'),extrator='teste',projeto='Projeto',versao=1))
def comparar(m=None,rs=None,**kw):
    m=m or modelo();return det.comparar_hipoteses(m,rs or registros(m),'EPSG:31983',**kw)

class InterpretacaoTest(unittest.TestCase):
    def test_epsg_explicito(self):self.assertEqual(det.interpretar_crs('EPSG:31983')['crs'],'EPSG:31983')
    def test_json_raiz_horizontal(self):
        j={'horizontalCRS':{'source':'EPSG, V1, 31983 [EPSG]','unit':'Meter','projection':{'zoneNumber':23,'hemisphere':'South'},'datum':{'epsg':6674}}}
        self.assertEqual(det.interpretar_crs(json.dumps(j))['crs'],'EPSG:31983')
    def test_datum_nao_e_epsg_do_crs(self):self.assertIsNone(det.interpretar_crs(json.dumps({'horizontalCRS':{'datum':{'epsg':6674}}})))
    def test_json_epsg_e_source_conflitantes(self):self.assertIsNone(det.interpretar_crs(json.dumps({'horizontalCRS':{'epsg':31983,'source':'32623 [EPSG]'}})))
    def test_projecao_inconsistente(self):
        with self.assertRaises(ValueError):det.interpretar_crs(json.dumps({'horizontalCRS':{'epsg':31983,'projection':{'zoneNumber':22,'hemisphere':'South'}}}))
    def test_nome_sem_definicao_nao_inventa_epsg(self):self.assertIsNone(det.interpretar_crs('UTM do município'))
    def test_crs_geografico_nao_metrico(self):self.assertFalse(det.metro('EPSG:4326'))
    def test_crs_metrico(self):self.assertTrue(det.metro('EPSG:31983'))

class SQLiteMetadadosTest(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name)/'modelo.sqlite'
    def tearDown(self):self.tmp.cleanup()
    def banco(self,valor):
        with closing(sqlite3.connect(self.p)) as c,c:
            c.execute('create table IdahoDataSet(HmiModelCoordinateReference TEXT,HMIDataSetGeometrySpatialReferenceConversionFactor REAL)')
            c.execute('insert into IdahoDataSet values(?,0)',(valor,))
    def test_presente_e_somente_leitura(self):
        self.banco('EPSG:31983');h=hash_arquivo(self.p);r=det.ler_metadados_sqlite(self.p)
        self.assertEqual(r['crs'],'EPSG:31983');self.assertEqual(hash_arquivo(self.p),h);self.assertEqual(r['registros'][0]['tabela'],'IdahoDataSet')
    def test_ausente(self):
        self.banco('');r=det.ler_metadados_sqlite(self.p);self.assertEqual(r['estado'],'PENDENTE');self.assertIn('NÃO IDENTIFICADO',r['mensagem'])
    def test_json_invalido(self):
        self.banco('{não é JSON');self.assertEqual(det.ler_metadados_sqlite(self.p)['estado'],'INCOMPATIVEL')
    def test_fator_zero_nao_comprova_unidade(self):
        self.banco('EPSG:31983');self.assertIsNone(det.ler_metadados_sqlite(self.p)['unidade_bruta'])
    def test_campo_desconhecido_nao_liberado(self):
        with closing(sqlite3.connect(self.p)) as c,c:c.execute('create table Aleatoria(EPSG text)');c.execute("insert into Aleatoria values('EPSG:31983')")
        self.assertIsNone(det.ler_metadados_sqlite(self.p)['crs'])
    def test_cancelamento(self):
        self.banco('EPSG:31983')
        with self.assertRaises(InterruptedError):det.ler_metadados_sqlite(self.p,lambda:True)

class HipotesesTest(unittest.TestCase):
    def test_metros(self):self.assertEqual(comparar()['fator_recomendado'],1)
    def test_pes(self):
        m=modelo();rs=registros(m)
        for e in m['elementos'].values():
            g=QgsGeometry();g.fromWkb(e['geometria']);g.transform(QTransform.fromScale(1/.3048,1/.3048));e['geometria']=bytes(g.asWkb())
        self.assertEqual(comparar(m,rs)['fator_recomendado'],.3048)
    def test_outra_unidade_fundamentada(self):
        m=modelo();rs=registros(m)
        for e in m['elementos'].values():
            g=QgsGeometry();g.fromWkb(e['geometria']);g.transform(QTransform.fromScale(100,100));e['geometria']=bytes(g.asWkb())
        self.assertEqual(comparar(m,rs,fatores=(1,.3048,.01))['fator_recomendado'],.01)
    def test_estatisticas_vertices(self):
        h=comparar()['hipoteses'][0];self.assertEqual(h['vertices_comparados'],4);self.assertEqual(h['maximo_m'],0);self.assertEqual(h['p95_m'],0)
    def test_nao_altera_geometria(self):
        m=modelo();antes=copy.deepcopy(m);comparar(m);self.assertEqual(m,antes)
    def test_sem_pares_inconclusivo(self):
        rs=registros();[r.update(chave_cadastral='inexistente') for r in rs];self.assertIsNone(comparar(rs=rs)['fator_recomendado'])
    def test_ids_repetidos_nao_inequivocos(self):
        rs=registros();rs.append(dict(rs[0],uid='duplicado'));r=comparar(rs=rs);self.assertEqual(r['hipoteses'][0]['compativeis'],1)
    def test_graus_bloqueados(self):
        with self.assertRaises(ValueError):det.comparar_hipoteses(modelo(),registros(),'EPSG:4326')
    def test_cancelamento(self):
        with self.assertRaises(InterruptedError):comparar(cancelar=lambda:True)
    def test_unidade_inconclusiva_em_origem_zero(self):
        m=modelo();rs=registros()
        for e in m['elementos'].values():e['geometria']=bytes(QgsGeometry.fromWkt('LINESTRING(0 0,0 0)').asWkb())
        for r in rs:r['geometria']=QgsGeometry.fromWkt('LINESTRING(0 0,0 0)')
        self.assertIsNone(comparar(m,rs)['fator_recomendado'])
    def test_percentil(self):self.assertEqual(det.percentil([0,10],.95),9.5)

class AvaliacaoTest(unittest.TestCase):
    def setUp(self):self.t=topologia();self.r=comparar(self.t['modelo'])
    def test_metadados_e_vertices_aptos(self):self.assertEqual(det.avaliar(self.t,self.r,metadados())['estado'],'APTO_PARA_CONFIRMACAO')
    def test_so_geometria_nao_comprova_datum(self):self.assertEqual(det.avaliar(self.t,self.r,metadados(None))['estado'],'PENDENTE')
    def test_documental_permite_confirmacao(self):self.assertEqual(det.avaliar(self.t,self.r,metadados(None),'EPSG:31983')['estado'],'APTO_PARA_CONFIRMACAO')
    def test_crs_incompativel(self):self.assertEqual(det.avaliar(self.t,self.r,metadados('EPSG:32623'))['estado'],'INCOMPATIVEL')
    def test_modelo_alterado(self):
        self.t['modelo']['elementos'][10]['label']='outro';self.assertEqual(det.avaliar(self.t,self.r,metadados())['estado'],'INCOMPATIVEL')
    def test_aprovacao_explicita(self):
        self.assertEqual(det.confirmar_assistida(self.t,self.r,metadados(),False,'')['validacao']['estado'],'VALIDADO')
    def test_responsavel_necessario(self):
        self.assertEqual(det.confirmar_assistida(self.t,self.r,metadados())['validacao']['responsavel'],'')
    def test_json_serializavel_contextual(self):
        r=det.confirmar_assistida(self.t,self.r,metadados(),True,'Engenheiro sintético');j=json.loads(bases.texto(r));self.assertEqual(j['validacao']['base_origem'],'base-sintetica');self.assertEqual(j['validacao']['regras'],det.REGRAS)

class JunctionTest(unittest.TestCase):
    def setUp(self):
        self.m=modelo();e=self.m['elementos'][1];e.update(tipo='IdahoJunction',label='J-controle',geometria=bytes(QgsGeometry.fromWkt('POINT(100.003 200.004)').asWkb()))
        self.c=dict(id=1,label='J-controle',x=100,y=200,decimais=2,contexto_modelo=ref.contexto_modelo(self.m),fonte='Observação sintética')
    def test_arredondamento_duas_casas(self):self.assertEqual(det.verificar_junction(self.m,self.c,1)['estado'],'COMPATIVEL')
    def test_fator_errado(self):self.assertEqual(det.verificar_junction(self.m,self.c,.3048)['estado'],'INCOMPATIVEL')
    def test_label_alterado(self):self.c['label']='outro';self.assertEqual(det.verificar_junction(self.m,self.c,1)['estado'],'NAO_ENCONTRADA')
    def test_id_ausente(self):self.c['id']=999;self.assertEqual(det.verificar_junction(self.m,self.c,1)['estado'],'NAO_ENCONTRADA')
    def test_contexto_alterado(self):self.c['contexto_modelo']='outro';self.assertEqual(det.verificar_junction(self.m,self.c,1)['estado'],'CONTEXTO_INCOMPATIVEL')
    def test_precisao_insuficiente(self):self.c['x']=100.01;self.assertEqual(det.verificar_junction(self.m,self.c,1)['estado'],'INCOMPATIVEL')

class FontesGISTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True);self.p=Path(self.tmp.name)/'rede.gpkg';c=camada('LineString',['LINESTRING(0 0,1 0)','LINESTRING(1 0,2 0)'])
        o=QgsVectorFileWriter.SaveVectorOptions();o.driverName='GPKG';o.layerName='rede';QgsVectorFileWriter.writeAsVectorFormatV3(c,str(self.p),QgsCoordinateTransformContext(),o)
        self.d=dict(contexto=dict(fontes=[dict(origem='r',camada='Rede sintética',fonte=str(self.p)+'|layername=rede',provedor='ogr',campo_id='id',crs_origem='EPSG:31983')],parametros=dict(crs='EPSG:31983')))
    def tearDown(self):self.tmp.cleanup()
    def test_crs_geopackage_lido(self):self.assertEqual(det.inventario_gis(self.d)['camadas'][0]['crs'],'EPSG:31983')
    def test_crs_projeto_distinto(self):
        r=det.inventario_gis(self.d,'EPSG:4326');self.assertEqual(r['crs_projeto'],'EPSG:4326');self.assertEqual(r['crs_auditoria'],'EPSG:31983')
    def test_inconsistencia_crs_anterior(self):
        self.d['contexto']['fontes'][0]['crs_origem']='EPSG:32623';self.assertTrue(det.inventario_gis(self.d)['camadas'][0]['inconsistencia'])
    def test_ranking_sem_correspondencia(self):self.assertTrue(all(r['unicas']==0 for r in det.candidatos_campos(self.d,modelo())))
    def test_assinatura_reproduzivel(self):self.assertEqual(assinatura_gis(self.d),assinatura_gis(self.d));self.assertTrue(assinatura_gis(self.d))
    def alterar(self,valores):
        c=QgsVectorLayer(str(self.p)+'|layername=rede','teste','ogr');campo=c.fields().indexFromName('nome')
        self.assertTrue(c.dataProvider().changeAttributeValues({f.id():{campo:v} for f,v in zip(c.getFeatures(),valores)}))
    def test_recomendacao_por_correspondencias(self):
        self.alterar(['E-10','E-11']);r=det.candidatos_campos(self.d,modelo());v=next(v for v in r if v['campo']=='nome');self.assertEqual(v['unicas'],2);self.assertTrue(v['recomendacao'].startswith('RECOMENDADO'))
    def test_repetidos_nao_inequivocos(self):
        self.alterar(['E-10','E-10']);v=next(v for v in det.candidatos_campos(self.d,modelo()) if v['campo']=='nome');self.assertEqual(v['multiplas'],2);self.assertEqual(v['unicas'],0)
    def test_nulo_e_vazio(self):
        self.alterar([None,'']);v=next(v for v in det.candidatos_campos(self.d,modelo()) if v['campo']=='nome');self.assertEqual((v['nulos'],v['vazios']),(1,1))
    def test_zero_textual_com_zeros_esquerda(self):
        self.alterar(['0007','0']);m=modelo();m['elementos'][10]['label']='0007';m['elementos'][11]['label']='0';v=next(v for v in det.candidatos_campos(self.d,m) if v['campo']=='nome');self.assertEqual(v['unicas'],2)
    def test_pipeline_de_reprojecao_registrado(self):
        from auditoria_topologica_watergems.gerenciamento import registros_gis
        rs,_=registros_gis(self.d,{'r':'id'},'EPSG:32623',registrar_operacoes=True)
        self.assertEqual(rs[0]['operacao_crs']['metodo'],'QgsCoordinateTransform');self.assertTrue(rs[0]['operacao_crs']['pipeline'])
    def test_crs_shapefile_prj(self):
        c=QgsVectorLayer(str(self.p)+'|layername=rede','teste','ogr');o=QgsVectorFileWriter.SaveVectorOptions();o.driverName='ESRI Shapefile'
        shp=self.p.with_suffix('.shp');QgsVectorFileWriter.writeAsVectorFormatV3(c,str(shp),QgsCoordinateTransformContext(),o)
        self.assertTrue(shp.with_suffix('.prj').exists());d=copy.deepcopy(self.d);d['contexto']['fontes'][0]['fonte']=str(shp)
        self.assertEqual(det.inventario_gis(d)['camadas'][0]['crs'],'EPSG:31983')

class PersistenciaAssistidaTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True);self.p=Path(self.tmp.name);self.fonte=self.p/'modelo.sqlite';banco_nativo(self.fonte);self.base=bases.criar(self.fonte,self.p/'base.gpkg');self.t=bases.restaurar(self.base)
    def tearDown(self):self.tmp.cleanup()
    def test_metadados_persistidos(self):self.assertIn('metadados_espaciais',self.t['meta_base'])
    def test_metadados_ausentes_ainda_consultavel(self):self.assertEqual(det.metadados_base(self.t)['estado'],'PENDENTE')
    def test_cache_independente_da_fonte_original(self):
        self.t['meta_base']['origem']={};self.assertEqual(det.metadados_base(self.t),self.t['meta_base']['metadados_espaciais'])
    def test_evidencia_json_relacional_reaberta(self):
        r=ref.referencia_reutilizada(self.t['modelo'],dict(modelo=self.t['modelo']['projeto'],contexto=ref.contexto_modelo(self.t['modelo']),referencia=REF,arquivo='sintetico',sha256='sintetico'))
        antes=hash_arquivo(self.base);dest=ref.salvar_referencia(self.base,self.p/'validada.gpkg',r)
        with closing(sqlite3.connect(dest)) as c:
            self.assertFalse(c.execute('pragma foreign_key_check').fetchall());self.assertEqual(c.execute('select base_uuid from WB_EVIDENCIA').fetchone()[0],bases.metadados(dest)['uuid'])
            self.assertEqual(json.loads(c.execute('select dados_json from WB_EVIDENCIA').fetchone()[0])['crs'],REF['crs'])
        self.assertEqual(hash_arquivo(self.base),antes);self.assertEqual(bases.metadados(dest)['anterior'],self.t['meta_base']['uuid'])
        self.assertTrue(list((self.p/'_tecnicos').rglob('EVIDENCIA_REFERENCIA.json')))
    def test_falha_anexo_nao_publica(self):
        r=dict(REF,validacao=dict(estado='VALIDADO',contexto_modelo=ref.contexto_modelo(self.t['modelo']),anexo=dict(arquivo=str(self.p/'ausente'),sha256='nulo')))
        with self.assertRaises(OSError):ref.salvar_referencia(self.base,self.p/'falhou.gpkg',r)
        self.assertFalse((self.p/'falhou.gpkg').exists())

class AssistenteUITest(unittest.TestCase):
    def setUp(self):
        from test_aplicacao_unificada import InterfaceUnificadaTest as _FixtureUI
        self.fixture=_FixtureUI();self.fixture.setUp();self.fixture.carregar();self.fixture.app.bases();self.w=self.fixture.app.wg
        self.w.base='base_sintetica.gpkg'
        with patch.object(AssistenteEspacial,'executar') as iniciar:self.a=AssistenteEspacial(self.w);iniciar.assert_called_once()
        self.a.t=topologia();self.a.metadados=metadados();self.a.evidencias=[];self.a.relatorio=comparar();self.a.relatorio['mapeamento']={};self.a.relatorio['transformacoes_gis']=[];self.a.assinatura=[]
    def tearDown(self):self.a.close();self.fixture.tearDown()
    def test_quatro_etapas(self):self.assertEqual(self.a.paginas.count(),4)
    def test_campos_exigem_confirmacao(self):
        self.a.pagina(1)
        with patch('auditoria_aplicacao.assistente_espacial.QMessageBox.information') as m:self.a.proximo();m.assert_called_once()
        self.assertEqual(self.a.paginas.currentIndex(),1)
    def test_sem_confirmacao_formal(self):self.assertFalse(hasattr(self.a,'aprovar'));self.assertFalse(hasattr(self.a,'responsavel'))
    def test_mudar_crs_invalida_prova(self):self.a.crs.setText('EPSG:32623');self.assertIsNone(self.a.relatorio)
    def test_mudar_tolerancia_invalida_prova(self):self.a.tolerancia.setValue(.02);self.assertIsNone(self.a.relatorio)
    def test_cancelar_nao_muda_base(self):
        antes=self.w.base;self.a.reject();self.assertEqual(self.w.base,antes)
    def test_salvar_sem_aprovacao_cancelado_preserva_base(self):
        with patch('auditoria_aplicacao.assistente_espacial.QMessageBox.warning') as m,patch('auditoria_aplicacao.assistente_espacial.QFileDialog.getSaveFileName',return_value=('','')) as escolher:self.a.salvar();escolher.assert_called_once();m.assert_not_called()
        self.assertIsNone(self.a.resultado)
    def test_estado_apto_nao_e_validado(self):
        self.a.atualizar_avaliacao();self.assertIn('pronto para salvar',self.a.avaliacao.text());self.assertIsNone(self.a.resultado)
    def test_bloqueio_saida_durante_trabalho(self):
        self.w.ocupado=True;self.assertFalse(self.fixture.app.preparar_saida());self.w.ocupado=False
    def test_resolucao_notebook(self):
        from qgis.PyQt.QtCore import QRect
        self.a.show();APP.processEvents();APP._wna_guarda.enquadrar(self.a,area=QRect(0,0,911,480));APP.processEvents();self.assertLessEqual(self.a.height(),424)

if __name__=='__main__':unittest.main()
