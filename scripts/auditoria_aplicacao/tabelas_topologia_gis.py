"""Tabelas compactas para investigação e revisão de relações GIS."""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QAbstractItemView, QHeaderView, QMenu, QTableWidget, QTableWidgetItem


ACOMPANHAMENTO={
    'PENDENTE':'Pendente', 'EM_ANALISE':'Em análise', 'VERIFICADO':'Verificado',
    'DESCARTADO':'Descartado', 'NECESSITA_CONFIRMACAO':'Necessita confirmação',
}
ESTADO_COMPONENTE={
    'ALCANCAVEL':'Com origem alcançável',
    'SEM_ORIGEM_ALCANCAVEL':'Sem ligação topológica a origem',
    'SEM_ORIGENS_VALIDAS':'Acesso a origens indeterminado',
}


def celula(valor):
    texto=f'{valor:.2f}' if isinstance(valor,float) else '—' if valor is None else str(valor)
    item=QTableWidgetItem(texto)
    item.setToolTip(texto)
    if isinstance(valor,(int,float)):item.setTextAlignment(Qt.AlignRight|Qt.AlignVCenter)
    return item


class TabelaGIS(QTableWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.verticalHeader().hide()
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.horizontalHeader().setDefaultSectionSize(104)
        self.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self._menu_colunas)
        self._titulos=()

    def colunas(self,titulos):
        if self._titulos==titulos:return
        self._titulos=titulos
        self.setColumnCount(len(titulos))
        self.setHorizontalHeaderLabels(titulos)
        for i,titulo in enumerate(titulos):
            self.horizontalHeaderItem(i).setToolTip(titulo)
            self.showColumn(i)
            self.setColumnWidth(i,max(74,min(185,self.fontMetrics().horizontalAdvance(titulo)+30)))

    def _menu_colunas(self,ponto):
        menu=QMenu('Colunas visíveis',self)
        for i,titulo in enumerate(self._titulos):
            acao=menu.addAction(titulo)
            acao.setCheckable(True)
            acao.setChecked(not self.isColumnHidden(i))
            acao.setEnabled(i!=0)
            acao.toggled.connect(lambda mostrar,i=i:self.setColumnHidden(i,not mostrar))
        menu.exec_(self.horizontalHeader().mapToGlobal(ponto))
        menu.deleteLater()

    def limpar(self):
        self.setRowCount(0)

    def inserir(self,valores,registro=None):
        linha=self.rowCount()
        self.insertRow(linha)
        for j,v in enumerate(valores):
            item=celula(v)
            if j==0:item.setData(Qt.UserRole,registro)
            self.setItem(linha,j,item)
        return self.item(linha,0)


class TabelaRelacoes(TabelaGIS):
    """A primeira coluna guarda a identidade e a marca de participação."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.colunas(('Incluída / nome','Tipo','Natureza','Interpretação','Revisão','Acompanhamento','Hipóteses'))

    def item(self,linha,coluna=0):
        return super().item(linha,coluna)

    def currentItem(self):
        return self.item(self.currentRow())

    def count(self):
        return self.rowCount()

    def clear(self):
        self.limpar()
