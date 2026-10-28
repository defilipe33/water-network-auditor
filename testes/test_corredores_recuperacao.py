"""Rotas escolhidas e recuperação por identidade, com exemplos inteiramente sintéticos."""
import copy
import unittest
import networkx as nx
from unittest.mock import patch
from test_auditoria_fronteiras import APP
from auditoria_topologica_watergems.corredores import calcular,resolver_terminal,buscar_terminais,resumir_selecao


def pacote(arestas,direcionado=False):
    g=nx.MultiDiGraph();el={}
    for i,a,b in arestas:
        for n in (a,b):
            el.setdefault(n,dict(id=n,uid='no-'+str(n),label='J-'+str(n),tipo='IdahoJunction',familia='NO',excluido=False,ativo=True));g.add_node((n,'E'),elemento=n)
        el[i]=dict(id=i,uid='tubo-'+str(i),label='P-'+str(i),tipo='IdahoPipe',familia='LINK',excluido=False,ativo=True,atributos={})
        g.add_edge((a,'E'),(b,'E'),key=('tubo',i),elemento=i,natureza='TUBULACAO')
        if not direcionado:g.add_edge((b,'E'),(a,'E'),key=('tubo',i),elemento=i,natureza='TUBULACAO')
    return dict(topologia=dict(modelo=dict(elementos=el),estrutural=dict(grafo=g,diagnosticos=[]),potencial=dict(grafo=g.copy(),diagnosticos=[])))


