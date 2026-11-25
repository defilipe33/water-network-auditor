"""Casos sintéticos de agrupamento, percurso, reabertura e cartografia."""

import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import test_grafo_gis as etapa2
from test_redes_estruturantes_gis import executar, rede_arestas
from medir_estrutura_gis import foto_municipal
from auditoria_aplicacao.agrupamento_corredores_gis import parametros
from auditoria_aplicacao.corredores_gis import analisar, novo_destino
from auditoria_aplicacao import persistencia_grafo_gis as pg
from auditoria_aplicacao.representacao_estrutura_gis import GeometriasEstrutura
from auditoria_aplicacao.representacao_corredores_gis import CorredoresNoMapa, exportar_tracado
from auditoria_fronteiras.modelos import Cancelado
from osgeo import ogr
from qgis.core import QgsPointXY, QgsProject, QgsRectangle
from qgis.PyQt.QtCore import Qt


def arvore(fonte=True):
    arestas=[('s','a','p1',2),('a','b','p2',3),('b','c','p3',4),
            ('c','n','pn',8),('c','l','pl',11),('b','z','pz',14),
            ('z','zz','pzz',4),('i','j','isolada',500)]
    return rede_arestas(arestas,[('fonte','s')] if fonte else [])


def agrupar(foto, *nos, automatico=False, **opcoes):
    return analisar(foto,destinos=[novo_destino('NO',n) for n in nos],
                    agrupamento=parametros('AUTOMATICO' if automatico else 'MANUAL',**opcoes))


class Agrupamento(unittest.TestCase):
    def confirmar_sequencias(self,d):
        cobertura=[]
        desvios=[]
        for c in d['agrupamento']['corredores']:
            self.assertEqual(len(c['segmentos'])+1,len(c['nos']))
            self.assertEqual(len(c['tubos']),len(set(c['tubos'])))
            cobertura.extend(c['segmentos'])
            for n,m,i in zip(c['nos'],c['nos'][1:],c['segmentos']):
                e=d['foto']['arestas'][i]
                self.assertEqual({n,m},{e['a'],e['b']})
        self.assertEqual(len(cobertura),len(set(cobertura)))
        por_uid={c['uid']:c for c in d['agrupamento']['corredores']}
        por_rota={r['uid']:r for r in d['rotas']}
        for p in d['agrupamento']['percursos']:
            grupos=[por_uid[u]['segmentos'] for u in p['corredores']]
            r=por_rota[p['rota']]
            esperado=r['segmentos'] if p['papel']=='REFERENCIA' else r['alternativa']['segmentos']
            self.assertEqual(set(esperado),{s for grupo in grupos for s in grupo})
            for a,b in zip(p['corredores'],p['corredores'][1:]):
                self.assertIn(b,por_uid[a]['posteriores'])
                self.assertIn(a,por_uid[b]['anteriores'])
            desvios.extend(esperado)
        if d['fontes']:
            self.assertEqual(set(cobertura),set(desvios))

    def test_tres_destinos_troncos_conectados_e_cadeia_de_pipes(self):
        d=agrupar(arvore(),'n','l','zz')
        self.confirmar_sequencias(d)
        cs=d['agrupamento']['corredores']
        troncos=[c for c in cs if 'TRONCO' in c['funcoes']]
        self.assertEqual(len(troncos),2)
        raiz=next(c for c in troncos if 'p1' in c['tubos'])
        self.assertEqual(set(raiz['tubos']),{'p1','p2'})
        self.assertEqual(raiz['referencias'],3)
        self.assertEqual(len(raiz['dependentes']),3)
        self.assertEqual(set(raiz['funcoes']),{'TRONCO','CRITICO'})
        self.assertTrue(set(raiz['posteriores']) & {c['uid'] for c in troncos})
        self.assertFalse(any('isolada' in c['tubos'] for c in cs))

    def test_anel_com_alternativa_e_bifurcacao_sem_duplicar_segmentos(self):
        f=rede_arestas([('a','b','ab',1),('b','c','bc',1),('a','d','ad',2),('d','c','dc',2),
                       ('c','e','ce',3)],[('S','a')])
        d=agrupar(f,'c','e')
        self.confirmar_sequencias(d)
        ps=d['agrupamento']['percursos']
        self.assertEqual(sum(p['papel']=='ALTERNATIVA' for p in ps),2)
        self.assertTrue(any(p['estado']=='DISJUNTA_VERIFICADA' for p in ps))
        self.assertTrue(any(p['estado']=='PARCIAL_VERIFICADA' for p in ps))
        compartilhados=[c for c in d['agrupamento']['corredores'] if len(c['percursos'])>1]
        self.assertTrue(compartilhados)

    def test_duas_origens_e_um_trecho_compartilhado(self):
        f=rede_arestas([('o1','j','a',2),('o2','j','b',3),('j','d','c',10)],[('S1','o1'),('S2','o2')])
        d=agrupar(f,'d')
        c=next(c for c in d['agrupamento']['corredores'] if c['tubos']==['c'])
        self.assertEqual(c['origens'],['S1','S2'])
        self.assertEqual(c['fontes_alcancaveis'],['S1','S2'])
        self.assertFalse(c['fontes_exclusivas'])
        self.assertEqual(c['referencias'],2)
        f['origens_validas']=['S1']
        n=agrupar(f,'d')
        self.assertTrue(all(c['origens']==['S1'] for c in n['agrupamento']['corredores']))
        self.assertNotEqual(d['uuid'],n['uuid'])

    def test_sem_origens_e_circuito_preservam_componentes_distintos(self):
        f=rede_arestas([('a','b','a',2),('b','c','b',3),('c','a','c',4),('d','e','d',4)])
        d=agrupar(f,automatico=True)
        self.confirmar_sequencias(d)
        a=d['agrupamento']
        self.assertEqual(a['orientacao'],'NAO_ORIENTADA')
        self.assertFalse(a['percursos'])
        self.assertEqual({c['estado'] for c in a['corredores']},{'CIRCUITO','SEM_ORIENTACAO'})
        self.assertEqual({len(c['tubos']) for c in a['corredores']},{1,3})

    def test_selecao_periferica_por_distancia_no_grafo_e_minimo(self):
        f=rede_arestas([('s','x','p',100),('x','a','p2',2),('x','b','p3',1),
                       ('s','c','p4',20),('c','d','p5',15)],[('S','s')])
        f['nos'][1]['xy']=f['nos'][0]['xy']
        d=agrupar(f,automatico=True,maximo=10,minimo_m=50.)
        e=agrupar(f,automatico=True,maximo=10,minimo_m=50.)
        self.assertEqual([(p['ref'],p['distancia_origem_m']) for p in d['destinos']],[('a',102)])
        self.assertEqual(d['destinos'],e['destinos'])
        self.assertEqual(d['agrupamento']['amostra']['elegiveis'],2)
        self.assertEqual(d['agrupamento']['amostra']['grupos'],1)
        self.assertFalse(agrupar(f,automatico=True,minimo_m=1000)['destinos'])

    def test_destino_por_zona_e_sem_fabricar_rota_isolada(self):
        f=arvore()
        f['areas']=[dict(uid='z',label='Zona declarada')]
        d=analisar(f,destinos=[novo_destino('NO','l',zona='z'),novo_destino('NO','j')],
                   agrupamento=parametros())
        self.assertEqual(d['zonas'][0]['evidencia'],'DECLARADA')
        self.assertEqual(d['destinos'][1]['estado'],'SEM_CAMINHO')
        self.assertEqual(len(d['agrupamento']['percursos']),1)

    def test_rede_municipal_limita_destinos_e_preserva_uniao(self):
        d=agrupar(foto_municipal(128,ramificada=True),automatico=True,maximo=12)
        self.assertGreater(len(d['tubulacoes']),16_000)
        self.assertEqual(len(d['destinos']),12)
        self.confirmar_sequencias(d)

    def test_cancelamento_perifericos(self):
        with self.assertRaises(Cancelado):
            analisar(arvore(),agrupamento=parametros('AUTOMATICO'),cancelar=lambda:True)


