from pathlib import Path
import sys
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction,QFileDialog,QMessageBox
from qgis.core import QgsSettings
from qgis.gui import QgsApplicationExitBlockerInterface
from qgis.PyQt import sip
from .bootstrap import ativar

class AuditoriaRedesPlugin:
    def __init__(self,iface):self.iface=iface;self.app=None;self.acao=None;self.toolbar=None;self.finder=None;self.bloqueador=None;self.acao_pasta=None;self._verificando_saida=False
    def initGui(self):
        if self.acao is not None:return
        self.acao=QAction(QIcon(str(Path(__file__).with_name('icone.svg'))),'Auditoria de Redes — GIS & WaterGEMS',self.iface.mainWindow());self.acao.triggered.connect(self.abrir)
        self.toolbar=self.iface.addToolBar('Auditoria de Redes');self.toolbar.setObjectName('AuditoriaRedesToolbar');self.toolbar.addAction(self.acao)
        self.iface.addPluginToMenu('&Auditoria de Redes',self.acao)
        self.acao_pasta=QAction('Alterar pasta de trabalho…',self.iface.mainWindow());self.acao_pasta.triggered.connect(self.alterar_pasta);self.iface.addPluginToMenu('&Auditoria de Redes',self.acao_pasta)
        plugin=self
        class Bloqueador(QgsApplicationExitBlockerInterface):
            def allowExit(self):return plugin.permitir_saida()
        self.bloqueador=Bloqueador();self.iface.registerApplicationExitBlocker(self.bloqueador)
    def permitir_saida(self):
        # QMessageBox executa um event loop: uma nova tentativa não pode entrar
        # recursivamente nem considerar a primeira autorização já concedida.
        if self._verificando_saida:return False
        self._verificando_saida=True
        try:
            if self.app is None:return True
            return bool(self.app.preparar_saida())
        except Exception:
            import traceback
            from qgis.core import QgsMessageLog,Qgis
            QgsMessageLog.logMessage(traceback.format_exc(),'Water Network Auditor',Qgis.Critical)
            principal=self.iface.mainWindow()
            if not sip.isdeleted(principal):QMessageBox.warning(principal,'Encerramento adiado','Não foi possível verificar as alterações pendentes. O QGIS permanecerá aberto. Salve seu trabalho e consulte o painel de mensagens Water Network Auditor antes de tentar novamente.')
            return False
        finally:self._verificando_saida=False
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
        except Exception as e:
            import traceback
            from qgis.core import QgsMessageLog,Qgis
            detalhes=traceback.format_exc();QgsMessageLog.logMessage(detalhes,'Water Network Auditor',Qgis.Critical)
            aviso=QMessageBox(self.iface.mainWindow());aviso.setIcon(QMessageBox.Warning);aviso.setWindowTitle('Ferramenta não aberta');aviso.setText('Não foi possível abrir o Water Network Auditor.');aviso.setInformativeText(str(e)+'\nOs arquivos de origem não foram alterados. Verifique a pasta de trabalho e a instalação; os detalhes técnicos estão disponíveis abaixo.');aviso.setDetailedText(detalhes);aviso.exec_()
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
