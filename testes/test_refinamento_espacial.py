"""Refinamento sem formalidades: as barreiras técnicas continuam obrigatórias."""
import copy,json,unittest
from pathlib import Path
from unittest.mock import patch
import test_deteccao_espacial as f
from auditoria_topologica_watergems import deteccao_espacial as det,referencia_espacial as ref,bases
from auditoria_topologica_watergems.arquivos import hash_arquivo

class ContratoTecnicoTest(unittest.TestCase):
    def setUp(self):self.t=f.topologia();self.r=f.comparar(self.t['modelo']);self.md=f.metadados()
    def test_sem_responsavel_sem_aprovacao_sem_anexo(self):
        r=det.confirmar_assistida(self.t,self.r,self.md);self.assertEqual(r['validacao']['estado'],'VALIDADO');self.assertEqual(r['validacao']['responsavel'],'');self.assertNotIn('anexo',r['validacao'])
    def test_checkbox_antigo_nao_altera_resultado(self):
        for valor in (False,True):self.assertEqual(det.confirmar_assistida(self.t,self.r,self.md,valor)['validacao']['estado'],'VALIDADO')
    def test_nome_nao_supera_falta_crs(self):
        with self.assertRaises(ValueError):det.confirmar_assistida(self.t,self.r,f.metadados(None),True,'Nome')
    def test_crs_invalido(self):
        self.r['crs']='EPSG:4326'
        with self.assertRaises(ValueError):det.confirmar_assistida(self.t,self.r,self.md)
    def test_unidade_incompativel(self):
        self.r['hipoteses'][0]['unidade']='PE_INTERNACIONAL'
        with self.assertRaises(ValueError):det.confirmar_assistida(self.t,self.r,self.md)
    def test_fator_inconclusivo(self):
        self.r['fator_recomendado']=None
        with self.assertRaises(ValueError):det.confirmar_assistida(self.t,self.r,self.md)
    def test_modelo_alterado(self):
        self.t['modelo']['cenario']=999
        with self.assertRaises(ValueError):det.confirmar_assistida(self.t,self.r,self.md)
    def test_crs_observado_sem_documento_anexado(self):
        r=det.confirmar_assistida(self.t,self.r,f.metadados(None),documento={'crs':'EPSG:31983'});self.assertEqual(r['validacao']['origem_crs'],'CRS_COMPLEMENTAR_INFORMADO');self.assertTrue(r['fonte'])
    def test_sem_crs_observado_permanece_pendente(self):self.assertEqual(det.avaliar(self.t,self.r,f.metadados(None))['estado'],'PENDENTE')
    def test_reuso_preserva_campos_historicos(self):
        r=det.confirmar_assistida(self.t,self.r,self.md,True,'Pessoa no registro antigo');r['validacao']['aprovacao_antiga']=True;e=dict(referencia=r,contexto=ref.contexto_modelo(self.t['modelo']),modelo=self.t['modelo']['projeto'],arquivo='base-anterior.gpkg',sha256='controle');novo=ref.referencia_reutilizada(self.t['modelo'],e);self.assertEqual(novo['validacao']['validacao_anterior']['responsavel'],'Pessoa no registro antigo');self.assertTrue(novo['validacao']['validacao_anterior']['aprovacao_antiga'])

class PersistenciaSemFormalidadesTest(unittest.TestCase):
    def setUp(self):self.f=f.PersistenciaAssistidaTest();self.f.setUp()
    def tearDown(self):self.f.tearDown()
    def test_nova_versao_sem_anexo_nem_nome(self):
        t=self.f.t;r=det.confirmar_assistida(t,f.comparar(t['modelo']),f.metadados());antes=hash_arquivo(self.f.base);dest=ref.salvar_referencia(self.f.base,self.f.p/'verificada.gpkg',r);m=bases.metadados(dest);self.assertEqual(m['anterior'],t['meta_base']['uuid']);self.assertEqual(ref.estado_referencia(m['referencia_espacial'],t['modelo'])['estado'],'VALIDADO');self.assertEqual(hash_arquivo(self.f.base),antes);self.assertNotEqual(m['uuid'],t['meta_base']['uuid'])
    def test_cancelamento_nao_modifica_origem(self):
        r=det.confirmar_assistida(self.f.t,f.comparar(self.f.t['modelo']),f.metadados());antes=hash_arquivo(self.f.base);dest=self.f.p/'cancelada.gpkg'
        with self.assertRaises(InterruptedError):ref.salvar_referencia(self.f.base,dest,r,lambda:True)
        self.assertEqual(hash_arquivo(self.f.base),antes);self.assertFalse(dest.exists())

