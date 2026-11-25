"""Seleções cartográficas e revisões da conectividade GIS em PyQGIS."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import test_grafo_gis as etapa2
from qgis.core import QgsCoordinateReferenceSystem, QgsGeometry, QgsProject
from auditoria_aplicacao import hipoteses_gis as hg, persistencia_grafo_gis as pg
from auditoria_aplicacao.grafo_gis import construir
from auditoria_aplicacao.mapa_topologia_gis import (
    CONTEXTO, MapaTopologiaGIS, IndiceSelecao, escolher, estilo_conexao, fracao_clicada,
)


class Mapa(unittest.TestCase):
    def setUp(self):
        self.mapa = MapaTopologiaGIS()
        self.crs = QgsCoordinateReferenceSystem('EPSG:31983')
        self.projeto = QgsProject.instance()
        self.addCleanup(self.projeto.clear)

    def test_sobreposicao_preserva_as_duas_identidades(self):
        a = etapa2.linha('fonte_a', (0, 0), (20, 0))
        b = etapa2.linha('fonte_b', (0, 0), (20, 0))
        a['id'] = b['id'] = '009'
        ponto = QgsGeometry.fromWkt('POINT(8 0.1)')
        resultados = IndiceSelecao([a, b]).consultar(ponto, .2)
        self.assertEqual([r[1] for r in resultados], ['fonte_a', 'fonte_b'])
        with patch('auditoria_aplicacao.mapa_topologia_gis.QInputDialog.getItem',
                   return_value=('009 · opção 2', True)):
            self.assertEqual(escolher(None, resultados, lambda r: r[2]['id'])[1], 'fonte_b')
        self.assertEqual(fracao_clicada(a['geom'], ponto, .2), .4)
        self.assertEqual(fracao_clicada(a['geom'], QgsGeometry.fromWkt('POINT(19.9 0)'), .2), 1.)

    def test_reutiliza_camadas_e_exibe_apenas_simbolos_visiveis(self):
        origem = dict(uuid='origem', tipo='ORIGEM', situacao='INFORMADA', nome='Teste',
                     xy=[100, 115], crs=self.crs.toWkt(), pontos_rede=[[100, 105]],
                     crs_rede=self.crs.toWkt())
        self.mapa.atualizar('projeto-sintetico', self.crs, [origem], {'origem'})
        ids = dict(self.mapa.camadas)
        fontes = self.projeto.mapLayer(ids['origens'])
        self.assertEqual([f['Estado'] for f in fontes.getFeatures()], ['INFORMADA'])
        self.assertEqual(self.projeto.mapLayer(ids['vinculos']).featureCount(), 1)
        ponto = QgsGeometry.fromWkt('POINT(100 115)')
        self.assertTrue(self.mapa.consultar(ponto, self.crs, .5))
        no = self.projeto.layerTreeRoot().findLayer(fontes.id())
        no.setItemVisibilityChecked(False)
        self.mapa.atualizar('projeto-sintetico', self.crs, [origem], set())
        self.assertEqual(ids, self.mapa.camadas)
        self.assertEqual([f['Estado'] for f in fontes.getFeatures()], ['DESABILITADA'])
        self.assertFalse(self.mapa.consultar(ponto, self.crs, .5))
        self.assertEqual(self.projeto.mapLayer(ids['vinculos']).featureCount(), 0)
        self.assertEqual(sum(g.customProperty(CONTEXTO)=='projeto-sintetico'
                             for g in self.projeto.layerTreeRoot().findGroups()), 1)

    def test_simbologia_discrimina_interpretacao_e_participacao(self):
        regra = dict(candidato='t', situacao='INFORMADA', decisao='CONFIRMADA')
        self.assertEqual(estilo_conexao(regra, True), 'CONFIRMADA')
        self.assertEqual(estilo_conexao(dict(regra, candidato=None), True), 'DECLARADA')
        self.assertEqual(estilo_conexao(dict(regra, situacao='PROPOSTA'), True), 'HIPOTESE')
        self.assertEqual(estilo_conexao(dict(regra, decisao='SEPARADA'), True), 'SEPARADA')
        self.assertEqual(estilo_conexao(regra, False), 'FORA')


class Hipoteses(unittest.TestCase):
    def test_gravar_nova_revisao_nao_altera_participacao_antiga(self):
        with TemporaryDirectory() as pasta:
            base = Path(pasta)/'complementos.gpkg'
            pg.criar_complementos(base, 'projeto')
            origem = pg.salvar_revisao(base, 'projeto', 'ORIGEM',
                dict(situacao='INFORMADA', portas=[['p', .5]], habilitado=True))
            a = pg.salvar_revisao(base, 'projeto', 'HIPOTESE',
                hg.dados_hipotese('Análise A', 'projeto', {}, [origem], 'assinatura'))
            alterada = pg.salvar_revisao(base, 'projeto', 'ORIGEM',
                dict(origem, habilitado=False), origem['uuid'], origem['rev'])
            b = pg.salvar_revisao(base, 'projeto', 'HIPOTESE',
                hg.dados_hipotese('Análise A', 'projeto', {}, [], 'assinatura'), a['uuid'], a['rev'])
            por_revisao = {r['rev']:r for r in pg.revisoes(base, 'projeto')}
            self.assertEqual(b['anterior'], a['rev'])
            self.assertEqual(hg.resolver_vinculos(a, por_revisao)[origem['uuid']]['rev'], origem['rev'])
            self.assertEqual(hg.resolver_vinculos(b, por_revisao), {})
            self.assertFalse(pg.vigentes(base, 'projeto')[alterada['uuid']]['habilitado'])
            with self.assertRaisesRegex(ValueError, '1.16.0'):
                hg.resolver_vinculos({'selecionados':[origem['uuid']]}, por_revisao)

    def test_compara_uniao_divisao_e_acesso_a_origem(self):
        tubos = [etapa2.linha('a', (0, 0), (20, 0)), etapa2.linha('b', (10, .05), (10, 20))]
        fonte = dict(tipo='ORIGEM', uuid='s', rev='s1', situacao='INFORMADA', portas=[('a', 0.)])
        anterior = construir(tubos, origens=[fonte])
        cand = next(d for d in anterior['diagnosticos'] if d['tipo']=='CONEXAO_T')
        conexao = dict(tipo='CONEXAO', uuid='t', rev='t1', decisao='CONFIRMADA',
                       portas=cand['portas'], candidato=cand['uid'])
        depois = construir(tubos, origens=[fonte], conexoes=[conexao])
        anterior.update(projeto_uid='sintetico', participantes=[fonte])
        depois.update(projeto_uid='sintetico', participantes=[fonte, conexao])
        uniao = hg.comparar_execucoes(anterior, depois)
        divisao = hg.comparar_execucoes(depois, anterior)
        self.assertEqual(uniao['componentes'], [2, 1])
        self.assertEqual(uniao['unioes'], 1)
        self.assertEqual(divisao['divisoes'], 1)
        self.assertAlmostEqual(uniao['passou_alcancar_m'], 19.95)
        self.assertIn('PERDEU', {r['tipo'] for r in divisao['diferencas']})
        self.assertEqual(depois['resolucoes_conexoes'], {'t':'APLICADA'})
        inadmissivel = construir(tubos, conexoes=[dict(conexao, candidato='modificado')])
        self.assertEqual(inadmissivel['resolucoes_conexoes'], {'t':'REFERENCIA_ALTERADA'})
        self.assertEqual(len(inadmissivel['componentes']), 2)


class Fluxo(unittest.TestCase):
    def setUp(self):
        fixture = etapa2.InterfaceGIS()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.painel = fixture.t
        self.aguardar = fixture.f.aguardar

    def test_salva_reexecuta_e_reabre_configuracao_exata(self):
        t = self.painel
        t._gravar_hipotese('Original')
        self.aguardar()
        a = t._hip_ativa
        self.assertTrue(a, t.status.text())
        t.iniciar(modo='salva')
        self.aguardar()
        d = t.dados
        self.assertTrue(d, t.status.text())
        self.assertEqual(d['hipotese']['rev'], a['rev'])
        t.limite.setValue(360.)
        t.iniciar(modo='temporaria')
        self.aguardar()
        self.assertIsNone(t.dados['hipotese'])
        self.assertNotEqual(t.dados['uuid'], d['uuid'])
        t._gravar_hipotese('Atualizada', a)
        self.aguardar()
        self.assertEqual(t._hip_ativa['anterior'], a['rev'])
        t._aplicar(a)
        self.assertEqual(t.limite.value(), a['configuracao']['parametros']['limite_mm'])
        t.iniciar(modo='salva')
        self.aguardar()
        self.assertEqual(t.dados['hipotese']['rev'], a['rev'])
        self.assertNotEqual(t.dados['uuid'], d['uuid'])

    def test_acompanhamento_independente_da_interpretacao_e_filtro(self):
        t = self.painel
        t.iniciar()
        self.aguardar()
        inicial = t.dados['componentes']
        escolhido = t._selecionado()
        t.acompanhamento.setCurrentIndex(t.acompanhamento.findData('VERIFICADO'))
        with patch('auditoria_aplicacao.topologia_gis_ui.QInputDialog.getMultiLineText',
                   return_value=('', True)):
            t.anotar()
        self.assertEqual(t._selecionado()['uid'], escolhido['uid'])
        self.assertEqual(t._acompanhamento(escolhido), 'Verificado')
        self.assertEqual(t.dados['componentes'], inicial)
        t.historico_resultado()
        self.assertIn('Verificado',t.historico.toPlainText())
        t.busca.setText('Verificado')
        t.mudar_resultados()
        t.ordenar_resultados(3)
        self.assertEqual(t.resultados.rowCount(),1)
        self.assertEqual(t._selecionado()['uid'], escolhido['uid'])

    def test_modelo_gis_revisionado_preserva_parametros_da_hipotese(self):
        t = self.painel
        t._gravar_hipotese('Antes da mudança cadastral')
        self.aguardar()
        a = t._hip_ativa
        from auditoria_aplicacao.modelo_gis import salvar_modelo
        anterior=t._revisao()
        nova = salvar_modelo(t.central.projetos,t.uid_projeto,anterior['uuid'],
                            anterior['fontes'],'INFERIR' if anterior['estrategia']!='INFERIR' else 'CADASTRADAS')
        self.assertNotEqual(a['configuracao']['modelo_rev'], nova['uuid'])
        self.assertEqual(t._revisao_operacional()['uuid'], anterior['uuid'])
        t.iniciar(modo='salva')
        self.aguardar()
        self.assertIsNotNone(t.dados,t.status.text())
        self.assertEqual(t.dados['modelo_rev'], anterior['uuid'])


if __name__ == '__main__':
    unittest.main()
