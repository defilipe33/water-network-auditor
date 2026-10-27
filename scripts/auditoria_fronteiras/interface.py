"""Interface mínima para ensaio operacional, executada na thread do QGIS.

O núcleo é chamado sem alterações. Um progresso modal impede edição das
entradas durante o processamento; callbacks processam eventos e cancelamento.
"""
from time import perf_counter

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QApplication, QAbstractItemView, QComboBox, QDialog, QDoubleSpinBox,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QCheckBox, QFileDialog,
    QPlainTextEdit, QProgressDialog, QPushButton, QTableWidget,QScrollArea,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)
from qgis.core import QgsCoordinateReferenceSystem, QgsProject, QgsVectorLayer, QgsWkbTypes
from qgis.gui import QgsProjectionSelectionWidget

from .entradas import crs_processamento
from .modelos import CamadaEntrada, Cancelado, Modo, Parametros
from .nucleo import auditar
from .investigacao import OpcoesLocais,analisar_investigacao,instante_execucao
from .visualizacao import (MARCA_RESULTADO, carregar_no_projeto,
                           criar_camadas_temporarias, texto_resumo)
from .fluxos import FluxosAuditoria
from .estados import Estado,EDITAVEIS,OCUPADOS
from .atividade import Progresso as QProgressDialog,acompanhada,falha


