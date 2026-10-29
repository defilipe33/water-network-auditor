"""Selection Sets sintéticos: IDs, pastas, compatibilidade e persistência."""
import copy,json,sqlite3,struct,tempfile,unittest
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
from test_auditoria_fronteiras import APP
from test_topologia_watergems import criar_banco
from auditoria_topologica_watergems import selection_sets as ss,selection_sets_persistencia as store,conjuntos_investigacao as obj
from auditoria_topologica_watergems.arquivos import hash_arquivo
from qgis.core import QgsProject


@contextmanager
def conexao(path):
    c=sqlite3.connect(path)
    try:
        with c:yield c
    finally:c.close()


class LeitorTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'m.sqlite';criar_banco(self.path)
        with conexao(self.path) as c:
            c.execute('CREATE TABLE HMISelectionSet(SelectionSetID INTEGER,SelectionSetType INTEGER,IsDeleted INTEGER,SelectionSetCount INTEGER,SelectionSetElementIDs BLOB,ParentID INTEGER,SelectionSetElementType INTEGER)')
            c.executemany('INSERT INTO HMISelectionSet VALUES(?,1,0,?,?,?,?)',[(1000,0,None,0,1),(1001,0,None,1000,1),(1002,2,struct.pack('<II',1,2),1001,0),(1003,0,None,0,0)])
            c.executemany('INSERT INTO HMIModelingElement VALUES(?,0,?)',[(1000,'Pasta repetida'),(1001,'Pasta repetida'),(1002,'Rede 001'),(1003,'Rede 001'),(1,'001'),(2,'001')]);c.executemany('INSERT INTO HMIDomainElement VALUES(?,0,0)',[(1,),(2,)])
    def tearDown(self):self.tmp.cleanup()
    def ler(self):return ss.ler(self.path)
    def test_uint32_little_endian(self):self.assertEqual(ss.decodificar(struct.pack('<II',1,4000000000),2),[1,4000000000])
    def test_blob_invalido(self):
        with self.assertRaises(ValueError):ss.decodificar(b'x',1)
    def test_contagem_divergente(self):
        with self.assertRaises(ValueError):ss.decodificar(b'\x00'*4,2)
    def test_nulo_nao_apaga_membros_declarados(self):
        with self.assertRaises(ValueError):ss.decodificar(None,1)
    def test_vazio(self):self.assertEqual(ss.decodificar(None,0),[])
    def test_pastas_aninhadas(self):r=self.ler();self.assertEqual(next(x for x in r['itens'] if x['id']==1002)['ancestrais'],[1000,1001])
    def test_nomes_iguais_ids_distintos(self):self.assertEqual(len({x['id'] for x in self.ler()['itens']}),4)
    def test_labels_repetidos_nao_sao_chave(self):r=next(x for x in self.ler()['itens'] if x['id']==1002);self.assertEqual([x['id'] for x in r['membros']],[1,2]);self.assertEqual([x['label'] for x in r['membros']],['001','001'])
    def test_hierarquia_ciclica_sinalizada(self):
        with conexao(self.path) as c:c.execute('UPDATE HMISelectionSet SET ParentID=1001 WHERE SelectionSetID=1000')
        self.assertTrue(any(x['hierarquia']=='CICLO' for x in self.ler()['itens']))
    def test_pasta_ausente_nao_inventada(self):
        with conexao(self.path) as c:c.execute('UPDATE HMISelectionSet SET ParentID=9999 WHERE SelectionSetID=1002')
        self.assertEqual(next(x for x in self.ler()['itens'] if x['id']==1002)['hierarquia'],'PASTA_AUSENTE_OU_INCOMPATIVEL')
    def test_membros_ausentes_preservados(self):
        with conexao(self.path) as c:c.execute('DELETE FROM HMIDomainElement WHERE DomainElementID=2')
        self.assertEqual(next(x for x in self.ler()['itens'] if x['id']==1002)['membros'][1]['situacao'],'AUSENTE')
    def test_excluidos_preservados(self):
        with conexao(self.path) as c:c.execute('UPDATE HMIDomainElement SET IsDeleted=1 WHERE DomainElementID=2')
        self.assertEqual(next(x for x in self.ler()['itens'] if x['id']==1002)['membros'][1]['situacao'],'EXCLUIDO')
    def test_dinamico_nao_avalia_query(self):
        with conexao(self.path) as c:c.execute('UPDATE HMISelectionSet SET SelectionSetType=99 WHERE SelectionSetID=1002')
        r=next(x for x in self.ler()['itens'] if x['id']==1002);self.assertEqual(r['membros'],[]);self.assertEqual(r['situacao'],'COMPOSICAO_NAO_VERIFICADA')
    def test_somente_leitura(self):h=hash_arquivo(self.path);self.ler();self.assertEqual(hash_arquivo(self.path),h)
    def test_cancelamento(self):
        with self.assertRaises(InterruptedError):ss.ler(self.path,cancelado=lambda:True)
    def test_tipo_pasta_diferente_de_conjunto_vazio(self):r=self.ler();self.assertTrue(r['itens'][0]['pasta']);self.assertFalse(r['itens'][-1]['pasta'])
    def test_hierarquia_nao_recuperavel(self):
        with conexao(self.path) as c:c.execute('ALTER TABLE HMISelectionSet RENAME COLUMN ParentID TO RelacaoDesconhecida')
        self.assertEqual(self.ler()['hierarquia'],'NAO_RECUPERADA')

    def test_confronto_opcional_com_composer(self):
        import sys,importlib.util
        raiz=Path(__file__).resolve().parents[1]/'referencias_codigo/model-builder-composer'
        if not raiz.exists():self.skipTest('Referência externa não distribuída com o WNA')
        sys.path.insert(0,str(raiz))
        try:
            from repository.selection_sets import WaterGemsSelectionSetRepository
            from database.schema import SchemaInspector
            class DB:
                def __init__(self,path):self.c=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True);self.c.row_factory=sqlite3.Row
                def fetchone(self,q,params=()):return self.c.execute(q,params).fetchone()
                def fetchall(self,q,params=()):return self.c.execute(q,params).fetchall()
            db=DB(self.path)
            try:
                r=WaterGemsSelectionSetRepository(db,SchemaInspector(db));novo=self.ler();self.assertEqual([(x['id'],x['name']) for x in r.list_sets()],[(x['id'],x['nome']) for x in novo['itens']]);self.assertEqual(r.member_ids(1002),[m['id'] for m in novo['itens'][2]['membros']])
            finally:db.c.close()
        finally:sys.path.remove(str(raiz))

    def test_ids_repetidos_preservam_sequencia_bruta(self):
        with conexao(self.path) as c:c.execute('UPDATE HMISelectionSet SET SelectionSetCount=3,SelectionSetElementIDs=? WHERE SelectionSetID=1002',(struct.pack('<III',1,2,1),))
        r=next(x for x in self.ler()['itens'] if x['id']==1002);self.assertEqual(r['ids_brutos'],[1,2,1]);self.assertEqual(r['duplicados'],1);self.assertEqual(len(r['membros']),2)

    def test_snapshot_considera_wal_comprometido(self):
        with conexao(self.path) as c:
            c.execute('PRAGMA journal_mode=WAL');c.execute("UPDATE HMIModelingElement SET Label='Nome no WAL' WHERE ElementID=1002");c.commit();r=self.ler();self.assertEqual(next(x for x in r['itens'] if x['id']==1002)['nome'],'Nome no WAL');self.assertIn('backup API',r['snapshot']['metodo'])


