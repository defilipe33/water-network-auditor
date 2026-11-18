"""Editor do Modelo GIS na Central de Trabalho."""
from copy import deepcopy
from collections import Counter

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)
from qgis.core import QgsProject

from .modelo_gis import (
    CATEGORIAS, CLASSIFICACOES, ESTRATEGIAS, PAPEIS, ROTULOS, VINCULOS_WG, conferir,
    configurar, descrever, estado_fonte, geometria, identificar, preparar_conferencia, relocalizar, revisoes,
    salvar_modelo, sugerir,
)

GEOMETRIAS = dict(Line='Linha', Point='Ponto', Polygon='Polígono', Table='Tabela', Raster='Raster')


def combo(itens, atual=None):
    campo = QComboBox()
    for chave, rotulo in itens.items():
        campo.addItem(rotulo, chave)
    campo.setCurrentIndex(max(0, campo.findData(atual)))
    return campo


def aviso(texto=''):
    rotulo = QLabel(texto)
    rotulo.setWordWrap(True)
    rotulo.setTextFormat(Qt.PlainText)
    return rotulo


def tabela(colunas):
    widget = QTableWidget(0, len(colunas))
    widget.setHorizontalHeaderLabels(colunas)
    widget.setEditTriggers(QTableWidget.NoEditTriggers)
    widget.setSelectionMode(QTableWidget.SingleSelection)
    widget.setSelectionBehavior(QTableWidget.SelectRows)
    widget.verticalHeader().hide()
    widget.verticalHeader().setDefaultSectionSize(22)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    widget.horizontalHeader().setStretchLastSection(True)
    return widget


def linha(tab, valores, dica=''):
    n = tab.rowCount()
    tab.insertRow(n)
    for j, valor in enumerate(valores):
        item = QTableWidgetItem(str(valor))
        item.setToolTip(dica or str(valor))
        tab.setItem(n, j, item)


