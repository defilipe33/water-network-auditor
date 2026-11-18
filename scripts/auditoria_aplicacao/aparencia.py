"""Cores semânticas locais, derivadas da paleta efetiva do QGIS/Qt.

Não altera QApplication, configurações de tema ou simbologias cartográficas.
"""
from qgis.PyQt.QtCore import QObject, QEvent, QTimer
from qgis.PyQt.QtGui import QColor, QPalette
from qgis.PyQt.QtWidgets import QApplication, QAbstractItemView, QComboBox, QStyledItemDelegate


def luminancia(cor):
    c = QColor(cor)
    canais = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
              for v in (c.redF(), c.greenF(), c.blueF())]
    return sum(a * b for a, b in zip(canais, (.2126, .7152, .0722)))


def contraste(a, b):
    x, y = sorted((luminancia(a), luminancia(b)))
    return (y + .05) / (x + .05)


def misturar(a, b, proporcao):
    a, b = QColor(a), QColor(b)
    return QColor(*(round(x * (1 - proporcao) + y * proporcao)
                    for x, y in zip(a.getRgb()[:3], b.getRgb()[:3])))


def legivel(cor, fundo, minimo=4.5):
    """Preserva a cor do tema quando adequada; aproxima do extremo legível."""
    cor, fundo = QColor(cor), QColor(fundo)
    if contraste(cor, fundo) >= minimo:
        return cor
    alvo = max((QColor('black'), QColor('white')), key=lambda c: contraste(c, fundo))
    baixo, alto = 0., 1.
    for _ in range(24):
        meio = (baixo + alto) / 2
        if contraste(misturar(cor, alvo, meio), fundo) >= minimo:
            alto = meio
        else:
            baixo = meio
    return misturar(cor, alvo, alto)


def cores(paleta):
    p = paleta
    c = {nome: p.color(QPalette.Active, papel) for nome, papel in (
        ('fundo', QPalette.Window), ('superficie', QPalette.Base),
        ('secundario', QPalette.AlternateBase), ('cartao', QPalette.Button),
        ('texto', QPalette.WindowText), ('campo_texto', QPalette.Text),
        ('botao_texto', QPalette.ButtonText), ('destaque', QPalette.Highlight),
        ('selecionado_texto', QPalette.HighlightedText))}
    c['texto'] = legivel(c['texto'], c['fundo'])
    c['secundario'] = misturar(c['fundo'], c['superficie'], .6)
    c['campo_texto'] = legivel(c['campo_texto'], c['superficie'])
    c['botao_texto'] = legivel(c['botao_texto'], c['cartao'])
    c['texto_secundario'] = legivel(misturar(c['texto'], c['fundo'], .25), c['fundo'])
    c['desabilitado'] = legivel(p.color(QPalette.Disabled, QPalette.Text), c['cartao'])
    c['selecionado_texto'] = legivel(c['selecionado_texto'], c['destaque'])
    c['hover'] = misturar(c['cartao'], c['destaque'], .18)
    c['hover_texto'] = legivel(c['botao_texto'], c['hover'])
    c['selecao'] = misturar(c['fundo'], c['destaque'], .28)
    c['selecao_texto'] = legivel(c['texto'], c['selecao'])
    c['borda'] = legivel(misturar(c['texto'], c['fundo'], .55), c['fundo'], 3)
    c['foco'] = legivel(legivel(c['destaque'], c['cartao'], 3), c['selecao'], 3)
    for nome, semente in [('aviso', '#966400'), ('erro', '#b53030'), ('sucesso', '#12734b')]:
        c[nome] = legivel(semente, c['fundo'])
    return c