import test_decisoes_topologicas as fixture
class ImportacaoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.DecisoesTest.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):fixture.DecisoesTest.tearDownClass.__func__(cls)
    def setUp(self):fixture.DecisoesTest.setUp(self);self.r=self.leitura()
    def tearDown(self):QgsProject.instance().removeAllMapLayers();fixture.DecisoesTest.tearDown(self)
    def leitura(self):
        el=self.p['topologia']['modelo']['elementos'];m=[dict(id=i,uid=e['uid'],tipo=e['tipo'],label=e['label'],firma=ss.firma_elemento(e),excluido=False,situacao='PRESENTE') for i,e in el.items() if e['excluido'] is False]
        return dict(regra='sintetico',modelo=self.p['topologia']['modelo']['projeto'],assinatura='sintetica-1',cenario=self.p['topologia']['modelo']['cenario'],alternativas={},data='2026-01-01',hierarquia='RECUPERADA',itens=[dict(id=70,nome='Pasta',pasta=True,pai=0,ancestrais=[],hierarquia='RECUPERADA',tipo='PASTA',quantidade=0,membros=[],situacao='PASTA',definicao={}),dict(id=71,nome='Rede 001',pasta=False,pai=70,ancestrais=[70],hierarquia='RECUPERADA',tipo='ESTATICO',quantidade=len(m),membros=m,situacao='MEMBROS_EXPLICITOS',definicao={})])
    def salvar(self):return store.importar(self.base,self.p,self.r,[71])
    def test_salvar_reabrir(self):self.salvar();self.assertEqual(store.atuais(self.base,self.p)[0]['dados']['id'],71)
    def test_pastas_no_snapshot(self):self.salvar();self.assertTrue(store.ultima(self.base,self.p)['itens'][0]['pasta'])
    def test_vinculos_multiplos_tipos(self):self.salvar();self.assertGreater(len({v['dados']['tipo'] for v in store.atuais(self.base,self.p)[0]['vinculos']}),1)
    def test_identidade_estavel(self):self.assertEqual(store.identidade(self.p,'m',71),store.identidade(self.p,'m',71))
    def test_outro_modelo_bloqueado(self):
        self.r['modelo']='outro'
        with self.assertRaises(ValueError):self.salvar()
    def test_versao_incompativel_preserva_referencia(self):self.r['itens'][1]['membros'][0]['firma']='outra';self.salvar();d=store.atuais(self.base,self.p)[0]['dados'];self.assertEqual(d['membros'][0]['situacao'],'INCOMPATIVEL_COM_VERSAO_TOPOLOGICA')
    def test_cancelamento_nao_publica(self):
        with self.assertRaises(InterruptedError):store.importar(self.base,self.p,self.r,[71],lambda:True)
        self.assertEqual(store.atuais(self.base,self.p),[])
    def test_mesma_importacao_sem_revisao_duplicada(self):self.salvar();n=len(obj.historico(self.base,self.p));self.salvar();self.assertEqual(len(obj.historico(self.base,self.p)),n)
    def test_renomear_mover_detectado(self):a=copy.deepcopy(self.r);self.r['itens'][1].update(nome='Outro',pai=0);c=ss.comparar(a,self.r);self.assertEqual(c['linhas'][1]['mudancas'],['RENOMEADO','MOVIDO'])
    def test_historico_atualizacao(self):self.salvar();self.r['assinatura']='sintetica-2';self.r['itens'][1]['nome']='Novo';self.salvar();self.assertEqual(len(obj.historico(self.base,self.p,'SELECTION_SET_WG')),2)
    def test_removido_preserva_historico(self):self.salvar();self.r['assinatura']='sintetica-2';self.r['itens']=self.r['itens'][:1];store.importar(self.base,self.p,self.r,[]);self.assertEqual(store.atuais(self.base,self.p),[]);self.assertTrue(obj.historico(self.base,self.p,'SELECTION_SET_WG'))
    def test_comparacao_sobreposicao_nao_e_erro(self):self.salvar();rs=store.atuais(self.base,self.p);c=store.comparar_conjuntos(rs,rs);self.assertTrue(c['comuns']);self.assertFalse(c['somente_a'])
    def test_filtro_identidade(self):self.salvar();self.assertEqual(store.escopo(self.base,self.p,[71]),{m['id'] for m in self.r['itens'][1]['membros']})
    def test_backup_existe(self):self.salvar();self.assertTrue(list(self.dir.glob('*antes_conjuntos*.gpkg')))
    def test_fk_integras(self):
        self.salvar()
        with conexao(self.base) as c:self.assertFalse(c.execute('pragma foreign_key_check').fetchall())
    def test_base_legada_nao_migra_leitura(self):h=hash_arquivo(self.base);self.assertEqual(store.atuais(self.base,self.p),[]);self.assertEqual(hash_arquivo(self.base),h)
    def test_mapa_crs_pendente(self):
        from auditoria_topologica_watergems.selection_sets_mapa import camadas
        self.salvar();self.p['resultado']['meta']['parametros']['espacial_habilitado']=False
        with self.assertRaises(ValueError):camadas(self.base,self.p,self.dir/'camadas',[71])
    def test_camadas_persistentes_reabertura_sem_duplicar(self):
        from auditoria_topologica_watergems.selection_sets_mapa import camadas,carregar
        self.salvar();m=camadas(self.base,self.p,self.dir/'camadas',[71]);ls=carregar(self.p,m);self.assertTrue(ls);ids={l.id() for l in ls};self.assertEqual(ids,{l.id() for l in carregar(self.p,m)});self.assertTrue(all(l.providerType()=='ogr' for l in ls))
    def test_simbolos_e_selecoes_preservados(self):
        from auditoria_topologica_watergems.selection_sets_mapa import camadas,carregar
        self.salvar();m=camadas(self.base,self.p,self.dir/'camadas',[71]);l=carregar(self.p,m)[0];l.selectAll();qml=l.renderer().dump();carregar(self.p,m);self.assertEqual(l.renderer().dump(),qml);self.assertTrue(l.selectedFeatureCount())
    def test_interface_arvore_recupera_importacao(self):self.salvar();j=fixture.DecisoesTest.painel(self);j.abrir_selection_sets();d=j._selection_sets_ui;self.assertEqual(d.arvore.topLevelItemCount(),1);d.close()
    def test_relatorio_pelo_renderizador_existente(self):
        from auditoria_topologica_watergems.selection_sets_relatorio import gerar
        self.salvar();d=gerar(self.base,self.p,[71],self.dir/'reports');self.assertEqual(len(d['ocorrencias']),1)

    def test_pasta_vazia_persistida(self):self.r['itens']=self.r['itens'][:1];store.importar(self.base,self.p,self.r,[]);self.assertEqual(len(store.ultima(self.base,self.p)['itens']),1)
    def test_organizacao_local_qgis_nao_e_sobrescrita(self):
        from auditoria_topologica_watergems.selection_sets_mapa import camadas,carregar
        self.salvar();m=camadas(self.base,self.p,self.dir/'camadas',[71]);l=carregar(self.p,m)[0];root=QgsProject.instance().layerTreeRoot();local=root.addGroup('Organização de reunião');n=root.findLayer(l.id());local.addChildNode(n.clone());n.parent().removeChildNode(n);carregar(self.p,m);self.assertEqual(root.findLayer(l.id()).parent().name(),'Organização de reunião')
    def test_geometria_ausente_nao_e_inventada(self):
        from auditoria_topologica_watergems.selection_sets_mapa import camadas
        self.salvar();self.p['geometrias']={};m=camadas(self.base,self.p,self.dir/'camadas',[71]);self.assertEqual(m['camadas'],[])
    def test_importacao_csv_identidade_modelo_obrigatoria(self):
        from auditoria_topologica_watergems.selection_sets_alternativa import ler_csv
        f=self.dir/'lista.csv';f.write_text('DomainElementID,Tipo,Modelo\n1,IdahoJunction,outro\n',encoding='utf8')
        with self.assertRaises(ValueError):ler_csv(f,self.p,'Lista')
    def test_importacao_csv_label_nao_e_chave(self):
        from auditoria_topologica_watergems.selection_sets_alternativa import ler_csv
        i,e=next(iter(self.p['topologia']['modelo']['elementos'].items()));f=self.dir/'lista.csv';f.write_text('DomainElementID,Tipo,Modelo,Label\n'+str(i)+','+e['tipo']+','+self.p['topologia']['modelo']['projeto']+',00001\n',encoding='utf8');r=ler_csv(f,self.p,'Lista');self.assertEqual(r['itens'][0]['membros'][0]['label'],'00001');self.assertEqual(r['hierarquia'],'NAO_RECUPERADA')
    def test_arquivo_shp_campos_compativeis(self):
        from auditoria_topologica_watergems.selection_sets_mapa import camadas
        self.salvar();camadas(self.base,self.p,self.dir/'shps',[71],shp=True);self.assertTrue(list((self.dir/'shps').glob('*.prj')))
    def test_concorrencia_impede_publicacao_parcial(self):
        real=obj.salvar;alterado=[]
        def concorrente(base,*a,**kw):
            x=real(base,*a,**kw)
            if Path(base)!=self.base and not alterado:
                alterado.append(True);real(self.base,self.p,'REDE_PRINCIPAL',{'nome':'Gravação de outra sessão'})
            return x
        with patch.object(obj,'salvar',side_effect=concorrente):
            with self.assertRaisesRegex(ValueError,'Outra sessão'):self.salvar()
        self.assertEqual(store.atuais(self.base,self.p),[])

    def test_atualizacao_nome_pasta_sem_duplicar_grupo(self):
        from auditoria_topologica_watergems.selection_sets_mapa import camadas,carregar
        self.salvar();m=camadas(self.base,self.p,self.dir/'camadas',[71]);carregar(self.p,m);m['importacao']['itens'][0]['nome']='Renomeada';carregar(self.p,m);groups=QgsProject.instance().layerTreeRoot().findGroups(True);self.assertEqual(sum(g.customProperty('ss/pasta_id')==70 for g in groups),1);self.assertTrue(any(g.name()=='Renomeada' for g in groups))
    def test_csv_nao_remove_conjuntos_nativos(self):
        self.salvar();r=copy.deepcopy(self.r);r['assinatura']='csv';r['regra']='lista-csv-1';r['itens']=r['itens'][1:];r['itens'][0].update(id='CSV:1',pai=None,ancestrais=[],definicao={'origem':'CSV_EXTERNO'});store.importar(self.base,self.p,r,['CSV:1']);self.assertEqual(len(store.atuais(self.base,self.p)),2)
    def test_cancelamento_representacao_nao_publica(self):
        from auditoria_topologica_watergems.selection_sets_mapa import camadas
        self.salvar()
        with self.assertRaises(InterruptedError):camadas(self.base,self.p,self.dir/'camadas',[71],cancelado=lambda:True)
    def test_qgz_reabre_estilo_e_identidade(self):
        from auditoria_topologica_watergems.selection_sets_mapa import camadas,carregar
        self.salvar();m=camadas(self.base,self.p,self.dir/'camadas',[71]);ls=carregar(self.p,m);ids={l.id() for l in ls};projeto=QgsProject.instance();p=self.dir/'teste.qgz';self.assertTrue(projeto.write(str(p)));projeto.clear();self.assertTrue(projeto.read(str(p)));self.assertEqual(ids,{l.id() for l in carregar(self.p,m)})

    def test_opcoes_relatorio_reutilizam_dialogo_existente(self):
        from qgis.PyQt.QtCore import Qt
        self.salvar();j=fixture.DecisoesTest.painel(self);j.abrir_selection_sets();d=j._selection_sets_ui;d.arvore.topLevelItem(0).setCheckState(0,Qt.Checked);d.opcoes_relatorio();self.assertIsNotNone(d._relatorio);self.assertEqual(len(d._relatorio.painel.casos),1);d._relatorio.close();d.close()

    def test_comparacao_versoes_persiste_no_historico_existente(self):
        self.salvar();r=store.comparar_versoes(self.base,self.p,self.base,self.p)
        with conexao(self.base) as c:self.assertEqual(c.execute('SELECT count(*) FROM IGD_COMPARACOES WHERE comp_uid=?',(r['uid'],)).fetchone()[0],1)


if __name__=='__main__':unittest.main()
