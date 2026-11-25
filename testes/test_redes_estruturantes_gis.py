"""Regressões sintéticas das funções estruturais e dos cortes de Pipe."""

import random
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import test_grafo_gis as etapa2
from auditoria_fronteiras.modelos import Cancelado
from auditoria_aplicacao.dependencias_gis import RedeGIS, avaliar_cortes, simular
from auditoria_aplicacao.corredores_gis import analisar, comparar_estruturas, novo_destino, testar_interrupcao as interromper
from auditoria_aplicacao import persistencia_grafo_gis as pg
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsGeometry, QgsPointXY, QgsProject


def executar(tubos,origens=(),conexoes=()):
    fontes=[dict(uuid=u,tipo='ORIGEM',situacao='INFORMADA',rev='r'+u,portas=ps) for u,ps in origens]
    d=etapa2.construir(tubos,origens=fontes,conexoes=conexoes)
    d.update(participantes=[*fontes,*conexoes],projeto_uid='projeto-teste',uuid='topologia',crs='EPSG:31983')
    return d


def rede_arestas(arestas,origens=()):
    tubos=[dict(uid=t,comprimento_m=sum(m for _,_,p,m in arestas if p==t))
           for t in sorted({t for _,_,t,_ in arestas})]
    nos={u:[] for a,b,_,_ in arestas for u in (a,b)}
    fontes=[]
    for nome,u in origens:
        porta=(nome,0.)
        nos[u].append(porta)
        fontes.append(dict(uuid=nome,tipo='ORIGEM',situacao='INFORMADA',portas=[porta],rev=nome+'-1'))
    return dict(tubos=tubos,nos=[dict(uid=u,portas=p,xy=[i,0.]) for i,(u,p) in enumerate(nos.items())],
                arestas=[dict(a=a,b=b,tubo=t,comprimento_m=m) for a,b,t,m in arestas],
                origens_validas=[r['uuid'] for r in fontes],participantes=fontes,
                projeto_uid='projeto-teste',uuid='topologia',crs='EPSG:31983')


