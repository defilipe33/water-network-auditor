"""Política visual e operações compartilhadas, exclusivamente com fontes sintéticas."""
import time,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
from test_auditoria_fronteiras import APP
from qgis.PyQt import sip
from qgis.PyQt.QtCore import Qt,QThread,QTimer
from qgis.PyQt.QtWidgets import QMainWindow,QDialog,QMenu,QLineEdit
from qgis.PyQt.QtTest import QTest
from auditoria_fronteiras.janelas import Janelas
from auditoria_fronteiras.atividade import Atividades,Progresso
from auditoria_fronteiras.atividade import acompanhada


class JanelasTest(unittest.TestCase):
    def setUp(self):self.main=QMainWindow();self.main.show();self.g=Janelas(self.main);self.a=QDialog(self.main);self.b=QDialog(self.a);self.g.registrar('gis',self.a,'auditoria GIS');self.g.registrar('watergems',self.b,'configuração WaterGEMS')
    def tearDown(self):self.g.limpar();self.a.close();self.b.close();self.main.close()
    def test_dialogos_irmaos(self):self.assertIs(self.b.parentWidget(),self.main)
    def test_ocultar_gis_nao_oculta_wg(self):self.g.mostrar('gis');self.g.mostrar('watergems');self.g.ocultar('gis');self.assertTrue(self.b.isVisible())
    def test_recuperar_oculta(self):self.g.ocultar('gis');self.assertTrue(self.g.mostrar('gis'));self.assertTrue(self.a.isVisible())
    def test_nao_recria_instancia(self):self.g.mostrar('watergems');self.g.mostrar('watergems');self.assertIs(self.g.obter('watergems'),self.b)
    def test_preserva_rascunho(self):
        t=QLineEdit(self.b);t.setText('Não salvo');self.g.ocultar('watergems');self.g.mostrar('watergems');self.assertEqual(t.text(),'Não salvo')
    def test_destruida_nao_reutilizada(self):sip.delete(self.b);self.assertIsNone(self.g.obter('watergems'));self.assertFalse(self.g.mostrar('watergems'));self.b=QDialog()
    def test_menu_apenas_validas(self):
        m=QMenu();self.g.preencher_menu(m);self.assertIn('Mostrar auditoria GIS',[a.text() for a in m.actions()]);self.assertNotIn('Mostrar consulta',[a.text() for a in m.actions()])
    def test_modal_nao_perde_foco(self):
        m=QDialog(self.main);m.setWindowModality(Qt.ApplicationModal);m.show();APP.processEvents();self.assertFalse(self.g.mostrar('gis'));self.assertFalse(self.a.isVisible());m.close()
    def test_assistente_concluido_nao_reabre_no_menu(self):
        a=QDialog();a.resultado='salvo';self.g.registrar('assistente',a,'assistente espacial');m=QMenu();self.g.preencher_menu(m);self.assertNotIn('Mostrar assistente espacial',[x.text() for x in m.actions()]);a.close()
    def test_restaurar_principais(self):self.g.restaurar();self.assertTrue(self.a.isVisible());self.assertTrue(self.b.isVisible())
    def test_minimizar_nao_revela_ocultas(self):
        self.g.ocultar('gis');self.main.showMinimized();APP.processEvents();self.main.showNormal();APP.processEvents();self.assertFalse(self.a.isVisible())
    def test_restaurar_qgis_explicitamente(self):self.main.showMinimized();self.g.mostrar('gis');self.assertFalse(self.main.isMinimized())
    def test_auxiliar_registrada_com_proprietario_logico(self):
        from auditoria_fronteiras.janelas import registrar_auxiliar
        d=QDialog(self.a);g=registrar_auxiliar(self.a,'comparacao',d,'comparação');self.assertIs(g,self.g);self.assertIs(d.parentWidget(),self.main);d.close()


