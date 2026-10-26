"""Persistência completa, snapshots WAL, versões e organização do complemento."""
import copy
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from test_auditoria_fronteiras import APP
from test_topologia_watergems import criar_banco,modelo
from auditoria_topologica_watergems import bases
from auditoria_topologica_watergems.arquivos import hash_arquivo
from auditoria_topologica_watergems.gerenciamento import Catalogo,identificar,sugestao
from empacotar_plugin import empacotar


def banco_nativo(p):
    criar_banco(p);m=modelo()
    with sqlite3.connect(p) as c:
        for tabela,ids in [('BaseLink',[10,11]),('BaseIdahoNode',[1,3]),('BaseDirectedNode',[2])]:
            c.execute(f'create table {tabela}(DomainElementID integer)')
            c.executemany(f'insert into {tabela} values(?)',[(i,) for i in ids])
            c.execute(f'create table {tabela}_HmiDataSetGeometry_Data(DomainElementID integer,AlternativeID integer,HMIGeometry blob)')
            c.executemany(f'insert into {tabela}_HmiDataSetGeometry_Data values(?,?,?)',[(i,20,m['elementos'][i]['geometria']) for i in ids])
            c.execute(f'create table {tabela}_HMIActiveTopology_Data(DomainElementID integer,AlternativeID integer,HMIActiveTopologyIsActive integer)')
            c.executemany(f'insert into {tabela}_HMIActiveTopology_Data values(?,?,1)',[(i,30) for i in ids])
        for tipo,ids in [('IdahoPipe',[10,11]),('IdahoJunction',[1,3]),('CheckValve',[2])]:
            c.execute(f'create table {tipo}(DomainElementID integer)');c.executemany(f'insert into {tipo} values(?)',[(i,) for i in ids])
        c.executemany('insert into HMIDomainElement values(?,0,0)',[(i,) for i in m['elementos']])
        c.executemany('insert into HMIModelingElement values(?,0,?)',[(i,e['label']) for i,e in m['elementos'].items()])
        c.executescript('''insert into HMIAlternative values(20,NULL,1,0),(30,NULL,3,0);
            insert into HMIScenarioAlternative values(1,1,20),(1,3,30);
            insert into BaseLink_HMIDataSetTopology_Data values(10,10,1,2),(11,10,2,3);
            create table BaseDirectedNode_HMIDataSetTopology_Data(DomainElementID integer,AlternativeID integer,HMITopologyDownstreamLinkID integer);
            insert into BaseDirectedNode_HMIDataSetTopology_Data values(2,10,11);''')


class BasesTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True);self.p=Path(self.tmp.name)
        self.fonte=self.p/'modelo.wtg.sqlite';criar_banco(self.fonte);self.m=modelo()
        self.m['elementos'][10]['atributos']={'bruto':b'\x00\xff','id':'00017'}
        self.ref=dict(crs='EPSG:31983',fator=1,fonte='Ensaio sintético controlado')
    def tearDown(self):self.tmp.cleanup()
    def criar(self,nome='v1.gpkg',m=None,**kw):
        with patch.object(bases,'Banco') as b:
            b.return_value.ler.return_value=copy.deepcopy(m or self.m)
            return bases.criar(self.fonte,self.p/nome,nome='Modelo sintético',projeto='Projeto',referencia=self.ref,**kw)
    def test_cenarios_sem_extracao_completa(self):
        with patch.object(bases,'Banco',side_effect=AssertionError):
            cs,ativo=bases.cenarios_fonte(self.fonte)
        self.assertEqual([c['id'] for c in cs],[1,2]);self.assertEqual(ativo,2)
    def test_extracao_nativa_versao_atualizada_sem_mock(self):
        fonte=self.p/'controle.sqlite';banco_nativo(fonte)
        a=bases.criar(fonte,self.p/'controle_v001.gpkg',nome='Controle sintético',projeto='Teste',referencia=self.ref);h=hash_arquivo(a)
        with sqlite3.connect(fonte) as c:c.execute('update BaseDirectedNode_HMIActiveTopology_Data set HMIActiveTopologyIsActive=0 where DomainElementID=2')
        b=bases.criar(fonte,self.p/'controle_v002.gpkg',nome='Controle sintético',projeto='Teste',referencia=self.ref,anterior=a)
        self.assertEqual(bases.comparar(a,b)['alterados']['ativo'],[2]);self.assertEqual(hash_arquivo(a),h)
        self.assertEqual(bases.restaurar(a)['estrutural']['resumo']['conexoes'],2)
    def test_snapshot_wal_inclui_commit_sem_checkpoint(self):
        with sqlite3.connect(self.fonte) as c:
            c.execute('pragma journal_mode=WAL');c.execute('pragma wal_autocheckpoint=0');c.execute('create table prova(valor)');c.execute("insert into prova values('gravado')");c.commit()
            h=hash_arquivo(self.fonte);s=bases.snapshot(self.fonte,self.p/'snapshot.sqlite')
            with sqlite3.connect(s['snapshot']) as q:self.assertEqual(q.execute('select valor from prova').fetchone()[0],'gravado')
            self.assertEqual(hash_arquivo(self.fonte),h)
    def test_snapshot_rejeita_sobrescrita(self):
        with self.assertRaises(FileExistsError):bases.snapshot(self.fonte,self.fonte)
    def test_snapshot_cancelado(self):
        with self.assertRaises(InterruptedError):bases.snapshot(self.fonte,self.p/'cancel.sqlite',lambda:True)
    def test_snapshot_espaco_insuficiente(self):
        with patch.object(bases.shutil,'disk_usage') as d:
            d.return_value.free=1
            with self.assertRaises(ValueError):bases.snapshot(self.fonte,self.p/'sem_espaco.sqlite')
    def test_reabre_sem_fonte_preserva_brutos(self):
        f=self.criar();self.fonte.rename(self.p/'fonte_movida.sqlite');q=bases.restaurar(f)
        self.assertEqual(q['modelo']['elementos'],self.m['elementos']);self.assertEqual(q['estrutural']['resumo']['conexoes'],2)
        self.assertEqual(q['modelo']['elementos'][10]['atributos']['bruto'],b'\x00\xff')
    def test_metadados_e_paginacao_nao_reconstroem_grafo(self):
        f=self.criar()
        with patch.object(bases,'analisar',side_effect=AssertionError):
            self.assertTrue(bases.metadados(f)['uuid']);self.assertEqual(len(bases.elementos(f,2,1)),2)
    def test_paginacao_invalida(self):
        with self.assertRaises(ValueError):bases.elementos('ausente',1001)
    def test_integridade_e_ambas_perspectivas(self):
        f=self.criar()
        with sqlite3.connect(f) as c:
            self.assertEqual(c.execute('pragma integrity_check').fetchone()[0],'ok');self.assertFalse(c.execute('pragma foreign_key_check').fetchall())
            self.assertEqual({r[0] for r in c.execute('select modo from WB_RESULTADOS')},set(bases.MODOS))
            self.assertEqual(c.execute('select count(*) from WB_ELEMENTOS').fetchone()[0],5)
    def test_conteudo_igual_reutiliza_sem_nome_caminho(self):
        f=self.criar();h=hash_arquivo(f);g=self.criar('v2.gpkg',anterior=f)
        self.assertEqual(f,g);self.assertFalse((self.p/'v2.gpkg').exists());self.assertEqual(hash_arquivo(f),h)
    def test_assinatura_ignora_esquema_auxiliar_e_caminho(self):
        m=copy.deepcopy(self.m);m.update(banco='outro',esquema=['Auxiliar'])
        self.assertEqual(bases.assinatura_modelo(m,bases.MODOS[0]),bases.assinatura_modelo(self.m,bases.MODOS[0]))
    def test_atualizacao_preserva_anterior(self):
        f=self.criar();h=hash_arquivo(f);m=copy.deepcopy(self.m);m['elementos'][11]['ativo']=False
        g=self.criar('meu_nome.gpkg',m,anterior=f);a=bases.metadados(f);b=bases.metadados(g)
        self.assertEqual(b['anterior'],a['uuid']);self.assertEqual(b['versao'],2);self.assertEqual(hash_arquivo(f),h)
        r=bases.comparar(f,g);self.assertEqual(r['alterados']['ativo'],[11]);self.assertIn('Não observado',r['aviso'])
    def test_cenario_muda_contexto(self):
        f=self.criar();m=copy.deepcopy(self.m);m['cenario']=2
        g=self.criar('cenario2.gpkg',m,cenario=2,anterior=f)
        self.assertEqual(bases.metadados(g)['versao'],2)
    def test_hipotese_invalida_bloqueada(self):
        with self.assertRaises(ValueError):self.criar(modo='ESTADOS_DO_CENARIO')
    def test_outro_modelo_nao_e_versao(self):
        f=self.criar();m=copy.deepcopy(self.m);m['projeto']='outra_identidade'
        with self.assertRaises(ValueError):self.criar('outro.gpkg',m,anterior=f)
        self.assertFalse((self.p/'outro.gpkg').exists())
    def test_cancelamento_nao_publica(self):
        with self.assertRaises(InterruptedError):self.criar(cancelar=lambda:True)
        self.assertFalse((self.p/'v1.gpkg').exists())
    def test_falha_exportacao_nao_publica(self):
        with patch.object(bases,'exportar_geografico',side_effect=OSError('Falha simulada')):
            with self.assertRaises(OSError):self.criar()
        self.assertFalse((self.p/'v1.gpkg').exists())
    def test_fonte_preservada(self):
        h=hash_arquivo(self.fonte);self.criar();self.assertEqual(h,hash_arquivo(self.fonte))
    def test_sobrescrita_bloqueada(self):
        f=self.criar();h=hash_arquivo(f)
        with self.assertRaises(FileExistsError):self.criar()
        self.assertEqual(hash_arquivo(f),h)
    def test_snapshot_alterado_detectado(self):
        f=self.criar()
        with sqlite3.connect(f) as c:
            r=json.loads(c.execute('select dados from WB_RESULTADOS where modo=?',(bases.MODOS[0],)).fetchone()[0]);r['resumo']['componentes']=999
            c.execute('update WB_RESULTADOS set dados=? where modo=?',(json.dumps(r),bases.MODOS[0]))
        with self.assertRaises(ValueError):bases.restaurar(f)
    def test_nome_livre_catalogo_e_municipios(self):
        f=self.criar('nome livre ç.gpkg');c=Catalogo(self.p);c.registrar(f)
        self.assertEqual(c.listar(projeto='Projeto')[0]['nome'],'Modelo sintético');self.assertFalse(c.listar(projeto='Outro'))
    def test_arquivo_renomeado_por_uuid(self):
        f=self.criar();c=Catalogo(self.p);r=c.registrar(f)[0];g=self.p/'mudou.gpkg';f.rename(g);c.localizar(r['uuid'],r['tipo'],g)
        self.assertEqual(len(c.listar()),2);self.assertTrue(c.listar()[0]['disponivel']);self.assertFalse(c.listar()[1]['disponivel'])
    def test_localizar_rejeita_outro_uuid(self):
        f=self.criar();c=Catalogo(self.p)
        with self.assertRaises(ValueError):c.localizar('outro','TOPOLOGIA_WG',f)
    def test_sugestao_sem_sobrescrever(self):
        a=sugestao(self.p,'São José','TopologiaWG');a.touch();b=sugestao(self.p,'São José','TopologiaWG')
        self.assertEqual(b.name,'Sao_Jose_TopologiaWG_v002.gpkg');self.assertEqual(b.parent.name,'Sao_Jose')
    def test_varredura_nao_exige_nome_padrao(self):
        f=self.criar('qualquer.gpkg');c=Catalogo(self.p);self.assertFalse(c.varrer());self.assertEqual(c.listar()[0]['base'],str(f))
    def test_legacy_importa_sem_dobrar_escala(self):
        from test_integracao_investigativa import IntegracaoPersistidaTest
        x=IntegracaoPersistidaTest();x.setUp()
        try:
            f=bases.importar_legado(x.gpkg,self.p/'legado.gpkg','Legado','Projeto')
            t=bases.restaurar(f);self.assertIn('LEGADO_PARCIAL',t['meta_base']['escopo']);self.assertEqual(t['meta_base']['referencia_espacial']['fator'],1)
            self.assertEqual(t['geometrias'][10].asWkt(),'LineString (0 0, 1 0)')
        finally:x.tearDown()


