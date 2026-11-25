"""Tabelas compactas para investigação e revisão de relações GIS."""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem


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
        self.horizontalHeader().setDefaultSectionSize(125)

    def colunas(self,titulos):
        self.setColumnCount(len(titulos))
        self.setHorizontalHeaderLabels(titulos)

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
        self.colunas(('Participa / nome','Natureza','Interpretação','Hipóteses'))

    def item(self,linha,coluna=0):
        return super().item(linha,coluna)

    def currentItem(self):
        return self.item(self.currentRow())

    def count(self):
        return self.rowCount()

    def clear(self):
        self.limpar()
