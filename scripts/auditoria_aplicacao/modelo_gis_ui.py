"""Editor do Modelo GIS na Central de Trabalho."""
from copy import deepcopy
from collections import Counter
from textwrap import fill

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import (
    QListWidget, QListWidgetItem, QSizePolicy, QStackedWidget, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHeaderView, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)
from qgis.core import QgsProject, QgsVectorLayer, QgsVectorLayerFeatureSource

from .cadastro_gis import OPERADORES, amostra, copiar_mapeamento, filtro_simples, incluir_fontes, sugerir_campos
from .modelo_gis import (
    CATEGORIAS, CLASSIFICACOES, ESTRATEGIAS, PAPEIS, ROTULOS, VINCULOS_WG, conferir,
    configurar, descrever, estado_fonte, geometria, identificar, preparar_conferencia, relocalizar, revisoes,
    salvar_modelo, expressao, origem_camada,
)

GEOMETRIAS = dict(Line='Linha', Point='Ponto', Polygon='Polígono', Table='Tabela', Raster='Raster')


def combo(itens, atual=None):
    campo = QComboBox()
    campo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    campo.setMinimumContentsLength(8)
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



def botao(layout, texto, acao=None):
    b = QPushButton(texto)
    if acao is not None:
        b.clicked.connect(acao)
    layout.addWidget(b)
    return b


def expansivel(layout, texto, botao_em=None):
    b = botao(botao_em if botao_em is not None else layout, texto)
    b.setCheckable(True)
    w = QWidget()
    layout.addWidget(w)
    w.hide()
    b.toggled.connect(w.setVisible)
    corpo = QVBoxLayout(w)
    corpo.setContentsMargins(10, 2, 2, 4)
    return b, corpo


def formulario(layout):
    form = QFormLayout()
    form.setRowWrapPolicy(QFormLayout.WrapLongRows)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    layout.addLayout(form)
    return form


def lista_compacta():
    lista = QListWidget()
    lista.setWordWrap(True)
    lista.setTextElideMode(Qt.ElideNone)
    lista.setMinimumHeight(95)
    lista.setMaximumHeight(120)
    return lista


class CamposSobDemanda(dict):
    def __init__(self, criar):
        super().__init__()
        self.criar = criar

    def __missing__(self, chave):
        self.criar()
        return dict.__getitem__(self, chave)


