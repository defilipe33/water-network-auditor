"""Layouts em coordenadas lógicas Qt; sem alterar DPI ou preferências globais."""
import weakref
from hashlib import sha256
from qgis.PyQt.QtCore import Qt,QObject,QEvent,QRect,QTimer
from qgis.PyQt.QtGui import QCursor
from qgis.PyQt.QtWidgets import (QApplication,QWidget,QDialog,QDockWidget,QVBoxLayout,QHBoxLayout,
    QGridLayout,QBoxLayout,QFormLayout,QLayout,QScrollArea,QPushButton,QDialogButtonBox,
    QComboBox,QCheckBox,QSizePolicy,QTableWidget,QTreeWidget,QHeaderView)
from qgis.PyQt import sip


def ajustar_rect(rect,area):
    """Área já é lógica: multiplicar por devicePixelRatio aplicaria DPI duas vezes."""
    w=min(max(240,rect.width()),max(120,area.width()-32))
    h=min(max(160,rect.height()),max(100,area.height()-56))
    return QRect(min(max(rect.x(),area.x()+16),area.right()-w-15),
                 min(max(rect.y(),area.y()+40),area.bottom()-h-15),w,h)


def _chave(janela):
    papel=janela.objectName() or janela.windowTitle()
    return 'auditoria_redes/janelas/'+type(janela).__name__+'_'+sha256(papel.encode('utf8')).hexdigest()[:12]


def _acoes(layout):
    itens=[layout.itemAt(i) for i in range(layout.count())]
    return bool(itens) and all(x.spacerItem() or isinstance(x.widget(),(QPushButton,QDialogButtonBox)) for x in itens)


def _grade_botoes(layout,grades):
    for i in range(layout.count()):
        item=layout.itemAt(i);sub=item.layout()
        if not sub:continue
        if isinstance(sub,QHBoxLayout) and _acoes(sub) and isinstance(layout,QBoxLayout):
            botoes=[]
            while sub.count():
                x=sub.takeAt(0)
                if x.widget():botoes.append(x.widget())
            layout.takeAt(i);sub.setParent(None);sub.deleteLater()
            grade=QGridLayout();layout.insertLayout(i,grade);grades.append((grade,botoes))
        else:_grade_botoes(sub,grades)


def configurar_controles(root):
    for f in root.findChildren(QFormLayout):f.setRowWrapPolicy(QFormLayout.WrapLongRows)
    for c in root.findChildren(QComboBox):
        c.setMinimumWidth(0);c.setMinimumContentsLength(12)
        c.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        c.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed)
    for t in root.findChildren(QTableWidget)+root.findChildren(QTreeWidget):
        t.setMinimumSize(0,70);t.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        t.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        h=t.horizontalHeader() if isinstance(t,QTableWidget) else t.header()
        h.setMinimumSectionSize(45);h.setSectionsMovable(True)


