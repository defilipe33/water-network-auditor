"""Gestos comuns para registros georreferenciados em vistas Qt."""

from qgis.PyQt.QtCore import QItemSelectionModel, QModelIndex, QPersistentModelIndex, Qt
from qgis.PyQt.QtWidgets import QMenu


def acao_disponivel(controle, motivo, dica=''):
    """Um motivo presente desabilita a ação e permanece acessível."""
    controle.setEnabled(not motivo)
    controle.setToolTip(motivo or dica)
    if hasattr(controle, 'setAccessibleDescription'):
        controle.setAccessibleDescription(motivo or dica)


def navegar_registros(vista, navegar, acoes=None, limpar=None, navegar_varios=None,elegivel=None):
    """Usa índices da vista, inclusive quando a apresentação é filtrada.

    navegar recebe (índice, aproximar). Ações extras são pares (rótulo, ação)
    ou trios (rótulo, ação, motivo de indisponibilidade). None separa grupos.
    """
    def registro(indice):
        return indice.siblingAtColumn(0)

    def selecionar(indice, preservar=False):
        selecao = vista.selectionModel()
        if preservar and selecao.isSelected(indice):
            selecao.setCurrentIndex(indice, QItemSelectionModel.NoUpdate)
        else:
            selecao.setCurrentIndex(indice, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)

    def duplo(indice):
        if indice.isValid() and (elegivel is None or elegivel(indice)):
            selecionar(indice)
            if registro(vista.currentIndex())==registro(indice):
                navegar(indice, True)

    def contexto(ponto):
        indice = vista.indexAt(ponto)
        if not indice.isValid() or elegivel is not None and not elegivel(indice):
            return
        selecionar(indice, preservar=True)
        if registro(vista.currentIndex())!=registro(indice):
            return
        alvo = QPersistentModelIndex(indice)
        menu = QMenu(vista)
        menu.setToolTipsVisible(True)

        def usar(aproximar):
            if alvo.isValid():
                navegar(QModelIndex(alvo), aproximar)

        opcoes = [('Aproximar e destacar', lambda: usar(True)), ('Apenas destacar', lambda: usar(False))]
        if navegar_varios:
            selecionados = {QPersistentModelIndex(registro(i)) for i in vista.selectedIndexes()}
            if len(selecionados) > 1:
                def varios():
                    indices = [QModelIndex(i) for i in selecionados if i.isValid()]
                    if indices:
                        navegar_varios(indices)
                opcoes.append(('Enquadrar seleção', varios))
        if limpar:
            opcoes.append(('Limpar destaque', limpar))
        extras = acoes(indice) if acoes else ()
        if extras:
            opcoes.extend([None, *extras])
        for opcao in opcoes:
            if opcao is None:
                menu.addSeparator()
                continue
            titulo, executar, *motivo = opcao
            action = menu.addAction(titulo)
            if motivo and motivo[0]:
                acao_disponivel(action, motivo[0])
            else:
                action.triggered.connect(lambda _, executar=executar: executar())
        menu.exec_(vista.viewport().mapToGlobal(ponto))
        menu.deleteLater()

    vista.doubleClicked.connect(duplo)
    vista.setContextMenuPolicy(Qt.CustomContextMenu)
    vista.customContextMenuRequested.connect(contexto)
