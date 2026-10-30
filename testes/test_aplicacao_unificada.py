"""Guardas do fluxo unificado com os widgets reais do PyQGIS."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from test_auditoria_fronteiras import APP
from qgis.PyQt.QtWidgets import QMainWindow,QMessageBox
from qgis.gui import QgsMapCanvas
from qgis.core import QgsProject
from auditoria_aplicacao.controlador import Aplicacao
from auditoria_fronteiras.estados import Estado
from test_inspecao_exportacao import preparar
from auditoria_fronteiras.persistencia import salvar_execucao


class InterfaceUnificadaTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True);self.raiz=Path(self.tmp.name);self.main=QMainWindow();self.canvas=QgsMapCanvas()
        class Iface:
            def mainWindow(s):return self.main
            def mapCanvas(s):return self.canvas
        self.app=Aplicacao(Iface(),self.raiz)
    def tearDown(self):
        self.app.geo.resolver_pendencias=lambda:True;self.app.geo._executando=False;self.app.ocupado=False
        # Limpeza do cenário sintético: as guardas são verificadas no corpo dos
        # testes, não se mantém um diálogo de saída aberto durante tearDown.
        self.app.resolver_configuracao_wg=lambda:True
        if self.app.wg:self.app.wg.ocupado=False
        self.app.encerrar();QgsProject.instance().removeAllMapLayers();self.main.close();self.tmp.cleanup()
    def carregar(self):
        _,_,d,_,_=preparar();self.base=self.raiz/'nome pessoal.gpkg';salvar_execucao(self.base,d);self.app.geo.abrir_auditoria(str(self.base),d['execucao_uid']);return d
    def test_sem_auditoria_nao_integra(self):
        with self.assertRaises(ValueError):self.app.validar_geo()
    def test_processando_bloqueia_mudanca_e_saida(self):
        self.app.geo._executando=True
        with self.assertRaises(ValueError):self.app.validar_geo()
        self.assertFalse(self.app.preparar_saida());self.app.bases();self.assertIsNone(self.app.wg)
    def test_integracao_ocupada_bloqueia_saida(self):
        self.app.ocupado=True;self.assertFalse(self.app.preparar_saida());self.app.bases();self.assertIsNone(self.app.wg)
    def test_quatro_modos_preservados(self):self.assertEqual(self.app.geo.modalidade.count(),4)
    def test_reabertura_ativa_sem_reprocessar(self):
        d=self.carregar();self.assertEqual(self.app.geo.dossie['execucao_uid'],d['execucao_uid']);self.assertTrue(self.app.validar_geo());self.assertEqual(self.app.geo.estado,Estado.INSPECIONANDO)
    def test_bases_janela_unica(self):
        self.app.bases();w=self.app.wg;self.app.bases();self.assertIs(self.app.wg,w)
    def test_estados_cenario_indisponivel(self):
        self.app.bases();self.assertFalse(self.app.wg.modo.model().item(2).isEnabled());self.assertEqual(self.app.wg.modo.currentText(),'TODAS_VALVULAS_ABERTAS')
    def test_mapeamento_cadastral_nao_e_escolhido_automaticamente(self):
        self.carregar();self.app.bases();self.assertTrue(self.app.wg.mapas);self.assertTrue(all(c.currentData() is None for c in self.app.wg.mapas.values()))
    def test_troca_geo_limpa_mapeamentos_antigos(self):
        self.carregar();self.app.bases();w=self.app.wg;origens=set(w.mapas);self.app.geo.dossie=None;w.atualizar_geo();self.assertFalse(w.mapas);self.assertIsNone(w.geo_uid)
    def test_revisao_cancelada_preserva_contexto(self):
        d=self.carregar()
        with patch.object(self.app,'resolver',return_value=False):self.assertFalse(self.app.validar_geo())
        self.assertEqual(self.app.geo.dossie['execucao_uid'],d['execucao_uid'])

if __name__=='__main__':unittest.main()
