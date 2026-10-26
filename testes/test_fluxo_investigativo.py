"""Registros leves, contexto visual e publicação do assistente: dados sintéticos."""
import copy
from contextlib import closing
from pathlib import Path
import shutil,sqlite3,tempfile,unittest
from unittest.mock import patch
from test_auditoria_fronteiras import APP,camada
import test_integracao_investigativa as fx
from qgis.core import QgsProject
from auditoria_fronteiras.organizacao_camadas import publicar,grupo,remover_temporarias
from auditoria_topologica_watergems import decisoes as db
from auditoria_topologica_watergems.diagnosticos import catalogar,MODOS
from auditoria_topologica_watergems.saidas_integracao import salvar_gpkg
from auditoria_topologica_watergems.painel_diagnosticos import abrir_diagnosticos

class RegistrosTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f=fx.IntegracaoPersistidaTest();cls.f.setUp();cls.p=cls.f.executar();cls.original=salvar_gpkg(cls.p,cls.f.p/'anotacoes.gpkg')
    @classmethod
    def tearDownClass(cls):cls.f.tearDown()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True);self.base=Path(self.tmp.name)/'base.gpkg';shutil.copyfile(self.original,self.base);self.c=next(c for c in catalogar(self.p) if c['tipo']=='LOCAL');self.ig=self.p['resultado']['meta']['uid'];self.projeto=QgsProject();self.j=None
    def tearDown(self):
        if self.j:
            self.j.analise.carregar(self.c,MODOS[0],True);self.j.close()
        self.projeto.removeAllMapLayers();self.tmp.cleanup()
    def salvar(self,t='Observação simples',c=None,modo=MODOS[0]):return db.salvar_registro(self.base,self.p,self.c,modo,t,c)
    def test_anotacao_so_texto(self):self.salvar();self.assertEqual(db.registros(self.base,self.ig)[0]['tipo'],'ANOTACAO')
    def test_anotacao_vazia(self):
        with self.assertRaises(ValueError):self.salvar(' ')
    def test_multiplas_anotacoes(self):self.salvar();self.salvar('Segunda');self.assertEqual(len(db.registros(self.base,self.ig)),2)
    def test_nao_cria_conclusao(self):self.salvar();self.assertEqual(db.historico(self.base,self.ig,self.c['uid'],MODOS[0]),[])
    def test_preliminar(self):self.salvar(c=db.PRELIMINARES[1]);self.assertEqual(db.registros(self.base,self.ig)[0]['tipo'],'PRELIMINAR')
    def test_confirmada_nao_aceita_como_preliminar(self):
        with self.assertRaises(ValueError):self.salvar(c=db.CONCLUSOES[2])
    def test_modo_independente(self):self.salvar(modo=MODOS[1]);self.assertEqual(db.registros(self.base,self.ig,modo=MODOS[0]),[])
    def test_uuid_e_contexto(self):
        uid=self.salvar();r=db.registros(self.base,self.ig)[0];self.assertEqual(r['reg_uid'],uid);self.assertTrue(r['assinatura']);self.assertEqual(r['occ_uid'],self.c['uid'])
    def test_historico_imutavel(self):
        self.salvar()
        with closing(sqlite3.connect(self.base)) as c:
            with self.assertRaises(sqlite3.IntegrityError):c.execute('DELETE FROM IGD_REGISTROS')
    def test_integridade(self):
        self.salvar()
        with closing(sqlite3.connect(self.base)) as c:self.assertFalse(c.execute('pragma foreign_key_check').fetchall())
    def test_base_antiga_nao_alterada_por_leitura(self):self.assertEqual(db.registros(self.base,self.ig),[])
    def test_exportacao_inclui_notas(self):
        self.salvar();from auditoria_topologica_watergems.exportacao_decisoes import tabelas_decisoes
        self.assertEqual(len(tabelas_decisoes(self.base,self.p)['ANOTACOES_PRELIMINARES'][1]),1)
    def painel(self):
        self.j=abrir_diagnosticos(self.p,self.base,self.projeto);self.j.limpar_filtros();self.j.lista.selectRow(next(i for i,c in enumerate(self.j.visiveis) if c['uid']==self.c['uid']));self.j.selecionar();return self.j.analise
    def test_ui_anotacao_sem_evidencia(self):
        a=self.painel();a.anotacao.setPlainText('Conferir no modelo');self.assertTrue(a.salvar_registro());self.assertFalse(a.anotacao.toPlainText())
    def test_anotacao_nao_herda_responsavel_da_conclusao(self):
        a=self.painel();a.operador='';a.responsavel.setText('Responsável de conclusão anterior');a.anotacao.setPlainText('Nova observação');self.assertTrue(a.salvar_registro());self.assertEqual(db.registros(self.base,self.ig)[0]['responsavel'],'')
    def test_ui_preliminar_sem_responsavel(self):
        a=self.painel();a.conclusao.setCurrentIndex(a.conclusao.findData('DESCONEXÃO INTENCIONAL'));a.justificativa.setPlainText('Investigar');a.usar_hipotese();self.assertTrue(a.salvar_registro(True));self.assertFalse(a.tem_edicoes());self.assertEqual(db.historico(self.base,self.ig,self.c['uid'],MODOS[0]),[])
    def test_ui_evidencias_recolhidas(self):self.assertFalse(self.painel().avancadas.isChecked())
    def test_ui_anotacao_nao_salva_guardada(self):
        a=self.painel();a.anotacao.setPlainText('Rascunho');self.assertTrue(a.tem_edicoes());a.carregar(self.c,MODOS[0]);self.assertEqual(a.anotacao.toPlainText(),'Rascunho')
    def test_ui_reabertura_historico(self):self.salvar('Texto preservado');self.assertIn('Texto preservado',self.painel().historia.toPlainText())
    def test_ui_andamento_sem_conclusao(self):
        a=self.painel();a.situacao.setCurrentText('EM_ANALISE');self.assertTrue(a.salvar_andamento());self.assertEqual(db.historico(self.base,self.ig,self.c['uid'],MODOS[0])[-1]['conclusao'],'NÃO AVALIADO')
    def test_reabrir_integracao_sem_copias(self):
        self.j=abrir_diagnosticos(self.p,self.base,self.projeto);n=len(self.projeto.mapLayers());outro=abrir_diagnosticos(self.p,self.base,self.projeto);self.assertEqual(len(self.projeto.mapLayers()),n);outro.close()
    def test_projeto_reaberto_recupera_cache_sem_duplicar(self):
        self.j=abrir_diagnosticos(self.p,self.base,self.projeto);n=len(self.projeto.mapLayers());self.j.close();self.j=None
        f=str(Path(self.tmp.name)/'investigacao.qgz');self.assertTrue(self.projeto.write(f));self.projeto.removeAllMapLayers();self.assertTrue(self.projeto.read(f))
        self.j=abrir_diagnosticos(self.p,self.base,self.projeto);self.assertEqual(len(self.projeto.mapLayers()),n);self.assertTrue(any(c.featureCount()>0 for c in self.projeto.mapLayers().values() if c.customProperty('integracao/grupo')=='wg'))

