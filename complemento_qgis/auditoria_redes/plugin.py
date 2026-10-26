from pathlib import Path
import sys
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction,QFileDialog,QMessageBox
from qgis.core import QgsSettings
from qgis.gui import QgsApplicationExitBlockerInterface
from .bootstrap import ativar

class AuditoriaRedesPlugin:
    def __init__(self,iface):self.iface=iface;self.app=None;self.acao=None;self.toolbar=None;self.finder=None;self.bloqueador=None;self.acao_pasta=None
    def initGui(self):
        if self.acao is not None:return
        self.acao=QAction(QIcon(str(Path(__file__).with_name('icone.svg'))),'Auditoria de Redes — GIS & WaterGEMS',self.iface.mainWindow());self.acao.triggered.connect(self.abrir)
        self.toolbar=self.iface.addToolBar('Auditoria de Redes');self.toolbar.setObjectName('AuditoriaRedesToolbar');self.toolbar.addAction(self.acao)
        self.iface.addPluginToMenu('&Auditoria de Redes',self.acao)
        self.acao_pasta=QAction('Alterar pasta de trabalho…',self.iface.mainWindow());self.acao_pasta.triggered.connect(self.alterar_pasta);self.iface.addPluginToMenu('&Auditoria de Redes',self.acao_pasta)
        plugin=self
        class Bloqueador(QgsApplicationExitBlockerInterface):
            def exitBlocked(self):return bool(plugin.app and not plugin.app.preparar_saida())
        self.bloqueador=Bloqueador();self.iface.registerApplicationExitBlocker(self.bloqueador)
    def abrir(self):
        try:
            if self.app is None:
                if self.finder is None:self.finder=ativar(Path(__file__).with_name('_biblioteca'))
                settings=QgsSettings();raiz=settings.value('auditoria_redes/pasta_trabalho','')
                if not raiz or not Path(raiz).is_dir():
                    raiz=QFileDialog.getExistingDirectory(self.iface.mainWindow(),'Pasta de trabalho das auditorias')
                    if not raiz:return
                    settings.setValue('auditoria_redes/pasta_trabalho',raiz)
                from auditoria_aplicacao.controlador import Aplicacao
                self.app=Aplicacao(self.iface,raiz)
            self.app.abrir()
        except Exception as e:QMessageBox.warning(self.iface.mainWindow(),'Auditoria de Redes',str(e))
    def alterar_pasta(self):
        raiz=QFileDialog.getExistingDirectory(self.iface.mainWindow(),'Pasta de trabalho das auditorias')
        if not raiz:return
        if self.app and not self.app.encerrar():return
        QgsSettings().setValue('auditoria_redes/pasta_trabalho',raiz);self.app=None;self.abrir()
    def unload(self):
        if self.app and not self.app.encerrar():raise RuntimeError('Descarregamento cancelado: resolva alterações pendentes ou aguarde o processamento')
        if self.bloqueador:self.iface.unregisterApplicationExitBlocker(self.bloqueador);self.bloqueador=None
        if self.acao_pasta:self.iface.removePluginMenu('&Auditoria de Redes',self.acao_pasta);self.acao_pasta.deleteLater();self.acao_pasta=None
        if self.acao is not None:
            self.iface.removePluginMenu('&Auditoria de Redes',self.acao);self.toolbar.removeAction(self.acao);self.acao.deleteLater();self.acao=None
        if self.toolbar is not None:self.toolbar.deleteLater();self.toolbar=None
        if self.finder in sys.meta_path:sys.meta_path.remove(self.finder)
        # Bibliotecas já carregadas são reutilizadas na mesma versão; sem remover
        # módulos enquanto objetos QGIS ainda podem referenciá-los.
        self.finder=None;self.app=None
