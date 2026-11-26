"""Regressões da navegação, captura e gestão do cadastro complementar."""

import unittest
from unittest.mock import patch

import test_grafo_gis as etapa2
from qgis.PyQt.QtCore import QItemSelectionModel, QTimer, Qt
from qgis.PyQt.QtGui import QColor, QKeyEvent, QPalette
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QApplication, QAbstractItemView, QComboBox, QMenu, QMessageBox, QPushButton, QVBoxLayout, QWidget
from qgis.core import QgsProject, QgsRectangle
from qgis.gui import QgsMapToolPan

from auditoria_aplicacao import persistencia_grafo_gis as pg
from auditoria_aplicacao.complementos_gis_ui import EditarComplemento
from auditoria_aplicacao.modelo_gis_ui import expansivel
from auditoria_aplicacao.navegacao_cartografica import navegar_registros
from auditoria_aplicacao.tabelas_topologia_gis import TabelaGIS


class Gestos(unittest.TestCase):
    def setUp(self):
        self.tabela=TabelaGIS()
        self.addCleanup(self.tabela.close)
        self.tabela.colunas(('Elemento','Distância'))
        self.tabela.inserir(('A',10),'a')
        self.tabela.inserir(('B',2),'b')
        self.tabela.resize(400,180)
        self.tabela.show()
        QTest.qWait(20)

    def test_duplo_clique_usa_registro_da_vista_ordenada_e_filtrada(self):
        t=self.tabela
        chamadas=[]
        navegar_registros(t,lambda i,a:chamadas.append((t.item(i.row(),0).data(Qt.UserRole),a)))
        t.sortItems(0,Qt.DescendingOrder)
        t.setRowHidden(1,True)
        t.doubleClicked.emit(t.model().index(0,1))
        self.assertEqual(chamadas,[('b',True)])
        self.assertEqual(t.currentRow(),0)

    def test_botao_direito_seleciona_alvo_e_expoe_motivo(self):
        t=self.tabela
        chamadas=[]
        navegar_registros(t,lambda i,a:chamadas.append((i.row(),a)),
                          lambda i:[('Editar',lambda:None,'Revisão somente para consulta')])
        t.selectRow(0)
        encontrado=[]
        def acionar(m,*_):
            encontrado.append((t.currentRow(),m.actions()[-1].isEnabled(),m.actions()[-1].toolTip()))
            m.actions()[0].trigger()
        with patch.object(QMenu,'exec_',new=acionar):
            t.customContextMenuRequested.emit(t.visualItemRect(t.item(1,0)).center())
        self.assertEqual(encontrado,[(1,False,'Revisão somente para consulta')])
        self.assertEqual(chamadas,[(1,True)])

    def test_menu_coletivo_preserva_multisselecao(self):
        t=self.tabela
        t.setSelectionMode(QAbstractItemView.ExtendedSelection)
        chamadas=[]
        navegar_registros(t,lambda i,a:None,navegar_varios=lambda is_:chamadas.append(sorted(i.row() for i in is_)))
        for n in (0,1):
            t.selectionModel().select(t.model().index(n,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
        with patch.object(QMenu,'exec_',new=lambda m,*_:next(
                (a for a in m.actions() if a.text()=='Enquadrar seleção'),m.actions()[0]).trigger()):
            t.customContextMenuRequested.emit(t.visualItemRect(t.item(1,0)).center())
        self.assertEqual(chamadas,[[0,1]])

    def test_painel_expansivel_usa_seta_e_superficie_do_tema(self):
        pai=QWidget()
        self.addCleanup(pai.close)
        botao,conteudo=expansivel(QVBoxLayout(pai),'Configuração')
        pai.show()
        self.assertEqual(botao.arrowType(),Qt.RightArrow)
        self.assertTrue(conteudo.parentWidget().isHidden())
        botao.click()
        self.assertEqual(botao.arrowType(),Qt.DownArrow)
        self.assertFalse(conteudo.parentWidget().isHidden())
        from auditoria_aplicacao.aparencia import contraste, cores, estilo
        paleta=QPalette()
        for fundo,texto in (('#252525','#eeeeee'),('#f4f4f4','#222222')):
            paleta.setColor(QPalette.Window,QColor(fundo))
            paleta.setColor(QPalette.WindowText,QColor(texto))
            paleta.setColor(QPalette.AlternateBase,QColor('white'))
            tokens=cores(paleta)
            self.assertGreaterEqual(contraste(tokens['texto_secao'],tokens['secao']),4.5)
            self.assertIn(f"background-color:{tokens['secao'].name()}",estilo(tokens))
        self.assertEqual(conteudo.parentWidget().objectName(),'WnaSecaoExpandida')


class Conectividade(unittest.TestCase):
    def setUp(self):
        self.fixture=etapa2.InterfaceGIS()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.t=self.fixture.t
        self.c=self.fixture.c
        self.canvas=self.c.mapa.canvas
        self.addCleanup(lambda:setattr(self.t,'_edicao_limpa',self.t._assinatura_edicao()))

    def aguardar(self):
        self.fixture.f.aguardar()

    def criar_editor(self):
        t=self.t
        t.editar('ORIGEM',ponto=dict(xy=[330005,7390050],crs=t.crs.crs().toWkt()))
        self.aguardar()
        dlg=t._editor
        self.assertIsInstance(dlg,EditarComplemento)
        self.addCleanup(lambda:dlg.reject() if t._editor is dlg else None)
        dlg.nome.setText('Origem sintética')
        dlg.nota.setText('Texto a preservar')
        return dlg

    def posicionar(self,dlg):
        ponto=next(iter(dlg.tubos.values()))['geom'].asPolyline()[0]
        self.canvas.setExtent(QgsRectangle(ponto.x()-20,ponto.y()-20,ponto.x()+20,ponto.y()+20))
        ferramenta=QgsMapToolPan(self.canvas)
        self.canvas.setMapTool(ferramenta)
        return ponto,ferramenta

    def test_captura_conclui_restaurando_editor_e_ferramenta(self):
        t=self.t
        dlg=self.criar_editor()
        p,anterior=self.posicionar(dlg)
        t.selecionar_no_editor(dlg,t.crs.crs().toWkt())
        self.assertTrue(dlg.isHidden())
        captura=t._ferramenta[1]
        captura.canvasClicked.emit(p,Qt.LeftButton)
        self.assertTrue(dlg.portas)
        captura.canvasClicked.emit(p,Qt.RightButton)
        self.assertFalse(dlg.isHidden())
        self.assertIs(self.canvas.mapTool(),anterior)
        self.assertEqual(dlg.nota.text(),'Texto a preservar')
        self.assertEqual(dlg.nome.text(),'Origem sintética')
        self.assertEqual(len(dlg.portas),1)
        self.assertIsNone(t._ferramenta)

    def test_escape_e_excecao_preservam_pontos_e_campos(self):
        t=self.t
        dlg=self.criar_editor()
        p,anterior=self.posicionar(dlg)
        uid=next(iter(dlg.tubos))
        dlg.adicionar_mapa(uid,.6)
        for falhar in (False,True):
            t.selecionar_no_editor(dlg,t.crs.crs().toWkt())
            captura=t._ferramenta[1]
            if falhar:
                with patch.object(t,'_clique_metricas',side_effect=ValueError('Transformação indisponível')):
                    captura.canvasClicked.emit(p,Qt.LeftButton)
                self.assertIn('Transformação indisponível',t.status.text())
            else:
                captura.canvasClicked.emit(p,Qt.LeftButton)
                captura.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress,Qt.Key_Escape,Qt.NoModifier))
            self.assertIsNone(t._ferramenta)
            self.assertIs(self.canvas.mapTool(),anterior)
            self.assertFalse(dlg.isHidden())
            self.assertEqual(dlg.portas,[(uid,.6)])
            self.assertEqual(dlg.nota.text(),'Texto a preservar')

    def test_desativacao_externa_respeita_ferramenta_escolhida_no_qgis(self):
        t=self.t
        dlg=self.criar_editor()
        self.posicionar(dlg)
        t.selecionar_no_editor(dlg,t.crs.crs().toWkt())
        substituta=QgsMapToolPan(self.canvas)
        self.canvas.setMapTool(substituta)
        QTest.qWait(30)
        self.assertIs(self.canvas.mapTool(),substituta)
        self.assertFalse(dlg.isHidden())
        self.assertIsNone(t._ferramenta)

    def test_duplo_clique_fonte_foca_local_sem_desmarcar_hipotese(self):
        t=self.t
        dlg=self.criar_editor()
        dlg.adicionar_mapa(next(iter(dlg.tubos)),0.)
        dlg.validar()
        self.assertIsNone(t._editor)
        linha=t.participantes.item(0)
        self.assertEqual(linha.checkState(),Qt.Unchecked)
        t.participantes.doubleClicked.emit(t.participantes.model().index(0,1))
        self.assertIsNone(t._editor)
        centro=self.canvas.extent().center()
        self.assertAlmostEqual(centro.x(),330005,places=1)
        self.assertAlmostEqual(centro.y(),7390050,places=1)
        self.assertEqual(linha.checkState(),Qt.Unchecked)
        self.assertGreaterEqual(len(self.c.mapa.itens),3)

    def test_exclusao_recuperacao_e_reexecucao_historica(self):
        t=self.t
        dlg=self.criar_editor()
        dlg.adicionar_mapa(next(iter(dlg.tubos)),0.)
        dlg.validar()
        t.participantes.item(0).setCheckState(Qt.Checked)
        t._gravar_hipotese('Hipótese original')
        self.aguardar()
        hip=t._hip_ativa
        original=next(iter(t._pinos.values()))
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes) as aviso:
            self.assertTrue(t.excluir_relacao(original))
            self.assertIn('Hipótese original',aviso.call_args.args[2])
        self.assertEqual(t.participantes.count(),0)
        excluida=t.registros[original['uuid']]
        self.assertTrue(excluida['excluido'])
        self.assertFalse(excluida['habilitado'])
        t.mostrar_excluidos.setChecked(True)
        self.assertEqual(t.participantes.count(),1)
        self.assertIn('Recuperar complemento', [a[0] for a in t._menu_relacao(t.participantes.model().index(0,0)) if a])
        t._aplicar(hip)
        self.assertEqual(t._participantes_exatos(repetir=True)[0]['rev'],original['rev'])
        with self.assertRaisesRegex(ValueError,'excluído'):
            t._participantes_exatos()
        t.iniciar(modo='salva')
        self.aguardar()
        self.assertEqual(t.dados['origens_validas'],[original['uuid']])
        self.assertTrue(t.excluir_relacao(excluida,False))
        rs=pg.revisoes(t._base_complementos(),t.uid_projeto,original['uuid'])
        self.assertEqual([r.get('excluido',False) for r in rs],[False,True,False])
        self.assertEqual(t._selecionados(),[])

    def test_dados_originais_nao_podem_ser_excluidos(self):
        t=self.t
        r=t._salvar('ORIGEM',dict(situacao='CADASTRADA',equipamento='reservatorio',portas=[]))
        self.assertFalse(t.excluir_relacao(r))
        self.assertEqual(len(pg.revisoes(t._base_complementos(),t.uid_projeto,r['uuid'])),1)
        menu=t._menu_relacao(t.participantes.model().index(0,0))
        self.assertFalse(any(a and 'Excluir' in a[0] for a in menu))

    def test_informa_ausencia_de_resultado_e_geometria(self):
        t=self.t
        self.assertFalse(t.revisar_b.isEnabled())
        self.assertIn('Execute',t.revisar_b.toolTip())
        t.destacar_relacao(r=dict(tipo='ORIGEM',portas=[],situacao='CADASTRADA'))
        self.assertIn('Geometria indisponível',t.status.text())

    def test_decisao_rapida_em_t_exige_participacao_explicita(self):
        from test_auditoria_fronteiras import camada
        t=self.t
        outra=camada('LineString',['LINESTRING(5 10,5 5.04)'],nome='Receptor sintético')
        QgsProject.instance().addMapLayer(outra)
        self.fixture.f.cadastrar('PIPE',[outra])
        self.assertTrue(self.fixture.f.m.salvar())
        t.abrir()
        t.iniciar()
        self.aguardar()
        candidata=next(d for d in t.dados['diagnosticos'] if d['tipo']=='CONEXAO_T')
        self.assertTrue(t.selecionar_resultado_uid(candidata['uid'],'CONEXAO_T'))
        indice=t.resultados.model().index(t.resultados.currentRow(),0)
        t.resultados.doubleClicked.emit(indice)
        self.assertIsNone(t._editor)
        self.assertTrue(self.c.mapa.itens)
        opcoes={a[0]:a[1] for a in t._menu_resultado(indice) if a}
        estados=[]
        def salvar():
            dialogo=QApplication.activeModalWidget()
            if dialogo is None:return
            estados.extend(c.currentData() for c in dialogo.findChildren(QComboBox))
            next(b for b in dialogo.findChildren(QPushButton) if b.text()=='Salvar decisão').click()
        QTimer.singleShot(0,salvar)
        opcoes['Confirmar sem incluir…']()
        self.assertEqual(estados,[('CONFIRMADA',False),'VERIFICADO'])
        self.assertIn('fora da hipótese',t.status.text())
        self.assertEqual(t._acompanhamento(candidata),'Verificado')
        self.assertEqual(t._acompanhamento_foto(candidata),'Sem revisão na fotografia')
        self.assertEqual(t._selecionados(),[])
        uid=next(r['uuid'] for r in t.registros.values() if r['tipo']=='CONEXAO')
        t._marcar_relacao(uid,True)
        self.assertIn(uid,t._selecionados())
        t.iniciar(modo='temporaria')
        self.aguardar()
        self.assertEqual(t.dados['resolucoes_conexoes'],{uid:'APLICADA'})
        nova=next(d for d in t.dados['diagnosticos'] if d['uid']==candidata['uid'])
        t.interpretar_candidata(nova,'SEPARADA')
        t.iniciar(modo='temporaria')
        self.aguardar()
        self.assertEqual(t.dados['resolucoes_conexoes'],{uid:'SEPARADA'})

    def test_localiza_componente_na_segunda_pagina_apos_ordenar(self):
        from test_auditoria_fronteiras import camada
        t=self.t
        rede=camada('LineString',[f'LINESTRING(100 {i*20},6100 {i*20})' for i in range(204)],
                    nome='Rede sintética independente')
        QgsProject.instance().addMapLayer(rede)
        self.fixture.f.cadastrar('PIPE',[rede])
        self.assertTrue(self.fixture.f.m.salvar())
        t.abrir()
        t.iniciar()
        self.aguardar()
        t.ordenar_resultados(3)
        t.paginar(1)
        self.assertGreater(t.resultados.rowCount(),1)
        item=t.resultados.item(1,0)
        uid=item.data(Qt.UserRole)
        t.resultados.doubleClicked.emit(t.resultados.model().index(1,1))
        self.assertEqual(t._selecionado()['uid'],uid)
        self.assertEqual(t._pagina,1)
        self.assertIsNone(t._editor)
        self.assertGreater(self.canvas.extent().width(),6000)


if __name__=='__main__':
    unittest.main()
