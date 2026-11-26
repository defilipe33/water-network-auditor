"""Contratos da interface de investigação e da prévia cadastral."""

import json
import sqlite3
import unittest
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import test_grafo_gis as gis
from test_redes_estruturantes_gis import executar
from auditoria_aplicacao import cadastro_exportavel as cadastro
from auditoria_aplicacao import estado_projeto, persistencia_grafo_gis as pg
from auditoria_aplicacao.corredores_gis import analisar, novo_destino
from auditoria_aplicacao.mapa_macro_origem import plano
from auditoria_aplicacao.macro_origem_gis import analisar as macro
from auditoria_aplicacao.revisao_sequencial_gis import selecionar
from qgis.PyQt.QtWidgets import QInputDialog
from qgis.core import QgsGeometry


def catalogo_sintetico():
    ts=[gis.linha('a',(0,0),(20,0)),gis.linha('b',(10,0),(10,8)),
        gis.linha('isolado',(55,10),(65,10)),gis.linha('fora',(65,10),(75,10))]
    for t,valor in zip(ts,(0,'010','010',None)):
        t.update(id=valor,feicao=t['uid'],fontes=['redes'],camada='Rede sintética',categoria='PIPE',
                 atributos_originais={'gisid':valor})
    foto=executar(ts[:3],[('A',[('a',0.)])],
                  [dict(uuid='c',tipo='CONEXAO',rev='rev1',situacao='INFORMADA',decisao='CONFIRMADA',
                        portas=[['a',.5],['b',0.]])])
    return foto,(ts,[],[],[],[])


class CadastroCompleto(unittest.TestCase):
    def test_inclui_isolada_e_fora_da_fotografia_preservando_zero_e_nulo(self):
        f,inv=catalogo_sintetico()
        d=cadastro.preparar(f,inv,atividades={'isolado':'ATIVO','fora':'INATIVO'})
        m=d['manifesto']['contagens']
        self.assertEqual((m['pipes_originais'],m['pipes_divididos'],m['segmentos']),(4,1,5))
        p={r['parte']:r for r in d['pipes']}
        self.assertEqual(p['a']['gis_id'],0)
        self.assertIsNone(p['fora']['gis_id'])
        self.assertEqual((p['isolado']['condicao_topologica'],p['isolado']['atividade']),('SEM_ORIGEM','ATIVO'))
        self.assertEqual((p['fora']['condicao_topologica'],p['fora']['atividade']),('NAO_ANALISADO','INATIVO'))
        self.assertNotEqual(p['fora']['no_a'],p['isolado']['no_b'])
        self.assertEqual(len({r['uid'] for r in d['pipes']}),5)
        self.assertTrue(any(r['resultado']=='APLICADA' for r in d['operacoes']))

    def test_reabre_gpkg_e_shapefile(self):
        from osgeo import ogr
        f,inv=catalogo_sintetico()
        d=cadastro.preparar(f,inv,modo_atividade='FORA_INATIVO')
        with TemporaryDirectory() as pasta:
            for fmt in ('GPKG','ESRI Shapefile'):
                p=cadastro.exportar(d,pasta,fmt)
                m=json.loads((p/'validacao.json').read_text('utf-8'))
                self.assertEqual(m['contagens']['atividade']['INATIVO'],1)
                nome=p/('cadastro_modelagem.gpkg' if fmt=='GPKG' else 'pipes.shp')
                ds=ogr.Open(str(nome))
                self.assertEqual(ds.GetLayerByName('pipes').GetFeatureCount(),5)
                ds.Destroy()
                if fmt=='GPKG':
                    with closing(sqlite3.connect(nome)) as con:
                        self.assertEqual(con.execute('PRAGMA integrity_check').fetchone(),('ok',))
                        self.assertEqual(con.execute('SELECT COUNT(*) FROM inventario_cadastral').fetchone(),(4,))
                else:
                    self.assertTrue(all((p/('pipes'+x)).is_file() for x in ('.shx','.dbf','.prj','.cpg')))

    def test_lacuna_explicita(self):
        f,inv=catalogo_sintetico()
        inv[4].append('Fonte indisponível')
        self.assertTrue(cadastro.preparar(f,inv)['manifesto']['lacunas'])

    def test_proposta_aplicada_preserva_bend_e_desabilitada_fica_fora(self):
        from test_projeto_topologico_118 import CRS, rede_proposta
        from auditoria_aplicacao.tubulacoes_propostas import preparar_propostas
        from qgis.core import QgsCoordinateTransformContext
        ts,p=rede_proposta()
        for t in ts:
            t.update(id=t['uid'],feicao=t['uid'],fontes=['redes'],camada='Rede sintética',categoria='PIPE')
        proposta,links,erros=preparar_propostas([p],ts,CRS,QgsCoordinateTransformContext())
        self.assertFalse(erros)
        f=gis.construir([*ts,*proposta],conexoes=links)
        f.update(uuid='execucao',projeto_uid='projeto',crs=CRS.toWkt(),propostas_aplicadas=[p['uuid']],
                 participantes=[p,dict(p,uuid='fora',habilitado=False)])
        d=cadastro.preparar(f,(ts,[],[],[],[]))
        saida=[r for r in d['pipes'] if r['proposta']]
        self.assertEqual(len(saida),1)
        self.assertEqual(saida[0]['proposta'],p['uuid'])
        self.assertEqual(saida[0]['atividade'],'A_DEFINIR')
        g=QgsGeometry()
        g.fromWkb(saida[0]['wkb'])
        self.assertEqual(len(g.asPolyline()),3)