class EditorFonte(QWidget):
    def __init__(self, painel, fonte, camada):
        super().__init__()
        self.painel, self.fonte = painel, fonte
        self.meta = descrever(camada)
        self._avancados = False
        self._papel = self._classe = None
        self.mapa = CamposSobDemanda(self.preparar_avancados)
        area = QVBoxLayout(self)
        area.addWidget(aviso(CATEGORIAS[fonte['categoria']].nome + ' · ' + fonte['nome']))
        essenciais = formulario(area)
        itens = {'': 'Não mapeado', **{f: f for f in self.meta['campos']}}
        _, ambiguos = sugerir_campos(self.meta['campos'], fonte['categoria'])
        self._opcoes_campos, self._ambiguos = itens, ambiguos
        self._extras_iniciais = {k: fonte['campos_mapeados'].get(k) for k in CATEGORIAS[fonte['categoria']].campos}
        for k in ('id', 'label', 'wg'):
            self.campo(essenciais, k, itens, ambiguos)
        self.alvo = combo({'': 'Sem associação', **{x: x for x in VINCULOS_WG}}, fonte['alvo_wg'])
        essenciais.addRow('Atributo no WaterGEMS', self.alvo)
        self.abrir_adicionais, self._extra = expansivel(area, 'Propriedades adicionais')
        self.abrir_adicionais.toggled.connect(lambda aberto: self.preparar_avancados() if aberto else None)
        self.estado_filtro = aviso()
        area.addWidget(self.estado_filtro)
        self.abrir_simples, simples = expansivel(area, 'Montar filtro simples')
        form = formulario(simples)
        self.coluna = combo(itens)
        self.operador = combo(OPERADORES)
        self.valor = QLineEdit()
        self.operador.currentIndexChanged.connect(
            lambda: self.valor.setEnabled(not self.operador.currentData().startswith('IS ')))
        form.addRow('Campo', self.coluna)
        form.addRow('Operador', self.operador)
        form.addRow('Valor', self.valor)
        self.usar_filtro_b = botao(simples, 'Usar este filtro', self.usar_filtro)
        _, avancado = expansivel(area, 'Expressão avançada')
        self.filtro = QLineEdit(fonte['filtro'])
        formulario(avancado).addRow('Expressão', self.filtro)
        botao(avancado, 'Limpar filtro', self.filtro.clear)
        self.amostra = tabela([])
        self.amostra.setMaximumHeight(145)
        area.addWidget(self.amostra)
        self.mensagem = aviso()
        area.addWidget(self.mensagem)
        self.filtro.textChanged.connect(self.atualizar_filtro)
        self._regra_aplicada = self.regra()
        self.atualizar_filtro()
        botao(area, 'Ver amostra dos valores', self.prever).setEnabled(isinstance(camada, QgsVectorLayer))
        area.addStretch()

    def preparar_avancados(self):
        if self._avancados:
            return
        self._avancados = True
        form = formulario(self._extra)
        for k in CATEGORIAS[self.fonte['categoria']].campos:
            self.campo(form, k, self._opcoes_campos, self._ambiguos)
        self._papel = combo(PAPEIS, self.fonte['papel'])
        self._classe = combo(CLASSIFICACOES, self.fonte['classificacao'])
        form.addRow('Papel da fonte', self._papel)
        if self.fonte['categoria'] == 'PIPE':
            form.addRow('Classificação', self._classe)

    @property
    def papel(self):
        self.preparar_avancados()
        return self._papel

    @property
    def classe(self):
        self.preparar_avancados()
        return self._classe

    def campo(self, form, k, itens, ambiguos):
        rotulo = ROTULOS.get(k, k.replace('_', ' ').capitalize())
        atual = self.fonte['campos_mapeados'].get(k)
        opcoes = itens if not atual or atual in itens else {**itens, atual: atual + ' (ausente)'}
        self.mapa[k] = combo(opcoes, atual)
        form.addRow(rotulo, self.mapa[k])
        if k in ambiguos and not atual:
            form.addRow(aviso('Opções para ' + rotulo.lower() + ': ' + ', '.join(ambiguos[k])))

    def atualizar_filtro(self):
        self.estado_filtro.setText('Filtro: ' + (self.filtro.text().strip() or 'todas as feições'))
        self.amostra.hide()

    def usar_filtro(self):
        try:
            campo, operador, valor = self.regra()
            self.filtro.setText(filtro_simples(campo, self.meta['campos'].get(campo, ''),
                                              operador, valor))
            self._regra_aplicada = self.regra()
            self.mensagem.setText('Filtro definido. Use a amostra ou aplique à fonte.')
        except ValueError as e:
            self.mensagem.setText(str(e))

    def camada(self):
        camada = identificar(self.fonte, self.painel.camadas())
        if camada is None:
            raise ValueError('Carregue a fonte no QGIS ou relocalize antes de editar.')
        return camada

    def valores(self):
        campos = {} if self._avancados else dict(self._extras_iniciais)
        campos.update({k: c.currentData() for k, c in self.mapa.items()})
        papel = self._papel.currentData() if self._avancados else self.fonte['papel']
        classe = self._classe.currentData() if self._avancados else self.fonte['classificacao']
        return ({k: v for k, v in campos.items() if v},
                self.filtro.text().strip(), self.alvo.currentData(),
                papel, classe)

    def regra(self):
        return self.coluna.currentData(), self.operador.currentData(), self.valor.text()

    def regra_pendente(self):
        return bool(self.coluna.currentData()) and self.regra() != self._regra_aplicada

    def pendente(self):
        f = self.fonte
        return self.regra_pendente() or self.valores() != (
            f['campos_mapeados'], f['filtro'], f['alvo_wg'], f['papel'], f['classificacao'])

    def configurar(self):
        if self.regra_pendente():
            campo, operador, valor = self.regra()
            self.filtro.setText(filtro_simples(campo, self.meta['campos'][campo], operador, valor))
            self._regra_aplicada = self.regra()
        mapa, filtro, alvo, papel, classe = self.valores()
        nova = configurar(descrever(self.camada()), self.fonte['categoria'], papel,
                          classe, mapa, filtro, alvo, self.fonte)
        if 'relocalizacao' in self.fonte:
            nova['relocalizacao'] = self.fonte['relocalizacao']
        return nova

    def prever(self):
        if self.painel.central.ocupado():
            return
        try:
            mapa, texto, *_ = self.valores()
            campos = list(dict.fromkeys(mapa.values()))
            fonte = QgsVectorLayerFeatureSource(self.camada())
            disponiveis = fonte.fields().names()
            if not set(campos) <= set(disponiveis):
                raise ValueError('Revise os campos ausentes antes de gerar a amostra.')
            expr = expressao(texto, disponiveis)
            if expr is not None and not campos:
                campos = sorted(expr.referencedColumns())
            self.mensagem.setText('Lendo uma amostra de até 250 feições.')
            self.painel.central.app.atividades.executar_thread(
                'Amostra de atributos', self.fonte['nome'],
                lambda cancelar, _: amostra(fonte, campos, texto, cancelar),
                lambda resultado: self.mostrar_amostra(campos, resultado),
                self.mensagem.setText)
        except (ValueError, RuntimeError) as e:
            self.mensagem.setText(str(e))

    def mostrar_amostra(self, campos, resultado):
        linhas, n, completa = resultado
        self.mensagem.setText(f'{n} feição(ões) correspondem ao filtro.' if completa else
                              f'{n} correspondência(s) nas primeiras 250 feições. Total não calculado.')
        self.amostra.setRowCount(0)
        self.amostra.setColumnCount(max(1, len(campos)))
        self.amostra.setHorizontalHeaderLabels(campos or ['Feições correspondentes'])
        for i, valores in enumerate(linhas, 1):
            linha(self.amostra, ['Nulo' if v is None else v for v in valores] or [i])
        self.amostra.setVisible(bool(linhas))

