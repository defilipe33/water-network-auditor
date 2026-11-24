"""Relevância não altera fatos geométricos, conectividade ou decisões."""
import csv,json,sqlite3,unittest
from copy import deepcopy
from pathlib import Path
from hashlib import sha256
from unittest.mock import patch
import test_integracao_modelo_gis as anterior
from qgis.core import QgsProject,QgsGeometry,QgsFeature,QgsCoordinateReferenceSystem
from qgis.PyQt.QtWidgets import QMessageBox
from auditoria_aplicacao.relevancia_gis import classificar,calcular,resumo,VERSAO
from auditoria_aplicacao.investigacao_gis import IndiceInvestigacao
from auditoria_aplicacao.contexto_equipamentos_gis import ContextoEquipamentos,preparar,ler
from auditoria_aplicacao.associacoes_gis import referencia,declarar
from auditoria_aplicacao.exportacao_investigacao_gis import exportar_tabelas,copiar_gpkg


def evento(classe='TRAVESSIA',ambiguo='NAO'):
 return dict(uid='evento',tecnico=dict(classificacao=classe),registro=dict(AMBIGUO=ambiguo))


class Regras(unittest.TestCase):
 def regra(self,classe):return classificar(evento(classe),['tubo'],{'tubo'})
 def test_travessia_setor_informativa(self):self.assertEqual(self.regra('TRAVESSIA')['categoria'],'INFORMATIVA')
 def test_travessia_vrp_informativa(self):self.assertEqual(self.regra('TRAVESSIA')['criterio'],'CONTATO_COM_FRONTEIRA')
 def test_travessia_booster_informativa(self):self.assertNotIn('defeito',self.regra('TRAVESSIA')['motivo'])
 def test_tangencia_informativa(self):self.assertEqual(self.regra('TANGENCIA')['categoria'],'INFORMATIVA')
 def test_extremidade_na_fronteira_nao_prova_isolamento(self):self.assertEqual(self.regra('EXTREMIDADE')['categoria'],'INFORMATIVA')
 def test_coincidencia_e_com_fronteira_nao_sobreposicao_de_tubos(self):self.assertEqual(self.regra('COINCIDENCIA')['categoria'],'INFORMATIVA')
 def test_continuidade_proxima_revisar(self):self.assertEqual(self.regra('CONTINUIDADE_POTENCIAL')['categoria'],'REVISAR')
 def test_cruzamento_sem_regra_nao_inventa_conexao(self):self.assertEqual(self.regra('CRUZAMENTO')['categoria'],'INDETERMINADA')
 def test_ambiguidade_geometrica_revisar(self):self.assertEqual(self.regra('AMBIGUA')['categoria'],'REVISAR')
 def test_travessia_ambigua_revisar(self):self.assertEqual(classificar(evento(ambiguo='SIM'),['tubo'],{'tubo'})['categoria'],'REVISAR')
 def test_ambiguidade_tecnica(self):
  e=evento();e['tecnico']['ambigua']=True;self.assertEqual(classificar(e,['tubo'],{'tubo'})['categoria'],'REVISAR')
 def test_sem_classificacao(self):self.assertEqual(self.regra(None)['categoria'],'INDETERMINADA')
 def test_sem_vinculos(self):self.assertEqual(classificar(evento(),[],set())['categoria'],'INDETERMINADA')
 def test_referencia_explicitamente_ausente(self):self.assertEqual(classificar(evento(),['ausente'],set())['categoria'],'INCONSISTENCIA_IDENTIFICADA')
 def test_nao_muta_evento(self):
  e=evento();antes=deepcopy(e);classificar(e,['tubo'],{'tubo'});self.assertEqual(e,antes)
 def test_assinatura_reproduzivel(self):self.assertEqual(self.regra('TRAVESSIA'),self.regra('TRAVESSIA'))
 def test_regra_versionada(self):self.assertEqual(self.regra('TRAVESSIA')['regra'],VERSAO)
 def test_revisao_nao_muda_relevancia(self):
  e=evento();r=classificar(e,['tubo'],{'tubo'});e['situacao']='VERIFICADO';self.assertEqual(classificar(e,['tubo'],{'tubo'}),r)
 def test_proximidade_nao_muda_relevancia(self):
  e=evento();e['equipamentos_proximos']=['BOOSTER'];self.assertEqual(classificar(e,['tubo'],{'tubo'})['categoria'],'INFORMATIVA')
 def test_contagens_incluem_zeros(self):self.assertEqual(sum(resumo({'e':self.regra('TRAVESSIA')}).values()),1)
 def test_equipo_distante_declarado_continua_visivel(self):
  r=dict(fonte_uid='f',id='R',nome='Reservatório',categoria='RESERVOIR',camada='Reservatórios',geometria=QgsGeometry.fromWkt('POINT(900 900)'),tubos={'t'},declaracoes=['a'])
  c=ContextoEquipamentos([r]);rs=c.consultar([QgsGeometry.fromWkt('POINT(0 0)')],{'t'},20)
  self.assertEqual(rs[0]['relacao'],'Associação declarada');self.assertGreater(rs[0]['distancia'],20)
 def test_equipamento_proximo_sem_associacao(self):
  r=dict(geometria=QgsGeometry.fromWkt('POINT(1 1)'),tubos=set());rs=ContextoEquipamentos([r]).consultar([QgsGeometry.fromWkt('POINT(0 0)')],set(),20)
  self.assertEqual(rs[0]['relacao'],'Proximidade geométrica apenas')
 def test_contexto_recusa_distancias_em_graus(self):
  with self.assertRaises(ValueError):preparar([],[],'EPSG:4326',QgsProject.instance().transformContext())
 def test_associacao_consultada_por_indice_sem_varrer_equipamentos(self):
  r=dict(geometria=QgsGeometry.fromWkt('POINT(900 900)'),tubos={'tubo'})
  c=ContextoEquipamentos([r])
  class AcessoIndexado(list):
   def __iter__(self):raise AssertionError('Consulta não deve varrer o inventário.')
  c.registros=AcessoIndexado(c.registros)
  self.assertEqual(c.consultar([],{'tubo'},20)[0]['relacao'],'Associação declarada')


