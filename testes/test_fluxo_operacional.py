"""Simula o fluxo do engenheiro; sem dispensar a validação QGIS desktop."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_auditoria_fronteiras import APP,camada,quadrado
from test_locais_investigacao import resultado,evento
from qgis.PyQt.QtCore import Qt,QTimer
from qgis.PyQt.QtWidgets import QMessageBox,QProgressDialog
from qgis.core import QgsProject
from auditoria_fronteiras.interface import AuditoriaFronteirasDialog
from auditoria_fronteiras.estados import Estado
from auditoria_fronteiras import auditar
from auditoria_fronteiras.investigacao import analisar_investigacao,OpcoesLocais
from auditoria_fronteiras.inspecao import texto
from auditoria_fronteiras.persistencia import salvar_execucao,carregar_execucao


class FluxoOperacionalTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.base=Path(self.tmp.name)/'fluxo.gpkg'
        self.projeto=QgsProject()
        self.rede=camada('LineString',['LINESTRING(-2 5,12 5)'],nome='rede livre')
        self.pol=camada('Polygon',[quadrado()],nome='setores livres')
        for c in (self.rede,self.pol):
            self.projeto.addMapLayer(c)
        self.j=AuditoriaFronteirasDialog(projeto=self.projeto)
        for nome in ('warning','critical','information'):
            p=patch('auditoria_fronteiras.interface.QMessageBox.'+nome);p.start();self.addCleanup(p.stop)

    def tearDown(self):
        with patch.object(self.j,'resolver_pendencias',return_value=True):
            if self.j.painel:
                self.j.painel._form_baseline=None
            self.j.close()
        self.projeto.clear();self.tmp.cleanup()

    def marcar(self,tabela,camada):
        linha=next(i for i in range(tabela.rowCount()) if tabela.item(i,0).data(Qt.UserRole)==camada.id())
        tabela.item(linha,0).setCheckState(Qt.Checked)
        for col in (2,3) if tabela is self.j.limites else (2,):
            w=tabela.cellWidget(linha,col);w.setCurrentIndex(w.findData('id'))
        return linha

    def configurar(self):
        self.marcar(self.j.redes,self.rede);self.marcar(self.j.limites,self.pol)
        self.j.agrupar.setChecked(True)

    def concluir(self):
        self.configurar()
        with patch.object(self.j,'confirmar_processamento',return_value=True):
            self.j.executar_auditoria()
        self.assertEqual(self.j.estado,Estado.INSPECIONANDO)
        return self.j.dossie

    def persistir(self):
        d=self.concluir();salvar_execucao(self.base,d)
        with patch('auditoria_fronteiras.fluxos.lembrar'):
            self.j.vincular_base(self.base)
        return d

    def test_abertura_escolha_modo_e_configuracao_pendente(self):
        self.assertEqual(self.j.estado,Estado.SEM_AUDITORIA)
        self.assertTrue(self.j.modalidade.isEnabled())
        self.configurar()
        self.assertEqual(self.j.estado,Estado.CONFIGURANDO)
        self.assertFalse(self.j.modalidade.isEnabled())
        self.assertTrue(self.j.pendente())
        self.assertIn('PENDENTE',self.j.estado_info.text())

    def test_conclui_bloqueia_entradas_mostra_execucao(self):
        d=self.concluir()
        for w in (self.j.abas,self.j.atualizar,self.j.tolerancia,self.j.continuidade,self.j.crs,self.j.agrupar):
            self.assertFalse(w.isEnabled())
        self.assertTrue(self.j.exportar.isEnabled());self.assertTrue(self.j.inspecionar.isEnabled())
        self.assertTrue(self.j.nome_auditoria.isReadOnly())
        self.assertIn(d['execucao_uid'],self.j.origem_info.text())
        self.assertIn(('PROCESSANDO','CONCLUIDO'),self.j.transicoes)

    def test_mutacao_programatica_apos_concluir_e_revertida(self):
        d=self.concluir();antes=texto(d)
        self.j.tolerancia.setValue(5);self.j.agrupar.setChecked(False)
        self.j.limites.item(0,0).setCheckState(Qt.Unchecked)
        self.assertEqual(self.j.tolerancia.value(),.01)
        self.assertTrue(self.j.agrupar.isChecked())
        self.assertEqual(self.j.limites.item(0,0).checkState(),Qt.Checked)
        self.assertEqual(texto(self.j.dossie),antes)

    def test_troca_dropdown_bloqueada_durante_configuracao_e_inspecao(self):
        self.configurar();self.j.modalidade.setCurrentIndex(3)
        self.assertEqual(self.j.modalidade.currentIndex(),0)
        self.concluir();self.j.modalidade.setCurrentIndex(2)
        self.assertEqual(self.j.modalidade.currentIndex(),0)

    def test_click_executar_em_inspecao_nao_recalcula(self):
        self.concluir()
        with patch('auditoria_fronteiras.interface.auditar',side_effect=AssertionError('reexecução indevida')):
            self.j.executar_auditoria()
        self.assertEqual(self.j.estado,Estado.INSPECIONANDO)

    def test_adicionar_boosters_reprocessa_sem_alterar_versao_anterior(self):
        d=self.persistir();antes=texto(d['eventos'])
        self.assertTrue(self.j.iniciar_operacao(3))
        booster=camada('Polygon',[quadrado(2,2,6)],nome='perímetro adicional')
        self.projeto.addMapLayer(booster);self.j.atualizar_camadas();self.marcar(self.j.limites,booster)
        self.assertEqual(self.j.estado,Estado.PREPARANDO_REPROCESSAMENTO)
        self.assertTrue(self.j.pendente())
        def confirmar(*_,**__):
            self.j._plano_operacao=dict(modo='NOVA',destino=str(self.base),confirmado=False)
            return True
        with patch.object(self.j,'mostrar_comparacao',return_value=True),\
             patch.object(self.j,'confirmar_processamento',side_effect=confirmar),\
             patch('auditoria_fronteiras.fluxos.lembrar'),\
             patch('auditoria_fronteiras.interface.auditar',wraps=auditar) as nucleo:
            self.j.executar_auditoria()
        self.assertEqual(nucleo.call_count,1)
        self.assertIn(booster.id(),[c.camada.id() for c in nucleo.call_args.args[1]])
        self.assertEqual(len(self.j.dossie['eventos']),4)
        self.assertNotEqual(self.j.dossie['execucao_uid'],d['execucao_uid'])
        self.assertEqual(texto(carregar_execucao(self.base,d['execucao_uid'])['eventos']),antes)
        self.assertEqual(self.j.estado,Estado.INSPECIONANDO)

    def test_troca_cancelada_preserva_configuracao(self):
        self.configurar();f=self.j.formulario()
        with patch('auditoria_fronteiras.estados.QMessageBox.question',return_value=QMessageBox.Cancel):
            self.assertFalse(self.j.iniciar_operacao(1))
        self.assertEqual(self.j.formulario(),f);self.assertEqual(self.j.estado,Estado.CONFIGURANDO)

    def test_troca_explicita_descarta_somente_com_confirmacao(self):
        self.configurar()
        with patch('auditoria_fronteiras.estados.QMessageBox.question',return_value=QMessageBox.Yes):
            self.assertTrue(self.j.iniciar_operacao(0))
        self.assertFalse(self.j.pendente())
        self.assertEqual(self.j.redes.item(0,0).checkState(),Qt.Unchecked)

    def test_cancelar_escolha_de_contexto_mantem_auditoria_anterior(self):
        d=self.concluir();ids=[c.id() for c in self.j.camadas_geradas]
        with patch.object(self.j,'escolher_auditoria',return_value=False):
            self.assertFalse(self.j.iniciar_operacao(1,usar_ativa=False))
        self.assertIs(self.j.dossie,d);self.assertEqual(self.j.estado,Estado.INSPECIONANDO)
        self.assertEqual([c.id() for c in self.j.camadas_geradas],ids)

    def test_revisao_nao_salva_cancelar_troca_preserva_texto(self):
        d=self.persistir();self.j.abrir_painel();p=self.j.painel
        p.locais.setCurrentIndex(1);p.observacoes.setPlainText('Investigação em andamento')
        with patch('auditoria_fronteiras.painel.QMessageBox.question',return_value=QMessageBox.Cancel):
            self.assertFalse(self.j.iniciar_operacao(0))
        self.assertIs(self.j.dossie,d)
        self.assertTrue(p.tem_edicoes());self.assertEqual(p.observacoes.toPlainText(),'Investigação em andamento')

    def test_salvar_revisao_antes_da_troca(self):
        d=self.persistir();self.j.abrir_painel();p=self.j.painel;p.locais.setCurrentIndex(1)
        uid=p.locais.currentData();p.observacoes.setPlainText('Salvar antes da troca')
        with patch('auditoria_fronteiras.painel.QMessageBox.question',return_value=QMessageBox.Save),\
             patch('auditoria_fronteiras.fluxos.lembrar'):
            self.assertTrue(self.j.iniciar_operacao(0))
        self.assertEqual(next(l for l in carregar_execucao(self.base,d['execucao_uid'])['locais'] if l['uid']==uid)['revisao']['observacoes'],'Salvar antes da troca')

    def test_atualizar_lista_preserva_selecoes_sem_recalcular(self):
        self.configurar();antes=self.j.configuracoes()
        q=camada('Polygon',[quadrado(2,2,6)],nome='booster');self.projeto.addMapLayer(q)
        with patch('auditoria_fronteiras.interface.auditar',side_effect=AssertionError()):
            self.j.atualizar_camadas()
        depois=self.j.configuracoes()
        self.assertEqual([c.camada.id() for c in antes[1]],[c.camada.id() for c in depois[1]])
        self.assertEqual(self.j.limites.rowCount(),2)
        self.assertIn('Nenhum processamento',self.j.status.text())

    def test_atualizar_lista_em_inspecao_nao_muda_formulario(self):
        self.concluir();f=self.j.formulario()
        self.projeto.addMapLayer(camada('Polygon',[quadrado()],nome='booster'))
        self.j.atualizar_camadas()
        self.assertEqual(self.j.formulario(),f)

    def test_configuracao_removida_reporta_erro_sem_publicar(self):
        self.configurar();self.projeto.removeMapLayer(self.rede.id())
        self.j.executar_auditoria();self.assertEqual(self.j.estado,Estado.ERRO)
        self.assertIsNone(self.j.dossie)
        self.j.retomar_configuracao();self.assertEqual(self.j.estado,Estado.CONFIGURANDO)

    def test_cancelar_confirmacao_nao_chama_nucleo(self):
        self.configurar()
        with patch.object(self.j,'mostrar_comparacao',return_value=False),\
             patch('auditoria_fronteiras.interface.auditar') as nucleo:
            self.j.executar_auditoria()
        nucleo.assert_not_called();self.assertEqual(self.j.estado,Estado.CONFIGURANDO)
        self.assertTrue(self.j.pendente())

    def test_resumo_previo_contem_camadas_parametros_e_destino(self):
        self.configurar();redes,limites,p=self.j.configuracoes()
        with patch.object(self.j,'mostrar_comparacao',return_value=False) as resumo:
            self.assertFalse(self.j.confirmar_processamento(redes,limites,p))
        texto_resumo='\n'.join(resumo.call_args.args[1])
        for termo in ('rede livre','setores livres','PERIMETRO','0.01','1.0','busca','extensão','NOVA','Destino','origem'):
            self.assertIn(termo,texto_resumo)

    def test_processamento_bloqueia_reentrada_navegacao_e_exportacao(self):
        self.configurar()
        def simular(*args):
            self.assertEqual(self.j.estado,Estado.PROCESSANDO)
            self.assertFalse(self.j.exportar_geo.isEnabled())
            self.assertFalse(self.j.trocar_operacao.isEnabled())
            self.assertFalse(self.j.iniciar_operacao(0))
            self.j.executar_auditoria()
            self.j.exportar_formatos()
            self.j.abrir_painel()
            return auditar(*args)
        with patch.object(self.j,'confirmar_processamento',return_value=True),\
             patch('auditoria_fronteiras.interface.auditar',side_effect=simular) as nucleo:
            self.j.executar_auditoria()
        self.assertEqual(nucleo.call_count,1)

    def test_falha_nucleo_preserva_execucao_anterior(self):
        d=self.persistir();self.j.iniciar_operacao(3)
        with patch.object(self.j,'preparar_reprocessamento',return_value={'configuracao':d['configuracao']}),\
             patch.object(self.j,'confirmar_processamento',return_value=True),\
             patch('auditoria_fronteiras.interface.auditar',side_effect=RuntimeError('falha demonstrada')):
            self.j.executar_auditoria()
        self.assertIs(self.j.dossie,d);self.assertEqual(self.j.estado,Estado.ERRO)
        self.assertTrue(self.j.exportar.isEnabled());self.j.voltar_inspecao()
        self.assertEqual(self.j.estado,Estado.INSPECIONANDO)

    def test_cancelamento_em_processamento_retorna_configuracao(self):
        self.configurar()
        def cancelar():
            for d in self.j.findChildren(QProgressDialog):
                d.cancel()
        with patch.object(self.j,'confirmar_processamento',return_value=True):
            QTimer.singleShot(0,cancelar);self.j.executar_auditoria()
        self.assertEqual(self.j.estado,Estado.CONFIGURANDO);self.assertIsNone(self.j.dossie)

    def test_zero_eventos_e_conclusao_explicita(self):
        self.configurar()
        self.pol.dataProvider().truncate()
        # Entrada vazia não é igual a uma auditoria sem eventos: usa polígono válido distante.
        from qgis.core import QgsFeature,QgsGeometry
        f=QgsFeature(self.pol.fields());f.setGeometry(QgsGeometry.fromWkt(quadrado(100,100,10)))
        self.pol.dataProvider().addFeatures([f])
        with patch.object(self.j,'confirmar_processamento',return_value=True):
            self.j.executar_auditoria()
        self.assertEqual(self.j.estado,Estado.INSPECIONANDO)
        self.assertEqual(len(self.j.dossie['eventos']),0)
        self.assertIn('nenhuma ocorrência',self.j.status.text())

    def test_painel_anterior_desativado_em_novo_contexto(self):
        self.concluir();self.j.abrir_painel();p=self.j.painel
        novo=deepcopy(self.j.dossie);novo['execucao_uid']='outra-execucao'
        self.j.publicar_auditoria(novo,None)
        self.assertFalse(p._ativo);self.assertFalse(p.isEnabled())
        with patch('auditoria_fronteiras.painel.salvar_revisao') as salvar:
            p.gravar_revisao()
        salvar.assert_not_called()

    def test_selecoes_tecnicas_nao_reutilizadas_apos_publicacao(self):
        self.concluir()
        for c in self.j.camadas_geradas:
            if c.isSpatial():
                c.selectAll()
        novo=deepcopy(self.j.dossie);novo['execucao_uid']='outra-execucao'
        self.j.publicar_auditoria(novo,None)
        self.assertTrue(all(not c.selectedFeatureIds() for c in self.j.camadas_geradas))

    def test_configuracao_visivel_deriva_do_resultado_e_nao_do_formulario(self):
        d=self.concluir();self.j.iniciar_operacao(0)
        self.assertEqual(self.j.redes.item(0,0).checkState(),Qt.Unchecked)
        self.j.publicar_auditoria(d,None)
        self.assertTrue(self.j.abas.isHidden())
        self.assertFalse(self.j.configuracao_ativa.isHidden())
        self.assertTrue(self.j.configuracao_ativa.isReadOnly())
        self.assertIn('Rede: rede livre',self.j.configuracao_ativa.toPlainText())
        self.assertIn('Limite: setores livres',self.j.configuracao_ativa.toPlainText())


class ParametrosIndependentesTest(unittest.TestCase):
    def test_quatro_combinacoes_aprovadas_sem_restricao_arbitraria(self):
        # Semente a (0), b (-4) e c (+4), mesmo tubo/limite. Ordem técnica estável.
        r=resultado([evento('a',0),evento('b',-4),evento('c',4)])
        esperado={(10,5):[1,2],(5,10):[3],(0,5):[1,1,1],(5,0):[1,1,1]}
        for (busca,extensao),tamanhos in esperado.items():
            with self.subTest(busca=busca,extensao=extensao):
                o=OpcoesLocais(True,busca,extensao);o.validar()
                a=analisar_investigacao(r,o)
                self.assertEqual(sorted(len(l['eventos']) for l in a.locais),tamanhos)
                self.assertTrue(all(l['extensao_m']<=extensao for l in a.locais))

    def test_zero_aceita_coincidentes_compativeis(self):
        r=resultado([evento('a',0),evento('b',0)])
        for busca,extensao in ((0,5),(5,0)):
            self.assertEqual(len(analisar_investigacao(r,OpcoesLocais(True,busca,extensao)).locais),1)

    def test_invalidos_continuam_rejeitados(self):
        for busca,extensao in ((-1,5),(5,-1),(float('nan'),5),(5,float('inf'))):
            with self.assertRaises(ValueError):
                OpcoesLocais(True,busca,extensao).validar()


if __name__=='__main__':
    unittest.main(verbosity=2)