GRUPOS = {
    'Redes': 'Redes',
    'Válvulas e equipamentos': 'Válvulas e equipamentos',
    'Reservatórios e bombas': 'Reservatórios e bombeamento',
    'Zonas e setores': 'Zonas e setores',
    'Nós': 'Junctions e conectividade',
    'Intervenções': 'Intervenções e apoio',
    'Camadas auxiliares': 'Intervenções e apoio',
}


class PainelModeloGIS(QWidget):
    def __init__(self, central):
        super().__init__(central)
        self.central, self.projetos = central, central.projetos
        self.camadas = lambda: QgsProject.instance().mapLayers().values()
        self.fontes, self.resultados, self.pares, self.alertas_lote = [], {}, {}, {}
        self._referencia = ([], 'INFERIR')
        self.categoria = self.editor = self.tarefa = self.selecionada = None
        self._estado = {}
        self._pendencias_cache = {}
        self._observadas = set()
        self._resolvidas_ids = set()
        self._fontes_sujas = False
        self._refresh_fontes = QTimer(self)
        self._refresh_fontes.setSingleShot(True)
        self._refresh_fontes.timeout.connect(self.atualizar)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.contexto = aviso()
        layout.addWidget(self.contexto)
        self.rolagem = QScrollArea()
        self.rolagem.setWidgetResizable(True)
        layout.addWidget(self.rolagem, 1)
        self.paginas = QStackedWidget()
        self.paginas.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.rolagem.setWidget(self.paginas)
        self.inicio, area = self.pagina()
        pergunta = aviso('O que você quer cadastrar?')
        pergunta.setStyleSheet('font-weight: bold')
        area.addWidget(pergunta)
        self.grupos, self.categorias, self.contagens = {}, {}, {}
        for grupo in dict.fromkeys(GRUPOS.values()):
            chaves = [k for k, cat in CATEGORIAS.items() if GRUPOS[cat.grupo] == grupo]
            faixa = QHBoxLayout()
            faixa.setSpacing(4)
            area.addLayout(faixa)
            if len(chaves) == 1:
                chave = chaves[0]
                b = botao(faixa, grupo, lambda _, k=chave: self.abrir_categoria(k))
                self.categorias[chave] = b
            else:
                b, sub = expansivel(area, grupo, faixa)
                for k in chaves:
                    self.categorias[k] = botao(sub, CATEGORIAS[k].nome,
                                              lambda _, c=k: self.abrir_categoria(c))
            self.grupos[grupo] = b, chaves
            b.setStyleSheet('font-weight: bold; text-align: left; padding: 3px')
            r = self.contagens[grupo] = aviso()
            faixa.addWidget(r, 1)
        botao(area, 'Consultar alterações', self.historico)
        area.addStretch()
        self.detalhe, area = self.pagina()
        botao(area, '‹ Categorias', self.abrir_inicio)
        self.titulo = aviso()
        self.titulo.setStyleSheet('font-weight: bold')
        area.addWidget(self.titulo)
        self.nos = QWidget()
        area.addWidget(self.nos)
        no_layout = QVBoxLayout(self.nos)
        no_layout.setContentsMargins(0, 0, 0, 0)
        no_layout.addWidget(aviso('Como serão obtidos os nós da rede?'))
        self.estrategia = combo(ESTRATEGIAS, 'INFERIR')
        no_layout.addWidget(self.estrategia)
        no_layout.addWidget(aviso('A estratégia será usada na Etapa 2, durante a construção da topologia GIS.'))
        self.adicionar_b = botao(area, 'Adicionar camadas…', self.adicionar)
        self.lista = lista_compacta()
        area.addWidget(self.lista)
        self.info_fonte = aviso()
        area.addWidget(self.info_fonte)
        self.editar_b = botao(area, 'Configurar campos e filtro…', self.editar)
        self.copiar_b = botao(area, 'Aplicar mapeamento a outras camadas…', self.escolher_lote)
        self.conferir_b = botao(area, 'Conferir fontes', self.conferir)
        self.alertas = QVBoxLayout()
        area.addLayout(self.alertas)
        self.mais_acoes, layout_extra = expansivel(area, 'Mais ações da fonte')
        self.mover_b = botao(layout_extra, 'Relocalizar fonte…', self.mover)
        self.remover_b = botao(layout_extra, 'Remover associação', self.remover)
        area.addStretch()
        self.lista.currentItemChanged.connect(self.atualizar_fonte)
        self.lista.itemDoubleClicked.connect(lambda _: self.editar())
        self.estrategia.currentIndexChanged.connect(self.atualizar)
        self.feedback = aviso()
        layout.addWidget(self.feedback)
        self.salvar_b = botao(layout, 'Salvar Modelo GIS', self.salvar)
        self.salvar_b.setStyleSheet('font-weight: bold')
        self.rodape_tarefa = QWidget()
        faixa = QHBoxLayout(self.rodape_tarefa)
        faixa.setContentsMargins(0, 0, 0, 0)
        self.cancelar_b = botao(faixa, 'Voltar', self.cancelar_tarefa)
        self.confirmar_b = botao(faixa, 'Aplicar', self.confirmar_tarefa)
        self.acao_tarefa = None
        layout.addWidget(self.rodape_tarefa)
        self.rodape_tarefa.hide()
        self.recarregar()
        QgsProject.instance().layersAdded.connect(self.ao_mudar_camadas)
        QgsProject.instance().layersRemoved.connect(self.ao_mudar_camadas)

    def ao_mudar_camadas(self, _):
        self.limpar_conferencia()
        self.atualizar()

    def fonte_mudou(self, *_):
        origem = self.sender()
        if origem is not None and origem.id() not in self._resolvidas_ids:
            return
        self.limpar_conferencia()
        self._pendencias_cache.clear()
        self._fontes_sujas = True
        self._refresh_fontes.start(0)

    def pagina(self):
        w = QWidget()
        self.paginas.addWidget(w)
        area = QVBoxLayout(w)
        area.setContentsMargins(4, 4, 4, 4)
        return w, area

    def mostrar(self, pagina):
        self.paginas.setCurrentWidget(pagina)
        self.rolagem.verticalScrollBar().setValue(0)

    def recarregar(self):
        self._pendencias_cache = {}
        self.cancelar_tarefa()
        projeto = self.projetos.atual() or {}
        hist = revisoes(projeto)
        atual = hist[-1] if hist else {}
        self.projeto_uid, self.anterior = projeto.get('uuid'), atual.get('uuid')
        self.fontes = deepcopy(atual.get('fontes', []))
        estrategia = atual.get('estrategia', 'INFERIR')
        self._referencia = deepcopy(self.fontes), estrategia
        self.estrategia.blockSignals(True)
        self.estrategia.setCurrentIndex(self.estrategia.findData(estrategia))
        self.estrategia.blockSignals(False)
        self.resultados, self.pares, self.alertas_lote = {}, {}, {}
        self.feedback.clear()
        self.abrir_inicio()

    def pendente(self):
        return bool(self.projeto_uid) and (
            (self.fontes, self.estrategia.currentData()) != self._referencia or
            bool(self.editor and self.editor.pendente()) or
            bool(self.tarefa is not None and getattr(self.tarefa, '_wna_pendente', lambda: False)()))

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

    def abrir_inicio(self):
        if self.tarefa is None:
            self.categoria = None
            self.mostrar(self.inicio)
            self.atualizar()

    def abrir_categoria(self, categoria):
        if self.projeto_uid and not self.central.ocupado() and self.tarefa is None:
            self.categoria, self.selecionada = categoria, None
            self.feedback.clear()
            self.mostrar(self.detalhe)
            if self._fontes_sujas:
                self.atualizar()
            else:
                self.atualizar_categoria()

    def mostrar_tarefa(self, widget, texto, acao, pode_confirmar=True):
        self.tarefa = widget
        self.acao_tarefa = acao
        self.confirmar_b.setText(texto)
        self.confirmar_b.setEnabled(pode_confirmar)
        self.cancelar_b.setText('Cancelar edição' if self.editor else 'Voltar')
        self.rodape_tarefa.show()
        self.salvar_b.setVisible(bool(self.editor))
        self.feedback.clear()
        self.paginas.addWidget(widget)
        self.mostrar(widget)
        self.atualizar()

    def confirmar_tarefa(self):
        if self.acao_tarefa is not None and not self.central.ocupado():
            self.acao_tarefa()

    def cancelar_tarefa(self):
        if self.tarefa is not None and not self.central.ocupado():
            self.paginas.removeWidget(self.tarefa)
            self.tarefa.deleteLater()
            self.editor = self.tarefa = None
            self.acao_tarefa = None
            self.rodape_tarefa.hide()
            self.salvar_b.show()
            self.mostrar(self.detalhe if self.categoria else self.inicio)
            self.atualizar()

    def fontes_categoria(self):
        return [f for f in self.fontes if f['categoria'] == self.categoria]

    def fonte_selecionada(self):
        return next((f for f in self.fontes_categoria() if f['uid'] == self.selecionada), None)

    def pendencias_fonte(self, fonte):
        uid = fonte['uid']
        resultado = self.resultados.get(uid, {})
        chave = (fonte['categoria'], tuple(fonte['campos'].items()), tuple(fonte['campos_mapeados'].items()),
                 fonte['filtro'], self._estado.get(uid),
                 tuple(str(resultado.get(k)) for k in ('erro','ausentes','repetidos','total')),
                 any(uid in par for par in self.pares), tuple(self.alertas_lote.get(uid, ())))
        anterior = self._pendencias_cache.get(uid)
        if anterior and anterior[0] == chave:
            return list(anterior[1])
        uid = fonte['uid']
        estado = self._estado.get(uid, 'Disponível')
        msgs = [estado] if estado != 'Disponível' else []
        mapa = fonte['campos_mapeados']
        if fonte['campos'] and not mapa.get('id'):
            msgs.append('Identificador por mapear')
        _, ambiguos = sugerir_campos(fonte['campos'], fonte['categoria'])
        if any(k not in mapa for k in ambiguos):
            msgs.append('Campos com várias opções')
        r = self.resultados.get(uid, {})
        if r.get('erro'):
            msgs.append(r['erro'])
        if r.get('ausentes') or r.get('repetidos'):
            msgs.append(f"IDs: {r['ausentes']} vazios, {r['repetidos']} repetidos")
        if r.get('total') == 0 and fonte['filtro'] and not r.get('erro'):
            msgs.append('Filtro sem resultados')
        if any(uid in par for par in self.pares):
            msgs.append('Filtro sobreposto a outra fonte')
        msgs += list(self.alertas_lote.get(uid, ()))
        self._pendencias_cache[uid] = (chave, tuple(msgs))
        return msgs

    def resumo(self):
        return len({f['categoria'] for f in self.fontes}), len(self.fontes), sum(
            bool(self.pendencias_fonte(f)) for f in self.fontes)

    def atualizar(self):
        self._refresh_fontes.stop()
        projeto = self.projetos.atual() or {}
        hist = revisoes(projeto)
        nome = projeto.get('nome')
        estado = 'Rascunho' if self.pendente() else f'Revisão {hist[-1]["versao"]}' if hist else 'Cadastro inicial'
        self.contexto.setText(f'{nome} · {estado}' if nome else 'Crie ou selecione um projeto para cadastrar as fontes.')
        self.salvar_b.setEnabled(bool(nome) and (self.editor is not None or self.tarefa is None
                                                 and (self.pendente() or not self.anterior)))
        if self.tarefa is not None:
            return
        camadas = list(self.camadas())
        resolvidas = {f['uid']: identificar(f, camadas) for f in self.fontes}
        self._resolvidas_ids = {c.id() for c in resolvidas.values() if c is not None}
        for camada in (c for c in resolvidas.values() if c is not None):
            if camada.id() not in self._observadas:
                self._observadas.add(camada.id())
                for nome in ('dataChanged', 'dataSourceChanged', 'updatedFields', 'crsChanged', 'subsetStringChanged'):
                    sinal = getattr(camada, nome, None)
                    if sinal is not None:
                        sinal.connect(self.fonte_mudou)
        self._estado = {f['uid']: estado_fonte(f, resolvidas[f['uid']]) for f in self.fontes}
        self._fontes_sujas = False
        contagem = Counter(f['categoria'] for f in self.fontes)
        pendencias = Counter(f['categoria'] for f in self.fontes if self.pendencias_fonte(f))
        for k, b in self.categorias.items():
            nome_cat = CATEGORIAS[k].nome if k != 'JUNCTION' else 'Junctions e conectividade'
            if k in ('PIPE', 'JUNCTION'):
                b.setText(nome_cat)
                texto = f'{contagem[k]} fonte(s)' if contagem[k] else 'Sem fontes'
                if pendencias[k]:
                    texto += f' · {pendencias[k]} a revisar'
                r = self.contagens[GRUPOS[CATEGORIAS[k].grupo]]
                if k == 'JUNCTION':
                    if self.estrategia.currentData() != 'CADASTRADAS':
                        texto += ' · inferência prevista'
                    r.setToolTip(self.estrategia.currentText())
                r.setText(texto)
            else:
                texto = f'{contagem[k]} fonte(s)' if contagem[k] else 'sem fontes'
                b.setText(f'{nome_cat} · {texto}' + (f' · {pendencias[k]} a revisar' if pendencias[k] else ''))
            b.setEnabled(bool(nome))
        for grupo, (b, chaves) in self.grupos.items():
            if len(chaves) > 1:
                n = sum(bool(contagem[c]) for c in chaves)
                p = sum(pendencias[c] for c in chaves)
                self.contagens[grupo].setText((f'{n} categoria(s)' if n else 'Sem fontes') +
                                             (f' · {p} a revisar' if p else ''))
        if self.categoria is not None:
            self.atualizar_categoria()

    def atualizar_categoria(self):
        fontes = self.fontes_categoria()
        titulo = CATEGORIAS[self.categoria].nome if self.categoria != 'JUNCTION' else 'Junctions e conectividade'
        self.titulo.setText(f'{titulo}\n{len(fontes)} fonte(s) cadastrada(s)')
        self.nos.setVisible(self.categoria == 'JUNCTION')
        self.lista.blockSignals(True)
        self.lista.clear()
        for f in fontes:
            uid = f['uid']
            msgs = self.pendencias_fonte(f)
            item = QListWidgetItem(f['nome'] + ('\n' + ' · '.join(msgs) if msgs else ''))
            item.setData(Qt.UserRole, uid)
            item.setToolTip(f['nome'] + '\n' + self._estado[uid])
            self.lista.addItem(item)
            if uid == self.selecionada:
                self.lista.setCurrentItem(item)
        if self.lista.currentItem() is None and fontes:
            self.lista.setCurrentRow(0)
        self.lista.blockSignals(False)
        self.atualizar_fonte(self.lista.currentItem())
        self.lista.setVisible(bool(fontes))
        self.conferir_b.setEnabled(bool(fontes))
        self.desenhar_alertas(fontes)

    def atualizar_fonte(self, item, _=None):
        self.selecionada = item.data(Qt.UserRole) if item else None
        fonte = self.fonte_selecionada()
        for b in (self.editar_b, self.mover_b, self.remover_b, self.copiar_b):
            b.setVisible(bool(fonte))
        self.mais_acoes.setVisible(bool(fonte))
        if not fonte:
            self.mais_acoes.setChecked(False)
        if not fonte:
            self.info_fonte.setText('Adicione as camadas usadas nesta categoria.')
            return
        mapa = fonte['campos_mapeados']
        itens = [f"{GEOMETRIAS[fonte['geometria']]} · {fonte['crs'] or 'CRS personalizado'}",
                 f"Identificador: {mapa.get('id', 'por mapear')} · Label: {mapa.get('label', '—')}",
                 'Filtro: ' + (fonte['filtro'] or 'todas as feições')]
        r = self.resultados.get(fonte['uid'], {})
        if r.get('total') is not None and not r.get('erro'):
            itens.append(f"{r['total']} feição(ões) na conferência")
        self.info_fonte.setText('\n'.join(itens))
        self.editar_b.setEnabled(identificar(fonte, self.camadas()) is not None)
        self.copiar_b.setEnabled(bool(mapa) and len(self.fontes_categoria()) > 1)

    def escolhas(self, titulo, opcoes, acao, executar, incompativeis=()):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(aviso(titulo))
        lista = lista_compacta()
        layout.addWidget(lista)
        for chave, rotulo, motivo in opcoes:
            item = QListWidgetItem(rotulo + ('\n' + motivo if motivo else ''))
            item.setData(Qt.UserRole, chave)
            item.setFlags(Qt.ItemIsEnabled)
            if not motivo:
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
            lista.addItem(item)
        if not opcoes:
            layout.addWidget(aviso('Carregue camadas compatíveis no projeto QGIS.'))
        if incompativeis:
            _, sub = expansivel(layout, 'Consultar camadas incompatíveis')
            sub.addWidget(aviso('\n'.join(incompativeis)))

        def selecionadas():
            return [lista.item(i).data(Qt.UserRole) for i in range(lista.count())
                    if lista.item(i).checkState() == Qt.Checked]

        w._wna_pendente = lambda: bool(selecionadas())
        lista.itemChanged.connect(lambda _: self.confirmar_b.setEnabled(bool(selecionadas())))
        layout.addStretch()
        self.mostrar_tarefa(w, acao, lambda: executar(selecionadas()), False)
        return lista

    def adicionar(self):
        if self.categoria is None or self.central.ocupado():
            return
        cat = CATEGORIAS[self.categoria]
        cadastradas = {f['origem'] for f in self.fontes_categoria()}
        opcoes, incompativeis = [], []
        camadas = sorted(self.camadas(), key=lambda c: (c.name().casefold(), c.id()))
        nomes = Counter(c.name() for c in camadas)
        for c in camadas:
            tipo = geometria(c)
            if not c.isValid() or tipo not in cat.geometrias:
                incompativeis.append(c.name() + ' · ' + GEOMETRIAS.get(tipo, 'tipo não suportado'))
                continue
            nome = c.name() + (' · ' + c.id()[-8:] if nomes[c.name()] > 1 else '')
            r = f"{nome} · {c.crs().authid() or GEOMETRIAS[tipo]}"
            motivo = 'Já cadastrada nesta categoria' if origem_camada(c) in cadastradas else ''
            opcoes.append((c.id(), r, motivo))
        return self.escolhas('Adicionar camadas · ' + cat.nome, opcoes,
                             'Adicionar selecionadas', self.adicionar_selecionadas, incompativeis)

    def adicionar_selecionadas(self, ids):
        ids = set(ids)
        novas, avisos, detalhes = incluir_fontes(
            self.fontes, self.categoria, [c for c in self.camadas() if c.id() in ids])
        self.fontes.extend(novas)
        if novas:
            self.selecionada = novas[0]['uid']
            self.limpar_conferencia()
        m = f'{len(novas)} fonte(s) adicionada(s).'
        if any(detalhes.values()):
            m += ' Revise os campos com mais de uma opção.'
        self.cancelar_tarefa()
        self.atualizar()
        self.feedback.setText('\n'.join([m, *avisos]))

    def editar(self):
        fonte = self.fonte_selecionada()
        if not fonte or self.central.ocupado():
            return
        camada = identificar(fonte, self.camadas())
        if camada is not None:
            try:
                self.editor = EditorFonte(self, fonte, camada)
                self.mostrar_tarefa(self.editor, 'Aplicar à fonte', self.aplicar_editor)
            except ValueError as e:
                self.feedback.setText(str(e))

    def aplicar_editor(self):
        if self.editor is None:
            return True
        if self.central.ocupado():
            return False
        try:
            nova = self.editor.configurar()
        except ValueError as e:
            self.editor.mensagem.setText(str(e))
            self.feedback.setText(str(e))
            return False
        self.substituir(nova)
        self.cancelar_tarefa()
        self.feedback.setText('Fonte atualizada no rascunho.')
        return True

    def limpar_conferencia(self):
        self.resultados.clear()
        self.pares.clear()

    def substituir(self, fonte):
        uid = fonte['uid']
        pos = next(i for i, f in enumerate(self.fontes) if f['uid'] == uid)
        self.fontes[pos] = fonte
        self.alertas_lote.pop(uid, None)
        self.limpar_conferencia()

    def escolher_lote(self):
        origem = self.fonte_selecionada()
        if not origem or self.central.ocupado():
            return
        opcoes = [(f['uid'], f['nome'], '' if identificar(f, self.camadas()) else 'Fonte indisponível')
                  for f in self.fontes_categoria() if f['uid'] != origem['uid']]
        return self.escolhas('Aplicar mapeamento de ' + origem['nome'], opcoes,
                             'Aplicar às selecionadas', lambda ids: self.aplicar_lote(origem, ids))

    def aplicar_lote(self, origem, ids):
        avisos = []
        atualizadas = 0
        camadas = list(self.camadas())
        for f in self.fontes_categoria():
            if f['uid'] not in ids or f['uid'] == origem['uid']:
                continue
            try:
                camada = identificar(f, camadas)
                if camada is None:
                    raise ValueError('Fonte indisponível.')
                nova, pendencias = copiar_mapeamento(origem, f, descrever(camada))
                self.substituir(nova)
                atualizadas += 1
                if pendencias:
                    msgs = [f'{ROTULOS.get(p, p)}: {n} ({m})' for p, n, m in pendencias]
                    self.alertas_lote[f['uid']] = msgs
                    avisos.append(f['nome'] + ' — ' + ', '.join(msgs))
            except ValueError as e:
                avisos.append(f['nome'] + ' — ' + str(e))
        self.cancelar_tarefa()
        self.atualizar()
        self.feedback.setText('\n'.join([f'Mapeamento aplicado a {atualizadas} fonte(s).', *avisos]))

    def mover(self):
        fonte = self.fonte_selecionada()
        if not fonte or self.central.ocupado():
            return
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(aviso('Relocalizar ' + fonte['nome']))
        alternativas = {c.id(): c.name() + ' · ' + c.id()[-8:] for c in self.camadas()
                        if c.isValid() and geometria(c) == fonte['geometria']}
        escolha = combo({'': 'Escolha uma camada carregada…', **alternativas})
        layout.addWidget(escolha)

        def aplicar():
            try:
                c = next((c for c in self.camadas() if c.id() == escolha.currentData()), None)
                if c is None:
                    raise ValueError('Escolha a camada que corresponde à origem.')
                meta = descrever(c)
                if any(f['uid'] != fonte['uid'] and f['origem'] == meta['origem'] and
                       f['filtro'] == fonte['filtro'] for f in self.fontes_categoria()):
                    raise ValueError('A camada já está associada com o mesmo filtro nesta categoria.')
                prova = relocalizar(fonte, meta)
                nova = {**fonte, **meta, 'relocalizacao': prova}
                if prova == 'COMPATIVEL_IDENTIDADE_PENDENTE':
                    nova['origem_estavel'] = meta['origem']
                self.substituir(nova)
            except ValueError as e:
                self.feedback.setText(str(e))
                return
            self.cancelar_tarefa()
            self.feedback.setText('Origem atualizada no rascunho.')

        layout.addStretch()
        self.mostrar_tarefa(w, 'Relocalizar', aplicar)

    def remover(self):
        fonte = self.fonte_selecionada()
        if fonte and not self.central.ocupado():
            self.fontes.remove(fonte)
            self.limpar_conferencia()
            self.alertas_lote.pop(fonte['uid'], None)
            self.feedback.setText('Associação retirada do rascunho. A revisão salva pode ser recuperada.')
            self.atualizar()

    def conferir(self):
        if self.central.ocupado() or self.tarefa is not None or not self.fontes:
            return
        try:
            dados = preparar_conferencia(self.fontes, list(self.camadas()))
            self.feedback.setText('Acompanhe a leitura das fontes em Atividade.')
            self.central.app.atividades.executar_thread(
                'Conferir fontes do Modelo GIS', self.contexto.text(),
                lambda parar, sinal: conferir(dados, parar, lambda etapa: sinal(0, etapa)),
                self.receber_conferencia, self.feedback.setText)
        except (ValueError, RuntimeError) as e:
            self.feedback.setText(str(e))

    def receber_conferencia(self, dados):
        self.resultados, self.pares = dados
        self.atualizar()
        categorias, fontes, pendentes = self.resumo()
        self.feedback.setText(f'Conferência concluída · {fontes} fonte(s) em {categorias} categoria(s) · {pendentes} a revisar.')
        self.central.atualizar()

    def desenhar_alertas(self, fontes):
        while self.alertas.count():
            self.alertas.takeAt(0).widget().deleteLater()
        pendentes = [f for f in fontes if self.pendencias_fonte(f)]
        if not self.resultados and not pendentes:
            return
        indisponiveis = sum(self._estado[f['uid']].startswith('Localizar') for f in fontes)
        resumo = f'{len(pendentes)} a revisar · {indisponiveis} indisponível(is)'
        if self.resultados:
            revisadas = [f for f in fontes if self.resultados.get(f['uid'], {}).get('total') is not None]
            resumo = f'{sum(not self.pendencias_fonte(f) for f in revisadas)} conferida(s) sem pendências · ' + resumo
        self.alertas.addWidget(aviso(resumo))
        por_uid = {f['uid']: f for f in self.fontes}
        for f in pendentes:
            _, detalhe = expansivel(self.alertas, fill('Detalhes de ' + f['nome'], 32))
            uid = f['uid']
            r = self.resultados.get(uid, {})
            msgs = self.pendencias_fonte(f)
            if r.get('exemplos'):
                msgs.append('Exemplos de IDs repetidos: ' + ', '.join(r['exemplos']))
            if r.get('total') is not None and not r.get('erro'):
                msgs.append(f"Feições: {r['total']} · Campo ID: {f['campos_mapeados'].get('id', 'por mapear')}")
            for par, n in self.pares.items():
                if uid in par:
                    outra = por_uid[par[0] if par[1] == uid else par[1]]
                    msgs.append(f"{n} feição(ões) também em {CATEGORIAS[outra['categoria']].nome} · {outra['nome']}")
            msgs.append('Carregue ou relocalize a camada no QGIS.' if self._estado[uid].startswith('Localizar')
                        else 'Revise o mapeamento e o filtro da fonte.')
            detalhe.addWidget(aviso('\n'.join(msgs)))

    def salvar(self):
        if not self.projeto_uid or self.central.ocupado():
            return False
        if self.tarefa is not None and self.editor is None:
            anterior = self.tarefa
            self.confirmar_tarefa()
            if self.tarefa is anterior:
                return False
        if not self.aplicar_editor():
            return False
        try:
            nova = salvar_modelo(self.projetos, self.projeto_uid, self.anterior,
                                 self.fontes, self.estrategia.currentData())
        except (ValueError, OSError) as e:
            self.feedback.setText('Cadastro mantido no rascunho. ' + str(e))
            return False
        self.anterior = nova['uuid']
        self._referencia = deepcopy(self.fontes), self.estrategia.currentData()
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
