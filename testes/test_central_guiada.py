"""Central: pré-requisitos reais, sem equiparar abertura a conclusão."""
import unittest,tempfile
from pathlib import Path
from unittest.mock import patch
from test_auditoria_fronteiras import APP
import test_aplicacao_unificada as fixture
from auditoria_aplicacao.dependencias import *
from auditoria_aplicacao.contexto_trabalho import Projetos,validar_registro

class DependenciasTest(unittest.TestCase):
    def test_vazio(self):r=avaliar({});self.assertEqual(recomendar(r),'gis');self.assertFalse(disponibilidade('integrar',r)[0])
    def test_topologia_independe_gis_e_crs(self):self.assertTrue(disponibilidade('topologia',avaliar({'wg':{'valido':True}}))[0])
    def test_gis_independente(self):self.assertTrue(disponibilidade('gis',avaliar({}))[0])
    def test_existe_nao_significa_validado(self):self.assertFalse(disponibilidade('topologia',avaliar({'wg':{'valido':False}}))[0])
    def test_integracao_requer_espacial(self):f=dict(gis={'valido':True},wg={'valido':True},compativel=True,correspondencia=True);self.assertFalse(disponibilidade('integrar',avaliar(f))[0])
    def test_completo(self):f=dict(gis={'valido':True},wg={'valido':True},compativel=True,correspondencia=True,espacial=True);self.assertTrue(disponibilidade('integrar',avaliar(f))[0])
    def test_incompativel(self):self.assertEqual(avaliar({'compativel':False})['compatibilidade'].estado,Estado.INCOMPATIVEL)
    def test_integrada_recomendacao(self):self.assertEqual(recomendar(avaliar({'integrada':{'valido':True}})),'continuar')
    def test_ocupado(self):self.assertFalse(disponibilidade('gis',avaliar({}),True)[0])
    def test_continuar_gis_pode_recuperar_sem_sessao(self):self.assertTrue(disponibilidade('continuar_gis',avaliar({}))[0])
    def test_projetos_uuid_nao_nome(self):
        with tempfile.TemporaryDirectory() as d:
            p=Projetos(d);a=p.criar('Mesmo nome');b=p.criar('Mesmo nome');self.assertNotEqual(a['uuid'],b['uuid']);self.assertEqual(Projetos(d).atual()['uuid'],b['uuid'])
    def test_arquivo_movido(self):self.assertFalse(validar_registro(dict(base='arquivo_inexistente.gpkg',uuid='x',tipo='INTEGRADA'))['valido'])

class CentralTest(unittest.TestCase):
    def setUp(self):self.fixture=fixture.InterfaceUnificadaTest();self.fixture.setUp();self.fixture.main.show();self.app=self.fixture.app
    def tearDown(self):self.fixture.tearDown()
    def test_abertura_central_nao_cria_resultados(self):self.app.abrir();self.assertIsNone(self.app.geo.dossie);self.assertTrue(self.app.central.isVisible())
    def test_instancia_unica(self):self.app.abrir();a=self.app.central;self.app.abrir();self.assertIs(a,self.app.central)
    def test_atividade_concluida_nao_deixa_mensagem_ocupada(self):
        self.app.abrir();self.app.ocupado=True;self.app.central.atualizar();self.assertIn('em andamento',self.app.central.pendencias.text());self.app.ocupado=False;self.app.central.atualizar();self.assertNotIn('em andamento',self.app.central.pendencias.text())
    def test_encaminhamento_preserva_intencao(self):
        from qgis.PyQt.QtWidgets import QMessageBox
        self.app.abrir()
        with patch.object(QMessageBox,'exec_',return_value=QMessageBox.Cancel):self.app.central.acionar('integrar')
        self.assertEqual(self.app.central.pendente,'integrar')
    def test_auditoria_real_concluida(self):self.fixture.carregar();self.app.abrir();self.assertEqual(self.app.central._requisitos['gis'].estado,Estado.CONCLUIDO)

