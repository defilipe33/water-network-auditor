"""Regressões do ambiente de produção e do mapa em fontes sintéticas."""
import tempfile
import unittest
from unittest.mock import patch

from test_auditoria_fronteiras import APP, camada, quadrado
import test_aplicacao_unificada as fixture
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import QgsCoordinateReferenceSystem, QgsProject, QgsRectangle, QgsVectorLayer

from auditoria_aplicacao.ambiente import AmbienteTrabalho
from auditoria_aplicacao.modelo_gis import configurar, descrever, revisoes
from auditoria_aplicacao.mapa_fontes import ler_destaque
from qgis.core import QgsVectorLayerFeatureSource


class AmbienteTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture.InterfaceUnificadaTest()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.f.app.abrir()
        self.f.canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:31983'))
        self.c = self.f.app.central
        self.c.projetos.criar('Projeto sintético')
        self.c._carregar_projetos()
        self.m = self.c.modelo_gis
        self.m.recarregar()
        self.c.quadro.escolher('REDES')
        self.redes = [camada('LineString', ['LINESTRING(0 0, 10 10)'], nome='Rede ' + str(i)) for i in range(3)]
        self.zona = camada('Polygon', [quadrado()], nome='Setor')
        self.valvula = camada('Point', ['POINT(1 1)', 'POINT(3 3)'], nome='Equipamentos')
        QgsProject.instance().addMapLayers([*self.redes, self.zona, self.valvula])
        self.addCleanup(self.limpar)

    def limpar(self):
        self.aguardar()
        self.m.recarregar()
        self.c.limpar_mapa()

    def aguardar(self):
        for _ in range(160):
            QTest.qWait(15)
            if not self.f.app.atividades.em_execucao():
                return
        self.fail('Worker não encerrou')

    def cadastrar(self, categoria='PIPE', camadas=None, filtro=''):
        camadas = self.redes if camadas is None else camadas
        for c in camadas:
            self.m.fontes.append(configurar(descrever(c), categoria, 'EXISTENTE', '', {'id': 'id'}, filtro))
        self.m.atualizar()
        return self.m.fontes[-1]

    def test_entrada_padrao_e_tres_areas(self):
        self.assertIsInstance(self.c, AmbienteTrabalho)
        self.assertIs(self.c.paginas.currentWidget(), self.c.quadro)
        self.assertTrue(self.c.legado.isHidden())
        self.assertEqual(list(self.c.quadro.cards), ['REDES', 'EQUIPAMENTOS', 'ÁREAS', 'CONECTIVIDADE'])
        self.assertEqual(self.c.area.count(), 3)
        for i, pagina in enumerate((self.c.quadro, self.c.investigar, self.c.trabalhos)):
            self.c.area.setCurrentIndex(i)
            self.assertIs(self.c.paginas.currentWidget(), pagina)

    def test_multifonte_mesmo_cadastro_e_revisao(self):
        self.assertIs(self.c.quadro.modelo, self.m)
        lista = self.m.adicionar()
        for i in range(lista.count()):
            lista.item(i).setCheckState(Qt.Checked)
        self.m.confirmar_b.click()
        self.assertEqual(len(self.m.fontes), 3)
        self.assertTrue(self.m.salvar())
        self.c.quadro.escolher('CONECTIVIDADE')
        self.m.estrategia.setCurrentIndex(self.m.estrategia.findData('COMBINAR'))
        self.assertTrue(self.m.salvar())
        hist = revisoes(self.c.projetos.atual())
        self.assertEqual(hist[1]['anterior'], hist[0]['uuid'])

    def test_filtros_independentes_e_auxiliares(self):
        self.c.quadro.escolher('EQUIPAMENTOS')
        for categoria, filtro in [('PRV', 'id = 1'), ('TCV', 'id = 2')]:
            self.c.quadro.categorias.setCurrentIndex(self.c.quadro.categorias.findData(categoria))
            self.cadastrar(categoria, [self.valvula], filtro)
        self.assertEqual(len({f['origem'] for f in self.m.fontes}), 1)
        self.assertEqual(len({f['uid'] for f in self.m.fontes}), 2)
        self.c.cadastro_auxiliar()
        self.assertIs(self.m.paginas.currentWidget(), self.m.inicio)

    def test_selecao_multifonte_pendente_salva_ao_sair(self):
        lista = self.m.adicionar()
        lista.item(0).setCheckState(Qt.Checked)
        self.assertTrue(self.m.pendente())
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Save):
            self.assertTrue(self.m.resolver())
        self.assertEqual(len(self.m.fontes), 1)
        self.assertFalse(self.m.pendente())

    def test_reusar_fonte_preserva_id_e_abre_editor(self):
        self.c.quadro.escolher('EQUIPAMENTOS')
        fonte = self.cadastrar('PRV', [self.valvula], 'id = 1')
        self.c.quadro.classificar()
        from qgis.PyQt.QtWidgets import QComboBox
        combo = self.m.tarefa.findChild(QComboBox)
        combo.setCurrentIndex(combo.findData('TCV'))
        self.m.confirmar_b.click()
        self.assertEqual(len(self.m.fontes), 2)
        a, b = self.m.fontes
        self.assertEqual(a['origem_estavel'], b['origem_estavel'])
        self.assertNotEqual(a['uid'], b['uid'])
        self.assertIsNotNone(self.m.editor)

    def test_contexto_area_nao_descarta_editor(self):
        self.cadastrar()
        self.m.editar()
        editor = self.m.editor
        editor.filtro.setText('id = 1')
        self.c.area.setCurrentIndex(1)
        self.c.area.setCurrentIndex(2)
        self.c.area.setCurrentIndex(0)
        self.c.apresentacao.alterar(1)
        self.c.apresentacao.alterar(0)
        self.assertIs(self.m.editor, editor)
        self.assertTrue(editor.pendente())

    def test_cancelar_troca_projeto_preserva_rascunho(self):
        self.cadastrar()
        antes = self.c.projetos.dados['ativo']
        with patch.object(QMessageBox, 'exec_', return_value=QMessageBox.Cancel):
            # O projeto candidato já existe em outro índice carregado.
            from auditoria_aplicacao.contexto_trabalho import Projetos
            outro = Projetos(self.f.raiz)
            p = outro.criar('Outro projeto')
            outro.ativar(antes)
            self.c.projetos.dados = outro.ler()
            self.c._carregar_projetos()
            self.c.escolher_projeto(self.c.projeto.findData(p['uuid']))
        self.assertEqual(self.c.projetos.dados['ativo'], antes)
        self.assertTrue(self.m.pendente())

    def test_cenario_cancelado_preserva_base(self):
        self.cadastrar()
        self.c.cenarios.addItem('Cenário candidato', {'uuid': 'novo', 'tipo': 'TOPOLOGIA_WG', 'base': 'ausente'})
        self.c.cenarios.setCurrentIndex(self.c.cenarios.count() - 1)
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Cancel), patch.object(self.f.app, 'trocar_base') as trocar:
            self.c.trocar_cenario()
            trocar.assert_not_called()
        self.assertTrue(self.m.pendente())

    def test_seletor_cenarios_respeita_modelo_e_projeto(self):
        a = dict(uuid='a', tipo='TOPOLOGIA_WG', base='a.gpkg', nome='Base', versao=1, modelo_uid='modelo', cenario=1)
        b = dict(a, uuid='b', base='b.gpkg', cenario=2)
        fora = dict(a, uuid='fora', modelo_uid='outro')
        self.c.projetos.vincular(a)
        self.c.projetos.vincular(b)
        self.c._registros = [a, b, fora]
        self.c._fatos = dict(wg={'valido': True, 'uuid': 'a'}, contexto={'modelo': 'Nome legível', 'cenario': 1})
        with patch.object(self.c.app.catalogo, 'listar_opcional', return_value=self.c._registros):
            self.c.atualizar_cenarios()
        rs = [self.c.cenarios.itemData(i) for i in range(self.c.cenarios.count())]
        self.assertIn(b, rs)
        self.assertNotIn(fora, rs)
        self.c.cenarios.setCurrentIndex(self.c.cenarios.findData(b))
        with patch.object(self.f.app, 'trocar_base', return_value=True) as trocar:
            self.c.trocar_cenario()
            trocar.assert_called_once_with(b)

    def test_destacar_fonte_sem_mudar_estilo_selecao_ou_zoom(self):
        f = self.cadastrar(camadas=[self.redes[0]])
        c = self.redes[0]
        c.selectByIds([next(c.getFeatures()).id()])
        original = c.renderer().symbol().dump()
        ids = c.selectedFeatureIds()
        canvas = self.f.canvas
        canvas.setExtent(QgsRectangle(-10, -10, 20, 20))
        antes = QgsRectangle(canvas.extent())
        self.c.destacar_fonte(f)
        self.aguardar()
        self.assertTrue(self.c.mapa.itens)
        self.assertEqual(c.renderer().symbol().dump(), original)
        self.assertEqual(c.selectedFeatureIds(), ids)
        self.assertEqual(canvas.extent(), antes)
        self.c.limpar_mapa()
        self.assertFalse(self.c.mapa.itens)

    def test_selecao_de_feicao_mostra_identidade(self):
        f = self.cadastrar('PRV', [self.valvula], 'id = 1')
        self.c.destacar_fonte(f)
        self.aguardar()
        feicao = next(self.valvula.getFeatures())
        self.valvula.selectByIds([feicao.id()])
        self.aguardar()
        self.assertIn('id = 1', self.c.mapa_info.toolTip())
        self.assertEqual(len(self.c.mapa.caixas), 1)

    def test_zona_e_fonte_indisponivel(self):
        f = self.cadastrar('SETOR', [self.zona])
        self.c.destacar_fonte(f)
        self.aguardar()
        self.assertTrue(self.c.mapa.itens)
        QgsProject.instance().removeMapLayer(self.zona.id())
        self.assertFalse(self.c.mapa.itens)
        self.assertFalse(self.c.mapa.destacar(f))

    def test_tabela_sem_geometria(self):
        t = QgsVectorLayer('None?field=id:integer', 'Tabela', 'memory')
        QgsProject.instance().addMapLayer(t)
        f = self.cadastrar('AUXILIAR', [t])
        self.assertFalse(self.c.mapa.destacar(f))
        self.assertIn('sem geometria', self.c.mapa_info.text())

    def test_ler_destaque_limita_e_respeita_filtro(self):
        c = self.valvula
        source = QgsVectorLayerFeatureSource(c)
        geos, nomes, parcial = ler_destaque(source, 'id = 2', None, ['id'], lambda: False, limite=1)
        self.assertEqual(len(geos), 1)
        self.assertFalse(parcial)
        self.assertIn('id = 2', nomes[0])
        geos, _, parcial = ler_destaque(source, '', None, [], lambda: False, limite=1)
        self.assertTrue(parcial)
        with self.assertRaises(InterruptedError):
            ler_destaque(source, '', None, [], lambda: True)

    def test_trabalhos_filtrados_por_projeto_e_sem_backup(self):
        self.c._registros = [
            dict(uuid='a', tipo='INTEGRADA', base='ativo.gpkg', nome='Investigação', versao=1),
            dict(uuid='b', tipo='INTEGRADA', base='backup.gpkg', nome='Backup', versao=1, classe_arquivo='BACKUP_TECNICO'),
            dict(uuid='c', tipo='TOPOLOGIA_WG', base='outro.gpkg', nome='Outro', versao=1),
        ]
        for r in self.c._registros[:2]:
            self.c.projetos.vincular(r)
        with patch.object(self.c.app.catalogo, 'listar_opcional', return_value=self.c._registros):
            self.c.area.setCurrentIndex(2)
        self.c.listar_trabalhos()
        self.assertEqual(self.c.trabalhos_lista.count(), 1)
        self.c.trabalhos_lista.setCurrentRow(0)
        self.c.pesquisa.setText('inves')
        self.assertEqual(self.c.trabalhos_lista.count(), 1)
        self.c.tipo_trabalho.setCurrentIndex(3)
        self.assertEqual(self.c.trabalhos_lista.count(), 0)

    def test_ferramentas_avancadas_retorno(self):
        self.c.abrir_avancados()
        self.assertFalse(self.c.legado.isHidden())
        self.c.abrir_modelo_gis()
        self.assertTrue(self.c.legado.isHidden())
        self.assertIs(self.c.paginas.currentWidget(), self.c.quadro)


if __name__ == '__main__':
    unittest.main()
