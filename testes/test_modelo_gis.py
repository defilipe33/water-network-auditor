"""Modelo GIS multifonte, identidade, verificações e ciclo de trabalho no QGIS."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_aplicacao_unificada as fixture
from test_auditoria_fronteiras import APP, camada, quadrado
from qgis.core import QgsProject, QgsVectorLayer
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QCheckBox, QMessageBox

from auditoria_aplicacao.contexto_trabalho import Projetos
from auditoria_aplicacao.modelo_gis import (
    chave_feicao, conferir, configurar, descrever, estado_fonte, identificar, preparar_conferencia, relocalizar,
    revisoes, salvar_modelo, sugerir,
)
from auditoria_aplicacao.modelo_gis_ui import FormularioFonte


class ModeloGIS(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.projetos = Projetos(self.tmp.name)
        self.projeto = self.projetos.criar('Projeto A')
        self.rede = camada('LineString', ['LINESTRING(0 0, 1 1)'], nome='Tubulações de distribuição')
        self.valvulas = camada('Point', ['POINT(0 0)', 'POINT(1 1)', 'POINT(2 2)'], ids=[4, 4, None])

    def fonte(self, camada_, categoria, filtro='', id_='id', **kw):
        return configurar(descrever(camada_), categoria, 'EXISTENTE', '', dict(id=id_, **kw), filtro,
                          'Label' if kw.get('wg') else '')

    def salvar(self, fontes, anterior=None, estrategia='INFERIR'):
        return salvar_modelo(self.projetos, self.projeto['uuid'], anterior, fontes, estrategia)

    def test_multifonte_preserva_campos_crs_e_nomes_repetidos(self):
        b = QgsVectorLayer('LineString?crs=epsg:4326&field=codigo:string', self.rede.name(), 'memory')
        fontes = [self.fonte(self.rede, 'PIPE'), self.fonte(b, 'PIPE', id_='codigo')]
        r = self.salvar(fontes)
        self.assertEqual(r['fontes'], revisoes(Projetos(self.tmp.name).atual())[0]['fontes'])
        self.assertNotEqual(*(f['origem'] for f in fontes))
        self.assertEqual([f['crs'] for f in fontes], ['EPSG:31983', 'EPSG:4326'])
        self.assertEqual([f['campos_mapeados']['id'] for f in fontes], ['id', 'codigo'])

    def test_multicategoria_filtros_independentes(self):
        a = self.fonte(self.valvulas, 'PRV', '"nome" IN (\'regiao_1\', \'regiao_2\')')
        b = self.fonte(self.valvulas, 'TCV', '"nome" <> \'regiao_1\'')
        r, sobreposicao = conferir(preparar_conferencia([a, b], [self.valvulas]))
        self.assertEqual(a['origem'], b['origem'])
        self.assertNotEqual(a['uid'], b['uid'])
        self.assertEqual(self.valvulas.subsetString(), '')
        self.assertEqual(sobreposicao, {(a['uid'], b['uid']): 1})
        self.assertEqual((r[a['uid']]['total'], r[a['uid']]['repetidos']), (2, 1))
        self.assertEqual((r[b['uid']]['total'], r[b['uid']]['ausentes']), (2, 1))

    def test_fonte_incompativel(self):
        with self.assertRaisesRegex(ValueError, 'Geometria incompatível'):
            self.fonte(self.rede, 'TANK')

    def test_filtro_parser_campo_ausente_e_referencia_externa(self):
        for filtro in ('=', '"x" = 1', 'attribute(@feature, \'id\') = 2'):
            with self.subTest(filtro=filtro), self.assertRaises(ValueError):
                self.fonte(self.rede, 'PIPE', filtro)

    def test_associacao_nao_assume_equivalencia(self):
        a = self.fonte(self.rede, 'PIPE', wg='nome', label='nome')
        self.assertEqual(a['alvo_wg'], 'Label')
        self.assertEqual(a['campos_mapeados'], {'id': 'id', 'wg': 'nome', 'label': 'nome'})

    def test_identificadores_preservam_texto_nulos_e_origem(self):
        a = self.fonte(self.rede, 'PIPE')
        b = self.fonte(camada('LineString', []), 'PIPE')
        self.assertNotEqual(chave_feicao(a, '01'), chave_feicao(a, 1))
        self.assertIsNotNone(chave_feicao(a, 0))
        self.assertIsNone(chave_feicao(a, None))
        self.assertNotEqual(chave_feicao(a, '01'), chave_feicao(b, '01'))

    def test_estrategias_parciais(self):
        r = self.salvar([])
        self.assertEqual((r['fontes'], r['estrategia']), ([], 'INFERIR'))
        no = self.fonte(self.valvulas, 'JUNCTION')
        for estrategia in ('CADASTRADAS', 'COMBINAR'):
            r = self.salvar([no], r['uuid'], estrategia)
            self.assertEqual(r['estrategia'], estrategia)

    def test_revisoes_e_indices_legados(self):
        self.projetos.vincular(dict(tipo='AUDITORIA_GIS', uuid='audit', base='antiga.gpkg'))
        a = self.salvar([])
        b = self.salvar([self.fonte(self.rede, 'PIPE')], a['uuid'])
        self.assertEqual(b['anterior'], a['uuid'])
        self.assertEqual(b['referencias_para_conferir'][0]['uuid'], 'audit')
        self.assertEqual(revisoes(Projetos(self.tmp.name).atual())[0], a)
        self.assertEqual(self.salvar(b['fontes'], b['uuid']), b)
        with self.assertRaisesRegex(ValueError, 'mudou desde'):
            self.salvar([], a['uuid'])

    def test_revisao_erro_de_gravacao_preserva_arquivo(self):
        a = self.salvar([])
        conteudo = self.projetos.path.read_bytes()
        with patch('auditoria_aplicacao.contexto_trabalho.os.replace', side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                self.salvar([self.fonte(self.rede, 'PIPE')], a['uuid'])
        self.assertEqual(self.projetos.path.read_bytes(), conteudo)
        self.assertEqual(list(Path(self.tmp.name).glob('*.tmp')), [])

    def test_ausente_nunca_usa_apenas_nome(self):
        f = self.fonte(self.rede, 'PIPE')
        b = camada('LineString', [], nome=self.rede.name())
        self.assertIsNone(identificar(f, [b]))
        self.assertIn('Localizar', estado_fonte(f, None))
        self.assertEqual(relocalizar(f, descrever(b)), 'COMPATIVEL_IDENTIDADE_PENDENTE')

    def test_relocalizar_arquivo_sem_perder_identidade(self):
        pasta = Path(self.tmp.name)
        a, b = pasta / 'a.geojson', pasta / 'b.geojson'
        a.write_text('{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"id":1},"geometry":{"type":"Point","coordinates":[0,0]}}]}', encoding='utf8')
        camada_a = QgsVectorLayer(str(a), 'Original', 'ogr')
        fonte = self.fonte(camada_a, 'JUNCTION')
        del camada_a
        a.rename(b)
        camada_b = QgsVectorLayer(str(b), 'Movida', 'ogr')
        self.assertEqual(relocalizar(fonte, descrever(camada_b)), 'MESMO_ARQUIVO')

    def test_projeto_qgz_normaliza_caminho_sem_trocar_identidade(self):
        pasta = Path(self.tmp.name)
        a = pasta / 'a.geojson'
        a.write_text('{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"id":1},"geometry":{"type":"Point","coordinates":[0,0]}}]}', encoding='utf8')
        projeto = QgsProject()
        original = QgsVectorLayer(str(a), 'Original', 'ogr')
        fonte = self.fonte(original, 'JUNCTION')
        projeto.addMapLayer(original)
        arquivo = str(pasta / 'mapa.qgz')
        self.assertTrue(projeto.write(arquivo))
        recuperado = QgsProject()
        self.assertTrue(recuperado.read(arquivo))
        c = identificar(fonte, recuperado.mapLayers().values())
        self.assertEqual(estado_fonte(fonte, c), 'Disponível')

    def test_relocalizar_rejeita_crs_incompativel(self):
        f = self.fonte(self.rede, 'PIPE')
        b = camada('LineString', [], crs='EPSG:4326')
        with self.assertRaisesRegex(ValueError, 'CRS'):
            relocalizar(f, descrever(b))

    def test_cancelamento_conferencia(self):
        dados = preparar_conferencia([self.fonte(self.rede, 'PIPE')], [self.rede])
        with self.assertRaises(InterruptedError):
            conferir(dados, lambda: True)

    def test_base_extensa_sem_geometrias_na_conferencia(self):
        rede = QgsVectorLayer('LineString?crs=EPSG:31983&field=id:integer', 'Rede extensa', 'memory')
        from qgis.core import QgsFeature
        fs = []
        for i in range(20000):
            f = QgsFeature(rede.fields())
            f.setAttributes([i])
            fs.append(f)
        rede.dataProvider().addFeatures(fs)
        fontes = [self.fonte(rede, 'PIPE', f'id >= {i * 5000}') for i in range(4)]
        resultados, pares = conferir(preparar_conferencia(fontes, [rede]))
        self.assertEqual([resultados[f['uid']]['total'] for f in fontes], [20000, 15000, 10000, 5000])
        self.assertEqual(len(pares), 6)

    def test_sugestao_sem_criar_vinculo(self):
        categorias, campos = sugerir(self.rede)
        self.assertIn('PIPE', categorias)
        self.assertEqual(campos['id'], 'id')
        self.assertNotIn('wg', campos)


class CentralModeloGIS(unittest.TestCase):
    def setUp(self):
        self.f = fixture.InterfaceUnificadaTest()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.app = self.f.app
        self.app.abrir()
        self.central = self.app.central
        self.central.projetos.criar('Projeto sintético')
        self.painel = self.central.modelo_gis
        self.painel.recarregar()
        self.central.abrir_modelo_gis()
        self.rede = camada('LineString', ['LINESTRING(0 0, 1 1)'], nome='Rede de teste')
        self.painel.camadas = lambda: [self.rede]

    def cadastrar(self):
        f = FormularioFonte(self.painel, [self.rede])
        f.camada.setCurrentIndex(1)
        f.categoria.setCurrentIndex(f.categoria.findData('PIPE'))
        self.assertFalse(f.findChildren(QCheckBox))
        f.aplicar()
        self.assertIsNotNone(f.resultado)
        self.painel.fontes.append(f.resultado)
        self.painel.atualizar()

    def test_salvar_parcial_sem_formalidades_e_recuperar(self):
        self.cadastrar()
        self.assertTrue(self.painel.salvar())
        self.painel.recarregar()
        self.assertEqual(len(self.painel.fontes), 1)
        self.assertIn('revisão 1', self.central.resumo_gis.text())
        self.assertIn('Sem camada de Junctions', self.painel.contexto.text())

    def test_trocar_apresentacao_preserva_rascunho(self):
        self.cadastrar()
        self.central.apresentacao.alterar(1)
        self.assertTrue(self.painel.pendente())
        self.central.apresentacao.alterar(0)
        self.assertEqual(len(self.painel.fontes), 1)
        self.assertIs(self.central.tabs.currentWidget(), self.painel)
        self.painel.recarregar()

    def test_encerramento_cancelado_sem_perda(self):
        self.cadastrar()
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Cancel):
            self.assertFalse(self.app.preparar_saida())
        self.assertTrue(self.painel.pendente())
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Discard):
            self.assertTrue(self.app.preparar_saida())
        self.assertEqual(self.painel.fontes, [])

    def test_conferencia_passa_pelo_worker(self):
        self.cadastrar()
        self.painel.conferir()
        for _ in range(100):
            QTest.qWait(25)
            if not self.app.atividades.em_execucao():
                break
        self.assertFalse(self.app.atividades.em_execucao())
        self.assertEqual(self.painel.resultados[self.painel.fontes[0]['uid']]['total'], 1)
        self.painel.recarregar()


if __name__ == '__main__':
    unittest.main()
