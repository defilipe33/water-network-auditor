"""Camada de apresentação não altera os resultados e mantém a reabertura legada."""
import copy
import unittest
from unittest.mock import patch
import test_integracao_investigativa as fixture
from test_auditoria_fronteiras import APP
from qgis.core import QgsProject,QgsCoordinateReferenceSystem
from qgis.gui import QgsMapCanvas
from auditoria_topologica_watergems.diagnosticos import catalogar,filtrar,contagens,MODOS
from auditoria_topologica_watergems.saidas_integracao import salvar_gpkg,reabrir
from auditoria_topologica_watergems.painel_diagnosticos import abrir_diagnosticos
from auditoria_topologica_watergems.arquivos import hash_arquivo


class DiagnosticosTest(unittest.TestCase):
    def setUp(self):
        self.fixture=fixture.IntegracaoPersistidaTest();self.fixture.setUp()
        self.p=self.fixture.executar();self.base=salvar_gpkg(self.p,self.fixture.p/'integrada.gpkg');self.janelas=[]
    def tearDown(self):
        for j in self.janelas:j.close()
        self.fixture.tearDown()
    def painel(self,canvas=None):
        j=abrir_diagnosticos(self.p,self.base,canvas=canvas);self.janelas.append(j);APP.processEvents();return j
    def test_catalogo_deterministico_sem_mutacao(self):
        r=copy.deepcopy(self.p['resultado']);a=catalogar(self.p);b=catalogar(self.p)
        self.assertEqual(a,b);self.assertEqual(r,self.p['resultado']);self.assertEqual(len(a),len({c['uid'] for c in a}))
    def test_filtro_tipo(self):
        for c in filtrar(catalogar(self.p),categoria='PEQUENO'):self.assertIn('PEQUENO',c['categorias'])
    def test_filtro_textual_preserva_ids_e_origens(self):
        cs=catalogar(self.p);self.assertTrue(filtrar(cs,elemento='10'))
        self.assertFalse(filtrar(cs,elemento='inexistente-total'))
    def test_filtro_componente_regiao_prioridade_fonte(self):
        cs=catalogar(self.p);c=cs[0];u=c['componentes'][MODOS[0]][0]
        self.assertIn(c,filtrar(cs,componente=u,prioridade=c['prioridade'],fonte=c['fontes'][MODOS[0]]))
        self.assertFalse(filtrar(cs,regiao='Não existe'))
    def test_contagens_unicas_e_tags_nao_aditivas(self):
        cs=catalogar(self.p);r=contagens(cs);self.assertEqual(r['total'],len(cs));self.assertGreaterEqual(sum(r['categorias'].values()),len(cs))
    def test_hipotese_indisponivel(self):
        j=self.painel();self.assertFalse(j.modo.model().item(2).isEnabled());j.modo.setCurrentIndex(1);self.assertEqual(j.modo.currentData(),MODOS[1])
    def test_detalhamento_tecnico_recolhido(self):
        j=self.painel();itens=[j.detalhes.topLevelItem(i) for i in range(j.detalhes.topLevelItemCount())]
        t=next(i for i in itens if i.text(0)=='Detalhamento técnico');self.assertFalse(t.isExpanded());self.assertTrue(j.atual['proxima'])
    def test_filtro_sem_resultado_limpa_contexto(self):
        j=self.painel();j.busca.setText('sem-correspondencia-impossivel');self.assertIsNone(j.atual);self.assertFalse(j.mapa.geometrias)
    def test_reabertura_sem_migracao_nem_escrita(self):
        h=hash_arquivo(self.base);p=reabrir(self.base);self.assertTrue(catalogar(p));j=self.painel();j.close();self.assertEqual(hash_arquivo(self.base),h)
    def test_selecao_inversa_unica_por_local(self):
        j=self.painel();c=next(c for c in j.casos if c['tipo']=='LOCAL');cam=j.legado.camada_locais
        cam.selectByIds([f.id() for f in cam.getFeatures() if f['LOC_UID']==c['local_uid']]);APP.processEvents()
        self.assertEqual(j.atual['local_uid'],c['local_uid'])
    def test_selecao_inversa_multipla_nao_escolhe_correspondencia(self):
        j=self.painel();cam=j.legado.wg_camadas[0];f=next(cam.getFeatures())
        c=copy.deepcopy(j.casos[0]);c['wg_ids']=[int(f['WG_ID'])];c['uid']='outro';j.casos.append(c)
        cam.selectByIds([f.id()]);APP.processEvents()
        self.assertIn('casos relacionados',j.aviso.text())
        self.assertIsNone(j.atual)
    def test_destaques_temporarios_com_canvas(self):
        canvas=QgsMapCanvas();canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:31983'))
        j=self.painel(canvas);antes=len(QgsProject.instance().mapLayers());j.componentes();self.assertTrue(j.mapa.destaques)
        self.assertEqual(len(QgsProject.instance().mapLayers()),antes);j.aproximar();j.close();self.assertFalse(j.mapa.destaques);canvas.close()
    def test_crs_ou_geometria_insuficiente_sem_posicao_inventada(self):
        self.p['geometrias']=None;self.p['areas']=[]
        j=self.painel();caso=next(c for c in j.casos if c['tipo']=='COMPONENTE')
        self.assertEqual(j.mapa.destacar(caso),0);self.assertIn('Mapa indisponível',j.mapa.aproximar())
    def test_sem_correspondencia_nao_vira_conexao(self):
        l=self.p['resultado']['locais'][0];l['perspectivas'][MODOS[0]]['classes']=['CORRESPONDENCIA_INSUFICIENTE'];l['perspectivas'][MODOS[0]]['classe']='CORRESPONDENCIA_INSUFICIENTE'
        c=next(c for c in catalogar(self.p) if c['tipo']=='LOCAL');self.assertIn('insuficiente',c['perspectivas'][MODOS[0]]['texto'])
    def test_conclusao_tecnica_nao_herda_status_espacial(self):
        self.p['dossie']['locais'][0]['revisao']['situacao']='VERIFICADO'
        j=self.painel();self.assertIn('Sem resultado investigativo',j.cartao.toPlainText())
    def test_fechar_desconecta_navegacao(self):
        j=self.painel();j.close();self.assertFalse(j._ativo);self.assertFalse(j._conexoes)
    def test_categoria_depende_da_perspectiva(self):
        l=self.p['resultado']['locais'][0]
        l['perspectivas'][MODOS[0]]['classes']=['CONEXAO_DIRETA_CONFIRMADA_NO_MODELO']
        l['perspectivas'][MODOS[1]]['classes']=['CONECTIVIDADE_DEPENDENTE_DE_DISPOSITIVO']
        cs=catalogar(self.p)
        self.assertFalse(filtrar(cs,categoria='DISPOSITIVO',modo=MODOS[0]))
        self.assertTrue(filtrar(cs,categoria='DISPOSITIVO',modo=MODOS[1]))
    def test_selecao_gis_temporaria_e_restaurada(self):
        j=self.painel();cam=j.legado.wg_camadas[0];fs=list(cam.getFeatures());cam.selectByIds([fs[0].id()])
        caso=j.casos[0]
        with patch('auditoria_fronteiras.painel.localizar_tubulacoes',return_value=({cam.id():[fs[-1].id()]},[])):
            j.mapa.selecionar_gis(caso)
        self.assertEqual(cam.selectedFeatureIds(),[fs[-1].id()]);j.close();self.assertEqual(cam.selectedFeatureIds(),[fs[0].id()])
    def test_cancelar_troca_preserva_painel_ativo(self):
        from auditoria_topologica_watergems.interface_integracao import JanelaIntegracao
        j=self.painel();janela=JanelaIntegracao();janela.painel=j
        with patch.object(j.legado,'tem_edicoes',return_value=True),patch.object(j.legado,'resolver_edicoes',return_value=False):
            self.assertFalse(janela.publicar(self.p,self.base))
        self.assertTrue(j._ativo);janela.painel=None;janela.close()
    def test_zoom_em_canvas_geografico_nao_interpreta_metros_como_graus(self):
        canvas=QgsMapCanvas();canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
        j=self.painel(canvas);j.aproximar()
        self.assertLess(canvas.extent().width(),1);self.assertLess(canvas.extent().height(),1)
        j.close();canvas.close()


if __name__=='__main__':unittest.main()