class PreparacaoTest(unittest.TestCase):
    def setUp(self):self.fixture=fixture.InterfaceUnificadaTest();self.fixture.setUp();self.app=self.fixture.app;self.app.abrir()
    def tearDown(self):self.fixture.tearDown()
    def test_etapas_mesmo_formulario(self):
        p=self.app.central.preparacao;g=self.app.geo;g.nome_auditoria.setText('Rascunho sintético')
        for i in range(5):p.etapa.setCurrentIndex(i);p.atualizar()
        self.assertEqual(g.nome_auditoria.text(),'Rascunho sintético');self.assertIsNone(g.dossie)
    def test_avancados_recolhidos(self):self.assertFalse(self.app.central.preparacao.avancados.isChecked())
    def test_nao_conclui_por_abrir_janela(self):self.app.bases();self.app.central.preparacao.atualizar();self.assertNotEqual(avaliar({})['wg'].estado,Estado.CONCLUIDO)
    def test_recomendacao_reflete_proxima_pendencia(self):self.assertEqual(recomendar(avaliar(dict(gis={'valido':True},wg={'valido':True}))),'espacial')

class ApresentacaoTest(unittest.TestCase):
    def setUp(self):self.fixture=fixture.InterfaceUnificadaTest();self.fixture.setUp();self.fixture.main.show();self.app=self.fixture.app;self.app.abrir();self.c=self.app.central;self.h=self.c.apresentacao
    def tearDown(self):self.fixture.tearDown()
    def test_alternancia_mesmo_widget(self):
        w=self.c.widget();self.app.geo.nome_auditoria.setText('Rascunho preservado');self.h.alterar(1);self.assertTrue(self.c.isFloating());self.h.alterar(0);self.assertFalse(self.c.isFloating());self.assertIs(w,self.c.widget());self.assertEqual(self.app.geo.nome_auditoria.text(),'Rascunho preservado')
    def test_preferencia_persistida(self):self.h.alterar(1);self.h.salvar();self.assertEqual(self.h.settings.value('apresentacao/central/modo',type=int),1)
    def test_tela_desconectada(self):
        from qgis.PyQt.QtCore import QRect
        from auditoria_fronteiras.ui_comum import ajustar_rect
        r=ajustar_rect(QRect(20000,20000,2000,1000),QRect(0,0,1366,768));self.assertLessEqual(r.right(),1366);self.assertLessEqual(r.bottom(),768)
    def test_processamento_impede_alternancia(self):
        from qgis.PyQt.QtWidgets import QMessageBox
        self.app.ocupado=True
        with patch.object(QMessageBox,'information'):self.h.alterar(1)
        self.assertFalse(self.c.isFloating())
    def test_guiado_avancado_mesmos_dados(self):
        self.app.geo.nome_auditoria.setText('Nome original');self.c.nivel.setCurrentText('Avançado');self.assertFalse(self.c.tabs.isTabVisible(self.c.tabs.indexOf(self.c.preparacao)));self.c.nivel.setCurrentText('Guiado');self.assertEqual(self.app.geo.nome_auditoria.text(),'Nome original')
    def test_centro_escala_nao_sao_redefinidos(self):
        from qgis.core import QgsRectangle
        from qgis.PyQt.QtTest import QTest
        canvas=self.app.iface.mapCanvas();canvas.setExtent(QgsRectangle(0,0,100,100));centro=canvas.center();escala=canvas.scale();self.h.alterar(1);QTest.qWait(20);self.assertAlmostEqual(canvas.scale(),escala,places=5);self.assertLess(canvas.center().distance(centro),.000001)

