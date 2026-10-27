"""Locais sem eventos, conjuntos estruturais e histórico em bases sintéticas."""
import copy
import csv
import json
import sqlite3
import unittest
from unittest.mock import patch
import networkx as nx
import test_decisoes_topologicas as fixture
from test_auditoria_fronteiras import APP
from auditoria_topologica_watergems import conjuntos_investigacao as st,locais_manuais as lm,redes_principais as rp,operacional as op
from auditoria_topologica_watergems.filtros import ContextoFiltros
from auditoria_topologica_watergems.arquivos import hash_arquivo


class LocaisRedesTest(unittest.TestCase):
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
            atividade=getattr(j,'_wna_atividades',None)
            if atividade:atividade.fechar()
            j.deleteLater()
        APP.sendPostedEvents(None,QEvent.DeferredDelete)
    def criar(self,**kw):
        d=dict(x=123.123456789,y=456.1,crs='EPSG:31983',titulo='',observacoes='');d.update(kw)
        return st.salvar(self.base,self.p,'LOCAL_MANUAL',d)
    def atual(self):return st.atuais(self.base,self.p,'LOCAL_MANUAL')[0]
    def wg(self):return next(i for i,e in self.p['topologia']['modelo']['elementos'].items() if e['familia']=='LINK' and e['excluido'] is False)
    def test_ponto_sem_evento(self):
        antes=copy.deepcopy(self.p['dossie']);uid,h=self.criar();r=self.atual();self.assertEqual(r['obj_uid'],uid);self.assertEqual(r['dados']['origem'],'MANUAL');self.assertEqual(antes,self.p['dossie']);self.assertEqual(r['vinculos'],[])
    def test_historico_titulo(self):
        uid,h=self.criar();r=self.atual();st.salvar(self.base,self.p,'LOCAL_MANUAL',dict(r['dados'],titulo='Conferir'),uid=uid,esperada=h);self.assertEqual(len(st.historico(self.base,self.p)),2);self.assertEqual(self.atual()['anterior'],h)
    def test_concorrencia(self):
        uid,h=self.criar()
        with self.assertRaisesRegex(ValueError,'outra sessão'):st.salvar(self.base,self.p,'LOCAL_MANUAL',self.atual()['dados'],uid=uid)
        self.assertEqual(len(st.historico(self.base,self.p)),1)
    def test_backup_integridade(self):
        self.criar();bs=list(self.dir.glob('*antes_conjuntos*.gpkg'));self.assertEqual(len(bs),1)
        with sqlite3.connect(bs[0]) as c:self.assertEqual(c.execute('pragma integrity_check').fetchone()[0],'ok');self.assertFalse(c.execute("select 1 from sqlite_master where name='IGD_OBJETOS'").fetchone())
    def test_idempotencia_esquema(self):
        self.criar();st.preparar(self.base,self.p);self.assertEqual(len(list(self.dir.glob('*antes_conjuntos*.gpkg'))),1)
    def test_historico_imutavel(self):
        self.criar()
        with sqlite3.connect(self.base) as c:
            with self.assertRaises(sqlite3.IntegrityError):c.execute('delete from IGD_OBJ_HIST')
    def test_exclusao_logica_e_reabertura(self):
        uid,h=self.criar();r=self.atual();st.salvar(self.base,self.p,'LOCAL_MANUAL',r['dados'],uid=uid,esperada=h,excluido=True);self.assertEqual(st.atuais(self.base,self.p),[]);self.assertEqual(len(st.atuais(self.base,self.p,excluidos=True)),1)
        r=st.atuais(self.base,self.p,excluidos=True)[0];st.salvar(self.base,self.p,'LOCAL_MANUAL',r['dados'],uid=uid,esperada=r['uid']);self.assertEqual(len(st.atuais(self.base,self.p)),1)
    def test_crs_invalido(self):
        with self.assertRaises(ValueError):self.criar(crs='sem_crs')
    def test_coordenada_invalida(self):
        with self.assertRaises(ValueError):self.criar(x=float('nan'))
    def test_perspectiva_bloqueada(self):
        with self.assertRaises(ValueError):st.salvar(self.base,self.p,'LOCAL_MANUAL',dict(x=1,y=2,crs='EPSG:31983'),modo='ESTADOS_DO_CENARIO')
    def test_vinculo_wg_identidade(self):
        i=self.wg();v=st.vinculo_wg(self.p,i);st.salvar(self.base,self.p,'LOCAL_MANUAL',dict(x=1,y=2,crs='EPSG:31983'),[v]);self.assertEqual(self.atual()['vinculos'][0]['dados']['uid'],self.p['topologia']['modelo']['elementos'][i]['uid'])
    def test_vinculo_repetido(self):
        v=st.vinculo_wg(self.p,self.wg())
        with self.assertRaisesRegex(ValueError,'repetido'):st.salvar(self.base,self.p,'LOCAL_MANUAL',dict(x=1,y=2,crs='EPSG:31983'),[v,v])
    def test_vinculo_ausente(self):
        with self.assertRaises(ValueError):st.vinculo_wg(self.p,-999)
    def test_preserva_modelo(self):
        m=copy.deepcopy(self.p['topologia']['modelo']);self.criar();self.assertEqual(m,self.p['topologia']['modelo'])
    def test_caso_sem_fusao(self):
        self.criar();cs=lm.casos(self.base,self.p);self.assertEqual(len(cs),1);self.assertEqual(cs[0]['tipo'],'MANUAL');self.assertIsNone(cs[0]['local_uid'])
    def test_edicao_texto_preserva_contexto(self):
        uid,h=self.criar();c=lm.casos(self.base,self.p)[0];r=self.atual();st.salvar(self.base,self.p,'LOCAL_MANUAL',dict(r['dados'],observacoes='Outro texto'),uid=uid,esperada=h);self.assertEqual(c['uid'],lm.casos(self.base,self.p)[0]['uid'])
    def test_mover_exige_nova_analise(self):
        uid,h=self.criar();c=lm.casos(self.base,self.p)[0];r=self.atual();st.salvar(self.base,self.p,'LOCAL_MANUAL',dict(r['dados'],x=999),uid=uid,esperada=h);self.assertNotEqual(c['uid'],lm.casos(self.base,self.p)[0]['uid'])
    def test_resultado_sem_responsavel(self):
        self.criar();c=lm.casos(self.base,self.p)[0];op.salvar(self.base,self.p,c,'ESTRUTURAL',resultado='MANTER CONFIGURAÇÃO ATUAL');self.assertEqual(op.indice(self.base,self.ig)[(c['uid'],'ESTRUTURAL')]['resultado'],'MANTER CONFIGURAÇÃO ATUAL')
    def test_reconciliacao_identica(self):
        v=st.vinculo_wg(self.p,self.wg());st.salvar(self.base,self.p,'LOCAL_MANUAL',dict(x=1,y=2,crs='EPSG:31983'),[v]);self.assertEqual(st.reconciliar(self.atual(),self.p)[0]['situacao'],'IDENTICO')
    def test_reconciliacao_alterada(self):
        i=self.wg();v=st.vinculo_wg(self.p,i);st.salvar(self.base,self.p,'LOCAL_MANUAL',dict(x=1,y=2,crs='EPSG:31983'),[v]);self.p['topologia']['modelo']['elementos'][i]['label']='alterado';self.assertEqual(st.reconciliar(self.atual(),self.p)[0]['situacao'],'ALTERADO')
    def test_reconciliacao_ausente(self):
        i=self.wg();v=st.vinculo_wg(self.p,i);st.salvar(self.base,self.p,'LOCAL_MANUAL',dict(x=1,y=2,crs='EPSG:31983'),[v]);del self.p['topologia']['modelo']['elementos'][i];self.assertEqual(st.reconciliar(self.atual(),self.p)[0]['situacao'],'AUSENTE')
    def test_fk(self):
        self.criar()
        with sqlite3.connect(self.base) as c:self.assertEqual(c.execute('pragma foreign_key_check').fetchall(),[])
    def test_reabrir(self):
        self.criar();from auditoria_topologica_watergems.saidas_integracao import reabrir
        p=reabrir(self.base);self.assertEqual(len(lm.casos(self.base,p)),1)
    def test_exportacao_label_texto(self):
        i=self.wg();self.p['topologia']['modelo']['elementos'][i]['label']='0012';v=st.vinculo_wg(self.p,i);uid,h=st.salvar(self.base,self.p,'REDE_PRINCIPAL',dict(nome='Teste'),[v]);r=st.atuais(self.base,self.p,'REDE_PRINCIPAL')[0];arquivo=rp.exportar_csv(self.dir/'lista.csv',self.p,r)
        with arquivo.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f));self.assertEqual(rows[0]['Label'],'0012');self.assertEqual(rows[0]['DomainElementID'],str(i))
    def test_nao_sobrescreve_csv(self):
        i=self.wg();st.salvar(self.base,self.p,'REDE_PRINCIPAL',dict(nome='Teste'),[st.vinculo_wg(self.p,i)]);r=st.atuais(self.base,self.p)[0];rp.exportar_csv(self.dir/'l.csv',self.p,r)
        with self.assertRaises(FileExistsError):rp.exportar_csv(self.dir/'l.csv',self.p,r)
    def test_conjunto_nome_obrigatorio(self):
        with self.assertRaises(ValueError):st.salvar(self.base,self.p,'REDE_PRINCIPAL',dict(nome=' '))
    def test_conjuntos_nao_sobrescrevem(self):
        st.salvar(self.base,self.p,'REDE_PRINCIPAL',dict(nome='A'));st.salvar(self.base,self.p,'REDE_PRINCIPAL',dict(nome='A'));self.assertEqual(len(st.atuais(self.base,self.p)),2)
    def test_comparar(self):
        a=dict(vinculos=[st.vinculo_wg(self.p,self.wg())],topo_uid='a');b=dict(vinculos=[],topo_uid='a');self.assertEqual(len(st.comparar_conjuntos(a,b)['removidos']),1)
    def test_cancelamento(self):
        with self.assertRaises(InterruptedError):rp.identificar(self.p,metodo='TOPOLOGICO',cancelado=lambda:True)
    def test_filtro_cadastral(self):
        i=self.wg();e=self.p['topologia']['modelo']['elementos'][i];cond=dict(camada='WG:'+e['tipo'],campo=['label'],operador='IGUAL',valor=e['label']);r=rp.identificar(self.p,condicao=cond);self.assertIn(str(i),r['criterios'])
    def test_campo_ausente_nao_seleciona(self):
        r=rp.identificar(self.p,condicao=dict(camada='WG:IdahoPipe',campo=['Inexistente'],operador='NULO'));self.assertEqual(r['elementos'],[])
    def test_cadastro_sem_condicao(self):
        with self.assertRaises(ValueError):rp.identificar(self.p)
    def test_grafo_nao_muda(self):
        g=self.p['topologia']['estrutural']['grafo'];arestas=list(g.edges(keys=True,data=True));rp.identificar(self.p,metodo='TOPOLOGICO');self.assertEqual(arestas,list(g.edges(keys=True,data=True)))
    def test_ui_origem_manual(self):
        self.criar();j=fixture.DecisoesTest.painel(self);j.origem_filtro.setCurrentIndex(2);self.assertEqual(len(j.visiveis),1);self.assertEqual(j.visiveis[0]['tipo'],'MANUAL')
    def test_ui_sem_duplicacao(self):
        self.criar();j=fixture.DecisoesTest.painel(self);j.recarregar_manuais();j.recarregar_manuais();self.assertEqual(sum(c['tipo']=='MANUAL' for c in j.casos),1)
    def test_vincular_regiao_sem_prova_de_pertencimento(self):
        a=next(iter(ContextoFiltros(self.p).areas));v=dict(origem='AREA',chave=a,natureza='MANUAL',dados=dict(exibicao='Área de teste'))
        st.salvar(self.base,self.p,'LOCAL_MANUAL',dict(x=1,y=2,crs='EPSG:31983'),[v]);c=lm.casos(self.base,self.p,ContextoFiltros(self.p))[0];self.assertIn(a,c['area_uids']);self.assertIsNone(c['local_uid'])
    def test_exporta_novas_tabelas(self):
        self.criar();from auditoria_topologica_watergems.exportacao_decisoes import tabelas_decisoes
        ts=tabelas_decisoes(self.base,self.p);self.assertEqual(len(ts['LOCAIS_MANUAIS'][1]),1);self.assertIn('CONJUNTOS_REDES',ts)
    def test_exporta_elemento_alterado_bloqueado(self):
        i=self.wg();st.salvar(self.base,self.p,'REDE_PRINCIPAL',dict(nome='Teste'),[st.vinculo_wg(self.p,i)]);r=st.atuais(self.base,self.p)[0];self.p['topologia']['modelo']['elementos'][i]['uid']='outra_identidade'
        with self.assertRaises(ValueError):rp.exportar_csv(self.dir/'l.csv',self.p,r)
        self.assertFalse((self.dir/'l.csv').exists())
    def test_exportacao_labels_repetidos_avisados(self):
        i=self.wg();e=self.p['topologia']['modelo']['elementos'][i];outro=next(x for x,t in self.p['topologia']['modelo']['elementos'].items() if x!=i and t['familia']=='LINK');self.p['topologia']['modelo']['elementos'][outro]['label']=e['label'];st.salvar(self.base,self.p,'REDE_PRINCIPAL',dict(nome='Teste'),[st.vinculo_wg(self.p,i)]);rp.exportar_csv(self.dir/'l.csv',self.p,st.atuais(self.base,self.p)[0]);self.assertIn('LABEL_REPETIDO',(self.dir/'l.csv').read_text(encoding='utf-8-sig'))
    def test_migracao_rollback(self):
        self.criar();r=self.atual()
        with patch.object(st.db,'texto',side_effect=RuntimeError('interrupção')):
            with self.assertRaises(RuntimeError):st.salvar(self.base,self.p,'LOCAL_MANUAL',r['dados'],uid=r['obj_uid'],esperada=r['uid'])
        self.assertEqual(len(st.historico(self.base,self.p)),1)
    def test_formulario_local_sem_campos_burocraticos(self):
        self.criar();j=fixture.DecisoesTest.painel(self);from auditoria_topologica_watergems.ferramentas_investigacao_ui import DialogoLocal
        d=DialogoLocal(j,dict(x=1,y=2,crs='EPSG:31983'));self.assertEqual(d.titulo.text(),'');self.assertFalse(hasattr(d,'responsavel'));d.reject()
    def test_dialogo_redes_cancelar_preserva(self):
        j=fixture.DecisoesTest.painel(self);from auditoria_topologica_watergems.ferramentas_investigacao_ui import DialogoRedes
        from qgis.PyQt.QtWidgets import QMessageBox
        d=DialogoRedes(j);d.preencher([st.vinculo_wg(self.p,self.wg())]);self.assertTrue(d.tem_edicoes())
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel):self.assertFalse(d.resolver());self.assertEqual(len(d.escolhidos()),1)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Discard):d.close()
    def test_salvar_conjunto_atualiza_baseline(self):
        j=fixture.DecisoesTest.painel(self);from auditoria_topologica_watergems.ferramentas_investigacao_ui import DialogoRedes
        d=DialogoRedes(j);d.preencher([st.vinculo_wg(self.p,self.wg())]);self.assertTrue(d.salvar());self.assertFalse(d.tem_edicoes());self.assertEqual(d.escolhidos(),d.registro['vinculos']);d.close()
    def test_metodo_combinado_e(self):
        i=self.wg();e=self.p['topologia']['modelo']['elementos'][i];cond=dict(camada='WG:'+e['tipo'],campo=['label'],operador='IGUAL',valor=e['label']);a=rp.identificar(self.p,condicao=cond);b=rp.identificar(self.p,metodo='TOPOLOGICO');c=rp.identificar(self.p,metodo='COMBINADO',condicao=cond,combinacao='E');self.assertEqual(set(c['criterios']),set(a['criterios'])&set(b['criterios']))
    def test_metodo_combinado_ou(self):
        i=self.wg();e=self.p['topologia']['modelo']['elementos'][i];cond=dict(camada='WG:'+e['tipo'],campo=['label'],operador='IGUAL',valor=e['label']);a=rp.identificar(self.p,condicao=cond);b=rp.identificar(self.p,metodo='TOPOLOGICO');c=rp.identificar(self.p,metodo='COMBINADO',condicao=cond);self.assertEqual(set(c['criterios']),set(a['criterios'])|set(b['criterios']))
    def destino(self):
        import shutil
        destino=self.dir/'destino.gpkg';shutil.copyfile(self.original,destino);return destino
    def test_importar_preserva_uuid_sem_conclusao(self):
        uid,h=self.criar();c=lm.casos(self.base,self.p)[0];op.salvar(self.base,self.p,c,'ESTRUTURAL',resultado='MANTER CONFIGURAÇÃO ATUAL');destino=self.destino();st.importar(self.base,self.p,destino,self.p);rs=st.atuais(destino,self.p,'LOCAL_MANUAL');self.assertEqual(rs[0]['obj_uid'],uid);self.assertTrue(rs[0]['dados']['reavaliacao']);self.assertFalse(op.historico(destino,self.ig))
    def test_importar_idempotente(self):
        self.criar();d=self.destino();st.importar(self.base,self.p,d,self.p);r=st.importar(self.base,self.p,d,self.p);self.assertEqual(r['importados'],0);self.assertEqual(len(st.atuais(d,self.p)),1)
    def test_importar_historia_preservada(self):
        uid,h=self.criar();st.salvar(self.base,self.p,'LOCAL_MANUAL',dict(self.atual()['dados'],titulo='Revisado'),uid=uid,esperada=h);d=self.destino();st.importar(self.base,self.p,d,self.p);self.assertEqual(len(st.atuais(d,self.p)[0]['dados']['historico_origem']),2)
    def test_importar_elemento_ausente_nao_associa(self):
        i=self.wg();st.salvar(self.base,self.p,'LOCAL_MANUAL',dict(x=1,y=2,crs='EPSG:31983'),[st.vinculo_wg(self.p,i)]);nova=fixture.clonar(self.p);del nova['topologia']['modelo']['elementos'][i];d=self.destino();r=st.importar(self.base,self.p,d,nova);self.assertEqual(r['vinculos_pendentes'],1);self.assertEqual(lm.casos(d,nova)[0]['wg_ids'],[])
    def test_importar_falha_destino_sem_objetos_parciais(self):
        self.criar();d=self.destino()
        with patch.object(st,'_importar',side_effect=RuntimeError('falha')):
            with self.assertRaises(RuntimeError):st.importar(self.base,self.p,d,self.p)
        self.assertEqual(st.atuais(d,self.p),[]);self.assertFalse(list(self.dir.glob('*_importacao_*.gpkg')))
    def test_importar_mesma_execucao_nao_duplica(self):
        self.criar();r=st.importar(self.base,self.p,self.base,self.p);self.assertEqual(r['importados'],0);self.assertEqual(len(st.atuais(self.base,self.p)),1)
    def test_exportacao_texto_longo_reconstituivel(self):
        from auditoria_topologica_watergems.exportacao_decisoes import tabelas_decisoes
        st.salvar(self.base,self.p,'REDE_PRINCIPAL',dict(nome='Teste',criterios='x'*90000));t=tabelas_decisoes(self.base,self.p);ps=t['DADOS_OBJETOS_PARTES'][1];self.assertGreater(len(ps),1);self.assertTrue(all(len(r[-1])<=30000 for r in ps));self.assertEqual(json.loads(''.join(r[-1] for r in ps))['criterios'],'x'*90000)
    def test_gpkg_camada_manual_reimportada(self):
        from qgis.core import QgsVectorLayer
        uid,h=self.criar();c=QgsVectorLayer(str(self.base)+'|layername=IG_MANUAIS_ATUAIS','Manuais','ogr');self.assertTrue(c.isValid());self.assertEqual(c.featureCount(),1);f=next(c.getFeatures());self.assertEqual(f['obj_uid'],uid);self.assertAlmostEqual(f.geometry().asPoint().x(),123.123456789,places=8)
    def test_gpkg_exclusao_nao_apaga_geometria(self):
        uid,h=self.criar();st.salvar(self.base,self.p,'LOCAL_MANUAL',self.atual()['dados'],uid=uid,esperada=h,excluido=True)
        with sqlite3.connect(self.base) as c:self.assertEqual(c.execute('select count(*) from IG_MANUAIS_ATUAIS').fetchone()[0],0);self.assertEqual(c.execute('select count(*) from IGD_MANUAL_GEOM').fetchone()[0],2)
    def test_revisao_espacial_nao_remove_manuais(self):
        self.criar();j=fixture.DecisoesTest.painel(self);j.revisao_atualizada();self.assertEqual(sum(c['tipo']=='MANUAL' for c in j.casos),1)


