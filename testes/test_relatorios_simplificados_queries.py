"""Regressões sintéticas: uso offline, recuperação de basemap e índice de Queries."""
import csv,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from test_auditoria_fronteiras import APP
from test_exportacao_catalogo_relatorio import exemplo
from auditoria_topologica_watergems import exportacao_watergems as ex,relatorio_investigacao as rel
from auditoria_topologica_watergems.fontes_relatorio import resolver,remota,BasemapPendente,FalhaBasemap
from auditoria_topologica_watergems.localizacao_relatorio import referencia_automatica,sugerir_logradouros
from qgis.core import QgsVectorLayer,QgsGeometry,QgsRectangle,QgsProject
from qgis.PyQt.QtGui import QImage,QColor


def local(licenca=True):
    c=QgsVectorLayer('LineString?crs=EPSG:31983&field=rua:string','Referência sintética','memory');c.setCustomProperty('wna/mapa_base',True)
    if licenca:m=c.metadata();m.setLicenses(['CC0']);c.setMetadata(m)
    return c


def servico():
    c=Mock();c.isValid.return_value=True;c.providerType.return_value='wms';c.source.return_value='url=https%3A%2F%2Fcartografia.example.invalid%2Fwms';c.name.return_value='Serviço de teste';c.customProperty.side_effect=lambda k,d=None:d;c.metadata.return_value.licenses.return_value=[];c.metadata.return_value.rights.return_value=[];c.clone.side_effect=lambda:local();return c


class FontesTest(unittest.TestCase):
    def test_sem_basemap_sem_licenca(self):self.assertEqual(resolver([],{},{'n':1})[0],[])
    def test_auto_sem_fonte_continua_offline(self):b,c=resolver([],dict(basemap_modo='AUTOMATICO'),5);self.assertEqual(b,[]);self.assertTrue(c['avisos_basemap'])
    def test_auto_local_permitida(self):c=local();b,cfg=resolver([c],dict(basemap_modo='AUTOMATICO'),5);self.assertEqual(b,[c]);self.assertIn('CC0',cfg['atribuicao'])
    def test_local_sem_permissao_nao_e_auto(self):b,c=resolver([local(False)],dict(basemap_modo='AUTOMATICO'),5);self.assertFalse(b)
    def test_layer_carregada_nao_autoriza(self):
        with self.assertRaises(BasemapPendente):resolver([local(False)],{},1)
    def test_auto_nao_consulta_remota(self):c=servico();self.assertFalse(resolver([c],dict(basemap_modo='AUTOMATICO'),5)[0]);c.clone.assert_not_called()
    def test_fonte_remota_carregada_exige_autorizacao(self):
        c=servico()
        with self.assertRaises(BasemapPendente):resolver([c],dict(licenca_exportacao=True,atribuicao='Teste'),1)
        c.clone.assert_not_called()
    def test_online_autorizada_uma(self):c=servico();self.assertEqual(resolver([c],dict(licenca_exportacao=True,atribuicao='Teste',mapas_online=True),1)[0],[c])
    def test_online_multiplas_sugere_uma(self):
        with self.assertRaises(BasemapPendente) as e:resolver([servico()],dict(licenca_exportacao=True,atribuicao='Teste',mapas_online=True),5)
        self.assertTrue(e.exception.uma_ocorrencia)
    def test_online_lote_autorizado(self):self.assertEqual(len(resolver([servico()],dict(licenca_exportacao=True,atribuicao='Teste',mapas_online=True,lote_online_autorizado=True),5)[0]),1)
    def test_negativa_nao_pode_ser_ignorada(self):
        c=local();c.setCustomProperty('wna/relatorio/exportacao_permitida',False)
        with self.assertRaises(BasemapPendente):resolver([c],dict(licenca_exportacao=True,atribuicao='Teste'),1)
    def test_negativa_textual_tambem_bloqueia(self):
        c=local();c.setCustomProperty('wna/relatorio/exportacao_permitida','False')
        with self.assertRaises(BasemapPendente):resolver([c],dict(licenca_exportacao=True,atribuicao='Teste'),1)
    def test_sem_imagens_nao_exige_basemap(self):self.assertEqual(resolver([servico()],dict(imagens=False),5)[0],[])
    def test_fonte_ogr_http_tambem_remota(self):c=servico();c.providerType.return_value='ogr';self.assertTrue(remota(c))
    def test_memoria_local(self):self.assertFalse(remota(local()))
    def test_fonte_invalida(self):
        c=servico();c.isValid.return_value=False
        with self.assertRaises(BasemapPendente):resolver([c],{},1)
    def test_ccby_sem_creditos_nao_auto(self):c=local();m=c.metadata();m.setLicenses(['CC-BY-4.0']);c.setMetadata(m);self.assertEqual(resolver([c],dict(basemap_modo='AUTOMATICO'),1)[0],[])