class FormularioFonte(QDialog):
    def __init__(self, pai, camadas, fonte=None, mover=False):
        super().__init__(pai)
        self.setWindowTitle('Relocalizar fonte GIS' if mover else 'Configurar fonte GIS')
        self.fonte, self.mover, self.resultado = fonte, mover, None
        self.camadas = {c.id(): c for c in camadas if c.isValid() and geometria(c)}
        self._mapas = {}
        self._categoria_anterior = None
        self._camada_anterior = None
        layout = QVBoxLayout(self)
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        conteudo = QWidget()
        area = QVBoxLayout(conteudo)
        rolagem.setWidget(conteudo)
        layout.addWidget(rolagem)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        area.addLayout(form)
        nomes = {c.id(): f'{c.name()} · {GEOMETRIAS[geometria(c)]} · {c.crs().authid() or "sem CRS"}'
                 for c in self.camadas.values()}
        repetidos = {nome for nome, n in Counter(nomes.values()).items() if n > 1}
        nomes = {uid: nome + (' · ' + uid[-8:] if nome in repetidos else '') for uid, nome in nomes.items()}
        atual = identificar(fonte, self.camadas.values()) if fonte else None
        self.camada = combo({'': 'Escolher camada carregada…', **nomes}, atual.id() if atual and not mover else '')
        self.categoria = QComboBox()
        self.papel = combo(PAPEIS, fonte['papel'] if fonte else 'EXISTENTE')
        form.addRow('Camada no QGIS', self.camada)
        form.addRow('Categoria', self.categoria)
        form.addRow('Papel da fonte', self.papel)
        self.sugestao = aviso()
        form.addRow(self.sugestao)
        self.filtro = QLineEdit(fonte['filtro'] if fonte else '')
        self.filtro.setPlaceholderText('Ex.: "TIPO" = \'PRV\'')
        self.filtro.setToolTip('Expressão de atributos aplicada apenas a esta fonte do Modelo GIS.')
        form.addRow('Filtro de atributos', self.filtro)
        self.basicos = QFormLayout()
        self.basicos.setRowWrapPolicy(QFormLayout.WrapLongRows)
        area.addLayout(self.basicos)
        self.alvo = combo({'': 'Sem associação', **{x: x for x in VINCULOS_WG}},
                          fonte['alvo_wg'] if fonte else '')
        self.vinculo = QFormLayout()
        self.vinculo.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.vinculo.addRow('Atributo no WaterGEMS', self.alvo)
        area.addLayout(self.vinculo)
        area.addWidget(aviso('O identificador cadastral identifica a feição GIS. A associação WaterGEMS será conferida ao usar a ferramenta correspondente.'))
        self.avancados = QGroupBox('Atributos técnicos e classificação')
        self.avancados.setCheckable(True)
        av = QVBoxLayout(self.avancados)
        self.extra = QWidget()
        self.atributos = QFormLayout(self.extra)
        self.atributos.setRowWrapPolicy(QFormLayout.WrapLongRows)
        av.addWidget(self.extra)
        self.avancados.toggled.connect(self.extra.setVisible)
        self.avancados.setChecked(False)
        area.addWidget(self.avancados)
        area.addStretch()
        self.feedback = aviso()
        layout.addWidget(self.feedback)
        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.button(QDialogButtonBox.Ok).setText('Aplicar à configuração')
        botoes.accepted.connect(self.aplicar)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)
        self.camada.currentIndexChanged.connect(self.trocar_camada)
        self.categoria.currentIndexChanged.connect(self.trocar_categoria)
        if fonte and not mover:
            self.camada.setEnabled(False)
            if not atual:
                self.feedback.setText('A camada de origem precisa estar carregada para editar. Use Relocalizar fonte.')
        if mover:
            for campo in (self.papel, self.filtro, self.alvo, self.avancados):
                campo.setEnabled(False)
        self.trocar_camada()
        tela = pai.screen().availableGeometry()
        self.resize(min(620, tela.width() - 40), min(590, tela.height() - 60))

    def trocar_camada(self):
        camada = self.camadas.get(self.camada.currentData())
        inicial = self._camada_anterior is None
        estado = self.fonte if inicial or self.mover else None
        self._camada_anterior = self.camada.currentData()
        self._categoria_anterior = None
        self.categoria.blockSignals(True)
        self.categoria.clear()
        self.categoria.addItem('Escolher categoria…', '')
        sugestoes = []
        if camada:
            sugestoes, _ = sugerir(camada)
            for k, cat in CATEGORIAS.items():
                if geometria(camada) in cat.geometrias:
                    self.categoria.addItem(cat.grupo + ' / ' + cat.nome, k)
        if estado:
            self.categoria.setCurrentIndex(max(0, self.categoria.findData(estado['categoria'])))
        self.categoria.blockSignals(False)
        self.categoria.setEnabled(not self.mover)
        self.sugestao.setText('Sugestão: ' + ', '.join(CATEGORIAS[k].nome for k in sugestoes) if sugestoes else '')
        self.trocar_categoria()

    def trocar_categoria(self):
        camada = self.camadas.get(self.camada.currentData())
        categoria = self.categoria.currentData()
        existente = self.fonte if self.fonte and self.fonte['categoria'] == categoria else None
        anterior = {k: c.currentData() for k, c in self._mapas.items()} if self._categoria_anterior else {}
        for form in (self.basicos, self.atributos):
            while form.rowCount():
                form.removeRow(0)
        self._mapas = {}
        self._categoria_anterior = categoria
        if not camada or not categoria:
            return
        nomes = getattr(camada, 'fields', lambda: [])()
        itens = {'': 'Não mapeado', **{f.name(): f.name() for f in nomes}}
        _, sugestoes = sugerir(camada)
        mapa = existente['campos_mapeados'] if existente else (anterior or sugestoes)
        for k in ('id', 'label', 'wg', *CATEGORIAS[categoria].campos):
            atual = mapa.get(k)
            opcoes = itens if not atual or atual in itens else {**itens, atual: atual + ' (ausente)'}
            self._mapas[k] = combo(opcoes, atual)
            self._mapas[k].setEnabled(not self.mover)
            form = self.basicos if k in ('id', 'label', 'wg') else self.atributos
            form.addRow(ROTULOS.get(k, k.replace('_', ' ').capitalize()), self._mapas[k])
        self.classificacao = combo(CLASSIFICACOES, existente['classificacao'] if existente else '')
        if categoria == 'PIPE':
            self.atributos.addRow('Classificação da tubulação', self.classificacao)
        else:
            self.classificacao.setParent(self)
            self.classificacao.hide()

    def aplicar(self):
        camada = self.camadas.get(self.camada.currentData())
        categoria = self.categoria.currentData()
        if not camada or not categoria:
            self.feedback.setText('Escolha a camada e a categoria.')
            return
        try:
            meta = descrever(camada)
            if self.mover:
                prova = relocalizar(self.fonte, meta)
                self.resultado = {**self.fonte, **meta, 'relocalizacao': prova}
                if prova == 'COMPATIVEL_IDENTIDADE_PENDENTE':
                    self.resultado['origem_estavel'] = meta['origem']
            else:
                mapa = {k: c.currentData() for k, c in self._mapas.items()}
                self.resultado = configurar(meta, categoria, self.papel.currentData(),
                                            self.classificacao.currentData(), mapa, self.filtro.text(),
                                            self.alvo.currentData(), self.fonte)
                if self.fonte and self.fonte.get('relocalizacao'):
                    self.resultado['relocalizacao'] = self.fonte['relocalizacao']
        except ValueError as e:
            self.feedback.setText(str(e))
            return
        self.accept()