class Fluxos(unittest.TestCase):
    def test_fila_centena_e_filtros_combinados(self):
        g=QgsGeometry.fromWkt('POINT(1 1)')
        wkb=bytes(g.asWkb()).hex()
        rs=[dict(uid=str(i),tipo='CONEXAO_T' if i%2 else 'CRUZAMENTO',
                 tubos=['p'] if i<50 else ['q'],wkb=wkb) for i in range(100)]
        self.assertEqual(len(selecionar(rs,{})),100)
        d={'1':'CONFIRMADA','3':'INDETERMINADA','5':'SEPARADA'}
        area=QgsGeometry.fromWkt('POLYGON((0 0,2 0,2 2,0 2,0 0))')
        self.assertEqual(selecionar(rs,d,pendentes=True,tipo='CONEXAO_T',ids={'1','3','5','7','81'},
                                   entradas={'p'},area=area),['3','7'])

    def test_destinos_combinados_com_limite_e_sem_duplicar_no(self):
        f,_=catalogo_sintetico()
        a=f['arestas'][0]['a']
        manual=novo_destino('NO',a)
        p=dict(modo='COMBINADO',maximo=2,minimo_m=0)
        a=analisar(f,destinos=[manual],agrupamento=p)
        b=analisar(f,destinos=[manual],agrupamento=p)
        self.assertEqual([r['uid'] for r in a['destinos']],[r['uid'] for r in b['destinos']])
        self.assertIn(manual['uid'],{r['uid'] for r in a['destinos']})
        self.assertEqual(len(a['destinos']),2)
        self.assertEqual(len({r['no_alvo'] for r in a['destinos']}),2)

    def test_espessura_e_ordem_com_nome_editado(self):
        f,_=catalogo_sintetico()
        m=macro(f,minimo_m=4)
        for c in m['corredores']:c['nome']='Minha rede'
        rs=plano(f,m,'AMBOS',m['blocos'],uniforme=False,papeis=True)
        self.assertTrue(any(r[2]=='1.0' and r[4]==2 for r in rs))
        rs=plano(f,m,'AMBOS',m['blocos'],uniforme=False,papeis=True,espessuras={'corredor':1.6})
        self.assertTrue(all(r[2]=='1.6' for r in rs if r[4]==2))