class FalhasMapaTest(unittest.TestCase):
    def imagem(self):i=QImage(1440,900,QImage.Format_ARGB32);i.fill(QColor('white'));return i
    def executar(self,motivo,decidir):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);p=Path(temp.name)/'mapa.png';caixa=QgsRectangle(0,0,160,100);erro=(self.imagem(),motivo=='timeout',[] if motivo=='timeout' else [motivo],caixa);ok=(self.imagem(),False,[],caixa)
        with patch.object(rel,'renderizar_imagem',side_effect=[erro,ok]) as render:
            r=rel.renderizar([(QgsGeometry.fromWkt('POINT(0 0)'),'LOCAL')],'EPSG:31983',p,{},[local()],ao_falhar_basemap=decidir)
        return r,render.call_count,p.exists()
    def test_internet_continuar_sem_base(self):r,n,existe=self.executar('rede indisponível',lambda m:True);self.assertTrue(existe);self.assertEqual(n,2);self.assertFalse(r['fontes']);self.assertTrue(any('escolha do usuário' in a for a in r['avisos']))
    def test_timeout_continuar(self):r,n,_=self.executar('timeout',lambda m:True);self.assertTrue(any('excedido' in a for a in r['avisos']))
    def test_autenticacao_continuar(self):r,n,_=self.executar('401 authentication failure',lambda m:True);self.assertTrue(any('autenticação' in a for a in r['avisos']))
    def test_cancelar_apos_falha(self):
        with self.assertRaises(InterruptedError):self.executar('rede',lambda m:False)
    def test_sem_resposta_nao_faz_fallback_silencioso(self):
        with self.assertRaises(FalhaBasemap):self.executar('rede',None)
    def test_online_nao_autorizada_nao_renderiza(self):
        with patch.object(rel,'renderizar_imagem') as render:
            with self.assertRaises(BasemapPendente):rel.renderizar([(QgsGeometry.fromWkt('POINT(0 0)'),'LOCAL')],'EPSG:31983','nao_criar.png',{},[servico()])
            render.assert_not_called()


class IndiceQueriesTest(unittest.TestCase):
    def dados(self):p,r=exemplo();d=ex.preparar(p,r);return p,r,d,ex.consultas(d,p['topologia']['modelo'],max_itens=1)
    def test_nome_por_tipo_singular(self):p,r,d,qs=self.dados();i=ex.indice_consultas(qs,d);self.assertEqual(i[0]['Arquivo'],'JUNCTION_LOTE_001_1_ELEMENTO.txt');self.assertTrue(any(q['Arquivo'].startswith('PIPE_') for q in i))
    def test_total_por_tipo(self):p,r,d,qs=self.dados();i=ex.indice_consultas(qs,d);self.assertEqual({q['TotalTipo'] for q in i if q['TipoWaterGEMS']=='IdahoJunction'},{3})
    def test_nao_mistura_tipo_em_lote(self):p,r,d,qs=self.dados();self.assertTrue(all(q['quantidade']==1 for q in qs));self.assertEqual(len(qs),5)
    def test_indice_mesmos_arquivos_exportados(self):
        p,r,d,qs=self.dados()
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)/'saida';ex.exportar(out,p,r,dict(max_itens=1));rows=list(csv.DictReader((out/'INDICE_QUERIES.csv').open(encoding='utf-8-sig'),delimiter=';'));self.assertEqual(len(rows),5);self.assertTrue(all((out/q['Arquivo']).is_file() for q in rows));self.assertFalse(list(out.glob('QUERY_*.txt')));self.assertTrue((out/'MANIFESTO_QUERIES.json').exists())
    def test_tipos_especiais_sem_caminhos_inseguros(self):
        p,r,d,qs=self.dados();qs[0]['tipo']='../Válvula:especial?';i=ex.indice_consultas(qs,d);self.assertNotIn('/',i[0]['Arquivo']);self.assertNotIn(':',i[0]['Arquivo'])
    def test_slugs_colidentes_distintos(self):p,r,d,qs=self.dados();qs[0]['tipo']='X-Y';qs[1]['tipo']='X Y';i=ex.indice_consultas(qs,d);self.assertNotEqual(i[0]['Arquivo'],i[1]['Arquivo'])
    def test_indices_modelo_versao_campo(self):p,r,d,qs=self.dados();i=ex.indice_consultas(qs,d,'ElementID');self.assertEqual(i[0]['Campo'],'ElementID');self.assertEqual(i[0]['Versao'],d['versao']);self.assertEqual(i[0]['Modelo'],'modelo')
    def test_labels_especiais_nao_viram_nome_arquivo(self):p,r,d,qs=self.dados();p['topologia']['modelo']['elementos'][101]['label']="00'O:/";d=ex.preparar(p,r);q=ex.consultas(d,p['topologia']['modelo']);i=ex.indice_consultas(q,d);self.assertIn("00''O:/",str(q));self.assertTrue(all('/' not in r['Arquivo'] for r in i))