class Cortes(unittest.TestCase):
    def test_rede_ramificada_prioriza_funcao_em_vez_do_diametro(self):
        l=etapa2.linha
        d=executar([l('alimentador',(0,0),(1,0),30),l('malha',(1,0),(20,0),200),
                    l('ramal',(1,0),(1,4)),l('isolada',(15,3),(20,3),800)],
                   [('entrada',[('alimentador',0.)])])
        r=RedeGIS(d)
        cortes,dfs,_=avaliar_cortes(r,{})
        self.assertEqual(cortes['alimentador']['perda_m'],23)
        self.assertEqual(cortes['alimentador']['afetadas'],2)
        self.assertEqual(cortes['isolada']['perda_m'],0)
        self.assertEqual(len(dfs.articulacoes),1)
        self.assertEqual(len(dfs.componentes),2)

    def test_duas_fontes_preservam_alcance_mas_perdem_uma_origem(self):
        d=rede_arestas([('a','x','ax',4),('x','y','xy',2),('y','b','yb',5)],[('fonte A','a'),('fonte B','b')])
        r=RedeGIS(d)
        ds=r.destinos([dict(uid='alvo',tipo='NO',ref='y')])
        cortes,_,_=avaliar_cortes(r,ds)
        self.assertEqual(cortes['xy']['perda_m'],0)
        self.assertEqual(cortes['xy']['componentes_novos'],1)
        self.assertEqual(cortes['xy']['fontes_perdidas'],['fonte A','fonte B'])
        self.assertEqual(simular(r,['xy'],ds)['destinos'][0]['depois'],['fonte B'])

    def test_multigrafo_paralelas_anel_e_pipe_agrupado(self):
        d=rede_arestas([('a','b','compartilhado',1),('b','c','compartilhado',1),
                        ('a','b','alternativa',2),('b','c','bc',2),
                        ('a','e','compartilhado',1),('c','e','ce',1),('c','d','cd',2)],[('fonte','a')])
        r=RedeGIS(d)
        alvo=r.destinos([dict(uid='d',tipo='NO',ref='d')])
        cortes,dfs,_=avaliar_cortes(r,alvo)
        self.assertEqual(len(dfs.pontes),1)
        self.assertEqual(cortes['compartilhado']['componentes_novos'],0)
        self.assertEqual(cortes['cd']['destinos_afetados'],1)
        self.assertEqual(simular(r,['compartilhado','bc'],alvo)['perda_m'],3)

    def test_divisao_virtual_e_origem_multiplas_portas(self):
        l=etapa2.linha
        ts=[l('a',(0,0),(10,0)),l('b',(4,4),(4,.05)),l('isolado',(25,25),(26,25))]
        base=executar(ts)
        c=next(d for d in base['diagnosticos'] if d['tipo']=='CONEXAO_T')
        regra=dict(uuid='t',rev='1',tipo='CONEXAO',candidato=c['uid'],portas=c['portas'],decisao='CONFIRMADA')
        d=executar(ts,[('origem',[('a',0.),('isolado',1.)])],[regra])
        r=RedeGIS(d)
        cortes,dfs,_=avaliar_cortes(r,{})
        self.assertEqual(len(dfs.componentes),2)
        self.assertEqual(len(r.pipes['a']),2)
        self.assertAlmostEqual(cortes['a']['perda_m'],3.95)
        self.assertEqual(cortes['a']['afetadas'],1)
        limitado,_,_=avaliar_cortes(r,{},orcamento=0)
        self.assertEqual(limitado['a']['estado'],'INDETERMINADA_LIMITE')
        self.assertNotIn('perda_m',limitado['a'])

    def test_cortes_por_intervalo_correspondem_a_busca_exata(self):
        g=random.Random(417)
        for tentativa in range(45):
            arestas=[(str(i-1),str(i),str(i),g.randint(1,11)) for i in range(1,9)]
            for j in range(tentativa % 5):
                u,v=sorted(g.sample(range(9),2))
                arestas.append((str(u),str(v),f'extra{j//2}',g.randint(1,17)))
            origens=[(f'f{i}',str(g.randrange(9))) for i in range(tentativa % 4)]
            rede=RedeGIS(rede_arestas(arestas,origens))
            destinos=rede.destinos([dict(uid='d1',tipo='NO',ref='2'),dict(uid='d2',tipo='PIPE',ref='7')])
            cortes,_,antes=avaliar_cortes(rede,destinos)
            for f,corte in cortes.items():
                esperado=simular(rede,[f],destinos,antes=antes)
                for k in ('componentes_novos','perda_m','afetadas','destinos_afetados','destinos_retirados'):
                    self.assertEqual(corte[k],esperado[k],(f,arestas,origens,k))

    def test_cancelamento_antes_de_calcular(self):
        rede=RedeGIS(rede_arestas([('a','b','t',5)]))
        with self.assertRaises(Cancelado):avaliar_cortes(rede,{},cancelar=lambda:True)

    def test_malha_municipal_sem_pontes_e_sem_varrer_um_corte_por_pipe(self):
        from medir_estrutura_gis import foto_municipal
        foto=foto_municipal(127)
        self.assertEqual(len(foto['tubos']),32004)
        with patch('auditoria_aplicacao.dependencias_gis.simular') as busca:
            d=analisar(foto)
        busca.assert_not_called()
        self.assertEqual(len(d['tubulacoes']),32004)
        self.assertEqual(d['pontes_segmentos'],0)
        self.assertFalse(d['articulacoes'])