class PainelModeloGIS(QWidget):
    def __init__(self, central):
        super().__init__(central)
        self.central = central
        self.projetos = central.projetos
        self.projeto_uid = None
        self.anterior = None
        self.fontes = []
        self.resultados = {}
        self._carregando = False
        self._referencia = ([], 'INFERIR')
        self.camadas = lambda: QgsProject.instance().mapLayers().values()
        layout = QVBoxLayout(self)
        self.contexto = aviso()
        layout.addWidget(self.contexto)
        self.estrategia = combo(ESTRATEGIAS, 'INFERIR')
        self.estrategia.setToolTip('A estratégia será usada quando a construção de topologia GIS estiver disponível.')
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.addRow('Como obter os nós da rede?', self.estrategia)
        layout.addLayout(form)
        self.tabela = tabela(['Categoria', 'Camada', 'Filtro', 'Estado', 'Geometria / CRS', 'Identificador'])
        for i, largura in enumerate((114, 129, 123, 103, 122)):
            self.tabela.setColumnWidth(i, largura)
        layout.addWidget(self.tabela, 1)
        self.botoes = []
        for linha_acoes in (
            [('Adicionar fonte…', self.adicionar), ('Editar…', self.editar), ('Relocalizar…', self.mover),
             ('Remover do rascunho', self.remover)],
            [('Conferir fontes', self.conferir), ('Consultar alterações', self.historico),
             ('Salvar Modelo GIS', self.salvar)],
        ):
            faixa = QHBoxLayout()
            layout.addLayout(faixa)
            for texto, acao in linha_acoes:
                b = QPushButton(texto)
                b.clicked.connect(acao)
                faixa.addWidget(b)
                self.botoes.append(b)
        self.botoes[-1].setStyleSheet('font-weight: bold')
        self.feedback = aviso()
        layout.addWidget(self.feedback)
        self.estrategia.currentIndexChanged.connect(self.atualizar)
        self.tabela.itemSelectionChanged.connect(self.acoes)
        self.tabela.itemDoubleClicked.connect(lambda _: self.editar())
        self.recarregar()

    def recarregar(self):
        projeto = self.projetos.atual() or {}
        hist = revisoes(projeto)
        atual = hist[-1] if hist else {}
        self.projeto_uid = projeto.get('uuid')
        self.anterior = atual.get('uuid')
        self._carregando = True
        self.fontes = deepcopy(atual.get('fontes', []))
        estrategia = atual.get('estrategia', 'INFERIR')
        self._referencia = (deepcopy(self.fontes), estrategia)
        self.estrategia.setCurrentIndex(self.estrategia.findData(estrategia))
        self.resultados = {}
        self._carregando = False
        self.feedback.clear()
        self.atualizar()

    def pendente(self):
        return bool(self.projeto_uid) and (self.fontes, self.estrategia.currentData()) != self._referencia

    def resolver(self):
        if not self.pendente():
            return True
        escolha = QMessageBox.question(self, 'Modelo GIS com alterações', 'Salvar a configuração do Modelo GIS?',
                                       QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                                       QMessageBox.Cancel)
        if escolha == QMessageBox.Save:
            return self.salvar()
        if escolha == QMessageBox.Discard:
            self.recarregar()
            return True
        return False

    def acoes(self):
        tem = self.projeto_uid is not None
        selecao = self.tabela.currentRow() >= 0
        self.estrategia.setEnabled(tem)
        estados = [tem, tem and selecao, tem and selecao, tem and selecao,
                   tem and bool(self.fontes), bool(self.anterior), tem and (self.pendente() or not self.anterior)]
        for b, estado in zip(self.botoes, estados):
            b.setEnabled(estado)

    def atualizar(self):
        if self._carregando:
            return
        projeto = self.projetos.atual() or {}
        hist = revisoes(projeto)
        nome = projeto.get('nome')
        info = 'Crie ou selecione um projeto para cadastrar suas fontes GIS.'
        if nome:
            estado = 'Rascunho com alterações' if self.pendente() else (
                'Revisão ' + str(hist[-1]['versao']) if hist else 'Cadastro inicial')
            info = f'{nome} · {estado} · {len(self.fontes)} fonte(s)\nCadastro de fontes · Topologia GIS ainda não construída.'
            if not any(f['categoria'] == 'JUNCTION' for f in self.fontes):
                if self.estrategia.currentData() == 'CADASTRADAS':
                    info += '\nA estratégia de nós cadastrados ainda precisa de uma fonte.'
                else:
                    info += '\nSem camada de Junctions · inferência registrada como estratégia futura.'
        self.contexto.setText(info)
        selecionada = self.tabela.currentRow()
        self.tabela.setRowCount(0)
        camadas = list(self.camadas())
        for fonte in self.fontes:
            camada = identificar(fonte, camadas)
            estado = estado_fonte(fonte, camada)
            verificacao = self.resultados.get(fonte['uid'], {})
            if estado == 'Disponível' and verificacao.get('total') is not None:
                estado += f' · {verificacao["total"]} feição(ões)'
                if verificacao['ausentes'] or verificacao['repetidos']:
                    estado += f' · ID: {verificacao["ausentes"]} vazios, {verificacao["repetidos"]} repetidos'
            chave = fonte['campos_mapeados'].get('id', 'Não mapeado')
            linha(self.tabela, (CATEGORIAS[fonte['categoria']].nome, fonte['nome'], fonte['filtro'] or 'Todas', estado,
                                GEOMETRIAS[fonte['geometria']] + ' / ' + (fonte['crs'] or 'personalizado'),
                                chave))
        if self.fontes and selecionada >= 0:
            self.tabela.selectRow(min(selecionada, len(self.fontes) - 1))
        self.acoes()

    def adicionar(self):
        self.formulario()

    def editar(self):
        self.formulario(self.tabela.currentRow())

    def mover(self):
        self.formulario(self.tabela.currentRow(), mover=True)

    def formulario(self, pos=None, mover=False):
        if not self.projeto_uid or (pos is not None and pos < 0) or self.central.ocupado():
            return
        fonte = self.fontes[pos] if pos is not None else None
        dialogo = FormularioFonte(self, self.camadas(), fonte, mover)
        if dialogo.exec_() != QDialog.Accepted:
            return
        if pos is None:
            self.fontes.append(dialogo.resultado)
        else:
            self.fontes[pos] = dialogo.resultado
        self.resultados.clear()
        self.feedback.setText('Alteração no rascunho. Use Salvar Modelo GIS para registrar uma revisão.')
        self.atualizar()
        self.tabela.selectRow(len(self.fontes) - 1 if pos is None else pos)

    def remover(self):
        if self.central.ocupado():
            return
        pos = self.tabela.currentRow()
        if pos >= 0:
            del self.fontes[pos]
            self.resultados.clear()
            self.feedback.setText('Fonte retirada do rascunho. As revisões salvas continuam disponíveis.')
            self.atualizar()

    def conferir(self):
        if self.central.ocupado():
            return
        atividades = self.central.app.atividades
        try:
            dados = preparar_conferencia(self.fontes, list(self.camadas()))
            def trabalhar(cancelar, sinal):
                return conferir(dados, cancelar, lambda etapa: sinal(0, etapa))
            self.feedback.setText('Acompanhe a leitura das fontes em Atividade.')
            atividades.executar_thread(
                'Conferir fontes do Modelo GIS', self.contexto.text(), trabalhar, self.receber_conferencia,
                lambda erro: self.feedback.setText(erro),
            )
        except Exception as e:
            self.feedback.setText(str(e))

    def receber_conferencia(self, dados):
        self.resultados, pares = dados
        alertas = []
        fontes = {f['uid']: f for f in self.fontes}
        for (a, b), n in pares.items():
            x, y = fontes[a], fontes[b]
            alertas.append(f'{x["nome"]} ({CATEGORIAS[x["categoria"]].nome} / {CATEGORIAS[y["categoria"]].nome}): {n}')
        ids = sum(r['ausentes'] + r['repetidos'] for r in self.resultados.values())
        msg = f'Conferência concluída. {ids} identificador(es) ausente(s) ou repetido(s).'
        if alertas:
            msg += f' {len(alertas)} par(es) de fontes compartilham feições.'
        self.feedback.setText(self.resumo_conferencia(msg, alertas))
        self.atualizar()

    def resumo_conferencia(self, mensagem, sobreposicoes):
        linhas = [mensagem]
        if sobreposicoes:
            linhas.extend(['Feições em mais de uma configuração:', *sobreposicoes[:12]])
        if len(sobreposicoes) > 12:
            linhas.append(f'Mais {len(sobreposicoes) - 12} combinações.')
        if not any(f['categoria'] == 'JUNCTION' for f in self.fontes):
            linhas.append('Sem camada de Junctions cadastrada.')
        return '\n'.join(linhas)

    def salvar(self):
        if not self.projeto_uid or self.central.ocupado():
            return False
        try:
            nova = salvar_modelo(self.projetos, self.projeto_uid, self.anterior,
                                 self.fontes, self.estrategia.currentData())
        except (ValueError, OSError) as e:
            self.feedback.setText('Cadastro mantido no rascunho. ' + str(e))
            return False
        self.anterior = nova['uuid']
        self._referencia = (deepcopy(self.fontes), self.estrategia.currentData())
        msg = f'Modelo GIS salvo na revisão {nova["versao"]}.'
        if nova['referencias_para_conferir']:
            msg += ' Confira a aplicabilidade das análises vinculadas antes de reutilizá-las.'
        self.feedback.setText(msg)
        self.atualizar()
        self.central.atualizar()
        return True

    def historico(self):
        dlg = QDialog(self)
        dlg.setWindowTitle('Revisões do Modelo GIS')
        layout = QVBoxLayout(dlg)
        revisoes_ = list(reversed(revisoes(self.projetos.atual())))
        tab = tabela(['Revisão', 'Data UTC', 'Fontes', 'Fontes alteradas', 'Análises para conferir'])
        layout.addWidget(tab)
        fontes = tabela(['Categoria', 'Camada', 'Filtro', 'Mapeamento'])
        layout.addWidget(fontes)
        estrategia = aviso()
        layout.addWidget(estrategia)
        for r in revisoes_:
            linha(tab, (r['versao'], r['data_utc'][:19], len(r['fontes']),
                        len(r['fontes_alteradas']), len(r['referencias_para_conferir'])))
        def mostrar():
            if tab.currentRow() < 0:
                return
            r = revisoes_[tab.currentRow()]
            fontes.setRowCount(0)
            estrategia.setText(ESTRATEGIAS[r['estrategia']])
            for f in r['fontes']:
                linha(fontes, (CATEGORIAS[f['categoria']].nome, f['nome'], f['filtro'] or 'Todas',
                              ', '.join(f'{ROTULOS.get(k, k)} = {v}' for k, v in f['campos_mapeados'].items())))
        tab.itemSelectionChanged.connect(mostrar)
        tab.selectRow(0)
        fechar = QDialogButtonBox(QDialogButtonBox.Close)
        fechar.rejected.connect(dlg.reject)
        layout.addWidget(fechar)
        tela = self.screen().availableGeometry()
        dlg.resize(min(710, tela.width() - 40), min(480, tela.height() - 60))
        dlg.exec_()
