"""Regressões dos marcos de salvamento, traçado e blocos GIS."""

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox
from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransformContext, QgsGeometry

import test_grafo_gis as gis
from test_redes_estruturantes_gis import executar
from test_continuidade_projetos import foto

from auditoria_aplicacao import blocos_gis, estado_projeto, manifesto_projeto, persistencia_grafo_gis as pg
from auditoria_aplicacao import topologia_derivada, trabalhos_projeto as tp
from auditoria_aplicacao.copia_projeto import copiar
from auditoria_aplicacao.contexto_trabalho import Projetos
from auditoria_aplicacao.corredores_gis import analisar
from auditoria_aplicacao.grafo_gis import construir
from auditoria_aplicacao.representacao_blocos_gis import exportar, registros
from auditoria_aplicacao.representacao_estrutura_gis import GeometriasEstrutura
from auditoria_aplicacao.tubulacoes_propostas import preparar_propostas, validar
from auditoria_fronteiras.modelos import Cancelado


CRS = QgsCoordinateReferenceSystem('EPSG:31983')


def rede_proposta():
    tubos=[gis.linha('A',(0,0),(10,0)),gis.linha('B',(12,5),(12,9))]
    p=dict(uuid='nova',rev='revpipe',tipo='PIPE',nome='Tubulação proposta',situacao='PROPOSTA',
           portas=[['A',.5],['B',0.]],vertices=[[5,0],[6,3],[12,5]],crs=CRS.toWkt(),diametro=20,unidade_diametro='cm')
    return tubos,p


