"""Contratos sintéticos de apresentação, evidências e adaptação de telas."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_auditoria_fronteiras import APP,camada
from test_topologia_watergems import modelo
from test_bases_plugin import banco_nativo
from qgis.core import QgsGeometry,QgsProject,QgsVectorFileWriter,QgsCoordinateTransformContext
from qgis.PyQt.QtCore import QRect,Qt
from qgis.PyQt.QtWidgets import QDialog,QVBoxLayout,QLabel,QPushButton,QHBoxLayout,QFormLayout,QComboBox,QMessageBox
from auditoria_fronteiras.ui_comum import adaptar_janela,ajustar_rect
from auditoria_fronteiras.tabelas_consulta import TabelaConsulta,texto_valor
from auditoria_topologica_watergems import referencia_espacial as ref,bases
from auditoria_topologica_watergems.gerenciamento import registros_gis,preparar_integracao
from auditoria_topologica_watergems.arquivos import hash_arquivo


REF=dict(crs='EPSG:31983',fator=1,fonte='Controle sintético com referência métrica independente',unidade_bruta='METRO')
def registros(m=None):
    m=m or modelo()
    return [dict(uid='gis-'+str(i),origem='rede',camada='Rede sintética',campo='codigo',bruto=e['label'],chave_cadastral=e['label'],geometria=QgsGeometry.fromWkt('LINESTRING(0 0,1 0)' if i==10 else 'LINESTRING(1 0,2 0)')) for i,e in m['elementos'].items() if e['familia']=='LINK']


class ReferenciaTest(unittest.TestCase):
    def test_sem_referencia_pendente(self):self.assertEqual(ref.estado_referencia(None)['estado'],'PENDENTE')
    def test_declaracao_legada_reabre(self):self.assertTrue(ref.estado_referencia(REF)['legada']);self.assertEqual(ref.estado_referencia(REF)['estado'],'VALIDADO')
    def test_graus_nao_metros(self):self.assertEqual(ref.estado_referencia(dict(REF,crs='EPSG:4326'))['estado'],'PENDENTE')
    def test_unidade_e_fator_incompativeis(self):self.assertEqual(ref.estado_referencia(dict(REF,fator=.3048))['estado'],'INCOMPATIVEL')
    def test_fator_nao_finito_bloqueado(self):self.assertEqual(ref.estado_referencia(dict(REF,fator=float('nan')))['estado'],'PENDENTE')
    def test_fonte_obrigatoria(self):self.assertEqual(ref.estado_referencia(dict(REF,fonte=''))['estado'],'PENDENTE')
    def test_previa_cadastral_nao_e_inequivoca(self):
        p=ref.previa(modelo(),registros());self.assertFalse(p['espacial']);self.assertTrue(all(a['situacao']=='UNICA_CADASTRAL_SEM_PROVA_ESPACIAL' for a in p['associacoes']))
    def test_previa_graus_nao_calcula_distancias(self):self.assertFalse(ref.previa(modelo(),registros(),dict(REF,crs='EPSG:4326'))['espacial'])
    def test_previa_geometria_confirma_pares(self):
        p=ref.previa(modelo(),registros(),REF);self.assertEqual(p['camadas'][0]['unicas'],2);self.assertEqual(p['evidencia']['pares_ate_tolerancia'],2)
    def test_pes_internacionais_conferidos_sem_modificar_brutos(self):
        from qgis.PyQt.QtGui import QTransform
        m=modelo()
        for e in m['elementos'].values():
            g=QgsGeometry();g.fromWkb(e['geometria']);g.transform(QTransform.fromScale(1/.3048,1/.3048));e['geometria']=bytes(g.asWkb())
        antes=copy.deepcopy(m);r=dict(REF,fator=.3048,unidade_bruta='PE_INTERNACIONAL');p=ref.previa(m,registros(),r)
        self.assertEqual(p['evidencia']['pares_ate_tolerancia'],2);self.assertEqual(m,antes);self.assertEqual(ref.estado_referencia(r)['estado'],'VALIDADO')
    def test_candidatos_repetidos_entre_fontes(self):
        regs=registros();regs.append(dict(regs[0],uid='gis-copia',origem='outra'))
        p=ref.previa(modelo(),regs,REF);self.assertEqual(sum(a['situacao']=='MULTIPLAS_CANDIDATAS' for a in p['associacoes']),2)
    def test_labels_repetidos_no_modelo(self):
        m=modelo();m['elementos'][11]['label']='E-10';p=ref.previa(m,registros(),REF)
        self.assertEqual(p['associacoes'][0]['situacao'],'MULTIPLAS_CANDIDATAS')
    def test_nulo_vazio_zero_e_zeros_esquerda(self):
        m=modelo();m['elementos'][10]['label']='0007';m['elementos'][11]['label']='0';rs=registros(m)
        for i,k in enumerate([None,'']):rs.append(dict(rs[0],uid='extra'+str(i),bruto=k,chave_cadastral=k))
        p=ref.previa(m,rs,REF);c=p['camadas'][0];self.assertEqual((c['nulos'],c['vazios'],c['nao_encontradas']),(1,1,2));self.assertIn('0007',[a['chave_cadastral'] for a in p['associacoes']])
    def test_inconsistencia_geometrica_visivel(self):
        rs=registros();rs[0]['geometria']=QgsGeometry.fromWkt('LINESTRING(20 0,21 0)');p=ref.previa(modelo(),rs,REF)
        self.assertEqual(p['camadas'][0]['inconsistencias_geometricas'],1)
    def test_amostras_preservam_geometrias_completas(self):
        p=ref.previa(modelo(),registros(),REF);self.assertTrue(all(x[11].startswith('LineString') for x in p['amostras']))
    def test_confirmacao_produz_proveniencia(self):
        m=modelo();p=ref.previa(m,registros(),REF);r=ref.confirmar_prova(m,REF,p,'Responsável sintético')
        self.assertEqual(ref.estado_referencia(r,m)['estado'],'VALIDADO');self.assertEqual(r['validacao']['responsavel'],'Responsável sintético');self.assertEqual(r['validacao']['contexto_modelo'],ref.contexto_modelo(m))
    def test_confirmacao_sem_pares_nao_libera(self):
        with self.assertRaises(ValueError):ref.confirmar_prova(modelo(),REF,ref.previa(modelo(),[],REF))
    def test_unidade_nao_declarada_nao_confirma(self):
        r={k:v for k,v in REF.items() if k!='unidade_bruta'}
        with self.assertRaises(ValueError):ref.confirmar_prova(modelo(),r,ref.previa(modelo(),registros(),r))
    def test_modelo_diferente_rejeita_reuso(self):
        e=dict(modelo='outro',referencia=REF,contexto=ref.contexto_modelo(modelo()))
        self.assertEqual(ref.compatibilidade(modelo(),e)['estado'],'INCOMPATIVEL')
    def test_mesmo_crs_nao_prova_compatibilidade(self):
        m=modelo();e=dict(modelo=m['projeto'],referencia=REF,contexto=ref.contexto_modelo(m));m['cenario']=2
        self.assertEqual(ref.compatibilidade(m,e)['estado'],'INCOMPATIVEL')
    def test_geometria_ou_atividade_mudou_revalida(self):
        m=modelo();e=dict(modelo=m['projeto'],referencia=REF,contexto=ref.contexto_modelo(m));m['elementos'][11]['ativo']=False
        self.assertEqual(ref.compatibilidade(m,e)['estado'],'INCOMPATIVEL')
    def test_json_antigo_sem_contexto_e_pendente(self):
        self.assertEqual(ref.compatibilidade(modelo(),dict(referencia=REF,contexto=None))['estado'],'PENDENTE')
    def test_referencia_confirmada_nao_migra_para_modelo_alterado(self):
        m=modelo();r=ref.confirmar_prova(m,REF,ref.previa(m,registros(),REF));m['elementos'][10]['label']='outra'
        self.assertEqual(ref.estado_referencia(r,m)['estado'],'INCOMPATIVEL')


class PersistenciaReferenciaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True);cls.p=Path(cls.tmp.name);cls.fonte=cls.p/'controle.sqlite';banco_nativo(cls.fonte)
        cls.sem=bases.criar(cls.fonte,cls.p/'sem.gpkg',nome='Controle',projeto='Ensaio')
        cls.com=bases.criar(cls.fonte,cls.p/'com.gpkg',nome='Controle',projeto='Ensaio',referencia=REF)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_reuso_legado_com_contexto_comprovado(self):
        m=bases.restaurar(self.sem)['modelo'];e=ref.ler_evidencia(self.com);self.assertEqual(ref.compatibilidade(m,e)['estado'],'VALIDADO');r=ref.referencia_reutilizada(m,e)
        self.assertEqual(r['fator'],1);self.assertEqual(r['validacao']['sha256_anterior'],hash_arquivo(self.com))
    def test_salva_nova_versao_sem_alterar_base_ou_sqlite(self):
        h=[hash_arquivo(self.sem),hash_arquivo(self.fonte)];t=bases.restaurar(self.sem);r=ref.referencia_reutilizada(t['modelo'],ref.ler_evidencia(self.com))
        nova=ref.salvar_referencia(self.sem,self.p/'nova.gpkg',r);nt=bases.restaurar(nova)
        self.assertEqual(nt['meta_base']['anterior'],t['meta_base']['uuid']);self.assertEqual(nt['meta_base']['versao'],2)
        self.assertEqual(nt['modelo']['elementos'],t['modelo']['elementos']);self.assertEqual(nt['estrutural']['conexoes'],t['estrutural']['conexoes']);self.assertTrue(nt['metrica']);self.assertEqual(h,[hash_arquivo(self.sem),hash_arquivo(self.fonte)])
    def test_reuso_incompativel_nao_grava(self):
        t=bases.restaurar(self.sem);e=ref.ler_evidencia(self.com);e['contexto']='incompativel'
        with self.assertRaises(ValueError):ref.referencia_reutilizada(t['modelo'],e)
    def test_referencia_nao_confirmada_nao_grava(self):
        with self.assertRaises(ValueError):ref.salvar_referencia(self.sem,self.p/'proibida.gpkg',REF)
        self.assertFalse((self.p/'proibida.gpkg').exists())
    def test_cancelamento_preserva_base(self):
        t=bases.restaurar(self.sem);r=ref.referencia_reutilizada(t['modelo'],ref.ler_evidencia(self.com));h=hash_arquivo(self.sem)
        with self.assertRaises(InterruptedError):ref.salvar_referencia(self.sem,self.p/'cancelada.gpkg',r,cancelar=lambda:True)
        self.assertEqual(hash_arquivo(self.sem),h);self.assertFalse((self.p/'cancelada.gpkg').exists())
    def test_integracao_espacial_bloqueada_antes_de_publicar(self):
        from test_inspecao_exportacao import preparar
        from auditoria_fronteiras.persistencia import salvar_execucao
        _,_,d,_,_=preparar();geo=self.p/'geo_bloqueio.gpkg';salvar_execucao(geo,d)
        with self.assertRaisesRegex(ValueError,'nenhuma integração foi publicada'):preparar_integracao(geo,d['execucao_uid'],self.sem,self.p/'nunca_criada')
        self.assertFalse((self.p/'nunca_criada').exists())
    def test_consulta_topologica_sem_fonte_sem_geometria_inventada(self):
        from auditoria_aplicacao.consulta_base import ConsultaBase
        with patch.object(bases,'Banco',side_effect=AssertionError('Não reextrair')):
            j=ConsultaBase(self.sem);j.tipo.setCurrentIndex(1);self.assertGreater(j.tabela.rowCount(),0);j.close()
            t=bases.restaurar(self.sem);self.assertFalse(t['metrica']);self.assertFalse(t['geometrias'])


class LayoutTabelasTest(unittest.TestCase):
    def test_resolucoes_dpi_e_multimonitor(self):
        for w,h in [(1366,768),(1920,1080)]:
            for escala in [1,1.25,1.5,1.75,2]:
                for x in [0,-int(w/escala)]:
                    a=QRect(x,0,int(w/escala),int(h/escala)-35);r=ajustar_rect(QRect(4000,4000,5000,5000),a)
                    self.assertTrue(a.contains(r),(w,h,escala,x,r));self.assertLessEqual(r.width(),a.width()-30);self.assertLessEqual(r.height(),a.height()-50)
    def test_rolagem_e_botoes_fora_do_conteudo(self):
        j=QDialog();v=QVBoxLayout(j)
        for i in range(45):v.addWidget(QLabel('Conteúdo '+str(i)))
        l=QHBoxLayout();l.addWidget(QPushButton('Confirmar'));l.addWidget(QPushButton('Cancelar'));v.addLayout(l);adaptar_janela(j);j.show();APP.processEvents()
        self.assertGreater(j._wna_scroll.verticalScrollBar().maximum(),0);self.assertFalse(j._wna_scroll.widget().isAncestorOf(j.findChildren(QPushButton)[-1]));j.close()
    def test_formulario_responsivo(self):
        j=QDialog();v=QVBoxLayout(j);f=QFormLayout();v.addLayout(f);f.addRow('Campo de identificação muito extenso',QComboBox());adaptar_janela(j)
        self.assertEqual(f.rowWrapPolicy(),QFormLayout.WrapLongRows);j.close()
    def test_tabela_preserva_nulos_textos_longos_e_zeros(self):
        t=TabelaConsulta(['ID','Texto']);longo='Texto integral '*1000;t.preencher([[None,longo],['0007',''],[0,'zero']])
        valores=[(t.tabela.item(r,0).data(Qt.UserRole),t.tabela.item(r,1).data(Qt.UserRole)) for r in range(3)]
        self.assertIn((None,longo),valores);self.assertIn(('0007',''),valores);self.assertIn((0,'zero'),valores)
        self.assertEqual(texto_valor(None),'〈nulo〉');self.assertEqual(texto_valor(''),'〈vazio〉');self.assertNotEqual(texto_valor(0),texto_valor(None))
    def test_filtro_e_colunas_configuraveis(self):
        t=TabelaConsulta(['ID','Texto']);t.preencher([['0007','um'],['0008','dois']]);t.busca.setText('dois')
        for r in range(2):self.assertEqual(t.tabela.isRowHidden(r),t.tabela.item(r,1).text()!='dois')
        t.colunas.menu().actions()[0].setChecked(False);self.assertTrue(t.tabela.isColumnHidden(0))
    def test_adaptacao_idempotente(self):
        j=QDialog();QVBoxLayout(j).addWidget(QLabel('Teste'));adaptar_janela(j);a=j._wna_scroll;adaptar_janela(j);self.assertIs(j._wna_scroll,a);j.close()


class RegistrosGISTest(unittest.TestCase):
    def setUp(self):
        from qgis.core import QgsVectorLayer,QgsFeature
        self.tmp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True);self.p=Path(self.tmp.name)/'entrada.gpkg'
        c=QgsVectorLayer('LineString?crs=EPSG:31983&field=id_auditoria:string&field=chave_label:string','Rede sintética','memory')
        for i,valor in enumerate(['0007','0','',None]):
            f=QgsFeature(c.fields());f.setAttributes(['ID-A-'+str(i),valor]);f.setGeometry(QgsGeometry.fromWkt(f'LINESTRING({i} 0,{i+1} 0)'));c.dataProvider().addFeatures([f])
        op=QgsVectorFileWriter.SaveVectorOptions();op.driverName='GPKG';op.layerName='rede'
        erro=QgsVectorFileWriter.writeAsVectorFormatV3(c,str(self.p),QgsCoordinateTransformContext(),op);self.assertEqual(erro[0],QgsVectorFileWriter.NoError)
        self.d=dict(contexto=dict(fontes=[dict(origem='rede',camada='Rede sintética',campo_id='id_auditoria',fonte=str(self.p)+'|layername=rede',provedor='ogr',modo=None)]))
    def tearDown(self):self.tmp.cleanup()
    def test_campo_correspondencia_diferente_do_campo_auditoria(self):
        rs,_=registros_gis(self.d,{'rede':'chave_label'},'EPSG:31983');self.assertEqual([r['chave_cadastral'] for r in rs],['0007','0','',None]);self.assertEqual({r['campo'] for r in rs},{'chave_label'})
    def test_nao_escolhe_campo_automaticamente(self):
        rs,avisos=registros_gis(self.d,{});self.assertFalse(rs);self.assertTrue(avisos)
    def test_campo_inexistente_orienta(self):
        with self.assertRaisesRegex(ValueError,'Fonte/campo indisponível'):registros_gis(self.d,{'rede':'inexistente'})
    def test_fonte_preservada(self):
        h=hash_arquivo(self.p);registros_gis(self.d,{'rede':'chave_label'},'EPSG:31983');self.assertEqual(hash_arquivo(self.p),h)


class FluxoWatergemsTest(unittest.TestCase):
    def setUp(self):
        from test_aplicacao_unificada import InterfaceUnificadaTest
        self.fixture=InterfaceUnificadaTest();self.fixture.setUp();self.fixture.carregar();self.app=self.fixture.app;self.app.bases();self.w=self.app.wg
        self.meta=dict(nome='Modelo sintético',projeto='Projeto',cenario=1,versao=1,uuid='base-sintetica',hipotese='TODAS_VALVULAS_ABERTAS',resumo=dict(componentes=1),resumo_potencial=dict(componentes=1),referencia_espacial={})
        self.patch_meta=patch('auditoria_aplicacao.watergems_ui.bases.metadados',return_value=self.meta);self.patch_meta.start()
        with patch.object(self.app.catalogo,'registrar'):self.w.usar_base('base_sintetica.gpkg')
        self.w._topologia=dict(modelo=modelo())
    def tearDown(self):self.patch_meta.stop();self.fixture.tearDown()
    def test_formulario_inicial_pendente_sem_assumir_crs_unidade(self):
        self.assertIsNone(self.w.unidade.currentData());self.assertFalse(self.w.espacial.isChecked());self.assertFalse(self.w.espacial.isEnabled());self.assertEqual(self.w.crs.text(),'')
    def test_crs_do_gis_so_e_copiado_por_acao_explicita(self):
        self.w.usar_crs_gis();self.assertEqual(self.w.crs.text(),self.app.geo.dossie['contexto']['parametros']['crs']);self.assertFalse(self.w.espacial.isChecked())
    def test_unidade_escolhida_controla_fator(self):
        self.w.unidade.setCurrentIndex(self.w.unidade.findData('PE_INTERNACIONAL'));self.assertAlmostEqual(self.w.fator.value(),.3048);self.assertFalse(self.w.espacial.isChecked())
    def test_edicao_de_crs_invalida_confirmacao(self):
        self.w._referencia_confirmada=REF;self.w.espacial.setChecked(True);self.w.crs.setText('EPSG:31983');self.assertIsNone(self.w._referencia_confirmada);self.assertFalse(self.w.espacial.isChecked())
    def test_cancelar_save_preserva_base_e_confirmacao(self):
        self.w._referencia_confirmada=REF;self.w._ref_pendente=True;antes=self.w.base
        with patch('auditoria_aplicacao.watergems_ui.QFileDialog.getSaveFileName',return_value=('','')):self.assertFalse(self.w.gravar_referencia())
        self.assertEqual(self.w.base,antes);self.assertTrue(self.w._ref_pendente)
    def test_reuso_cancelado_preserva_formulario(self):
        e=dict(modelo='projeto',contexto=ref.contexto_modelo(modelo()),referencia=REF,arquivo='controle.gpkg',sha256='teste');antes=self.w.dados_referencia()
        with patch('auditoria_aplicacao.watergems_ui.QInputDialog.getItem',return_value=('Selecionar GPKG ou JSON de evidência…',True)),patch('auditoria_aplicacao.watergems_ui.QFileDialog.getOpenFileName',return_value=('controle.gpkg','')),patch.object(ref,'ler_evidencia',return_value=e),patch('auditoria_aplicacao.watergems_ui.QMessageBox.question',return_value=QMessageBox.Cancel):self.w.verificar_evidencia()
        self.assertEqual(self.w.dados_referencia(),antes);self.assertIsNone(self.w._referencia_confirmada)
    def test_sem_crs_oferece_topologia_validacao_cancelamento(self):
        class Mensagem:
            AcceptRole=0;ActionRole=1;Cancel=2
            def __init__(s,*a):s.b=[]
            def setWindowTitle(s,*a):pass
            def setText(s,t):self.mensagem=t
            def addButton(s,*a):b=object();s.b.append(b);return b
            def exec_(s):pass
            def clickedButton(s):return s.b[0]
        with patch('auditoria_aplicacao.watergems_ui.QMessageBox',Mensagem),patch.object(self.w,'consultar') as consultar,patch.object(self.app,'integrar') as integrar:
            self.w.integrar();consultar.assert_called_once();integrar.assert_not_called()
        self.assertIn('Nenhum resultado espacial',self.mensagem)
    def test_previa_sem_mapeamento_explica_campo_gis(self):
        with patch('auditoria_aplicacao.watergems_ui.QMessageBox.warning') as aviso:self.assertFalse(self.w.previsualizar())
        self.assertIn('coluna GIS',aviso.call_args[0][2])


if __name__=='__main__':unittest.main()
