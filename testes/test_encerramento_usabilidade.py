"""Contrato de saída do QGIS e refinamentos da apresentação, sem dados reais."""
import sys,tempfile,unittest,shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from test_auditoria_fronteiras import APP
from qgis.core import QgsProject
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtWidgets import QMainWindow,QMessageBox
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QRect
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'complemento_qgis'))
from auditoria_redes.plugin import AuditoriaRedesPlugin
from auditoria_aplicacao.controlador import Aplicacao
import test_integracao_investigativa as fx
from auditoria_topologica_watergems.saidas_integracao import salvar_gpkg
from auditoria_topologica_watergems.painel_diagnosticos import abrir_diagnosticos
from auditoria_topologica_watergems import decisoes as db


class ContratoSaidaTest(unittest.TestCase):
    def setUp(self):
        self.main=QMainWindow();self.iface=Mock();self.iface.mainWindow.return_value=self.main
        self.plugin=AuditoriaRedesPlugin(self.iface);self.plugin.initGui()
    def tearDown(self):
        self.plugin.app=None;self.plugin.unload();self.main.close()
    def app(self,resultado=True):
        self.plugin.app=SimpleNamespace(preparar_saida=Mock(return_value=resultado),encerrar=Mock(return_value=True));return self.plugin.app
    def test_sem_abrir_autoriza(self):self.assertTrue(self.plugin.bloqueador.allowExit())
    def test_resultado_true_autoriza(self):self.app();self.assertTrue(self.plugin.bloqueador.allowExit())
    def test_cancelar_impede(self):self.app(False);self.assertFalse(self.plugin.bloqueador.allowExit())
    def test_uma_consulta(self):
        a=self.app();self.plugin.bloqueador.allowExit();a.preparar_saida.assert_called_once()
    def test_reentrada_impede_sem_recursao(self):
        a=self.app();a.preparar_saida.side_effect=self.plugin.bloqueador.allowExit
        self.assertFalse(self.plugin.bloqueador.allowExit());a.preparar_saida.assert_called_once();self.assertFalse(self.plugin._verificando_saida)
    def test_erro_nao_autoriza_perda(self):
        a=self.app();a.preparar_saida.side_effect=RuntimeError('Falha sintética')
        with patch.object(QMessageBox,'warning') as aviso:self.assertFalse(self.plugin.bloqueador.allowExit());aviso.assert_called_once()
        self.assertFalse(self.plugin._verificando_saida)
    def test_init_gui_idempotente(self):self.plugin.initGui();self.iface.registerApplicationExitBlocker.assert_called_once()
    def test_unload_remove_uma_vez(self):
        b=self.plugin.bloqueador;self.plugin.unload();self.plugin.unload();self.iface.unregisterApplicationExitBlocker.assert_called_once_with(b)
    def test_reload_nao_acumula(self):
        self.plugin.unload();self.plugin.initGui();self.assertEqual(self.iface.registerApplicationExitBlocker.call_count,2)
    def test_unload_cancelado_mantem_guarda(self):
        a=self.app();a.encerrar.return_value=False;b=self.plugin.bloqueador
        with self.assertRaises(RuntimeError):self.plugin.unload()
        self.assertIs(self.plugin.bloqueador,b);self.iface.unregisterApplicationExitBlocker.assert_not_called()


class SaidaIntegradaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f=fx.IntegracaoPersistidaTest();cls.f.setUp();cls.p=cls.f.executar();cls.original=salvar_gpkg(cls.p,cls.f.p/'saida.gpkg')
    @classmethod
    def tearDownClass(cls):cls.f.tearDown()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True);self.base=Path(self.tmp.name)/'integrada.gpkg';shutil.copyfile(self.original,self.base)
        self.main=QMainWindow();self.canvas=QgsMapCanvas();self.iface=Mock();self.iface.mainWindow.return_value=self.main;self.iface.mapCanvas.return_value=self.canvas
        self.app=Aplicacao(self.iface,self.tmp.name)
        with patch('qgis.utils.iface',self.iface):self.assertTrue(self.app.publicar(self.p,self.base))
        self.j=self.app.painel
    def tearDown(self):
        if self.j:self.j.analise.carregar(self.j.atual,self.j.modo.currentData(),True)
        self.app.geo._executando=False;self.app.ocupado=False
        if self.app.wg:self.app.wg.ocupado=False
        self.app.encerrar();QgsProject.instance().removeAllMapLayers();self.canvas.close();self.main.close();self.tmp.cleanup()
    def test_controlador_nao_registra_segundo_bloqueador(self):self.assertIsNone(self.j._bloqueador);self.iface.registerApplicationExitBlocker.assert_not_called()
    def test_saida_limpa_sem_perguntas(self):
        with patch.object(QMessageBox,'question') as q:self.assertTrue(self.app.preparar_saida());q.assert_not_called()
    def test_anotacao_cancelada_permanece(self):
        self.j.analise.anotacao.setPlainText('Rascunho')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel) as q:self.assertFalse(self.app.preparar_saida());q.assert_called_once()
        self.assertEqual(self.j.analise.anotacao.toPlainText(),'Rascunho');self.assertTrue(self.j._ativo)
    def test_anotacao_salva_saida_e_releitura(self):
        a=self.j.analise;uid=a.caso['uid'];a.anotacao.setPlainText('Preservar')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Save) as q:self.assertTrue(self.app.preparar_saida());self.assertTrue(self.app.preparar_saida());q.assert_called_once()
        self.assertEqual(db.registros(self.base,a.ig,uid)[0]['observacao'],'Preservar')
    def test_descartar_nao_grava_e_nao_repete(self):
        a=self.j.analise;a.anotacao.setPlainText('Descartar')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Discard) as q:self.assertTrue(self.app.preparar_saida());self.assertTrue(self.app.preparar_saida());q.assert_called_once()
        self.assertFalse(db.registros(self.base,a.ig));self.assertFalse(a.tem_edicoes())
    def test_descarte_legado_consumido(self):
        l=self.j.legado;l.locais.setCurrentIndex(1);l.observacoes.setPlainText('Revisão espacial em rascunho')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Discard) as q:self.assertTrue(self.app.preparar_saida());self.assertTrue(self.app.preparar_saida());q.assert_called_once()
        self.assertFalse(l.tem_edicoes())
    def test_salvar_falhou_impede_saida(self):
        a=self.j.analise;a.anotacao.setPlainText('Preservar rascunho')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Save),patch.object(a,'salvar_registro',return_value=False):self.assertFalse(self.app.preparar_saida())
        self.assertEqual(a.anotacao.toPlainText(),'Preservar rascunho')
    def test_processamento_nao_interrompido(self):
        self.app.ocupado=True
        with patch.object(self.j,'resolver_alteracoes') as r:self.assertFalse(self.app.preparar_saida());r.assert_not_called()
        self.app.ocupado=False;self.assertTrue(self.app.preparar_saida())
    def test_thread_watergems_impede_saida(self):
        self.app.bases();self.app.wg.ocupado=True;self.assertFalse(self.app.preparar_saida());self.app.wg.ocupado=False;self.assertTrue(self.app.preparar_saida())
    def test_painel_destruido_nao_e_consultado(self):
        self.j.close();sip.delete(self.j);self.assertTrue(self.app.resolver());self.assertIsNone(self.app.painel);self.j=self.app.painel=None
    def test_informacoes_avancadas_recolhidas(self):self.assertFalse(self.j.mostrar_detalhes.isChecked());self.assertTrue(self.j.detalhes.isHidden())
    def test_anotar_leva_ao_campo_sem_mudar_modo(self):
        m=self.j.modo.currentData();self.j.anotar();self.assertEqual(self.j.tabs.currentIndex(),0);self.assertEqual(self.j.modo.currentData(),m);self.assertIsNotNone(self.j.resultado_analise.observacoes)
    def test_proxima_cancelada_mantem_caso(self):
        self.j.limpar_filtros();self.j.lista.selectRow(0);uid=self.j.atual['uid'];self.j.analise.anotacao.setPlainText('Pendente')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel):self.j.proxima()
        self.assertEqual(self.j.atual['uid'],uid);self.assertTrue(self.j.analise.tem_edicoes())
    def test_navegacao_principal_acoes_claras(self):self.assertEqual(len(self.app.navegacao),6);self.assertTrue(all(b.toolTip() for b in self.app.navegacao.values()))
    def test_campos_opcionais_ocultos_preservam_formulario(self):
        g=self.app.geo;f=g.formulario();self.assertTrue(g.redes.isColumnHidden(3));g.campos_opcionais.setChecked(True);self.assertFalse(g.redes.isColumnHidden(3));self.assertEqual(g.formulario(),f)
    def test_crs_avancado_recolhido(self):self.app.bases();self.assertFalse(self.app.wg.opcoes_referencia.isChecked())
    def test_salvar_observacao_e_proxima(self):
        self.j.limpar_filtros();self.j.lista.selectRow(0);a=self.j.analise;anterior=self.j.atual['uid'];a.anotacao.setPlainText('Conferência rápida');a.salvar_e_proxima()
        self.assertNotEqual(self.j.atual['uid'],anterior);self.assertEqual(db.registros(self.base,a.ig,anterior)[0]['observacao'],'Conferência rápida')
    def test_salvar_e_proxima_nao_perde_texto_em_erro(self):
        a=self.j.analise;uid=self.j.atual['uid'];a.anotacao.setPlainText('Preservar')
        with patch.object(a,'salvar_registro',return_value=False):a.salvar_e_proxima()
        self.assertEqual(self.j.atual['uid'],uid);self.assertEqual(a.anotacao.toPlainText(),'Preservar')
    def test_painel_console_remove_guarda_ao_destruir(self):
        with patch('qgis.utils.iface',self.iface):j=abrir_diagnosticos(self.p,self.base,QgsProject.instance(),self.main,self.canvas)
        b=j._bloqueador;self.assertTrue(b.allowExit());j.close();sip.delete(j)
        self.iface.unregisterApplicationExitBlocker.assert_called_once_with(b);self.assertTrue(b.allowExit())
    def test_janelas_em_area_logica_notebook(self):
        self.app.bases()
        for largura,altura in ((1366,768),(1280,720),(910,512),(1920,1080)):
            for w in (self.app.geo,self.app.wg):
                APP._wna_guarda.enquadrar(w,area=QRect(0,0,largura,altura));self.assertLessEqual(w.width(),largura-32);self.assertLessEqual(w.height(),altura-56);self.assertTrue(hasattr(w,'_wna_scroll'))


if __name__=='__main__':unittest.main()
