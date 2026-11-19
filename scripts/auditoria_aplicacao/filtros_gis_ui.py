"""Construtor visual sob demanda; abrir não altera filtros existentes."""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QTreeWidget, QTreeWidgetItem, QLineEdit, QListWidget, QWidget, QVBoxLayout
from qgis.core import QgsVectorLayerFeatureSource
from .modelo_gis_ui import combo, formulario, botao, aviso
from .filtros_gis import operadores, gerar, valores_amostrados


class ConstrutorFiltros(QWidget):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.sujo = False
        v = QVBoxLayout(self)
        v.addWidget(aviso('Selecione um grupo para adicionar condições. Cada grupo combina seus itens com E ou OU. O filtro anterior só muda ao usar as condições.'))
        self.arvore = QTreeWidget()
        self.arvore.setHeaderLabels(['Condições e grupos'])
        self.arvore.setMinimumHeight(120)
        self.arvore.setMaximumHeight(140)
        v.addWidget(self.arvore)
        self.raiz = QTreeWidgetItem(self.arvore, ['Todas as condições (E)'])
        self.raiz.setData(0, Qt.UserRole, {'grupo': 'AND'})
        self.arvore.setCurrentItem(self.raiz)
        f = formulario(v)
        self.conectivo = combo({'AND': 'E — todas', 'OR': 'OU — pelo menos uma'})
        f.addRow('Conectivo do grupo', self.conectivo)
        botao(v, 'Aplicar conectivo ao grupo', self.conectar)
        botao(v, 'Adicionar subgrupo', self.grupo)
        self.campo = combo({k: k for k in editor.meta['campos']})
        self.operador = combo({})
        self.valor = combo({}); self.valor.setEditable(True)
        self.valor2 = QLineEdit()
        f.addRow('Campo', self.campo); f.addRow('Operador', self.operador)
        f.addRow('Valor', self.valor); f.addRow('Segundo valor', self.valor2)
        self.rotulo_valor2 = f.labelForField(self.valor2)
        self.lista_valores = QListWidget(); self.lista_valores.setMaximumHeight(85); v.addWidget(self.lista_valores)
        self.add_valor = botao(v, 'Acrescentar valor à lista', self.adicionar_valor)
        self.rem_valor = botao(v, 'Retirar valor selecionado da lista', self.remover_valor)
        self.campo.currentIndexChanged.connect(self.trocar_campo)
        self.operador.currentIndexChanged.connect(self.trocar_operador)
        self.arvore.currentItemChanged.connect(self.selecionar)
        botao(v, 'Consultar valores existentes (amostra)', self.valores)
        botao(v, 'Adicionar condição', self.adicionar)
        botao(v, 'Atualizar condição selecionada', self.editar)
        botao(v, 'Remover item selecionado', self.remover)
        botao(v, 'Usar condições no filtro', self.aplicar)
        self.info = aviso('Filtro existente preservado no Modo especialista. Nenhuma conversão automática foi feita.' if editor.filtro.text() else '')
        v.addWidget(self.info)
        self.trocar_campo()

    def trocar_campo(self):
        self.operador.blockSignals(True); self.operador.clear()
        for k, nome in operadores(self.editor.meta['campos'].get(self.campo.currentData(), '')).items():
            self.operador.addItem(nome, k)
        self.operador.blockSignals(False)
        self.valor.clear(); self.trocar_operador()

    def trocar_operador(self):
        op = self.operador.currentData()
        self.valor.setEnabled(op not in ('IS NULL', 'VAZIO', 'NAO_VAZIO'))
        self.valor2.setVisible(op == 'ENTRE')
        self.rotulo_valor2.setVisible(op == 'ENTRE')
        for w in (self.lista_valores, self.add_valor, self.rem_valor): w.setVisible(op == 'LISTA')
        self.valor.setToolTip('Datas: AAAA-MM-DD. Valores existentes são apenas uma amostra. Para listas, acrescente cada valor com o botão.')

    def adicionar_valor(self):
        valor = self.valor.currentText()
        if valor not in [self.lista_valores.item(i).text() for i in range(self.lista_valores.count())]:
            self.lista_valores.addItem(valor)

    def remover_valor(self):
        self.lista_valores.takeItem(self.lista_valores.currentRow())

    def pai(self):
        item = self.arvore.currentItem() or self.raiz
        return item if 'grupo' in item.data(0, Qt.UserRole) else item.parent()

    def conectar(self):
        p = self.pai(); op = self.conectivo.currentData()
        p.setData(0, Qt.UserRole, {'grupo': op}); p.setText(0, 'Todas as condições (E)' if op == 'AND' else 'Pelo menos uma condição (OU)')
        self.sujo = True

    def grupo(self):
        item = QTreeWidgetItem(self.pai(), ['Todas as condições (E)'])
        item.setData(0, Qt.UserRole, {'grupo': 'AND'}); self.arvore.setCurrentItem(item)
        self.arvore.expandAll(); self.sujo = True

    def condicao(self):
        n = dict(campo=self.campo.currentData(), operador=self.operador.currentData(),
                 valor=self.valor.currentText(), valor2=self.valor2.text())
        if n['operador'] == 'LISTA': n['valor'] = [self.lista_valores.item(i).text() for i in range(self.lista_valores.count())]
        gerar(n, self.editor.meta['campos'])
        return n

    def escrever(self, item, n):
        item.setData(0, Qt.UserRole, n)
        item.setText(0, n['campo'] + ' · ' + operadores(self.editor.meta['campos'][n['campo']])[n['operador']] + ' · ' + str(n['valor']) + (' até ' + n['valor2'] if n['operador'] == 'ENTRE' else ''))
        self.arvore.expandAll(); self.sujo = True

    def adicionar(self):
        try:
            n = self.condicao(); item = QTreeWidgetItem(self.pai()); self.escrever(item, n)
        except ValueError as e: self.info.setText(str(e))

    def editar(self):
        item = self.arvore.currentItem()
        if item is None or 'grupo' in item.data(0, Qt.UserRole): return
        try: self.escrever(item, self.condicao())
        except ValueError as e: self.info.setText(str(e))

    def remover(self):
        item = self.arvore.currentItem()
        if item is not None and item is not self.raiz:
            item.parent().removeChild(item); self.sujo = True

    def selecionar(self, item, *_):
        if item is None: return
        n = item.data(0, Qt.UserRole)
        if 'grupo' in n:
            self.conectivo.setCurrentIndex(self.conectivo.findData(n['grupo'])); return
        self.campo.setCurrentIndex(self.campo.findData(n['campo']))
        self.operador.setCurrentIndex(self.operador.findData(n['operador']))
        self.lista_valores.clear()
        if isinstance(n['valor'], list):
            self.lista_valores.addItems(n['valor']); self.valor.setEditText('')
        else: self.valor.setEditText(n['valor'])
        self.valor2.setText(n.get('valor2', ''))

    def dados(self, item=None):
        item = item or self.raiz
        n = dict(item.data(0, Qt.UserRole))
        if 'grupo' in n: n['itens'] = [self.dados(item.child(i)) for i in range(item.childCount())]
        return n

    def aplicar(self):
        try:
            texto = gerar(self.dados(), self.editor.meta['campos'])
            self.editor.filtro.setText(texto); self.sujo = False
            self.info.setText('Expressão gerada: ' + texto)
        except ValueError as e: self.info.setText(str(e))

    def valores(self):
        if self.editor.painel.central.ocupado(): return
        try:
            fonte = QgsVectorLayerFeatureSource(self.editor.camada()); campo = self.campo.currentData()
            self.editor.painel.central.app.atividades.executar_thread(
                'Consultar valores GIS', campo,
                lambda parar, _: valores_amostrados(fonte, campo, parar),
                lambda valores: self.receber_valores(campo, valores), self.info.setText)
        except (ValueError, RuntimeError) as e: self.info.setText(str(e))

    def receber_valores(self, campo, valores):
        if self.campo.currentData() != campo: return
        atual = self.valor.currentText(); self.valor.clear(); self.valor.addItems(valores)
        self.valor.setEditText(atual)
        self.info.setText(f'{len(valores)} valor(es) distintos em até 250 feições; lista parcial, sem contagem global.')