class Arquivos(unittest.TestCase):
    def setUp(self):
        pasta=TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.raiz=Path(pasta.name)
        l=etapa2.linha
        ts=[l('00-A',(0,0),(10,0),80),l('00-B',(4,.02),(4,6),50),l('00-C',(20,20),(50,20),900)]
        bases=[('S',[('00-A',0.)])]
        antes=executar(ts,bases)
        cand=next(d for d in antes['diagnosticos'] if d['tipo']=='CONEXAO_T')
        regra=dict(uuid='T',rev='rt',tipo='CONEXAO',candidato=cand['uid'],portas=cand['portas'],
                   decisao='CONFIRMADA',situacao='INFORMADA')
        foto=executar(ts,bases,[regra])
        no=next(n['uid'] for n in foto['nos'] if ('00-B',1.) in n['portas'])
        self.antes=agrupar(antes,automatico=True)
        self.d=agrupar(foto,no)
        self.m=CorredoresNoMapa(GeometriasEstrutura(self.d))

    def test_t_confirmado_parte_virtual_e_exportacao_individual(self):
        r=next(iter(self.m.percursos.values()))
        c=self.m.corredores[r['corredores'][0]]
        self.assertEqual(len(c['segmentos']),2)
        self.assertEqual(len(c['tubos']),2)
        self.assertNotIn('00-B',self.antes['agrupamento']['corredores'][0]['tubos'])
        v=exportar_tracado(self.d,'CORREDOR',c['uid'],self.raiz,'GPKG')
        dados=ogr.Open(str(v/'tracado.gpkg'))
        camada=dados.GetLayer(0)
        self.assertEqual(camada.GetFeatureCount(),2)
        metros=sum(f.GetGeometryRef().Length() for f in camada)
        self.assertAlmostEqual(metros,9.98)
        dados=None
        with (v/'segmentos.csv').open(encoding='utf-8-sig',newline='') as entrada:
            rs=list(csv.DictReader(entrada))
        self.assertEqual([r['ordem'] for r in rs],['1','2'])
        self.assertNotIn('00-C',{r['pipe'] for r in rs})

    def test_exporta_percurso_com_pipes_completos_e_shapefile_autonomo(self):
        p=next(iter(self.m.percursos.values()))
        v=exportar_tracado(self.d,'PERCURSO',p['uid'],self.raiz,'ESRI Shapefile','PIPES')
        self.assertTrue(all((v/('tracado'+ext)).exists() for ext in ('.shp','.shx','.prj','.dbf','.cpg')))
        ds=ogr.Open(str(v/'tracado.shp'))
        layer=ds.GetLayer()
        self.assertEqual(layer.GetFeatureCount(),2)
        self.assertAlmostEqual(sum(f.GetGeometryRef().Length() for f in layer),15.98)
        self.assertTrue(all(len(layer.GetLayerDefn().GetFieldDefn(i).GetName())<=10
                            for i in range(layer.GetLayerDefn().GetFieldCount())))
        ds=None
        meta=json.loads((v/'execucao.json').read_text(encoding='utf8'))
        self.assertEqual(meta['geometria'],'PIPES')
        self.assertEqual(meta['percurso']['uid'],p['uid'])
        self.assertIsInstance(meta['fontes'],list)

    def test_reabertura_identidade_e_revisao_de_nome(self):
        p=self.raiz/'estrutura.gpkg'
        pg.salvar_estrutura(p,self.d)
        foto=pg.carregar_estrutura(p,self.d['uuid'],self.d['projeto_uid'])
        u=next(iter(self.m.corredores))
        self.assertEqual(foto['agrupamento'],self.d['agrupamento'])
        base=self.raiz/'historico.gpkg'
        pg.criar_complementos(base,self.d['projeto_uid'])
        r=pg.salvar_revisao(base,self.d['projeto_uid'],'CORREDOR_NOME',
                           dict(analise_uid=self.d['uuid'],nome='Tronco Norte'),u)
        pg.salvar_revisao(base,self.d['projeto_uid'],'CORREDOR_NOME',
                         dict(analise_uid=self.d['uuid'],nome='Tronco Norte revisto'),u,r['rev'])
        nomes=pg.revisoes(base,self.d['projeto_uid'],u,tipo='CORREDOR_NOME')
        self.assertEqual([n['nome'] for n in nomes],['Tronco Norte','Tronco Norte revisto'])
        saida=exportar_tracado(foto,'CORREDOR',u,self.raiz,'CSV',nomes={u:nomes[-1]})
        self.assertFalse((saida/'tracado.gpkg').exists())
        self.assertIn('Tronco Norte revisto',(saida/'corredores.csv').read_text(encoding='utf-8-sig'))

    def test_camadas_sem_duplicacao_e_realce_integral(self):
        self.addCleanup(QgsProject.instance().clear)
        a=self.m.publicar(self.m.preparar_camada())
        b=self.m.publicar(self.m.preparar_camada())
        self.assertEqual(a.id(),b.id())
        self.assertEqual(a.featureCount(),1)
        c=next(iter(self.m.corredores.values()))
        itens=self.m.destaque(c)
        self.assertAlmostEqual(itens[0][1].length(),9.98)
        self.assertEqual({p for p,_ in itens},{'tubo','inicio_corredor','fim_corredor'})