class Rotas(unittest.TestCase):
    def test_anel_verifica_independencia_por_feicao_fisica(self):
        ds=[novo_destino('NO','d')]
        base=[('s','a','x',1),('a','d','ad',1),('s','b','y',2),('b','d','bd',2)]
        d=rede_arestas(base,[('origem','s')])
        r=analisar(d,destinos=ds)
        p=r['rotas'][0]
        self.assertEqual(p['alternativa_estado'],'DISJUNTA_VERIFICADA')
        self.assertFalse(set(p['tubos']) & set(p['alternativa']['tubos']))
        # Uma segunda aresta pode representar a mesma feição GIS multipartes.
        d['tubos'][next(i for i,t in enumerate(d['tubos']) if t['uid']=='x')]['feicao']='mesmo'
        d['tubos'][next(i for i,t in enumerate(d['tubos']) if t['uid']=='y')]['feicao']='mesmo'
        p=analisar(d,destinos=ds)['rotas'][0]
        self.assertEqual(p['alternativa_estado'],'PARCIAL_VERIFICADA')
        self.assertEqual(set(p['tubos']) & set(p['alternativa']['tubos']),{'mesmo'})

    def test_alternativa_parcial_atras_de_trecho_obrigatorio(self):
        d=rede_arestas([('o','s','entrada',1),('s','a','x',1),('a','d','ad',1),
                        ('s','b','y',3),('b','d','bd',2)],[('origem','o')])
        r=analisar(d,destinos=[novo_destino('NO','d')])
        p=r['rotas'][0]
        self.assertEqual(p['alternativa_estado'],'PARCIAL_VERIFICADA')
        self.assertIn('entrada',p['alternativa']['tubos'])
        self.assertEqual(r['destinos'][0]['criticas'],['entrada'])

    def test_duas_fontes_alcancam_zona_com_dependencias_distintas(self):
        foto=rede_arestas([('a','x','ax',1),('x','b','xb',2)],[('fA','a'),('fB','b')])
        foto['areas']=[dict(uid='zona',label='B'),dict(uid='sem',label='Sem alvo')]
        d=novo_destino('NO','x',zona='zona')
        r=analisar(foto,destinos=[d])
        self.assertEqual(r['zonas'][0]['origens'],['fA','fB'])
        self.assertEqual(r['zonas'][1]['estado'],'SEM_DESTINO')
        self.assertEqual(r['destinos'][0]['dependencias_fontes'],{'fA':['ax'],'fB':['xb']})
        self.assertFalse(r['destinos'][0]['criticas'])
        self.assertEqual(analisar(foto,['fA'],[d])['destinos'][0]['criticas'],['ax'])

    def test_passagem_requer_zona_declarada_e_pode_coexistir_com_funcao_local(self):
        l=etapa2.linha
        t=l('p',(0,0),(15,0))
        t['zonas_uids']=['A','B']
        foto=executar([t],[('f',[('p',0.)])])
        foto['areas']=[dict(uid='A', label='Setor A', wkb=bytes(QgsGeometry.fromWkt(
            'POLYGON((2 -2,7 -2,7 2,2 2,2 -2))').asWkb()).hex()),
            dict(uid='B',label='Setor B', wkb=bytes(QgsGeometry.fromWkt(
                'POLYGON((9 -2,16 -2,16 2,9 2,9 -2))').asWkb()).hex())]
        fim=next(n['uid'] for n in foto['nos'] if ('p',1.) in n['portas'])
        le=analisar(foto,destinos=[novo_destino('NO',fim,zona='B',modo='ESPACIAL')])['tubulacoes'][0]
        self.assertEqual(le['travessias'],['A','B'])
        self.assertNotIn('PASSAGEM',le['funcoes'])
        visto=analisar(foto,destinos=[novo_destino('NO',fim,zona='B')])['tubulacoes'][0]
        self.assertEqual(visto['zonas_passagem'],['A'])
        self.assertTrue({'LOCAL','PASSAGEM','CORREDOR'}<=set(visto['funcoes']))

    def test_fonte_afastada_conserva_no_declarado(self):
        foto=executar([etapa2.linha('x',(0,0),(5,0))],[('suplementar',[('x',0.)])])
        foto['participantes'][0]['xy']=[8000.,9000.]
        a=next(n['uid'] for n in foto['nos'] if ('x',1.) in n['portas'])
        p=analisar(foto,destinos=[novo_destino('NO',a)])['rotas'][0]
        self.assertEqual(p['comprimento_m'],5.)
        self.assertEqual(p['origem'],'suplementar')