class Interface(unittest.TestCase):
    def setUp(self):
        self.f=gis.InterfaceGIS()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.c,self.t=self.f.c,self.f.t
        self.aguardar=self.f.f.aguardar

    def test_hierarquia_dependencia_nomes_e_modalidades(self):
        c,t=self.c,self.t
        self.assertEqual([c.objetivo.itemData(i) for i in range(3)],['verificar','conectividade','estrutura'])
        self.assertTrue(c.abrir_estrutura())
        p=c.estrutura_gis
        self.assertIn('primeiro',p.status.text())
        self.assertEqual(p.execucoes.count(),1)
        self.assertTrue(c.abrir_conectividade())
        t.nome.setText('Minha execução')
        t.iniciar();self.aguardar()
        t.iniciar();self.aguardar()
        rs=[r for r in c.registros_projeto() if r['tipo']=='TOPOLOGIA_GIS']
        self.assertEqual(len({r['uuid'] for r in rs}),2)
        alvo=rs[0]
        arquivo=Path(alvo['base'])
        antes=sha256(arquivo.read_bytes()).digest()
        with patch.object(QInputDialog,'getText',return_value=('Nome revisado',True)):
            c.renomear_analise(alvo)
        self.assertEqual(sha256(arquivo.read_bytes()).digest(),antes)
        self.assertEqual(pg.carregar(arquivo,alvo['uuid'],t.uid_projeto)['nome'],'Minha execução')
        p.listar_execucoes()
        self.assertTrue(any('Nome revisado' in p.execucoes.itemText(i) for i in range(p.execucoes.count())))
        for modo,esperado in [('INTEGRAL','MACRO_BLOCOS'),('PERCURSOS','ROTAS'),('CRITICIDADE','PONTES')]:
            p.modalidade.setCurrentIndex(p.modalidade.findData(modo))
            self.assertGreaterEqual(p.categoria.findData(esperado),0)

    def test_decisao_versionada_e_retomada_do_cursor(self):
        c,t=self.c,self.t
        t.iniciar();self.aguardar()
        u=t.dados['tubos'][0]['uid']
        wkb=bytes(QgsGeometry.fromWkt('POINT(10 0)').asWkb()).hex()
        for i,(a,b) in enumerate(((.1,.2),(.3,.4),(.5,.6),(.7,.8))):
            t.dados['diagnosticos'].append(dict(uid='teste-'+str(i),tipo='CONEXAO_T',portas=[[u,a],[u,b]],
                                                tubos=[u],situacao='CANDIDATA',wkb=wkb))
        t.preencher_conexoes(t.registros,set())
        t.revisao_seq_b.setChecked(True)
        t.iniciar_revisao_sequencial()
        for decisao,incluir in (('CONFIRMADA',True),('CONFIRMADA',False),('SEPARADA',True),('INDETERMINADA',False)):
            t.decidir_sequencia(decisao,incluir)
        self.assertEqual(t._posicao_conexoes,4)
        self.assertEqual(len(t._selecionados()),2)
        self.assertEqual(len(pg.revisoes(t._base_complementos(),t.uid_projeto,tipo='CONEXAO')),4)
        t.mover_revisao(-1)
        t._fila_conexoes=[]
        t._posicao_conexoes=0
        t.retomar_revisao_sequencial()
        self.assertEqual(t._posicao_conexoes,3)
        self.assertIn('4 revisadas',t.seq_progresso.text())
        d=estado_projeto.ler(c.app.catalogo.raiz,c.projetos.atual(),estado_projeto.RASCUNHO)
        self.assertEqual(set(d['vinculos']),set(t._selecionados()))

    def test_revisar_cem_candidatas_salvando_decisoes(self):
        t=self.t
        t.iniciar();self.aguardar()
        u=t.dados['tubos'][0]['uid']
        wkb=bytes(QgsGeometry.fromWkt('POINT(10 0)').asWkb()).hex()
        t.dados['diagnosticos'].extend(dict(uid=f'candidata-{i:03}',tipo='CONEXAO_T',
            portas=[[u,i/200],[u,.9]],tubos=[u],situacao='CANDIDATA',wkb=wkb) for i in range(100))
        t.preencher_conexoes(t.registros,set())
        t.revisao_seq_b.setChecked(True)
        t.iniciar_revisao_sequencial()
        for _ in range(100):
            t.decidir_sequencia('CONFIRMADA',False)
        self.assertEqual(t._posicao_conexoes,100)
        self.assertIn('100 revisadas',t.seq_progresso.text())
        self.assertEqual(len(pg.revisoes(t._base_complementos(),t.uid_projeto,tipo='CONEXAO')),100)