class Topologia(unittest.TestCase):
    def test_bends_e_divisao_no_interior(self):
        tubos,p=rede_proposta()
        novos,ligacoes,erros=preparar_propostas([p],tubos,CRS,QgsCoordinateTransformContext())
        self.assertFalse(erros)
        self.assertEqual(novos[0]['diametro_mm'],200)
        d=construir([*tubos,*novos],conexoes=ligacoes)
        self.assertEqual(len(d['componentes']),1)
        self.assertEqual(len(d['arestas']),4)
        n=next(n for n in d['nos'] if ('A',.5) in n['portas'])
        self.assertIn(('proposta:nova',0.),n['portas'])
        self.assertAlmostEqual(novos[0]['geom'].length(),(10**.5)+(40**.5))

    def test_geometria_alterada_rejeita_proposta_sem_union(self):
        tubos,p=rede_proposta()
        p['vertices'][-1]=[13,5]
        novos,ligacoes,erros=preparar_propostas([p],tubos,CRS,QgsCoordinateTransformContext())
        self.assertFalse(novos or ligacoes)
        self.assertIn('mudou',erros[0][1])
        self.assertEqual(len(construir(tubos)['componentes']),2)

    def test_proposta_protege_arestas_e_validacao_de_vertices(self):
        tubos,p=rede_proposta()
        p['vertices'].insert(1,[5,0])
        with self.assertRaisesRegex(ValueError,'nulo'):validar(p)
        p['vertices'].pop(1)
        tubos.append(gis.linha('C',(5,0),(5,-8)))
        novos,links,_=preparar_propostas([p],tubos,CRS,QgsCoordinateTransformContext())
        d=construir([*tubos,*novos],conexoes=links)
        self.assertEqual(len(d['componentes']),2)

    def test_multiplas_divisoes_e_exportacao(self):
        tubos,p=rede_proposta()
        novos,links,_=preparar_propostas([p],tubos,CRS,QgsCoordinateTransformContext())
        outra=dict(uuid='conexao',rev='r',decisao='CONFIRMADA',portas=[('A',.7),('B',.5)])
        foto_=construir([*tubos,*novos],conexoes=[*links,outra])
        foto_.update(uuid='execucao',projeto_uid='projeto',crs=CRS.toWkt(),algoritmo='teste')
        r,n,div,_=topologia_derivada.preparar(foto_)
        self.assertEqual(sorted(f for f,_ in div['A']),[.5,.7])
        self.assertEqual(sum(t['comprimento_m'] for t in r if t['original']=='A'),10)
        self.assertEqual(len({t['uid'] for t in r}),len(r))
        with TemporaryDirectory() as tmp:
            pasta=topologia_derivada.exportar(foto_,tmp)
            from osgeo import ogr
            ds=ogr.Open(str(pasta/'topologia.gpkg'))
            self.assertEqual(ds.GetLayerByName('pipes').GetFeatureCount(),len(r))
            self.assertEqual(ds.GetLayerByName('junctions').GetFeatureCount(),len(n))
            ds=None

    def test_blocos_malha_ramos_e_multifonte(self):
        l=gis.linha
        topo=executar([l('a',(0,0),(10,0)),l('b',(10,0),(10,10)),l('c',(10,10),(0,0)),
                       l('ramal',(10,10),(20,10)),l('ponta',(20,10),(30,10)),
                       l('isolada',(60,10),(61,10))],[('F1',[('a',0.)]),('F2',[('ponta',1.)])])
        d=analisar(topo);macro=blocos_gis.analisar(d);d['blocos']=macro
        self.assertEqual(len(macro['blocos']),3)
        anel=next(b for b in macro['blocos'] if b['tipo']=='MALHA')
        self.assertEqual(anel['origens'],['F1','F2'])
        self.assertEqual(anel['redundancia'],'MALHA_COM_PIPES_DISTINTOS')
        self.assertEqual(len(macro['ligacoes']),1)
        self.assertEqual(sum(len(b['segmentos']) for b in macro['blocos']),6)
        detalhado=blocos_gis.analisar(d,'DETALHADO')
        self.assertEqual(len(detalhado['blocos']),4)
        self.assertTrue(list(blocos_gis.comparar(macro,detalhado)))
        geo=GeometriasEstrutura(d)
        self.assertEqual(len(registros(geo,macro['blocos'])),3)
        with TemporaryDirectory() as tmp:
            for formato in ('GeoPackage','Shapefile','CSV'):
                p=exportar(d,geo,[anel],tmp,formato)
                self.assertTrue((p/'segmentos.csv').is_file())
        with self.assertRaises(Cancelado):blocos_gis.analisar(d,cancelar=lambda:True)

    def test_area_intersecta_so_segmentos_do_bloco_e_nao_recorta_grafo(self):
        l=gis.linha
        d=executar([l('A',(0,0),(20,0)),l('B',(20,0),(40,0))],[('F',[('A',0.)])])
        g=QgsGeometry.fromWkt('POLYGON((29 -2,35 -2,35 2,29 2,29 -2))')
        d['areas']=[dict(uid='poligono',wkb=bytes(g.asWkb()).hex())]
        r=blocos_gis.analisar(analisar(d),'DETALHADO')
        por_pipe={b['pipes'][0]:b for b in r['blocos']}
        self.assertFalse(por_pipe['A']['areas'])
        self.assertEqual(por_pipe['B']['areas'],['poligono'])
        self.assertEqual(por_pipe['B']['origens'],['F'])


