"""Integração PyQt/PyQGIS offscreen; nenhum dado original é gravado."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_auditoria_fronteiras import APP, camada, quadrado
from qgis.PyQt.QtCore import Qt, QTimer, QDate, QDateTime
from qgis.PyQt.QtWidgets import QProgressDialog
from qgis.core import QgsProject, QgsWkbTypes
from auditoria_fronteiras import CamadaEntrada, Modo, Parametros, auditar
from auditoria_fronteiras.interface import AuditoriaFronteirasDialog
from auditoria_fronteiras.modelos import Cancelado
from auditoria_fronteiras.visualizacao import (
    ESTILOS, MARCA_RESULTADO, carregar_no_projeto, criar_camadas_temporarias,
    resumir, texto_json, texto_resumo,
)


class VisualizacaoTest(unittest.TestCase):
    def resultado(self, linhas=None, poligonos=None, modo=Modo.PERIMETRO):
        rede = camada('LineString', linhas or ['LINESTRING(-2 5,12 5)'])
        limite = camada('Polygon', poligonos or [quadrado()])
        return auditar([CamadaEntrada(rede, 'id')],
            [CamadaEntrada(limite, 'id', 'nome', modo)], Parametros(distancia_continuidade=0))

    def test_pontos_e_campos_rastreaveis(self):
        r = self.resultado()
        saida = criar_camadas_temporarias(r)
        self.assertEqual(len(saida), 2)
        p = saida[0]
        self.assertEqual(p.providerType(), 'memory')
        self.assertEqual(p.crs().authid(), r.parametros.crs)
        self.assertEqual(p.featureCount(), len(r.ocorrencias))
        self.assertEqual(p.geometryType(), QgsWkbTypes.PointGeometry)
        f = next(saida[1].getFeatures())
        self.assertEqual(json.loads(f['rede_ids']), [1])
        self.assertEqual(json.loads(f['pol_ids']), [1])
        self.assertEqual(json.loads(f['refs_rede'])[0], r.ocorrencias[0].tubulacoes[0])
        self.assertEqual(f['ocorr_id'], r.ocorrencias[0].id)
        self.assertEqual(next(p.getFeatures()).geometry().asPoint().x(), f['x_m'])
        self.assertTrue(p.customProperty(MARCA_RESULTADO))
        self.assertFalse(p.startEditing())

    def test_coincidencia_ponto_medio_e_linha_relacionados(self):
        r = self.resultado(['LINESTRING(-2 0,12 0)'])
        wkb = bytes(r.ocorrencias[0].geometria.asWkb())
        p,t,l = criar_camadas_temporarias(r)
        fp,fl = next(p.getFeatures()),next(l.getFeatures())
        self.assertEqual(fp['CLASSIF'],'COINCIDENCIA')
        self.assertEqual(next(t.getFeatures())['geom_repr'],'MEIO_DO_TRECHO')
        self.assertAlmostEqual(fp.geometry().asPoint().x(),5.)
        self.assertEqual(fp['EVT_UID'],fl['EVT_UID'])
        self.assertAlmostEqual(fl.geometry().length(),10.)
        self.assertEqual(wkb,bytes(r.ocorrencias[0].geometria.asWkb()))

    def test_simbologia_categorias_distintas(self):
        p = criar_camadas_temporarias(self.resultado())[0]
        renderer = p.renderer()
        self.assertEqual(renderer.type(),'categorizedSymbol')
        self.assertEqual(renderer.classAttribute(),'CLASSIF')
        cats = renderer.categories()
        self.assertEqual({c.value() for c in cats},set(ESTILOS))
        self.assertEqual(len({c.symbol().color().name() for c in cats}),6)

    def test_regioes_multiplas_e_ids_nulos_sem_truncamento(self):
        r = self.resultado(poligonos=[quadrado(),quadrado(5)],modo=Modo.TRANSICAO)
        r.ocorrencias[0].tubulacoes[0]['id_original'] = None
        r.ocorrencias[0].tubulacoes[0]['atributos_originais']['longo'] = 'x'*1000
        saida = criar_camadas_temporarias(r)[1]
        features = list(saida.getFeatures())
        self.assertEqual(json.loads(features[0]['rede_ids']),[None])
        self.assertTrue(any(len(json.loads(f['reg_depois']))==2 for f in features))
        self.assertEqual(json.loads(features[0]['refs_rede'])[0]['atributos_originais']['longo'],'x'*1000)

    def test_continuidade_preserva_ambos_identificadores(self):
        r = self.resultado(['LINESTRING(-2 5,0 5)','LINESTRING(0 5,5 5)'])
        pontos = criar_camadas_temporarias(r)[1]
        f = next(f for f in pontos.getFeatures() if f['classe']=='CONTINUIDADE_POTENCIAL')
        self.assertEqual(json.loads(f['rede_ids']),[1,2])
        self.assertEqual(len(json.loads(f['detalhes'])['extremidades']),2)
        self.assertEqual(f['geom_repr'],'MEIO_DAS_EXTREMIDADES')

    def test_resumo_compartilhada_conta_uma_transicao(self):
        r = self.resultado(['LINESTRING(5 5,15 5)'],[quadrado(),quadrado(10)],Modo.TRANSICAO)
        resumo = resumir(r)
        self.assertEqual(resumo['total'],1)
        self.assertEqual(resumo['camadas'][0]['total'],1)
        self.assertEqual(resumo['classes'],{'TRAVESSIA':1})
        self.assertIn('Tempo do núcleo',texto_resumo(r))

    def test_camada_sem_eventos_no_resumo(self):
        r = self.resultado(['LINESTRING(2 2,3 3)'])
        self.assertEqual(resumir(r)['camadas'][0]['total'],0)
        self.assertEqual(criar_camadas_temporarias(r)[0].featureCount(),0)

    def test_cancelamento_preparacao_sem_publicacao(self):
        projeto = QgsProject()
        with self.assertRaises(Cancelado):
            criar_camadas_temporarias(self.resultado(),cancelar=lambda:True)
        self.assertEqual(projeto.mapLayers(),{})
        r = self.resultado()
        r.cancelado=True
        with self.assertRaises(ValueError):
            criar_camadas_temporarias(r)

    def test_execucoes_em_grupos_separados(self):
        projeto = QgsProject()
        r = self.resultado()
        grupo1 = carregar_no_projeto(criar_camadas_temporarias(r),projeto)
        grupo2 = carregar_no_projeto(criar_camadas_temporarias(r),projeto)
        self.assertNotEqual(grupo1.name(),grupo2.name())
        self.assertEqual(len(projeto.mapLayers()),4)
        projeto.clear()

    def test_json_tipos_identificadores_e_datas(self):
        d = json.loads(texto_json([None,'001',123,2**61,QDate(2026,10,23),
                                  QDateTime(QDate(2026,10,23)),float('nan')]))
        self.assertEqual(d[:4],[None,'001',123,2**61])
        self.assertEqual(d[4]['valor'],'2026-10-23')
        self.assertEqual(d[6],{'tipo':'float','valor':'nan'})


class InterfaceTest(unittest.TestCase):
    def setUp(self):
        self.projeto = QgsProject()
        self.rede1 = camada('LineString',['LINESTRING(-2 5,12 5)'],nome='nome livre')
        self.rede2 = camada('LineString',['LINESTRING(-2 7,12 7)'],nome='nome livre')
        self.setores = camada('Polygon',[quadrado(),quadrado(10)],nome='nome livre')
        self.area = camada('Polygon',[quadrado(2,2,6)],nome='outra área')
        for c in (self.rede1,self.rede2,self.setores,self.area):
            self.projeto.addMapLayer(c)
        self.janela = AuditoriaFronteirasDialog(projeto=self.projeto)
        self.warning = patch('auditoria_fronteiras.interface.QMessageBox.warning').start()
        self.critical = patch('auditoria_fronteiras.interface.QMessageBox.critical').start()
        # Estes testes exercitam processamento, não a nova confirmação/navegação.
        patch('auditoria_fronteiras.interface.AuditoriaFronteirasDialog.confirmar_processamento',return_value=True).start()
        patch('auditoria_fronteiras.interface.AuditoriaFronteirasDialog.resolver_pendencias',return_value=True).start()

    def tearDown(self):
        self.janela.close()
        self.janela.deleteLater()
        APP.processEvents()
        self.projeto.clear()
        patch.stopall()

    def marcar(self,tabela,camada,modo=None):
        for linha in range(tabela.rowCount()):
            item=tabela.item(linha,0)
            if item.data(Qt.UserRole)==camada.id():
                item.setCheckState(Qt.Checked)
                combo=tabela.cellWidget(linha,2)
                combo.setCurrentIndex(combo.findData('id'))
                if tabela is self.janela.limites:
                    combo=tabela.cellWidget(linha,3)
                    combo.setCurrentIndex(combo.findData('nome'))
                    if modo:
                        combo=tabela.cellWidget(linha,4)
                        combo.setCurrentIndex(combo.findData(modo.value))
                return linha
        self.fail('Camada ausente na interface')

    def configurar(self):
        self.marcar(self.janela.redes,self.rede1)
        self.marcar(self.janela.redes,self.rede2)
        self.marcar(self.janela.limites,self.setores,Modo.TRANSICAO)
        self.marcar(self.janela.limites,self.area,Modo.PERIMETRO)

    def test_multiplas_camadas_com_nomes_iguais_e_modos_individuais(self):
        self.configurar()
        redes,limites,p = self.janela.configuracoes()
        self.assertEqual({c.camada.id() for c in redes},{self.rede1.id(),self.rede2.id()})
        por_id = {c.camada.id(): c for c in limites}
        self.assertEqual(por_id[self.setores.id()].modo,Modo.TRANSICAO)
        self.assertEqual(por_id[self.area.id()].modo,Modo.PERIMETRO)
        self.assertTrue(all(c.campo_id=='id' for c in redes+limites))
        self.janela.tolerancia.setValue(.003)
        self.janela.continuidade.setValue(2.5)
        self.assertEqual(self.janela.configuracoes()[2].tolerancia_geometrica,.003)
        self.assertEqual(self.janela.configuracoes()[2].distancia_continuidade,2.5)

    def test_atualizar_preserva_configuracao_e_exclui_resultados(self):
        self.configurar()
        r=auditar(*self.janela.configuracoes())
        carregar_no_projeto(criar_camadas_temporarias(r),self.projeto)
        self.janela.atualizar_camadas()
        self.assertEqual(self.janela.redes.rowCount(),2)
        self.assertEqual(self.janela.limites.rowCount(),2)
        self.assertEqual(len(self.janela.configuracoes()[0]),2)
        self.assertEqual({c.modo for c in self.janela.configuracoes()[1]},set(Modo))

    def test_sem_selecao_ou_camada_removida(self):
        with self.assertRaises(ValueError):
            self.janela.configuracoes()
        self.configurar()
        self.projeto.removeMapLayer(self.rede1.id())
        with self.assertRaises(ValueError):
            self.janela.configuracoes()

    def test_execucao_chama_nucleo_e_carrega_sem_alterar_entradas(self):
        self.configurar()
        self.rede1.selectAll()
        def estado(c):
            return ([(bytes(f.geometry().asWkb()),f.attributes()) for f in c.getFeatures()],
                    c.selectedFeatureIds(), c.renderer().dump(), c.source())
        antes=estado(self.rede1)
        with patch('auditoria_fronteiras.interface.auditar',wraps=auditar) as nucleo:
            self.janela.executar_auditoria()
            self.assertEqual(nucleo.call_count,1)
        self.critical.assert_not_called()
        self.warning.assert_not_called()
        self.assertIsNotNone(self.janela.resultado)
        self.assertEqual(len(self.janela.camadas_geradas),2)
        self.assertEqual(len(self.projeto.mapLayers()),6)
        self.assertEqual(antes,estado(self.rede1))
        self.assertFalse(self.rede1.isEditable())
        self.assertIn('Tempo total',self.janela.resumo.toPlainText())
        self.assertIn('TRANSICAO',self.janela.resumo.toPlainText())
        self.assertTrue(self.janela.executar.isEnabled())

    def test_cancelamento_modal_nao_publica_parcial(self):
        self.configurar()
        def cancelar():
            from auditoria_fronteiras.atividade import sistema
            sistema(self.janela).atual.cancelar()
        QTimer.singleShot(0,cancelar)
        self.janela.executar_auditoria()
        self.critical.assert_not_called()
        self.assertEqual(self.janela.camadas_geradas,[])
        self.assertEqual(len(self.projeto.mapLayers()),4)
        self.assertIn('CANCELADO',self.janela.resumo.toPlainText())
        self.assertTrue(self.janela.executar.isEnabled())

    def test_erro_configuracao_nao_altera_projeto(self):
        self.janela.executar_auditoria()
        self.warning.assert_called_once()
        self.assertEqual(len(self.projeto.mapLayers()),4)
        self.assertFalse(self.janela._executando)

    def test_erro_preparacao_preserva_projeto_e_habilita_interface(self):
        self.configurar()
        with patch('auditoria_fronteiras.interface.criar_camadas_temporarias',side_effect=RuntimeError('falha simulada')):
            self.janela.executar_auditoria()
        self.critical.assert_called_once()
        self.assertEqual(len(self.projeto.mapLayers()),4)
        self.assertTrue(self.janela.executar.isEnabled())


if __name__=='__main__':
    unittest.main(verbosity=2)