class GrafoControladoTest(unittest.TestCase):
    def pacote(self,arestas):
        g=nx.MultiDiGraph();el={}
        for i,a,b in arestas:
            el[i]=dict(uid=str(i),id=i,label=str(i),tipo='IdahoPipe',familia='LINK',excluido=False,ativo=True)
            for x,y in ((a,b),(b,a)):g.add_edge((x,'E'),(y,'E'),key=('tubo',i),natureza='TUBULACAO',elemento=i)
        return dict(topologia=dict(modelo=dict(elementos=el),estrutural=dict(grafo=g),potencial=dict(grafo=g)))
    def test_ramificacao_pontes(self):self.assertEqual(len(rp.identificar(self.pacote([(10,1,2),(11,2,3)]),metodo='TOPOLOGICO')['elementos']),2)
    def test_malha_sem_pontes(self):self.assertEqual(rp.identificar(self.pacote([(10,1,2),(11,2,3),(12,3,1)]),metodo='TOPOLOGICO')['elementos'],[])
    def test_paralelas_nao_sao_pontes(self):self.assertEqual(rp.identificar(self.pacote([(10,1,2),(11,1,2)]),metodo='TOPOLOGICO')['elementos'],[])
    def test_laco_nao_e_ponte(self):self.assertEqual(rp.identificar(self.pacote([(10,1,1)]),metodo='TOPOLOGICO')['elementos'],[])
    def test_escopo_explicito(self):
        r=rp.identificar(self.pacote([(10,1,2),(11,2,3),(12,3,1)]),metodo='TOPOLOGICO',escopo=[10,11]);self.assertEqual(len(r['elementos']),2);self.assertEqual(r['escopo'],[10,11])
    def test_escopo_invalido(self):
        with self.assertRaises(ValueError):rp.identificar(self.pacote([(10,1,2)]),metodo='TOPOLOGICO',escopo=[999])
    def test_progresso_sem_percentual_falso(self):
        passos=[];rp.identificar(self.pacote([(10,1,2)]),metodo='TOPOLOGICO',progresso=lambda *a:passos.append(a));self.assertTrue(passos);self.assertTrue(all(p[1] is None for p in passos))
    def fonte(self):
        p=self.pacote([(10,1,2),(11,2,3)]);p['topologia']['modelo']['elementos'][1]=dict(uid='n1',label='Fonte',tipo='IdahoReservoir',familia='NO',excluido=False,ativo=True);return p
    def test_corredor_dirigido(self):
        r=rp.identificar(self.fonte(),metodo='TOPOLOGICO',pontes=False,origens=[1],destinos=[3]);self.assertEqual(set(r['criterios']),{'10','11'})
    def test_barreira_bloqueada_nao_cria_caminho(self):
        p=self.fonte();g=p['topologia']['potencial']['grafo'];g.remove_edge((2,'E'),(3,'E'),('tubo',11));r=rp.identificar(p,modo='TODAS_VALVULAS_ABERTAS',metodo='TOPOLOGICO',pontes=False,origens=[1],destinos=[3]);self.assertEqual(r['elementos'],[])
    def test_bomba_nao_e_fonte(self):
        p=self.fonte();p['topologia']['modelo']['elementos'][1]['tipo']='StandardPump'
        with self.assertRaises(ValueError):rp.identificar(p,metodo='TOPOLOGICO',origens=[1],destinos=[3])


if __name__=='__main__':unittest.main()
