"""Dispositivos e caminhos sintéticos: restrição nunca modifica a fonte."""
import copy,json,sqlite3,unittest
from unittest.mock import patch
from test_corredores_recuperacao import pacote
from auditoria_topologica_watergems.corredores import calcular
from auditoria_topologica_watergems import restricoes_percurso as rp,conjuntos_investigacao as st,exportacao_watergems as ex


def exemplo(malha=True,tipo='PRV'):
    p=pacote([(101,1,2),(102,2,3)]+([(103,1,4),(104,4,5),(105,5,3)] if malha else []));p['topologia']['modelo'].update(projeto='modelo-sintetico',cenario={'id':1})
    e=p['topologia']['modelo']['elementos'][2];e.update(tipo=tipo,familia='DISPOSITIVO',topologia={'HMITopologyDownstreamLinkID':102})
    return p


class RestricoesTest(unittest.TestCase):
    def setUp(self):self.p=exemplo()
    def calc(self,c=None,**kw):
        args=dict(modo='ESTRUTURAL',origens=[1],destinos=[3],criterio='COMPRIMENTO',comprimentos={101:10,102:10,103:100,104:100,105:100},restricoes=c or {});args.update(kw);return calcular(self.p,**args)
    def ids(self,r):return {int(v['chave']) for v in r['elementos']}
    def ref(self,**kw):return dict(rp.referencia(self.p,2),**kw)
    def test_permitir_todos(self):self.assertEqual(self.ids(self.calc()),{101,102})
    def test_evitar_prv_lexicografico(self):r=self.calc({'regras':{'PRV':'EVITAR'}});self.assertEqual(self.ids(r),{103,104,105});self.assertEqual(r['rotas'][0]['custo_lexicografico'],[0,300])
    def test_evitar_por_arestas(self):self.assertEqual(self.ids(self.calc({'regras':{'PRV':'EVITAR'}},criterio='ARESTAS')),{103,104,105})
    def test_evitar_sem_alternativa(self):self.p=exemplo(False);r=self.calc({'regras':{'PRV':'EVITAR'}});self.assertEqual(r['rotas'][0]['custo_lexicografico'],[1,20]);self.assertEqual(r['comparacao_restricoes']['evitados_utilizados'],[2])
    def test_custo_informativo_sem_penalidade(self):self.assertEqual(self.ids(self.calc({'regras':{'PRV':'EVITAR'},'otimizacao':'CUSTO'})),{101,102})
    def test_bloquear_prv(self):self.assertEqual(self.ids(self.calc({'regras':{'PRV':'BLOQUEAR'}})),{103,104,105})
    def test_bloquear_boosters(self):self.p=exemplo(tipo='StandardPump');self.assertEqual(self.ids(self.calc({'regras':{'StandardPump':'BLOQUEAR'}})),{103,104,105})
    def test_excecao_permitir(self):self.assertEqual(self.ids(self.calc({'regras':{'PRV':'BLOQUEAR'},'excecoes':[self.ref(acao='PERMITIR')]})),{101,102})
    def test_excecao_bloquear(self):self.assertEqual(self.ids(self.calc({'excecoes':[self.ref(acao='BLOQUEAR')]})),{103,104,105})
    def test_ausente(self):
        with self.assertRaisesRegex(ValueError,'ausente'):self.calc({'excecoes':[dict(id=999)]})
    def test_tipo_incompativel(self):
        r=self.ref(acao='PERMITIR');r['tipo']='TCV'
        with self.assertRaisesRegex(ValueError,'incompatível'):self.calc({'excecoes':[r]})
    def test_uid_incompativel(self):
        r=self.ref(acao='PERMITIR');r['uid']='outro'
        with self.assertRaises(ValueError):self.calc({'excecoes':[r]})
    def test_regra_repetida(self):
        r=self.ref(acao='EVITAR')
        with self.assertRaisesRegex(ValueError,'duplicada'):self.calc({'excecoes':[r,r]})
    def test_outro_modelo(self):
        with self.assertRaisesRegex(ValueError,'outro modelo'):self.calc({'contexto':{'modelo':'outro'},'excecoes':[self.ref(acao='PERMITIR')]})
    def test_estado_desconhecido_nao_fecha(self):self.assertEqual(self.ids(self.calc({'bloquear_indisponiveis':True,'estados':[self.ref(estado='DESCONHECIDO',origem='MANUAL')]})),{101,102})
    def test_estado_manual_hipotese(self):r=self.calc({'bloquear_indisponiveis':True,'estados':[self.ref(estado='FECHADO',origem='MANUAL')]});self.assertEqual(self.ids(r),{103,104,105});self.assertEqual(r['restricoes']['estados'][0]['natureza'],'HIPOTESE_DE_INVESTIGACAO')
    def test_estado_bruto_nao_validado(self):
        with self.assertRaisesRegex(ValueError,'códigos brutos'):self.calc({'estados':[self.ref(estado='FECHADO',origem='Initial Settings')]})
    def test_estado_validado_contrato_explicito(self):self.p['topologia']['modelo']['estados_validados']=[dict(self.ref(),estado='INDISPONIVEL',validado=True,fonte='ensaio sintético',contexto=rp.contexto(self.p))];self.assertEqual(self.ids(self.calc({'bloquear_indisponiveis':True})),{103,104,105})
    def test_excecao_nao_supera_indisponibilidade(self):self.assertEqual(self.ids(self.calc({'bloquear_indisponiveis':True,'estados':[self.ref(estado='FECHADO',origem='MANUAL')],'excecoes':[self.ref(acao='PERMITIR')]})),{103,104,105})
    def test_origem_bloqueada_exige_escolha(self):
        with self.assertRaisesRegex(ValueError,'Origem 2 está bloqueado'):self.calc({'regras':{'PRV':'BLOQUEAR'}},origens=[2])
    def test_destino_bloqueado_exige_escolha(self):
        with self.assertRaisesRegex(ValueError,'Destino 2 está bloqueado'):self.calc({'regras':{'PRV':'BLOQUEAR'}},destinos=[2])
    def test_inalcancavel_barreiras_nao_causa_unica(self):self.p=exemplo(False);r=self.calc({'regras':{'PRV':'BLOQUEAR'}});self.assertEqual(r['destinos_inalcancaveis'][0]['barreiras'],[2]);self.assertTrue(r['destinos_inalcancaveis'][0]['barreiras_nao_exaustivas'])
    def test_componentes_desconectados(self):self.p['topologia']['estrutural']['grafo'].remove_node((3,'E'));r=self.calc();self.assertFalse(r['destinos_inalcancaveis'][0]['conexao_estrutural'])
    def test_comparacao_adicionados_removidos(self):c=self.calc({'regras':{'PRV':'EVITAR'}})['comparacao_restricoes'];self.assertEqual(c['adicionados'],[103,104,105]);self.assertEqual(c['removidos'],[101,102]);self.assertEqual(c['equipamentos_evitados'],[2])
    def test_multiplas_origens_destinos(self):r=self.calc({'regras':{'PRV':'BLOQUEAR'}},origens=[1,4],destinos=[3,5]);self.assertEqual(len(r['destinos_alcancados']),2)
    def test_retencao_direcao_obrigatoria(self):self.p=exemplo(False,'CheckValve');self.assertTrue(self.calc()['rotas']);self.assertFalse(self.calc(origens=[3],destinos=[1])['rotas'])
    def test_permitir_nao_reverte_retencao(self):self.p=exemplo(False,'CheckValve');self.assertFalse(self.calc({'excecoes':[self.ref(acao='PERMITIR')]},origens=[3],destinos=[1])['rotas'])
    def test_retencao_evitar_conta_uma_passagem(self):self.p=exemplo(False,'CheckValve');self.assertEqual(self.calc({'regras':{'CheckValve':'EVITAR'}})['rotas'][0]['custo_lexicografico'][0],1)
    def test_retencao_sem_jusante_nao_inventa_ligacao(self):self.p=exemplo(False,'CheckValve');self.p['topologia']['modelo']['elementos'][2]['topologia']={};r=self.calc();self.assertFalse(r['rotas']);self.assertEqual(r['comparacao_restricoes']['direcao_indeterminada'],[2])
    def test_perspectiva_nao_cria_arestas_bomba(self):self.p['topologia']['potencial']['grafo'].remove_node((2,'E'));self.assertNotIn(101,self.ids(self.calc(modo='TODAS_VALVULAS_ABERTAS')))
    def test_cenario_continua_bloqueado(self):
        with self.assertRaises(ValueError):self.calc(modo='ESTADOS_DO_CENARIO')
    def test_alternativas_respeitam_bloqueios(self):r=self.calc({'regras':{'PRV':'BLOQUEAR'}},alternativas=2);self.assertTrue(all(2 not in t['dispositivos'] for t in r['rotas']+r['rotas_alternativas']))
    def test_grafo_e_elementos_preservados(self):a=copy.deepcopy(self.p);self.calc({'regras':{'PRV':'BLOQUEAR'}});self.assertEqual(list(a['topologia']['estrutural']['grafo'].edges(keys=True,data=True)),list(self.p['topologia']['estrutural']['grafo'].edges(keys=True,data=True)));self.assertEqual(a['topologia']['modelo'],self.p['topologia']['modelo'])
    def test_cancelamento(self):
        with self.assertRaises(InterruptedError):self.calc(cancelado=lambda:True)
    def test_comprimento_invalido_nao_vira_zero(self):
        with self.assertRaises(ValueError):self.calc(comprimentos={})
    def test_categorias_so_dispositivos_existentes(self):self.assertEqual(rp.categorias(self.p),['PRV'])
    def test_perfil_booleano_textual_nao_ativa_bloqueio(self):
        with self.assertRaisesRegex(ValueError,'booleano'):self.calc({'bloquear_indisponiveis':'false'})
    def test_falso_id_nao_vira_numero(self):
        with self.assertRaises(ValueError):rp.referencia(self.p,True)
    def test_exportacao_retencao_pipes_nos_dispositivo(self):
        self.p=exemplo(False,'CheckValve');self.p['resultado']=dict(meta=dict(topologia=dict(execucao_uid='v1',projeto='sintetico',cenario='c1')));r=self.calc();reg=dict(modo='ESTRUTURAL',topo_uid='v1',obj_uid='conjunto',dados=dict(criterios=r),vinculos=r['elementos']);d=ex.preparar(self.p,reg);self.assertEqual({e['DomainElementID'] for e in d['elementos']},{1,2,3,101,102});self.assertTrue(any(e['Tipo']=='CheckValve' for e in d['percursos']))
    def test_exportacao_omite_prv_e_tubos_bloqueados(self):
        self.p['resultado']=dict(meta=dict(topologia=dict(execucao_uid='v1',projeto='sintetico',cenario='c1')));r=self.calc({'regras':{'PRV':'BLOQUEAR'}});reg=dict(modo='ESTRUTURAL',topo_uid='v1',obj_uid='conjunto',dados=dict(criterios=r),vinculos=r['elementos']);d=ex.preparar(self.p,reg);self.assertFalse({2,101,102}&{e['DomainElementID'] for e in d['elementos']})
    def test_selecao_manual_nao_burla_bloqueio(self):
        with self.assertRaisesRegex(ValueError,'indisponíveis'):rp.validar_selecao(self.p,'ESTRUTURAL',{'regras':{'PRV':'BLOQUEAR'}},[dict(origem='WG',chave='101')])
    def test_perfil_serializavel(self):self.assertEqual(json.loads(json.dumps(self.calc()['restricoes']))['versao_regras'],'restricoes-1')


