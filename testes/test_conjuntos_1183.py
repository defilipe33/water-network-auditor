"""Regressões de vereditos, duplicatas e Selection Sets materializados."""

import csv
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

import test_grafo_gis as gis
from test_consolidacao_1182 import catalogo_sintetico
from test_redes_estruturantes_gis import executar

from auditoria_aplicacao import cadastro_exportavel as cadastro
from auditoria_aplicacao import conjuntos_modelagem as cm
from auditoria_aplicacao import persistencia_grafo_gis as pg
from auditoria_aplicacao.duplicatas_conexoes_gis import auditar, equivalentes
from auditoria_aplicacao.revisao_sequencial_gis import selecionar
from auditoria_aplicacao.topologia_gis_relacoes_ui import acompanhamento_padrao


class Duplicatas(unittest.TestCase):
    def setUp(self):
        self.tubos={r['uid']:r for r in (
            gis.linha('a',(0,0),(20,0)),gis.linha('b',(10,0),(10,8)),
            gis.linha('c',(10,0),(10,-8)))}
        self.conexao=dict(uuid='a',tipo='CONEXAO',situacao='INFORMADA',
                          decisao='CONFIRMADA',portas=[['a',.5],['b',0.]])
        self.candidata=dict(uid='aut',tipo='CONEXAO_T',portas=self.conexao['portas'])

    def test_duplicata_exata_independe_da_ordem(self):
        outra=dict(self.conexao,uuid='b',portas=list(reversed(self.conexao['portas'])))
        pares,pend=auditar([], [self.conexao,outra],self.tubos)
        self.assertEqual([p['tipo'] for p in pares],['EXATA'])
        self.assertFalse(pend)

    def test_distinta_proxima_preserva_tubulacao_concorrente(self):
        outra=dict(self.candidata,uid='outra',portas=[['a',.5],['c',0.]])
        pares,_=auditar([outra,self.candidata],[],self.tubos)
        self.assertEqual([p['tipo'] for p in pares],['LOCAL'])
        self.assertEqual(equivalentes(self.conexao,[],[outra,self.candidata],self.tubos,.2),[self.candidata])

    def test_tolerancia_conflito_direcao_e_partes_ausentes(self):
        outra=dict(self.conexao,uuid='b',decisao='SEPARADA',portas=[['a',.505],['b',0.]])
        pares,_=auditar([], [self.conexao,outra],self.tubos)
        self.assertEqual(pares[0]['tipo'],'CONFLITO')
        self.assertEqual(auditar([], [self.conexao,outra],self.tubos,.01)[0],[])
        self.assertEqual(auditar([], [self.conexao,dict(outra,dirigida=True)],self.tubos)[0][0]['tipo'],'LOCAL')
        self.assertEqual(auditar([], [self.conexao],{})[1],['a'])

    def test_acompanhamento_e_vinculo_historico(self):
        c=dict(self.conexao,rev='v1',candidato='aut')
        r=dict(c,rev='v2')
        pares,_=auditar([self.candidata],[r],self.tubos,historico=[c,r])
        self.assertEqual({p['tipo'] for p in pares},{'VINCULO','REVISAO'})
        self.assertEqual(acompanhamento_padrao('CONFIRMADA'),'VERIFICADO')
        self.assertEqual(acompanhamento_padrao('SEPARADA'),'VERIFICADO')
        self.assertEqual(acompanhamento_padrao('INDETERMINADA'),'NECESSITA_CONFIRMACAO')
        self.assertEqual(selecionar([self.candidata],{'aut':'CONFIRMADA'},pendentes=True,
                                   acompanhamento_pendente={'aut'}),['aut'])

    def test_substituicao_conserva_referencias_anteriores_e_valida_concorrencia(self):
        with TemporaryDirectory() as pasta:
            p=Path(pasta)/'complementos.gpkg'
            pg.criar_complementos(p,'projeto')
            a=pg.salvar_revisao(p,'projeto','CONEXAO',self.conexao)
            b=pg.salvar_revisao(p,'projeto','CONEXAO',self.conexao)
            dados=dict(b,habilitado=False,substituida_por=a['uuid'])
            with self.assertRaisesRegex(ValueError,'principal mudou'):
                pg.salvar_revisao(p,'projeto','CONEXAO',dados,b['uuid'],b['rev'],referencia=(a['uuid'],'antiga'))
            pg.salvar_revisao(p,'projeto','CONEXAO',dados,b['uuid'],b['rev'],referencia=(a['uuid'],a['rev']))
            antes,depois=pg.revisoes(p,'projeto',b['uuid'])
            self.assertNotIn('substituida_por',antes)
            self.assertEqual(depois['substituida_por'],a['uuid'])