class AuditoriaFronteirasDialog(FluxosAuditoria,QDialog):
    def __init__(self, parent=None, projeto=None):
        super().__init__(parent)
        self.projeto = projeto if projeto is not None else QgsProject.instance()
        self.resultado = None
        self.analise = None
        self.dossie = None
        self.base_revisao = None
        self.painel = None
        self.camadas_geradas = []
        self._executando = False
        self.setWindowTitle('AUDITORIA_FRONTEIRAS — teste operacional')
        self.resize(1000, 790)
        externo=QVBoxLayout(self)
        rolagem=QScrollArea()
        rolagem.setWidgetResizable(True)
        conteudo=QWidget()
        rolagem.setWidget(conteudo)
        externo.addWidget(rolagem)
        raiz = QVBoxLayout(conteudo)
        self.montar_fluxos(raiz)
        tela=QApplication.primaryScreen()
        if tela:
            self.resize(min(1000,tela.availableGeometry().width()-40),min(790,tela.availableGeometry().height()-60))
        aviso = QLabel('Marque as entradas e escolha seus campos. Toda a camada será analisada, '
                       'independentemente da seleção de feições. Exportação e revisão são opcionais.')
        aviso.setWordWrap(True)
        raiz.addWidget(aviso)
        self.abas = QTabWidget()
        self.redes = self._tabela(['Usar', 'Camada de rede', 'Campo identificador',
                                 'Setor cadastral (opcional)','Diâmetro (opcional)','Material (opcional)',
                                 'Exibição (opcional)'])
        self.limites = self._tabela(['Usar', 'Camada de limite', 'Campo identificador',
                                   'Campo de exibição', 'Modo de análise'])
        self.abas.addTab(self.redes, 'Redes lineares')
        self.abas.addTab(self.limites, 'Limites poligonais')
        self.campos_opcionais=QCheckBox('Mostrar campos cadastrais opcionais da rede')
        self.campos_opcionais.setToolTip('Setor cadastral, diâmetro, material e exibição são opcionais. Ocultar colunas preserva os campos configurados.')
        for coluna in range(3,7):self.redes.setColumnHidden(coluna,True)
        self.campos_opcionais.toggled.connect(lambda mostrar:[self.redes.setColumnHidden(c,not mostrar) for c in range(3,7)])
        raiz.addWidget(self.campos_opcionais)
        self.configuracao_ativa=QPlainTextEdit()
        self.configuracao_ativa.setReadOnly(True)
        self.configuracao_ativa.setMaximumHeight(160)
        raiz.addWidget(self.configuracao_ativa)
        raiz.addWidget(self.abas, 3)
        self.atualizar = QPushButton('Atualizar lista de camadas disponíveis')
        self.atualizar.setToolTip('Atualiza as camadas disponíveis para seleção. Não executa nem atualiza os resultados da auditoria.')
        self.atualizar.clicked.connect(self.atualizar_camadas)
        raiz.addWidget(self.atualizar)
        self.parametros_widget = QWidget()
        form = QFormLayout(self.parametros_widget)
        self.tolerancia = self._distancia(0.01)
        self.continuidade = self._distancia(1.)
        form.addRow('Tolerância geométrica (m):', self.tolerancia)
        form.addRow('Distância máxima de continuidade potencial (m):', self.continuidade)
        self.agrupar=QCheckBox('Habilitar Locais de Investigação')
        self.distancia_locais=self._distancia(5.)
        self.extensao_locais=self._distancia(5.)
        form.addRow(self.agrupar)
        form.addRow('Distância máxima para procurar eventos candidatos (m):',self.distancia_locais)
        form.addRow('Distância máxima entre eventos do mesmo local (m):',self.extensao_locais)
        self.distancia_locais.setToolTip('Raio de busca a partir do evento semente. Busca 5 m pode localizar eventos em lados opostos da semente, separados por até 10 m. Proximidade não basta: a compatibilidade técnica continua obrigatória.')
        self.extensao_locais.setToolTip('Limita a maior distância entre quaisquer dois membros. Busca 10 m / extensão 5 m encontra mais candidatos, mas nenhum grupo ultrapassa 5 m. Busca 5 m / extensão 10 m é válida. Zero exige coincidência exata. Ambos os parâmetros aceitam valores finitos não negativos, independentemente.')
        for w in (self.distancia_locais,self.extensao_locais):
            w.setEnabled(False)
        self.crs = QgsProjectionSelectionWidget()
        self.crs.setCrs(QgsCoordinateReferenceSystem('EPSG:31983'))
        form.addRow('CRS projetado em metros:', self.crs)
        raiz.addWidget(self.parametros_widget)
        self.status = QLabel('Pronto para configurar as entradas.')
        self.status.setWordWrap(True)
        raiz.addWidget(self.status)
        self.resumo = QPlainTextEdit()
        self.resumo.setReadOnly(True)
        self.resumo.setPlaceholderText('Resumo por classificação, camada de limite, tempo e avisos.')
        raiz.addWidget(self.resumo, 2)
        relatorio = QHBoxLayout()
        self.exportar = QPushButton('Gerar relatório Excel…')
        self.exportar.setEnabled(False)
        self.exportar.clicked.connect(lambda checked=False: self.gerar_relatorio())
        self.detalhes_excel = QCheckBox('Incluir aba técnica no Excel')
        self.detalhes_excel.setToolTip('O arquivo técnico JSON completo acompanha o XLSX em qualquer opção.')
        relatorio.addWidget(self.exportar)
        relatorio.addWidget(self.detalhes_excel)
        raiz.addLayout(relatorio)
        acoes=QHBoxLayout()
        self.inspecionar=QPushButton('Inspecionar locais…')
        self.inspecionar.clicked.connect(self.abrir_painel)
        acoes.addWidget(self.inspecionar)
        self.exportar_geo=QPushButton('Exportar GPKG / SHP / XLSX…')
        self.exportar_geo.clicked.connect(lambda checked=False: self.exportar_formatos())
        acoes.addWidget(self.exportar_geo)
        self.reabrir=QPushButton('Reabrir execução GPKG…')
        self.reabrir.clicked.connect(self.reabrir_execucao)
        acoes.addWidget(self.reabrir)
        raiz.addLayout(acoes)
        botoes = QHBoxLayout()
        self.executar = QPushButton('Executar auditoria e carregar temporárias')
        self.executar.clicked.connect(self.executar_auditoria)
        self.fechar = QPushButton('Fechar')
        self.fechar.clicked.connect(self.close)
        botoes.addWidget(self.executar)
        botoes.addWidget(self.fechar)
        externo.addLayout(botoes)
        self.atualizar_camadas()
        self.monitorar_configuracao()
        self.mudar_modalidade()
        from auditoria_fronteiras.ui_comum import adaptar_janela
        adaptar_janela(self)

    @staticmethod
    def _tabela(cabecalhos):
        tabela = QTableWidget(0, len(cabecalhos))
        tabela.setHorizontalHeaderLabels(cabecalhos)
        tabela.setAlternatingRowColors(True)
        tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        tabela.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        tabela.verticalHeader().setVisible(False)
        return tabela

    @staticmethod
    def _distancia(valor):
        campo = QDoubleSpinBox()
        campo.setDecimals(6)
        campo.setRange(0., 1000000.)
        campo.setValue(valor)
        campo.setToolTip('Valor em metros. Ajustável; não é requisito normativo.')
        return campo

    @staticmethod
    def _campos(camada):
        combo = QComboBox()
        combo.addItem('(Sem campo)', None)
        for campo in camada.fields():
            combo.addItem(campo.name(), campo.name())
        return combo

    def atualizar_camadas(self,interno=False):
        if self._executando or (self.estado not in EDITAVEIS and not interno):
            return
        with self.restaurando():
            self._atualizar_camadas()
        if not interno:
            self.configuracao_alterada()
        if hasattr(self,'status'):
            self.status.setText('Lista de fontes atualizada. Nenhum processamento foi executado; resultados ativos preservados.')

    def _atualizar_camadas(self):
        for tabela, tipo in ((self.redes, QgsWkbTypes.LineGeometry),
                             (self.limites, QgsWkbTypes.PolygonGeometry)):
            anterior = {}
            for linha in range(tabela.rowCount()):
                item = tabela.item(linha, 0)
                anterior[item.data(Qt.UserRole)] = (
                    item.checkState(),
                    [tabela.cellWidget(linha, coluna).currentData()
                     for coluna in range(2, tabela.columnCount())])
            tabela.setRowCount(0)
            camadas = [c for c in self.projeto.mapLayers().values()
                       if isinstance(c, QgsVectorLayer) and c.isValid()
                       and QgsWkbTypes.geometryType(c.wkbType()) == tipo
                       and not c.customProperty(MARCA_RESULTADO, False)]
            for camada in sorted(camadas, key=lambda c: (c.name().casefold(), c.id())):
                linha = tabela.rowCount()
                tabela.insertRow(linha)
                usar = QTableWidgetItem()
                usar.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
                usar.setData(Qt.UserRole, camada.id())
                estado, escolhas = anterior.get(camada.id(), (Qt.Unchecked, []))
                usar.setCheckState(estado)
                tabela.setItem(linha, 0, usar)
                nome = QTableWidgetItem(f'{camada.name()} [{camada.id()[-6:]}]')
                nome.setToolTip(f'ID da camada: {camada.id()}\nCRS: {camada.crs().authid()}')
                tabela.setItem(linha, 1, nome)
                tabela.setCellWidget(linha, 2, self._campos(camada))
                if tipo == QgsWkbTypes.PolygonGeometry:
                    tabela.setCellWidget(linha, 3, self._campos(camada))
                    modo = QComboBox()
                    modo.addItem('Travessia individual de perímetro', Modo.PERIMETRO.value)
                    modo.addItem('Transição entre regiões', Modo.TRANSICAO.value)
                    tabela.setCellWidget(linha, 4, modo)
                else:
                    for coluna in (3,4,5,6):
                        tabela.setCellWidget(linha,coluna,self._campos(camada))
                for coluna, valor in enumerate(escolhas, 2):
                    combo = tabela.cellWidget(linha, coluna)
                    indice = combo.findData(valor)
                    if indice >= 0:
                        combo.setCurrentIndex(indice)
                for coluna in range(2,tabela.columnCount()):
                    tabela.cellWidget(linha,coluna).currentIndexChanged.connect(self.configuracao_alterada)

    def configuracoes(self):
        """Resolve por ID de camada, nunca pelo nome exibido."""
        grupos = []
        for tabela in (self.redes, self.limites):
            configs = []
            for linha in range(tabela.rowCount()):
                item = tabela.item(linha, 0)
                if item.checkState() != Qt.Checked:
                    continue
                camada = self.projeto.mapLayer(item.data(Qt.UserRole))
                if not camada or not camada.isValid():
                    raise ValueError('Uma camada marcada foi removida ou ficou inválida; atualize a lista.')
                campo_id = tabela.cellWidget(linha, 2).currentData()
                if tabela is self.redes:
                    for coluna in (3,4,5):
                        extra=tabela.cellWidget(linha,coluna).currentData()
                        if extra and camada.fields().indexFromName(extra)<0:
                            raise ValueError('Campo de inspeção ausente: '+extra)
                campo_nome = tabela.cellWidget(linha, 3 if tabela is self.limites else 6).currentData()
                modo = Modo(tabela.cellWidget(linha, 4).currentData()) if tabela is self.limites else Modo.PERIMETRO
                configs.append(CamadaEntrada(camada, campo_id, campo_nome, modo,
                    self._origens_configuradas.get(camada.id())))
            grupos.append(configs)
        if not all(grupos):
            raise ValueError('Marque ao menos uma rede e uma camada de limites.')
        crs = self.crs.crs()
        from dataclasses import asdict
        valores=asdict(Parametros())
        if self.modalidade.currentIndex()==3:
            valores.update(getattr(self,'_parametros_recuperados',{}))
        valores.update(crs=crs.authid() or crs.toWkt(),tolerancia_geometrica=self.tolerancia.value(),
            distancia_continuidade=self.continuidade.value(),distancia_agrupamento=self.distancia_locais.value())
        parametros = Parametros(**valores)
        crs_processamento(parametros)
        return grupos[0], grupos[1], parametros

    def executar_auditoria(self):
        if self._executando:
            return
        if self.estado in (Estado.INSPECIONANDO,Estado.CONCLUIDO) or (self.estado==Estado.ERRO and self.dossie):
            self.voltar_inspecao()
            self.abrir_painel()
            return
        if self.estado not in EDITAVEIS:
            return
        if self.modalidade.currentIndex()==1:
            self.escolher_auditoria()
            return
        if self.modalidade.currentIndex()==2:
            self.executar_regeneracao()
            return
        if self.painel and not self.painel.close():
            return
        try:
            redes, limites, parametros = self.configuracoes()
            preparacao=None
            if self.modalidade.currentIndex()==3:
                preparacao=self.preparar_reprocessamento(redes,limites,parametros,self.opcoes_agrupamento())
                if preparacao is None:
                    return
            self._modo_fixo=self.modalidade.currentIndex()
            self._estado_antes_processar=self.estado_configuracao()
            self._formulario_em_execucao=self.formulario()
            self.definir_estado(Estado.CONFIRMANDO)
            if not self.confirmar_processamento(redes,limites,parametros):
                self.definir_estado(self._estado_antes_processar)
                return
        except Exception as erro:
            self.definir_estado(Estado.ERRO)
            self.status.setText(str(erro))
            QMessageBox.warning(self, 'Configuração das entradas', str(erro))
            return
        self._executando = True
        self.definir_estado(Estado.PROCESSANDO)
        self.exportar.setEnabled(False)
        anterior=(self.camadas_geradas,self.resultado,self.analise,self.dossie,self.base_revisao)
        data_execucao=instante_execucao()
        opcoes=OpcoesLocais(self.agrupar.isChecked(),self.distancia_locais.value(),self.extensao_locais.value())
        for widget in (self.abas, self.atualizar, self.executar, self.fechar, self.parametros_widget):
            widget.setEnabled(False)
        inicio = perf_counter()
        self.resumo.clear()
        progresso = QProgressDialog('Validando e lendo entradas…', 'Cancelar', 0, 0, self)
        progresso.setWindowTitle('Auditoria de fronteiras')
        progresso.setWindowModality(Qt.ApplicationModal)
        progresso.setMinimumDuration(0)
        progresso.setAutoClose(False)
        progresso.setAutoReset(False)
        progresso.show()
        def cancelar():
            return progresso.wasCanceled()
        def avancar(n, total):
            if n < total:
                progresso.setRange(0, total)
                progresso.setValue(n)
                progresso.setLabelText(f'Analisando tubulações: {n}/{total}')
            else:
                progresso.setRange(0, 0)
                progresso.setLabelText('Investigando continuidades potenciais…')
        try:
            cancelar()
            self.resultado = auditar(redes, limites, parametros, cancelar, avancar)
            self.resumo.setPlainText(texto_resumo(self.resultado))
            if self.resultado.cancelado or cancelar():
                raise Cancelado('Execução cancelada; nenhuma camada desta execução foi carregada.')
            progresso.setRange(0, 0)
            progresso.setLabelText('Organizando locais, pares e metadados…')
            self.analise=analisar_investigacao(self.resultado,opcoes,cancelar,data_execucao)
            from .inspecao import construir_dossie,contagens
            campos={}
            for linha in range(self.redes.rowCount()):
                item=self.redes.item(linha,0)
                if item.checkState()!=Qt.Checked:
                    continue
                c=self.projeto.mapLayer(item.data(Qt.UserRole))
                fonte=next(f for f in self.resultado.fontes if not f['modo'] and f['fonte']==c.source()
                           and f['provedor']==c.providerType())
                campos[fonte['origem']]={nome:self.redes.cellWidget(linha,coluna).currentData()
                    for nome,coluna in [('setor',3),('diametro',4),('material',5)]}
            self.dossie=construir_dossie(self.resultado,self.analise,campos)
            from .ciclo import inicializar,configuracao_proposta,comparar_locais
            inicializar(self.dossie,self.nome_auditoria.text(),self.projeto_auditoria.text(),
                self.auditoria_origem if preparacao else None)
            self.dossie['configuracao']=preparacao['configuracao'] if preparacao else configuracao_proposta(
                redes,limites,parametros,opcoes,campos,cancelar=cancelar)
            counts=contagens(self.dossie)
            self.resumo.appendPlainText(f"\nEventos ambíguos: {counts['eventos_ambiguos']}"
                f"\nLocais com ambiguidade: {counts['locais_ambiguos']}")
            self.resumo.appendPlainText(f'\nLocais de investigação: {len(self.analise.locais)}'
                + (' (agrupamento habilitado)' if opcoes.habilitado else ' (agrupamento desabilitado)'))
            progresso.setLabelText('Preparando camadas temporárias…')
            camadas = criar_camadas_temporarias(self.resultado, cancelar, self.analise)
            if cancelar():
                raise Cancelado('Preparação cancelada; nenhuma camada desta execução foi carregada.')
            if preparacao:
                novo=self.dossie
                self.camadas_geradas,self.resultado,self.analise,self.dossie,self.base_revisao=anterior
                progresso.close()
                preparada=dict(origem=self.auditoria_origem,novo=novo,
                    comparacao=comparar_locais(self.auditoria_origem,novo),token_origem=preparacao['token_origem'])
                if not self.salvar_operacao(preparada):
                    return
            else:
                self.publicar_auditoria(self.dossie,None,camadas)
            self.exportar.setEnabled(True)
            tempo = perf_counter() - inicio
            self.resumo.appendPlainText(f'\nTempo total, incluindo visualização: {tempo:.3f} s')
            self.resumo.appendPlainText('Camadas temporárias carregadas em um novo grupo. '
                                        'COINCIDENCIA tem ponto representativo e trecho linear relacionado.')
            self.status.setText(f'{len(self.resultado.ocorrencias)} ocorrências; '
                                f'{len(self.resultado.problemas)} avisos. Feche ou minimize a janela para revisar o mapa.')
            if not self.resultado.ocorrencias:
                self.status.setText('Processamento concluído e validado: nenhuma ocorrência encontrada (0 eventos).')
            progresso.concluir()
        except Cancelado as erro:
            progresso.falhar(erro)
            self.camadas_geradas,self.resultado,self.analise,self.dossie,self.base_revisao=anterior
            self.status.setText(str(erro))
            self.resumo.appendPlainText('\nCANCELADO: nenhuma camada desta execução foi carregada. '
                                        'Grupos anteriores foram preservados.')
            self.definir_estado(self._estado_antes_processar)
        except Exception as erro:
            progresso.falhar(erro)
            self.camadas_geradas,self.resultado,self.analise,self.dossie,self.base_revisao=anterior
            self.status.setText('Falha: ' + str(erro))
            self.resumo.appendPlainText('\nFalha: ' + str(erro))
            QMessageBox.critical(self, 'Auditoria de fronteiras', str(erro))
            self.definir_estado(Estado.ERRO)
        finally:
            progresso.close()
            progresso.deleteLater()
            self._executando = False
            for widget in (self.abas, self.atualizar, self.executar, self.fechar, self.parametros_widget):
                widget.setEnabled(True)
            self.exportar.setEnabled(bool(self.dossie))
            if self.estado==Estado.PROCESSANDO:
                self.definir_estado(self._estado_antes_processar)
            self.aplicar_estado()

    @acompanhada('Gerando relatório Excel da auditoria GIS')
    def gerar_relatorio(self):
        if self.estado in OCUPADOS or self._executando or not self.camadas_geradas or not self.resultado or self.resultado.cancelado:
            return
        if not self.preparar_exportacao():
            return
        from datetime import datetime
        nome = 'AUDITORIA_FRONTEIRAS_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.xlsx'
        caminho, _ = QFileDialog.getSaveFileName(self,'Salvar relatório Excel',nome,'Excel (*.xlsx)')
        if not caminho:
            return False
        if not caminho.lower().endswith('.xlsx'):
            caminho += '.xlsx'
        try:
            from .relatorio import exportar_xlsx
            arquivos = exportar_xlsx(self.resultado,caminho,self.detalhes_excel.isChecked(),self.analise,self.dossie)
            self.registrar_exportacao(['XLSX'],caminho)
            self.resumo.appendPlainText('\nExcel: ' + arquivos['xlsx'] + '\nRastreabilidade: ' + arquivos['tecnico'])
            self.status.setText('Relatório salvo. As camadas temporárias permanecem disponíveis.')
        except Exception as erro:
            falha(self,erro)
            self.resumo.appendPlainText('\nRelatório não salvo: ' + str(erro))
            QMessageBox.warning(self,'Relatório Excel',str(erro) + '\nAs camadas temporárias permanecem disponíveis.')

    def abrir_painel(self):
        if self.estado in OCUPADOS or self._executando:
            return
        if not self.dossie or not self.dossie['locais']:
            QMessageBox.information(self,'Inspeção','Execute com agrupamento habilitado ou reabra uma execução com locais.')
            return
        if self.painel and self.painel.dossie is self.dossie:
            self.painel.show()
            self.painel.raise_()
            return
        from .painel import PainelInspecao
        from qgis.utils import iface
        self.painel=PainelInspecao(self.dossie,self.camadas_geradas,self.projeto,self,
                                 iface.mapCanvas() if iface else None,self.base_revisao)
        self.painel.revisao_salva.connect(self.vincular_base)
        self.painel.show()

    @acompanhada('Exportando resultados da auditoria GIS')
    def exportar_formatos(self):
        if self.estado in OCUPADOS or self._executando:
            return
        if not self.dossie:
            QMessageBox.information(self,'Exportação','Execute uma auditoria ou reabra uma execução primeiro.')
            return
        if not self.preparar_exportacao():
            return
        dialogo=QDialog(self)
        dialogo.setWindowTitle('Formatos de exportação independentes')
        layout=QVBoxLayout(dialogo)
        opcoes={n:QCheckBox(n) for n in ('GPKG','SHP','XLSX')}
        from .ciclo import perfil
        preferencias=perfil(self.dossie).get('exportacao',{})
        for nome,w in opcoes.items():
            w.setChecked(nome in preferencias.get('formatos',[]))
        for w in opcoes.values():
            layout.addWidget(w)
        aviso=QLabel('Escolha um ou mais formatos. Será criada uma pasta nova de entrega.\n'
                     'GPKG: base completa; SHP: pontos de auditoria e CSVs relacionais.')
        aviso.setWordWrap(True)
        layout.addWidget(aviso)
        b=QPushButton('Escolher pasta e exportar')
        b.clicked.connect(dialogo.accept)
        layout.addWidget(b)
        if dialogo.exec()!=QDialog.Accepted or not any(w.isChecked() for w in opcoes.values()):
            return False
        destino=QFileDialog.getExistingDirectory(self,'Pasta de destino',preferencias.get('pasta',''))
        if not destino:
            return False
        from pathlib import Path
        from datetime import datetime
        pasta=Path(destino)/('AUDITORIA_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        try:
            pasta.mkdir()
            if opcoes['GPKG'].isChecked():
                from .persistencia import exportar_gpkg
                from .exportacao import validar_gpkg
                base=pasta/'AUDITORIA_FRONTEIRAS.gpkg'
                origem=self.painel.base if self.painel and self.painel.dossie is self.dossie else self.base_revisao
                atual=exportar_gpkg(base,self.dossie,origem)
                validar_gpkg(base,atual)
                if not self.base_revisao:
                    self.base_revisao=str(base)
                self.dossie.clear()
                self.dossie.update(atual)
            if opcoes['SHP'].isChecked():
                from .exportacao import exportar_shp
                saida=exportar_shp(self.dossie,pasta/'SHP')
                self.resumo.appendPlainText(f"SHP: {len(saida['avisos'])} avisos; consulte o dicionário da entrega.")
            if opcoes['XLSX'].isChecked():
                from .relatorio import exportar_xlsx
                exportar_xlsx(self.resultado,pasta/'AUDITORIA_FRONTEIRAS.xlsx',
                              self.detalhes_excel.isChecked(),self.analise,self.dossie)
            self.resumo.appendPlainText('\nEntrega exportada: '+str(pasta))
            self.registrar_exportacao([n for n,w in opcoes.items() if w.isChecked()],str(pasta))
        except Exception as erro:
            falha(self,erro)
            QMessageBox.warning(self,'Exportação incompleta',str(erro)+'\nVerifique os arquivos já produzidos em '+str(pasta))

    def reabrir_execucao(self):
        self.iniciar_operacao(1,usar_ativa=False)
        return
    def preparar_exportacao(self):
        if self.painel and self.painel.dossie is self.dossie and self.painel.tem_edicoes():
            if not self.painel.resolver_edicoes():
                return False
            if self.painel.tem_edicoes():
                self.painel.atualizar()
        return True

    def registrar_exportacao(self,formatos,destino):
        from pathlib import Path
        from .ciclo import perfil
        from .versoes import salvar_preferencias
        self.dossie.setdefault('configuracao',perfil(self.dossie))['exportacao']=dict(
            formatos=formatos,destino=str(destino),pasta=str(Path(destino).parent if Path(destino).suffix else Path(destino)))
        base=self.painel.base if self.painel and self.painel.dossie is self.dossie else self.base_revisao
        if base:
            self.vincular_base(base)
            salvar_preferencias(base,self.dossie['execucao_uid'],self.dossie['configuracao']['exportacao'])
            from .catalogo import lembrar
            lembrar(base,self.dossie['execucao_uid'])

    def reject(self):
        if not self._executando:
            if not self.resolver_pendencias():
                return
            if self.painel and not self.painel.close():
                return
            super().reject()

    def closeEvent(self, evento):
        if self._executando:
            evento.ignore()
        else:
            if not self.resolver_pendencias():
                evento.ignore()
                return
            if self.painel and not self.painel.close():
                evento.ignore()
                return
            super().closeEvent(evento)


_janela = None


def abrir_interface():
    """Abre/reutiliza a janela e mantém referência para o console QGIS."""
    global _janela
    if _janela is None:
        from qgis.utils import iface
        _janela = AuditoriaFronteirasDialog(iface.mainWindow() if iface else None)
    if not _janela._executando:
        _janela.atualizar_camadas()
    _janela.show()
    _janela.raise_()
    _janela.activateWindow()
    return _janela