class AtividadeTest(unittest.TestCase):
    def setUp(self):self.main=QMainWindow();self.main.show();self.s=Atividades(self.main);self.d=QDialog(self.main);self.s.vincular(self.d)
    def tearDown(self):
        if self.s.atual:self.s.atual.cancelar()
        for t in list(self.s.workers):
            if not sip.isdeleted(t):t.requestInterruption();t.wait(3000)
        APP.processEvents()
        if self.s.atual:self.s.atual.finalizar('CANCELADO')
        self.s.fechar();self.main.close()
    def esperar(self):
        limite=time.monotonic()+5
        while self.s.em_execucao() and time.monotonic()<limite:QTest.qWait(20)
        self.assertFalse(self.s.em_execucao())
    def test_rapida_sem_dock(self):
        with self.s.operacao('Rápida'):pass
        QTest.qWait(450);self.assertFalse(self.s.dock.isVisible());self.assertEqual(self.s.ultima.estado,'CONCLUIDO')
    def test_demorada_exibe(self):
        with self.s.operacao('Demorada'):
            limite=time.monotonic()+2
            while not self.s.dock.isVisible() and time.monotonic()<limite:QTest.qWait(20)
            self.assertTrue(self.s.dock.isVisible())
    def test_indeterminado(self):
        with self.s.operacao('Lendo') as o:o.atualizar('Lendo banco');self.assertEqual(self.s.barra.maximum(),0)
    def test_determinado_real(self):
        with self.s.operacao('Tubos') as o:o.atualizar('Analisando tubos',5,10);self.assertEqual(self.s.barra.value(),50)
    def test_cem_so_ao_concluir(self):
        with self.s.operacao('Etapas') as o:o.atualizar('Finalizando etapa',10,10);self.assertEqual(self.s.barra.maximum(),0)
        self.assertEqual(self.s.barra.value(),100)
    def test_cancelamento(self):
        avisos=[]
        with self.s.operacao('Cancelável',cancelar=lambda:avisos.append(True)) as o:o.cancelar();self.assertTrue(o.ponto())
        self.assertEqual(self.s.ultima.estado,'CANCELADO');self.assertEqual(avisos,[True])
    def test_sem_cancelamento_nao_finge(self):
        with self.s.operacao('Crítica') as o:o.cancelar();self.assertFalse(o.solicitado);self.assertFalse(self.s.cancelar.isEnabled())
    def test_erro_libera_sistema(self):
        with self.assertRaises(ValueError):
            with self.s.operacao('Erro'):raise ValueError('Falha sintética')
        self.assertEqual(self.s.ultima.estado,'ERRO');self.assertIsNone(self.s.atual);self.assertIn('ValueError',self.s.ultima.detalhes)
    def test_apos_erro_permite_nova(self):
        with self.assertRaises(ValueError):
            with self.s.operacao('Erro'):raise ValueError('Falha')
        with self.s.operacao('Outra'):pass
        self.assertEqual(self.s.ultima.estado,'CONCLUIDO')
    def test_nao_simultaneas(self):
        with self.s.operacao('Primeira'):
            with self.assertRaises(RuntimeError):self.s.iniciar('Segunda')
    def test_nao_fechar_durante_operacao(self):
        with self.s.operacao('Ativa'):self.assertFalse(self.s.fechar())
    def test_critica_respeita_cancelamento_anterior(self):
        with self.assertRaises(InterruptedError):
            with self.s.operacao('Teste',cancelar=lambda:None) as o:o.cancelar();o.critica('Publicar')
        self.assertEqual(self.s.ultima.estado,'CANCELADO')
    def test_worker_pronto_no_thread_gui(self):
        recepcao=[];self.s.executar_thread('Leitura','Sintético',lambda c,p:17,lambda valor:recepcao.append((valor,QThread.currentThread()==APP.thread())))
        self.esperar();self.assertEqual(recepcao,[(17,True)])
    def test_worker_mantem_heartbeat(self):
        def funcao(c,p):p(0,'Lendo');time.sleep(.2);return 1
        self.s.executar_thread('Leitura','Sintético',funcao,lambda r:None);QTest.qWait(30);self.assertTrue(self.s.em_execucao());self.esperar()
    def test_worker_cancelado_nao_publica(self):
        publicados=[]
        def funcao(c,p):
            while not c():time.sleep(.01)
            raise InterruptedError('Cancelado')
        self.s.executar_thread('Leitura','Sintético',funcao,publicados.append);self.s.atual.cancelar();self.esperar();self.assertEqual(publicados,[]);self.assertEqual(self.s.ultima.estado,'CANCELADO')
    def test_worker_erro_sem_orfa(self):
        def funcao(c,p):raise ValueError('Falha controlada')
        erros=[];self.s.executar_thread('Leitura','Sintético',funcao,lambda r:None,erros.append);self.esperar();self.assertEqual(len(erros),1);self.assertEqual(self.s.ultima.estado,'ERRO');self.assertIn('ValueError',self.s.ultima.detalhes)
    def test_adaptador_nao_declara_sucesso_ao_fechar(self):
        p=Progresso('Preparando','Cancelar',0,0,self.d);p.close();self.assertEqual(self.s.ultima.estado,'AGUARDANDO_CONFIRMACAO')
    def test_adaptador_concluido(self):p=Progresso('Preparando','Cancelar',0,0,self.d);p.concluir();p.close();self.assertEqual(self.s.ultima.estado,'CONCLUIDO')
    def test_adaptador_cancelado(self):p=Progresso('Preparando','Cancelar',0,0,self.d);p.cancel();self.assertTrue(p.wasCanceled());p.close();self.assertEqual(self.s.ultima.estado,'CANCELADO')
    def test_timer_nao_reentra_na_mesma_operacao(self):
        chamadas=[];tentativas=[];s=self.s
        class Dialogo(QDialog):
            @acompanhada('Carregando')
            def carregar(self):
                chamadas.append(True);QTimer.singleShot(0,lambda:tentativas.append(self.carregar()));s.atual._ultima=0;s.atual.ponto();return True
        d=Dialogo(self.main);s.vincular(d);self.assertTrue(d.carregar());self.assertEqual(chamadas,[True]);self.assertEqual(tentativas,[False]);d.close()
    def test_etapa_do_assistente_nao_confirma_validacao(self):
        from unittest.mock import Mock
        import test_deteccao_espacial as fx
        f=fx.AssistenteUITest();f.setUp()
        try:
            from auditoria_fronteiras.atividade import sistema
            f.a.trabalho=Mock();f.a.trabalho.isRunning.return_value=False;f.a.trabalho.isInterruptionRequested.return_value=False
            f.a._atividade=sistema(f.w).iniciar('Validando referência');f.a.terminou()
            self.assertEqual(f.a._atividade.estado,'ETAPA_CONCLUIDA');self.assertIsNone(f.a._atividade.percentual);self.assertEqual(f.a.barra.value(),0)
        finally:f.tearDown()

if __name__=='__main__':unittest.main()
