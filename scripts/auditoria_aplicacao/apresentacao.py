"""Uma instância QDockWidget, duas apresentações, sem recriar seu conteúdo."""
from qgis.PyQt.QtCore import QObject,QEvent,QTimer,Qt,QSettings
from qgis.PyQt.QtWidgets import QApplication,QComboBox,QMessageBox
from qgis.PyQt import sip
from auditoria_fronteiras.ui_comum import ajustar_rect

class Apresentacao(QObject):
    def __init__(self,app,dock,chave,settings=None):
        super().__init__(dock);self.app=app;self.dock=dock;self.chave='apresentacao/'+chave;self.settings=settings or QSettings(str(app.catalogo.raiz/'preferencias_interface.ini'),QSettings.IniFormat);self._restaurando=False;self.combo=QComboBox();self.combo.addItems(['Painel integrado','Janela independente']);self.combo.setToolTip('Alterna a mesma interface, preservando formulários, filtros e seleção.');self.combo.currentIndexChanged.connect(self.alterar);dock.installEventFilter(self);self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(300);self.timer.timeout.connect(self.salvar);dock.topLevelChanged.connect(self.sincronizar)
    def ocupado(self):return self.app.ocupado or self.app.geo._executando or self.app.atividades.em_execucao() or bool(self.app.wg and self.app.wg.ocupado)
    def restaurar(self):
        self._restaurando=True
        try:
            modo=self.settings.value(self.chave+'/modo',0,type=int);self.aplicar(modo)
            geo=self.settings.value(self.chave+'/geometria')
            if modo and geo:self.dock.restoreGeometry(geo)
            self.enquadrar()
            if modo and self.settings.value(self.chave+'/maximizada',False,type=bool):self.dock.showMaximized()
        finally:self._restaurando=False
        self.sincronizar(self.dock.isFloating())
    def alterar(self,n):
        if self._restaurando:return
        if self.ocupado():
            self.sincronizar(self.dock.isFloating());QMessageBox.information(self.dock,'Aguarde a operação','A apresentação poderá ser alterada quando o processamento terminar ou for cancelado em ponto seguro.');return
        canvas=self.app.iface.mapCanvas() if hasattr(self.app.iface,'mapCanvas') else None
        vista=(canvas.center(),canvas.scale()) if canvas and canvas.scale()>0 else None
        self._restaurando=True
        try:self.aplicar(n);self.enquadrar()
        finally:self._restaurando=False
        self.salvar()
        if vista:
            def conservar_mapa():
                if not sip.isdeleted(canvas):canvas.setCenter(vista[0]);canvas.zoomScale(vista[1])
            QTimer.singleShot(0,conservar_mapa)
    def aplicar(self,n):
        d=self.dock
        if n:
            d.setFloating(True);d.setWindowFlags(Qt.Window|Qt.WindowMinMaxButtonsHint|Qt.WindowCloseButtonHint);d.show()
        else:
            area=self.settings.value(self.chave+'/area',int(Qt.RightDockWidgetArea),type=int)
            if area not in (int(Qt.LeftDockWidgetArea),int(Qt.RightDockWidgetArea)):area=int(Qt.RightDockWidgetArea)
            self.app.iface.mainWindow().addDockWidget(Qt.DockWidgetArea(area),d);d.setFloating(False);d.show()
        self.combo.blockSignals(True);self.combo.setCurrentIndex(1 if n else 0);self.combo.blockSignals(False)
    def sincronizar(self,flutuante):
        if sip.isdeleted(self.dock):return
        self.combo.blockSignals(True);self.combo.setCurrentIndex(1 if flutuante else 0);self.combo.blockSignals(False)
        if not self._restaurando:self.timer.start()
    def enquadrar(self):
        d=self.dock
        if not d.isFloating():return
        tela=QApplication.screenAt(d.frameGeometry().center()) or QApplication.primaryScreen()
        if not tela:return
        area=tela.availableGeometry();d.setMinimumSize(min(350,area.width()-32),min(200,area.height()-56));d.setMaximumSize(area.width()-24,area.height()-40)
        if not d.isMaximized():d.setGeometry(ajustar_rect(d.geometry(),area))
    def salvar(self):
        if sip.isdeleted(self.dock) or self._restaurando:return
        s=self.settings;d=self.dock;s.setValue(self.chave+'/modo',int(d.isFloating()));s.setValue(self.chave+'/area',int(self.app.iface.mainWindow().dockWidgetArea(d)));s.setValue(self.chave+'/maximizada',d.isMaximized());s.setValue(self.chave+'/geometria',d.saveGeometry());t=d.screen();s.setValue(self.chave+'/monitor',t.name() if t else '');s.sync()
    def eventFilter(self,obj,event):
        if not sip.isdeleted(self.dock) and obj is self.dock:
            if event.type() in (QEvent.Move,QEvent.Resize,QEvent.WindowStateChange) and not self._restaurando:self.timer.start()
            elif event.type()==QEvent.Close:self.salvar()
            elif event.type()==getattr(QEvent,'ScreenChangeInternal',216):self.enquadrar()
        return False