class ArvoreTest(unittest.TestCase):
    def setUp(self):self.p=QgsProject();self.c=camada('LineString',['LINESTRING(0 0,1 1)']);self.c.setName('WG_TUBULACOES')
    def tearDown(self):self.p.removeAllMapLayers()
    def add(self,uid='u',cat='wg',base='fonte.gpkg',**kw):return publicar(self.c,self.p,cat,uid,base,'Projeto',1,**kw)
    def test_raiz(self):self.add();self.assertEqual(self.p.layerTreeRoot().children()[0].name(),'TOPOLOGIA WATERGEMS')
    def test_uuid_grupo(self):self.add();self.assertEqual(self.p.layerTreeRoot().children()[0].children()[0].customProperty('wna/uid'),'u')
    def test_versoes_separadas(self):self.add();grupo(self.p,'wg','v2','fonte.gpkg','Projeto',2);self.assertEqual(len(self.p.layerTreeRoot().children()[0].children()),2)
    def test_categorias_separadas(self):self.add();grupo(self.p,'integrada','i','ig.gpkg','Projeto',1);self.assertEqual(len(self.p.layerTreeRoot().children()),2)
    def test_nao_adota_grupo_do_usuario(self):self.p.layerTreeRoot().addGroup('TOPOLOGIA WATERGEMS');self.add();self.assertEqual(len(self.p.layerTreeRoot().children()),2)
    def test_nao_move_original(self):
        g=self.p.layerTreeRoot().addGroup('Original');self.p.addMapLayer(self.c,False);g.addLayer(self.c);c=camada('Point',['POINT(0 0)']);publicar(c,self.p,'wg','u',nome='Novo');self.assertEqual(self.p.layerTreeRoot().findLayer(self.c.id()).parent(),g)
    def test_estilo_e_selecao_preservados(self):
        self.c.selectAll();ids=self.c.selectedFeatureIds();estilo=self.c.renderer().dump();self.add();self.assertEqual(self.c.renderer().dump(),estilo);self.assertEqual(self.c.selectedFeatureIds(),ids)
    def test_visibilidade_reabertura(self):
        self.add();self.p.layerTreeRoot().findLayer(self.c.id()).setItemVisibilityChecked(False);self.add();self.assertFalse(self.p.layerTreeRoot().findLayer(self.c.id()).itemVisibilityChecked())
    def test_reusa_mesma_fonte_uid(self):self.add();self.assertEqual(self.add().id(),self.c.id());self.assertEqual(len(self.p.mapLayers()),1)
    def test_fontes_diferentes_separadas(self):self.add();grupo(self.p,'wg','u','outro.gpkg','Projeto',1);self.assertEqual(len(self.p.layerTreeRoot().children()[0].children()),2)
    def test_temporarias_apenas_proprias(self):
        self.add(temporaria=True);c=camada('Point',['POINT(0 0)']);self.p.addMapLayer(c);self.assertEqual(remover_temporarias(self.p),1);self.assertIsNotNone(self.p.mapLayer(c.id()))
    def test_salvar_reabrir_qgz_metadados(self):
        self.add()
        with tempfile.TemporaryDirectory() as tmp:
            f=str(Path(tmp)/'teste.qgz');self.assertTrue(self.p.write(f));p=QgsProject();self.assertTrue(p.read(f));self.assertEqual(p.layerTreeRoot().children()[0].customProperty('wna/categoria'),'wg');p.removeAllMapLayers()