class ContextosTest(unittest.TestCase):
    def setUp(self):
        self.fixture=fixture.InterfaceUnificadaTest();self.fixture.setUp();self.app=self.fixture.app;self.app.abrir();self.projetos=self.app.central.projetos;self.projetos.criar('Projeto sintético')
    def tearDown(self):self.fixture.tearDown()
    def test_projeto_nao_herda_fontes(self):
        self.fixture.carregar();self.assertTrue(self.projetos.contem('AUDITORIA_GIS',self.app.geo.dossie['execucao_uid']));self.projetos.criar('Outro');self.app.central.atualizar();self.assertEqual(self.app.central._requisitos['gis'].estado,Estado.PENDENTE)
    def test_cancelar_nao_vincula_base(self):
        c=self.app.central;c._visiveis=[dict(uuid='x',tipo='AUDITORIA_GIS',base='nao.gpkg')];c.tabela.setRowCount(1);c.tabela.selectRow(0)
        with patch('auditoria_aplicacao.central.validar_registro',return_value={'valido':True}),patch.object(self.app,'abrir_registro',return_value=False):c.abrir_registro()
        self.assertEqual(self.projetos.atual()['bases'],[])
    def test_associacao_historica(self):
        from auditoria_aplicacao.contexto_trabalho import associar_cenario
        alvo=dict(origem='AREA',id='area-estavel',investigacao='i');a=associar_cenario(self.projetos,'m',2,'v2',alvo);b=associar_cenario(self.projetos,'m',2,'v2',alvo);self.assertEqual(b['anterior'],a['uuid']);self.assertEqual(len(Projetos(self.app.catalogo.raiz).atual()['associacoes_cenarios']),2)
    def test_associacao_exige_identidade(self):
        from auditoria_aplicacao.contexto_trabalho import associar_cenario
        with self.assertRaises(ValueError):associar_cenario(self.projetos,'m',1,'v',{'nome':'Setor'})
    def test_cenario_filtra_modelo_e_id(self):
        from auditoria_aplicacao.cenarios_ui import bases_cenario
        rs=[dict(tipo='TOPOLOGIA_WG',modelo_uid='m',cenario=2,uuid='a'),dict(tipo='TOPOLOGIA_WG',modelo_uid='outro',cenario=2,uuid='b'),dict(tipo='TOPOLOGIA_WG',modelo_uid='m',cenario=1,uuid='c')]
        with patch.object(self.app.catalogo,'listar_opcional',return_value=rs):self.assertEqual([r['uuid'] for r in bases_cenario(self.app.catalogo,'m',2)],['a'])
    def test_troca_cancelada_preserva_base(self):
        with patch('auditoria_aplicacao.contexto_trabalho.validar_registro',return_value={'valido':True}),patch.object(self.app,'resolver',return_value=False):self.assertFalse(self.app.trocar_base(dict(base='nova',uuid='nova',tipo='TOPOLOGIA_WG')))
        self.assertIsNone(self.app.wg)
    def test_base_invalida_nao_resolve_rascunhos(self):
        with patch.object(self.app,'resolver') as resolver:
            with self.assertRaises(ValueError):self.app.trocar_base(dict(base='ausente',uuid='nova',tipo='TOPOLOGIA_WG'))
            resolver.assert_not_called()
    def test_cancelar_configuracao_wg_preserva_pendencia(self):
        from qgis.PyQt.QtWidgets import QMessageBox
        self.app.bases();self.app.wg._ref_pendente=True
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel):self.assertFalse(self.app.resolver_configuracao_wg())
        self.assertTrue(self.app.wg._ref_pendente)
    def test_contexto_base_nao_e_uniao(self):
        from auditoria_aplicacao.contexto_trabalho import contexto_modelo
        m=dict(projeto='m',cenario=1,cenarios=[dict(id=1,pai=None,nome='Base'),dict(id=2,pai=1,nome='Filho')],alternativas={'3':[30]});r=contexto_modelo(m,'v','ESTRUTURAL');self.assertEqual(r['alternativa'],[30]);self.assertIn('GLOBAL',r['escopo'])

class TopologiaSemGISTest(unittest.TestCase):
    def setUp(self):
        import test_bases_plugin as f
        from auditoria_topologica_watergems import bases
        from auditoria_aplicacao.topologia_direta import pacote_topologico
        self.f=f.BasesTest();self.f.setUp();self.base=self.f.criar();self.p=pacote_topologico(bases.restaurar(self.base))
    def tearDown(self):self.f.tearDown()
    def test_adapter_nao_cria_auditoria(self):
        self.assertEqual(self.p['natureza'],'CONTEXTO_TOPOLOGICO_SEM_GIS');self.assertEqual(self.p['dossie']['tubulacoes'],[]);self.assertEqual(self.p['resultado']['locais'],[])
    def test_corredor_reutiliza_grafo(self):
        from auditoria_topologica_watergems import corredores
        antes=self.p['topologia']['estrutural']['grafo'].number_of_edges();r=corredores.calcular(self.p,'ESTRUTURAL',[1],[3],criterio='ARESTAS');self.assertEqual(set(r['metricas']),{'10','11'});self.assertEqual(antes,self.p['topologia']['estrutural']['grafo'].number_of_edges())
    def test_ilhas_sem_gis_e_sem_fonte_nao_declara_defeito(self):
        from auditoria_topologica_watergems import ilhas
        r=ilhas.analisar(self.p);self.assertEqual(r['estado'],'SEM_ORIGENS');self.assertEqual(r['ilhas'],[])

if __name__=='__main__':unittest.main()