class EmpacotamentoTest(unittest.TestCase):
    def test_bootstrap_recusa_atualizacao_na_mesma_sessao(self):
        import subprocess
        import sys
        raiz=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);lib=p/'_biblioteca';lib.mkdir();(p/'MANIFESTO.json').write_text('primeira')
            codigo="""import importlib.util,sys,types
from pathlib import Path
spec=importlib.util.spec_from_file_location('bootstrap_teste',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
lib=Path(sys.argv[2]);m.ativar(lib)
sys.modules['auditoria_fronteiras']=types.SimpleNamespace(__file__=str(lib/'auditoria_fronteiras/__init__.py'))
m.ativar(lib)
(lib.parent/'MANIFESTO.json').write_text('segunda')
try:m.ativar(lib)
except RuntimeError:print('BLOQUEADO')
else:raise AssertionError('Mistura de versões permitida')
"""
            r=subprocess.run([sys.executable,'-c',codigo,str(raiz/'complemento_qgis/auditoria_redes/bootstrap.py'),str(lib)],capture_output=True,text=True,timeout=20)
            self.assertEqual(r.returncode,0,r.stderr);self.assertIn('BLOQUEADO',r.stdout)
    def test_ids_repetidos_entre_fontes_nao_sao_inequivocos(self):
        from auditoria_topologica_watergems.gerenciamento import provar_fontes
        from qgis.core import QgsGeometry
        m=modelo();regs=[dict(uid='a',origem='fonte1',chave_cadastral='E-10',geometria=QgsGeometry.fromWkt('LINESTRING(0 0,1 0)')),dict(uid='b',origem='fonte2',chave_cadastral='E-10',geometria=QgsGeometry.fromWkt('LINESTRING(0 0,1 0)'))]
        a,_=provar_fontes(m,regs,1,.01);self.assertTrue(all(x['situacao']=='MULTIPLAS_CANDIDATAS' for x in a))
    def test_id_nulo_preserva_diagnostico_bruto_sem_associar(self):
        from auditoria_topologica_watergems.gerenciamento import provar_fontes
        a,_=provar_fontes(modelo(),[dict(uid='a',origem='fonte1',chave_cadastral=None,geometria=None)],1,.01)
        self.assertEqual(a[0]['situacao'],'NAO_ENCONTRADA');self.assertEqual(a[0]['classificacao_bruta'],'INCONSISTENTE');self.assertFalse(a[0]['candidatos'])
    def test_zip_autonomo_manifesto_e_contrato(self):
        import zipfile
        raiz=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as p:
            z=empacotar(raiz,Path(p)/'plugin.zip')
            with zipfile.ZipFile(z) as pacote:
                nomes=pacote.namelist();self.assertIn('auditoria_redes/metadata.txt',nomes);self.assertIn('auditoria_redes/_biblioteca/auditoria_aplicacao/controlador.py',nomes)
                self.assertFalse(any('__pycache__' in n for n in nomes));self.assertEqual(len(nomes),len(set(nomes)))
                from hashlib import sha256
                for n,h in json.loads(pacote.read('auditoria_redes/MANIFESTO.json')).items():self.assertEqual(sha256(pacote.read(n)).hexdigest(),h)
            with self.assertRaises(FileExistsError):empacotar(raiz,z)

if __name__=='__main__':unittest.main()