class LocalizacaoAutomaticaTest(unittest.TestCase):
    def pacote(self,attrs):return dict(dossie=dict(tubulacoes=[dict(uid='t',origem='o',camada='Rede',atributos=attrs)]))
    def test_rua_cadastral_sem_configuracao(self):r=referencia_automatica(self.pacote({'NOME_LOGRADOURO':'Rua de teste'}),dict(gis_uids=['t']),{});self.assertEqual(r['candidatos'][0]['valor'],'Rua de teste')
    def test_nome_generico_nao_e_rua(self):self.assertIsNone(referencia_automatica(self.pacote({'NOME':'Setor A'}),dict(gis_uids=['t']),{}))
    def test_campos_ambiguos_nao_escolhe_um(self):self.assertIsNone(referencia_automatica(self.pacote({'RUA':'A','ENDERECO':'B'}),dict(gis_uids=['t']),{}))
    def test_campo_de_rua_local(self):c=local();self.assertEqual(sugerir_logradouros([c]),[(c,'rua')])
    def test_rua_remota_nao_e_descoberta_online(self):self.assertFalse(sugerir_logradouros([servico()]))


import test_decisoes_topologicas as fixture
class InterfaceSimplificadaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.DecisoesTest.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):fixture.DecisoesTest.tearDownClass.__func__(cls)
    def setUp(self):fixture.DecisoesTest.setUp(self)
    def tearDown(self):fixture.DecisoesTest.tearDown(self)
    def dialogo(self):
        from auditoria_topologica_watergems.relatorio_ui import RelatorioDialog
        j=fixture.DecisoesTest.painel(self);d=RelatorioDialog(j);self.addCleanup(d.deleteLater);return d
    def test_padrao_offline_sem_formulario_tecnico(self):d=self.dialogo();self.assertEqual(d.config()['basemap_modo'],'AUTOMATICO');self.assertFalse(d.online.isChecked());self.assertFalse(d.avancado.isChecked());self.assertFalse(d.fontes_widget.isVisible())
    def test_outra_fonte_remota_cancelada_sem_consulta(self):
        from qgis.PyQt.QtWidgets import QInputDialog,QMessageBox
        d=self.dialogo()
        with patch.object(QInputDialog,'getItem',return_value=('wms',True)),patch.object(QInputDialog,'getText',return_value=('url=https://exemplo.invalid/wms',True)),patch.object(QMessageBox,'question',return_value=QMessageBox.No),patch('auditoria_topologica_watergems.relatorio_ui.QgsRasterLayer') as construtor:
            d.outra_fonte();construtor.assert_not_called()

    def test_destino_inicial(self):self.assertEqual(Path(self.dialogo().destino.text()),self.base.parent)
    def test_padrao_resolve_sem_base(self):d=self.dialogo();cfg,fontes=d.preparar_fontes(d.config());self.assertEqual(fontes,[])
    def test_previa_mapa_nao_encolhe_em_faixa(self):
        from qgis.PyQt.QtWidgets import QApplication
        d=self.dialogo();d.resize(800,600);d.show();QApplication.processEvents()
        def gerar(p,cfg):
            p.mkdir();img=QImage(1440,900,QImage.Format_ARGB32);img.fill(QColor('white'));img.save(str(p/'mapa_00000.png'))
            return dict(ocorrencias=[dict(titulo='Ocorrência sintética',acompanhamento='EM ABERTO',resultado='PENDENTE',localizacao=dict(texto='Localização não identificada'))])
        with patch.object(d,'executar',side_effect=gerar):d.previa()
        QApplication.processEvents();self.assertGreaterEqual(d.imagem.height(),d.imagem.pixmap().height());self.assertGreater(d.scroll.verticalScrollBar().maximum(),0)

    def test_previa_pede_apenas_um_caso(self):
        d=self.dialogo();d.painel.atual=d.painel.casos[0]
        with patch.object(d,'executar',return_value=None) as run:d.previa()
        self.assertEqual(len(run.call_args.args[1]['ids']),1);self.assertEqual(run.call_args.args[1]['escopo'],'SELECAO')
    def test_alternativa_sem_base_preserva_selecao(self):
        from qgis.PyQt.QtWidgets import QMessageBox
        d=self.dialogo();c=local(False);d.base.addItem('Sem licença',c);d.base.setCurrentIndex(d.base.count()-1);antes=d.config()
        def escolher(w):
            next(b for b in w.buttons() if b.text()=='Gerar sem mapa-base').click();return 0
        with patch.object(QMessageBox,'exec_',new=escolher):cfg,fontes=d.preparar_fontes(antes)
        self.assertEqual(fontes,[]);self.assertEqual(cfg['escopo'],antes['escopo']);self.assertEqual(cfg['basemap_modo'],'NENHUM');self.assertEqual(d.basemap_modo.currentData(),'SELECIONAR')


    def test_cancelar_alternativa_preserva_formulario(self):
        from qgis.PyQt.QtWidgets import QMessageBox
        d=self.dialogo();c=local(False);d.base.addItem('Sem licença',c);d.base.setCurrentIndex(d.base.count()-1);antes=d.config()
        def escolher(w):next(b for b in w.buttons() if b.text()=='Cancelar').click();return 0
        with patch.object(QMessageBox,'exec_',new=escolher):self.assertIsNone(d.preparar_fontes(antes))
        self.assertEqual(d.config(),antes)
    def test_uma_ocorrencia_sem_mudar_filtros(self):
        from qgis.PyQt.QtWidgets import QMessageBox,QInputDialog
        d=self.dialogo();c=servico();d.base.addItem('Serviço',c);d.base.setCurrentIndex(d.base.count()-1);d.licenca.setChecked(True);d.atri.setText('Fonte de teste');d.online.setChecked(True)
        def escolher(w):next(b for b in w.buttons() if b.text()=='Somente uma ocorrência').click();return 0
        def um(*args):return args[3][0],True
        with patch.object(QMessageBox,'exec_',new=escolher),patch.object(QInputDialog,'getItem',side_effect=um):cfg,fontes=d.preparar_fontes(d.config())
        self.assertEqual(len(cfg['ids']),1);self.assertEqual(d.escopo.currentData(),'TODOS');c.clone.assert_not_called()
    def test_falha_multiplas_continua_sem_reiniciar(self):
        import copy
        c2=copy.deepcopy(self.c);c2['uid']='segunda_ocorrencia_sintetica';img=QImage(1440,900,QImage.Format_ARGB32);img.fill(QColor('white'));contador=[0]
        def render(*args):
            contador[0]+=1;return img,False,['rede indisponível'] if contador[0]==1 else [],QgsRectangle(0,0,160,100)
        with patch.object(rel,'renderizar_imagem',side_effect=render):
            escolha=Mock(return_value=True);r=rel.gerar(self.base,self.p,[self.c,c2],'ESTRUTURAL',self.dir/'continuar',{},[local()],ao_falhar_basemap=escolha)
        self.assertEqual(len(r['ocorrencias']),2);escolha.assert_called_once();self.assertTrue(all(not o['mapa_meta'][0]['fontes'] for o in r['ocorrencias']))

