"""Modelo GIS multifonte, identidade, verificações e ciclo de trabalho no QGIS."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_aplicacao_unificada as fixture
from test_auditoria_fronteiras import APP, camada, quadrado
from qgis.core import QgsFeature, QgsProject, QgsVectorLayer, QgsVectorLayerFeatureSource
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QCheckBox, QMessageBox

from auditoria_aplicacao.cadastro_gis import amostra, copiar_mapeamento, filtro_simples, incluir_fontes, sugerir_campos
from auditoria_aplicacao.contexto_trabalho import Projetos
from auditoria_aplicacao.modelo_gis import (
    chave_feicao, conferir, configurar, descrever, estado_fonte, identificar, preparar_conferencia, relocalizar,
    revisoes, salvar_modelo, sugerir,
)


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
        self.painel.categorias['PIPE'].click()
        lista = self.painel.adicionar()
        from qgis.PyQt.QtCore import Qt
        self.assertFalse(self.painel.findChildren(QCheckBox))
        lista.item(0).setCheckState(Qt.Checked)
        self.painel.confirmar_b.click()
        self.assertEqual(len(self.painel.fontes), 1)

    def test_salvar_parcial_sem_formalidades_e_recuperar(self):
        self.cadastrar()
        self.assertTrue(self.painel.salvar())
        self.painel.recarregar()
        self.assertEqual(len(self.painel.fontes), 1)
        self.assertIn('revisão 1', self.central.resumo_gis.text())
        self.assertIn('Sem fontes', self.painel.contagens['Junctions e conectividade'].text())

    def test_trocar_apresentacao_preserva_rascunho(self):
        self.cadastrar()
        self.central.apresentacao.alterar(1)
        self.assertTrue(self.painel.pendente())
        self.central.apresentacao.alterar(0)
        self.assertEqual(len(self.painel.fontes), 1)
        self.assertIs(self.central.paginas.currentWidget(), self.central.quadro)
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



class RefinamentoModeloGIS(unittest.TestCase):
    def setUp(self):
        self.rede = QgsVectorLayer('LineString?crs=EPSG:31983&field=GIS_ID:string&field=DIAMETRO:integer&field=label:string',
                                   'Rede', 'memory')
        f = QgsFeature(self.rede.fields())
        f.setAttributes(['001', 100, "P-\'1"])
        self.rede.dataProvider().addFeatures([f])

    def test_sugestoes_por_categoria_tipo_e_ambiguidade(self):
        mapa, pendentes = sugerir_campos({'GIS_ID': 'String', 'ID_GIS': 'Integer', 'DN': 'Integer',
                                         'MATERIAL': 'String', 'ano': 'String'}, 'PIPE')
        self.assertEqual(mapa, {'diametro': 'DN', 'material': 'MATERIAL'})
        self.assertEqual(set(pendentes), {'id', 'gis_id'})
        self.assertNotIn('diametro', sugerir_campos({'DN': 'String'}, 'PIPE')[0])
        self.assertNotIn('diametro', sugerir_campos({'DN': 'Integer'}, 'ZONA')[0])

    def test_inclusao_omite_repeticao_e_geometria_incompativel(self):
        outra = QgsVectorLayer('LineString?crs=EPSG:4326&field=ID_GIS:integer', 'Rede', 'memory')
        ponto = camada('Point', ['POINT(0 0)'])
        a, msgs, _ = incluir_fontes([], 'PIPE', [self.rede, outra, self.rede, ponto])
        self.assertEqual(len(a), 2)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(a[0]['campos_mapeados']['id'], 'GIS_ID')
        self.assertEqual(a[0]['campos_mapeados']['diametro'], 'DIAMETRO')
        self.assertEqual(incluir_fontes(a, 'PIPE', [self.rede])[0], [])

    def test_mapeamento_lote_preserva_filtro_e_avisos(self):
        a, _, _ = incluir_fontes([], 'PIPE', [self.rede])
        a = a[0]
        b = QgsVectorLayer('LineString?crs=EPSG:31983&field=GIS_ID:string&field=DIAMETRO:string',
                           'Destino', 'memory')
        meta = descrever(b)
        destino = configurar(meta, 'PIPE', 'PROJETADO', 'ADUCAO', {}, '"GIS_ID" IS NOT NULL')
        nova, pendencias = copiar_mapeamento(a, destino, meta)
        self.assertEqual(nova['uid'], destino['uid'])
        self.assertEqual(nova['filtro'], destino['filtro'])
        self.assertEqual(nova['papel'], 'PROJETADO')
        self.assertEqual(nova['campos_mapeados'], {'id': 'GIS_ID', 'gis_id': 'GIS_ID'})
        self.assertIn(('diametro', 'DIAMETRO', 'tipo incompatível'), pendencias)
        self.assertIn(('label', 'label', 'ausente'), pendencias)

    def test_filtro_simples_preserva_texto_e_aspas(self):
        fonte = QgsVectorLayerFeatureSource(self.rede)
        for campo, tipo, valor in [('GIS_ID', 'String', '001'), ('label', 'String', "P-\'1"),
                                   ('DIAMETRO', 'Integer', '100')]:
            with self.subTest(campo=campo):
                expr = filtro_simples(campo, tipo, '=', valor)
                self.assertEqual(amostra(fonte, [campo], expr), ([[valor]], 1, True))
        with self.assertRaises(ValueError):
            filtro_simples('DIAMETRO', 'Integer', '=', '100.2')

    def test_amostra_limita_e_diferencia_zero_de_filtro_invalido(self):
        fs = []
        for _ in range(300):
            f = QgsFeature(self.rede.fields())
            f.setAttributes(['002', 150, 'P2'])
            fs.append(f)
        self.rede.dataProvider().addFeatures(fs)
        fonte = QgsVectorLayerFeatureSource(self.rede)
        self.assertEqual(amostra(fonte, ['GIS_ID'], 'upper("GIS_ID") = \'100\'', limite=3), ([], 0, False))
        self.assertEqual(amostra(fonte, ['GIS_ID'], '"DIAMETRO" = 999', limite=350), ([], 0, True))
        with self.assertRaises(ValueError):
            amostra(fonte, [], '"NÃO EXISTE" = 1')
        self.assertEqual(len(amostra(fonte, ['GIS_ID'], '', limite=8)[0]), 5)

    def test_conferencia_exibe_exemplos_e_mantem_fontes_validas(self):
        b = camada('Point', ['POINT(0 0)', 'POINT(1 1)'], ids=[4, 4])
        meta = descrever(b)
        ruim = configurar(meta, 'PRV', 'EXISTENTE', '', {'id': 'id'}, 'to_int("nome") > 0')
        boa = configurar(meta, 'TCV', 'EXISTENTE', '', {'id': 'id'})
        resultados, pares = conferir(preparar_conferencia([ruim, boa], [b]))
        self.assertIn('erro', resultados[ruim['uid']])
        self.assertEqual(resultados[boa['uid']]['exemplos'], ['4'])
        self.assertEqual(pares, {})


class FluxoModeloGIS(unittest.TestCase):
    def setUp(self):
        f = fixture.InterfaceUnificadaTest()
        f.setUp()
        self.addCleanup(f.tearDown)
        f.app.abrir()
        self.central = f.app.central
        self.central.projetos.criar('Projeto sintético')
        self.painel = self.central.modelo_gis
        self.painel.recarregar()
        self.redes = [camada('LineString', ['LINESTRING(0 0, 1 1)'], nome=f'Rede {i}') for i in range(3)]
        self.valvulas = camada('Point', ['POINT(0 0)'], nome='Válvulas')
        self.painel.camadas = lambda: [*self.redes, self.valvulas]
        self.addCleanup(self.painel.recarregar)

    def selecionar(self, lista):
        for i in range(lista.count()):
            if lista.item(i).flags() & Qt.ItemIsUserCheckable:
                lista.item(i).setCheckState(Qt.Checked)
        self.painel.confirmar_b.click()

    def cadastrar_redes(self):
        self.painel.categorias['PIPE'].click()
        lista = self.painel.adicionar()
        self.assertEqual(lista.count(), 3)
        self.selecionar(lista)

    def test_fluxo_multifonte_sem_formulario_repetido(self):
        self.assertIs(self.central.paginas.currentWidget(), self.central.quadro)
        self.cadastrar_redes()
        self.assertEqual(len(self.painel.fontes), 3)
        self.assertTrue(all(f['campos_mapeados'].get('id') == 'id' for f in self.painel.fontes))
        lista = self.painel.adicionar()
        self.assertTrue(all(not lista.item(i).flags() & Qt.ItemIsUserCheckable for i in range(3)))
        self.painel.cancelar_tarefa()
        self.painel.remover()
        self.assertEqual(len(self.painel.fontes), 2)

    def test_edicao_filtro_lote_e_persistencia(self):
        self.cadastrar_redes()
        self.assertTrue(self.painel.salvar())
        self.painel.editar()
        ed = self.painel.editor
        ed.coluna.setCurrentIndex(ed.coluna.findData('nome'))
        ed.valor.setText('regiao_1')
        ed.usar_filtro()
        ed.mapa['label'].setCurrentIndex(ed.mapa['label'].findData('nome'))
        self.assertTrue(self.painel.aplicar_editor())
        self.selecionar(self.painel.escolher_lote())
        self.assertEqual(sum(bool(f['filtro']) for f in self.painel.fontes), 1)
        self.assertTrue(all(f['campos_mapeados']['label'] == 'nome' for f in self.painel.fontes))
        self.assertTrue(self.painel.salvar())
        r = revisoes(self.central.projetos.atual())
        self.assertEqual(r[1]['anterior'], r[0]['uuid'])
        self.assertNotIn('label', r[0]['fontes'][0]['campos_mapeados'])
        self.painel.recarregar()
        self.assertEqual(self.painel.fontes, r[1]['fontes'])

    def test_editor_preservado_ao_flutuar_e_cancelar(self):
        self.cadastrar_redes()
        self.painel.editar()
        ed = self.painel.editor
        ed.filtro.setText('"nome" IS NOT NULL')
        self.central.apresentacao.alterar(1)
        self.central.apresentacao.alterar(0)
        self.assertIs(self.painel.editor, ed)
        self.assertTrue(ed.pendente())
        self.painel.cancelar_tarefa()
        self.assertEqual(self.painel.fonte_selecionada()['filtro'], '')

    def test_salvar_aplica_regra_simples_ainda_no_editor(self):
        self.cadastrar_redes()
        self.painel.editar()
        ed = self.painel.editor
        ed.coluna.setCurrentIndex(ed.coluna.findData('nome'))
        ed.valor.setText('regiao_1')
        self.assertTrue(ed.pendente())
        self.assertTrue(self.painel.salvar())
        self.assertEqual(self.painel.fonte_selecionada()['filtro'], '"nome" = \'regiao_1\'')

    def test_mesma_camada_duas_categorias_e_estrategia_de_nos(self):
        for cat in ('PRV', 'TCV'):
            self.painel.abrir_categoria(cat)
            self.selecionar(self.painel.adicionar())
        self.assertEqual(len(self.painel.fontes), 2)
        self.assertEqual(self.painel.fontes[0]['origem'], self.painel.fontes[1]['origem'])
        self.painel.abrir_categoria('JUNCTION')
        self.assertEqual(self.painel.estrategia.currentData(), 'INFERIR')
        self.painel.estrategia.setCurrentIndex(self.painel.estrategia.findData('COMBINAR'))
        self.assertTrue(self.painel.salvar())
        self.painel.recarregar()
        self.assertEqual(self.painel.estrategia.currentData(), 'COMBINAR')


if __name__ == '__main__':
    unittest.main()
