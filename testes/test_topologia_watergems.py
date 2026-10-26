"""Contratos sintéticos + reimportação PyQGIS; não substituem WaterGEMS desktop."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree as ET
from test_auditoria_fronteiras import APP
from qgis.core import QgsGeometry
from auditoria_topologica_watergems.arquivos import caminho_seguro,extrair_modelo,hash_arquivo
from auditoria_topologica_watergems.leitura import Banco
from auditoria_topologica_watergems.topologia import analisar,alcancaveis,corresponder
from auditoria_topologica_watergems.espacial import geometrias,candidatos
from auditoria_topologica_watergems.saidas import exportar_json,exportar_xlsx,camadas,exportar_geografico


def elemento(i,tipo='IdahoJunction',familia='NO',wkt=None,**kw):
    e=dict(id=i,uid=f'projeto:{i}',label=f'E-{i}',tipo=tipo,familia=familia,
           excluido=False,ativo=True,topologia={},geometria=None,atributos={},estados={})
    if wkt:e['geometria']=bytes(QgsGeometry.fromWkt(wkt).asWkb())
    e.update(kw);return e


def modelo():
    el={1:elemento(1,wkt='POINT(0 0)'),2:elemento(2,'CheckValve','DISPOSITIVO',wkt='POINT(1 0)',
        topologia={'HMITopologyDownstreamLinkID':11}),3:elemento(3,wkt='POINT(2 0)')}
    for i,a,b,w in [(10,1,2,'LINESTRING(0 0,1 0)'),(11,2,3,'LINESTRING(1 0,2 0)')]:
        el[i]=elemento(i,'IdahoPipe','LINK',wkt=w,topologia={'HMITopologyStartNodeID':a,'HMITopologyStopNodeID':b})
    return dict(elementos=el,projeto='projeto',banco='sintetico',cenario=1,alternativas={'1':[2]},avisos=[])


def criar_banco(p):
    c=sqlite3.connect(p)
    c.executescript('''
    CREATE TABLE HMIScenario(ScenarioID INTEGER,ParentID INTEGER,IsDeleted INTEGER,DomainDataSetID INTEGER);
    INSERT INTO HMIScenario VALUES(1,NULL,0,1),(2,1,0,1);
    CREATE TABLE HMIAlternative(AlternativeID INTEGER,ParentID INTEGER,AlternativeTypeID INTEGER,IsDeleted INTEGER);
    INSERT INTO HMIAlternative VALUES(10,NULL,2,0),(11,10,2,0);
    CREATE TABLE HMIScenarioAlternative(ScenarioID INTEGER,AlternativeTypeID INTEGER,AlternativeID INTEGER);
    INSERT INTO HMIScenarioAlternative VALUES(1,2,10),(2,2,11);
    CREATE TABLE HMIDomainDataSet(DomainDataSetID INTEGER,Guid BLOB,ActiveScenarioID INTEGER);
    INSERT INTO HMIDomainDataSet VALUES(1,X'010203',2);
    CREATE TABLE HMIDomainElement(DomainElementID INTEGER,IsDeleted INTEGER,IsPrototype INTEGER);
    CREATE TABLE HMIModelingElement(ElementID INTEGER,IsDeleted INTEGER,Label TEXT);
    CREATE TABLE BaseLink_HMIDataSetTopology_Data(DomainElementID INTEGER,AlternativeID INTEGER,HMITopologyStartNodeID INTEGER,HMITopologyStopNodeID INTEGER);
    INSERT INTO BaseLink_HMIDataSetTopology_Data VALUES(100,10,1,2),(101,10,2,3),(100,11,1,NULL);
    ''');c.commit();c.close()


class LeituraWatergemsTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name)/'modelo.sqlite';criar_banco(self.p);self.b=Banco(self.p)
    def tearDown(self):self.b.close();self.tmp.cleanup()
    def test_somente_leitura(self):
        with self.assertRaises(sqlite3.OperationalError):self.b.con.execute('DELETE FROM HMIScenario')
    def test_cenario_ativo_rotulo_fallback(self):
        self.assertEqual(self.b.ativo,2);self.assertEqual(self.b.listar_cenarios()[1]['nome'],'2')
    def test_cadeia_cenarios(self):self.assertEqual(list(self.b.cadeia_cenarios(2)),[2,1])
    def test_heranca_alternativas(self):self.assertEqual(list(self.b.cadeia_alternativas(2,2)),[11,10])
    def test_linha_filha_prevalece_nulo_nao_herda(self):
        r=self.b.resolver('BaseLink_HMIDataSetTopology_Data',2,2)
        self.assertIsNone(r[100]['HMITopologyStopNodeID']);self.assertEqual(r[101]['HMITopologyStopNodeID'],3)
    def test_tipo_alternativa_ausente_nao_escolhe_qualquer(self):self.assertEqual(list(self.b.cadeia_alternativas(2,21)),[])
    def test_ciclo_cenario_bloqueado(self):
        self.b.cenarios[1]['ParentID']=2
        with self.assertRaises(ValueError):list(self.b.cadeia_cenarios(2))
    def test_ciclo_alternativa_bloqueado(self):
        self.b.alternativas[10]['ParentID']=11
        with self.assertRaises(ValueError):list(self.b.cadeia_alternativas(2,2))
    def test_cenario_excluido_bloqueado(self):
        self.b.cenarios[2]['IsDeleted']=1
        with self.assertRaises(ValueError):list(self.b.cadeia_cenarios(2))
    def test_tabela_ausente_registra_aviso(self):
        self.assertEqual(self.b.resolver('ausente',2,2),{});self.assertTrue(self.b.avisos)
    def test_esquema_incompativel(self):
        p=Path(self.tmp.name)/'outro.sqlite';sqlite3.connect(p).close()
        with self.assertRaises(ValueError):Banco(p)


class GrafoWatergemsTest(unittest.TestCase):
    def test_componentes_conexoes_estrutura(self):
        a=analisar(modelo());self.assertEqual(a['resumo']['componentes'],1);self.assertEqual(len(a['conexoes']),2)
    def test_retencao_direcional_independe_start_stop(self):
        m=modelo();a=analisar(m,'TODAS_VALVULAS_ABERTAS')
        self.assertIn(3,alcancaveis(a,1));self.assertNotIn(1,alcancaveis(a,3))
        t=m['elementos'][11]['topologia'];t['HMITopologyStartNodeID'],t['HMITopologyStopNodeID']=3,2
        self.assertIn(3,alcancaveis(analisar(m,'TODAS_VALVULAS_ABERTAS'),1))
    def test_valvula_aberta_bidirecional(self):
        m=modelo();m['elementos'][2]['tipo']='TCV';a=analisar(m,'TODAS_VALVULAS_ABERTAS')
        self.assertIn(1,alcancaveis(a,3))
    def test_bomba_nao_habilitada_sem_estado_validado(self):
        m=modelo();m['elementos'][2]['tipo']='StandardPump';a=analisar(m,'TODAS_VALVULAS_ABERTAS')
        self.assertNotIn(3,alcancaveis(a,1));self.assertEqual(a['resumo']['diagnosticos']['BOMBA_ESTADO_INDETERMINADO'],1)
    def test_ativo_falso_nao_reativa(self):
        m=modelo();m['elementos'][11]['ativo']=False;a=analisar(m,'TODAS_VALVULAS_ABERTAS')
        self.assertEqual(len(a['conexoes']),1);self.assertNotIn(3,alcancaveis(a,1))
    def test_ativo_desconhecido_nao_abre(self):
        m=modelo();m['elementos'][2]['ativo']=None
        self.assertIn('ATIVACAO_INDETERMINADA',analisar(m,'TODAS_VALVULAS_ABERTAS')['resumo']['diagnosticos'])
    def test_excluido_nao_entra(self):
        m=modelo();m['elementos'][11]['excluido']=True;self.assertEqual(len(analisar(m)['conexoes']),1)
    def test_jusante_invalido_nao_inventa_passagem(self):
        m=modelo();m['elementos'][2]['topologia']['HMITopologyDownstreamLinkID']=999
        a=analisar(m);self.assertEqual(a['resumo']['diagnosticos']['JUSANTE_INVALIDO'],1)
        self.assertFalse(a['grafo'].has_edge((2,'E'),(2,'S')))
    def test_no_ausente_orfao_e_extremidades(self):
        m=modelo();m['elementos'][10]['topologia']['HMITopologyStartNodeID']=999
        a=analisar(m);self.assertIn('VINCULO_AUSENTE',a['resumo']['diagnosticos']);self.assertIn('NO_ORFAO',a['resumo']['diagnosticos'])
    def test_estados_nao_validados_bloqueados(self):
        with self.assertRaisesRegex(ValueError,'indisponível'):analisar(modelo(),'ESTADOS_DO_CENARIO')
    def test_entrada_integral_preservada(self):
        m=modelo();antes=copy.deepcopy(m);analisar(m);analisar(m,'TODAS_VALVULAS_ABERTAS');self.assertEqual(m,antes)
    def test_consumidor_nao_e_conexao_hidraulica(self):
        m=modelo();m['elementos'][5]=elemento(5,'CustomerNode','CONSUMIDOR');self.assertNotIn((5,'E'),analisar(m)['grafo'])
    def test_correspondencia_explicita_multipla_nula(self):
        m=modelo()
        for i in (10,11):m['elementos'][i]['atributos']={'UDX':{'ID_GIS':'0012'}}
        r=corresponder(m,[{'uid':'a','id':'0012'},{'uid':'b','id':None}],'ID_GIS','id')
        self.assertEqual(r[0]['situacao'],'MULTIPLA');self.assertEqual(r[1]['candidatos'],[])


class EspacialSaidasTest(unittest.TestCase):
    def test_crs_e_unidade_confirmados(self):
        m=modelo()
        with self.assertRaises(ValueError):geometrias(m,'EPSG:4326',1,'teste')
        with self.assertRaises(ValueError):geometrias(m,'EPSG:31983',1,'')
        g,_=geometrias(m,'EPSG:31983',.3048,'Hipótese sintética')
        self.assertAlmostEqual(g[3].asPoint().x(),.6096)
    def test_proximidade_nao_cria_arestas(self):
        m=modelo();g,_=geometrias(m,'EPSG:31983',1,'sintético');a=analisar(m)
        r=candidatos(m,g,3,False);self.assertEqual(len(r),1);self.assertEqual(len(a['conexoes']),2)
    def test_exportar_json_preserva_wkb_ids(self):
        with tempfile.TemporaryDirectory() as p:
            m=modelo();f=exportar_json(m,analisar(m),Path(p)/'a.json');d=json.loads(f.read_text(encoding='utf8'))
            self.assertIn('wkb_hex',d['modelo']['elementos']['1']['geometria'])
            with self.assertRaises(FileExistsError):exportar_json(m,analisar(m),f)
    def test_xlsx_estrutura_filtros_cabecalhos(self):
        with tempfile.TemporaryDirectory() as p:
            m=modelo();f=exportar_xlsx(m,analisar(m),Path(p)/'a.xlsx');ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            with zipfile.ZipFile(f) as z:
                for n in z.namelist():
                    if n.endswith('.xml'):ET.fromstring(z.read(n))
                    if n.startswith('xl/tables/') and n.endswith('.xml'):
                        t=ET.fromstring(z.read(n));self.assertEqual(t.attrib['ref'],t.find('s:autoFilter',ns).attrib['ref'])
                        cols=t.find('s:tableColumns',ns);self.assertEqual(len(cols),len({c.attrib['name'] for c in cols}))
                    if n.startswith('xl/worksheets/sheet') and n.endswith('.xml'):
                        w=ET.fromstring(z.read(n));self.assertIsNotNone(w.find('s:sheetViews/s:sheetView/s:pane',ns))
                        if w.find('s:tableParts',ns) is not None:self.assertIsNone(w.find('s:autoFilter',ns))
    def test_geopackage_e_shp_reimportacao(self):
        # O pool OGR pode manter o GPKG aberto até o fim do processo Windows.
        # A validação dos dados ocorre antes da limpeza, independentemente dela.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as p:
            m=modelo();a=analisar(m);g,_=geometrias(m,'EPSG:31983',1,'sintético');c=camadas(m,a,g,'EPSG:31983')
            for formato in ('GPKG','SHP'):
                r=exportar_geografico(c,Path(p)/formato,formato);self.assertEqual(sum(x['registros'] for x in r[:3]),5)
                self.assertGreaterEqual(len(r),6)
            self.assertTrue((Path(p)/'SHP/WG_TUBULACOES.prj').exists())
    def test_shp_crs_desconhecido_bloqueado(self):
        with tempfile.TemporaryDirectory() as p:
            m=modelo()
            with self.assertRaisesRegex(ValueError,'CRS'):exportar_geografico(camadas(m,analisar(m)),Path(p)/'SHP','SHP')
    def test_zip_seletivo_preserva_original(self):
        with tempfile.TemporaryDirectory() as p:
            p=Path(p);z=p/'a.zip'
            with zipfile.ZipFile(z,'w') as f:
                f.writestr('modelo/a.wtg.sqlite',b'SQLite ficticio');f.writestr('modelo/a.wtg',b'xml');f.writestr('modelo/a.wtg.sqlite.bak',b'backup')
            h=hash_arquivo(z);r=extrair_modelo(z,p/'saida',reserva=0)
            self.assertEqual(len(r['extraidos']),2);self.assertEqual(hash_arquivo(z),h)
            with self.assertRaises(FileExistsError):extrair_modelo(z,p/'saida',reserva=0)
    def test_caminhos_inseguros_bloqueados(self):
        for p in ('../a','C:/a','/tmp/a','p/../../a'):
            with self.subTest(p=p),self.assertRaises(ValueError):caminho_seguro(p)

    def test_interface_publica_resultado_e_preserva_entradas(self):
        from auditoria_topologica_watergems.interface import Janela
        from qgis.core import QgsProject
        j=Janela();m=modelo();a=analisar(m);antes=copy.deepcopy(m)
        try:
            j.publicar(m,a)
            self.assertEqual(m,antes);self.assertTrue(j.exportar.isEnabled())
            self.assertGreaterEqual(len(j.camadas),6);self.assertIn('PENDENTES',j.resumo.toPlainText())
        finally:
            for c in j.camadas:QgsProject.instance().removeMapLayer(c.id())
            j.close()

    def test_interface_nao_oferece_estados_nao_validados(self):
        from auditoria_topologica_watergems.interface import Janela
        j=Janela();self.assertEqual(j.modo.count(),2);self.assertFalse(j.espacial.isChecked());j.close()


if __name__=='__main__':unittest.main()
