"""Casos sintéticos da topologia independente e da abertura de projetos."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from test_auditoria_fronteiras import APP, camada, quadrado
from qgis.core import QgsGeometry, QgsProject, QgsCoordinateReferenceSystem, QgsCoordinateTransformContext
from qgis.PyQt.QtCore import Qt
from auditoria_aplicacao.grafo_gis import construir
from auditoria_aplicacao.contexto_trabalho import Projetos
from auditoria_aplicacao import persistencia_grafo_gis as pg


def tubo(uid, wkt, diametro=None):
    return dict(uid=uid, geom=QgsGeometry.fromWkt(wkt), diametro_mm=diametro)


def linha(uid, a, b, diametro=None):
    return tubo(uid, f'LINESTRING({a[0]} {a[1]},{b[0]} {b[1]})', diametro)


class GrafoGIS(unittest.TestCase):
    def test_rede_sem_origens(self):
        r = construir([linha('a',(0,0),(5,0)),linha('b',(5,0),(6,1))])
        self.assertEqual(len(r['componentes']),1)
        self.assertEqual(r['componentes'][0]['situacao'],'SEM_ORIGENS_VALIDAS')
        self.assertFalse(any(d['tipo']=='SEM_ORIGEM' for d in r['diagnosticos']))

    def test_prioridade_5km_e_5m(self):
        r = construir([linha('a',(0,0),(5,0)),linha('b',(0,5),(5000,5))])
        self.assertEqual([c['comprimento_m'] for c in r['componentes']],[5000.,5.])
        self.assertEqual(r['diagnosticos'][0]['tipo'],'COMPONENTE_INDEPENDENTE')

    def test_nenhuma_uniao_por_encadeamento(self):
        ts = [linha('a',(0,0),(0,4)),linha('b',(.15,0),(.15,-4)),linha('c',(.30,0),(.30,4))]
        r = construir(ts,inferir_proximas=True)
        self.assertEqual(len(r['componentes']),3)
        self.assertEqual(sum(d['tipo']=='EXTREMIDADES_PROXIMAS' for d in r['diagnosticos']),2)

    def test_t_candidato_e_divisao_virtual_explicita(self):
        ts = [linha('a',(0,0),(10,0)),linha('b',(4,4),(4,.05))]
        r = construir(ts)
        c = next(d for d in r['diagnosticos'] if d['tipo']=='CONEXAO_T')
        self.assertAlmostEqual(c['distancia_m'],.05)
        self.assertEqual(len(r['componentes']),2)
        regra = dict(uuid='conexao', rev='1', candidato=c['uid'], portas=c['portas'])
        unido = construir(ts,conexoes=[regra])
        self.assertEqual(len(unido['componentes']),1)
        self.assertEqual(len(unido['arestas']),3)
        self.assertAlmostEqual(unido['componentes'][0]['comprimento_m'],13.95)
        self.assertEqual(unido['componentes'][0]['quantidade_tubos'],2)
        self.assertEqual(len(unido['ramos']),1)

    def test_cruzamento_interior_nao_une(self):
        r = construir([linha('a',(0,0),(10,0)),linha('b',(5,-5),(5,5))])
        self.assertEqual(len(r['componentes']),2)
        self.assertIn('CRUZAMENTO',{d['tipo'] for d in r['diagnosticos']})
        self.assertNotIn('CONEXAO_T',{d['tipo'] for d in r['diagnosticos']})

    def test_sobreposicao(self):
        r = construir([linha('a',(0,0),(10,0)),linha('b',(5,0),(15,0))])
        self.assertIn('SOBREPOSICAO',{d['tipo'] for d in r['diagnosticos']})

    def test_origem_alcanca_componente_e_diametro_isolado(self):
        ts = [linha('a',(0,0),(10,0),250),linha('b',(0,5),(5,5),300)]
        r = construir(ts,origens=[dict(uuid='reservatorio',portas=[('a',0.)])])
        por_tubo = {c['tubos'][0]:c for c in r['componentes']}
        self.assertEqual(por_tubo['a']['origens'],['reservatorio'])
        self.assertEqual(por_tubo['b']['situacao'],'SEM_ORIGEM_ALCANCAVEL')
        self.assertEqual([d['tubos'] for d in r['diagnosticos'] if d['tipo']=='REDE_PRINCIPAL'],[['b']])

    def test_multiplas_origens_e_multiplas_portas(self):
        ts=[linha('a',(0,0),(10,0)),linha('b',(0,5),(5,5))]
        fontes=[dict(uuid='afastada',portas=[('a',.5),('b',1.)],xy=[999,999]),
                dict(uuid='segunda',portas=[('b',0.)])]
        r=construir(ts,origens=fontes)
        self.assertEqual([c['origens'] for c in r['componentes']],[['afastada'],['afastada','segunda']])
        self.assertEqual(len(r['componentes']),2)
        self.assertAlmostEqual(sum(c['comprimento_m'] for c in r['componentes']),15.)

    def test_conexao_manual_entre_trechos_distantes(self):
        ts=[linha('a',(0,0),(10,0)),linha('b',(0,5),(5,5))]
        r=construir(ts,conexoes=[dict(uuid='ponte',rev='r',portas=[('a',1.),('b',0.)])])
        self.assertEqual(len(r['componentes']),1)
        self.assertAlmostEqual(r['componentes'][0]['comprimento_m'],15.)

    def test_referencia_alterada_nao_conecta(self):
        r=construir([linha('a',(0,0),(10,0))],origens=[dict(uuid='afastada',portas=[('alterada',0.)])])
        self.assertEqual(r['origens_validas'],[])
        self.assertIn('EQUIPAMENTO_PENDENTE',{d['tipo'] for d in r['diagnosticos']})

    def test_limites_de_tolerancia_e_inferencia_optativa(self):
        a=linha('a',(0,0),(5,0))
        b=linha('b',(5.19,0),(8,0))
        c=linha('c',(8.21,0),(11,0))
        sem=construir([a,b,c]);com=construir([a,b,c],inferir_proximas=True)
        self.assertEqual(len(sem['componentes']),3)
        self.assertEqual(len(com['componentes']),2)
        self.assertEqual(sum(d['tipo']=='EXTREMIDADES_PROXIMAS' for d in sem['diagnosticos']),1)

    def test_manter_pontas_separadas_prevalece_sobre_inferencia(self):
        ts=[linha('a',(0,0),(5,0)),linha('b',(5.19,0),(8,0))]
        candidato=next(d for d in construir(ts)['diagnosticos'] if d['tipo']=='EXTREMIDADES_PROXIMAS')
        r=dict(uuid='separacao',rev='rev',decisao='SEPARADA',candidato=candidato['uid'],
               categoria_candidata=candidato['tipo'],portas=candidato['portas'])
        separado=construir(ts,inferir_proximas=True,conexoes=[r])
        self.assertEqual(len(separado['componentes']),2)
        self.assertIn('SEPARADA',{d['situacao'] for d in separado['diagnosticos']})

    def test_junction_unica_e_ambiguidades(self):
        ts=[linha('a',(0,0),(5,0)),linha('b',(5.1,0),(8,0))]
        ancora=lambda uid,x:dict(uid=uid,geom=QgsGeometry.fromWkt(f'POINT({x} 0)'))
        uma=construir(ts,[ancora('j',5.05)],estrategia='CADASTRADAS')
        duas=construir(ts,[ancora('j',5.05),ancora('k',5.06)],estrategia='COMBINAR')
        self.assertEqual(len(uma['componentes']),1)
        self.assertEqual(len(duas['componentes']),2)

    def test_varios_t_candidatos(self):
        ts=[linha('a',(0,0),(10,0)),linha('b',(0,-.1),(10,-.1)),linha('c',(4,4),(4,.01))]
        r=construir(ts)
        self.assertEqual(sorted(d['concorrentes'] for d in r['diagnosticos'] if d['tipo']=='CONEXAO_T'),[1,1])

    def test_malha_com_acesso_e_sem_contagem_duplicada(self):
        coords=[(0,0),(10,0),(10,10),(0,10),(0,0)]
        r=construir([linha(str(i),a,b,250) for i,(a,b) in enumerate(zip(coords,coords[1:]))],
                    origens=[dict(uuid='fonte',portas=[('0',0.)])])
        self.assertEqual(len(r['componentes']),1)
        g=r['componentes'][0]
        self.assertEqual(g['situacao'],'ALCANCAVEL')
        self.assertEqual((len(g['nos']),g['quantidade_tubos'],g['comprimento_m']),(4,4,40.))

    def test_cancelamento(self):
        from auditoria_fronteiras.modelos import Cancelado
        with self.assertRaises(Cancelado):
            construir([linha('a',(0,0),(10,0))],cancelar=lambda:True)

    def test_zonas_intersectadas_sem_mistura_operacional(self):
        from auditoria_aplicacao.entradas_grafo_gis import preparar
        from auditoria_aplicacao.executar_grafo_gis import executar
        from auditoria_aplicacao.modelo_gis import configurar,descrever
        rede=camada('LineString',['LINESTRING(-5 4,15 4)'],nome='Rede')
        area=camada('Polygon',[quadrado()],nome='Zona')
        fs=[configurar(descrever(c),tipo,'EXISTENTE','',{'id':'id','label':'nome'})
            for c,tipo in [(rede,'PIPE'),(area,'SETOR')]]
        prep=preparar(fs,[rede,area],'EPSG:31983',QgsCoordinateTransformContext())
        r=executar(prep,dict(projeto_uid='p',nome='Teste'),{},[])
        self.assertTrue(r['componentes'][0]['zonas'])
        self.assertNotIn('MISTURA_SETORES',{d['tipo'] for d in r['diagnosticos']})

    def test_mistura_exige_conexao_declarada_e_atributos_operacionais(self):
        ts=[dict(linha('a',(0,0),(10,0)),setor_operacional='A'),
            dict(linha('b',(0,5),(5,5)),setor_operacional='B')]
        regra=dict(uuid='c',rev='1',portas=[('a',1.),('b',0.)])
        self.assertNotIn('MISTURA_SETORES',{d['tipo'] for d in construir(ts)['diagnosticos']})
        r=construir(ts,conexoes=[regra])
        c=next(d for d in r['diagnosticos'] if d['tipo']=='MISTURA_SETORES')
        self.assertEqual(c['setores_declarados'],['A','B'])

    def test_fontes_crs_distintos_e_unidades_explicitas(self):
        from auditoria_aplicacao.entradas_grafo_gis import preparar,ler
        from auditoria_aplicacao.modelo_gis import configurar,descrever
        r=camada('LineString',['LINESTRING(-46 -23,-46.00001 -23)'],ids=[25],crs='EPSG:4326')
        f=configurar(descrever(r),'PIPE','EXISTENTE','',{'id':'id','diametro':'id'})
        def obter(unidades):
            p=preparar([f],[r],'EPSG:31983',QgsCoordinateTransformContext(),unidades=unidades)
            return ler(p)[0][0]
        a,b=obter({}),obter({f['uid']:'cm'})
        self.assertTrue(1<a['geom'].length()<2)
        self.assertIsNone(a['diametro_mm'])
        self.assertEqual(b['diametro_mm'],250)


class InterfaceGIS(unittest.TestCase):
    def setUp(self):
        import test_nova_interface as fixture
        from test_integracao_modelo_gis import limpar_fixture
        self.f=fixture.AmbienteTest();self.f.setUp();self.addCleanup(limpar_fixture,self.f)
        self.f.cadastrar('PIPE',[self.f.redes[0]])
        self.assertTrue(self.f.m.salvar())
        self.c=self.f.c
        self.assertTrue(self.c.abrir_conectividade())
        self.t=self.c.conectividade_gis
        self.t.crs.setCrs(QgsCoordinateReferenceSystem('EPSG:31983'))

    def test_painel_salva_e_reabre_trabalho_sem_poligonos(self):
        self.t.iniciar();self.f.aguardar()
        self.assertIsNotNone(self.t.dados,self.t.status.text())
        r=self.c.projetos.atual()['bases'][-1]
        self.assertEqual(r['tipo'],'TOPOLOGIA_GIS')
        self.assertEqual(len(self.t.dados['componentes']),1)
        self.t.destacar()
        self.assertTrue(self.c.mapa.itens)
        self.t.dados=None
        self.t.reabrir(r);self.f.aguardar()
        self.assertEqual(self.t.dados['uuid'],r['uuid'])

    def test_contexto_mudou_apos_revisao(self):
        self.t.iniciar();self.f.aguardar()
        self.assertIsNotNone(self.t.dados,self.t.status.text())
        self.f.m.estrategia.setCurrentIndex(self.f.m.estrategia.findData('CADASTRADAS'))
        self.assertTrue(self.f.m.salvar())
        self.t.mostrar_contexto()
        self.assertIn('mudaram',self.t.resumo.text())

    def test_resultados_exportados_em_dois_formatos(self):
        from auditoria_aplicacao.exportar_grafo_gis import exportar
        self.t.iniciar();self.f.aguardar()
        self.assertIsNotNone(self.t.dados,self.t.status.text())
        with TemporaryDirectory() as pasta:
            a=exportar(self.t.dados,pasta,'GPKG')
            b=exportar(self.t.dados,pasta,'ESRI Shapefile')
            self.assertTrue((a/'topologia.gpkg').is_file())
            self.assertTrue(all((b/('tubulacoes'+ext)).is_file() for ext in ('.shp','.shx','.dbf','.prj','.cpg')))

    def test_manifesto_recarrega_estado_da_categoria_sem_cache(self):
        p=self.c.projetos
        arq=p.path.parent/'teste.wna'
        p.salvar_manifesto(arq)
        self.c.modelo_gis._fontes_sujas=False
        self.c.modelo_gis._estado={}
        self.c._manifesto_aberto()
        self.assertEqual(len(self.c.modelo_gis.fontes),1)

    def test_cancelamento_e_retomada_sem_execucao_parcial(self):
        from auditoria_fronteiras.modelos import Cancelado
        with patch('auditoria_aplicacao.topologia_gis_ui.executar',side_effect=Cancelado('Cancelada')):
            self.t.iniciar();self.f.aguardar()
        self.assertFalse(self.c.projetos.atual()['bases'])
        self.assertIsNone(self.t.dados)
        self.t.iniciar();self.f.aguardar()
        self.assertIsNotNone(self.t.dados,self.t.status.text())


class Manifesto(unittest.TestCase):
    def setUp(self):
        self.pasta = TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.raiz = Path(self.pasta.name)
        self.projetos = Projetos(self.raiz)

    def test_migra_legado_e_reabre_em_outro_indice(self):
        p = self.projetos.criar('Teste')
        self.projetos.vincular(dict(tipo='AUDITORIA_GIS', uuid='e',base=str(self.raiz/'inexistente.gpkg')))
        arquivo = self.raiz/'Teste.wna'
        self.projetos.salvar_manifesto(arquivo)
        bruto=json.loads(arquivo.read_text(encoding='utf8'))
        self.assertEqual(bruto['projeto']['bases'][0]['base'],'inexistente.gpkg')
        outra=self.raiz/'outra';outra.mkdir()
        aberto=Projetos(outra).abrir_manifesto(arquivo)
        self.assertEqual(aberto['uuid'],p['uuid'])
        self.assertEqual(Path(aberto['bases'][0]['base']),self.raiz/'inexistente.gpkg')

    def test_concorrencia_preserva_a_revisao_mais_recente(self):
        p=self.projetos.salvar_manifesto(self.raiz/'novo.wna','Novo')
        outra=Projetos(self.raiz)
        self.projetos.vincular(dict(tipo='AUDITORIA_GIS',uuid='a',base=str(self.raiz/'a.gpkg')))
        with self.assertRaisesRegex(ValueError,'outra sessão'):
            outra.vincular(dict(tipo='AUDITORIA_GIS',uuid='b',base=str(self.raiz/'b.gpkg')))
        self.assertEqual(Projetos(self.raiz).atual()['bases'][0]['uuid'],'a')

    def test_nao_sobrescreve_manifesto(self):
        arquivo=self.raiz/'protegido.wna';arquivo.write_bytes(b'existente')
        with self.assertRaises(FileExistsError):
            self.projetos.salvar_manifesto(arquivo,'Novo')
        self.assertEqual(arquivo.read_bytes(),b'existente')

    def test_pasta_movida_resolve_caminhos_internos_e_preserva_externos(self):
        pasta=self.raiz/'original'
        pasta.mkdir()
        externo=self.raiz/'externo.gpkg'
        p=self.projetos.salvar_manifesto(pasta/'rede.wna','Rede')
        self.projetos.vincular(dict(tipo='TOPOLOGIA_GIS',uuid='interna',base=str(pasta/'rede.gpkg')))
        self.projetos.vincular(dict(tipo='AUDITORIA_GIS',uuid='externa',base=str(externo)))
        destino=pasta.rename(self.raiz/'movida')
        aberto=self.projetos.abrir_manifesto(destino/'rede.wna')
        self.assertEqual(p['uuid'],aberto['uuid'])
        self.assertEqual({Path(r['base']) for r in aberto['bases']},{destino/'rede.gpkg',externo})

    def test_hipoteses_explicitas_e_historico_imutavel(self):
        base=self.raiz/'origens.gpkg'
        pg.criar_complementos(base,'projeto')
        dados=dict(nome='Reservatório distante',situacao='HIPOTETICA',categoria='RESERVOIR',
                   xy=[1000,1000],crs='EPSG:31983',portas=[['a',0.],['b',1.]])
        a=pg.salvar_revisao(base,'projeto','ORIGEM',dados)
        self.assertEqual(pg.selecionar(pg.vigentes(base,'projeto'),[]),[])
        self.assertEqual(pg.selecionar(pg.vigentes(base,'projeto'),[a['uuid']])[0]['rev'],a['rev'])
        nova=pg.salvar_revisao(base,'projeto','ORIGEM',dict(dados,habilitado=False),a['uuid'],a['rev'])
        self.assertEqual(nova['anterior'],a['rev'])
        with self.assertRaises(ValueError):
            pg.selecionar(pg.vigentes(base,'projeto'),[a['uuid']])
        with self.assertRaises(ValueError):
            pg.salvar_revisao(base,'projeto','ORIGEM',dados,a['uuid'],a['rev'])
        self.assertEqual(len(pg.revisoes(base,'projeto')),2)

    def test_salvar_carregar_sem_geometrias_de_entrada(self):
        base=self.raiz/'analise.gpkg'
        d=construir([linha('a',(0,0),(5,0))])
        d.update(uuid='analise',projeto_uid='projeto',nome='Rede',data_utc='2026-11-24')
        pg.salvar_execucao(base,d)
        self.assertEqual(pg.carregar(base,'analise','projeto')['componentes'],d['componentes'])
        with self.assertRaises(ValueError):pg.carregar(base,'analise','outro')


if __name__=='__main__':
    unittest.main()