class CorredoresTest(unittest.TestCase):
    def setUp(self):self.p=pacote([(101,1,2),(102,2,3),(103,2,4)])
    def calc(self,p=None,**kw):
        args=dict(modo='ESTRUTURAL',origens=[1],destinos=[3],comprimentos={101:10,102:20,103:30});args.update(kw);return calcular(p or self.p,**args)
    def test_junction_origem_destino(self):self.assertEqual(set(self.calc()['criterios']),{'101','102'})
    def test_nao_inclui_ramo_sem_destino(self):self.assertNotIn('103',self.calc()['criterios'])
    def test_sem_origem_nao_seleciona_pontes(self):
        with self.assertRaisesRegex(ValueError,'Pontes'):self.calc(origens=[])
    def test_sem_destino(self):
        with self.assertRaises(ValueError):self.calc(destinos=[])
    def test_caminho_exige_um_par(self):
        with self.assertRaises(ValueError):self.calc(metodo='CAMINHO',destinos=[3,4])
    def test_corredor_compartilhado(self):
        r=self.calc(destinos=[3,4]);self.assertEqual(r['metricas']['101']['destinos'],2);self.assertTrue(r['metricas']['101']['compartilhado']);self.assertEqual(r['metricas']['102']['classe'],'RAMO_DESTINO')
    def test_multiplas_origens_custo_menor(self):
        r=self.calc(origens=[1,4]);self.assertEqual(r['rotas'][0]['origem'],(1,'E'))
    def test_multiplas_origens_sistemas_separados(self):
        p=pacote([(101,1,2),(102,3,4)]);r=self.calc(p,origens=[1,3],destinos=[2,4]);self.assertEqual(len(r['componentes_selecionados']),2);self.assertEqual(len(r['destinos_alcancados']),2)
    def test_inalcancavel(self):
        p=pacote([(101,1,2),(102,3,4)]);r=self.calc(p,destinos=[4]);self.assertEqual(r['elementos'],[]);self.assertEqual(len(r['destinos_inalcancaveis']),1)
    def test_destino_ausente(self):self.assertEqual(len(self.calc(destinos=[999])['destinos_inalcancaveis']),1)
    def test_origem_ausente(self):
        with self.assertRaises(ValueError):self.calc(origens=[999])
    def test_origem_tubulacao_rejeitada(self):
        with self.assertRaises(ValueError):self.calc(origens=[101])
    def test_nenhum_sentido_de_fluxo_inferido(self):
        p=pacote([(101,1,2),(102,2,3)],True);self.assertEqual(self.calc(p,origens=[3],destinos=[1])['elementos'],[])
    def test_comprimento_diferente_numero_arestas(self):
        p=pacote([(101,1,2),(102,2,3),(104,1,3)]);ls={101:1,102:1,104:20}
        self.assertEqual(set(self.calc(p,comprimentos=ls)['criterios']),{'104'});self.assertEqual(set(self.calc(p,criterio='COMPRIMENTO',comprimentos=ls)['criterios']),{'101','102'})
    def test_comprimento_indisponivel_nao_zero(self):
        with self.assertRaisesRegex(ValueError,'indisponível'):self.calc(criterio='COMPRIMENTO',comprimentos={})
    def test_arestas_sem_comprimento(self):self.assertIsNone(self.calc(comprimentos={})['rotas'][0]['comprimento_m'])
    def test_diametro_bruto_nao_confirmado(self):
        self.p['topologia']['modelo']['elementos'][101]['atributos']={'Physical':{'Physical_PipeDiameter':.5}};m=self.calc()['metricas']['101'];self.assertEqual(m['diametro_bruto'],.5);self.assertEqual(m['unidade_diametro'],'NÃO CONFIRMADA')
    def test_paralelas_apenas_uma_rota_principal(self):
        p=pacote([(101,1,2),(102,1,2)]);r=self.calc(p,destinos=[2],alternativas=1);self.assertEqual(len(r['elementos']),1);self.assertEqual(len(r['rotas_alternativas']),1);self.assertNotEqual(r['rotas'][0]['tubulacoes'],r['rotas_alternativas'][0]['tubulacoes'])
    def test_malha_alternativa_mesmo_custo(self):
        p=pacote([(101,1,2),(102,2,3),(103,1,4),(104,4,3)]);r=self.calc(p,alternativas=2);self.assertTrue(r['rotas_alternativas']);self.assertEqual(r['rotas_alternativas'][0]['comparacao'],'MESMO_CUSTO')
    def test_rotas_duplicadas_nao_inflam_contagem(self):self.assertEqual(self.calc(destinos=[3,3])['metricas']['101']['rotas'],1)
    def test_cancelamento(self):
        with self.assertRaises(InterruptedError):self.calc(cancelado=lambda:True)
    def test_nao_modifica_grafo(self):
        antes=list(self.p['topologia']['estrutural']['grafo'].edges(keys=True,data=True));self.calc(alternativas=1);self.assertEqual(antes,list(self.p['topologia']['estrutural']['grafo'].edges(keys=True,data=True)))
    def test_portas_nao_fundidas(self):
        g=self.p['topologia']['estrutural']['grafo'];g.add_node((1,'S'))
        with self.assertRaisesRegex(ValueError,'múltiplas portas'):self.calc()
        self.assertEqual(len(self.calc(origens=[{'id':1,'porta':'S'}])['destinos_inalcancaveis']),1)
    def test_porta_explicita(self):self.assertEqual(len(self.calc(origens=[dict(id=1,porta='E')])['rotas']),1)
    def test_porta_invalida(self):
        with self.assertRaises(ValueError):self.calc(origens=[dict(id=1,porta='Z')])
    def test_hipotese_bloqueada(self):
        with self.assertRaises(ValueError):self.calc(modo='ESTADOS_DO_CENARIO')
    def test_perspectivas_distintas(self):
        self.p['topologia']['potencial']['grafo'].remove_edge((2,'E'),(3,'E'),('tubo',102));self.assertEqual(len(self.calc()['rotas']),1);self.assertEqual(len(self.calc(modo='TODAS_VALVULAS_ABERTAS')['rotas']),0)
    def test_avisos_sem_provar_causa(self):
        p=pacote([(101,1,2),(102,3,4)]);p['topologia']['estrutural']['diagnosticos']=[dict(codigo='JUSANTE_NAO_INFORMADO',id=3)];r=self.calc(p,destinos=[4]);self.assertTrue(r['destinos_inalcancaveis'][0]['interrupcoes'])
    def test_origem_igual_destino(self):self.assertEqual(self.calc(destinos=[1])['rotas'][0]['quantidade_arestas'],0)
    def test_continuidade_editada(self):
        r=resumir_selecao(self.p,'ESTRUTURAL',[102,103],[(1,'E')],[(3,'E')]);self.assertEqual(len(r['componentes']),1);self.assertEqual(r['componentes'][0]['origens'],[])
    def test_busca_label_e_id(self):
        self.assertEqual(buscar_terminais(self.p,'ESTRUTURAL','J-3')[0]['id'],3);self.assertEqual(buscar_terminais(self.p,'ESTRUTURAL','3')[0]['id'],3)
    def test_busca_preserva_label_textual(self):
        self.p['topologia']['modelo']['elementos'][3]['label']='0012';self.assertEqual(buscar_terminais(self.p,'ESTRUTURAL','0012')[0]['label'],'0012')
    def test_busca_labels_repetidos(self):
        for i in (1,2):self.p['topologia']['modelo']['elementos'][i]['label']='Igual'
        self.assertEqual(len(buscar_terminais(self.p,'ESTRUTURAL','Igual')),2)
    def test_progresso(self):
        eventos=[];self.calc(progresso=lambda *a:eventos.append(a));self.assertTrue(eventos);self.assertTrue(all(a[1] is None or a[1]<a[2] for a in eventos))
    def test_resumo_componentes_multiplas_origens(self):
        p=pacote([(101,1,2),(102,3,4)]);r=resumir_selecao(p,'ESTRUTURAL',[101,102],[(1,'E'),(3,'E')],[(2,'E'),(4,'E')]);self.assertEqual(len(r['componentes']),2);self.assertTrue(all(c['origens'] for c in r['componentes']))


