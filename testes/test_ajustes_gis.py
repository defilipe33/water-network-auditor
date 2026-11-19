"""Regressões de filtros, amostras e relações GIS declaradas, sem WaterGEMS."""
import unittest
from copy import deepcopy
from unittest.mock import patch
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QDate, Qt
from qgis.PyQt.QtWidgets import QWidget, QListView, QComboBox, QVBoxLayout
from qgis.PyQt.QtTest import QTest
from qgis.core import QgsExpression, QgsExpressionContext, QgsFeature, QgsVectorLayer, QgsVectorLayerFeatureSource
from test_auditoria_fronteiras import APP, camada
import test_nova_interface as fixtures
from auditoria_aplicacao.aparencia import Aparencia, cores, estilo
from auditoria_aplicacao.modelo_gis import configurar, descrever, revisoes, ROTULOS
from auditoria_aplicacao.cadastro_gis import sugerir_campos, amostra_elementos
from auditoria_aplicacao.filtros_gis import gerar, operadores, valores_amostrados
from auditoria_aplicacao.associacoes_gis import referencia, verificar_referencia, declarar, vigentes, remover, pendencias

class CondicoesTest(unittest.TestCase):
    campos={'Tipo especial':'String','DN':'Double','data':'Date','ID':'String'}
    def cond(self, campo='Tipo especial', op='=', v='PRV', v2=''):
        return dict(campo=campo,operador=op,valor=v,valor2=v2)
    def avaliar(self, n, valores):
        c=QgsVectorLayer('None?field=Tipo especial:string&field=DN:double&field=data:date&field=ID:string','sintetica','memory')
        f=QgsFeature(c.fields());f.setAttributes(valores)
        e=QgsExpression(gerar(n,self.campos));ctx=QgsExpressionContext();ctx.setFeature(f)
        v=e.evaluate(ctx);self.assertFalse(e.hasEvalError(),e.evalErrorString());return v
    def test_texto_especial(self): self.assertTrue(self.avaliar(self.cond(v="D'Água"),["D'Água",100,None,'001']))
    def test_identificador_textual(self): self.assertIn("'001'",gerar(self.cond('ID',v='001'),self.campos))
    def test_entre_numeros(self): self.assertTrue(self.avaliar(self.cond('DN','ENTRE','100','300'),['PRV',200,None,'001']))
    def test_numero_invalido(self):
        with self.assertRaises(ValueError):gerar(self.cond('DN','=', 'nan'),self.campos)
    def test_data(self): self.assertTrue(self.avaliar(self.cond('data','ENTRE','2026-01-01','2026-12-31'),['PRV',10,QDate(2026,5,2),'001']))
    def test_data_invalida(self):
        with self.assertRaises(ValueError):gerar(self.cond('data','=', '2026-99-99'),self.campos)
    def test_agrupamento(self):
        a=dict(grupo='AND',itens=[dict(grupo='OR',itens=[self.cond(v='PRV'),self.cond(v='TCV')]),self.cond('DN','>=','200')])
        self.assertTrue(self.avaliar(a,['TCV',300,None,'001']));self.assertFalse(self.avaliar(a,['TCV',100,None,'001']))
    def test_operadores_por_tipo(self):
        self.assertNotIn('CONTEM',operadores('Double'));self.assertNotIn('>',operadores('String'));self.assertIn('ENTRE',operadores('Date'))
    def test_contem_literal(self):
        for op,v in [('CONTEM','a_b'),('NAO_CONTEM','xyz'),('INICIA','a_'),('TERMINA','%')]:
            self.assertTrue(self.avaliar(self.cond(op=op,v=v),['a_b%',100,None,'001']),op)
    def test_lista(self): self.assertTrue(self.avaliar(self.cond(op='LISTA',v='["PRV", "TCV"]'),['TCV',100,None,'001']))
    def test_ou_sem_espacos_e_nulo(self):
        a=dict(grupo='OR',itens=[self.cond('ID',v='002'),self.cond('ID',v='001')])
        self.assertTrue(self.avaliar(a,['TCV',100,None,'001']))
        self.assertFalse(self.avaliar(a,['TCV',100,None,'003']))
    def test_filtro_invalido_na_amostra(self):
        c=camada('Point',['POINT(0 0)'])
        with self.assertRaises(ValueError):amostra_elementos(QgsVectorLayerFeatureSource(c),['id'],'id = ')
    def test_vrp_nome_opcional_preserva_mapa(self):
        c=camada('Point',['POINT(0 0)']);meta=descrever(c)
        f=configurar(meta,'PRV','EXISTENTE','',{'id':'id'})
        nova=configurar(meta,'PRV','EXISTENTE','',{'id':'id','nome':'nome'},anterior=f)
        self.assertEqual(nova['uid'],f['uid']);self.assertEqual(nova['campos_mapeados']['nome'],'nome')
    def test_vazio_e_nulo(self):
        self.assertTrue(self.avaliar(self.cond(op='VAZIO'),['',100,None,'001']))
        self.assertTrue(self.avaliar(self.cond('data','IS NULL'),['PRV',100,None,'001']))
    def test_campo_ausente(self):
        with self.assertRaises(ValueError):gerar(self.cond('ausente'),self.campos)
    def test_grupo_vazio(self):
        with self.assertRaises(ValueError):gerar(dict(grupo='AND',itens=[]),self.campos)
    def test_nome_sem_tag(self):
        m,a=sugerir_campos({'NOME_VRP':'String','TAG':'String'},'PRV');self.assertEqual(m['nome'],'NOME_VRP')
        self.assertNotIn('nome',sugerir_campos({'TAG':'String'},'PRV')[0])
    def test_nome_ambiguo(self): self.assertIn('nome',sugerir_campos({'NOME':'String','NAME':'String'},'PRV')[1])
    def test_amostra_20_e_total_desconhecido(self):
        c=camada('Point',['POINT(0 0)']*60);s=QgsVectorLayerFeatureSource(c)
        r=amostra_elementos(s,['id'],'');self.assertEqual(len(r['linhas']),20);self.assertIsNone(r['total'])
        self.assertEqual(c.selectedFeatureIds(),[])
    def test_amostra_sem_resultados(self):
        c=camada('Point',['POINT(0 0)']);r=amostra_elementos(QgsVectorLayerFeatureSource(c),['id'],'id < 0')
        self.assertTrue(r['completa']);self.assertEqual(r['total'],0)
    def test_amostra_limite_e_cancelar(self):
        c=camada('Point',['POINT(0 0)']*60);s=QgsVectorLayerFeatureSource(c)
        r=amostra_elementos(s,['id'],'id < 0',limite=3);self.assertIsNone(r['total']);self.assertEqual(r['lidas'],3)
        with self.assertRaises(InterruptedError):amostra_elementos(s,['id'],'',lambda:True)
    def test_destaque_intersecta_fid_e_filtro(self):
        from auditoria_aplicacao.mapa_fontes import ler_destaque
        c=camada('Point',['POINT(0 0)','POINT(1 1)','POINT(2 2)']);s=QgsVectorLayerFeatureSource(c)
        fid=next(c.getFeatures()).id()
        dados,_,_=ler_destaque(s,'id > 0',[fid],['nome'],lambda:False)
        self.assertEqual(len(dados),1)
        dados,_,_=ler_destaque(s,'id > 2',[fid],['nome'],lambda:False)
        self.assertEqual(len(dados),0)
    def test_valores_limitados(self):
        c=camada('Point',['POINT(0 0)']*10);self.assertLessEqual(len(valores_amostrados(QgsVectorLayerFeatureSource(c),'id',limite=3)),3)
    def test_rotulos_sem_mudar_chaves(self):
        self.assertEqual(ROTULOS['id'],'ID da feição');self.assertEqual(ROTULOS['label'],'Nome exibido')

