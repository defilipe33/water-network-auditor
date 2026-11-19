"""Entrega 1: cadastro alimenta o motor geométrico sem formulários de entrada."""
import unittest,tempfile,sqlite3
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from qgis.core import QgsProject,QgsCoordinateTransformContext,QgsCoordinateReferenceSystem,QgsGeometry,QgsCoordinateTransform
from qgis.PyQt.QtCore import Qt,QCoreApplication,QEvent
from qgis.PyQt import sip
from qgis.PyQt.QtWidgets import QMessageBox
from test_auditoria_fronteiras import APP,camada
import test_nova_interface as fixture
from auditoria_aplicacao.modelo_gis import configurar,descrever
from auditoria_aplicacao.analise_modelo_gis import preparar,executar,reservar,persistir,publicar,conferir_contexto
from auditoria_fronteiras import CamadaEntrada,Parametros,Modo,auditar
from auditoria_fronteiras.modelos import Cancelado
from auditoria_fronteiras.persistencia import carregar_execucao,historico

class AdaptadorGIS(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.rede=camada('LineString',['LINESTRING(-2 5,12 5)','LINESTRING(-2 6,12 6)'],ids=[101,202],nome='Rede sem nome obrigatório')
  self.area=camada('Polygon',['POLYGON((0 0,10 0,10 10,0 10,0 0))'],nome='Área cadastrada')
  self.fontes=[self.fonte(self.rede,'PIPE'),self.fonte(self.area,'SETOR')]
 def fonte(self,c,k,filtro=''):
  return configurar(descrever(c),k,'EXISTENTE','',{'id':'id','label':'nome'},filtro)
 def prep(self,fontes=None,objetivo='verificar'):
  return preparar(self.fontes if fontes is None else fontes,[self.rede,self.area],Parametros(),QgsCoordinateTransformContext(),objetivo,projeto_uid='projeto',revisao_uid='revisao')
 def rodar(self,p=None):return executar(p or self.prep(),'Ensaio sintético','Projeto sintético')
 def test_reutiliza_motor_sem_alterar_contagens(self):
  p=self.prep();d=self.rodar(p)
  antigo=auditar([CamadaEntrada(self.rede,'id','nome',chave_origem=self.fontes[0]['uid'])],[CamadaEntrada(self.area,'id','nome',chave_origem=self.fontes[1]['uid'])])
  self.assertEqual(len(d['eventos']),len(antigo.ocorrencias));self.assertGreater(len(d['eventos']),0)
  self.assertEqual(sorted(x['tecnico']['classificacao'] for x in d['eventos']),sorted(x.classificacao for x in antigo.ocorrencias))
 def test_filtro_por_fonte_preserva_id_original(self):
  self.fontes[0]['filtro']='id = 202';d=self.rodar()
  self.assertEqual({x['id_bruto'] for x in d['tubulacoes']},{202});self.assertEqual(self.rede.subsetString(),'')
 def test_uma_fonte_multiplos_filtros(self):
  a=self.fonte(self.rede,'PIPE','id = 101');b=self.fonte(self.rede,'PIPE','id = 202')
  d=self.rodar(self.prep([a,b,self.fontes[1]]));self.assertEqual({x['origem'] for x in d['tubulacoes']},{a['uid'],b['uid']})
 def test_poligonos_independentes_por_categoria(self):
  self.fontes.append(self.fonte(self.area,'ZONA_VRP'));d=self.rodar();self.assertEqual(len(d['poligonos']),2)
 def test_sem_watergems_e_proveniencia(self):
  d=self.rodar();p=d['configuracao']['modelo_gis'];self.assertEqual(p['revisao_uid'],'revisao');self.assertEqual(p['fontes'][0]['campos']['id'],'id')
  self.assertNotIn('watergems',p)
 def test_objetivos_diferenciam_modo(self):
  p=self.prep(objetivo='fronteiras');self.assertEqual(p.limites[0].modo,Modo.TRANSICAO)
  self.assertNotEqual(p.limites[0].modo,self.prep(objetivo='interferencias').limites[0].modo)
 def test_fonte_indisponivel(self):
  f=deepcopy(self.fontes);f[0]['camada_id']='ausente'
  with self.assertRaisesRegex(ValueError,'indisponível'):self.prep(f)
 def test_esquema_alterado_bloqueia_sem_recadastro(self):
  f=deepcopy(self.fontes);f[0]['assinatura']='antiga'
  with self.assertRaisesRegex(ValueError,'alterada'):self.prep(f)
 def test_mapeamento_ausente(self):
  f=deepcopy(self.fontes);f[0]['campos_mapeados']['id']='apagado'
  with self.assertRaisesRegex(ValueError,'Mapeamento'):self.prep(f)
 def test_id_nao_mapeado_chave_tecnica_explicita(self):
  self.fontes[0]['campos_mapeados'].pop('id');p=self.prep();self.assertTrue(p.avisos);d=self.rodar(p)
  self.assertTrue(all(x['id_bruto'] is None for x in d['tubulacoes']));self.assertTrue(all(x['uid'] for x in d['tubulacoes']))
 def test_sem_limites_explicita_motor_disponivel(self):
  with self.assertRaisesRegex(ValueError,'áreas de referência'):self.prep([self.fontes[0]])
 def test_crs_em_graus_nao_e_metro(self):
  with self.assertRaises(ValueError):preparar(self.fontes,[self.rede,self.area],Parametros(crs='EPSG:4326'),QgsCoordinateTransformContext())
 def test_crs_diferentes_reprojeta_sem_escrever(self):
  crs=QgsCoordinateReferenceSystem('EPSG:31983');dest=QgsCoordinateReferenceSystem('EPSG:4326')
  trans=QgsCoordinateTransform(crs,dest,QgsCoordinateTransformContext());g=QgsGeometry.fromWkt('LINESTRING(330000 7390000,330010 7390010)');g.transform(trans)
  c=camada('LineString',[g.asWkt(15)],crs='EPSG:4326');f=self.fonte(c,'PIPE');antes=bytes(next(c.getFeatures()).geometry().asWkb())
  p=preparar([f,self.fontes[1]],[c,self.area],Parametros(),QgsCoordinateTransformContext())
  copy=next(p.redes[0].camada.getFeatures());self.assertLess(abs(copy.geometry().asPolyline()[0].x()-330000),.001)
  self.assertEqual(bytes(next(c.getFeatures()).geometry().asWkb()),antes)
 def test_cancelamento_sem_resultado_publicado(self):
  p=self.prep()
  with self.assertRaises(Cancelado):executar(p,'teste','teste',lambda:True)
  self.assertEqual(list(Path(self.tmp.name).iterdir()),[])
 def test_publicacao_integridade_historico_e_nao_sobrescrever(self):
  d=self.rodar();tmp,final=reservar(self.tmp.name,d['contexto']['parametros']['crs']);persistir(tmp,d);publicar(tmp,final)
  aberto=carregar_execucao(final,d['execucao_uid']);self.assertEqual(aberto['configuracao']['modelo_gis'],d['configuracao']['modelo_gis'])
  outro,_=reservar(self.tmp.name,d['contexto']['parametros']['crs'])
  with self.assertRaises(FileExistsError):publicar(outro,final)
  self.assertTrue(final.is_file())
 def test_contexto_alterado_nao_publica(self):
  p=self.prep()
  with self.assertRaises(ValueError):conferir_contexto(p,self.fontes,[self.rede,self.area],'outro','revisao')
  f=deepcopy(self.fontes);f[0]['filtro']='id = 101'
  with self.assertRaises(ValueError):conferir_contexto(p,f,[self.rede,self.area],'projeto','revisao')
 def test_equipamentos_sao_contexto_sem_associacao_geometrica(self):
  f=self.fonte(self.rede,'PIPE');equips=deepcopy(f);equips['categoria']='TANK'
  p=self.prep([f,self.fontes[1],equips]);self.assertEqual(p.proveniencia['referencias'][0]['categoria'],'TANK');self.assertEqual(len(p.redes),1)
 def test_sem_mutacao_selecao_simbologia(self):
  self.rede.selectAll();ids=self.rede.selectedFeatureIds();xml=self.rede.renderer().dump();self.rodar()
  self.assertEqual(self.rede.selectedFeatureIds(),ids);self.assertEqual(self.rede.renderer().dump(),xml)

def limpar_fixture(f):
 f.doCleanups()
 # O cenário embutido cria uma janela e um canvas por caso. Fechar apenas oculta:
 # destruir deterministicamente enquanto o runtime QGIS ainda está disponível.
 for w in (f.f.canvas,f.f.main):
  if not sip.isdeleted(w):w.deleteLater()
 QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

class PaginaGIS(unittest.TestCase):
 def setUp(self):
  self.f=fixture.AmbienteTest();self.f.setUp();self.addCleanup(limpar_fixture,self.f)
  self.c,self.m,self.app=self.f.c,self.f.m,self.f.f.app
  r=camada('LineString',['LINESTRING(-2 5,12 5)','LINESTRING(-2 6,12 6)'],ids=[101,202],nome='Distribuição')
  r2=camada('LineString',['LINESTRING(5 -2,5 12)'],ids=[303],nome='Rede complementar')
  a=camada('Polygon',['POLYGON((0 0,10 0,10 10,0 10,0 0))'],nome='Setores')
  QgsProject.instance().addMapLayers([r,r2,a])
  self.redes=[r,r2];self.area=a
  self.f.cadastrar('PIPE',[r], 'id = 202');self.f.cadastrar('PIPE',[r2]);self.f.cadastrar('SETOR',[a])
  for cat in ('PRV','TCV','TANK'):self.f.cadastrar(cat,[self.f.valvula])
  for cat in ('ZONA_VRP','ZONA_BOOSTER'):self.f.cadastrar(cat,[a])
  self.assertTrue(self.m.salvar());self.c.abrir_analise_gis('verificar');self.p=self.c.analise_gis
  self.p.pasta.setText(str(self.app.catalogo.raiz/'ensaios_gis'))
 def iniciar(self):self.p.iniciar();self.f.aguardar();self.assertIsNotNone(self.p.dossie,self.p.info.text());return self.p.dossie
 def test_entrada_contextual_sem_formulario_antigo(self):
  self.assertIs(self.c.paginas.currentWidget(),self.p);self.assertFalse(self.app.geo.isVisible());self.assertIsNone(self.c._central_legada)
  self.assertIn('2 fonte(s) de tubulações',self.p.resumo.text())
 def test_execucao_multifonte_sem_wg(self):
  d=self.iniciar();self.assertIsNone(self.app.wg);self.assertTrue(Path(self.p.base).is_file());self.assertGreater(len(d['eventos']),0)
  self.assertNotIn(101,{x['id_bruto'] for x in d['tubulacoes']});self.assertFalse(self.app.geo.isVisible())
 def test_ocorrencia_destacada_sem_zoom_automatico(self):
  self.iniciar();antes=self.f.f.canvas.extent();self.p.destacar();self.assertTrue(self.c.mapa.itens);self.assertEqual(self.f.f.canvas.extent(),antes)
 def test_observacao_historico_e_reabertura(self):
  d=self.iniciar();self.p.lista.selectRow(0);self.p.observacao.setPlainText('Verificar esta travessia.');self.assertTrue(self.p.salvar_observacao())
  self.p.observacao.setPlainText('Conferência adicional.');self.assertTrue(self.p.salvar_observacao())
  uid=self.p.selecionado['uid'];self.assertEqual(len(historico(self.p.base,d['execucao_uid'],uid)),2)
  r=dict(tipo='AUDITORIA_GIS',base=self.p.base,uuid=d['execucao_uid'],nome='Teste');self.assertTrue(self.p.abrir_persistida(r));self.f.aguardar()
  self.assertEqual(next(l for l in self.p.dossie['locais'] if l['uid']==uid)['revisao']['observacoes'],'Conferência adicional.')
 def test_cancelar_rascunho_impede_saida(self):
  self.iniciar();self.p.observacao.setPlainText('Rascunho')
  with patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel):self.assertFalse(self.app.preparar_saida())
  self.p.observacao.setPlainText('')
 def test_reabertura_nao_duplica_camadas(self):
  d=self.iniciar();n=len(QgsProject.instance().mapLayers());self.p.carregar_camadas();self.assertEqual(len(QgsProject.instance().mapLayers()),n)
 def test_execucao_repetida_durante_worker_ignorada(self):
  self.p._executando=True
  with patch.object(self.app.atividades,'executar_thread') as t:self.p.iniciar();t.assert_not_called()
  self.p._executando=False
 def test_cancelar_worker_restaura_interface_sem_publicar(self):
  self.p.iniciar();self.app.atividades.atual.cancelar();self.f.aguardar()
  self.assertFalse(self.p._executando);self.assertTrue(self.p.executar_b.isEnabled())
  self.assertIsNone(self.p.dossie);self.assertIsNone(self.p._temporario)
  self.assertEqual(list(Path(self.p.pasta.text()).glob('*.gpkg')),[])
 def test_fonte_removida_gera_orientacao(self):
  QgsProject.instance().removeMapLayer(self.redes[0]);self.p.iniciar();self.assertIsNone(self.p.dossie);self.assertIn('indisponível',self.p.info.text())
 def test_trocar_objetivo_nao_apresenta_resultado_anterior_com_outro_titulo(self):
  self.iniciar();base=self.p.base;self.assertTrue(self.p.abrir('fronteiras'))
  self.assertIsNone(self.p.dossie);self.assertTrue(Path(base).is_file())
 def test_cancelar_abertura_pergunta_uma_vez_e_preserva_rascunho(self):
  d=self.iniciar();self.p.observacao.setPlainText('Rascunho preservado')
  r=dict(tipo='AUDITORIA_GIS',base=self.p.base,uuid=d['execucao_uid'],nome='Teste')
  with patch.object(self.c,'registro_trabalho',return_value=r),patch('auditoria_aplicacao.contexto_trabalho.validar_registro',return_value={'valido':True}),patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel) as pergunta:
   self.assertFalse(self.c.abrir_trabalho());self.assertEqual(pergunta.call_count,1)
  self.assertEqual(self.p.observacao.toPlainText(),'Rascunho preservado');self.p.observacao.clear()
 def test_reabertura_identifica_objetivo_original(self):
  self.p.abrir('fronteiras');d=self.iniciar()
  r=dict(tipo='AUDITORIA_GIS',base=self.p.base,uuid=d['execucao_uid'],nome='Fronteiras')
  self.p.abrir('verificar');self.p.abrir_persistida(r);self.f.aguardar()
  self.assertEqual(self.p.objetivo,'fronteiras');self.assertEqual(self.p.titulo.text(),'Zonas e fronteiras')
 def test_secoes_fonte_e_filtro_unificado(self):
  self.c.abrir_modelo_gis();self.c.quadro.escolher('REDES');self.m.editar();e=self.m.editor
  e.abrir_visual.setChecked(True);self.assertIsNotNone(e.construtor);self.assertTrue(e.amostra_mais.menu());self.assertEqual(self.m.salvar_b.objectName(),'Principal')

if __name__=='__main__':unittest.main()
