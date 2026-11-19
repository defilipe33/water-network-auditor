"""Contratos de atualização incremental, invalidação e diagnóstico opcional."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtTest import QTest
from qgis.core import QgsField, QgsProject
import test_nova_interface as interface_fixture
from auditoria_aplicacao.diagnostico import Diagnostico


class DesempenhoTest(unittest.TestCase):
    def setUp(self):
        self.fixture=interface_fixture.AmbienteTest();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.c,self.m=self.fixture.c,self.fixture.m

    def test_legado_ausente_na_navegacao(self):
        self.assertIsNone(self.c._central_legada)
        for g in self.c.quadro.cards:self.c.quadro.escolher(g)
        self.assertIsNone(self.c._central_legada)

    def test_um_resumo_por_clique_sem_metadados_ou_catalogo(self):
        self.fixture.cadastrar()
        with patch.object(self.c.quadro,'atualizar',wraps=self.c.quadro.atualizar) as q, \
             patch('auditoria_aplicacao.modelo_gis_ui.estado_fonte') as fonte, \
             patch.object(self.c.app.catalogo,'listar_opcional') as catalogo:
            for g in self.c.quadro.cards:self.c.quadro.escolher(g)
            self.assertEqual(q.call_count,4);fonte.assert_not_called();catalogo.assert_not_called()

    def test_requisitos_sem_atualizar_central_oculta(self):
        with patch('auditoria_aplicacao.central.CentralTrabalho.atualizar') as antigo, \
             patch.object(self.c.app.catalogo,'listar_opcional') as catalogo, \
             patch('auditoria_aplicacao.contexto_trabalho.fatos',return_value={}) as fatos:
            self.c._contexto_lido=None
            self.c.atualizar();self.c.atualizar()
            antigo.assert_not_called();catalogo.assert_not_called()
            self.assertEqual(fatos.call_count,1)
            anterior=self.c.app.geo.base_revisao
            self.c.app.geo.base_revisao='outra_base_sintetica.gpkg';self.c.atualizar()
            self.assertEqual(fatos.call_count,2)
            self.c.app.geo.base_revisao=anterior

    def test_legado_unico_compartilha_cadastro(self):
        self.c.abrir_avancados();legado=self.c._central_legada
        self.assertIs(legado.modelo_gis,self.m);self.assertIs(legado.projetos,self.c.projetos)
        self.assertFalse(legado.timer.isActive())
        self.c.abrir_modelo_gis();self.c.abrir_avancados();self.assertIs(self.c._central_legada,legado)

    def test_cache_invalidado_por_mapeamento_filtro_e_resultado(self):
        f=self.fixture.cadastrar()
        self.assertEqual(self.m.pendencias_fonte(f),[])
        f['campos_mapeados'].pop('id');self.assertIn('Identificador por mapear',self.m.pendencias_fonte(f))
        self.m.resultados[f['uid']]={'total':0};f['filtro']='id > 10'
        self.assertIn('Filtro sem resultados',self.m.pendencias_fonte(f))
        f['filtro']='';self.assertNotIn('Filtro sem resultados',self.m.pendencias_fonte(f))

    def test_alerta_lote_nao_desaparece_no_cache(self):
        f=self.fixture.cadastrar();self.m.alertas_lote[f['uid']]=['Campo ausente no destino']
        self.assertEqual(self.m.pendencias_fonte(f),self.m.pendencias_fonte(f))
        self.assertIn('Campo ausente no destino',self.m.pendencias_fonte(f))

    def test_mudanca_provedor_invalida_conferencia(self):
        f=self.fixture.cadastrar(camadas=[self.fixture.redes[0]]);c=self.fixture.redes[0]
        self.m.resultados[f['uid']]={'total':1}
        c.dataProvider().addAttributes([QgsField('campo_novo',QVariant.String)]);c.updateFields()
        self.c.quadro.escolher('REDES')
        self.assertFalse(self.m._refresh_fontes.isActive())
        QTest.qWait(30)
        self.assertFalse(self.m.resultados)
        self.assertIn('alterada',self.m._estado[f['uid']].lower())

    def test_remocao_camada_invalida_estado(self):
        f=self.fixture.cadastrar(camadas=[self.fixture.redes[0]]);QgsProject.instance().removeMapLayer(self.fixture.redes[0].id())
        self.assertNotEqual(self.m._estado[f['uid']],'Disponível')

    def test_fonte_alheia_nao_invalida_conferencia(self):
        f=self.fixture.cadastrar(camadas=[self.fixture.redes[0]])
        self.m.resultados[f['uid']]={'total':1}
        outra=self.fixture.redes[1]
        outra.dataProvider().addAttributes([QgsField('outra_coluna',QVariant.String)]);outra.updateFields();QTest.qWait(20)
        self.assertEqual(self.m.resultados[f['uid']],{'total':1})
        self.assertFalse(self.m._refresh_fontes.isActive())

    def test_catalogo_indice_so_rele_quando_marca_muda(self):
        with patch.object(self.c,'marca',return_value=('a',)) as marca, \
             patch.object(self.c.app.catalogo,'listar_opcional',return_value=[]) as ler:
            self.c.garantir_catalogo();self.c.garantir_catalogo();self.assertEqual(ler.call_count,1)
            marca.return_value=('b',);self.c.garantir_catalogo();self.assertEqual(ler.call_count,2)

    def test_projeto_novo_limpa_cache_e_rascunho_anterior(self):
        self.fixture.cadastrar();self.assertTrue(self.m.salvar())
        self.m.pendencias_fonte(self.m.fontes[0]);self.assertTrue(self.m._pendencias_cache)
        self.c.projetos.criar('Outro projeto');self.c._carregar_projetos();self.m.recarregar();self.c.atualizar()
        self.assertFalse(self.m.fontes);self.assertFalse(self.m._pendencias_cache)

    def test_propriedades_ocultas_sao_criadas_uma_vez(self):
        self.fixture.cadastrar();self.c.quadro.escolher('REDES');self.m.editar();ed=self.m.editor
        self.assertFalse(ed._avancados);self.assertIsNone(ed._papel)
        antes=ed.valores();ed.abrir_adicionais.setChecked(True)
        self.assertTrue(ed._avancados);papel=ed.papel;ed.abrir_adicionais.setChecked(False);ed.abrir_adicionais.setChecked(True)
        self.assertIs(ed.papel,papel);self.assertEqual(ed.valores(),antes)

    def test_mapeamentos_adicionais_preservados_sem_abrir(self):
        f=self.fixture.cadastrar();f['campos_mapeados']['material']='nome'
        self.c.quadro.escolher('REDES');self.m.selecionada=f['uid'];self.m.atualizar_categoria();self.m.editar();ed=self.m.editor
        self.assertFalse(ed._avancados);self.assertEqual(ed.valores()[0]['material'],'nome')
        self.assertFalse(ed.pendente());self.assertEqual(ed.mapa['material'].currentData(),'nome')
        self.assertTrue(ed._avancados)


class DiagnosticoTest(unittest.TestCase):
    def test_desabilitado_nao_instrumenta_ou_grava(self):
        with tempfile.TemporaryDirectory() as t:
            d=Diagnostico(Path(t)/'inexistente',False)
            d.envolver(json,'dumps');self.assertEqual(d.medir('op',lambda:7),7);d.salvar()
            self.assertFalse(d.pasta.exists())

    def test_restauracao_sem_argumentos_sensiveis(self):
        with tempfile.TemporaryDirectory() as t:
            original=json.dumps
            with Diagnostico(t) as d:
                d.envolver(json,'dumps','serializar');d.envolver(json,'dumps','duplicada')
                d.medir('operacao',lambda:json.dumps({'segredo_teste':'não publicar'}),3)
                self.assertEqual(d.chamadas['serializar'],3)
            self.assertIs(json.dumps,original)
            texto=d.salvar().read_text();self.assertNotIn('segredo_teste',texto)
            self.assertEqual(len(d.resultados),1)

    def test_perfil_nao_aceita_caminho_externo(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):Diagnostico(t).perfil('../externo',lambda:0)


if __name__=='__main__':unittest.main()