class AparenciaSeguraTest(unittest.TestCase):
    def test_delegate_pinta_selecao_hover_e_desabilitado(self):
        from qgis.PyQt.QtCore import QRect
        from qgis.PyQt.QtGui import QImage, QPainter
        from qgis.PyQt.QtWidgets import QListWidget, QStyle, QStyleOptionViewItem
        from auditoria_aplicacao.aparencia import DelegateFontes
        view=QListWidget();view.addItem('Fonte');delegate=DelegateFontes(view)
        def fundo(estado):
            img=QImage(220,30,QImage.Format_ARGB32);opt=QStyleOptionViewItem();opt.widget=view;opt.rect=QRect(0,0,220,30);opt.state=estado
            painter=QPainter(img);delegate.paint(painter,opt,view.model().index(0,0));painter.end();return img.pixelColor(210,15)
        sel=fundo(QStyle.State_Enabled|QStyle.State_Selected)
        self.assertEqual(sel,fundo(QStyle.State_Enabled|QStyle.State_Selected|QStyle.State_MouseOver))
        self.assertNotEqual(sel,fundo(QStyle.State_Enabled|QStyle.State_MouseOver));self.assertNotEqual(sel,fundo(QStyle.State_None))
        view.deleteLater();QTest.qWait(5)
    def test_sem_delegate_e_destruido(self):
        raiz=QWidget();origem=QWidget();a=Aparencia(raiz,origem);v=QListView(raiz);v.setItemDelegate(None)
        a.popup(v);self.assertIsNone(v.itemDelegate())
        sip.delete(v);a.popup(v);raiz.deleteLater();origem.deleteLater();QTest.qWait(5)
    def test_estados_distintos(self):
        css=estilo(cores(APP.palette()))
        self.assertIn('::item:hover:!selected:enabled',css);self.assertIn('::item:selected:hover',css)
        self.assertNotEqual(cores(APP.palette())['hover'],cores(APP.palette())['destaque'])
    def test_popup_repetido(self):
        raiz=QWidget();origem=QWidget();v=QVBoxLayout(raiz);c=QComboBox();c.addItems(['A','B']);v.addWidget(c);a=Aparencia(raiz,origem)
        raiz.show()
        for _ in range(4):c.showPopup();QTest.qWait(5);c.hidePopup()
        self.assertEqual(c.currentText(),'A');raiz.close();raiz.deleteLater();origem.deleteLater();QTest.qWait(5)

