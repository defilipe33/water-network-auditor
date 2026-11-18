"""Contraste calculado e atualização sem reconstrução dos formulários."""
import unittest
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QPalette
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QWidget, QLineEdit, QVBoxLayout, QComboBox
from test_auditoria_fronteiras import APP
from auditoria_aplicacao.aparencia import Aparencia, cores, contraste, estilo, legivel


def paleta(escura):
    p = QPalette()
    for papel, claro, escuro in (
        (QPalette.Window, '#eeeeee', '#303236'), (QPalette.Base, '#ffffff', '#202226'),
        (QPalette.Button, '#e0e0e0', '#414348'), (QPalette.WindowText, '#202020', '#dddddd'),
        (QPalette.Text, '#101010', '#eeeeee'), (QPalette.ButtonText, '#151515', '#eeeeee'),
        (QPalette.Highlight, '#3165b5', '#397cba'), (QPalette.HighlightedText, '#ffffff', '#ffffff')):
        p.setColor(papel, QColor(escuro if escura else claro))
    return p


class AparenciaTest(unittest.TestCase):
    def conferir(self, p):
        c = cores(p)
        for texto, fundo in [('texto','fundo'), ('texto_secundario','fundo'),
                             ('campo_texto','superficie'), ('botao_texto','cartao'),
                             ('desabilitado','cartao'), ('hover_texto','hover'),
                             ('selecao_texto','selecao'), ('selecionado_texto','destaque'),
                             ('aviso','fundo'), ('erro','fundo'), ('sucesso','fundo')]:
            self.assertGreaterEqual(contraste(c[texto],c[fundo]),4.5,(texto,fundo))
        self.assertGreaterEqual(contraste(c['borda'],c['fundo']),3)
        self.assertGreaterEqual(contraste(c['foco'],c['cartao']),3)
        self.assertGreaterEqual(contraste(c['foco'],c['selecao']),3)

    def test_contraste_claro(self): self.conferir(paleta(False))
    def test_contraste_escuro(self): self.conferir(paleta(True))
    def test_paleta_de_baixo_contraste(self):
        p=QPalette()
        for r in (QPalette.Text,QPalette.WindowText,QPalette.ButtonText,QPalette.HighlightedText):
            p.setColor(r,QColor('#777777'))
        self.conferir(p)

    def test_preserva_cor_valida(self):
        self.assertEqual(legivel('#ececec','#202020'),QColor('#ececec'))

    def test_cores_derivadas_do_tema(self):
        for escura in (False,True):
            p=paleta(escura);c=cores(p)
            self.assertEqual(c['fundo'],p.color(QPalette.Window))
            self.assertEqual(c['destaque'],p.color(QPalette.Highlight))
            self.assertIn('QMenu::item:selected',estilo(c))
            self.assertIn('QPushButton#Principal:disabled',estilo(c))

    def test_popup_criado_depois_da_aparencia(self):
        origem=QWidget();raiz=QWidget();origem.setPalette(paleta(True))
        a=Aparencia(raiz,origem);layout=QVBoxLayout(raiz)
        combo=QComboBox();combo.addItems(['Campo A','Campo B']);layout.addWidget(combo)
        try:
            raiz.show();combo.showPopup();QTest.qWait(30)
            self.assertIn('selection-background-color:'+a.tokens['destaque'].name(),combo.view().styleSheet())
            combo.hidePopup();origem.setPalette(paleta(False));QTest.qWait(30)
            self.assertIn('selection-color:'+a.tokens['selecionado_texto'].name(),combo.view().styleSheet())
            self.assertEqual(combo.currentText(),'Campo A')
        finally:
            raiz.close();raiz.deleteLater();origem.deleteLater();QTest.qWait(10)

    def test_alternancia_preserva_contexto_e_rascunho(self):
        origem=QWidget();raiz=QWidget();layout=QVBoxLayout(raiz)
        campo=QLineEdit('rascunho');layout.addWidget(campo)
        combo=QComboBox();combo.addItems(['Preparar','Investigar']);combo.setCurrentIndex(1);layout.addWidget(combo)
        original=APP.palette();outro=QWidget();css_app=APP.styleSheet()
        try:
            origem.setPalette(paleta(False));a=Aparencia(raiz,origem);antes=raiz.styleSheet()
            origem.setPalette(paleta(True));QTest.qWait(40)
            self.assertNotEqual(antes,raiz.styleSheet())
            self.assertEqual(campo.text(),'rascunho');self.assertEqual(combo.currentIndex(),1)
            self.assertEqual(APP.palette(),original);self.assertEqual(APP.styleSheet(),css_app)
            self.assertEqual(outro.styleSheet(),'')
            origem.setPalette(paleta(False));QTest.qWait(40)
            self.assertEqual(antes,raiz.styleSheet())
            raiz.close();origem.setPalette(paleta(True));QTest.qWait(40)
        finally:
            raiz.deleteLater();origem.deleteLater();outro.deleteLater();QTest.qWait(10)


if __name__=='__main__': unittest.main()