class Persistencia(unittest.TestCase):
    def test_copia_independente_remapeia_trabalhos_sem_alterar_original(self):
        with TemporaryDirectory() as tmp:
            pasta=Path(tmp)
            p=Projetos(pasta)
            pr=p.salvar_manifesto(pasta/'Registro.wna','Registro')
            original=pr['uuid']
            caminho=pasta/'conectividade.gpkg'
            f=foto(original,'execucao')
            pg.salvar_execucao(caminho,f)
            p.vincular(tp.identificar(caminho)[0])
            d=analisar(f)
            estrut=pasta/'estrutural.gpkg'
            pg.salvar_estrutura(estrut,d)
            p.vincular(tp.identificar(estrut)[0])
            h=sha256(estrut.read_bytes()).digest()
            alvo,avisos,_=copiar(p.atual(),pasta/'copia'/'Registro.wna','INDEPENDENTE')
            novo=manifesto_projeto.ler(alvo)
            self.assertNotEqual(novo['uuid'],original)
            self.assertFalse(avisos)
            estrutural=pg.carregar_estrutura(novo['ultima']['base'],novo['ultima']['uuid'],novo['uuid'])
            execucao=next(r for r in novo['bases'] if r['tipo']=='TOPOLOGIA_GIS')
            self.assertEqual(estrutural['foto']['uuid'],execucao['uuid'])
            self.assertEqual(sha256(estrut.read_bytes()).digest(),h)

    def test_copia_opcional_de_fontes_e_referencia_relativa(self):
        import json
        from qgis.core import QgsVectorLayer
        from auditoria_aplicacao.modelo_gis import configurar,descrever,identificar,assinatura_confere
        with TemporaryDirectory() as tmp:
            raiz=Path(tmp)
            arq=raiz/'origem.geojson'
            arq.write_text(json.dumps(dict(type='FeatureCollection',features=[dict(type='Feature',
                  geometry=dict(type='LineString',coordinates=[[0,0],[1,1]]),properties=dict(codigo='1'))])),encoding='utf-8')
            fonte=configurar(descrever(QgsVectorLayer(str(arq),'Rede','ogr')),'PIPE','EXISTENTE','DISTRIBUICAO',{'id':'codigo'})
            p=Projetos(raiz)
            p.salvar_manifesto(raiz/'Registro.wna','Registro')
            p.atual()['modelo_gis']=dict(revisoes=[dict(fontes=[fonte])])
            p.salvar()
            alvo,_,_=copiar(p.atual(),raiz/'copia'/'Registro.wna','PORTATIL',incorporar=True)
            novo=manifesto_projeto.ler(alvo)
            base=novo['modelo_gis']['revisoes'][0]['fontes'][0]
            self.assertTrue(Path(base['uri_portatil']).is_relative_to(alvo.parent))
            c=QgsVectorLayer(base['uri_portatil'],'Rede copiada','ogr')
            self.assertIs(identificar(base,[c]),c)
            self.assertTrue(assinatura_confere(base,descrever(c)))
            self.assertEqual(base['origem_estavel'],fonte['origem_estavel'])
            from qgis.PyQt import sip
            sip.delete(c)