import test_decisoes_topologicas as fixture
from test_auditoria_fronteiras import APP
from auditoria_topologica_watergems import operacional as op,decisoes as db,conjuntos_investigacao as st
from auditoria_topologica_watergems.recuperacao_analises import inventariar,abrir_consulta
from auditoria_topologica_watergems.arquivos import hash_arquivo


class RecuperacaoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.DecisoesTest.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):fixture.DecisoesTest.tearDownClass.__func__(cls)
    def setUp(self):fixture.DecisoesTest.setUp(self)
    def tearDown(self):
        for j in self.janelas:
            if j.resultado_analise.tem_edicoes():j.resultado_analise.carregar(j.resultado_analise.caso,j.resultado_analise.modo,True)
        fixture.DecisoesTest.tearDown(self)
        from qgis.PyQt.QtCore import QEvent
        for j in self.janelas:
            if getattr(j,'_wna_atividades',None):j._wna_atividades.fechar()
            j.deleteLater()
        APP.sendPostedEvents(None,QEvent.DeferredDelete)
    def painel(self):return fixture.DecisoesTest.painel(self)
    def salvar(self):return op.salvar(self.base,self.p,self.c,'TODAS_VALVULAS_ABERTAS',resultado='MANTER CONFIGURAÇÃO ATUAL',observacao='Anotação preservada')
    def test_inventario_sem_escrever(self):
        h=hash_arquivo(self.base);r=inventariar(self.base,self.p);self.assertEqual(r['analises'],0);self.assertEqual(hash_arquivo(self.base),h)
    def test_contagens_banco(self):
        self.salvar();r=inventariar(self.base,self.p);self.assertEqual(r['analises'],1);self.assertEqual(r['por_perspectiva']['TODAS_VALVULAS_ABERTAS'],1);self.assertEqual(r['observacoes'],1)
    def test_pendente_oculta_na_perspectiva_errada(self):
        self.salvar();j=self.painel();self.assertEqual(j.modo.currentData(),'ESTRUTURAL');self.assertIn('1 análises salvas (0 nesta perspectiva)',j.carregada.text())
    def test_abrir_salva_remove_filtros_e_muda_perspectiva(self):
        self.salvar();j=self.painel();j.busca.setText('texto que oculta');j.origem_filtro.setCurrentIndex(2);self.assertTrue(j.mostrar_registro_salvo(self.c['uid'],'TODAS_VALVULAS_ABERTAS'));self.assertEqual(j.atual['uid'],self.c['uid']);self.assertEqual(j.fila.currentData(),'TODOS');self.assertEqual(j.resultado_analise.head['observacao'],'Anotação preservada')
    def test_consulta_nao_depende_de_filtros(self):
        self.salvar();j=self.painel();j.busca.setText('ocultar');d=abrir_consulta(j);self.assertTrue(d.isVisible());self.assertEqual(len(inventariar(self.base,self.p)['linhas']),1);d.close()
    def test_historico_analise_texto_antigo_disponivel(self):
        uid=self.salvar();op.salvar(self.base,self.p,self.c,'TODAS_VALVULAS_ABERTAS',resultado='CORREÇÃO NECESSÁRIA',esperada=uid);r=inventariar(self.base,self.p);self.assertEqual(len(r['linhas']),2);self.assertEqual(r['contextos_analisados'],1);self.assertIn('histórico',r['linhas'][0]['titulo'])
    def test_anotacao_legada(self):
        db.salvar_registro(self.base,self.p,self.c,'ESTRUTURAL','Anotação antiga');r=inventariar(self.base,self.p);self.assertEqual(r['anotacoes_legadas'],1);self.assertEqual(r['linhas'][0]['observacao'],'Anotação antiga')
    def test_revisao_legada(self):
        db.salvar_decisao(self.base,self.p,self.c,'ESTRUTURAL',justificativa='Legado');r=inventariar(self.base,self.p);self.assertEqual(r['revisoes_legadas'],1);self.assertEqual(r['linhas'][0]['observacao'],'Legado')
    def test_contexto_ausente_mantem_snapshot(self):
        self.salvar();r=inventariar(self.base,self.p,[]);self.assertFalse(r['linhas'][0]['localizavel']);self.assertEqual(r['linhas'][0]['titulo'],self.c['titulo'])
    def test_manual_recuperado(self):
        st.salvar(self.base,self.p,'LOCAL_MANUAL',dict(x=1,y=2,crs='EPSG:31983',titulo='Local manual'));j=self.painel();self.assertEqual(j._recuperadas['locais_manuais'],1);j.consultar_rapido(4);self.assertEqual(len(j.visiveis),1)
    def test_padrao_corredores_sem_pontes(self):
        j=self.painel();j.abrir_redes();d=j._redes_ui;self.assertEqual(d.metodo.currentData(),'CORREDORES');self.assertFalse(d.pontes.isChecked());self.assertFalse(d.origem_ui.valores());d.close()
    def test_terminal_por_tabela(self):
        j=self.painel();j.abrir_redes();d=j._redes_ui;s=d.origem_ui;s.setChecked(True);s.busca.setText('1');s.procurar();self.assertGreater(s.tabela.rowCount(),0);s.tabela.selectRow(0);s.adicionar_linhas();self.assertEqual(len(s.valores()),1);d.close()
    def test_metodos_ocultam_parametros_irrelevantes(self):
        j=self.painel();j.abrir_redes();d=j._redes_ui;d.metodo.setCurrentIndex(d.metodo.findData('PONTES'));self.assertTrue(d.origem_ui.isHidden());d.metodo.setCurrentIndex(d.metodo.findData('CORREDORES'));self.assertFalse(d.origem_ui.isHidden());d.close()
    def test_conjunto_legado_nao_renomeado_corredor(self):
        j=self.painel();j.abrir_redes();d=j._redes_ui;d.restaurar_parametros(dict(metodo='TOPOLOGICO',origens=[],destinos=[]));self.assertEqual(d.metodo.currentData(),'LEGADO');d.close()
    def test_selecao_qgis_identidade_node(self):
        from qgis.core import QgsVectorLayer,QgsField,QgsFeature,QgsProject
        from qgis.PyQt.QtCore import QVariant
        j=self.painel();j.abrir_redes();d=j._redes_ui;el=self.p['topologia']['modelo']['elementos'];i=next(i for i,e in el.items() if e['familia']=='NO' and e['excluido'] is False)
        c=QgsVectorLayer('Point?crs=EPSG:31983','Nós sintéticos','memory');c.dataProvider().addAttributes([QgsField('WG_ID',QVariant.String),QgsField('WG_UID',QVariant.String)]);c.updateFields();f=QgsFeature(c.fields());f.setAttributes([str(i),el[i]['uid']]);c.dataProvider().addFeatures([f]);c.setCustomProperty('wna/uid',self.p['resultado']['meta']['topologia']['execucao_uid']);QgsProject.instance().addMapLayer(c);c.selectAll();d.origem_ui.usar_selecao();self.assertEqual(d.origem_ui.valores()[0]['id'],i);d.close();QgsProject.instance().removeMapLayer(c.id())
    def test_captura_cancelada(self):
        from qgis.gui import QgsMapCanvas
        from qgis.PyQt.QtGui import QKeyEvent
        from qgis.PyQt.QtCore import Qt,QEvent
        j=self.painel();canvas=QgsMapCanvas();j.legado.canvas=canvas;j.abrir_redes();d=j._redes_ui;d.origem_ui.capturar();self.assertIsNotNone(d.origem_ui._captura);d.origem_ui._captura[0].keyPressEvent(QKeyEvent(QEvent.KeyPress,Qt.Key_Escape,Qt.NoModifier));self.assertIsNone(d.origem_ui._captura);self.assertEqual(d.origem_ui.valores(),[]);d.close();canvas.deleteLater()
    def test_captura_mapa_com_confirmacao(self):
        from qgis.gui import QgsMapCanvas
        from qgis.core import QgsCoordinateReferenceSystem
        from qgis.PyQt.QtCore import Qt
        from qgis.PyQt.QtWidgets import QInputDialog
        j=self.painel();canvas=QgsMapCanvas();canvas.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:31983'));j.legado.canvas=canvas;j.abrir_redes();d=j._redes_ui;s=d.origem_ui;s.capturar();_,dados,_=s.indice();i,g=dados[0]
        with patch.object(QInputDialog,'getItem',side_effect=lambda *args:(args[3][0],True)):s._captura[0].canvasClicked.emit(g.asPoint(),Qt.LeftButton)
        self.assertEqual(len(s.valores()),1);d.close();canvas.deleteLater()
    def test_persistencia_rota_reabertura_exportacao(self):
        from auditoria_topologica_watergems.saidas_integracao import reabrir
        from auditoria_topologica_watergems.redes_principais import exportar_csv
        a,b,k,d=next((a,b,k,d) for a,b,k,d in self.p['topologia']['estrutural']['grafo'].edges(keys=True,data=True) if d.get('natureza')=='TUBULACAO')
        r=calcular(self.p,'ESTRUTURAL',[dict(id=a[0],porta=a[1])],[dict(id=b[0],porta=b[1])],comprimentos={});st.salvar(self.base,self.p,'REDE_PRINCIPAL',dict(nome='Caminho sintético',criterios=r),r['elementos']);p=reabrir(self.base);registro=st.atuais(self.base,p,'REDE_PRINCIPAL')[0];self.assertTrue(registro['dados']['criterios']['rotas']);f=exportar_csv(self.dir/'rotas.csv',p,registro);self.assertIn('DestinosAtendidos',f.read_text(encoding='utf-8-sig'))
    def test_paginacao_analise_salva(self):
        j=self.painel();clones=[dict(copy.deepcopy(self.c),uid='sintetico-'+str(n),titulo='Caso '+str(n)) for n in range(450)];alvo=clones[-1];op.salvar(self.base,self.p,alvo,'TODAS_VALVULAS_ABERTAS',resultado='MANTER CONFIGURAÇÃO ATUAL');j.casos+=clones;j._analises=op.indice(self.base,self.ig);self.assertTrue(j.mostrar_registro_salvo(alvo['uid'],'TODAS_VALVULAS_ABERTAS'));self.assertEqual(j.atual['uid'],alvo['uid']);self.assertGreater(j._pagina,0)
    def test_falha_worker_preserva_assinatura_antiga(self):
        from auditoria_fronteiras.atividade import sistema
        from qgis.PyQt.QtWidgets import QMessageBox
        j=self.painel();j.abrir_redes();d=j._redes_ui;d.gerado={'metodo':'CORREDORES'};d._parametros_calculados='antiga';d.origem_ui.adicionar([dict(id=1,porta='E')]);d.destino_ui.adicionar([dict(id=3,porta='E')])
        with patch.object(sistema(j),'executar_thread',side_effect=lambda titulo,contexto,fn,pronto,erro:erro('Falha de ensaio')):d.calcular()
        self.assertEqual(d._parametros_calculados,'antiga')
        with patch.object(QMessageBox,'warning'),patch.object(st,'salvar') as gravar:self.assertFalse(d.salvar());gravar.assert_not_called()
        d.close()
    def test_filtros_irrelevantes_nao_invalidam_caminho(self):
        j=self.painel();j.abrir_redes();d=j._redes_ui;a=d.parametros_assinatura()
        with patch.object(j.editor_filtros,'configuracao',return_value={'mudou':True}):self.assertEqual(a,d.parametros_assinatura())
        d.close()
    def test_consulta_reutiliza_janela(self):
        self.salvar();j=self.painel();a=abrir_consulta(j);b=abrir_consulta(j);self.assertIs(a,b);a.close()
    def test_conjuntos_outra_perspectiva_disponiveis(self):
        from qgis.PyQt.QtWidgets import QInputDialog
        st.salvar(self.base,self.p,'REDE_PRINCIPAL',dict(nome='Conjunto potencial'),modo='TODAS_VALVULAS_ABERTAS');j=self.painel();j.abrir_redes();d=j._redes_ui;self.assertEqual(d.modo,'ESTRUTURAL')
        with patch.object(QInputDialog,'getItem',side_effect=lambda *a:(a[3][0],True)):d.recuperar()
        self.assertEqual(d.modo,'TODAS_VALVULAS_ABERTAS');self.assertEqual(j.modo.currentData(),'ESTRUTURAL');self.assertIn('TODAS_VALVULAS_ABERTAS',d.windowTitle());d.close()


if __name__=='__main__':unittest.main()
