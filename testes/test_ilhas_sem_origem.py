"""Ilhas sintéticas: conectividade fraca não equivale a alcance dirigido."""
import copy,unittest,sqlite3
from unittest.mock import patch
from test_auditoria_fronteiras import APP
from test_corredores_recuperacao import pacote
from auditoria_topologica_watergems import ilhas as il,ilhas_investigacao as inv,ilhas_persistencia as store,restricoes_percurso as rp


def exemplo(edges=None):
    p=pacote(edges or [(101,1,2),(102,2,3),(103,4,5)]);p['topologia']['modelo'].update(projeto='sintetico-ilhas',cenario={'id':1});p['topologia']['modelo']['elementos'][1]['tipo']='IdahoReservoir';p.update(resultado=dict(meta=dict(uid='ig',topologia=dict(execucao_uid='topo',projeto='modelo',cenario='cenario'),parametros=dict(crs='EPSG:31983',espacial_habilitado=False)),locais=[],componentes=[],componentes_potenciais=[]),dossie=dict(tubulacoes=[],contexto=dict(parametros=dict(crs='EPSG:31983'))),areas=[],geometrias={});return p


class IlhasTest(unittest.TestCase):
    def setUp(self):self.p=exemplo()
    def calc(self,c=None):return il.analisar(self.p,c)
    def tubos(self,r,visao):return {i for v in r['ilhas'] if v['visao']==visao for i in v['tubos']}
    def test_totalmente_alcancavel(self):self.p=exemplo([(101,1,2),(102,2,3)]);self.assertEqual(self.calc()['ilhas'],[])
    def test_pequena_sem_origem(self):r=self.calc();self.assertEqual(self.tubos(r,'ESTRUTURAL'),{103});self.assertEqual(self.tubos(r,'RESTRITA'),set())
    def test_grande_cinco_mil_tubos(self):self.p=exemplo([(101,1,2)]+[(100000+i,1000+i,1001+i) for i in range(5000)]);r=self.calc();v=next(v for v in r['ilhas'] if v['tubos']);self.assertEqual(len(v['tubos']),5000);self.assertEqual(v['prioridade'],'Alta')
    def test_multiplas_origens(self):self.p['topologia']['modelo']['elementos'][4]['tipo']='IdahoReservoir';self.assertEqual(self.calc()['ilhas'],[])
    def test_reservoir_inativo(self):self.p['topologia']['modelo']['elementos'][1]['ativo']=False;r=self.calc();self.assertEqual(r['estado'],'SEM_ORIGENS');self.assertEqual(r['ilhas'],[])
    def test_tank_nao_e_origem_permanente(self):self.p['topologia']['modelo']['elementos'][1]['tipo']='ConventionalTank';self.assertEqual(self.calc()['estado'],'SEM_ORIGENS')
    def test_tank_exige_hipotese(self):
        with self.assertRaisesRegex(ValueError,'Tanks'):self.calc({'origens':'RESERVOIRS_TANKS'})
    def test_tank_incluido_explicitamente(self):self.p['topologia']['modelo']['elementos'][1]['tipo']='ConventionalTank';r=self.calc({'origens':'RESERVOIRS_TANKS','incluir_tanks':True});self.assertEqual(r['origens_info']['utilizadas'],1)
    def selecionada(self,i):e=self.p['topologia']['modelo']['elementos'][i];return dict(id=i,uid=e['uid'],tipo=e['tipo'],porta='E')
    def test_junction_personalizada(self):r=self.calc({'origens':'PERSONALIZADAS','selecionadas':[self.selecionada(4)]});self.assertEqual(self.tubos(r,'ESTRUTURAL'),{101,102})
    def test_origem_uid_incompativel(self):
        s=self.selecionada(4);s['uid']='outro'
        with self.assertRaises(ValueError):self.calc({'origens':'PERSONALIZADAS','selecionadas':[s]})
    def test_nenhuma_origem_selecionada(self):self.assertEqual(self.calc({'origens':'SELECIONADAS'})['estado'],'SEM_ORIGENS')
    def dispositivo(self,tipo='PRV'):
        e=self.p['topologia']['modelo']['elementos'][2];e.update(tipo=tipo,familia='DISPOSITIVO',topologia={'HMITopologyDownstreamLinkID':102})
    def test_prv_bloqueada(self):self.dispositivo();r=self.calc({'restricoes':{'regras':{'PRV':'BLOQUEAR'}}});self.assertEqual(self.tubos(r,'RESTRITA'),{102});self.assertIn(101,r['fronteiras']);self.assertEqual(self.tubos(r,'ESTRUTURAL'),{103})
    def test_booster_bloqueado(self):self.dispositivo('StandardPump');self.assertIn(102,self.tubos(self.calc({'restricoes':{'regras':{'StandardPump':'BLOQUEAR'}}}),'RESTRITA'))
    def test_excecao_permitida(self):self.dispositivo();r=self.calc({'restricoes':{'regras':{'PRV':'BLOQUEAR'},'excecoes':[dict(rp.referencia(self.p,2),acao='PERMITIR')]}});self.assertEqual(self.tubos(r,'RESTRITA'),set())
    def test_retencao_direcional(self):self.dispositivo('CheckValve');r=self.calc({'origens':'PERSONALIZADAS','selecionadas':[self.selecionada(3)]});self.assertIn(101,self.tubos(r,'RESTRITA'));self.assertNotIn(101,self.tubos(r,'ESTRUTURAL'))
    def test_grafo_dirigido_nao_e_fraco(self):self.p['topologia']['potencial']['grafo'].remove_edge((2,'E'),(3,'E'),('tubo',102));r=self.calc();self.assertTrue(any(3 in v['membros'] for v in r['ilhas'] if v['visao']=='RESTRITA'))
    def test_dispositivo_sem_direcao_nao_inventa_passagem(self):self.dispositivo('CheckValve');self.p['topologia']['modelo']['elementos'][2]['topologia']={};r=self.calc();self.assertTrue(self.tubos(r,'RESTRITA'))
    def test_elemento_inativo_fora_da_perspectiva(self):g=self.p['topologia']['potencial']['grafo'];g.remove_edge((2,'E'),(3,'E'),('tubo',102));g.remove_edge((3,'E'),(2,'E'),('tubo',102));r=self.calc();self.assertIn(102,r['fora_perspectiva'])
    def test_sem_geometria_nao_inventa_comprimento(self):v=self.calc()['ilhas'][0];self.assertIsNone(v['comprimento_m']);self.assertIsNone(v['extensao']);self.assertIsNone(v['demanda'])
    def test_referencia_incompleta_nao_e_ilha_inventada(self):self.p['topologia']['modelo']['elementos'][999]=dict(uid='u999',familia='LINK',tipo='IdahoPipe',excluido=False);self.assertIn(999,self.calc()['sem_topologia'])
    def test_sem_duplicacao_de_tubos(self):self.dispositivo();r=self.calc({'restricoes':{'regras':{'PRV':'BLOQUEAR'}}});a=[i for v in r['ilhas'] for i in v['tubos']];self.assertEqual(len(a),len(set(a)))
    def test_contexto_e_grafo_preservados(self):a=copy.deepcopy(self.p);self.calc();self.assertEqual(list(a['topologia']['estrutural']['grafo'].edges(keys=True,data=True)),list(self.p['topologia']['estrutural']['grafo'].edges(keys=True,data=True)));self.assertEqual(a['topologia']['modelo'],self.p['topologia']['modelo'])
    def test_cancelamento(self):
        with self.assertRaises(InterruptedError):il.analisar(self.p,cancelado=lambda:True)
    def test_uid_estavel(self):self.assertEqual([v['uid'] for v in self.calc()['ilhas']],[v['uid'] for v in self.calc()['ilhas']])
    def test_mudanca_origens_muda_assinatura(self):self.assertNotEqual(self.calc()['assinatura'],self.calc({'origens':'PERSONALIZADAS','selecionadas':[self.selecionada(3)]})['assinatura'])
    def test_prioridade_configuravel(self):r=self.calc({'prioridade':{'percentual_alta':100,'tubos_alta':1000}});self.assertEqual(r['ilhas'][0]['prioridade'],'Média')
    def test_bloqueio_na_origem_exige_escolha(self):
        self.dispositivo()
        with self.assertRaisesRegex(ValueError,'Origem bloqueada'):self.calc({'origens':'PERSONALIZADAS','selecionadas':[self.selecionada(2)],'restricoes':{'regras':{'PRV':'BLOQUEAR'}}})
    def test_busca_linear_dirigida(self):g=self.p['topologia']['estrutural']['grafo'];self.assertNotIn((4,'E'),il.buscar(g,[(1,'E')],True))
    def test_comparacao_nao_declara_correcao(self):r0=self.calc();self.p['topologia']['modelo']['elementos'][4]['tipo']='IdahoReservoir';r1=self.calc();r=inv.comparar(self.p,r0,self.p,r1);self.assertTrue(any(v['classe']=='NAO_OBSERVADA_NA_NOVA_EXECUCAO' for v in r['linhas']));self.assertTrue(r['sem_transferencia_automatica_de_revisoes'])
    def test_candidato_geometrico_nao_cria_conexao(self):
        from qgis.core import QgsGeometry
        self.p['resultado']['meta']['parametros']['espacial_habilitado']=True;self.p['geometrias']={101:QgsGeometry.fromWkt('LINESTRING(100 100,110 100)'),102:QgsGeometry.fromWkt('LINESTRING(110 100,120 100)'),103:QgsGeometry.fromWkt('LINESTRING(120.5 100,130 100)')};r=self.calc();v=next(v for v in r['ilhas'] if 103 in v['tubos']);c=inv.Candidatos(self.p,r).procurar(v,2);self.assertTrue(c['candidatos']);self.assertIn(103,self.tubos(self.calc(),'ESTRUTURAL'))
    def test_sem_crs_preserva_candidato_topologico(self):
        self.dispositivo();r=self.calc({'restricoes':{'regras':{'PRV':'BLOQUEAR'}}});v=next(v for v in r['ilhas'] if v['visao']=='RESTRITA');c=inv.Candidatos(self.p,r).procurar(v);self.assertFalse(c['espacial_disponivel']);self.assertTrue(any(ca['tipo']=='BLOQUEIO_RESTRICAO' for ca in c['candidatos']))
    def test_dispositivo_parcial_nao_e_contado_como_totalmente_inacessivel(self):
        self.dispositivo('CheckValve');r=self.calc({'origens':'PERSONALIZADAS','selecionadas':[self.selecionada(3)]});self.assertIn(2,r['dispositivos_parcialmente_alcancados']);self.assertFalse(any(2 in v['membros'] for v in r['ilhas'] if v['visao']=='RESTRITA'))
    def test_redes_e_orfaos_contados_separadamente(self):
        r=self.calc();self.assertEqual(r['contagens']['redes_estruturais'],1);self.assertEqual(r['contagens']['grupos_estruturais_sem_tubos'],0)
    def test_exportar_alcancaveis_nao_inclui_porta_proibida(self):
        self.dispositivo('CheckValve');r=self.calc({'origens':'PERSONALIZADAS','selecionadas':[self.selecionada(3)]});registro=inv.registro_alcancaveis(self.p,r);self.assertNotIn('101',{v['chave'] for v in registro['vinculos']})
    def test_comparacao_sem_origens_inconclusiva(self):r=self.calc();r1=self.calc({'origens':'SELECIONADAS'});self.assertEqual(inv.comparar(self.p,r,self.p,r1)['estado'],'INCONCLUSIVO')
    def test_comparacao_mudanca_topologica_mesmos_membros_requer_reavaliacao(self):
        antes=copy.deepcopy(self.p);r0=il.analisar(antes);self.p['topologia']['modelo']['elementos'][4]['ativo']=False;r1=self.calc();c=inv.comparar(antes,r0,self.p,r1);self.assertTrue(any(l['classe']=='REQUER_REAVALIACAO' for l in c['linhas']))
    def test_comparacao_alternativas_distintas_incerta(self):
        antes=copy.deepcopy(self.p);r0=il.analisar(antes);self.p['topologia']['modelo']['alternativas']={'topologia':2};r1=self.calc();self.assertEqual(inv.comparar(antes,r0,self.p,r1)['estado'],'CONTEXTO_DIFERENTE')
    def test_comparacao_ganho_caminho_conserva_identidade(self):
        antes=copy.deepcopy(self.p);cfg={'comparar_restricoes':False};r0=il.analisar(antes,cfg);self.p['topologia']['estrutural']['grafo'].add_edge((3,'E'),(4,'E'),elemento=103,natureza='TUBULACAO');r1=self.calc(cfg);c=inv.comparar(antes,r0,self.p,r1);self.assertTrue(c['passaram_a_ter_caminho']);self.assertTrue(c['sem_transferencia_automatica_de_revisoes'])
    def test_candidatos_consideram_extremidades_de_todas_as_partes(self):
        from qgis.core import QgsGeometry
        self.p['resultado']['meta']['parametros']['espacial_habilitado']=True;self.p['geometrias']={101:QgsGeometry.fromWkt('LINESTRING(100 100,110 100)'),102:QgsGeometry.fromWkt('LINESTRING(110 100,120 100)'),103:QgsGeometry.fromWkt('MULTILINESTRING((200 100,120.5 100),(300 100,310 100))')};r=self.calc();v=next(v for v in r['ilhas'] if 103 in v['tubos']);c=inv.Candidatos(self.p,r).procurar(v,2);self.assertTrue(any(x['tipo']=='PROXIMIDADE_GEOMETRICA' for x in c['candidatos']))