class Interface(unittest.TestCase):
 def setUp(self):
  self.f=anterior.PaginaGIS();self.f.setUp();self.addCleanup(self.f.doCleanups)
  self.d=self.f.iniciar();self.p=self.f.p;self.uid=self.p.selecionado['uid'];self.e=self.p.selecionado['eventos'][0]
 def test_fila_inicial_e_todos(self):
  self.p.filtro_relevancia.setCurrentIndex(self.p.filtro_relevancia.findData('ATENCAO'))
  self.assertEqual(self.p.lista.rowCount(),0);self.assertIn('Todas as ocorrências',self.p.pagina_info.text())
  self.p.limpar_filtros();self.assertGreater(self.p.lista.rowCount(),0)
 def test_informativo_pendente(self):
  self.assertEqual(self.p.indice.relevancias[self.e]['categoria'],'INFORMATIVA');self.assertEqual(self.p.situacao.currentData(),'PENDENTE')
 def test_gravacao_individual_protege_e_restaura_renderizacao(self):
  canvas=self.f.f.f.canvas;self.p.alvo.setCurrentIndex(self.p.alvo.findData(self.e))
  self.p.situacao.setCurrentIndex(self.p.situacao.findData('VERIFICADO'));self.p.salvar_decisao()
  self.assertTrue(canvas.isFrozen());self.f.f.aguardar();self.assertFalse(canvas.isFrozen());self.assertEqual(self.p.indice.revisoes[self.e]['situacao'],'VERIFICADO')
 def test_falha_de_gravacao_restaura_mapa_e_rascunho(self):
  canvas=self.f.f.f.canvas;self.p.alvo.setCurrentIndex(1);self.p.observacao.setPlainText('Preservar rascunho')
  with patch('auditoria_aplicacao.painel_investigacao_gis.individuais.salvar',side_effect=ValueError('Falha sintética')):
   self.p.salvar_decisao();self.f.f.aguardar()
  self.assertFalse(canvas.isFrozen());self.assertEqual(self.p.observacao.toPlainText(),'Preservar rascunho')
  self.p.observacao.clear()
 def test_preserva_mapa_previamente_congelado(self):
  canvas=self.f.f.f.canvas;canvas.freeze(True);self.p.situacao.setCurrentIndex(self.p.situacao.findData('VERIFICADO'))
  self.assertTrue(self.p.salvar_decisao());self.assertTrue(canvas.isFrozen());canvas.freeze(False)
 def test_misto_sem_contaminacao_de_relevancia(self):
  d=deepcopy(self.d);es=d['locais'][0]['eventos'];self.assertGreater(len(es),1)
  next(e for e in d['eventos'] if e['uid']==es[0])['tecnico']['classificacao']='CONTINUIDADE_POTENCIAL'
  i=IndiceInvestigacao(d);self.assertEqual(i.relevancias[es[0]]['categoria'],'REVISAR');self.assertEqual(i.relevancias[es[1]]['categoria'],'INFORMATIVA')
  self.assertTrue(i.filtrar(relevancia='ATENCAO'));self.assertFalse(i.filtrar(relevancia='ATENCAO',classe='TANGENCIA'))
 def test_filtro_regiao_e_relevancia(self):
  nome=self.d['poligonos'][0]['camada'];self.assertTrue(self.p.indice.filtrar(regiao=nome,relevancia='INFORMATIVA'));self.assertFalse(self.p.indice.filtrar(regiao='inexistente'))
 def test_ponto_no_mapa_abre_uuid(self):
  c=next(c for c in QgsProject.instance().mapLayers().values() if c.customProperty('wna/tecnico')=='EVENTOS_FRONTEIRAS')
  f=next(f for f in c.getFeatures() if f['EVT_UID']==self.e)
  self.p.filtro_relevancia.setCurrentIndex(0);antes=self.f.f.f.canvas.extent();c.selectByIds([f.id()])
  self.assertEqual(self.p._evento_uid,self.e);self.assertEqual(self.p.selecionado['uid'],self.uid);self.assertEqual(antes,self.f.f.f.canvas.extent())
 def test_simbologia_virtual_preserva_base(self):
  c=next(c for c in QgsProject.instance().mapLayers().values() if c.customProperty('wna/tecnico')=='EVENTOS_FRONTEIRAS')
  self.assertEqual(c.renderer().type(),'categorizedSymbol');self.assertEqual(next(c.getFeatures())['WNA_RELEVANCIA'],'INFORMATIVA')
  with sqlite3.connect(self.p.base) as con:self.assertNotIn('WNA_RELEVANCIA',[r[1] for r in con.execute('PRAGMA table_info(EVENTOS_FRONTEIRAS)')])
 def test_execucao_unica_nao_exige_subset_ogr(self):
  cs=[c for c in QgsProject.instance().mapLayers().values() if c.customProperty('wna/categoria')=='gis']
  self.assertTrue(cs);self.assertTrue(all(not c.subsetString() for c in cs))
 def test_base_compartilhada_isola_execucao(self):
  from auditoria_fronteiras.persistencia import salvar_execucao
  d=deepcopy(self.d);d['execucao_uid']='outra_execucao_sintetica'
  salvar_execucao(self.p.base,d,reconciliar=False);self.p.carregar_camadas()
  c=next(c for c in QgsProject.instance().mapLayers().values() if c.customProperty('wna/tecnico')=='EVENTOS_FRONTEIRAS')
  self.assertTrue(c.subsetString());self.assertEqual(len(list(c.getFeatures())),len(self.d['eventos']))
  self.assertEqual({f['EXE_UID'] for f in c.getFeatures()},{self.d['execucao_uid']})
 def test_renderer_usuario_preservado_ao_reabrir(self):
  c=next(c for c in QgsProject.instance().mapLayers().values() if c.customProperty('wna/tecnico')=='EVENTOS_FRONTEIRAS')
  from qgis.core import QgsSingleSymbolRenderer,QgsMarkerSymbol
  c.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple({'color':'pink'})));antes=c.renderer().dump();self.p.carregar_camadas();self.assertEqual(c.renderer().dump(),antes)
 def test_cor_personalizada_na_mesma_categoria_preservada(self):
  c=next(c for c in QgsProject.instance().mapLayers().values() if c.customProperty('wna/tecnico')=='EVENTOS_FRONTEIRAS')
  from qgis.PyQt.QtGui import QColor
  from auditoria_aplicacao.mapa_relevancia_gis import assinatura_renderer
  categorias=c.renderer().categories()
  simbolo=categorias[0].symbol().clone();simbolo.setColor(QColor('pink'));c.renderer().updateCategorySymbol(0,simbolo)
  antes=assinatura_renderer(c);self.p.carregar_camadas();self.assertEqual(assinatura_renderer(c),antes)
 def test_indice_da_nova_analise_preparado_no_worker(self):
  from qgis.PyQt.QtCore import QThread
  threads=[]
  def construir(*args,**kwargs):
   threads.append(QThread.currentThread()!=self.p.thread());return IndiceInvestigacao(*args,**kwargs)
  with patch('auditoria_aplicacao.analise_gis_ui.IndiceInvestigacao',side_effect=construir):self.p.iniciar();self.f.f.aguardar()
  self.assertEqual(threads,[True])
 def test_indice_da_reabertura_preparado_no_worker(self):
  from qgis.PyQt.QtCore import QThread
  threads=[]
  def construir(*args,**kwargs):
   threads.append(QThread.currentThread()!=self.p.thread());return IndiceInvestigacao(*args,**kwargs)
  with patch('auditoria_aplicacao.analise_gis_ui.IndiceInvestigacao',side_effect=construir):
   self.p.abrir_persistida(dict(base=self.p.base,uuid=self.d['execucao_uid'],nome='Antiga'));self.f.f.aguardar()
  self.assertEqual(threads,[True])
 def test_legado_reclassificado_sem_escrever_historico(self):
  self.p.situacao.setCurrentIndex(self.p.situacao.findData('VERIFICADO'));self.p.salvar_decisao();antes=sha256(Path(self.p.base).read_bytes()).hexdigest()
  self.p.abrir_persistida(dict(base=self.p.base,uuid=self.d['execucao_uid'],nome='Antiga'));self.f.f.aguardar()
  self.assertEqual(sha256(Path(self.p.base).read_bytes()).hexdigest(),antes);self.assertEqual(self.p.indice.situacao(self.uid),'VERIFICADO')
 def test_exportacao_todas_categorias(self):
  dest=Path(self.p.base).parent/'relevancia';dest.mkdir();exportar_tabelas(self.d,dest,self.p.base)
  with (dest/'RELEVANCIA_EVENTOS.csv').open(encoding='utf-8-sig') as f:rs=list(csv.DictReader(f))
  self.assertEqual(len(rs),len(self.d['eventos']));self.assertTrue(all(r['REGRA']==VERSAO for r in rs))
  antes=sha256(Path(self.p.base).read_bytes()).hexdigest();copiar_gpkg(self.p.base,dest/'copia.gpkg',self.d['execucao_uid'],lambda:False)
  with sqlite3.connect(dest/'copia.gpkg') as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM WNA_RELEVANCIA_EVENTOS').fetchone()[0],len(rs))
  self.assertEqual(sha256(Path(self.p.base).read_bytes()).hexdigest(),antes)
 def test_contexto_consultado_sem_mudar_relevancia(self):
  antes=deepcopy(self.p.indice.relevancias);self.p.consultar_equipamentos();self.f.f.aguardar()
  self.assertIsNotNone(self.p._equipamentos,self.p.equipamentos_info.text());self.assertEqual(antes,self.p.indice.relevancias)
  self.assertTrue(self.p.filtro_equipamento.isEnabled());self.p.filtro_equipamento.setText('PRV');self.p.filtrar();self.assertGreater(self.p.lista.rowCount(),0)
 def test_contexto_invalidado_apos_remover_fonte(self):
  self.p.consultar_equipamentos();self.f.f.aguardar();self.assertTrue(self.p.equipamentos_validos())
  QgsProject.instance().removeMapLayer(self.f.f.valvula.id());self.assertFalse(self.p.equipamentos_validos())
 def test_reservatorio_associado_validado_por_identidade(self):
  m=self.f.m;f=next(f for f in m.fontes if f['categoria']=='TANK');pipe=next(f for f in m.fontes if f['categoria']=='PIPE')
  camada=self.f.f.valvula;pr=next(self.f.redes[0].getFeatures())
  # A fonte de tubos tem filtro id=202; escolher exatamente essa feição.
  pr=next(r for r in self.f.redes[0].getFeatures() if r['id']==202)
  nova=declarar(f,referencia(f,next(camada.getFeatures())),[referencia(pipe,pr)])
  fontes=[nova if x['uid']==f['uid'] else x for x in m.fontes]
  prep=preparar(fontes,list(m.camadas()),self.d['contexto']['parametros']['crs'],QgsProject.instance().transformContext())
  c,avisos=ler(prep,self.d);self.assertTrue(any(r['tubos'] for r in c.registros),avisos)


if __name__=='__main__':unittest.main()
