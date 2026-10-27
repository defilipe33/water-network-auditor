"""Decisões, propostas, concorrência e confrontos em cópias de bases sintéticas."""
import copy
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import test_integracao_investigativa as fixture
from test_auditoria_fronteiras import APP
from qgis.PyQt.QtWidgets import QMessageBox
from auditoria_topologica_watergems.diagnosticos import catalogar,MODOS
from auditoria_topologica_watergems.saidas_integracao import salvar_gpkg,reabrir
from auditoria_topologica_watergems.arquivos import hash_arquivo
from auditoria_topologica_watergems import decisoes as db
from auditoria_topologica_watergems.comparacao_decisoes import comparar,salvar_comparacao,avaliar_proposta,salvar_validacao
from auditoria_topologica_watergems.painel_diagnosticos import abrir_diagnosticos
from auditoria_topologica_watergems.topologia import analisar


def clonar(p):
    return dict(p,resultado=copy.deepcopy(p['resultado']),dossie=copy.deepcopy(p['dossie']),
        topologia=dict(p['topologia'],modelo=copy.deepcopy(p['topologia']['modelo'])))


class DecisoesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=fixture.IntegracaoPersistidaTest();cls.fixture.setUp();cls.pacote=cls.fixture.executar()
        cls.original=salvar_gpkg(cls.pacote,cls.fixture.p/'original.gpkg')
    @classmethod
    def tearDownClass(cls):cls.fixture.tearDown()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True);self.dir=Path(self.tmp.name);self.base=self.dir/'base.gpkg';shutil.copyfile(self.original,self.base)
        self.p=clonar(self.pacote);self.c=next(c for c in catalogar(self.p) if c['tipo']=='LOCAL');self.ig=self.p['resultado']['meta']['uid'];self.janelas=[]
    def tearDown(self):
        for j in self.janelas:
            if j.analise.tem_edicoes():j.analise.carregar(j.analise.caso,j.analise.modo,True)
            j.close()
        self.tmp.cleanup()
    def decisao(self,**kw):return db.salvar_decisao(self.base,self.p,self.c,MODOS[0],**kw)
    def proposta(self,**kw):
        args=dict(tipo='Conectar dois nós',descricao='Ligação em exemplo sintético',justificativa='Ensaio controlado',requisitos='Conferir ligação explícita',responsavel='Teste',evidencia='Evidência sintética',elementos=[1,3],elementos_confirmados=True)
        args.update(kw);return db.salvar_proposta(self.base,self.p,self.c,MODOS[0],**args)
    def painel(self):
        j=abrir_diagnosticos(self.p,self.base);self.janelas.append(j);APP.processEvents();return j
    def test_leitura_base_antiga_nao_migra(self):
        h=hash_arquivo(self.base);self.assertEqual(db.historico(self.base,self.ig,self.c['uid'],MODOS[0]),[]);self.assertEqual(hash_arquivo(self.base),h)
    def test_primeira_extensao_tem_backup_integro(self):
        self.decisao();bs=list(self.dir.glob('*antes_decisoes*.gpkg'));self.assertEqual(len(bs),1)
        with sqlite3.connect(bs[0]) as con:self.assertEqual(con.execute('pragma integrity_check').fetchone()[0],'ok');self.assertFalse(db.existe(con))
        with sqlite3.connect(self.base) as con:self.assertFalse(con.execute('pragma foreign_key_check').fetchall())
    def test_historico_decisoes_e_reabertura(self):
        uid=self.decisao(justificativa='Observação inicial');v=self.decisao(situacao='EM_ANALISE',conclusao='NECESSITA VERIFICAÇÃO DE CAMPO',esperada=uid)
        hs=db.historico(self.base,self.ig,self.c['uid'],MODOS[0]);self.assertEqual(hs[-1]['anterior'],uid);self.assertEqual(hs[-1]['rev_uid'],v);self.assertEqual(len(hs),2);self.assertEqual(reabrir(self.base)['dossie'],self.p['dossie'])
    def test_justificativa_definitiva_obrigatoria(self):
        with self.assertRaises(ValueError):self.decisao(conclusao='DESCONEXÃO INTENCIONAL')
    def test_hipotese_nao_vira_confirmacao(self):
        with self.assertRaises(ValueError):self.decisao(conclusao='CONEXÃO FALTANTE CONFIRMADA',justificativa='Teste',responsavel='Teste',fonte=db.FONTES[0],natureza='HIPOTESE',evidencia='Hipótese')
    def test_situacao_independente_da_conclusao(self):
        self.decisao(situacao='VERIFICADO',conclusao='DESCONEXÃO INTENCIONAL',justificativa='Separação no exemplo controlado',responsavel='Teste',fonte=db.FONTES[2],natureza='DOCUMENTAL',evidencia='Desenho sintético do teste')
        h=db.historico(self.base,self.ig,self.c['uid'],MODOS[0])[-1];self.assertEqual(h['situacao'],'VERIFICADO');self.assertEqual(h['conclusao'],'DESCONEXÃO INTENCIONAL')
    def test_perspectivas_independentes(self):
        self.decisao();self.assertFalse(db.historico(self.base,self.ig,self.c['uid'],MODOS[1]))
    def test_concorrencia_decisao(self):
        self.decisao()
        with self.assertRaisesRegex(ValueError,'outra sessão'):self.decisao()
        self.assertEqual(len(db.historico(self.base,self.ig,self.c['uid'],MODOS[0])),1)
    def test_contexto_mudado_nao_herda(self):
        u=self.decisao();self.p['topologia']['modelo']['elementos'][1]['ativo']=False
        with self.assertRaisesRegex(ValueError,'Contexto técnico mudou'):self.decisao(esperada=u)
    def test_historico_imutavel(self):
        self.decisao()
        with sqlite3.connect(self.base) as con:
            with self.assertRaises(sqlite3.IntegrityError):con.execute("update IGD_REVISOES set situacao='VERIFICADO'")
            with self.assertRaises(sqlite3.IntegrityError):con.execute('delete from IGD_REVISOES')
    def test_observacao_nao_cria_proposta(self):self.decisao(justificativa='Investigar');self.assertFalse(db.propostas(self.base,self.ig))
    def test_proposta_incompleta_rascunho(self):
        self.proposta(elementos=[],elementos_confirmados=False);self.assertEqual(db.propostas(self.base,self.ig)[0]['atual']['incompleta'],1)
    def test_nova_proposta_nao_pode_nascer_aprovada(self):
        with self.assertRaises(ValueError):self.proposta(situacao='APROVADA',confirmacao=True)
    def test_elemento_inexistente_bloqueado(self):
        with self.assertRaises(ValueError):self.proposta(elementos=[99999])
    def test_concorrencia_proposta(self):
        uid,h=self.proposta()
        with self.assertRaisesRegex(ValueError,'outra sessão'):self.proposta(prop_uid=uid,esperada='obsoleta')
    def test_aprovacao_e_aplicacao_nao_sao_validacao(self):
        uid,h=self.proposta();uid,h=self.proposta(prop_uid=uid,esperada=h,situacao='PROPOSTA_PARA_APROVACAO')
        with self.assertRaises(ValueError):self.proposta(prop_uid=uid,esperada=h,situacao='APROVADA')
        uid,h=self.proposta(prop_uid=uid,esperada=h,situacao='APROVADA',confirmacao=True)
        uid,h=self.proposta(prop_uid=uid,esperada=h,situacao='APLICACAO_INFORMADA',confirmacao=True)
        self.assertEqual(db.propostas(self.base,self.ig)[0]['atual']['situacao'],'APLICACAO_INFORMADA')
        with self.assertRaises(ValueError):self.proposta(prop_uid=uid,esperada=h,situacao='VALIDADA',confirmacao=True)
    def test_escopo_aprovado_nao_muda_silenciosamente(self):
        uid,h=self.proposta();uid,h=self.proposta(prop_uid=uid,esperada=h,situacao='PROPOSTA_PARA_APROVACAO');uid,h=self.proposta(prop_uid=uid,esperada=h,situacao='APROVADA',confirmacao=True)
        with self.assertRaises(ValueError):self.proposta(prop_uid=uid,esperada=h,situacao='APLICACAO_INFORMADA',confirmacao=True,descricao='Mudança indevida')
    def test_comparacao_identica_permanece(self):
        r=comparar(self.p,self.p);self.assertEqual(set(r['contagens']),{'PERMANECE'})
    def test_comparacao_cenario_diferente_reavalia(self):
        n=clonar(self.p);n['topologia']['modelo']['cenario']=999;r=comparar(self.p,n);self.assertIn('REQUER REAVALIAÇÃO',r['contagens'])
    def test_ids_reutilizados_com_label_diferente_incerto(self):
        n=clonar(self.p);n['topologia']['modelo']['elementos'][1]['label']='outro';r=comparar(self.p,n);self.assertIn('CORRESPONDÊNCIA INCERTA',r['contagens'])
    def test_grafo_alterado_nao_transfere_decisao(self):
        n=clonar(self.p);n['topologia']['modelo']['elementos'][1]['ativo']=False;r=comparar(self.p,n);self.assertIn('ALTERADA',r['contagens']);self.assertTrue(any(l['reavaliar'] for l in r['linhas']))
    def test_comparacao_persistente(self):
        r=comparar(self.p,self.p);salvar_comparacao(self.base,self.p,r)
        with sqlite3.connect(self.base) as con:self.assertEqual(con.execute('select count(*) from IGD_COMPARACOES').fetchone()[0],1)
    def test_validacao_produz_evidencias_nao_aprova(self):
        uid,h=self.proposta();pr=db.propostas(self.base,self.ig)[0];r=avaliar_proposta(pr,self.p,self.p)
        self.assertEqual(r['resultado'],'LIGACAO_DIRETA_NAO_OBSERVADA');self.assertEqual(db.propostas(self.base,self.ig)[0]['atual']['situacao'],'RASCUNHO')
    def test_validacao_conexao_direta_sintetica(self):
        self.proposta();pr=db.propostas(self.base,self.ig)[0];n=clonar(self.p)
        e=copy.deepcopy(n['topologia']['modelo']['elementos'][10]);e['id']=12;e['uid']=e['uid']+'-12';e['topologia']={'HMITopologyStartNodeID':1,'HMITopologyStopNodeID':3};n['topologia']['modelo']['elementos'][12]=e
        n['topologia']['estrutural']=analisar(n['topologia']['modelo']);r=avaliar_proposta(pr,self.p,n)
        self.assertIn(12,r['conexoes_diretas_depois']);self.assertEqual(r['resultado'],'LIGACAO_DIRETA_OBSERVADA')
    def test_salvar_validacao_exige_aplicacao_informada(self):
        self.proposta();pr=db.propostas(self.base,self.ig)[0]
        with self.assertRaises(ValueError):salvar_validacao(self.base,self.p,pr,avaliar_proposta(pr,self.p,self.p))
    def test_formulario_mesmo_contexto_preserva_rascunho(self):
        j=self.painel();j.analise.justificativa.setPlainText('Rascunho não salvo');j.selecionar();self.assertEqual(j.analise.justificativa.toPlainText(),'Rascunho não salvo')
    def test_cancelar_troca_perspectiva_preserva_rascunho(self):
        j=self.painel();j.analise.justificativa.setPlainText('Não perder')
        with patch('auditoria_topologica_watergems.form_decisao.QMessageBox.question',return_value=QMessageBox.Cancel):j.modo.setCurrentIndex(1)
        self.assertEqual(j.modo.currentData(),MODOS[0]);self.assertEqual(j.analise.justificativa.toPlainText(),'Não perder')
    def test_cancelar_filtro_preserva_ocorrencia(self):
        j=self.painel();uid=j.atual['uid'];j.analise.justificativa.setPlainText('Não perder')
        with patch('auditoria_topologica_watergems.form_decisao.QMessageBox.question',return_value=QMessageBox.Cancel):j.busca.setText('nunca-encontrar')
        self.assertEqual(j.atual['uid'],uid);self.assertEqual(j.busca.text(),'');self.assertTrue(j.analise.tem_edicoes())
    def test_cancelar_fechamento(self):
        j=self.painel();j.analise.justificativa.setPlainText('Não perder')
        with patch('auditoria_topologica_watergems.form_decisao.QMessageBox.question',return_value=QMessageBox.Cancel):self.assertFalse(j.close())
        self.assertTrue(j._ativo)
    def test_descarte_consciente(self):
        j=self.painel();j.analise.justificativa.setPlainText('Descartar')
        with patch('auditoria_topologica_watergems.form_decisao.QMessageBox.question',return_value=QMessageBox.Discard):self.assertTrue(j.analise.resolver_edicoes())
        self.assertFalse(j.analise.tem_edicoes())
    def test_formulario_exige_escolha_explicita(self):
        j=self.painel();self.assertIsNone(j.analise.conclusao.currentData())
        with patch('auditoria_topologica_watergems.form_decisao.QMessageBox.warning'):self.assertFalse(j.analise.salvar_decisao())
    def test_salvar_e_reabrir_formulario(self):
        j=self.painel();j.analise.conclusao.setCurrentIndex(j.analise.conclusao.findData('NÃO AVALIADO'));j.analise.justificativa.setPlainText('Observação salva')
        self.assertTrue(j.analise.salvar_decisao());j.analise.carregar(j.atual,MODOS[0],True);self.assertEqual(j.analise.justificativa.toPlainText(),'Observação salva')
    def test_legenda_permanente_e_filtros_recolhiveis(self):
        j=self.painel();j.mostrar_filtros.setChecked(False);self.assertFalse(j.bloco_filtros.isVisible());self.assertTrue(j.legenda.isVisible());j.exibir_legenda.setChecked(False);self.assertFalse(j.legenda.isVisible())
    def test_ids_decimais_nao_sao_arredondados(self):
        with self.assertRaises(ValueError):self.proposta(elementos=[1.000001,3])
    def test_valvula_sem_link_permanece_incompleta(self):
        uid,h=self.proposta(tipo='Corrigir vínculo de válvula',elementos=[2]);self.assertEqual(db.propostas(self.base,self.ig)[0]['atual']['incompleta'],1)
        with self.assertRaises(ValueError):self.proposta(tipo='Corrigir vínculo de válvula',elementos=[2],prop_uid=uid,esperada=h,situacao='PROPOSTA_PARA_APROVACAO')
    def test_hipotese_operacional_bloqueada_antes_de_gravar(self):
        h=hash_arquivo(self.base)
        with self.assertRaises(ValueError):db.salvar_decisao(self.base,self.p,self.c,'ESTADOS_DO_CENARIO')
        self.assertEqual(hash_arquivo(self.base),h)
    def test_ausencia_nao_equivale_a_correcao(self):
        cs=catalogar(self.p)
        with patch('auditoria_topologica_watergems.comparacao_decisoes.catalogar',side_effect=[cs,[]]):r=comparar(self.p,self.p)
        self.assertEqual(set(r['contagens']),{'NÃO OBSERVADA NA NOVA EXECUÇÃO'});self.assertFalse(any('resolvida' in l for l in r['linhas']))
    def test_nova_ocorrencia(self):
        cs=catalogar(self.p)
        with patch('auditoria_topologica_watergems.comparacao_decisoes.catalogar',side_effect=[[],cs]):r=comparar(self.p,self.p)
        self.assertEqual(set(r['contagens']),{'NOVA OCORRÊNCIA'})
    def test_reconciliacao_nao_copia_conclusao(self):
        from auditoria_topologica_watergems.comparacao_decisoes import reconciliar
        rev=self.decisao(responsavel='Teste');r=comparar(self.p,self.p);salvar_comparacao(self.base,self.p,r)
        item=next(i for i,l in enumerate(r['linhas']) if self.c['uid'] in l['destinos']);reconciliar(self.base,r['uid'],item,self.c['uid'],rev,'Teste','Equivalência sintética','Ensaio')
        self.assertEqual(len(db.historico(self.base,self.ig,self.c['uid'],MODOS[0])),1)
        with sqlite3.connect(self.base) as con:self.assertEqual(con.execute('select count(*) from IGD_RECONCILIACOES').fetchone()[0],1)
    def aplicada(self):
        uid,h=self.proposta()
        for sit in ('PROPOSTA_PARA_APROVACAO','APROVADA','APLICACAO_INFORMADA','VALIDACAO_PENDENTE'):
            uid,h=self.proposta(prop_uid=uid,esperada=h,situacao=sit,confirmacao=sit in ('APROVADA','APLICACAO_INFORMADA'))
        return uid,h,db.propostas(self.base,self.ig)[0]
    def test_validacao_negativa_nao_pode_ser_aprovada(self):
        uid,h,pr=self.aplicada();r=avaliar_proposta(pr,self.p,self.p);v=salvar_validacao(self.base,self.p,pr,r)
        with self.assertRaises(ValueError):self.proposta(prop_uid=uid,esperada=h,situacao='VALIDADA',confirmacao=True,validacao_uid=v)
    def test_validacao_positiva_exige_acao_humana(self):
        uid,h,pr=self.aplicada();n=clonar(self.p);e=copy.deepcopy(n['topologia']['modelo']['elementos'][10]);e['id']=12;e['uid']+='12';e['topologia']={'HMITopologyStartNodeID':1,'HMITopologyStopNodeID':3};n['topologia']['modelo']['elementos'][12]=e;n['topologia']['estrutural']=analisar(n['topologia']['modelo'])
        r=avaliar_proposta(pr,self.p,n);v=salvar_validacao(self.base,self.p,pr,r)
        with self.assertRaises(ValueError):self.proposta(prop_uid=uid,esperada=h,situacao='VALIDADA',validacao_uid=v)
        self.proposta(prop_uid=uid,esperada=h,situacao='VALIDADA',confirmacao=True,validacao_uid=v)
        self.assertEqual(db.propostas(self.base,self.ig)[0]['atual']['situacao'],'VALIDADA')
    def test_salvar_navegacao_persiste_decisao(self):
        j=self.painel();a=j.analise;a.conclusao.setCurrentIndex(a.conclusao.findData('NÃO AVALIADO'));a.justificativa.setPlainText('Salvar na troca')
        with patch('auditoria_topologica_watergems.form_decisao.QMessageBox.question',return_value=QMessageBox.Save):j.modo.setCurrentIndex(1)
        self.assertTrue(db.historico(self.base,self.ig,self.c['uid'],MODOS[0]));self.assertEqual(j.modo.currentData(),MODOS[1])
    def test_exportacao_relacional_xlsx_shp(self):
        from auditoria_topologica_watergems.exportacao_decisoes import exportar_acompanhamento
        from validar_estrutura_xlsx import validar_xlsx
        self.decisao(justificativa='Acompanhamento');self.proposta()
        pasta=exportar_acompanhamento(self.base,self.p,self.dir/'exportacao',gpkg=True,shp=True)
        self.assertTrue(validar_xlsx(pasta/'ACOMPANHAMENTO.xlsx')['valido'])
        self.assertTrue((pasta/'SHP/DECISOES_OCORRENCIAS.prj').exists())
        with sqlite3.connect(pasta/'ACOMPANHAMENTO.gpkg') as con:self.assertEqual(con.execute('select count(*) from IGD_REVISOES').fetchone()[0],1);self.assertFalse(con.execute('pragma foreign_key_check').fetchall())
    def test_mesmos_tubos_em_locais_distintos_nao_sao_confundidos(self):
        cs=[copy.deepcopy(self.c),copy.deepcopy(self.c)];cs[1]['uid']='outro-local';cs[1]['chave']='outra-composicao-de-eventos'
        with patch('auditoria_topologica_watergems.comparacao_decisoes.catalogar',side_effect=[cs,cs]):r=comparar(self.p,self.p)
        self.assertEqual(r['contagens'],{'PERMANECE':2})
    def test_projetos_distintos_sao_incertos(self):
        n=clonar(self.p);n['topologia']['modelo']['projeto']='outro-modelo';r=comparar(self.p,n)
        self.assertEqual(set(r['contagens']),{'CORRESPONDÊNCIA INCERTA'})
    def test_reabertura_recupera_propostas_e_evidencias(self):
        uid,h,pr=self.aplicada();v=salvar_validacao(self.base,self.p,pr,avaliar_proposta(pr,self.p,self.p))
        j=self.painel();j.analise.seletor.setCurrentIndex(j.analise.seletor.findData(uid))
        self.assertEqual(j.analise.validacao_uid,v)
    def test_filtro_topologico_independente_do_espacial(self):
        self.decisao(situacao='EM_ANALISE');j=self.painel();j.revisao_topo.setCurrentIndex(j.revisao_topo.findData('EM_ANALISE'))
        self.assertTrue(j.visiveis);self.assertTrue(all(c['revisao']!='EM_ANALISE' for c in j.visiveis))
    def test_legenda_visivel_na_aba_de_decisao(self):
        j=self.painel();j.tabs.setCurrentIndex(1);self.assertTrue(j.legenda.isVisible())
    def test_protege_encerramento_qgis_pelo_bloqueador(self):
        from qgis.gui import QgsMapCanvas
        from unittest.mock import MagicMock
        canvas=QgsMapCanvas();iface=MagicMock()
        with patch('qgis.utils.iface',iface):j=abrir_diagnosticos(self.p,self.base,canvas=canvas)
        self.janelas.append(j);self.assertIsNotNone(j._bloqueador)
        with patch.object(j,'resolver_alteracoes',return_value=False):self.assertFalse(j._bloqueador.allowExit())
        j.close();self.assertTrue(iface.unregisterApplicationExitBlocker.called);canvas.close()


if __name__=='__main__':unittest.main()