import test_decisoes_topologicas as fixture
class PersistenciaIlhasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.DecisoesTest.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):fixture.DecisoesTest.tearDownClass.__func__(cls)
    def setUp(self):fixture.DecisoesTest.setUp(self)
    def tearDown(self):fixture.DecisoesTest.tearDown(self)
    def resultado(self):
        el=self.p['topologia']['modelo']['elementos'];g=self.p['topologia']['estrutural']['grafo'];i=next(n[0] for n in g if el[n[0]]['familia']=='NO');return il.analisar(self.p,dict(origens='PERSONALIZADAS',selecionadas=[dict(id=i,porta='E',uid=el[i]['uid'],tipo=el[i]['tipo'])],incluir_tanks=True))
    def test_base_legada_sem_migracao_na_leitura(self):a=self.base.read_bytes();self.assertEqual(store.listar(self.base,self.p),[]);self.assertEqual(a,self.base.read_bytes())
    def test_persistir_reabrir_sem_perder_membros(self):r=self.resultado();s=store.salvar(self.base,self.p,r);self.assertEqual(len(s['ilhas']),len(r['ilhas']));self.assertEqual({i for v in s['ilhas'] for i in v['membros']},{i for v in r['ilhas'] for i in v['membros']})
    def test_cache_nao_duplica(self):r=self.resultado();a=store.salvar(self.base,self.p,r);b=store.salvar(self.base,self.p,r);self.assertEqual(a['uid'],b['uid']);self.assertEqual(len(store.listar(self.base,self.p)),1)
    def test_relacoes_integras(self):
        store.salvar(self.base,self.p,self.resultado())
        with sqlite3.connect(self.base) as c:self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())
    def test_backup_completo(self):store.salvar(self.base,self.p,self.resultado());self.assertTrue(list(self.dir.glob('*antes_ilhas*.gpkg')))
    def test_cancelamento_rollback(self):
        r=self.resultado();r['ilhas']=r['ilhas'] or [dict(uid='sintetica',membros=[],gis=[],areas=[],locais=[])]
        with self.assertRaises(InterruptedError):store.salvar(self.base,self.p,r,cancelado=lambda:True)
        self.assertEqual(store.listar(self.base,self.p),[])
    def ilha_fixture(self):
        el=self.p['topologia']['modelo']['elementos'];g=self.p['topologia']['estrutural']['grafo'];i=next(n[0] for n in g if el[n[0]]['familia']=='NO');r=il.analisar(self.p,dict(origens='PERSONALIZADAS',selecionadas=[dict(id=i,uid=el[i]['uid'],tipo=el[i]['tipo'],porta='E')],incluir_tanks=True,restricoes={'regras':{'CheckValve':'BLOQUEAR'}}));return r
    def test_revisao_resolucao_no_mesmo_contexto(self):
        from auditoria_topologica_watergems import operacional as op,acompanhamento as ac
        r=self.ilha_fixture();self.assertTrue(r['ilhas']);r=store.salvar(self.base,self.p,r);c=il.casos(self.p,r)[0];modo=c['modo_exclusivo'];op.salvar(self.base,self.p,c,modo,resultado='MANTER CONFIGURAÇÃO ATUAL');ac.salvar(self.base,self.p,c,modo,'RESOLVIDO');self.assertEqual(op.historico(self.base,self.ig)[0]['resultado'],'MANTER CONFIGURAÇÃO ATUAL');self.assertEqual(ac.indice(self.base,self.p)[c['uid'],modo]['estado'],'RESOLVIDO')
    def test_exporta_so_membros_da_ilha(self):
        from auditoria_topologica_watergems import exportacao_watergems as ex
        r=self.ilha_fixture();self.assertTrue(r['ilhas']);v=r['ilhas'][0];d=ex.exportar(self.dir/'ilha_exportada',self.p,inv.registro_exportacao(self.p,r,v));self.assertEqual({e['DomainElementID'] for e in d['elementos']},set(v['membros']));self.assertTrue((self.dir/'ilha_exportada/INDICE_QUERIES.csv').exists())
    def test_relatorio_distingue_ilhas(self):
        from auditoria_topologica_watergems import relatorio_investigacao as rel
        r=self.ilha_fixture();store.salvar(self.base,self.p,r);cs=il.casos(self.p,r);self.assertTrue(cs);modo=cs[0]['modo_exclusivo'];d=rel.snapshot(self.base,self.p,cs,modo,{});self.assertTrue(d['ocorrencias'][0]['ilha']);self.assertTrue(all(c['ilha']['visao']==cs[0]['ilha']['visao'] for c in d['ocorrencias']))
    def test_painel_recupera_categoria_salva(self):
        store.salvar(self.base,self.p,self.ilha_fixture());j=fixture.DecisoesTest.painel(self);self.assertTrue(any(c['tipo']=='ILHA' for c in j.casos));self.assertGreaterEqual(j.categoria.findData('SEM_CAMINHO_ATE_ORIGEM'),0)
    def test_selecao_no_painel_com_detalhes_expansiveis(self):
        store.salvar(self.base,self.p,self.ilha_fixture());j=fixture.DecisoesTest.painel(self);c=next(c for c in j.casos if c['tipo']=='ILHA');j.modo.setCurrentIndex(j.modo.findData(c['modo_exclusivo']));j.categoria.setCurrentIndex(j.categoria.findData('SEM_CAMINHO_ATE_ORIGEM'));j.fila.setCurrentIndex(j.fila.findData('TODOS'));j.selecionar_uid(c['uid']);self.assertEqual(j.atual['uid'],c['uid'])
    def test_historico_imutavel(self):
        store.salvar(self.base,self.p,self.ilha_fixture())
        with sqlite3.connect(self.base) as c:
            with self.assertRaises(sqlite3.IntegrityError):c.execute('DELETE FROM IGD_ILHAS_ANALISES')
    def test_cancelar_contexto_preserva_analise(self):
        from qgis.PyQt.QtWidgets import QMessageBox
        j=fixture.DecisoesTest.painel(self);j.abrir_ilhas();d=j._ilhas_ui;d.resultado=self.ilha_fixture();d.gerado_config=d.cfg()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel):self.assertFalse(d.resolver())
        self.assertTrue(d.resultado);d.resultado=None;d.close()
    def test_comparacao_persistida_no_historico_existente(self):
        from auditoria_topologica_watergems.comparacao_decisoes import salvar_comparacao
        r=store.salvar(self.base,self.p,self.ilha_fixture());cmp=inv.comparar(self.p,r,self.p,r);u=salvar_comparacao(self.base,self.p,cmp)
        with sqlite3.connect(self.base) as c:self.assertEqual(c.execute('SELECT count(*) FROM IGD_COMPARACOES WHERE comp_uid=?',(u,)).fetchone()[0],1);self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())
    def test_ui_abre_sem_calcular(self):j=fixture.DecisoesTest.painel(self);j.abrir_ilhas();d=j._ilhas_ui;self.assertIsNone(d.resultado);d.close()


if __name__=='__main__':unittest.main()