class AssistenteFimTest(unittest.TestCase):
    def setUp(self):
        from test_deteccao_espacial import AssistenteUITest
        self.f=AssistenteUITest();self.f.setUp();self.a=self.f.a
    def tearDown(self):self.f.tearDown()
    def test_responsavel_ausente_preserva_dados(self):
        self.a.responsavel.clear();antes=self.a.relatorio
        with patch('auditoria_aplicacao.assistente_espacial.QMessageBox.warning'):self.a.salvar()
        self.assertIs(self.a.relatorio,antes);self.assertIn('border',self.a.responsavel.styleSheet())
    def test_versao_publicada_bloqueia_nova_gravacao(self):
        self.a._publicacao='nova.gpkg'
        with patch('auditoria_aplicacao.assistente_espacial.QFileDialog.getSaveFileName') as escolha:self.a.salvar();escolha.assert_not_called()
    def test_fim_fecha_e_atualiza_pai(self):
        from test_usabilidade_crs import REF
        self.a.show()
        with patch('auditoria_aplicacao.assistente_espacial.bases.metadados',return_value={'referencia_espacial':REF}),patch.object(self.a.pai,'usar_base',side_effect=lambda p:setattr(self.a.pai,'base',str(p))) as usar:
            self.a.salvo('nova.gpkg');self.a.terminou();usar.assert_called_once_with('nova.gpkg')
        self.assertFalse(self.a.isVisible());self.assertEqual(self.a.resultado,'nova.gpkg')
    def test_x_antes_salvar_preserva_base(self):
        antes=self.a.pai.base;self.a.show();self.a.close();self.assertEqual(self.a.pai.base,antes);self.assertIsNone(self.a.resultado)
    def test_x_apos_publicacao_mantem_pai_atualizado(self):
        from test_usabilidade_crs import REF
        self.a.show()
        with patch('auditoria_aplicacao.assistente_espacial.bases.metadados',return_value={'referencia_espacial':REF}),patch.object(self.a.pai,'usar_base',side_effect=lambda p:setattr(self.a.pai,'base',str(p))):self.a.salvo('nova.gpkg');self.a.close()
        self.assertEqual(self.a.pai.base,'nova.gpkg');self.assertEqual(self.a.resultado,'nova.gpkg')

if __name__=='__main__':unittest.main()