class Interface(unittest.TestCase):
    def setUp(self):
        self.f=gis.InterfaceGIS()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.c,self.t=self.f.c,self.f.t
        self.aguardar=self.f.f.aguardar
        def limpar():
            self.c._falha_salvar=None
            self.t._edicao_limpa=self.t._assinatura_edicao()
        self.addCleanup(limpar)

    def test_salvar_projeto_cria_manifesto_e_preserva_rascunho_sem_executar(self):
        c,t=self.c,self.t
        t.limite.setValue(741)
        c._atualizar_salvamento()
        self.assertIn('não salvas',c.estado_salvar.text())
        arq=Path(c.app.catalogo.raiz)/'Registro.wna'
        with (patch.object(QFileDialog,'getSaveFileName',return_value=(str(arq),'')),
              patch('auditoria_aplicacao.topologia_gis_ui.executar',side_effect=AssertionError('Recalculou'))):
            self.assertTrue(c.salvar_projeto())
        p=manifesto_projeto.ler(arq)
        self.assertFalse(p['bases'])
        self.assertTrue(p['sessao_wna']['rascunho'])
        r=estado_projeto.ler(c.app.catalogo.raiz,p,estado_projeto.RASCUNHO)
        self.assertEqual(r['limite_mm'],741)
        self.assertFalse(t.edicao_pendente())
        self.assertIn('Salvo',c.estado_salvar.text())

    def test_falha_do_manifesto_preserva_rascunho_e_impede_saida(self):
        c,t=self.c,self.t
        arq=Path(c.app.catalogo.raiz)/'Registro.wna'
        c.projetos.salvar_manifesto(arq)
        t.limite.setValue(583)
        with patch.object(c.projetos,'salvar_sessao',side_effect=OSError('Disco indisponível')):
            self.assertFalse(c.salvar_projeto())
        self.assertNotIn('sessao_wna',manifesto_projeto.ler(arq))
        self.assertIn('não salvas',c.estado_salvar.text())
        with patch.object(QMessageBox,'exec_',return_value=QMessageBox.Cancel):
            self.assertFalse(c.app.preparar_saida())
        self.assertTrue(c.salvar_projeto())

    def test_origens_e_conexoes_separadas_com_revisao_rapida(self):
        t=self.t
        origem=t._salvar('ORIGEM',dict(situacao='INFORMADA',portas=[]))
        rel=t._salvar('CONEXAO',dict(situacao='INFORMADA',decisao='CANDIDATA',portas=[['A',0.],['B',0.]]))
        self.assertEqual(t.participantes.item(0).data(Qt.UserRole),origem['uuid'])
        self.assertEqual(t.conexoes_lista.item(0).data(Qt.UserRole),rel['uuid'])
        self.assertTrue(t.interpretar_candidata(rel,'CONFIRMADA',incluir=True))
        self.assertIn(rel['uuid'],t._selecionados())
        r=t.registros[rel['uuid']]
        self.assertEqual(r['acompanhamento'],'VERIFICADO')
        self.assertTrue(t.interpretar_candidata(r,'CONFIRMADA',incluir=False))
        self.assertNotIn(rel['uuid'],t._selecionados())

    def test_lista_paginada_preserva_participacao_entre_categorias(self):
        t=self.t
        r={str(i):dict(uuid=str(i),rev='r'+str(i),tipo='CONEXAO',
                       situacao='HIPOTETICA' if i%2 else 'INFORMADA',
                       decisao='CANDIDATA',portas=[]) for i in range(241)}
        t.registros.update(r)
        t.preencher_conexoes(r,{'240'})
        n=t.conexoes_lista
        self.assertEqual(sum(not n.isRowHidden(i) for i in range(n.count())),100)
        t.filtrar_conexoes(1)
        self.assertEqual(t._pagina_conexoes,1)
        self.assertEqual(t._selecionados(),['240'])
        t.filtro_conexoes.setCurrentIndex(t.filtro_conexoes.findData('PROPOSTA'))
        self.assertEqual(t._pagina_conexoes,0)
        self.assertEqual(t._selecionados(),['240'])

    def test_arquivo_ausente_indisponibilidade_e_cancelamento_da_troca(self):
        c,t=self.c,self.t
        arq=Path(c.app.catalogo.raiz)/'Registro.wna'
        c.projetos.salvar_manifesto(arq)
        c.projetos.vincular(dict(tipo='TOPOLOGIA_GIS',uuid='ausente',base=str(arq.with_suffix('.gpkg'))))
        self.assertFalse(c.salvar_projeto())
        self.assertIn('Arquivo de resultado ausente',c.mapa_info.text())
        t.limite.setValue(621)
        with (patch.object(QMessageBox,'exec_',return_value=QMessageBox.Cancel),
              patch.object(QFileDialog,'getOpenFileName') as abrir):
            c.abrir_projeto()
            abrir.assert_not_called()
        self.assertEqual(t.limite.value(),621)
        with patch.object(c,'ocupado',return_value=True):
            self.assertFalse(c.salvar_projeto())
        self.assertIn('Aguarde a atividade',c.mapa_info.text())

    def test_salvar_e_continuar_confirma_saida_sem_recalculo(self):
        from qgis.PyQt.QtWidgets import QApplication
        c,t=self.c,self.t
        arq=Path(c.app.catalogo.raiz)/'Registro.wna'
        c.projetos.salvar_manifesto(arq)
        t.limite.setValue(343)
        def confirmar():
            visor=QApplication.activeModalWidget()
            if not visor:return
            botao=next(b for b in visor.buttons() if b.text()=='Salvar e continuar')
            botao.click()
        QTimer.singleShot(10,confirmar)
        self.assertTrue(c.app.preparar_saida())
        p=manifesto_projeto.ler(arq)
        self.assertFalse(p['bases'])
        self.assertTrue(p['sessao_wna']['rascunho'])

    def test_tabela_de_blocos_mostra_o_resultado_e_destaca_a_rede(self):
        t,c=self.t,self.c
        t.iniciar()
        self.aguardar()
        self.assertTrue(c.abrir_estrutura(foto=t.dados))
        p=c.estrutura_gis
        p.calcular(agrupado=True,blocos=True)
        self.aguardar()
        self.assertEqual(p.categoria.currentData(),'BLOCOS')
        self.assertEqual(p.tabela.horizontalHeaderItem(0).text(),'Bloco')
        self.assertIn('fronteiras',p.registro())
        p.localizar_linha(p.tabela.currentIndex(),True)
        self.assertTrue(c.mapa.itens)
