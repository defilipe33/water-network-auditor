"""Índice reconstruível, dados sintéticos e cenários de falha entre sessões."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import os
import stat
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from test_auditoria_fronteiras import APP
from auditoria_topologica_watergems.gerenciamento import Catalogo,ErroCatalogo
from auditoria_topologica_watergems.arquivos import hash_arquivo

def base_sintetica(p,uid='uuid-sintetico',historico='observação preservada'):
    m=dict(uuid=uid,tipo='TOPOLOGIA_WG',nome='Modelo sintético',projeto='Projeto',modelo_uid='modelo-teste',versao=2,anterior='v1',cenario=1,assinatura='assinatura-sintetica',data='2026-01-01')
    with closing(sqlite3.connect(p)) as c,c:
        c.execute('CREATE TABLE WB_BASE(uuid TEXT,meta TEXT,modelo TEXT)');c.execute('INSERT INTO WB_BASE VALUES(?,?,?)',(uid,json.dumps(m),'{}'))
        c.execute('CREATE TABLE REVISOES(observacao TEXT)');c.execute('INSERT INTO REVISOES VALUES(?)',(historico,))
        c.execute('CREATE TABLE PROPOSTAS(texto TEXT)');c.execute("INSERT INTO PROPOSTAS VALUES('não executar automaticamente')")
    return p

class RecuperacaoCatalogoTest(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name);self.arq=self.p/'catalogo_bases.sqlite'
    def tearDown(self):self.tmp.cleanup()
    def tabela(self):
        with closing(sqlite3.connect(self.arq)) as c:return 'bases' in {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    def test_inexistente(self):self.assertEqual(Catalogo(self.p).listar(),[]);self.assertTrue(self.tabela())
    def test_pasta_nao_informada_nao_usa_diretorio_atual(self):
        with self.assertRaisesRegex(ErroCatalogo,'explicitamente'):Catalogo('')
    def test_zero_bytes_antes_construtor(self):self.arq.touch();self.assertEqual(Catalogo(self.p).listar(),[]);self.assertTrue(self.tabela())
    def test_zero_bytes_depois_construtor_reproduz_sessao(self):
        c=Catalogo(self.p);self.arq.write_bytes(b'');self.assertEqual(c.listar(),[]);self.assertTrue(self.tabela())
    def test_desapareceu_apos_construtor(self):
        c=Catalogo(self.p);self.arq.rename(self.p/'catalogo_anterior.sqlite');self.assertEqual(c.listar(),[]);self.assertTrue(self.tabela())
    def test_sqlite_sem_bases_preserva_outras_tabelas(self):
        with closing(sqlite3.connect(self.arq)) as c,c:c.execute('CREATE TABLE outro(v TEXT)');c.execute("INSERT INTO outro VALUES('preservar')")
        Catalogo(self.p).listar()
        with closing(sqlite3.connect(self.arq)) as c:self.assertEqual(c.execute('SELECT v FROM outro').fetchone()[0],'preservar')
        self.assertTrue(list(self.p.glob('catalogo_bases.backup_*.sqlite')))
    def test_valido_vazio(self):
        c=Catalogo(self.p);antes=hash_arquivo(self.arq);self.assertEqual(Catalogo(self.p).listar(),[]);self.assertEqual(hash_arquivo(self.arq),antes)
    def test_registros_reabertos(self):
        b=base_sintetica(self.p/'base.gpkg');Catalogo(self.p).registrar(b);r=Catalogo(self.p).listar()[0];self.assertEqual(r['uuid'],'uuid-sintetico');self.assertEqual(r['anterior'],'v1')
    def test_migracao_aliases_com_backup(self):
        with closing(sqlite3.connect(self.arq)) as c,c:
            c.execute('CREATE TABLE bases(uuid TEXT,tipo TEXT,caminho TEXT,metadados TEXT)');c.execute('INSERT INTO bases VALUES(?,?,?,?)',('anterior','TOPOLOGIA_WG','movido.gpkg',json.dumps({'versao':7})))
        r=Catalogo(self.p).listar()[0];self.assertEqual((r['uuid'],r['versao']),('anterior',7));self.assertTrue(list(self.p.glob('*.backup_*.sqlite')))
    def test_legado_nao_interpretavel_preservado(self):
        with closing(sqlite3.connect(self.arq)) as c,c:c.execute('CREATE TABLE bases(valor TEXT)');c.execute("INSERT INTO bases VALUES('registro não descartado')")
        cat=Catalogo(self.p);cat.listar()
        with closing(sqlite3.connect(self.arq)) as c:
            t=c.execute("SELECT name FROM sqlite_master WHERE name LIKE 'bases_legado_%'").fetchone()[0];self.assertEqual(c.execute('SELECT valor FROM '+t).fetchone()[0],'registro não descartado')
    def test_corrupcao_nao_e_vazio(self):
        self.arq.write_bytes(b'arquivo corrompido, nao substituir');antes=hash_arquivo(self.arq);c=Catalogo(self.p)
        with self.assertRaisesRegex(ErroCatalogo,'corrompido'):c.listar()
        self.assertEqual(c.listar_opcional(),[]);self.assertTrue(c.avisos);self.assertEqual(hash_arquivo(self.arq),antes)
    def test_leitura_valida_nao_exige_gravacao(self):
        c=Catalogo(self.p)
        with patch.object(c,'_abrir_rw',side_effect=PermissionError('permission denied')):self.assertEqual(c.listar(),[])
    def test_zero_somente_leitura_mensagem(self):
        c=Catalogo(self.p);self.arq.write_bytes(b'')
        with patch.object(c,'_abrir_rw',side_effect=sqlite3.OperationalError('attempt to write a readonly database')):
            with self.assertRaisesRegex(ErroCatalogo,'permissão'):c.listar()
        self.assertEqual(self.arq.stat().st_size,0)
    def test_bloqueio_transitorio(self):
        c=Catalogo(self.p)
        with patch.object(c,'_abrir_ro',side_effect=sqlite3.OperationalError('database is locked')):
            with self.assertRaisesRegex(ErroCatalogo,'outra sessão'):c.listar()
        self.assertEqual(c.listar(),[])
    @unittest.skipUnless(os.name=='nt','Atributo somente leitura do Windows')
    def test_arquivo_somente_leitura_windows(self):
        b=base_sintetica(self.p/'base.gpkg');c=Catalogo(self.p);c.registrar(b);c.listar();self.arq.chmod(stat.S_IREAD)
        try:
            self.assertEqual(len(c.listar()),1)
            with self.assertRaisesRegex(ErroCatalogo,'permissão'):c.registrar(b)
        finally:self.arq.chmod(stat.S_IREAD|stat.S_IWRITE)
    def test_bloqueio_real_sqlite(self):
        c=Catalogo(self.p)
        with closing(sqlite3.connect(self.arq)) as con:
            con.execute('BEGIN EXCLUSIVE')
            try:
                with self.assertRaisesRegex(ErroCatalogo,'outra sessão'):c.listar()
            finally:con.rollback()
        self.assertEqual(c.listar(),[])
    def test_falha_migracao_preserva_banco(self):
        c=Catalogo(self.p)
        with closing(sqlite3.connect(self.arq)) as con,con:con.execute('ALTER TABLE bases ADD COLUMN extra TEXT')
        antes=hash_arquivo(self.arq)
        with patch.object(c,'backup',side_effect=ValueError('falha controlada no backup')):
            with self.assertRaises(ErroCatalogo):c.garantir()
        self.assertEqual(hash_arquivo(self.arq),antes)
    def test_duas_sessoes_simultaneas(self):
        b=base_sintetica(self.p/'base.gpkg')
        def gravar(_):c=Catalogo(self.p);c.registrar(b);return c.listar()[0]['uuid']
        with ThreadPoolExecutor(2) as pool:self.assertEqual(list(pool.map(gravar,range(2))),['uuid-sintetico']*2)
        self.assertEqual(len(Catalogo(self.p).listar()),1)
    def test_interrupcao_rollback(self):
        with closing(sqlite3.connect(self.arq)) as c:c.execute('BEGIN IMMEDIATE');c.execute('CREATE TABLE bases(incompleta TEXT)');c.rollback()
        self.assertEqual(Catalogo(self.p).listar(),[]);self.assertTrue(self.tabela())
    def test_reconstrucao_preserva_decisoes_e_propostas(self):
        b=base_sintetica(self.p/'arquivo_livre.gpkg');antes=hash_arquivo(b);self.arq.touch();r=Catalogo(self.p).listar()[0]
        self.assertEqual(r['uuid'],'uuid-sintetico');self.assertEqual(hash_arquivo(b),antes)
    def test_copias_identicas_nao_sao_versoes(self):
        a=base_sintetica(self.p/'a.gpkg');b=self.p/'b.gpkg';shutil.copyfile(a,b);c=Catalogo(self.p);c.registrar(a);c.registrar(b);r=c.listar();self.assertEqual(len(r),1);self.assertEqual(len(r[0]['caminhos']),2)
    def test_mesmo_uuid_conteudo_divergente(self):
        a=base_sintetica(self.p/'a.gpkg');b=base_sintetica(self.p/'b.gpkg',historico='outra revisão');c=Catalogo(self.p);c.registrar(a);c.registrar(b);r=c.listar()
        self.assertEqual(len(r),2);self.assertTrue(all(v['conflito_identidade'] for v in r));self.assertTrue(any('conteúdo diferente' in v for v in c.avisos))
    def test_caminho_movido(self):
        a=base_sintetica(self.p/'a.gpkg');c=Catalogo(self.p);c.registrar(a);b=self.p/'b.gpkg';a.rename(b);c.localizar('uuid-sintetico','TOPOLOGIA_WG',b)
        self.assertEqual(len(c.listar()),2);self.assertTrue(c.avisos)
    def test_nao_recria_pasta_desaparecida(self):
        pasta=self.p/'escolhida';c=Catalogo(pasta);pasta.rename(self.p/'movida')
        with self.assertRaisesRegex(ErroCatalogo,'pasta'):c.listar()
        self.assertFalse(pasta.exists())
    def test_metadados_invalidos_nao_apagados(self):
        c=Catalogo(self.p)
        with closing(sqlite3.connect(self.arq)) as con,con:con.execute("INSERT INTO bases VALUES('u','tipo','ausente','JSON inválido')")
        self.assertEqual(c.listar(),[])
        with closing(sqlite3.connect(self.arq)) as con:self.assertEqual(con.execute('SELECT count(*) FROM bases').fetchone()[0],1)
    def test_indice_desatualizado_sinalizado(self):
        b=base_sintetica(self.p/'base.gpkg');c=Catalogo(self.p);c.registrar(b);c.listar()
        with closing(sqlite3.connect(b)) as con,con:con.execute("INSERT INTO REVISOES VALUES('nova observação')")
        self.assertTrue(c.listar()[0]['indice_desatualizado'])

class AssistenteCatalogoTest(unittest.TestCase):
    def setUp(self):
        from test_aplicacao_unificada import InterfaceUnificadaTest
        self.f=InterfaceUnificadaTest();self.f.setUp();self.f.carregar();self.f.app.bases();self.w=self.f.app.wg;self.w.base='base-ativa.gpkg'
    def tearDown(self):
        a=getattr(self.w,'_assistente',None)
        if a:a.close()
        self.f.tearDown()
    def abrir(self):
        from auditoria_aplicacao.assistente_espacial import AssistenteEspacial
        with patch.object(AssistenteEspacial,'executar'):self.w.assistente_espacial()
        return self.w._assistente
    def test_assistente_com_catalogo_zero(self):
        self.f.app.catalogo.arquivo.write_bytes(b'');a=self.abrir();self.assertIsNotNone(a);self.assertTrue(a.avisos_catalogo)
    def test_assistente_sem_bases(self):self.assertIsNotNone(self.abrir())
    def test_assistente_corrupcao_continua_com_ativa(self):
        self.f.app.catalogo.arquivo.write_bytes(b'corrupcao');a=self.abrir();self.assertEqual(a.base,'base-ativa.gpkg');self.assertEqual(a.catalogo,[]);self.assertTrue(a.avisos_catalogo)
    def test_erro_construcao_e_tratado(self):
        with patch('auditoria_aplicacao.assistente_espacial.AssistenteEspacial',side_effect=RuntimeError('falha controlada')),patch('auditoria_aplicacao.watergems_ui.QMessageBox.warning') as aviso:self.w.assistente_espacial();aviso.assert_called_once()

if __name__=='__main__':unittest.main()
