"""Quadro contextual sobre a mesma instância do cadastro multifonte."""
from qgis.PyQt.QtWidgets import QGridLayout, QPushButton, QVBoxLayout, QWidget
from uuid import uuid4

from .modelo_gis import CATEGORIAS
from .modelo_gis_ui import aviso, combo

GRUPOS_QUADRO = {
    'REDES': ('PIPE',),
    'EQUIPAMENTOS': ('PRV', 'TCV', 'FCV', 'PBV', 'AIR_VALVE', 'HYDRANT', 'REGISTRO',
                     'PUMP', 'BOOSTER', 'RESERVOIR', 'TANK', 'ENTRADA', 'DISPOSITIVO'),
    'ÁREAS': ('SETOR', 'ZONA_VRP', 'ZONA_BOOSTER', 'ZONA'),
    'CONECTIVIDADE': ('JUNCTION',),
}


class QuadroModelo(QWidget):
    def __init__(self, central):
        super().__init__()
        self.central, self.modelo = central, central.modelo_gis
        self.grupo = 'REDES'
        self.modelo.setParent(self)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(aviso('O que tenho no meu modelo?',))
        grid = QGridLayout()
        grid.setSpacing(6)
        v.addLayout(grid)
        self.cards = {}
        for i, nome in enumerate(GRUPOS_QUADRO):
            b = QPushButton(nome)
            b.setObjectName('ComponenteModelo')
            b.setCheckable(True)
            b.clicked.connect(lambda _, n=nome: self.escolher(n))
            grid.addWidget(b, i // 2, i % 2)
            self.cards[nome] = b
        self.categorias = combo({c: CATEGORIAS[c].nome for c in GRUPOS_QUADRO[self.grupo]})
        self.categorias.currentIndexChanged.connect(self.escolher_categoria)
        v.addWidget(self.categorias)
        v.addWidget(self.modelo, 1)
        self.modelo.show()
        self.modelo.contexto.hide()
        self.modelo.feedback.hide()
        self.modelo.atualizar_original = self.modelo.atualizar
        self.modelo.atualizar = self.atualizar_modelo
        self.modelo.abrir_inicio = self.voltar_quadro
        voltar = self.modelo.detalhe.findChildren(QPushButton)[0]
        voltar.setText('Quadro e resumo')
        voltar.hide()
        voltar.clicked.disconnect()
        voltar.clicked.connect(self.resumo)
        self.modelo.lista.itemClicked.connect(self.realcar)
        self.modelo.lista.itemActivated.connect(self.realcar)
        self.reclassificar = QPushButton('Usar esta fonte em outra categoria…')
        extra = self.modelo.mover_b.parentWidget().layout()
        extra.addWidget(self.reclassificar)
        self.reclassificar.clicked.connect(self.classificar)
        self.resumo_pagina, area = self.modelo.pagina()
        self.resumo_b = QPushButton('Resumo e revisões')
        self.resumo_b.clicked.connect(self.resumo)
        extra.addWidget(self.resumo_b)
        self.resumo_texto = aviso()
        area.addWidget(self.resumo_texto)
        b = QPushButton('Conferir fontes')
        b.clicked.connect(self.modelo.conferir)
        area.addWidget(b)
        b = QPushButton('Continuar cadastro')
        b.clicked.connect(lambda: self.escolher(self.grupo))
        area.addWidget(b)
        b = QPushButton('Revisões do cadastro')
        b.clicked.connect(self.modelo.historico)
        area.addWidget(b)
        area.addStretch()
        self.escolher(self.grupo)

    def atualizar_modelo(self):
        self.modelo.atualizar_original()
        self.atualizar()
        if hasattr(self.central, 'contexto_curto'):
            self.central.atualizar_contexto()

    def atualizar(self):
        self.modelo.feedback.setVisible(bool(self.modelo.feedback.text()))
        for nome, categorias in GRUPOS_QUADRO.items():
            fs = [f for f in self.modelo.fontes if f['categoria'] in categorias]
            n = sum(bool(self.modelo.pendencias_fonte(f)) for f in fs)
            texto = f'{len(fs)} fonte(s)' if fs else 'Sem fontes'
            if nome == 'CONECTIVIDADE' and self.modelo.estrategia.currentData() != 'CADASTRADAS':
                texto = 'Inferência prevista'
            if n:
                texto += f' · {n} a revisar'
            self.cards[nome].setText(nome + '\n' + texto)
            self.cards[nome].setChecked(nome == self.grupo)
        self.categorias.setEnabled(self.modelo.tarefa is None)
        for b in self.cards.values():
            b.setEnabled(self.modelo.tarefa is None)
        if self.central.projetos.atual():
            self.modelo.salvar_b.setText('Salvar alterações' if self.modelo.pendente() else 'Salvar Modelo GIS')

    def voltar_quadro(self):
        if self.modelo.tarefa is None:
            self.escolher(self.grupo)

    def escolher(self, grupo):
        if self.modelo.tarefa is not None or self.central.ocupado():
            return
        self.grupo = grupo
        self.central.settings.setValue('quadro/grupo', grupo)
        self.categorias.blockSignals(True)
        self.categorias.clear()
        for c in GRUPOS_QUADRO[grupo]:
            self.categorias.addItem(CATEGORIAS[c].nome, c)
        self.categorias.blockSignals(False)
        self.categorias.setVisible(len(GRUPOS_QUADRO[grupo]) > 1)
        self.escolher_categoria()

    def escolher_categoria(self):
        categoria = self.categorias.currentData()
        if categoria:
            self.central.settings.setValue('quadro/categoria', categoria)
            self.modelo.abrir_categoria(categoria)
            nomes = {'REDES': 'Adicionar camadas', 'EQUIPAMENTOS': 'Adicionar equipamentos',
                     'ÁREAS': 'Adicionar zonas ou setores', 'CONECTIVIDADE': 'Adicionar Junctions cadastradas'}
            self.modelo.adicionar_b.setText(nomes[self.grupo])
            self.modelo.editar_b.setText('Editar detalhes da fonte')
        self.atualizar()

    def realcar(self, *_):
        fonte = self.modelo.fonte_selecionada()
        if fonte and self.central.paginas.currentWidget() is self:
            self.central.destacar_fonte(fonte)

    def resumo(self):
        if self.modelo.tarefa is not None:
            return
        m = self.modelo
        linhas = []
        for nome, cats in GRUPOS_QUADRO.items():
            fs = [f for f in m.fontes if f['categoria'] in cats]
            linhas.append(f'{nome} · {len(fs)} fonte(s)')
            linhas.extend(f"  {f['nome']} · {CATEGORIAS[f['categoria']].nome}" for f in fs)
        linhas += [m.estrategia.currentText(), 'Topologia GIS ainda não construída.']
        self.resumo_texto.setText('\n'.join(linhas))
        m.mostrar(self.resumo_pagina)

    def classificar(self):
        from copy import deepcopy
        fonte = self.modelo.fonte_selecionada()
        if not fonte or self.central.ocupado():
            return
        opcoes = {c: cat.nome for c, cat in CATEGORIAS.items()
                  if fonte['geometria'] in cat.geometrias and c != fonte['categoria']}
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(aviso('Classificar ' + fonte['nome']))
        escolha = combo(opcoes)
        layout.addWidget(escolha)
        layout.addWidget(aviso('Os campos compatíveis serão reaproveitados. Revise o filtro para selecionar os elementos desta categoria.'))

        def aplicar():
            categoria = escolha.currentData()
            if not categoria:
                return
            if any(f['origem'] == fonte['origem'] and f['categoria'] == categoria
                   for f in self.modelo.fontes):
                self.modelo.feedback.setText('Esta fonte já foi cadastrada na categoria. Edite o filtro existente.')
                return
            nova = deepcopy(fonte)
            nova['uid'] = uuid4().hex
            nova['categoria'] = categoria
            nova['campos_mapeados'] = {k: v for k, v in fonte['campos_mapeados'].items()
                                      if k in ('id', 'label', 'wg', *CATEGORIAS[categoria].campos)}
            self.modelo.fontes.append(nova)
            self.modelo.limpar_conferencia()
            self.modelo.cancelar_tarefa()
            grupo = next((n for n, cs in GRUPOS_QUADRO.items() if categoria in cs), None)
            if grupo:
                self.escolher(grupo)
                self.categorias.setCurrentIndex(self.categorias.findData(categoria))
                self.modelo.selecionada = nova['uid']
                self.modelo.atualizar()
            self.modelo.feedback.setText('Fonte reaproveitada no rascunho. Confira o filtro e eventuais sobreposições.')
            self.modelo.editar()

        self.modelo.mostrar_tarefa(w, 'Criar classificação', aplicar)