class _Guarda(QObject):
    def __init__(self,app):super().__init__(app);self.raizes=weakref.WeakSet();self.pendentes=set()
    def eventFilter(self,obj,event):
        if event.type()==QEvent.Show and isinstance(obj,(QDialog,QDockWidget)) and type(obj).__name__ not in ('QMessageBox','QFileDialog','QProgressDialog','QInputDialog'):
            p=obj
            while p is not None and p not in self.raizes:p=p.parentWidget()
            if p is not None:
                adaptar_janela(obj)
                self.enquadrar(obj,restaurar=True)
        elif event.type()==QEvent.Resize and isinstance(obj,(QDialog,QDockWidget)) and obj.property('wna/adaptada'):
            self.organizar(obj)
        elif event.type()==getattr(QEvent,'ScreenChangeInternal',216) and isinstance(obj,(QDialog,QDockWidget)) and obj.property('wna/adaptada'):
            self.enquadrar(obj)
        elif event.type()==QEvent.Close and isinstance(obj,(QDialog,QDockWidget)) and obj.property('wna/adaptada'):
            if obj._wna_lembrar.isChecked():
                from qgis.core import QgsSettings
                s=QgsSettings();s.setValue(_chave(obj)+'/geometria',obj.saveGeometry())
                s.setValue(_chave(obj)+'/lembrar',True)
            else:
                from qgis.core import QgsSettings
                # Não escrever preferências quando o usuário nunca optou por elas.
                s=QgsSettings();k=_chave(obj)+'/lembrar'
                if s.contains(k):s.setValue(k,False)
        return False
    def organizar(self,obj):
        largura=max(200,obj.width()-65)
        for grade,botoes in getattr(obj,'_wna_grades',[]):
            colunas=2 if largura>=620 else 1
            for b in botoes:grade.removeWidget(b)
            for i,b in enumerate(botoes):
                b.setMinimumWidth(0);b.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);b.setToolTip(b.toolTip() or b.text() if isinstance(b,QPushButton) else '')
                grade.addWidget(b,i//colunas,i%colunas)
    def enquadrar(self,obj,restaurar=False,area=None):
        if sip.isdeleted(obj):return
        if isinstance(obj,QDockWidget) and not obj.isFloating() and not obj.isWindow():
            obj.setMinimumWidth(0);self.organizar(obj);return
        if restaurar and not obj.property('wna/restaurada'):
            from qgis.core import QgsSettings
            s=QgsSettings();k=_chave(obj)
            lembrar=s.value(k+'/lembrar',False,type=bool);obj._wna_lembrar.setChecked(lembrar)
            obj.setProperty('wna/restaurada',True)
            if lembrar and s.contains(k+'/geometria'):obj.restoreGeometry(s.value(k+'/geometria'))
        tela=QApplication.screenAt(obj.frameGeometry().center()) or (obj.windowHandle().screen() if obj.windowHandle() else None)
        tela=tela or QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if not tela:return
        area=area if area is not None else tela.availableGeometry()
        r=ajustar_rect(obj.geometry(),area)
        obj.setMinimumSize(min(320,r.width()),min(180,r.height()))
        obj.setMaximumSize(max(120,area.width()-32),max(100,area.height()-56))
        if not obj.isMaximized():obj.setGeometry(r)
        self.organizar(obj)


def adaptar_janela(janela):
    app=QApplication.instance()
    if not hasattr(app,'_wna_guarda'):
        app._wna_guarda=_Guarda(app);app.installEventFilter(app._wna_guarda)
    app._wna_guarda.raizes.add(janela)
    if janela.property('wna/adaptada'):return
    raiz=janela.widget() if isinstance(janela,QDockWidget) else janela
    antigo=raiz.layout()
    if antigo is None:return
    janela.setProperty('wna/adaptada',True);janela._wna_grades=[]
    configurar_controles(raiz)
    rodapes=[]
    for i in range(antigo.count()-1,-1,-1):
        x=antigo.itemAt(i)
        if isinstance(x.widget(),(QPushButton,QDialogButtonBox)) or (x.layout() and _acoes(x.layout())):
            rodapes.append(antigo.takeAt(i))
        elif rodapes:break
    existente=next((antigo.itemAt(i).widget() for i in range(antigo.count()) if isinstance(antigo.itemAt(i).widget(),QScrollArea)),None)
    if existente is not None:externo=antigo;scroll=existente
    else:
        corpo=QWidget();corpo.setLayout(antigo);corpo.setMinimumSize(0,0)
        antigo.setSizeConstraint(QLayout.SetDefaultConstraint)
        externo=QVBoxLayout(raiz);scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(corpo)
        externo.addWidget(scroll,1)
    scroll.setMinimumSize(0,0);janela._wna_scroll=scroll
    for rodape in reversed(rodapes):
        if rodape.widget():
            b=rodape.widget();b.setMinimumWidth(0);b.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);externo.addWidget(b)
        elif rodape.layout():externo.addLayout(rodape.layout())
    lembrar=QCheckBox('Lembrar tamanho e posição nesta tela');externo.addWidget(lembrar);janela._wna_lembrar=lembrar
    _grade_botoes(externo,janela._wna_grades)
    # Inclui os botões que permaneceram no conteúdo rolável.
    _grade_botoes(antigo,janela._wna_grades)
    app._wna_guarda.enquadrar(janela)
