"""Ambiente padrão de preparação, investigação e trabalhos; reaproveita a Central."""
from pathlib import Path

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QComboBox, QHBoxLayout, QLineEdit, QMenu,
    QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget, QFileDialog, QInputDialog,
)
from .central import CentralTrabalho
from .mapa_fontes import MapaFontes
from .modelo_gis_ui import aviso
from .navegacao_cartografica import acao_disponivel,navegar_registros
from .quadro_modelo import QuadroModelo
from .projeto_ui import GestaoProjetosUI, TabelaTrabalhos
from .projeto_visual_ui import VisualProjetoUI
from .salvamento_projeto_ui import SalvamentoProjetoUI
from . import trabalhos_projeto as tp


def acao(layout, texto, executar, primaria=False):
    b = QPushButton(texto)
    b.setObjectName('Principal' if primaria else 'Secundaria')
    b.clicked.connect(executar)
    layout.addWidget(b)
    return b


class AmbienteTrabalho(CentralTrabalho, GestaoProjetosUI, VisualProjetoUI, SalvamentoProjetoUI):
    def __init__(self, app):
        self._pronto = False
        self._fonte_mapa = None
        self._central_legada = None
        self._contexto_lido = self._catalogo_lido = None
        self._extras_trabalhos={}
        self._filtro_hipotese_uid=None
        self._preservar_filtro_hipotese=False
        self._ordem_trabalhos=None
        self._falha_salvar=None
        super().__init__(app, leve=True)
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
        menu_b.setToolTip('Arquivo e opções do projeto')
        menu_b.setAccessibleName('Arquivo')
        menu = QMenu(menu_b)
        menu.addAction('Novo projeto (.wna)…', self.novo_manifesto)
        menu.addAction('Abrir projeto (.wna)…', self.abrir_projeto)
        menu.addAction('Salvar projeto',self.salvar_projeto)
        menu.addAction('Salvar projeto como…',self.salvar_projeto_como)
        menu.addAction('Organizar projeto existente…', self.organizar_existente)
        menu.addAction('Mostrar localização do projeto',self.mostrar_localizacao)
        menu.addAction('Abrir pasta do projeto',self.abrir_pasta_projeto)
        menu.addAction('Copiar caminho do projeto',self.copiar_localizacao)
        menu.addAction('Consultar arquivos vinculados…',self.consultar_arquivos)
        menu.addAction('Recuperar trabalhos sem referência…',self.recuperar_orfaos)
        recentes=menu.addMenu('Projetos recentes')
        recentes.aboutToShow.connect(lambda:self.menu_projetos_recentes(recentes))
        menu.addAction('Configuração WaterGEMS', lambda: self.acionar('preparar_wg'))
        menu.addAction('Cenários e versões', lambda: self.acionar('cenarios'))
        menu.addAction('Cadastro auxiliar e intervenções', self.cadastro_auxiliar)
        menu.addAction('Ferramentas avançadas', self.abrir_avancados)
        menu_b.setMenu(menu)
        self.barra_topo.addWidget(menu_b)
        faixa_salvar = QHBoxLayout()
        v.addLayout(faixa_salvar)
        self.estado_salvar = aviso()
        self.estado_salvar.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
        faixa_salvar.addWidget(self.estado_salvar,1)
        self.salvar_projeto_b = acao(faixa_salvar,'Salvar projeto',self.salvar_projeto)
        self.abrir_rascunho_b = acao(v,'Retomar edição salva',self.abrir_rascunho_salvo)
        self.abrir_rascunho_b.hide()
        self.contexto_curto = aviso()
        self.contexto_curto.setProperty("papel", "secundario")
        v.addWidget(self.contexto_curto)
        self.ultimo_trabalho_info=aviso()
        v.addWidget(self.ultimo_trabalho_info)
        self.continuar_trabalho_b=acao(v,'Continuar último trabalho',self.continuar_trabalho,True)
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
        self.iniciar_estado_visual()
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
        acao(iv, 'Analisar conectividade', self.abrir_conectividade)
        acao(iv,'Abrir análise de conectividade salva…',lambda:self.listar_execucoes_salvas())
        self.continuar_investigacao = acao(iv, 'Continuar investigação aberta', lambda: self.acionar('continuar'))
        self.investigacao_mais = QPushButton('Outras ações deste contexto')
        self.menu_investigar = QMenu(self.investigacao_mais)
        for nome, chave in [('Consulta topológica', 'topologia'), ('Ilhas sem origem', 'ilhas'),
                             ('Auditoria GIS', 'gis'), ('Associar GIS e WaterGEMS', 'integrar'),
                             ('Corredores sobre topologia WaterGEMS', 'corredores')]:
            self.menu_investigar.addAction(nome, lambda checked=False, c=chave: self.acionar(c))
        self.investigacao_mais.setMenu(self.menu_investigar)
        iv.addWidget(self.investigacao_mais)
        iv.addWidget(aviso('Zonas topológicas e isolamento por válvulas estão no roadmap.'))
        iv.addStretch()
        self.trabalhos, tv = self.pagina()
        tv.addWidget(aviso('Quais trabalhos já realizei?'))
        self.pesquisa = QLineEdit()
        self.pesquisa.setPlaceholderText('Pesquisar nome, modelo ou projeto')
        self.pesquisa.textChanged.connect(self.listar_trabalhos)
        tv.addWidget(self.pesquisa)
        self.tipo_trabalho = QComboBox()
        for rotulo, tipo in [('Todos', None), ('Investigações', 'INTEGRADA'),
                             ('Auditorias GIS', 'AUDITORIA_GIS'), ('Topologias WaterGEMS', 'TOPOLOGIA_WG'),
                             ('Conectividade GIS', 'TOPOLOGIA_GIS'), ('Redes estruturantes GIS', 'ESTRUTURA_GIS')]:
            self.tipo_trabalho.addItem(rotulo, tipo)
        self.tipo_trabalho.currentIndexChanged.connect(self.alterar_tipo_trabalho)
        tv.addWidget(self.tipo_trabalho)
        self.filtro_hipotese_info=aviso()
        self.filtro_hipotese_info.hide()
        tv.addWidget(self.filtro_hipotese_info)
        self.trabalhos_lista = TabelaTrabalhos()
        self.trabalhos_lista.colunas(('Nome','Tipo','Hipótese','Revisão','Data (UTC)','Última abertura (UTC)','Arquivo'))
        self.trabalhos_lista.setMinimumHeight(90)
        self.trabalhos_lista.setMaximumHeight(250)
        self.trabalhos_lista.currentCellChanged.connect(self.detalhar_trabalho)
        self.trabalhos_lista.horizontalHeader().sectionClicked.connect(self.ordenar_trabalhos)
        navegar_registros(self.trabalhos_lista,lambda _,a:self.abrir_trabalho(cartografar=True,aproximar=a),
                          acoes=self.menu_trabalho,limpar=self.limpar_mapa)
        tv.addWidget(self.trabalhos_lista)
        self.trabalho_detalhes = aviso()
        tv.addWidget(self.trabalho_detalhes)
        self.abrir_trabalho_b = acao(tv, 'Abrir trabalho', self.abrir_trabalho, True)
        self.localizar_trabalho_b = acao(tv,'Localizar arquivo do trabalho…',self.relocalizar_trabalho)
        self.localizar_trabalho_b.hide()
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
        self.aproximar_b = acao(mapa_faixa, 'Enquadrar destaque', self.aproximar_contexto)
        self.paginas.currentChanged.connect(self.atualizar_comando_mapa)
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
        self.atualizar_continuacao()
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

    def __getattr__(self, nome):
        # Compatibilidade dos acessos avançados, sem construir a Central na entrada.
        if self.__dict__.get('_pronto') and nome in ('tabs', 'nivel', 'preparacao', 'tabela', 'progresso', 'acoes', 'resumo_gis'):
            return getattr(self.obter_legado(), nome)
        raise AttributeError(nome)

    def obter_legado(self):
        if self._central_legada is None:
            legado = CentralTrabalho(self.app, dono=self)
            legado.setObjectName('WNA_Central_Legada')
            legado.timer.stop()
            legado.setParent(self)
            antigo = self.legado
            self.legado = legado.widget()
            self.legado.setParent(self.raiz)
            self.legado.hide()
            antigo.deleteLater()
            self._central_legada = legado
        return self._central_legada

    def mudar_area(self):
        if not self._pronto:
            return
        if self.ocupado():
            self.app.atividades.exibir()
        conectividade=self.__dict__.get('conectividade_gis')
        if conectividade is not None:
            if self.paginas.currentWidget() is conectividade and not conectividade.resolver_edicao():
                bloqueado=self.area.blockSignals(True)
                self.area.setCurrentIndex(self.area.findData('investigar'))
                self.area.blockSignals(bloqueado)
                return
            conectividade.cancelar_captura()
        estrutura=self.__dict__.get('estrutura_gis')
        if estrutura is not None:estrutura.cancelar_captura()
        codigo = self.area.currentData()
        self.salvar_estado_atual()
        self.paginas.setCurrentWidget({'preparar': self.quadro, 'investigar': self.investigar,
                                       'trabalhos': self.trabalhos}[codigo])
        self.settings.setValue('ambiente/area', codigo)
        if codigo == 'trabalhos':
            if not self.projetos.atual():self.garantir_catalogo()
            self.listar_trabalhos()

    def abrir_modelo_gis(self):
        if not self._pronto:
            return super().abrir_modelo_gis()
        self.legado.hide()
        self.paginas.show()
        self.area.show()
        self.area.setCurrentIndex(0)
        self.paginas.setCurrentWidget(self.quadro)

    def abrir_avancados(self):
        if self.ocupado():
            return
        self.obter_legado().atualizar()
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
            return
        self._atualizar_salvamento()
        if self.ocupado():
            self.pendencias.setText('Atividade em andamento. Acompanhe etapas e cancelamento em Janelas / painéis.')
            return
        if self.pendencias.text().startswith('Atividade em andamento.'):
            self.pendencias.clear()
        from .contexto_trabalho import fatos
        from .dependencias import avaliar
        g, w, p = self.app.geo, self.app.wg, self.app.painel
        from qgis.PyQt import sip
        if w and sip.isdeleted(w): w = None
        if p and sip.isdeleted(p): p = None
        base = getattr(w, 'base', None)
        chave = (self.projetos.dados['ativo'], id(g.dossie), (g.dossie or {}).get('execucao_uid'),
                 g.base_revisao, g._executando, g.pendente(),
                 base, self.marca(base), id(getattr(w, '_prova', None)),
                 w.modo.currentText() if w else None,
                 tuple(c.currentData() for c in w.mapas.values()) if w else (),
                 id(p), p.pacote['resultado']['meta']['uid'] if p else None,
                 p._ativo if p else None, p.modo.currentData() if p else None)
        if chave != self._contexto_lido:
            self._fatos = fatos(self.app)
            self._requisitos = avaliar(self._fatos)
            self._contexto_lido = chave
            if self._central_legada is not None and self.legado.isVisible():
                self._central_legada._carregar_projetos()
                self._central_legada.atualizar()
        self.atualizar_contexto()
        self.avisos.setText(self.pendencias.text())
        self.avisos.setVisible(bool(self.avisos.text()))
        self.atualizar_cenarios()
        self.quadro.atualizar()
        self.preparar_avisos()
        if self.paginas.currentWidget() is self.trabalhos:
            if not self.projetos.atual():self.garantir_catalogo()
            self.listar_trabalhos()

    @staticmethod
    def marca(arquivo):
        if not arquivo:
            return None
        marcas = []
        for nome in (str(arquivo), str(arquivo) + '-wal'):
            try:
                s = Path(nome).stat()
                marcas.append((s.st_size, s.st_mtime_ns))
            except OSError:
                marcas.append(None)
        return tuple(marcas)

    def garantir_catalogo(self):
        chave = self.marca(self.app.catalogo.raiz / 'catalogo_bases.sqlite')
        if chave != self._catalogo_lido:
            self._registros = self.app.catalogo.listar_opcional()
            self._catalogo_lido = self.marca(self.app.catalogo.raiz / 'catalogo_bases.sqlite')

    def acionar(self, chave):
        # Os requisitos são verificados no instante da ação, não na troca de categoria.
        self._contexto_lido = None
        return super().acionar(chave)

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
        if atual:
            self.garantir_catalogo()
        modelo = next((r.get('modelo_uid') for r in self._registros
                       if r['uuid'] == atual and r['tipo'] == 'TOPOLOGIA_WG'), None)
        rs = [r for r in self._registros if r['tipo'] == 'TOPOLOGIA_WG' and modelo
              and self.projetos.contem(r['tipo'], r['uuid'])
              and r.get('modelo_uid') == modelo]
        chave_cenarios = (self.projetos.dados['ativo'], atual, str(ctx.get('cenario')), str(ctx.get('nome_cenario')),
                          tuple((r['uuid'], r.get('nome'), r.get('cenario'), r.get('versao')) for r in rs))
        if chave_cenarios == getattr(self, '_chave_cenarios', None):
            return
        self._chave_cenarios = chave_cenarios
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
        self.novo_manifesto()

    def menu_projetos_recentes(self, menu):
        menu.clear()
        for p in reversed(self.projetos.dados['projetos']):
            menu.addAction(p['nome'], lambda checked=False,uid=p['uuid']:self.escolher_projeto(self.projeto.findData(uid)))

    def _resolver_troca_projeto(self):
        if (not self.ocupado() and self.resolver_salvamento_projeto()
                and self.app.resolver() and self.app.geo.resolver_pendencias()
                and self.app.resolver_configuracao_wg() and self.modelo_gis.resolver()):
            self.salvar_estado_atual()
            return True
        return False

    def novo_manifesto(self):
        if not self._resolver_troca_projeto():return
        nome,ok=QInputDialog.getText(self,'Novo projeto','Nome do projeto')
        if ok and nome.strip():self._salvar_manifesto(nome.strip())

    def migrar_manifesto(self):
        self.organizar_existente()

    def _salvar_manifesto(self,nome):
        from .manifesto_projeto import nome_arquivo
        pasta=QFileDialog.getExistingDirectory(self,'Pasta que receberá o novo projeto',str(self.app.catalogo.raiz))
        if not pasta:return
        try:
            slug=nome_arquivo(nome)
            destino=Path(pasta)/slug
            destino.mkdir(exist_ok=False)
            arq=destino/(slug+'.wna')
            self.projetos.salvar_manifesto(arq,nome)
            self._manifesto_aberto()
        except (ValueError,OSError) as e:self.receber_mapa(str(e))

    def abrir_projeto(self):
        if not self._resolver_troca_projeto():return
        arq,_=QFileDialog.getOpenFileName(self,'Abrir projeto','','Projeto Water Network Auditor (*.wna)')
        if not arq:return
        try:
            self.projetos.abrir_manifesto(arq)
            self._manifesto_aberto()
        except (ValueError,OSError) as e:self.receber_mapa(str(e))

    def _manifesto_aberto(self):
        self.limpar_mapa()
        self._carregar_projetos()
        from .manifesto_projeto import recuperar_camadas_locais
        avisos=recuperar_camadas_locais(self.projetos.atual())
        self.modelo_gis.recarregar()
        self._extras_trabalhos={}
        self._filtro_hipotese_uid=None
        self.tipo_trabalho.setCurrentIndex(0)
        self.pesquisa.clear()
        self._catalogo_lido=None
        self.area.setCurrentIndex(self.area.findData('trabalhos'))
        self.mudar_area()
        self.atualizar()
        self.atualizar_continuacao()
        if avisos:self.receber_mapa('\n'.join(avisos))
        self.enriquecer_lista()

    def abrir_conectividade(self, checked=False, origens=False):
        if self.ocupado() or not self.app.resolver() or not self.modelo_gis.resolver():
            return False
        if not self.projetos.atual():
            self.receber_mapa('Crie ou abra um projeto para analisar sua rede.')
            return False
        pagina=self._pagina_conectividade()
        pagina.abrir(origens)
        self.area.setCurrentIndex(self.area.findData('investigar'))
        self.paginas.setCurrentWidget(pagina)
        return True

    def _pagina_conectividade(self):
        pagina=self.__dict__.get('conectividade_gis')
        if pagina is None:
            from .topologia_gis_ui import TopologiaGIS
            pagina=self.conectividade_gis=TopologiaGIS(self)
            self.paginas.addWidget(pagina)
        return pagina

    def abrir_estrutura(self, checked=False, foto=None, recuperar=False):
        if self.ocupado() or not self.app.resolver() or not self.modelo_gis.resolver():
            return False
        p=self.projetos.atual()
        if not p:
            self.receber_mapa('Crie ou abra um projeto para analisar redes estruturantes.')
            return False
        topologia=self.__dict__.get('conectividade_gis')
        if foto is None and not recuperar and topologia is not None:
            d=topologia.dados
            if d and d.get('projeto_uid')==p['uuid']:foto=d
        pagina=self.__dict__.get('estrutura_gis')
        if pagina is None:
            from .estrutura_gis_ui import EstruturaGIS
            pagina=self.estrutura_gis=EstruturaGIS(self)
            self.paginas.addWidget(pagina)
        self.area.setCurrentIndex(self.area.findData('investigar'))
        self.paginas.setCurrentWidget(pagina)
        pagina.abrir(foto)
        return True

    def escolher_projeto(self, i):
        antes = self.projetos.dados['ativo']
        uid = self.projeto.itemData(i)
        if self._pronto and uid and uid != antes and not self._resolver_troca_projeto():
            self._carregar_projetos()
            return
        if self._pronto:self.salvar_estado_atual()
        super().escolher_projeto(i)
        if self._pronto and antes != self.projetos.dados['ativo']:
            self._extras_trabalhos={}
            self._filtro_hipotese_uid=None
            self.limpar_mapa()
            self.quadro.escolher(self.quadro.grupo)
            if self.paginas.currentWidget() in (self.__dict__.get('conectividade_gis'),self.__dict__.get('estrutura_gis')):
                self.mudar_area()
            self.atualizar_continuacao()
            if self.paginas.currentWidget() is self.trabalhos:
                self.listar_trabalhos()
                self.enriquecer_lista()

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
        estrutura=self.__dict__.get('estrutura_gis')
        if estrutura is not None:estrutura.restaurar_opacidade_macro()
        self._fonte_mapa = None
        self.mapa.limpar()
        self.mapa_info.clear()
        self.mapa_info.hide()

    def atualizar_objetivo(self):
        textos = [
            ('Auditoria geométrica de travessias em setores, zonas de VRP, zonas de booster e outros limites cadastrados.', 'Verificar travessias e limites'),
            ('Investigue corredores, ligações críticas e dependências sobre uma execução de conectividade GIS.', 'Abrir redes estruturantes'),
            ('Auditoria GIS de travessias entre redes e limites. Não exige WaterGEMS. Zonas topológicas são futuras.', 'Investigar fronteiras GIS'),
            ('Examinar travessias e dispositivos próximos nas camadas GIS. Comparação topológica com WaterGEMS é adicional.', 'Examinar interferências GIS'),
            ('Propostas existentes pertencem à investigação integrada aberta. Planejamento sobre topologia GIS independente é futuro.', 'Consultar propostas existentes'),
        ]
        descricao, acao_ = textos[self.objetivo.currentIndex()]
        self.descricao.setText(descricao)
        self.executar_objetivo.setText(acao_)

    def iniciar_objetivo(self):
        self.limpar_mapa()
        i = self.objetivo.currentIndex()
        if i == 4:
            self.historico_aberto()
        elif i in (0, 2, 3):
            self.abrir_analise_gis({0: 'verificar', 2: 'fronteiras', 3: 'interferencias'}[i])
        else:
            self.abrir_estrutura()

    def abrir_analise_gis(self, objetivo):
        if self.ocupado() or not self.modelo_gis.resolver(): return False
        pagina = self.__dict__.get('analise_gis')
        if pagina is None:
            from .analise_gis_ui import AnaliseGIS
            pagina = self.analise_gis = AnaliseGIS(self)
            self.paginas.addWidget(pagina)
        if not pagina.abrir(objetivo): return False
        self.area.setCurrentIndex(self.area.findData('investigar'))
        self.paginas.setCurrentWidget(pagina)
        return True

    def atualizar_comando_mapa(self, *_):
        gis = self.__dict__.get('analise_gis')
        ativo = gis is not None and self.paginas.currentWidget() is gis
        self.aproximar_b.setText('Aproximar local' if ativo else 'Enquadrar destaque')

    def aproximar_contexto(self):
        gis = self.__dict__.get('analise_gis')
        if gis is not None and self.paginas.currentWidget() is gis: return gis.aproximar()
        return self.mapa.aproximar()

    def alterar_tipo_trabalho(self,*_):
        if not self._preservar_filtro_hipotese:self._filtro_hipotese_uid=None
        self.listar_trabalhos()

    def ordenar_trabalhos(self,coluna):
        anterior=self._ordem_trabalhos
        desc=not anterior[1] if anterior and anterior[0]==coluna else coluna in (4,5)
        self._ordem_trabalhos=(coluna,desc)
        h=self.trabalhos_lista.horizontalHeader()
        h.setSortIndicator(coluna,Qt.DescendingOrder if desc else Qt.AscendingOrder)
        h.setSortIndicatorShown(True)
        self.listar_trabalhos()

    def listar_trabalhos(self,*_):
        if not self._pronto:
            return
        antigo = self.trabalhos_lista.currentItem()
        identidade = tp.chave(antigo.data(Qt.UserRole)) if antigo else None
        termo = self.pesquisa.text().casefold()
        tipo = self.tipo_trabalho.currentData()
        hip=self._filtro_hipotese_uid
        visual=self.estados_de_visualizacao()
        linhas=[]
        for r in self.registros_projeto():
            if tipo and r['tipo']!=tipo:continue
            if hip and r.get('hipotese_uid')!=hip:continue
            if termo not in ' '.join(str(r.get(k,'')) for k in ('nome','modelo_uid','hipotese_nome','base','uuid')).casefold():
                continue
            v=visual.get(f"{r['tipo']}:{r['uuid']}",{})
            t='Revisar' if r.get('erro') else 'Disponível' if r['disponivel'] else 'Ausente'
            valores=(r['nome'],tp.ROTULOS.get(r['tipo'],r['tipo']),r.get('hipotese_nome') or '—',
                     (r.get('hipotese_rev') or '')[:8],(r.get('data') or '')[:19].replace('T',' '),
                     v.get('ultima_abertura','')[:19].replace('T',' '),t)
            linhas.append((r,valores))
        if self._ordem_trabalhos:
            coluna,desc=self._ordem_trabalhos
            linhas.sort(key=lambda linha:linha[1][coluna].casefold(),reverse=desc)
        chave_lista=(self.projetos.dados['ativo'],hip,self._ordem_trabalhos,linhas)
        if chave_lista==getattr(self,'_lista_trabalhos_chave',None):
            self.atualizar_continuacao()
            return
        self._lista_trabalhos_chave=chave_lista
        self.trabalhos_lista.blockSignals(True)
        self.trabalhos_lista.limpar()
        self._trabalhos = []
        for r,valores in linhas:
            item=self.trabalhos_lista.inserir(valores,r)
            item.setToolTip(r['base'])
            self._trabalhos.append(r)
            if tp.chave(r)==identidade:self.trabalhos_lista.setCurrentItem(item)
        self.trabalhos_lista.blockSignals(False)
        self.filtro_hipotese_info.setVisible(bool(hip))
        if hip:
            nome_hip=next((r['hipotese_nome'] for r,_ in linhas if r.get('hipotese_nome')),hip[:8])
            self.filtro_hipotese_info.setText('Execuções da hipótese '+nome_hip+' · altere o tipo para limpar o filtro.')
        self.detalhar_trabalho()
        self.atualizar_continuacao()

    def detalhar_trabalho(self, *_):
        r = self.registro_trabalho()
        acao_disponivel(self.abrir_trabalho_b,'' if r else 'Selecione um trabalho para abrir.')
        self.localizar_trabalho_b.setVisible(bool(r and not Path(r['base']).is_file()))
        if r:
            dispo = r.get('erro') or ('Disponível' if r['disponivel'] else 'Arquivo ausente · use Localizar arquivo do trabalho')
            cenario = r.get('cenario')
            hip=r.get('hipotese_nome')
            detalhes=f"\nHipótese {hip} · revisão {(r.get('hipotese_rev') or '—')[:8]}" if hip else ''
            if r.get('componentes') is not None:
                detalhes+=f"\n{r['componentes']} componentes · {r.get('origens') or 0} fontes · {r.get('conexoes') or 0} conexões"
            self.trabalho_detalhes.setText(r['nome'] + '\n' + dispo + detalhes +'\n'+r['base']+
                                          ('\nCenário ' + str(cenario) if cenario is not None else ''))
        else:
            self.trabalho_detalhes.setText('Selecione um trabalho do projeto. Use o catálogo para adicionar ou recuperar arquivos.')

    def registro_trabalho(self):
        item=self.trabalhos_lista.currentItem()
        return item.data(Qt.UserRole) if item else None

    def menu_trabalho(self,i):
        item=self.trabalhos_lista.item(i.row(),0)
        r=item.data(Qt.UserRole)
        opcoes=[('Abrir trabalho',lambda:self.abrir_trabalho(registro=r)),
                ('Abrir pasta do arquivo',lambda:self.abrir_pasta_local(Path(r['base']).parent)),
                ('Localizar arquivo…',self.relocalizar_trabalho),
                ('Histórico e dependências',lambda:self.historico_trabalho(r))]
        if r['tipo'] in tp.TABELAS:
            opcoes.append(('Abrir para comparar…',lambda:self.abrir_trabalho(registro=r,comparar=True)))
        return opcoes

    def relocalizar_trabalho(self):
        r=self.registro_trabalho()
        if not r or not self.projetos.atual() or not self._resolver_troca_projeto():return
        arquivo,_=QFileDialog.getOpenFileName(self,'Localizar trabalho','','GeoPackage (*.gpkg)')
        if not arquivo:return
        self.confirmar_vinculo(r,arquivo)

    def trabalho_cartografico(self,indice):
        return (0<=indice.row()<len(getattr(self,'_trabalhos',())) and
                self._trabalhos[indice.row()]['tipo'] in ('AUDITORIA_GIS','TOPOLOGIA_GIS','ESTRUTURA_GIS'))

    def abrir_trabalho(self,checked=False,cartografar=False,aproximar=False,registro=None,comparar=False):
        r = registro or self.registro_trabalho()
        if not r:
            return False
        if not self.modelo_gis.resolver():
            return False
        try:
            if not Path(r['base']).is_file():
                self.receber_mapa(f"Arquivo ausente: {r['base']}. Em Meus trabalhos, selecione Localizar arquivo.")
                return False
            if r.get('erro'):
                self.receber_mapa(r['erro'])
                return False
            self.salvar_estado_atual()
            self.limpar_mapa()
            if r['tipo']=='ESTRUTURA_GIS':
                if not self.abrir_estrutura(recuperar=True):return False
                worker=self.estrutura_gis.reabrir(r)
                self.ao_abrir_trabalho(worker,self.estrutura_gis,r,cartografar,aproximar,comparar)
                return bool(worker)
            if r['tipo']=='TOPOLOGIA_GIS':
                if not self.abrir_conectividade():return False
                worker=self.conectividade_gis.reabrir(r)
                self.ao_abrir_trabalho(worker,self.conectividade_gis,r,cartografar,aproximar,comparar)
                return bool(worker)
            if r['tipo'] == 'AUDITORIA_GIS':
                if not self.abrir_analise_gis('verificar'): return False
                return self.analise_gis.abrir_persistida(r,cartografar=cartografar,aproximar=aproximar)
            from .contexto_trabalho import validar_registro
            check = validar_registro(r)
            if not check['valido']:
                self.pendencias.setText(check['erro'])
                self.avisos.setText(check['erro'])
                self.avisos.show()
                return False
            if self.app.abrir_registro(r):
                if not self.projetos.contem(r['tipo'],r['uuid']):self.projetos.vincular(r)
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
        self.salvar_estado_atual()
        for chave in ('conectividade_gis','estrutura_gis'):
            pagina=self.__dict__.get(chave)
            if pagina is not None:pagina.cancelar_captura()
        self.limpar_mapa()
        super().closeEvent(event)