class SelecaoMaterializada(unittest.TestCase):
    def setUp(self):
        self.foto,self.inv=catalogo_sintetico()
        self.previa=cadastro.preparar(self.foto,self.inv,modo_atividade='FORA_INATIVO')
        self.a={('PIPE',p['uid']) for p in self.previa['pipes'] if p['parte']=='a'}
        self.fora={('PIPE',p['uid']) for p in self.previa['pipes'] if p['parte']=='fora'}

    def conjunto(self,chaves,u='conjunto',nome='Corredor sintético',cat='CORREDORES'):
        return dict(cm.compor(self.previa,chaves,nome=nome,categoria=cat,origem='AUTOMATICA'),uuid=u)

    def test_conexao_refere_pipes_segmentados_e_no_materializado(self):
        chaves=cm.da_conexao(self.previa,'c')
        self.assertEqual(sum(t=='PIPE' for t,_ in chaves),3)
        self.assertEqual(sum(t=='JUNCTION' for t,_ in chaves),1)
        self.assertTrue(self.a<=chaves)
        self.assertEqual(len(cm.selecionar(self.previa,self.a,incluir_nos=True)),5)
        self.assertEqual(cm.selecionar(self.previa,self.fora,estado='ATIVO'),set())

    def test_reconciliar_distingue_segmentos_novos_e_nao_rescreve_a_revisao(self):
        antiga=executar(self.inv[0][:3],[('A',[('a',0.)])])
        antiga['uuid']='anterior'
        p=cadastro.preparar(antiga,self.inv)
        u=next(r['uid'] for r in p['pipes'] if r['parte']=='a')
        antigo=cm.compor(p,{('PIPE',u)},nome='Antes',categoria='BLOCOS',origem='MANUAL')
        r=cm.reconciliar(antigo,self.previa)
        self.assertFalse(r['compativel'])
        self.assertEqual(set(r['novos']),self.a)
        self.assertEqual(antigo['membros'][0]['uid'],u)

    def test_reabre_conjunto_e_revisoes_sem_migrar_tabelas_anteriores(self):
        with TemporaryDirectory() as pasta:
            p=Path(pasta)/'complementos.gpkg'
            pg.criar_complementos(p,self.foto['projeto_uid'])
            conjunto=self.conjunto(self.a)
            a=pg.salvar_revisao(p,self.foto['projeto_uid'],'CONJUNTO_WG',conjunto)
            b=pg.salvar_revisao(p,self.foto['projeto_uid'],'CONJUNTO_WG',dict(a,nome='Renomeado',arquivado=True),
                              a['uuid'],a['rev'])
            self.assertEqual(pg.revisoes(p,self.foto['projeto_uid'],a['uuid']),[a,b])
            self.assertTrue(cm.reconciliar(b,self.previa)['compativel'])

    def test_pacote_gpkg_e_shp_preserva_pertencimento_multiplo_e_inativo(self):
        from osgeo import ogr
        c1=self.conjunto(self.a|self.fora)
        c2=self.conjunto(self.a,u='bloco',nome='Bloco sintético',cat='BLOCOS')
        with TemporaryDirectory() as pasta:
            for fmt in ('GPKG','ESRI Shapefile'):
                r=cadastro.exportar(self.previa,pasta,fmt,selecoes=[c1,c2],somente_conjuntos=True)
                with (r/'WNA_ELEMENTO_CONJUNTO.csv').open(encoding='utf-8-sig',newline='') as f:
                    linhas=list(csv.DictReader(f))
                self.assertEqual(len(linhas),5)
                self.assertEqual({e['situacao_participacao'] for e in linhas},{'INATIVO','A_DEFINIR'})
                self.assertIn('0',{e['id_gis'] for e in linhas})
                self.assertEqual(len(list((r/'MINUTAS_QUERIES').glob('*.txt'))),2)
                gp=r/'cadastro_modelagem.gpkg'
                ds=ogr.Open(str(gp if gp.is_file() else r/'pipes.shp'))
                cam=ds.GetLayerByName('pipes')
                self.assertEqual(cam.GetFeatureCount(),3)
                self.assertEqual(len({f['WNA_UID'] for f in cam}),3)
                cam=None
                ds.Destroy()
                if gp.is_file():
                    with closing(sqlite3.connect(gp)) as con:
                        self.assertEqual(con.execute('SELECT count(*) FROM WNA_ELEMENTO_CONJUNTO').fetchone(),(5,))

    def test_bloqueia_outra_execucao_e_ids_repetidos(self):
        c=self.conjunto(self.a)
        with self.assertRaisesRegex(ValueError,'incompatível'):
            cm.preparar_exportacao(self.previa,[dict(c,topologia_uid='outra')])
        with self.assertRaisesRegex(ValueError,'repetidos'):
            cm.validar(dict(c,membros=c['membros']+c['membros']),self.foto['projeto_uid'])

    def test_tres_segmentos_e_lote_extenso_sem_truncamento(self):
        tubos=[gis.linha('p',(0,0),(30,0))]
        tubos.extend(gis.linha(f'x{i}',(10*i,0),(10*i,5)) for i in (1,2))
        tubos.extend(gis.linha(f'extra{i}',(i,100),(i,105)) for i in range(100))
        for t in tubos:t.update(feicao=t['uid'],fontes=['redes'],label='Label repetido')
        rel=[dict(uuid=f'c{i}',tipo='CONEXAO',rev='rev',situacao='INFORMADA',decisao='CONFIRMADA',
                  portas=[['p',i/3],['x'+str(i),0.]]) for i in (1,2)]
        f=executar(tubos,[('A',[('p',0.)])],rel)
        p=cadastro.preparar(f,(tubos,[],[],[],[]))
        self.assertEqual(len([r for r in p['pipes'] if r['parte']=='p']),3)
        chaves={('PIPE',r['uid']) for r in p['pipes']}
        c=dict(cm.compor(p,chaves,nome='Rede',categoria='BLOCOS',origem='MANUAL'),uuid='rede')
        with TemporaryDirectory() as pasta:
            saida=cadastro.exportar(p,pasta,'GPKG',selecoes=[c],somente_conjuntos=True)
            q=saida/'MINUTAS_QUERIES'
            lotes=sorted(q.glob('*.txt'))
            self.assertEqual([p.read_text(encoding='utf8').count("'")//2 for p in lotes],[100,5])
            for _,u in chaves:self.assertEqual(sum(u in p.read_text(encoding='utf8') for p in lotes),1)
