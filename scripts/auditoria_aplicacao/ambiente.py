"""Ambiente padrão de preparação, investigação e trabalhos; reaproveita a Central."""
from pathlib import Path

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QComboBox, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)
from .central import CentralTrabalho
from .mapa_fontes import MapaFontes
from .modelo_gis_ui import aviso
from .quadro_modelo import QuadroModelo


def acao(layout, texto, executar, primaria=False):
    b = QPushButton(texto)
    b.setObjectName('Principal' if primaria else 'Secundaria')
    b.clicked.connect(executar)
    layout.addWidget(b)
    return b


class AmbienteTrabalho(CentralTrabalho):
    def __init__(self, app):
        self._pronto = False
        self._fonte_mapa = None
        super().__init__(app)
        self.setWindowTitle('Water Network Auditor — Quadro do Modelo')
        self.legado = self.widget()
        self.legado.setParent(None)
        self.legado.hide()
        self.raiz = QWidget()
        self.raiz.setObjectName('AmbienteWNA')
        self.setWidget(self.raiz)
        self.legado.setParent(self.raiz)
        self.legado.hide()
        self.raiz.setMinimumWidth(300)
        from .aparencia import Aparencia
        self.aparencia = Aparencia(self.raiz, app.iface.mainWindow())
        v = QVBoxLayout(self.raiz)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(5)
        titulo = aviso('WATER NETWORK AUDITOR')
        titulo.setStyleSheet('font-weight:700;font-size:15px;')
        v.addWidget(titulo)
        self.barra_topo = QHBoxLayout()
        v.addLayout(self.barra_topo)
        self.projeto.setParent(self.raiz)
        self.projeto.setMinimumContentsLength(10)
        self.projeto.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.barra_topo.addWidget(self.projeto, 1)
        menu_b = QPushButton('⋯')
        menu_b.setMaximumWidth(36)
        menu = QMenu(menu_b)
        menu.addAction('Criar projeto', self.criar_projeto)
        menu.addAction('Configuração WaterGEMS', lambda: self.acionar('preparar_wg'))
        menu.addAction('Cenários e versões', lambda: self.acionar('cenarios'))
        menu.addAction('Cadastro auxiliar e intervenções', self.cadastro_auxiliar)
        menu.addAction('Ferramentas avançadas', self.abrir_avancados)
        menu_b.setMenu(menu)
        self.barra_topo.addWidget(menu_b)
        self.contexto_curto = aviso()
        self.contexto_curto.setProperty("papel", "secundario")
        v.addWidget(self.contexto_curto)
        self.cenarios = QComboBox()
        self.cenarios.setMinimumContentsLength(10)
        self.cenarios.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cenarios.setToolTip('Cada opção abre uma versão persistida com a identidade correspondente ao cenário.')
        self.cenarios.activated.connect(self.trocar_cenario)
        v.addWidget(self.cenarios)
        self.area = QComboBox()
        for rotulo, codigo in [('Preparar minha rede', 'preparar'), ('Investigar minha rede', 'investigar'),
                                ('Meus trabalhos', 'trabalhos')]:
            self.area.addItem(rotulo, codigo)
        self.area.currentIndexChanged.connect(self.mudar_area)
        v.addWidget(self.area)
        self.paginas = QStackedWidget()
        self.paginas.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        v.addWidget(self.paginas, 1)
        self.mapa = MapaFontes(app, self)
        grupo_salvo = self.settings.value('quadro/grupo', 'REDES')
        categoria_salva = self.settings.value('quadro/categoria', '')
        self.quadro = QuadroModelo(self)
        self.paginas.addWidget(self.quadro)
        self.investigar, iv = self.pagina()
        iv.addWidget(aviso('O que posso investigar?'))
        self.objetivo = QComboBox()
        for texto in ['Verificar modelo', 'Redes estruturantes', 'Zonas e fronteiras',
                      'Interferências', 'Intervenções']:
            self.objetivo.addItem(texto)
        iv.addWidget(self.objetivo)
        self.objetivo.currentIndexChanged.connect(self.atualizar_objetivo)
        self.descricao = aviso()
        iv.addWidget(self.descricao)
        self.executar_objetivo = acao(iv, 'Abrir análise', self.iniciar_objetivo, True)
        self.continuar_investigacao = acao(iv, 'Continuar investigação aberta', lambda: self.acionar('continuar'))
        self.investigacao_mais = QPushButton('Outras ações deste contexto')
        self.menu_investigar = QMenu(self.investigacao_mais)
        for nome, chave in [('Consulta topológica', 'topologia'), ('Ilhas sem origem', 'ilhas'),
                             ('Auditoria GIS', 'gis'), ('Associar GIS e WaterGEMS', 'integrar')]:
            self.menu_investigar.addAction(nome, lambda checked=False, c=chave: self.acionar(c))
        self.investigacao_mais.setMenu(self.menu_investigar)
        iv.addWidget(self.investigacao_mais)
        iv.addWidget(aviso('No roadmap · Topologia GIS, zonas topológicas e isolamento por válvulas.'))
        iv.addStretch()
        self.trabalhos, tv = self.pagina()
        tv.addWidget(aviso('Quais trabalhos já realizei?'))
        self.pesquisa = QLineEdit()
        self.pesquisa.setPlaceholderText('Pesquisar nome, modelo ou projeto')
        self.pesquisa.textChanged.connect(self.listar_trabalhos)
        tv.addWidget(self.pesquisa)
        self.tipo_trabalho = QComboBox()
        for rotulo, tipo in [('Todos', None), ('Investigações', 'INTEGRADA'),
                             ('Auditorias GIS', 'AUDITORIA_GIS'), ('Topologias WaterGEMS', 'TOPOLOGIA_WG')]:
            self.tipo_trabalho.addItem(rotulo, tipo)
        self.tipo_trabalho.currentIndexChanged.connect(self.listar_trabalhos)
        tv.addWidget(self.tipo_trabalho)
        self.trabalhos_lista = QListWidget()
        self.trabalhos_lista.setWordWrap(True)
        self.trabalhos_lista.setTextElideMode(Qt.ElideNone)
        self.trabalhos_lista.setMinimumHeight(90)
        self.trabalhos_lista.setMaximumHeight(120)
        self.trabalhos_lista.currentItemChanged.connect(self.detalhar_trabalho)
        tv.addWidget(self.trabalhos_lista)
        self.trabalho_detalhes = aviso()
        tv.addWidget(self.trabalho_detalhes)
        self.abrir_trabalho_b = acao(tv, 'Abrir trabalho', self.abrir_trabalho, True)
        self.trabalhos_menu_b = QPushButton('Histórico, conjuntos e exportações')
        self.trabalhos_menu = QMenu(self.trabalhos_menu_b)
        for nome, fn in [
            ('Análises salvas, ocorrências e propostas', self.historico_aberto),
            ('Selection Sets importados', lambda: self.acionar('selection_sets')),
            ('Relatório ilustrado', lambda: self.acionar('relatorio')),
            ('Exportar acompanhamento', self.exportar_aberto),
            ('Comparar versões', self.comparar_aberto),
            ('Gerenciar catálogo e recuperação', lambda: self.app.catalogar()),
        ]:
            self.trabalhos_menu.addAction(nome, fn)
        self.trabalhos_menu_b.setMenu(self.trabalhos_menu)
        tv.addWidget(self.trabalhos_menu_b)
        tv.addWidget(aviso('Ocorrências, decisões, propostas e conjuntos pertencem à investigação aberta.'))
        tv.addStretch()
        self.mapa.mensagem.connect(self.receber_mapa)
        self.mapa_info = aviso()
        self.mapa_info.hide()
        self.mapa_info.setMaximumHeight(80)
        self.mapa_info.setToolTip('Selecione feições no QGIS para consultar sua identificação sem alterar a seleção.')
        v.addWidget(self.mapa_info)
        mapa_faixa = QHBoxLayout()
        v.addLayout(mapa_faixa)
        acao(mapa_faixa, 'Enquadrar destaque', self.mapa.aproximar)
        acao(mapa_faixa, 'Limpar', self.limpar_mapa)
        self.avisos = aviso()
        self.avisos.hide()
        v.addWidget(self.avisos)
        rodape = QHBoxLayout()
        v.addLayout(rodape)
        janela = QPushButton('Janelas')
        janela.setMenu(app.menu_janelas)
        rodape.addWidget(janela)
        self._pronto = True
        grupo = grupo_salvo
        self.quadro.escolher(grupo if grupo in self.quadro.cards else 'REDES')
        idx = self.quadro.categorias.findData(categoria_salva)
        if idx >= 0:
            self.quadro.categorias.setCurrentIndex(idx)
        codigo = self.settings.value('ambiente/area', 'preparar')
        self.area.setCurrentIndex(max(0, self.area.findData(codigo)))
        self.pesquisa.setText(self.settings.value('ambiente/pesquisa', ''))
        self.pesquisa.textChanged.connect(lambda t: self.settings.setValue('ambiente/pesquisa', t))
        self.atualizar_objetivo()
        self.atualizar()

    def pagina(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(2, 4, 2, 4)
        scroll.setWidget(w)
        self.paginas.addWidget(scroll)
        return scroll, v

    def mudar_area(self):
        if not self._pronto:
            return
        if self.ocupado():
            self.app.atividades.exibir()
        codigo = self.area.currentData()
        self.paginas.setCurrentWidget({'preparar': self.quadro, 'investigar': self.investigar,
                                       'trabalhos': self.trabalhos}[codigo])
        self.settings.setValue('ambiente/area', codigo)
        if codigo == 'trabalhos':
            self.listar_trabalhos()

    def abrir_modelo_gis(self):
        if not self._pronto:
            return super().abrir_modelo_gis()
        self.legado.hide()
        self.paginas.show()
        self.area.show()
        self.area.setCurrentIndex(0)
        self.paginas.setCurrentWidget(self.quadro)
        self.modelo_gis.atualizar()

    def abrir_avancados(self):
        if self.ocupado():
            return
        self.paginas.hide()
        self.area.hide()
        if not getattr(self, '_legado_inserido', False):
            self.raiz.layout().insertWidget(self.raiz.layout().indexOf(self.paginas), self.legado, 1)
            retorno = QPushButton('‹ Voltar ao Quadro do Modelo')
            retorno.clicked.connect(self.abrir_modelo_gis)
            self.legado.layout().insertWidget(0, retorno)
            self._legado_inserido = True
        self.legado.show()

    def cadastro_auxiliar(self):
        self.abrir_modelo_gis()
        if self.modelo_gis.tarefa is None:
            self.modelo_gis.mostrar(self.modelo_gis.inicio)

    def atualizar(self):
        if not self._pronto:
            return super().atualizar()
        super().atualizar()
        self.atualizar_contexto()
        self.avisos.setText(self.pendencias.text())
        self.avisos.setVisible(bool(self.avisos.text()))
        self.atualizar_cenarios()
        self.quadro.atualizar()
        self.preparar_avisos()
        self.listar_trabalhos()

    def atualizar_contexto(self):
        f = self._fatos
        projeto = self.projetos.atual()
        self.projeto.setToolTip((projeto['nome'] + '\nUUID ' + projeto['uuid']) if projeto else 'Selecione um projeto')
        ctx = f.get('contexto', {})
        if f.get('wg', {}).get('valido'):
            texto = str(ctx.get('modelo', 'WaterGEMS')) + ' · Cenário ' + str(ctx.get('nome_cenario', ctx.get('cenario', '')))
            texto += '\nHipótese · ' + str(ctx.get('perspectiva', 'não selecionada'))
        else:
            texto = 'Cadastro GIS'
        cats, fontes, pendentes = self.modelo_gis.resumo()
        self.contexto_curto.setText(texto + f' · {fontes} fonte(s)' + (f' · {pendentes} a revisar' if pendentes else ''))
        self.contexto_curto.setToolTip('Projeto, modelo e cenário são vinculados por identidade. As hipóteses de conectividade não confirmam operação hidráulica.')

    def preparar_avisos(self):
        if not self.ocupado():
            self.continuar_investigacao.setText('Continuar investigação aberta' if self.app.painel_atual()
                                                else 'Abrir investigação persistida…')

    def atualizar_cenarios(self):
        f = self._fatos
        ctx = f.get('contexto', {})
        atual = f.get('wg', {}).get('uuid')
        modelo = next((r.get('modelo_uid') for r in self._registros
                       if r['uuid'] == atual and r['tipo'] == 'TOPOLOGIA_WG'), None)
        rs = [r for r in self._registros if r['tipo'] == 'TOPOLOGIA_WG' and modelo
              and self.projetos.contem(r['tipo'], r['uuid'])
              and r.get('modelo_uid') == modelo]
        self.cenarios.blockSignals(True)
        self.cenarios.clear()
        rotulo = ('Cenário ' + str(ctx.get('nome_cenario', ctx.get('cenario', '—'))) + ' · versão incorporada'
                  if atual else 'Selecionar cenário WaterGEMS…')
        self.cenarios.addItem(rotulo, None)
        for r in rs:
            self.cenarios.addItem(f"Cenário {r.get('cenario')} · {r['nome']} · V{r.get('versao')}", r)
            if r['uuid'] == atual:
                self.cenarios.setCurrentIndex(self.cenarios.count() - 1)
        self.cenarios.addItem('Outros cenários / preparar versão…', 'abrir')
        self.cenarios.blockSignals(False)
        self.cenarios.setVisible(bool(atual))

    def trocar_cenario(self):
        r = self.cenarios.currentData()
        if r == 'abrir' or r is None:
            self.acionar('cenarios' if self._fatos.get('wg', {}).get('valido') else 'preparar_wg')
            return
        if not self.modelo_gis.resolver():
            self.atualizar_cenarios()
            return
        try:
            if self.app.trocar_base(r):
                self.projetos.vincular(r)
                self.limpar_mapa()
        except Exception as e:
            self.pendencias.setText('Cenário preservado. ' + str(e))
        self.atualizar()

    def criar_projeto(self):
        antes = self.projetos.dados['ativo']
        super().criar_projeto()
        if self._pronto and antes != self.projetos.dados['ativo']:
            self.limpar_mapa()
            self.quadro.escolher(self.quadro.grupo)

    def escolher_projeto(self, i):
        antes = self.projetos.dados['ativo']
        super().escolher_projeto(i)
        if self._pronto and antes != self.projetos.dados['ativo']:
            self.limpar_mapa()
            self.quadro.escolher(self.quadro.grupo)

    def destacar_fonte(self, fonte):
        token = (fonte['uid'], fonte['assinatura'], fonte['filtro'])
        if (token != self._fonte_mapa or self.mapa.fonte is None) and not self.ocupado():
            if self.mapa.destacar(fonte):
                self._fonte_mapa = token

    def receber_mapa(self, mensagem):
        self.mapa_info.setText(mensagem.split('\n')[0])
        self.mapa_info.show()
        self.mapa_info.setToolTip(mensagem)
        if '\n' in mensagem:
            self.mapa_info.setText(mensagem)

    def limpar_mapa(self):
        self._fonte_mapa = None
        self.mapa.limpar()
        self.mapa_info.clear()
        self.mapa_info.hide()

    def atualizar_objetivo(self):
        textos = [
            ('Consultar a conectividade WaterGEMS e os dispositivos da versão aberta.', 'Abrir consulta topológica'),
            ('Calcular corredores entre origens e destinos com os critérios disponíveis.', 'Identificar corredores'),
            ('Investigar travessias, dispositivos próximos e correspondências na investigação.', 'Abrir investigação'),
            ('Consultar ocorrências e evidências entre regiões na investigação integrada.', 'Examinar ocorrências'),
            ('Recuperar propostas e criar intervenções investigativas na ocorrência selecionada.', 'Consultar propostas'),
        ]
        descricao, acao_ = textos[self.objetivo.currentIndex()]
        self.descricao.setText(descricao)
        self.executar_objetivo.setText(acao_)

    def iniciar_objetivo(self):
        self.limpar_mapa()
        i = self.objetivo.currentIndex()
        if i == 4:
            self.historico_aberto()
        else:
            self.acionar(['topologia', 'corredores', 'continuar', 'continuar'][i])

    def listar_trabalhos(self):
        if not self._pronto:
            return
        antigo = self.trabalhos_lista.currentItem()
        identidade = antigo.data(Qt.UserRole) if antigo else None
        termo = self.pesquisa.text().casefold()
        tipo = self.tipo_trabalho.currentData()
        self.trabalhos_lista.blockSignals(True)
        self.trabalhos_lista.clear()
        self._trabalhos = []
        p = self.projetos.atual()
        refs = {(r['uuid'], r['tipo']) for r in (p or {}).get('bases', [])}
        for r in self._registros:
            if p and (r['uuid'], r['tipo']) not in refs:
                continue
            if r.get('estado_catalogo') in ('ARQUIVADA', 'RETIRADA') or r.get('classe_arquivo') in ('BACKUP_TECNICO', 'BACKUP_CANDIDATO'):
                continue
            if tipo and r['tipo'] != tipo:
                continue
            if termo not in ' '.join(str(r.get(k, '')) for k in ('nome', 'modelo_uid', 'projeto', 'cenario')).casefold():
                continue
            chave = (r['uuid'], r['tipo'], r['base'])
            item = QListWidgetItem(r['nome'] + f"\n{r['tipo']} · V{r.get('versao', '—')}")
            item.setData(Qt.UserRole, chave)
            item.setToolTip(r['base'])
            self.trabalhos_lista.addItem(item)
            self._trabalhos.append(r)
            if chave == identidade:
                self.trabalhos_lista.setCurrentItem(item)
        self.trabalhos_lista.blockSignals(False)
        self.detalhar_trabalho(self.trabalhos_lista.currentItem())

    def detalhar_trabalho(self, item, *_):
        r = self.registro_trabalho()
        self.abrir_trabalho_b.setEnabled(bool(r))
        if r:
            dispo = 'Disponível' if Path(r['base']).is_file() else 'Arquivo ausente · localizar pelo catálogo'
            cenario = r.get('cenario')
            self.trabalho_detalhes.setText(r['nome'] + '\n' + dispo +
                                          ('\nCenário ' + str(cenario) if cenario is not None else ''))
        else:
            self.trabalho_detalhes.setText('Selecione um trabalho do projeto. Use o catálogo para adicionar ou recuperar arquivos.')

    def registro_trabalho(self):
        i = self.trabalhos_lista.currentRow()
        return self._trabalhos[i] if 0 <= i < len(getattr(self, '_trabalhos', [])) else None

    def abrir_trabalho(self):
        r = self.registro_trabalho()
        if not r:
            return False
        if not self.modelo_gis.resolver():
            return False
        try:
            self.limpar_mapa()
            from .contexto_trabalho import validar_registro
            check = validar_registro(r)
            if not check['valido']:
                self.pendencias.setText(check['erro'])
                self.avisos.setText(check['erro'])
                self.avisos.show()
                return False
            if self.app.abrir_registro(r):
                self.projetos.vincular(r)
                self.atualizar()
                return True
        except Exception as e:
            self.pendencias.setText('Trabalho preservado. ' + str(e))
            self.avisos.setText(self.pendencias.text())
            self.avisos.show()
        return False

    def historico_aberto(self):
        if self.app.painel_atual():
            self.limpar_mapa()
            p = self.app.painel
            self.app.janelas.mostrar('integrada')
            p.tabs.setCurrentWidget(p.analise)
        else:
            self.acionar('continuar')

    def exportar_aberto(self):
        if self.app.painel_atual():
            self.app.painel.exportar_decisoes()
        else:
            self.acionar('continuar')

    def comparar_aberto(self):
        if self.app.painel_atual():
            self.app.painel.comparar_versoes()
        else:
            self.app.comparar()

    def closeEvent(self, event):
        if not self.app.preparar_saida():
            event.ignore()
            return
        self.limpar_mapa()
        super().closeEvent(event)