class QueriesExtensasTest(unittest.TestCase):
    def test_1001_elementos_sem_truncar(self):
        elems=[dict(DomainElementID=i,Label='00'+str(i),Tipo='IdahoPipe',Modelo='sintetico') for i in range(1001)];d=dict(elementos=elems,versao='v1');m=dict(elementos={i:dict(tipo='IdahoPipe',label=e['Label'],excluido=False) for i,e in enumerate(elems)});qs=ex.consultas(d,m);indice=ex.indice_consultas(qs,d)
        self.assertEqual(sum(q['Quantidade'] for q in indice),1001);self.assertEqual(indice[0]['Arquivo'],'PIPE_LOTE_001_100_ELEMENTOS.txt');self.assertEqual(indice[-1]['Arquivo'],'PIPE_LOTE_011_1_ELEMENTO.txt')
    def test_tipo_reservado_nome_seguro(self):
        d=dict(elementos=[],versao='v1');q=[dict(tipo='CON',lote=1,quantidade=1,estado='DOCUMENTADA')];self.assertTrue(ex.indice_consultas(q,d)[0]['Arquivo'].startswith('TIPO_CON_'))
    def test_gui_mostra_indice_completo(self):
        from types import SimpleNamespace
        from qgis.PyQt.QtWidgets import QWidget
        from auditoria_topologica_watergems.exportacao_watergems_ui import ExportarWatergems
        p,r=exemplo();pai=QWidget();pai.painel=SimpleNamespace(pacote=p);pai.registro=r;d=ExportarWatergems(pai);self.addCleanup(d.deleteLater);self.addCleanup(pai.deleteLater);d.consultas();self.assertEqual(d.tabela.columnCount(),10);self.assertIn('_LOTE_',d.tabela.item(0,2).text());d.tabela.setCurrentCell(0,0);self.assertIn(' IN (',d.texto.toPlainText())

if __name__=='__main__':unittest.main()