class FluxosAjustadosTest(unittest.TestCase):
    def setUp(self):
        self.fx=fixtures.AmbienteTest();self.fx.setUp();self.addCleanup(self.fx.doCleanups);self.m=self.fx.m;self.c=self.fx.c
    def editor(self,cat='PIPE',camadas=None):
        f=self.fx.cadastrar(cat,camadas);self.m.abrir_categoria(cat);self.m.selecionada=f['uid'];self.m.atualizar_categoria();self.m.editar();return self.m.editor
    def test_construtor_sob_demanda_e_expressao_antiga(self):
        e=self.editor();e.filtro.setText('coalesce(id, 0) > 0');self.assertIsNone(e.construtor)
        e.abrir_visual.setChecked(True);self.assertEqual(e.filtro.text(),'coalesce(id, 0) > 0');self.assertFalse(e.construtor.sujo)
        self.assertEqual(e.configurar()['filtro'],'coalesce(id, 0) > 0')
    def test_construtor_salva_condicoes(self):
        e=self.editor();e.abrir_visual.setChecked(True);b=e.construtor;b.campo.setCurrentIndex(b.campo.findData('id'));b.valor.setEditText('1');b.adicionar()
        self.assertTrue(e.pendente());self.assertIn('id',e.configurar()['filtro']);self.assertFalse(b.sujo)
    def test_modificar_remover_condicao_e_grupo(self):
        e=self.editor();e.abrir_visual.setChecked(True);b=e.construtor
        b.campo.setCurrentIndex(b.campo.findData('id'));b.valor.setEditText('1');b.adicionar()
        item=b.raiz.child(0);b.arvore.setCurrentItem(item);b.valor.setEditText('2');b.editar()
        self.assertEqual(item.data(0,Qt.UserRole)['valor'],'2');b.remover();self.assertEqual(b.raiz.childCount(),0)
        b.grupo();b.conectivo.setCurrentIndex(b.conectivo.findData('OR'));b.conectar()
        self.assertEqual(b.raiz.child(0).data(0,Qt.UserRole)['grupo'],'OR')
    def test_amostra_alterada_descarta_retorno(self):
        e=self.editor();e.filtro.setText('id > 2')
        e.receber_amostra('', ['id'], dict(linhas=[dict(fid=1,valores=['1'])],lidas=1,total=1,completa=True))
        self.assertFalse(e._amostra_fids);self.assertIn('mudou',e.mensagem.text())
    def test_fonte_alterada_descarta_retorno_com_mesmo_filtro(self):
        e=self.editor();token=(e.filtro.text(),e._amostra_geracao);e.invalidar_amostra()
        e.receber_amostra(token,['id'],dict(linhas=[dict(fid=1,valores=['1'])],lidas=1,total=1,completa=True))
        self.assertFalse(e._amostra_fids);self.assertIn('fonte mudou',e.mensagem.text())
    def test_amostra_e_mapa(self):
        e=self.editor();antes=self.fx.redes[-1].selectedFeatureIds();e.prever();self.fx.aguardar()
        self.assertEqual(e.amostra.rowCount(),1);e.amostra.selectRow(0);e.destacar_amostra();self.fx.aguardar()
        self.assertTrue(self.c.mapa.itens);self.assertEqual(self.fx.redes[-1].selectedFeatureIds(),antes)
        e.filtro.setText('id < 0');self.assertFalse(e._amostra_fids)
    def test_investigar_gis_sem_wg(self):
        for i in (0,2,3):
            self.c.objetivo.setCurrentIndex(i)
            with patch.object(self.c,'acionar') as a:self.c.iniciar_objetivo();a.assert_called_once_with('gis')
    def test_poligono_sem_wg(self):
        e=self.editor('SETOR',[self.fx.zona]);self.assertEqual(e.configurar()['alvo_wg'],'')
    def test_declarar_reservatorio_afastado_e_reabrir(self):
        self.fx.cadastrar();c=camada('Point',['POINT(9999 9999)'],nome='Reservatorio distante')
        from qgis.core import QgsProject
        QgsProject.instance().addMapLayer(c)
        e=self.editor('RESERVOIR',[c]);c.selectAll();self.fx.redes[0].selectAll();e.preparar_conexoes(True);e.declarar_conexoes();self.fx.aguardar()
        self.assertEqual(len(e._associacoes),1);self.assertEqual(e._associacoes[0]['natureza'],'DECLARADA_MANUALMENTE')
        self.assertTrue(self.m.salvar());self.m.recarregar();self.assertTrue(any(f.get('associacoes_rede') for f in self.m.fontes))
    def test_associacao_historico_e_mudanca_identidade(self):
        eq=self.fx.cadastrar('TANK',[self.fx.valvula]);p=self.fx.cadastrar(camadas=[self.fx.redes[0]])
        er=referencia(eq,next(self.fx.valvula.getFeatures()));pr=referencia(p,next(self.fx.redes[0].getFeatures()))
        verificar_referencia(pr,p,QgsVectorLayerFeatureSource(self.fx.redes[0]))
        a=declarar(eq,er,[pr]);self.assertEqual(len(vigentes(a)),1)
        b=declarar(a,er,[pr],'FIM',a['associacoes_rede'][0]['uuid']);self.assertEqual(len(vigentes(b)),1)
        d=remover(b,vigentes(b)[0]['uuid']);self.assertEqual(len(d['associacoes_rede']),3);self.assertEqual(vigentes(d),[])
        p['assinatura']='alterada';self.assertTrue(pendencias(vigentes(a)[0],[eq,p]))
    def test_id_duplicado_bloqueia_associacao(self):
        c=camada('Point',['POINT(1 1)','POINT(2 2)'],ids=[1,1]);f=configurar(descrever(c),'TANK','EXISTENTE','',{'id':'id'});ref=referencia(f,next(c.getFeatures()))
        with self.assertRaises(ValueError):verificar_referencia(ref,f,QgsVectorLayerFeatureSource(c))
    def test_referencia_desaparecida_e_cancelada(self):
        f=self.fx.cadastrar(camadas=[self.fx.redes[0]]);c=self.fx.redes[0];ref=referencia(f,next(c.getFeatures()))
        with self.assertRaises(InterruptedError):verificar_referencia(ref,f,QgsVectorLayerFeatureSource(c),lambda:True)
        ref['valor']=999
        with self.assertRaises(ValueError):verificar_referencia(ref,f,QgsVectorLayerFeatureSource(c))
    def test_relacao_preservada_ao_editar_campos(self):
        f=self.fx.cadastrar('RESERVOIR',[self.fx.valvula]);p=self.fx.cadastrar(camadas=[self.fx.redes[0]])
        a=declarar(f,referencia(f,next(self.fx.valvula.getFeatures())),[referencia(p,next(self.fx.redes[0].getFeatures()))])
        nova=configurar(descrever(self.fx.valvula),'RESERVOIR','EXISTENTE','',{'id':'id'},anterior=a)
        self.assertEqual(nova['associacoes_rede'],a['associacoes_rede'])

if __name__=='__main__':unittest.main()
