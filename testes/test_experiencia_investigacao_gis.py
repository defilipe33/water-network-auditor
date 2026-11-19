"""Regressões de interpretação, vínculo, acompanhamento e mapa; dados sintéticos."""
import csv,sqlite3,unittest
from copy import deepcopy
from pathlib import Path
from hashlib import sha256
from unittest.mock import patch
import test_integracao_modelo_gis as antigo
from qgis.core import QgsProject,QgsGeometry
from qgis.PyQt.QtWidgets import QMessageBox
from auditoria_fronteiras.inspecao import detalhes_local
from auditoria_fronteiras import revisoes_ocorrencias as ro
from auditoria_fronteiras.persistencia import historico
from auditoria_aplicacao.investigacao_gis import IndiceInvestigacao,descricao,geometria
from auditoria_aplicacao.geometrias_investigacao import preparar,localizar
from auditoria_aplicacao.exportacao_investigacao_gis import exportar_tabelas,copiar_gpkg


class ExperienciaGIS(unittest.TestCase):
 def setUp(self):
  self.f=antigo.PaginaGIS();self.f.setUp();self.addCleanup(self.f.doCleanups)
  self.p,self.c,self.app=self.f.p,self.f.c,self.f.app;self.d=self.f.iniciar();self.uid=self.p.selecionado['uid'];self.e=self.p.selecionado['eventos'][0]
 def esperar(self):self.f.f.aguardar()
 def estado(self,k):self.p.situacao.setCurrentIndex(self.p.situacao.findData(k))
 def individual(self,k='VERIFICADO',obs=''):
  self.p.alvo.setCurrentIndex(self.p.alvo.findData(self.e));self.estado(k);self.p.observacao.setPlainText(obs);self.p.salvar_decisao();self.esperar()
 def test_detalhes_equivalentes_ao_contrato_existente(self):
  self.assertEqual(detalhes_local(self.d,self.uid),detalhes_local(self.d,self.uid,self.p.indice))
 def test_multiplicidade_e_classes_visiveis(self):
  self.assertGreater(self.p.eventos_lista.rowCount(),1);self.assertTrue(self.p.descricao_evento.toPlainText());self.assertGreater(self.p.tubos_lista.rowCount(),0)
 def test_ocorrencia_individual_restringe_vinculos(self):
  self.p.alvo.setCurrentIndex(1);d=self.p.indice.detalhes(self.uid,self.e)
  self.assertEqual(len(d['eventos']),1);self.assertEqual(self.p.tubos_lista.rowCount(),len(d['tubulacoes']))
 def test_ocorrencia_de_outro_local_bloqueada(self):
  e=next(e['uid'] for e in self.d['eventos'] if e['uid'] not in self.p.selecionado['eventos'])
  with self.assertRaises(ValueError):self.p.indice.detalhes(self.uid,e)
 def test_classificacoes_diferentes_mesmo_local(self):
  d=deepcopy(self.d);es=d['locais'][0]['eventos'];next(e for e in d['eventos'] if e['uid']==es[0])['tecnico']['classificacao']='COINCIDENCIA'
  i=IndiceInvestigacao(d);self.assertIn('COINCIDENCIA',i.classes[d['locais'][0]['uid']]);self.assertGreater(len(i.classes[d['locais'][0]['uid']]),1)
 def test_descricao_nao_inventa_conexao(self):
  e=deepcopy(self.d['eventos'][0]);e['tecnico']['classificacao']='CONTINUIDADE_POTENCIAL';self.assertIn('não uma conexão confirmada',descricao(e))
 def test_geometria_evento_e_tubulacao_persistida(self):
  self.assertIsNotNone(geometria(self.d['eventos'][0]['tecnico']['geometria_wkb_hex']));self.assertTrue(all(t.get('geometria_wkb_hex') for t in self.d['tubulacoes']))
 def test_destacar_preserva_zoom_e_simbologia(self):
  canvas=self.f.f.f.canvas;antes=canvas.extent();renderer=self.f.redes[0].renderer().dump();self.p.destacar()
  self.assertEqual(canvas.extent(),antes);self.assertEqual(self.f.redes[0].renderer().dump(),renderer);self.assertGreater(len(self.c.mapa.itens),1)
 def test_aproximar_usa_local_atual_e_minimo_metrico(self):
  self.p.aproximar();canvas=self.f.f.f.canvas;caixa=canvas.extent();self.assertGreaterEqual(caixa.width(),30);self.assertGreaterEqual(caixa.height(),30)
  self.assertEqual(self.p._destaque_alvo[0],self.uid);self.assertEqual(self.c.aproximar_b.text(),'Aproximar local')
 def test_nomenclatura_contextual_mapa(self):
  self.c.abrir_modelo_gis();self.assertEqual(self.c.aproximar_b.text(),'Enquadrar destaque')
 def test_tubo_longo_nao_afasta_local_e_extensao_completa_e_opcional(self):
  from qgis.core import QgsCoordinateReferenceSystem
  itens=[('tubo',QgsGeometry.fromWkt('LINESTRING(-2500 0,2500 0)')),('evento',QgsGeometry.fromWkt('POINT(0 0)'))];crs=QgsCoordinateReferenceSystem('EPSG:31983')
  self.c.mapa.destacar_investigacao(itens,crs,True);self.assertLess(self.f.f.f.canvas.extent().width(),1000)
  self.c.mapa.destacar_investigacao(itens,crs,True,True);self.assertGreater(self.f.f.f.canvas.extent().width(),4900)
 def test_sem_geometria_nao_inventa_tubo(self):
  self.p._cache_geometrias={};t=deepcopy(self.d['tubulacoes'][0]);t.pop('geometria_wkb_hex',None);t['uid']='inexistente_1'
  gs,avisos=localizar(preparar(self.d,[t],QgsProject.instance()),self.d['contexto']['parametros']['crs']);self.assertFalse(gs);self.assertTrue(avisos)
 def test_reconstroi_legado_por_assinatura(self):
  ts=deepcopy(self.d['tubulacoes']);[t.pop('geometria_wkb_hex',None) for t in ts]
  gs,avisos=localizar(preparar(self.d,ts,QgsProject.instance()),self.d['contexto']['parametros']['crs']);self.assertEqual(set(gs),{t['uid'] for t in ts});self.assertFalse(avisos)
 def test_fonte_ausente_avisa(self):
  ts=deepcopy(self.d['tubulacoes']);QgsProject.instance().removeMapLayers([r.id() for r in self.f.redes])
  gs,avisos=localizar(preparar(self.d,ts,QgsProject.instance()),self.d['contexto']['parametros']['crs']);self.assertFalse(gs);self.assertTrue(avisos)
 def test_situacao_sem_observacao(self):
  self.estado('VERIFICADO');self.assertTrue(self.p.salvar_decisao());self.assertEqual(self.p.selecionado['revisao']['situacao'],'VERIFICADO');self.assertEqual(self.p.observacao.toPlainText(),'')
 def test_observacao_nao_sobrescreve_estado(self):
  self.estado('DESCARTADO');self.p.observacao.setPlainText('Interpretação do usuário');self.p.salvar_decisao();self.assertEqual(self.p.selecionado['revisao']['situacao'],'DESCARTADO')
 def test_reabrir_agrupamento(self):
  self.estado('VERIFICADO');self.p.salvar_decisao();self.estado('PENDENTE');self.p.salvar_decisao();self.assertEqual(len(historico(self.p.base,self.d['execucao_uid'],self.uid)),2)
 def test_revisao_individual_e_grupo_independentes(self):
  self.individual();self.assertEqual(self.p.indice.revisoes[self.e]['situacao'],'VERIFICADO');self.assertEqual(self.p.indice.locais[self.uid]['revisao']['situacao'],'PENDENTE')
 def test_estados_mistos(self):
  self.individual();self.assertEqual(self.p.indice.situacao(self.uid),'MISTO')
 def test_grupo_verificado_nao_oculta_individuais_pendentes(self):
  self.estado('VERIFICADO');self.p.salvar_decisao();self.individual('PENDENTE');self.assertNotEqual(self.p.indice.situacao(self.uid),'VERIFICADO')
 def test_historico_individual_concorrencia(self):
  self.individual(obs='Primeira');r=self.p.indice.revisoes[self.e]
  with self.assertRaises(ValueError):ro.salvar(self.p.base,self.d['execucao_uid'],self.e,'PENDENTE','',None)
  self.assertEqual(len(ro.historico(self.p.base,self.d['execucao_uid'],self.e)),1)
 def test_historico_imutavel(self):
  self.individual()
  with sqlite3.connect(self.p.base) as c:
   with self.assertRaises(sqlite3.IntegrityError):c.execute('DELETE FROM REVISOES_OCORRENCIAS')
 def test_backup_migracao_verificado(self):
  self.individual();bs=list(Path(self.p.base).parent.glob('*_antes_decisoes_ocorrencias_*.gpkg'));self.assertEqual(len(bs),1)
  with sqlite3.connect(bs[0]) as c:self.assertFalse(ro.existe(c));self.assertEqual(c.execute('PRAGMA quick_check').fetchone()[0],'ok')
 def test_migracao_uma_vez(self):
  self.individual();self.individual('PENDENTE');self.assertEqual(len(list(Path(self.p.base).parent.glob('*_antes_decisoes_ocorrencias_*.gpkg'))),1)
 def test_invalidos_nao_migram(self):
  with self.assertRaises(ValueError):ro.salvar(self.p.base,self.d['execucao_uid'],'inexistente','VERIFICADO')
  with sqlite3.connect(self.p.base) as c:self.assertFalse(ro.existe(c))
 def test_pesquisa_tubo_e_filtros(self):
  t=self.p.indice.detalhes(self.uid)['tubulacoes'][0];self.p.busca.setText(t['id_exibido']);self.p.filtrar();self.assertTrue(self.p._filtrados)
  self.p.filtro_situacao.setCurrentIndex(self.p.filtro_situacao.findData('VERIFICADO'));self.assertEqual(self.p.lista.rowCount(),0)
 def test_filtro_tipo(self):
  k=self.d['eventos'][0]['tecnico']['classificacao'];self.p.filtro_tipo.setCurrentIndex(self.p.filtro_tipo.findData(k));self.assertTrue(all(k in self.p.indice.classes[l['uid']] for l in self.p._filtrados))
 def test_local_preservado_apos_salvar(self):
  self.estado('EM_ANALISE');self.p.salvar_decisao();self.assertEqual(self.p.selecionado['uid'],self.uid)
 def test_cancelar_troca_alvo_preserva_texto(self):
  self.p.observacao.setPlainText('Rascunho')
  with patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel):self.p.alvo.setCurrentIndex(1)
  self.assertIsNone(self.p._evento_uid);self.assertEqual(self.p.observacao.toPlainText(),'Rascunho');self.p.observacao.clear()
 def test_recuperar_revisao_cria_novo_historico(self):
  self.estado('VERIFICADO');self.p.salvar_decisao();self.estado('PENDENTE');self.p.salvar_decisao();self.p.historico();self.p.historico_lista.setCurrentCell(0,0);self.p.recuperar_revisao();self.assertTrue(self.p.pendente());self.p.salvar_decisao();self.assertEqual(len(historico(self.p.base,self.d['execucao_uid'],self.uid)),3)
  self.assertEqual(self.p.historico_lista.rowCount(),3)
 def test_recuperar_revisao_salvando_rascunho(self):
  self.estado('VERIFICADO');self.p.salvar_decisao();self.p.historico();self.p.historico_lista.setCurrentCell(0,0);self.p.observacao.setPlainText('Rascunho a salvar')
  with patch.object(QMessageBox,'question',return_value=QMessageBox.Save):self.p.recuperar_revisao()
  self.assertEqual(len(historico(self.p.base,self.d['execucao_uid'],self.uid)),2);self.assertEqual(self.p.observacao.toPlainText(),'')
  with patch.object(QMessageBox,'question',return_value=QMessageBox.Discard):self.p.resolver()
 def test_salvar_ao_trocar_alvo_preserva_destino(self):
  self.p.observacao.setPlainText('Anotação do local');e=self.p.alvo.itemData(1)
  with patch.object(QMessageBox,'question',return_value=QMessageBox.Save):self.p.alvo.setCurrentIndex(1)
  self.assertEqual(self.p._evento_uid,e);self.assertEqual(self.p.indice.locais[self.uid]['revisao']['observacoes'],'Anotação do local')
 def test_crs_alterado_nao_reconstroi_tubo(self):
  from qgis.core import QgsCoordinateReferenceSystem
  t=deepcopy(self.d['tubulacoes'][0]);r=next(r for r in self.f.redes if r.name()==t['camada']);r.setCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
  gs,avisos=localizar(preparar(self.d,[t],QgsProject.instance()),self.d['contexto']['parametros']['crs']);self.assertFalse(gs);self.assertTrue(avisos)
 def test_todas_individuais_verificadas(self):
  for e in self.p.selecionado['eventos']:self.p.indice.revisoes[e]=ro.salvar(self.p.base,self.d['execucao_uid'],e,'VERIFICADO')
  self.assertEqual(self.p.indice.situacao(self.uid),'VERIFICADO');self.assertEqual(self.p.selecionado['revisao']['situacao'],'PENDENTE')
 def test_reabertura_individual(self):
  self.individual(obs='Registro individual');r=dict(base=self.p.base,uuid=self.d['execucao_uid'],nome='Reabertura');self.p.abrir_persistida(r);self.esperar();self.assertEqual(self.p.indice.revisoes[self.e]['observacoes'],'Registro individual')
 def test_exportacao_tabelas_e_gpkg(self):
  self.individual();dest=Path(self.p.base).parent/'tabelas';dest.mkdir();exportar_tabelas(self.d,dest,self.p.base)
  self.assertEqual(len(list(csv.DictReader((dest/'DECISOES_OCORRENCIAS.csv').open(encoding='utf-8-sig')))),1)
  copia=dest/'copia.gpkg';copiar_gpkg(self.p.base,copia,self.d['execucao_uid'],lambda:False);self.assertEqual(len(ro.historico(copia,self.d['execucao_uid'])),1)
 def test_abertura_legada_nao_migra_nem_modifica(self):
  base=Path(self.p.base);antes=sha256(base.read_bytes()).hexdigest();self.p.abrir_persistida(dict(base=str(base),uuid=self.d['execucao_uid'],nome='Antiga'));self.esperar();self.assertEqual(sha256(base.read_bytes()).hexdigest(),antes)
 def test_multiplas_tubulacoes_e_ids_repetidos_entre_fontes(self):
  r=self.f.redes[1];fid=next(r.getFeatures()).id();r.dataProvider().changeGeometryValues({fid:QgsGeometry.fromWkt('LINESTRING(-2 6,5 6)')});r.dataProvider().changeAttributeValues({fid:{r.fields().indexFromName('id'):202}})
  for k,b in self.p.areas.items():b.setChecked(k=='SETOR')
  self.p.iniciar();self.esperar();ls=[l for l in self.p.dossie['locais'] if len(self.p.indice.detalhes(l['uid'])['tubulacoes'])>=2];self.assertTrue(ls)
  ts=self.p.indice.detalhes(ls[0]['uid'])['tubulacoes'];self.assertEqual({t['id_bruto'] for t in ts},{202});self.assertGreater(len({t['origem'] for t in ts}),1)
 def test_quatro_eventos_duas_tubulacoes_no_indice(self):
  d=deepcopy(self.d);por_tubo={}
  for e in d['eventos']:por_tubo.setdefault(e['tecnico']['tubulacoes'][0]['chave'],[]).append(e['uid'])
  ids=[u for es in list(por_tubo.values())[:2] for u in es[:2]];self.assertEqual(len(ids),4)
  l=d['locais'][0];l['eventos']=ids;l['registro']['N_EVENTOS']=4;l['registro']['N_TUBOS']=2
  i=IndiceInvestigacao(d);self.assertEqual(len(i.detalhes(l['uid'])['eventos']),4);self.assertEqual(len(i.detalhes(l['uid'])['tubulacoes']),2)
 def test_navegacao_pesquisa_mais_de_200(self):
  d=deepcopy(self.d);modelo=d['locais'][0];d['locais']=[]
  for i in range(745):
   l=deepcopy(modelo);l['uid']='local'+str(i);l['registro']['LOCAL']='L'+str(i).zfill(4);d['locais'].append(l)
  self.p.receber(d,self.p.base);self.p.busca.setText('L0744');self.p.filtrar();self.assertEqual(self.p.lista.rowCount(),1);self.assertEqual(self.p.selecionado['registro']['LOCAL'],'L0744')

if __name__=='__main__':unittest.main()
