"""Identidade e recuperação de interfaces; nunca reprocessa ou repõe formulários."""
import weakref
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QObject,Qt
from qgis.PyQt.QtWidgets import QAction,QDialog,QApplication


class Janelas(QObject):
    def __init__(self,principal):super().__init__(principal);self.principal=principal;self.itens={};self.ativa=None
    def registrar(self,chave,janela,titulo,reabrir=None):
        self.itens[chave]=dict(ref=weakref.ref(janela),titulo=titulo,reabrir=reabrir)
        # Diálogos irmãos do QGIS não acompanham hide() de outro diálogo.
        # Não reparentear docks nem widgets já visíveis ou modais em execução.
        if isinstance(janela,QDialog) and not janela.isVisible() and janela.parentWidget()!=self.principal:
            janela.setParent(self.principal,janela.windowFlags())
        janela.setAttribute(Qt.WA_DeleteOnClose,False)
        janela._wna_janelas=self
        return janela
    def obter(self,chave):
        item=self.itens.get(chave);w=item['ref']() if item else None
        return w if w is not None and not sip.isdeleted(w) else None
    def mostrar(self,chave):
        w=self.obter(chave)
        if w is None:return False
        modal=QApplication.activeModalWidget()
        if modal is not None and modal is not w:
            modal.raise_();modal.activateWindow();return False
        if self.principal.isMinimized():self.principal.setWindowState(self.principal.windowState() & ~Qt.WindowMinimized)
        if getattr(w,'_ativo',True) is False:
            fn=self.itens[chave]['reabrir']
            return bool(fn()) if fn else False
        # Uma restauração nunca substitui contexto, dados, seleção ou rascunho.
        if w.isMinimized():w.showNormal()
        else:w.show()
        w.raise_();w.activateWindow();self.ativa=chave;return True
    def ocultar(self,chave):
        w=self.obter(chave)
        if w:w.hide()
    def restaurar(self):
        # Assistentes concluídos não são reabertos. Janelas fechadas explicitamente
        # permanecem disponíveis por ação individual, sem ressuscitar todo auxiliar.
        for chave in ('gis','watergems','integrada'):
            if self.obter(chave) is not None:self.mostrar(chave)
    def preencher_menu(self,menu):
        menu.clear()
        for chave,item in list(self.itens.items()):
            w=self.obter(chave)
            if w is None or (chave=='assistente' and getattr(w,'resultado',None)):continue
            a=QAction('Mostrar '+item['titulo'],menu);a.triggered.connect(lambda _,k=chave:self.mostrar(k));menu.addAction(a)
        if menu.actions():
            menu.addSeparator();a=menu.addAction('Restaurar janelas abertas');a.triggered.connect(self.restaurar)
    def limpar(self):self.itens.clear();self.ativa=None


def registrar_auxiliar(origem,chave,janela,titulo):
    p=origem
    while p is not None:
        g=getattr(p,'_wna_janelas',None)
        if g:
            g.registrar(chave,janela,titulo)
            from .atividade import sistema
            sistema(origem).vincular(janela)
            return g
        p=p.parentWidget()
    return None