def estilo(c):
    t = {k: v.name() for k, v in c.items()}
    return '''
        QWidget {background-color:%(fundo)s; color:%(texto)s;}
        QLabel {background:transparent;}
        QLabel[papel="secundario"] {color:%(texto_secundario)s;}
        QLabel[papel="aviso"] {color:%(aviso)s;}
        QLabel[papel="erro"] {color:%(erro)s;}
        QLabel[papel="sucesso"] {color:%(sucesso)s;}
        QScrollArea {border:0;}
        QPushButton {padding:5px 7px; border:1px solid %(borda)s; border-radius:6px;
                     background-color:%(cartao)s; color:%(botao_texto)s;}
        QPushButton:hover {background-color:%(hover)s; color:%(hover_texto)s;}
        QPushButton:focus {border:2px solid %(foco)s;}
        QPushButton:disabled {color:%(desabilitado)s; background-color:%(cartao)s; border-style:dashed;}
        QPushButton#ComponenteModelo {text-align:left; padding:9px; font-weight:600;}
        QPushButton#ComponenteModelo:checked {background-color:%(selecao)s;
            color:%(selecao_texto)s; border:2px solid %(foco)s;}
        QPushButton#ComponenteModelo:checked:disabled {color:%(desabilitado)s; background-color:%(cartao)s;}
        QPushButton#Principal {background-color:%(destaque)s; color:%(selecionado_texto)s; font-weight:600;}
        QPushButton#Principal:hover {border:2px solid %(foco)s;}
        QPushButton#Principal:disabled {background-color:%(cartao)s; color:%(desabilitado)s;}
        QPushButton#Secundaria {text-align:left;}
        QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QAbstractItemView,
        QSpinBox, QDoubleSpinBox {background-color:%(superficie)s; color:%(campo_texto)s;
            selection-background-color:%(destaque)s; selection-color:%(selecionado_texto)s;}
        QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {
            border:1px solid %(borda)s;}
        QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
            border:2px solid %(foco)s;}
        QLineEdit, QComboBox {padding:4px; min-width:60px;}
        QComboBox:on {background-color:%(superficie)s; color:%(campo_texto)s;
            selection-background-color:%(destaque)s; selection-color:%(selecionado_texto)s;}
        QLineEdit:disabled, QComboBox:disabled, QTextEdit:disabled,
        QAbstractItemView:disabled {background-color:%(cartao)s; color:%(desabilitado)s;}
        QAbstractItemView::item:selected {background-color:%(destaque)s; color:%(selecionado_texto)s;}
        QComboBox QAbstractItemView::item:selected, QComboBox QListView::item:selected,
        QComboBox QAbstractItemView::item:hover {background-color:%(destaque)s; color:%(selecionado_texto)s;}
        QAbstractItemView {alternate-background-color:%(secundario)s;}
        QComboBox QAbstractItemView, QMenu {background-color:%(superficie)s; color:%(campo_texto)s;}
        QMenu::item:selected {background-color:%(destaque)s; color:%(selecionado_texto)s;}
        QMenu::item:disabled {color:%(desabilitado)s; background-color:%(cartao)s;}
        QHeaderView::section {background-color:%(cartao)s; color:%(botao_texto)s;}
        QScrollBar {background-color:%(fundo)s;}
        QScrollBar::handle {background-color:%(borda)s; border-radius:3px;}
        QScrollBar::handle:vertical {min-height:24px;}
        QScrollBar::handle:horizontal {min-width:24px;}
        QScrollBar::handle:hover {background-color:%(foco)s;}
        QToolTip {background-color:%(superficie)s; color:%(campo_texto)s; border:1px solid %(borda)s;}
    ''' % t


class Aparencia(QObject):
    """Atualiza apenas a subárvore do Auditor, sem recriar seus widgets."""
    def __init__(self, raiz, origem):
        super().__init__(raiz)
        self.raiz, self.origem = raiz, origem
        self.assinatura = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.atualizar)
        origem.installEventFilter(self)
        self.atualizar()
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, objeto, evento):
        if objeto is self.origem and evento.type() in (QEvent.PaletteChange, QEvent.ApplicationPaletteChange, QEvent.StyleChange):
            self.timer.start(0)
        if evento.type() == QEvent.Show and isinstance(objeto, QAbstractItemView):
            ancestral = objeto.parent()
            while ancestral is not None and ancestral is not self.raiz:
                ancestral = ancestral.parent()
            if ancestral is self.raiz:
                self.popup(objeto)
        return False

    def popup(self, view):
        # O popup é uma janela Qt própria; alguns temas aplicam um delegate que
        # não herda as regras ::item do widget ancestral.
        t = {k: v.name() for k, v in self.tokens.items()}
        css = ('QAbstractItemView {background:%(superficie)s; color:%(campo_texto)s; '
               'selection-background-color:%(destaque)s; selection-color:%(selecionado_texto)s;}'
               'QAbstractItemView::item:selected, QAbstractItemView::item:hover {'
               'background:%(destaque)s; color:%(selecionado_texto)s;}') % t
        if view.styleSheet() != css:
            view.setStyleSheet(css)
        # O delegate de menu nativo de alguns estilos ignora a paleta da view.
        # O delegate Qt padrão respeita seleção, estados e os dados do modelo.
        if view.itemDelegate().metaObject().className() in ('QComboMenuDelegate', 'QComboBoxDelegate'):
            view.setItemDelegate(QStyledItemDelegate(view))

    def atualizar(self):
        self.tokens = cores(self.origem.palette())
        assinatura = tuple((k, v.name()) for k, v in self.tokens.items())
        if assinatura != self.assinatura:
            self.assinatura = assinatura
            self.raiz.setStyleSheet(estilo(self.tokens))
            for combo in self.raiz.findChildren(QComboBox):
                self.popup(combo.view())