class Interface(unittest.TestCase):
    def test_mapa_integral_nome_e_reabertura_de_trabalho_antigo(self):
        fixture=etapa2.InterfaceGIS()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        c,t=fixture.c,fixture.t
        esperar=fixture.f.aguardar
        t.iniciar();esperar()
        self.assertTrue(c.abrir_estrutura(foto=t.dados))
        p=c.estrutura_gis
        p.calcular();esperar()
        anterior=c.projetos.atual()['bases'][-1]
        self.assertNotIn('agrupamento',p.dados)
        p.executar_macro_b.click();esperar()
        self.assertTrue(p.macro.corredores,p.status.text())
        r=p.registro()
        self.assertIsNotNone(r)
        p.tabela.doubleClicked.emit(p.tabela.model().index(0,0))
        centro=c.app.iface.mapCanvas().extent()
        for _,g in p.macro.destaque(r):
            self.assertTrue(centro.contains(g.boundingBox()))
        p.mostrar_macro();esperar()
        self.assertIsNotNone(p.camada_macro)
        p.tabela.doubleClicked.emit(p.tabela.model().index(0,0))
        self.assertAlmostEqual(p.camada_macro.opacity(),.24)
        c.limpar_mapa()
        self.assertEqual(p.camada_macro.opacity(),1.)
        with patch('auditoria_aplicacao.corredores_agrupados_ui.QInputDialog.getText',
                   return_value=('Ramal revisado',True)):
            p.renomear_corredor(r)
        self.assertIn('Ramal revisado',{f['Nome'] for f in p.camada_macro.getFeatures()})
        novo=c.projetos.atual()['bases'][-1]
        p.reabrir(anterior);esperar()
        self.assertIsNone(p.macro)
        p.reabrir(novo);esperar()
        self.assertEqual(p.macro.corredores[r['uid']]['nome'],'Ramal revisado')