class FluxoSimplesTest(unittest.TestCase):
    def setUp(self):self.f=f.AssistenteUITest();self.f.setUp();self.a=self.f.a
    def tearDown(self):self.f.tearDown()
    def test_sem_controles_administrativos(self):
        for campo in ('responsavel','aprovar','confirmar_campos'):self.assertFalse(hasattr(self.a,campo))
    def test_avancados_recolhidos(self):self.assertFalse(self.a.avancados.isChecked());self.assertFalse(self.a.meta_avancado.isChecked());self.assertFalse(self.a.campos_avancado.isChecked())
    def test_progresso_somente_durante_operacao(self):self.a.terminou();self.assertTrue(self.a.barra.isHidden())
    def test_fim_do_assistente_oculta_cancelamento_no_pai(self):
        self.a.pai.ocupado=True;self.a.pai.atualizar_acoes();self.assertFalse(self.a.pai.cancelar_botao.isHidden());self.a.terminou();self.assertTrue(self.a.pai.cancelar_botao.isHidden())
    def test_pendencia_nao_abre_destino(self):
        self.a.metadados=f.metadados(None)
        with patch('auditoria_aplicacao.assistente_espacial.QFileDialog.getSaveFileName') as escolher,patch('auditoria_aplicacao.assistente_espacial.QMessageBox.warning'):self.a.salvar();escolher.assert_not_called()
    def test_selecao_de_campos_sem_checkbox(self):
        from qgis.PyQt.QtWidgets import QComboBox
        c=QComboBox();c.addItem('id','id');self.a.combos={'r':c};self.a.pagina(1)
        with patch.object(self.a,'executar') as executar:self.a.proximo();executar.assert_called_once()
    def test_texto_do_resultado_sem_codigo_interno(self):self.a.atualizar_avaliacao();self.assertIn('pronto para salvar',self.a.avaliacao.text());self.assertNotIn('APTO_PARA',self.a.avaliacao.text())

class RegistrosLegadosSemFormalidadesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_decisoes_topologicas as legado
        cls.legado=legado.DecisoesTest;cls.legado.setUpClass()
    @classmethod
    def tearDownClass(cls):cls.legado.tearDownClass()
    def setUp(self):
        import test_decisoes_topologicas as legado
        self.f=legado.DecisoesTest();self.f.setUp()
    def tearDown(self):self.f.tearDown()
    def test_conclusao_fundamentada_sem_operador(self):
        from auditoria_topologica_watergems import decisoes as db
        self.f.decisao(conclusao='DESCONEXÃO INTENCIONAL',justificativa='Separação no exemplo',responsavel='',fonte=db.FONTES[0],natureza='DOCUMENTAL',evidencia='Exemplo sintético');self.assertEqual(db.historico(self.f.base,self.f.ig,self.f.c['uid'],db.MODOS[0])[-1]['responsavel'],'')
    def test_proposta_sem_operador_ou_checkbox_administrativo(self):
        from auditoria_topologica_watergems import decisoes as db
        uid,h=self.f.proposta(responsavel='',evidencia='');uid,h=self.f.proposta(prop_uid=uid,esperada=h,situacao='PROPOSTA_PARA_APROVACAO',responsavel='',evidencia='');uid,h=self.f.proposta(prop_uid=uid,esperada=h,situacao='APROVADA',responsavel='',evidencia='',confirmacao=False);self.assertEqual(db.propostas(self.f.base,self.f.ig)[0]['atual']['responsavel'],'')

if __name__=='__main__':unittest.main()
