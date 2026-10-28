"""Resultados simples, proveniência, relações e filtros tipados com fontes sintéticas."""
import unittest,sqlite3,copy,json
from pathlib import Path
from unittest.mock import patch
import test_decisoes_topologicas as fixture
from test_auditoria_fronteiras import APP,camada,quadrado
from auditoria_topologica_watergems import operacional as op,decisoes as db
from auditoria_topologica_watergems.filtros import ContextoFiltros,comparar,combinar,quantificar,AUSENTE
from qgis.PyQt.QtWidgets import QMessageBox
from auditoria_topologica_watergems.exportacao_decisoes import tabelas_decisoes

class FiltrosTipadosTest(unittest.TestCase):
    def test_numero(self):self.assertTrue(comparar(100,'IGUAL','100'));self.assertFalse(comparar(100,'MAIOR','100'))
    def test_intervalo(self):self.assertTrue(comparar(150,'ENTRE','100','300'));self.assertFalse(comparar(99,'ENTRE','100','300'))
    def test_texto_id(self):self.assertTrue(comparar('0012','IGUAL','0012'));self.assertFalse(comparar('0012','IGUAL','12'));self.assertIsNone(comparar('0012','MAIOR','10'))
    def test_contem(self):self.assertTrue(comparar('PVC','CONTEM','PV'));self.assertTrue(comparar('PVC','COMECA','P'));self.assertTrue(comparar('PVC','TERMINA','C'))
    def test_lista(self):self.assertTrue(comparar('001','LISTA',['001','002']));self.assertFalse(comparar('1','LISTA',['001']))
    def test_nulos_vazios(self):self.assertTrue(comparar(None,'NULO'));self.assertFalse(comparar('','NULO'));self.assertTrue(comparar('','VAZIO'));self.assertFalse(comparar(0,'NULO'))
    def test_ausente_nao_nulo(self):self.assertIsNone(comparar(AUSENTE,'NULO'));self.assertIsNone(comparar(None,'DIFERENTE','PVC'))
    def test_booleanos(self):self.assertTrue(comparar(False,'FALSO'));self.assertIsNone(comparar(0,'FALSO'));self.assertTrue(comparar(True,'VERDADEIRO'))
    def test_datas(self):
        from datetime import date
        self.assertTrue(comparar(date(2026,1,1),'ANTES','2026-02-01'));self.assertTrue(comparar(date(2026,1,1),'ENTRE','2025-01-01','2027-01-01'))
    def test_nao_finitos(self):self.assertIsNone(comparar(float('nan'),'IGUAL','3'));self.assertIsNone(comparar(1,'ENTRE','5','1'))
    def test_tres_valores(self):self.assertIsNone(combinar([True,None],'E'));self.assertFalse(combinar([False,None],'E'));self.assertTrue(combinar([True,None],'OU'))
    def test_quantificadores(self):self.assertTrue(quantificar([False,True],'QUALQUER'));self.assertFalse(quantificar([False,True],'TODOS'));self.assertFalse(quantificar([False,True],'NENHUM'));self.assertIsNone(quantificar([False,None],'NENHUM'));self.assertIsNone(quantificar([],'TODOS'))

class OperacionalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.DecisoesTest.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):fixture.DecisoesTest.tearDownClass.__func__(cls)
    setUp=fixture.DecisoesTest.setUp
    painel=fixture.DecisoesTest.painel
    def tearDown(self):
        for j in self.janelas:
            j.resultado_analise.carregar(j.resultado_analise.caso,j.resultado_analise.modo,True)
        fixture.DecisoesTest.tearDown(self)
    def salvar(self,**kwargs):return op.salvar(self.base,self.p,self.c,db.MODOS[0],**kwargs)
    def test_observacao_sem_conclusao(self):self.salvar(observacao='Verificar ponta seca');self.assertEqual(op.historico(self.base,self.ig)[0]['resultado'],'PENDENTE')
    def test_resultados_sem_requisitos(self):
        anterior=None
        for r in op.RESULTADOS:anterior=self.salvar(resultado=r,esperada=anterior)
        self.assertEqual(len(op.historico(self.base,self.ig)),len(op.RESULTADOS))
    def test_manter_vrp(self):
        self.salvar(resultado=op.RESULTADOS[2],motivo=op.MOTIVOS[1]);h=op.historico(self.base,self.ig)[0];self.assertFalse(op.pendente(h));self.assertEqual(h['motivo'],op.MOTIVOS[1]);self.assertEqual(db.propostas(self.base,self.ig),[])
    def test_adequada(self):self.salvar(resultado=op.RESULTADOS[1]);self.assertEqual(op.estado(op.historico(self.base,self.ig)[0]),op.ESTADOS[2])
    def test_correcao_sem_proposta(self):self.salvar(resultado=op.RESULTADOS[3]);self.assertFalse(db.propostas(self.base,self.ig))
    def test_motivo_livre(self):self.salvar(resultado=op.RESULTADOS[2],motivo='Separação mantida no exemplo sintético')
    def test_sem_resultado_nem_texto(self):
        with self.assertRaises(ValueError):self.salvar()
    def test_historico_reabrir(self):
        a=self.salvar(resultado=op.RESULTADOS[2]);b=self.salvar(resultado=op.RESULTADOS[4],esperada=a);h=op.historico(self.base,self.ig);self.assertEqual(h[-1]['anterior'],a);self.assertEqual(h[-1]['uid'],b)
    def test_concorrencia(self):
        self.salvar(resultado='PENDENTE')
        with self.assertRaises(ValueError):self.salvar(resultado=op.RESULTADOS[2])
        self.assertEqual(len(op.historico(self.base,self.ig)),1)
    def test_migracao_backup(self):
        before=db.historico(self.base,self.ig,self.c['uid'],db.MODOS[0]);self.salvar(resultado=op.RESULTADOS[2]);backups=list(self.dir.glob('*antes_operacional*.gpkg'));self.assertEqual(len(backups),1)
        with sqlite3.connect(backups[0]) as c:self.assertEqual(c.execute('pragma integrity_check').fetchone()[0],'ok');self.assertFalse(c.execute("select name from sqlite_master where name='IGD_ANALISES'").fetchone())
        self.assertEqual(db.historico(self.base,self.ig,self.c['uid'],db.MODOS[0]),before)
    def test_imutavel_integridade(self):
        self.salvar(resultado=op.RESULTADOS[2])
        with sqlite3.connect(self.base) as c:
            self.assertFalse(c.execute('pragma foreign_key_check').fetchall())
            with self.assertRaises(sqlite3.IntegrityError):c.execute("update IGD_ANALISES set resultado='PENDENTE'")
    def test_prioridade_manual(self):
        self.salvar(resultado='PENDENTE',prioridade='Baixa');h=op.historico(self.base,self.ig)[0];self.assertEqual(h['prioridade_trabalho'],'Baixa');self.assertIn(h['prioridade_auto'],op.PRIORIDADES)
    def test_sugestao_nao_e_defeito(self):
        c=copy.deepcopy(self.c);c['categorias']=['AUSENTE'];self.assertEqual(op.sugerir(c)[0],'Média')
    def test_perspectivas_separadas(self):
        self.salvar(resultado=op.RESULTADOS[2]);self.assertFalse(op.historico(self.base,self.ig,modo=db.MODOS[1]))
    def test_filtros_persistidos(self):
        d={'operador':'E','condicoes':[]};op.salvar_filtros(self.base,self.p,db.MODOS[0],d);self.assertEqual(op.carregar_filtros(self.base,self.p,db.MODOS[0]),d);self.assertIsNone(op.carregar_filtros(self.base,self.p,db.MODOS[1]))
    def test_nao_herda_versao(self):
        self.salvar(resultado=op.RESULTADOS[2]);self.assertFalse(op.historico(self.base,'execucao-diferente'));n=fixture.clonar(self.p);n['resultado']['meta']['topologia']['execucao_uid']='outra';self.assertIsNone(op.carregar_filtros(self.base,n,db.MODOS[0]))
    def contexto(self):
        t=self.p['dossie']['tubulacoes'][0];t['atributos'].update(diametro_teste=150,material_teste='PVC',codigo_teste='0001',vazio_teste='',nulo_teste=None);ctx=ContextoFiltros(self.p);k=ctx._gis[t['uid']]['camada'];return ctx,k
    def cond(self,k,campo,operador='IGUAL',valor='PVC',**kwargs):return dict(camada=k,campo=[campo],operador=operador,valor=valor,quantificador='QUALQUER',**kwargs)
    def test_material_diametro_personalizado(self):
        ctx,k=self.contexto();d=dict(operador='E',condicoes=[self.cond(k,'material_teste'),self.cond(k,'diametro_teste','ENTRE','100',valor2='300'),self.cond(k,'codigo_teste','IGUAL','0001')]);self.assertTrue(ctx.avaliar(self.c,d))
    def test_campo_nulo_ausente(self):
        ctx,k=self.contexto();self.assertTrue(ctx.avaliar(self.c,self.cond(k,'nulo_teste','NULO')));self.assertIsNone(ctx.avaliar(self.c,self.cond(k,'nao_existe','NULO')))
    def test_ou_grupos(self):
        ctx,k=self.contexto();self.assertTrue(ctx.avaliar(self.c,dict(operador='OU',condicoes=[self.cond(k,'material_teste','IGUAL','FERRO'),self.cond(k,'codigo_teste','IGUAL','0001')])))
    def test_cache_subconjuntos(self):
        ctx,k=self.contexto();cond={'operador':'E','condicoes':[]};ctx.filtrar([self.c],cond,db.MODOS[0]);casos=fixture.catalogar(self.p);self.assertEqual(len(ctx.filtrar(casos,cond,db.MODOS[0])[0]),len(casos))
    def test_campos_tipos_zeros(self):
        ctx,k=self.contexto();campos={tuple(c['caminho']):c for c in ctx.campos(k)};self.assertEqual(campos[('codigo_teste',)]['tipo'],'texto');self.assertEqual(campos[('diametro_teste',)]['tipo'],'numero')
    def test_wg_proveniencia(self):
        ctx=ContextoFiltros(self.p);i=self.c['wg_ids'][0];key=ctx._wg[i]['camada'];e=ctx.entidades_caso(self.c,key)[0];self.assertIn('cenario',e['proveniencia']);self.assertIn('alternativas',e['proveniencia']);self.assertTrue(ctx.avaliar(self.c,self.cond(key,'label',valor=self.p['topologia']['modelo']['elementos'][i]['label'])))
    def test_relacoes_identificadas(self):
        ctx=ContextoFiltros(self.p);self.assertTrue(ctx.areas);self.assertTrue(ctx.relacoes);self.salvar(resultado='PENDENTE',contexto=ctx)
        with sqlite3.connect(self.base) as c:self.assertGreater(c.execute('select count(*) from IGD_RELACOES_AREA').fetchone()[0],0)
    def test_nomes_nao_criam_relacoes(self):
        p=fixture.clonar(self.p);p['dossie']['evento_poligono']=[];ctx=ContextoFiltros(p);self.assertFalse(any(r['origem']=='AUDITORIA_GEOMETRICA' for r in ctx.relacoes))
    def test_poligono_adicional_e_crs(self):
        from qgis.core import QgsCoordinateReferenceSystem,QgsCoordinateTransform,QgsProject
        ctx=ContextoFiltros(self.p);poly=camada('Polygon',[quadrado(-50,-50,100)]);key=ctx.adicionar_poligonos(poly);self.assertTrue(ctx.avaliar(self.c,self.cond(key,'id',valor=1,relacao='DENTRO')))
        self.salvar(resultado='PENDENTE',contexto=ctx);novo=ContextoFiltros(self.p);novo.restaurar_persistidas(self.base);self.assertIn(key,novo.camadas);self.assertTrue(novo.avaliar(self.c,self.cond(key,'id',valor=1,relacao='DENTRO')))
    def test_crs_nao_validado_bloqueia(self):
        p=fixture.clonar(self.p);p['resultado']['meta']['parametros']['espacial_habilitado']=False;ctx=ContextoFiltros(p)
        with self.assertRaises(ValueError):ctx.adicionar_poligonos(camada('Polygon',[quadrado()]))
    def test_ui_simples_sem_responsavel(self):
        j=self.painel();f=j.resultado_analise;f.resultado.setCurrentIndex(f.resultado.findData(op.RESULTADOS[2]));f.salvar_botao.click();self.assertTrue(op.historico(self.base,self.ig));self.assertFalse(j.analise.tabs.isTabVisible(0))
    def test_ui_observacao_sem_resultado(self):
        j=self.painel();f=j.resultado_analise;f.observacoes.setPlainText('Conferir no modelo');self.assertTrue(f.salvar());self.assertEqual(op.historico(self.base,self.ig)[0]['resultado'],'PENDENTE')
    def test_ui_sai_da_fila(self):
        j=self.painel();j.fila.setCurrentIndex(j.fila.findData('PENDENTES'));u=j.atual['uid'];f=j.resultado_analise;f.resultado.setCurrentIndex(f.resultado.findData(op.RESULTADOS[2]));self.assertTrue(f.salvar());self.assertNotIn(u,[c['uid'] for c in j.visiveis]);j.fila.setCurrentIndex(j.fila.findData('TODOS'));self.assertIn(u,[c['uid'] for c in j.visiveis])
    def test_ui_cancelamento_preserva(self):
        j=self.painel();f=j.resultado_analise;f.observacoes.setPlainText('Não perder');u=j.atual['uid']
        with patch('auditoria_topologica_watergems.form_operacional.QMessageBox.question',return_value=QMessageBox.Cancel):j.busca.setText('sem-resultados')
        self.assertEqual(j.atual['uid'],u);self.assertEqual(f.observacoes.toPlainText(),'Não perder')
    def test_resultado_vazio_observacao_vazia_com_selecao(self):
        self.salvar(resultado=op.RESULTADOS[3],observacao='',motivo='');self.assertEqual(op.historico(self.base,self.ig)[0]['resultado'],op.RESULTADOS[3])
    def test_separacao_setores(self):
        self.salvar(resultado=op.RESULTADOS[2],motivo=op.MOTIVOS[0]);self.assertFalse(op.pendente(op.historico(self.base,self.ig)[0]))
    def test_prioridade_sugerida_preservada(self):
        u=self.salvar(resultado='PENDENTE');h=op.historico(self.base,self.ig)[0]
        with patch('auditoria_topologica_watergems.operacional.sugerir',return_value=('Alta','Regra modificada no teste')):self.salvar(resultado='PENDENTE',esperada=u)
        self.assertEqual(op.historico(self.base,self.ig)[-1]['criterio_auto'],h['criterio_auto'])
    def test_falha_na_gravacao_rollback(self):
        with patch('auditoria_topologica_watergems.operacional.persistir_relacoes',side_effect=RuntimeError('Falha simulada')):
            with self.assertRaises(RuntimeError):self.salvar(resultado=op.RESULTADOS[2])
        self.assertEqual(op.historico(self.base,self.ig),[])
    def test_contexto_outra_versao_nao_herda(self):
        self.salvar(resultado=op.RESULTADOS[2]);nova=fixture.clonar(self.p);nova['resultado']['meta']['uid']='nova-execucao';self.assertFalse(op.indice(self.base,nova['resultado']['meta']['uid']))
    def test_poligonos_crs_diferentes(self):
        ctx=ContextoFiltros(self.p);c=camada('Polygon',['POLYGON((-47 -24,-46 -24,-46 -23,-47 -23,-47 -24))'],crs='EPSG:4326');key=ctx.adicionar_poligonos(c);a=next(a for a in ctx.areas.values() if a.get('fonte_filtro')==key);self.assertEqual(a['crs'],'EPSG:31983');self.assertEqual(__import__('qgis.core',fromlist=['QgsCoordinateReferenceSystem']).QgsCoordinateReferenceSystem(a['crs_origem']).authid(),'EPSG:4326')
    def test_geometrias_ausentes_nao_inventadas(self):
        ctx=ContextoFiltros(self.p);self.assertEqual(ctx.recuperar_geometrias(),0);self.assertTrue(ctx.avisos)
    def test_geometrias_recuperadas_por_assinatura(self):
        from test_inspecao_exportacao import preparar
        from qgis.core import QgsProject
        r,a,d,redes,pol=preparar();p=fixture.clonar(self.p);p['dossie']=d;p['resultado']['locais']=d['locais'];ctx=ContextoFiltros(p);projeto=QgsProject();projeto.addMapLayer(pol)
        try:self.assertGreater(ctx.recuperar_geometrias(projeto),0)
        finally:projeto.clear()
    def test_filtro_sobreposicao_preserva_candidatos(self):
        ctx=ContextoFiltros(self.p);c=camada('Polygon',[quadrado(-50,-50,100),quadrado(-20,-20,100)]);key=ctx.adicionar_poligonos(c);self.assertEqual(len(ctx.entidades_caso(self.c,key)),2)
    def test_condicoes_setor_e_vrp(self):
        ctx=ContextoFiltros(self.p);a=camada('Polygon',[quadrado(-50,-50,100)],nome='Limite A');b=camada('Polygon',[quadrado(-40,-40,80)],nome='Limite B');ka=ctx.adicionar_poligonos(a);kb=ctx.adicionar_poligonos(b);d=dict(operador='E',condicoes=[self.cond(ka,'id',valor=1,relacao='DENTRO'),self.cond(kb,'id',valor=1,relacao='DENTRO')]);self.assertTrue(ctx.avaliar(self.c,d))
    def test_nenhum_atributo_ausente_indeterminado(self):
        ctx,k=self.contexto();d=self.cond(k,'inexistente');d['quantificador']='NENHUM';self.assertIsNone(ctx.avaliar(self.c,d))
    def test_mesma_camada_cache_campos(self):
        ctx,k=self.contexto();self.assertIs(ctx.campos(k),ctx.campos(k))
    def test_ui_resultado_analisado_filtro_todos(self):
        j=self.painel();j.resultado_filtro.setCurrentIndex(j.resultado_filtro.findData(op.RESULTADOS[2]));self.assertEqual(j.fila.currentData(),'TODOS')
    def test_ui_salvar_proxima_nao_pula_caso(self):
        j=self.painel();j.limpar_filtros();ids=[c['uid'] for c in j.visiveis];self.assertGreater(len(ids),1);j.lista.selectRow(0);f=j.resultado_analise;f.resultado.setCurrentIndex(f.resultado.findData(op.RESULTADOS[2]));f.proxima_botao.click();self.assertEqual(j.atual['uid'],ids[1])
    def test_ui_repeticao_nao_duplica(self):
        j=self.painel();f=j.resultado_analise;f.observacoes.setPlainText('Ainda investigando');self.assertTrue(f.salvar());self.assertTrue(f.salvar());self.assertEqual(len(op.historico(self.base,self.ig)),1)
    def test_ui_historico_legado_preservado(self):
        db.salvar_registro(self.base,self.p,self.c,db.MODOS[0],'Anotação anterior');j=self.painel();self.assertIn('Anotação anterior',j.analise.historia.toPlainText())
    def test_datas_qgis_persistidas(self):
        from qgis.core import QgsField
        from qgis.PyQt.QtCore import QDate,QVariant
        ctx=ContextoFiltros(self.p);c=camada('Polygon',[quadrado(-50,-50,100)]);c.dataProvider().addAttributes([QgsField('DATA_TESTE',QVariant.Date)]);c.updateFields();f=next(c.getFeatures());c.dataProvider().changeAttributeValues({f.id():{c.fields().indexFromName('DATA_TESTE'):QDate(2026,10,27)}});k=ctx.adicionar_poligonos(c);cond=self.cond(k,'DATA_TESTE','ANTES','2027-01-01');self.assertTrue(ctx.avaliar(self.c,cond));self.salvar(resultado='PENDENTE',contexto=ctx);novo=ContextoFiltros(self.p);novo.restaurar_persistidas(self.base);self.assertTrue(novo.avaliar(self.c,cond))
    def test_contagem_indeterminados(self):
        ctx,k=self.contexto();v,n=ctx.filtrar([self.c],self.cond(k,'inexistente'),db.MODOS[0]);self.assertEqual(v,[]);self.assertEqual(n,1)
    def test_editor_adicionar_remover(self):
        from qgis.PyQt.QtWidgets import QPushButton
        ctx,k=self.contexto();j=self.painel();editor=j.editor_filtros;editor.setChecked(True);editor.camada.setCurrentIndex(editor.camada.findData(k));idx=next(i for i in range(editor.campo.count()) if editor.campo.itemData(i)['caminho']==['material_teste']);editor.campo.setCurrentIndex(idx);editor.valor.setText('PVC');next(b for b in editor.findChildren(QPushButton) if b.text()=='Adicionar condição').click();self.assertEqual(len(editor.configuracao()['condicoes']),1);editor.arvore.setCurrentItem(editor.arvore.topLevelItem(0).child(0));editor.remover();self.assertFalse(editor.configuracao()['condicoes'])
    def test_editor_salvar_clicked(self):
        from qgis.PyQt.QtWidgets import QPushButton
        j=self.painel();editor=j.editor_filtros;editor.setChecked(True);next(b for b in editor.findChildren(QPushButton) if b.text().startswith('Salvar filtros')).click();self.assertIsNotNone(op.carregar_filtros(self.base,self.p,j.modo.currentData()))
    def test_paginacao_sem_truncar_filtro(self):
        j=self.painel();c=copy.deepcopy(j.atual);j.casos=[dict(c,uid='sintetico-%04d'%i,titulo='Ocorrência %04d'%i) for i in range(550)];j.limpar_filtros();self.assertEqual(len(j.visiveis),550);self.assertEqual(j.lista.rowCount(),200);j.mudar_pagina(1);self.assertEqual(j.atual['uid'],j.visiveis[200]['uid']);j.selecionar_uid(j.visiveis[500]['uid']);self.assertEqual(j.lista.rowCount(),150);self.assertEqual(j.atual['uid'],j.visiveis[500]['uid'])
    def test_cache_limitado(self):
        ctx,k=self.contexto()
        for n in range(20):ctx.filtrar([self.c],self.cond(k,'codigo_teste',valor=str(n)),db.MODOS[0])
        self.assertLessEqual(len(ctx._cache),8)
    def test_referencia_repetida_nao_duplica(self):
        ctx=ContextoFiltros(self.p);c=camada('Polygon',[quadrado(-50,-50,100)]);k=ctx.adicionar_poligonos(c);k2=ctx.adicionar_poligonos(c);self.assertEqual(k,k2);self.assertEqual(len(ctx._por_camada[k]),1)
    def test_comparacao_conta_novos_resultados_sem_comprovacao(self):
        from auditoria_topologica_watergems.comparacao_decisoes import resumo_revisoes
        self.salvar(resultado=op.RESULTADOS[2]);r=resumo_revisoes(self.base,self.ig,db.MODOS[0],10);self.assertEqual(r['revisados'],1);self.assertEqual(r['pendentes'],9);self.assertEqual(r['corretos'],0);self.assertEqual(r['manter_configuracao'],1)
    def test_exportacoes(self):
        self.salvar(resultado=op.RESULTADOS[2]);t=tabelas_decisoes(self.base,self.p);self.assertEqual(len(t['HIST_ANALISES'][1]),1);self.assertTrue(any(r[4]==op.RESULTADOS[2] for r in t['RESULTADOS_INVESTIGATIVOS'][1]))

if __name__=='__main__':unittest.main()