import test_decisoes_topologicas as fixture
class PersistenciaRestricoesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.DecisoesTest.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):fixture.DecisoesTest.tearDownClass.__func__(cls)
    def setUp(self):fixture.DecisoesTest.setUp(self)
    def tearDown(self):fixture.DecisoesTest.tearDown(self)
    def test_salvar_reabrir_perfil(self):uid,h=rp.salvar_perfil(self.base,self.p,'Evitar controles',{'regras':{'PRV':'EVITAR'}});rs=st.atuais(self.base,self.p,'PERFIL_RESTRICOES');self.assertEqual(rs[0]['obj_uid'],uid);self.assertEqual(rs[0]['dados']['restricoes']['regras']['PRV'],'EVITAR')
    def test_renomear_historico(self):
        rp.salvar_perfil(self.base,self.p,'Perfil A',{});r=st.atuais(self.base,self.p,'PERFIL_RESTRICOES')[0];rp.salvar_perfil(self.base,self.p,'Perfil B',{},r);self.assertEqual(len(st.historico(self.base,self.p,'PERFIL_RESTRICOES')),2)
        from qgis.PyQt.QtWidgets import QInputDialog
        j=fixture.DecisoesTest.painel(self);j.abrir_redes();d=j._redes_ui;w=d.restricoes;indice=next(i for i in range(w.perfis.count()) if isinstance(w.perfis.itemData(i),dict) and w.perfis.itemData(i)['obj_uid']==r['obj_uid']);w.perfis.setCurrentIndex(indice);self.assertEqual(w.registro['obj_uid'],r['obj_uid'])
        with patch.object(QInputDialog,'getText',return_value=('Perfil C',True)):w.salvar()
        self.assertEqual(st.atuais(self.base,self.p,'PERFIL_RESTRICOES')[0]['obj_uid'],r['obj_uid']);self.assertIn('Perfil C',w.perfis.currentText());self.assertEqual(len(st.historico(self.base,self.p,'PERFIL_RESTRICOES')),3);d.close()
    def test_excluir_logicamente(self):rp.salvar_perfil(self.base,self.p,'Perfil',{});r=st.atuais(self.base,self.p,'PERFIL_RESTRICOES')[0];rp.salvar_perfil(self.base,self.p,'Perfil',{},r,True);self.assertEqual(st.atuais(self.base,self.p,'PERFIL_RESTRICOES'),[]);self.assertEqual(len(st.historico(self.base,self.p,'PERFIL_RESTRICOES')),2)
    def test_concorrencia_perfil(self):
        rp.salvar_perfil(self.base,self.p,'Perfil',{});r=st.atuais(self.base,self.p,'PERFIL_RESTRICOES')[0];rp.salvar_perfil(self.base,self.p,'Outro',{},r)
        with self.assertRaisesRegex(ValueError,'outra sessão'):rp.salvar_perfil(self.base,self.p,'Não sobrescrever',{},r)
    def test_interface_restricoes_recolhida(self):
        j=fixture.DecisoesTest.painel(self);j.abrir_redes();d=j._redes_ui;self.assertFalse(d.restricoes.isChecked());self.assertEqual(set(d.restricoes.regras),set(rp.categorias(self.p)));d.close()
    def test_interface_categorias_visiveis_ao_expandir(self):
        from qgis.PyQt.QtWidgets import QApplication
        j=fixture.DecisoesTest.painel(self);j.abrir_redes();d=j._redes_ui;d.restricoes.setChecked(True);QApplication.processEvents();self.assertTrue(d.restricoes.perfis.isVisible());self.assertTrue(all(w.isVisible() for w in d.restricoes.regras.values()));d.close()
    def test_reabertura_identifica_perfil_ativo(self):
        uid,h=rp.salvar_perfil(self.base,self.p,'Perfil nomeado',{});j=fixture.DecisoesTest.painel(self);j.abrir_redes();d=j._redes_ui;d.restricoes.carregar(dict(perfil=dict(uid=uid,revisao=h),regras={}));self.assertEqual(d.restricoes.perfis.currentData()['obj_uid'],uid);self.assertIn('Perfil nomeado',d.restricoes.perfis.currentText());d.close()
    def test_interface_perfil_presets(self):
        j=fixture.DecisoesTest.painel(self);j.abrir_redes();d=j._redes_ui;w=d.restricoes;w.perfis.setCurrentIndex(1);self.assertEqual(w.perfis.currentText(),'Evitar PRVs');self.assertTrue(all(a=='EVITAR' for t,a in w.config()['regras'].items() if t=='PRV'));d.close()
    def test_interface_busca_labels_duplicados_nao_escolhe(self):
        j=fixture.DecisoesTest.painel(self);j.abrir_redes();d=j._redes_ui;w=d.restricoes;rows=[dict(id=i,uid='s-'+str(i),label='igual',tipo='PRV',porta='*') for i in (80,81)]
        with patch.object(w.seletor,'catalogo',return_value=(rows,{80:[rows[0]],81:[rows[1]]})):
            w.seletor.busca.setText('igual');w.seletor.procurar();self.assertEqual(w.seletor.tabela.rowCount(),2);self.assertEqual(w.config()['excecoes'],[])
        d.close()
    def test_interface_excecao_e_estado_sem_documento(self):
        j=fixture.DecisoesTest.painel(self);j.abrir_redes();d=j._redes_ui;w=d.restricoes;rows=w.seletor.catalogo()[0];self.assertTrue(rows);w.seletor.adicionar([rows[0]]);w.acao.setCurrentText('BLOQUEAR');w.estado.setCurrentIndex(w.estado.findData('FECHADO'));w.aplicar();self.assertEqual(w.config()['excecoes'][0]['acao'],'BLOQUEAR');self.assertEqual(w.config()['estados'][0]['origem'],'MANUAL');d.close()
    def test_conjunto_reaberto_e_exportado(self):
        from auditoria_topologica_watergems.saidas_integracao import reabrir
        g=self.p['topologia']['estrutural']['grafo'];a,b,d=next((a,b,d) for a,b,d in g.edges(data=True) if d['natureza']=='TUBULACAO');r=calcular(self.p,'ESTRUTURAL',[dict(id=a[0],porta=a[1])],[dict(id=b[0],porta=b[1])],restricoes={});uid,h=st.salvar(self.base,self.p,'REDE_PRINCIPAL',dict(nome='Corredor restrito',criterios=r),r['elementos']);p=reabrir(self.base);reg=next(c for c in st.atuais(self.base,p,'REDE_PRINCIPAL') if c['obj_uid']==uid);out=self.dir/'exportacao';dados=ex.exportar(out,p,reg);self.assertTrue((out/'RESTRICOES_PERCURSO.json').exists());self.assertTrue(dados['percursos']);self.assertEqual(dados['restricoes']['versao_regras'],'restricoes-1')
    def test_cancelar_fechamento_preserva_regras(self):
        from qgis.PyQt.QtWidgets import QMessageBox
        j=fixture.DecisoesTest.painel(self);j.abrir_redes();d=j._redes_ui;d.registro=dict(dados={});d.baseline=d.assinatura();tipo=next(iter(d.restricoes.regras));d.restricoes.regras[tipo].setCurrentText('EVITAR')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel):self.assertFalse(d.resolver())
        self.assertEqual(d.restricoes.regras[tipo].currentText(),'EVITAR');d.baseline=d.assinatura();d.close()
    def test_relacoes_integras(self):
        rp.salvar_perfil(self.base,self.p,'Perfil',{})
        with sqlite3.connect(self.base) as c:self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())


if __name__=='__main__':unittest.main()