class Trabalhos(unittest.TestCase):
    def test_interrupcoes_duplas_em_anel_e_recuperacao_de_trajeto(self):
        d=rede_arestas([('s','a','x',1),('a','d','ad',1),('s','b','y',2),
                      ('b','d','bd',2),('d','e','ramal',5)],[('f','s')])
        r=analisar(d,destinos=[novo_destino('NO','d'),novo_destino('PIPE','x')])
        principal=r['destinos'][0]['uid']
        teste=interromper(r,['x'])
        self.assertEqual(teste['destinos_retirados'],1)
        self.assertEqual(teste['destinos_afetados'],0)
        self.assertEqual(teste['novas_rotas'][principal]['tubos'],['y','bd'])
        dupla=interromper(r,['x','y'])
        self.assertEqual(dupla['perda_m'],8)
        self.assertEqual(dupla['destinos_afetados'],1)
        self.assertEqual(len(dupla['componentes']),2)
        self.assertFalse(dupla['novas_rotas'])
        self.assertEqual(len(r['foto']['arestas']),5)

    def test_comparacao_de_hipoteses_preserva_evidencias(self):
        foto=rede_arestas([('a','x','ax',1),('x','b','xb',2),('b','c','bc',5)],
                          [('fA','a'),('fB','b')])
        foto['areas']=[dict(uid='z',label='Zona')]
        ds=[novo_destino('NO','x',zona='z')]
        a=analisar(foto,['fA'],ds)
        b=analisar(foto,['fA','fB'],ds)
        dif=comparar_estruturas(a,b)
        self.assertIn(('DEIXOU_CRITICA','ax'),[(r['tipo'],r['ref']) for r in dif])
        self.assertIn('ZONA_DEPENDENCIAS',{r['tipo'] for r in dif})
        self.assertEqual(a['zonas'][0]['origens_exclusivas'],['fA'])
        self.assertEqual(b['zonas'][0]['origens_exclusivas'],[])

    def test_conexao_candidata_so_comparece_depois_de_confirmada(self):
        l=etapa2.linha
        tubos=[l('principal',(0,0),(10,0)),l('ramal',(5,0.1),(5,10))]
        fontes=[('A',[('principal',0.)])]
        a=executar(tubos,fontes)
        cand=next(d for d in a['diagnosticos'] if d['tipo']=='CONEXAO_T')
        regra=dict(uuid='conexao',rev='rev',tipo='CONEXAO',situacao='INFORMADA',
                   candidato=cand['uid'],portas=cand['portas'],decisao='CONFIRMADA')
        b=executar(tubos,fontes,[regra])
        alvo=[novo_destino('PIPE','ramal')]
        primeiro=analisar(a,destinos=alvo);segundo=analisar(b,destinos=alvo)
        self.assertEqual(primeiro['destinos'][0]['estado'],'SEM_CAMINHO')
        self.assertEqual(segundo['destinos'][0]['estado'],'ALCANCAVEL')
        self.assertIn('CONEXAO_APLICADA',{r['tipo'] for r in comparar_estruturas(primeiro,segundo)})

    def test_gravacao_recuperacao_exportacao_e_cancelamento(self):
        import json
        from osgeo import ogr
        from auditoria_aplicacao.representacao_estrutura_gis import exportar, carregar_camadas, GeometriasEstrutura
        from auditoria_aplicacao.contexto_trabalho import Projetos, validar_registro
        from auditoria_topologica_watergems.gerenciamento import identificar
        with TemporaryDirectory() as tmp:
            raiz=Path(tmp);projetos=Projetos(raiz)
            projeto=projetos.criar('Rede de teste')
            foto=executar([etapa2.linha('00-A',(0,0),(5,0)),etapa2.linha('00-B',(5,0),(15,0))],
                         [('origem',[('00-A',0.)])])
            foto.update(projeto_uid=projeto['uuid'])
            fim=next(n['uid'] for n in foto['nos'] if ('00-B',1.) in n['portas'])
            trabalho=analisar(foto,destinos=[novo_destino('NO',fim)])
            trabalho['interrupcao']=interromper(trabalho,['00-A'])
            arq=raiz/'estruturas.gpkg'
            with self.assertRaises(Cancelado):pg.salvar_estrutura(arq,trabalho,lambda:True)
            self.assertEqual(list(raiz.glob('*.gpkg')),[])
            pg.salvar_estrutura(arq,trabalho)
            r=identificar(arq)[0]
            self.assertEqual(r['tipo'],'ESTRUTURA_GIS')
            self.assertTrue(validar_registro(r)['valido'])
            projetos.vincular(r)
            mf=raiz/'Teste.wna';projetos.salvar_manifesto(mf)
            (raiz/'outro').mkdir()
            outro=Projetos(raiz/'outro')
            outro.abrir_manifesto(mf)
            base=outro.atual()['bases'][0]
            self.assertEqual(base['nome'],trabalho['nome'])
            d=pg.carregar_estrutura(base['base'],base['uuid'],projeto['uuid'])
            self.assertEqual(d['interrupcao']['perda_m'],10)
            self.assertEqual(d['tubulacoes'],trabalho['tubulacoes'])
            with self.assertRaisesRegex(ValueError,'outro projeto'):
                pg.carregar_estrutura(arq,base['uuid'],'outra')
            g=exportar(d,tmp,'GPKG')
            b=exportar(d,tmp,'ESRI Shapefile')
            gpkg=ogr.Open(str(g/'estrutura.gpkg'))
            self.assertEqual(gpkg.GetLayerByName('corredor').GetFeatureCount(),2)
            self.assertEqual(gpkg.GetLayerByName('destinos').GetFeatureCount(),1)
            gpkg=None
            self.assertTrue(all((b/('corredor'+e)).exists() for e in ('.shp','.shx','.dbf','.prj','.cpg')))
            self.assertEqual(json.loads((g/'execucao.json').read_text(encoding='utf-8'))['interrupcao']['retiradas'],['00-A'])
            projeto_qgis=QgsProject.instance()
            self.addCleanup(projeto_qgis.clear)
            carregar_camadas(d,GeometriasEstrutura(d))
            antes=set(projeto_qgis.mapLayers())
            carregar_camadas(d,GeometriasEstrutura(d))
            self.assertEqual(set(projeto_qgis.mapLayers()),antes)


