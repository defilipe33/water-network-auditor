"""Resolução é acompanhamento, não resultado técnico nem modificação hidráulica."""
import copy,json,sqlite3,unittest
from pathlib import Path
from unittest.mock import patch
import test_decisoes_topologicas as fixture
from test_auditoria_fronteiras import APP
from auditoria_topologica_watergems import acompanhamento as ac,operacional as op,relatorio_investigacao as rel
from auditoria_topologica_watergems.diagnosticos import catalogar
from auditoria_topologica_watergems.saidas_integracao import reabrir,salvar_gpkg


class ResolvidoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.DecisoesTest.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):fixture.DecisoesTest.tearDownClass.__func__(cls)
    def setUp(self):fixture.DecisoesTest.setUp(self)
    def tearDown(self):fixture.DecisoesTest.tearDown(self)
    def resolver(self,**kw):return ac.salvar(self.base,self.p,self.c,'ESTRUTURAL','RESOLVIDO',**kw)
    def painel(self):return fixture.DecisoesTest.painel(self)
    def test_legado_lido_sem_migrar(self):a=self.base.read_bytes();self.assertEqual(ac.indice(self.base,self.p),{});self.assertEqual(self.base.read_bytes(),a)
    def test_resolver_sem_responsavel_justificativa(self):self.resolver();h=ac.historico(self.base,self.ig)[0];self.assertEqual(h['estado'],'RESOLVIDO');self.assertEqual(h['observacao'],'')
    def test_nao_substitui_resultado(self):
        op.salvar(self.base,self.p,self.c,'ESTRUTURAL',resultado='MANTER CONFIGURAÇÃO ATUAL',prioridade='Baixa');antes=op.historico(self.base,self.ig);self.resolver();self.assertEqual(op.historico(self.base,self.ig),antes)
    def test_nao_altera_diagnostico_prioridade(self):antes=copy.deepcopy(self.c);self.resolver();self.assertEqual(self.c,antes)
    def test_sem_analise_tecnica_obrigatoria(self):self.resolver();self.assertEqual(op.historico(self.base,self.ig),[])
    def test_reabrir_preserva_historico(self):uid=self.resolver(observacao='Separação intencional');ac.salvar(self.base,self.p,self.c,'ESTRUTURAL','EM_ABERTO',esperada=uid);hs=ac.historico(self.base,self.ig);self.assertEqual(len(hs),2);self.assertEqual(hs[1]['anterior'],uid);self.assertEqual(hs[1]['estado_anterior'],'RESOLVIDO');self.assertEqual(hs[0]['observacao'],'Separação intencional')
    def test_historico_imutavel(self):
        self.resolver()
        with sqlite3.connect(self.base) as c:
            with self.assertRaises(sqlite3.IntegrityError):c.execute('DELETE FROM IGD_ACOMPANHAMENTO')
    def test_concorrencia_nao_sobrescreve(self):
        self.resolver()
        with self.assertRaises(ValueError):self.resolver()
        self.assertEqual(len(ac.historico(self.base,self.ig)),1)
    def test_backup_completo_verificado(self):
        self.resolver();p=next(self.dir.glob('*antes_acompanhamento*.gpkg'))
        with sqlite3.connect(p) as c:self.assertEqual(c.execute('PRAGMA quick_check').fetchone()[0],'ok');self.assertFalse(c.execute("SELECT 1 FROM sqlite_master WHERE name='IGD_ACOMPANHAMENTO'").fetchone())
    def test_relacoes_integras(self):
        self.resolver()
        with sqlite3.connect(self.base) as c:self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())
    def test_reabertura_base_recupera_resolvido(self):self.resolver();p=reabrir(self.base);h=ac.indice(self.base,p)[self.c['uid'],'ESTRUTURAL'];self.assertEqual(ac.estado(h,self.c,p,'ESTRUTURAL'),'RESOLVIDO')
    def test_perspectiva_separada(self):self.resolver();self.assertNotIn((self.c['uid'],'TODAS_VALVULAS_ABERTAS'),ac.indice(self.base,self.p))
    def test_situacao_invalida(self):
        with self.assertRaises(ValueError):ac.salvar(self.base,self.p,self.c,'ESTRUTURAL','CORRIGIDO_AUTOMATICAMENTE')
    def test_filtro_em_aberto_padrao(self):self.resolver();j=self.painel();self.assertEqual(j.fila.currentData(),'EM_ABERTO');self.assertNotIn(self.c['uid'],[c['uid'] for c in j.visiveis])
    def test_filtro_resolvidas_e_todas(self):self.resolver();j=self.painel();j.fila.setCurrentIndex(j.fila.findData('RESOLVIDAS'));self.assertIn(self.c['uid'],[c['uid'] for c in j.visiveis]);j.fila.setCurrentIndex(j.fila.findData('TODOS'));self.assertIn(self.c['uid'],[c['uid'] for c in j.visiveis])
    def test_resultado_manter_nao_resolve_implicitamente(self):op.salvar(self.base,self.p,self.c,'ESTRUTURAL',resultado='MANTER CONFIGURAÇÃO ATUAL');j=self.painel();self.assertIn(self.c['uid'],[c['uid'] for c in j.visiveis]);self.assertEqual(ac.indice(self.base,self.p),{})
    def test_botao_um_clique_sem_confirmacao(self):
        j=self.painel();uid=j.atual['uid']
        with patch('qgis.PyQt.QtWidgets.QMessageBox.question') as msg:self.assertTrue(j.resultado_analise.resolver_ocorrencia());msg.assert_not_called()
        self.assertNotIn(uid,[c['uid'] for c in j.visiveis])
    def test_resolver_e_proxima_preserva_filtros(self):
        j=self.painel();ids=[c['uid'] for c in j.visiveis];antes=j.editor_filtros.configuracao();modo=j.modo.currentData();j.resultado_analise.resolver_proxima_botao.click();self.assertEqual(j.atual['uid'],ids[1]);self.assertEqual(j.editor_filtros.configuracao(),antes);self.assertEqual(j.modo.currentData(),modo)
    def test_ui_reabrir(self):self.resolver();j=self.painel();j.fila.setCurrentIndex(j.fila.findData('RESOLVIDAS'));j.selecionar_uid(self.c['uid']);self.assertEqual(j.resultado_analise.resolver_botao.text(),'Reabrir investigação');self.assertTrue(j.resultado_analise.resolver_ocorrencia());self.assertEqual(ac.indice(self.base,self.p)[self.c['uid'],'ESTRUTURAL']['estado'],'EM_ABERTO')
    def test_nota_opcional_preservada(self):j=self.painel();uid=j.atual['uid'];j.resultado_analise.nota_acomp.setText('Sem necessidade de conexão');self.assertTrue(j.resultado_analise.resolver_ocorrencia());self.assertEqual(ac.indice(self.base,self.p)[uid,'ESTRUTURAL']['observacao'],'Sem necessidade de conexão')
    def test_nota_pendente_cancelar_nao_perde(self):
        from qgis.PyQt.QtWidgets import QMessageBox
        j=self.painel();f=j.resultado_analise;f.nota_acomp.setText('Rascunho')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel):self.assertFalse(f.resolver_edicoes())
        self.assertEqual(f.nota_acomp.text(),'Rascunho');f.nota_acomp.clear()
    def test_observacao_somente_salva_sem_criar_resultado(self):j=self.painel();f=j.resultado_analise;uid=f.caso['uid'];f.nota_acomp.setText('Primeira observação');self.assertTrue(f.salvar());self.assertEqual(ac.indice(self.base,self.p)[uid,'ESTRUTURAL']['estado'],'EM_ABERTO');self.assertEqual(op.historico(self.base,self.ig),[])
    def test_relatorio_todas_separa_resultado_situacao(self):self.resolver();d=rel.snapshot(self.base,self.p,[self.c],'ESTRUTURAL',{});self.assertEqual(d['ocorrencias'][0]['resultado'],'PENDENTE');self.assertEqual(d['ocorrencias'][0]['acompanhamento'],'RESOLVIDO')
    def test_relatorio_excluir_resolvidas(self):self.resolver();self.assertEqual(rel.snapshot(self.base,self.p,[self.c],'ESTRUTURAL',dict(situacao_acompanhamento='EM_ABERTO'))['ocorrencias'],[])
    def test_relatorio_somente_resolvidas(self):self.resolver();d=rel.snapshot(self.base,self.p,[self.c],'ESTRUTURAL',dict(situacao_acompanhamento='RESOLVIDAS',historico=True));self.assertEqual(d['acompanhamento_contagens'],{'RESOLVIDO':1});self.assertEqual(len(d['ocorrencias'][0]['historico_acomp']),1)
    def novo(self):
        p=fixture.clonar(self.p);p['resultado']['meta']['uid']='nova-execucao-sintetica';p['resultado']['meta']['topologia']['execucao_uid']='nova-topologia-sintetica';return p
    def test_versao_equivalente_nao_reabre(self):self.resolver();p=self.novo();r=ac.comparar(self.base,self.p,[self.c],p,catalogar(p),'ESTRUTURAL');self.assertEqual(r['linhas'][0]['classe'],'EQUIVALENTE')
    def test_mudanca_relevante_exige_reavaliacao(self):self.resolver();p=self.novo();i=self.c['wg_ids'][0];p['topologia']['modelo']['elementos'][i]['ativo']=False;r=ac.comparar(self.base,self.p,[self.c],p,catalogar(p),'ESTRUTURAL');self.assertEqual(r['linhas'][0]['classe'],'REAVALIACAO_NECESSARIA')
    def test_mudanca_metadado_irrelevante(self):self.resolver();p=self.novo();p['topologia']['modelo']['banco']='outro_caminho';p['resultado']['meta']['nome']='Outro nome de exibição';r=ac.comparar(self.base,self.p,[self.c],p,catalogar(p),'ESTRUTURAL');self.assertEqual(r['linhas'][0]['classe'],'EQUIVALENTE')
    def test_contexto_alterado_nao_mantem_resolvido(self):self.resolver();h=ac.indice(self.base,self.p)[self.c['uid'],'ESTRUTURAL'];p=self.novo();p['topologia']['modelo']['elementos'][self.c['wg_ids'][0]]['ativo']=False;self.assertEqual(ac.estado(h,self.c,p,'ESTRUTURAL'),'REAVALIACAO_NECESSARIA')
    def test_nova_execucao_nao_herda_silenciosamente(self):self.resolver();p=self.novo();self.assertEqual(ac.indice(self.base,p),{})
    def test_comparacao_preserva_origem_e_reconciliacao(self):
        self.resolver(observacao='Separação intencional');p=self.novo();cs=catalogar(p);r=ac.comparar(self.base,self.p,[self.c],p,cs,'ESTRUTURAL');dest=self.dir/'nova.gpkg';salvar_gpkg(p,dest);ac.aplicar_comparacao(dest,p,cs,'ESTRUTURAL',r);hs=ac.historico(dest,p['resultado']['meta']['uid']);self.assertEqual(hs[0]['estado'],'RESOLVIDO');self.assertEqual(hs[0]['observacao'],'Separação intencional');self.assertEqual(len(ac.historico(self.base,self.ig)),1)


if __name__=='__main__':unittest.main()
