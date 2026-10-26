"""Seleção compacta, somente apresentação; não abre nem altera uma execução."""
from pathlib import Path
from qgis.PyQt.QtCore import Qt,QSize
from qgis.PyQt.QtWidgets import (QApplication,QDialog,QVBoxLayout,QLabel,QListWidget,
    QListWidgetItem,QWidget,QGridLayout,QDialogButtonBox,QTextBrowser,QSizePolicy)


class SeletorVersoes(QDialog):
    def __init__(self,itens,parent=None,execucao_ativa=None):
        super().__init__(parent)
        self.itens=itens
        self.setWindowTitle('Versões disponíveis')
        tela=QApplication.primaryScreen().availableGeometry()
        self.resize(min(720,tela.width()-40),min(220+min(len(itens),3)*145,tela.height()-60))
        self.setMinimumSize(min(420,tela.width()-40),min(340,tela.height()-60))
        layout=QVBoxLayout(self)
        aviso=QLabel('Selecione uma execução e confirme para abri-la. Cancelar mantém a auditoria atual.')
        aviso.setWordWrap(True);layout.addWidget(aviso)
        self.lista=QListWidget();self.lista.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self.lista,1)
        self.detalhes=QTextBrowser();self.detalhes.setMaximumHeight(115)
        layout.addWidget(self.detalhes)
        self.botoes=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        self.botoes.accepted.connect(self.confirmar);self.botoes.rejected.connect(self.reject)
        layout.addWidget(self.botoes)
        self._caminhos=[]
        origens={(r.get('base'),r.get('origem')) for r in itens if r.get('origem')}
        for r in itens:
            item=QListWidgetItem(self.lista)
            card=QWidget();card.setAttribute(Qt.WA_TransparentForMouseEvents)
            grade=QGridLayout(card);grade.setContentsMargins(8,6,8,6)
            situacao=('SUBSTITUÍDA' if not r.get('ativa',True) else
                'HISTÓRICA — origem preservada' if (r.get('base'),r['execucao_uid']) in origens else 'ATIVA — não substituída')
            if r['execucao_uid']==execucao_ativa:
                situacao+=' | em inspeção'
            o=r.get('agrupamento',{})
            valores=[(r.get('nome') or 'Auditoria',0,0,1,2),
                (r.get('projeto') or 'Projeto não informado',1,0,1,2),
                (f"Processada: {r.get('data','—')}\n{r.get('eventos',0)} eventos · {r.get('locais',0)} locais",2,0,1,1),
                (f"Operação: {r.get('operacao','—')}\n{situacao}",2,1,1,1),
                (f"Busca: {o.get('distancia','não registrada')} m · Extensão: {o.get('extensao_maxima','não registrada')} m",3,0,1,2),
                (f"Execução: {r['execucao_uid'][:12]}… · Origem: {(r.get('origem') or 'nenhuma')[:12]}",4,0,1,2)]
            for texto,linha,coluna,altura,largura in valores:
                label=QLabel(texto);label.setTextFormat(Qt.PlainText);label.setWordWrap(True)
                label.setToolTip(texto)
                if linha in (0,1):label.setMaximumHeight(label.fontMetrics().lineSpacing()*2+2)
                label.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
                if linha==0:
                    f=label.font();f.setBold(True);label.setFont(f)
                grade.addWidget(label,linha,coluna,altura,largura)
            caminho=QLabel();caminho.setToolTip(r.get('base',''))
            caminho.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
            grade.addWidget(caminho,5,0,1,2);self._caminhos.append((caminho,r.get('base','')))
            self.lista.setItemWidget(item,card);item.setSizeHint(QSize(0,200))
        self.lista.currentRowChanged.connect(self.atualizar_detalhes)
        self.lista.itemDoubleClicked.connect(lambda _:self.confirmar())
        self.lista.setCurrentRow(0 if itens else -1)
        self.botoes.button(QDialogButtonBox.Ok).setEnabled(bool(itens))
        self.abreviar()
        from auditoria_fronteiras.ui_comum import adaptar_janela
        adaptar_janela(self)

    def abreviar(self):
        for label,caminho in self._caminhos:
            label.setText(label.fontMetrics().elidedText(caminho,Qt.ElideMiddle,max(100,self.width()-65)))

    def resizeEvent(self,evento):
        super().resizeEvent(evento)
        if hasattr(self,'_caminhos'):
            self.abreviar()

    def atualizar_detalhes(self,linha):
        if linha<0:
            self.detalhes.clear();return
        r=self.itens[linha]
        self.detalhes.setPlainText(f"Auditoria: {r.get('nome') or 'Auditoria'}\nProjeto: {r.get('projeto') or 'Não informado'}\nID completo: {r['execucao_uid']}\n"
            f"Origem: {r.get('origem') or 'Nenhuma'}\nGeoPackage: {r.get('base','')}\n"
            f"Última revisão: {r.get('ultima_revisao') or 'Não registrada'}")

    def selecionada(self):
        linha=self.lista.currentRow()
        return self.itens[linha] if linha>=0 else None

    def confirmar(self):
        if self.selecionada() is not None:
            self.accept()