class Interface(unittest.TestCase):
    def setUp(self):
        self.f=etapa2.InterfaceGIS()
        self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.c=self.f.c
        t=self.f.t
        t.iniciar();self.f.f.aguardar()
        self.assertIsNotNone(t.dados,t.status.text())
        self.assertTrue(self.c.abrir_estrutura(foto=t.dados))
        self.p=self.c.estrutura_gis

    def test_destino_no_mapa_interrupcao_e_reabertura(self):
        p=self.p
        p.selecao_tipo.setCurrentIndex(p.selecao_tipo.findData('NO'))
        p.selecionar_mapa();self.f.f.aguardar()
        self.assertIsNotNone(p._ferramenta,p.status.text())
        n=next(iter(p.nos_foto.values()))
        ferramenta=p._ferramenta[1]
        ferramenta.canvasClicked.emit(QgsPointXY(*n['xy']),Qt.LeftButton)
        ferramenta.canvasClicked.emit(QgsPointXY(*n['xy']),Qt.RightButton)
        self.assertEqual(len(p._destinos),1)
        p.calcular();self.f.f.aguardar()
        self.assertIsNotNone(p.dados,p.status.text())
        self.assertEqual(len(p.dados['destinos']),1)
        p.tabela.doubleClicked.emit(p.tabela.indexAt(p.tabela.visualItemRect(p.tabela.item(0,0)).center()))
        self.assertTrue(self.c.mapa.itens)
        uid=p.dados['tubulacoes'][0]['uid']
        p.testar_pipe(uid);self.f.f.aguardar()
        self.assertIsNotNone(p.interrupcao,p.status.text())
        p.salvar_teste();self.f.f.aguardar()
        r=self.c.projetos.atual()['bases'][-1]
        self.assertEqual(r['tipo'],'ESTRUTURA_GIS')
        self.assertEqual(r['uuid'],p.dados['uuid'])
        p.categoria.setCurrentIndex(p.categoria.findData('DESTINOS'))
        p.reabrir(r);self.f.f.aguardar()
        self.assertEqual(p.dados['uuid'],r['uuid'])
        self.assertEqual(p.interrupcao['retiradas'],[uid])

    def test_cancelamento_conserva_catalogo_e_revisao_alerta(self):
        p=self.p
        with patch('auditoria_aplicacao.estrutura_gis_ui.motor.analisar',side_effect=Cancelado('Cancelada')):
            p.calcular();self.f.f.aguardar()
        self.assertFalse(any(r['tipo']=='ESTRUTURA_GIS' for r in self.c.projetos.atual()['bases']))
        self.f.f.m.estrategia.setCurrentIndex(self.f.f.m.estrategia.findData('CADASTRADAS'))
        self.assertTrue(self.f.f.m.salvar())
        p.descrever_foto()
        self.assertIn('outra revisão',p.identidade.text())

    def test_detecta_mudanca_no_conteudo_sem_recomputar_topologia(self):
        p=self.p
        p.conferir_fontes();self.f.f.aguardar()
        self.assertIn('corresponde',p.status.text())
        camada=self.f.f.redes[0]
        f=next(camada.getFeatures())
        g=f.geometry()
        g.translate(0,3)
        self.assertTrue(camada.dataProvider().changeGeometryValues({f.id():g}))
        p.conferir_fontes();self.f.f.aguardar()
        self.assertIn('Conteúdo das fontes mudou',p.status.text())
        self.assertEqual(p.foto['assinatura_inventario'],self.f.t.dados['assinatura_inventario'])
