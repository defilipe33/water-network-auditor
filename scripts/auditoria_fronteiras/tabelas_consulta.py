"""Tabelas de apresentação: dados integrais, nulos explícitos e colunas configuráveis."""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,QToolButton,QMenu,
    QAction,QTableWidget,QTableWidgetItem,QAbstractItemView,QHeaderView,QDialog,QPlainTextEdit,QPushButton)


def texto_valor(v):return '〈nulo〉' if v is None else '〈vazio〉' if v=='' else str(v)


class TabelaConsulta(QWidget):
    def __init__(self,cabecalhos,parent=None):
        super().__init__(parent);v=QVBoxLayout(self);v.setContentsMargins(0,0,0,0);l=QHBoxLayout();v.addLayout(l)
        self.busca=QLineEdit();self.busca.setPlaceholderText('Filtrar qualquer coluna…');l.addWidget(self.busca)
        self.colunas=QToolButton();self.colunas.setText('Colunas');self.colunas.setPopupMode(QToolButton.InstantPopup);menu=QMenu(self.colunas);self.colunas.setMenu(menu);l.addWidget(self.colunas)
        self.tabela=QTableWidget(0,len(cabecalhos));self.tabela.setHorizontalHeaderLabels(cabecalhos);v.addWidget(self.tabela,1)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers);self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded);self.tabela.setWordWrap(False)
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive);self.tabela.horizontalHeader().setSectionsMovable(True)
        self.tabela.horizontalHeader().setStretchLastSection(False)
        for i,h in enumerate(cabecalhos):
            a=QAction(h,menu);a.setCheckable(True);a.setChecked(True);a.toggled.connect(lambda visivel,c=i:self.tabela.setColumnHidden(c,not visivel));menu.addAction(a)
            self.tabela.setColumnWidth(i,160)
        self.busca.textChanged.connect(self.filtrar);self.tabela.itemDoubleClicked.connect(self.exibir_celula)
        menu.aboutToShow.connect(self.sincronizar_colunas)
    def sincronizar_colunas(self):
        for c,a in enumerate(self.colunas.menu().actions()):
            a.blockSignals(True);a.setChecked(not self.tabela.isColumnHidden(c));a.blockSignals(False)
    def preencher(self,linhas):
        self.tabela.setSortingEnabled(False);self.tabela.setRowCount(len(linhas))
        for r,linha in enumerate(linhas):
            for c,valor in enumerate(linha):
                item=QTableWidgetItem(texto_valor(valor));item.setData(Qt.UserRole,valor);item.setToolTip(texto_valor(valor));self.tabela.setItem(r,c,item)
        self.tabela.setSortingEnabled(True);self.filtrar()
    def filtrar(self):
        q=self.busca.text().casefold()
        for r in range(self.tabela.rowCount()):
            texto=' '.join(self.tabela.item(r,c).text() for c in range(self.tabela.columnCount()) if self.tabela.item(r,c)).casefold()
            self.tabela.setRowHidden(r,q not in texto)
    def exibir_celula(self,item):
        j=QDialog(self);j.setWindowTitle('Valor completo — somente leitura');j.resize(640,380)
        l=QVBoxLayout(j);t=QPlainTextEdit();t.setReadOnly(True);t.setPlainText(item.text());l.addWidget(t)
        b=QPushButton('Fechar');b.clicked.connect(j.accept);l.addWidget(b)
        from .ui_comum import adaptar_janela
        adaptar_janela(j);j.exec_()
