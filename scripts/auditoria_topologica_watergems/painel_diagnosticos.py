"""Ambiente de diagnóstico: casos legíveis, filtros e mapa; legado disponível."""
from pathlib import Path
from html import escape
from collections import defaultdict
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QDockWidget,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,
    QLabel,QComboBox,QLineEdit,QTableWidget,QTableWidgetItem,QAbstractItemView,
    QTreeWidget,QTreeWidgetItem,QPushButton,QTabWidget,QSplitter,QScrollArea,QTextBrowser,QHeaderView,QCheckBox,QMessageBox,QFileDialog)
from qgis.PyQt import sip
from .filtros import ContextoFiltros
from . import operacional as op
from . import acompanhamento as ac
from .diagnosticos import catalogar,filtrar,contagens,CATEGORIAS,MODOS
from .mapa_diagnosticos import MapaDiagnosticos
from auditoria_fronteiras.atividade import acompanhada,falha


class PainelDiagnosticos(QDockWidget):
    def __init__(self,legado,parent=None):
        super().__init__('Diagnósticos GIS × WaterGEMS',parent)
        self.legado=legado;self.pacote=legado.pacote;self.base=legado.base;self._ativo=True;self._sincronizando=False
        self.casos=catalogar(self.pacote);self.indice_atributos=ContextoFiltros(self.pacote);self.indice_atributos.restaurar_persistidas(self.base)
        from .locais_manuais import casos as casos_manuais
        self.casos+=casos_manuais(self.base,self.pacote,self.indice_atributos)
        self._redes_ui=None;self._ferramenta_manual=None
        self._acomp=ac.indice(self.base,self.pacote);self._contexto_acomp=ac.Contexto(self.pacote);self._situacoes_acomp={}
        self._analises=op.indice(self.base,self.pacote['resultado']['meta']['uid']);self._generico_estavel=None;self._fila_estavel=0;self._resultado_estavel=0;self._filtros_sessao={};self._pagina=0;self._tamanho_pagina=200;self._itens_pagina=[];self.atual=None;self._inversos=None;self._conexoes=[]
        self._filtros_estaveis=None;self._modo_estavel='ESTRUTURAL';self._bloqueador=None;self._iface=None
        self.mapa=MapaDiagnosticos(self.pacote,legado.projeto,legado.canvas)
        w=QWidget();self.setWidget(w);v=QVBoxLayout(w);self.resize(920,720)
        self.execucao=QLabel('Auditoria integrada · '+self.pacote['resultado']['meta']['uid'][:12]+' · detectar → localizar → investigar');self.execucao.setWordWrap(True);v.addWidget(self.execucao)
        self.tabs=QTabWidget();v.addWidget(self.tabs);diag=QWidget();self.tabs.addTab(diag,'DIAGNÓSTICOS');layout=QVBoxLayout(diag)
        self.resumo=QLabel();self.resumo.setWordWrap(True);layout.addWidget(self.resumo)
        self.carregada=QLabel();self.carregada.setWordWrap(True);layout.addWidget(self.carregada)
        atalhos=QHBoxLayout();layout.addLayout(atalhos);self.analises_salvas_botao=QPushButton('Mostrar todas as análises salvas');self.analises_salvas_botao.clicked.connect(lambda checked=False:self.abrir_analises_salvas());atalhos.addWidget(self.analises_salvas_botao)
        self.consulta_rapida=QComboBox();self.consulta_rapida.addItems(['Consultar…','Todos os casos','Casos já analisados','Anotações salvas','Locais manuais','Conjuntos salvos']);self.consulta_rapida.activated.connect(self.consultar_rapido);atalhos.addWidget(self.consulta_rapida)
        acoes_manuais=QHBoxLayout();layout.addLayout(acoes_manuais)
        self.origem_filtro=QComboBox();self.origem_filtro.addItem('Todas as origens',None);self.origem_filtro.addItem('Automática','AUTOMATICA');self.origem_filtro.addItem('Manual','MANUAL');acoes_manuais.addWidget(self.origem_filtro)
        from .ferramentas_investigacao_ui import iniciar_local
        for nome,acao in [('Adicionar local',lambda:iniciar_local(self)),('A partir da seleção',lambda:iniciar_local(self,por_selecao=True)),('Editar local manual',lambda:iniciar_local(self,editar=True)),('Corredores / redes…',self.abrir_redes)]:
            b=QPushButton(nome);b.clicked.connect(lambda checked=False,acao=acao:acao());acoes_manuais.addWidget(b)
        self.origem_filtro.currentIndexChanged.connect(self.filtrar)
        self.mostrar_filtros=QPushButton('Filtros ▾');self.mostrar_filtros.setCheckable(True);self.mostrar_filtros.setChecked(True);layout.addWidget(self.mostrar_filtros)
        self.bloco_filtros=QWidget();filtros=QGridLayout(self.bloco_filtros);self.rolagem_filtros=QScrollArea();self.rolagem_filtros.setWidgetResizable(True);self.rolagem_filtros.setWidget(self.bloco_filtros);self.rolagem_filtros.setMaximumHeight(240);self.rolagem_filtros.setMinimumHeight(70);layout.addWidget(self.rolagem_filtros)
        self.mostrar_filtros.toggled.connect(self.rolagem_filtros.setVisible)
        self.filtros_ativos=QLabel();self.filtros_ativos.setWordWrap(True);layout.addWidget(self.filtros_ativos)
        self.categoria=QComboBox();self.categoria.addItem('Todos os tipos',None)
        numeros=contagens(self.casos)['categorias']
        for k,n in CATEGORIAS.items():self.categoria.addItem(f"{n} ({numeros.get(k,0)})",k)
        self.modo=QComboBox();self.modo.addItem('Estrutural',MODOS[0]);self.modo.addItem('Potencial · válvulas abertas',MODOS[1])
        self.modo.addItem('Estados do cenário · indisponível','ESTADOS_DO_CENARIO');self.modo.model().item(2).setEnabled(False)
        self.modo.setToolTip('Estrutural: relações cadastradas, inclusive inativos identificados. Válvulas abertas: hipótese que respeita Active Topology e restrições de dispositivos; não demonstra a operação real. Estados do cenário ainda não estão validados.')
        self.componente=QComboBox();self.regiao=QComboBox();self.revisao=QComboBox();self.fonte=QComboBox();self.prioridade=QComboBox();self.busca=QLineEdit()
        self.busca.setPlaceholderText('Label, ID cadastral, local ou elemento…')
        limpar=QPushButton('Limpar filtros');limpar.clicked.connect(self.limpar_filtros);filtros.addWidget(limpar,10,0,1,2)
        from .decisoes import SITUACOES
        self.revisao_topo=QComboBox();self.revisao_topo.addItem('Todas as revisões topológicas',None)
        for situacao in SITUACOES:self.revisao_topo.addItem(situacao,situacao)
        self.revisao_topo.addItem('Com anotações ou revisão','ANALISADOS')
        self.regiao.addItem('Todas as regiões',None)
        for n in sorted({a for c in self.casos for a in c['regioes']}):self.regiao.addItem(n,n)
        self.revisao.addItem('Todas as revisões espaciais',None)
        for n in sorted({c['revisao'] for c in self.casos}):self.revisao.addItem('Sem revisão por ocorrência' if n=='SEM_REVISAO_POR_OCORRENCIA' else n,n)
        for nome,valor in [('Fonte: qualquer',None),('Com reservatório/tanque',True),('Sem reservatório/tanque',False)]:self.fonte.addItem(nome,valor)
        self.prioridade.addItem('Qualquer prioridade',None)
        for n in ('Alta','Média','Baixa'):self.prioridade.addItem(n,n)
        for k,(nome,widget) in enumerate([('Tipo',self.categoria),('Perspectiva',self.modo),('Componente',self.componente),('Texto de região (legado)',self.regiao),('Revisão espacial',self.revisao),('Fonte cadastrada',self.fonte),('Prioridade',self.prioridade),('Elemento',self.busca),('Revisão topológica',self.revisao_topo)]):
            linha=(k//2)*2;col=k%2;filtros.addWidget(QLabel(nome),linha,col);filtros.addWidget(widget,linha+1,col)
        self.lista=QTableWidget(0,5);self.lista.setHorizontalHeaderLabels(['Ocorrência / diagnóstico','Prioridade','Acompanhamento','Regiões','Resultado da análise'])
        self.lista.setSelectionBehavior(QAbstractItemView.SelectRows);self.lista.setSelectionMode(QAbstractItemView.SingleSelection);self.lista.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.lista.setColumnWidth(1,70);self.lista.setColumnWidth(2,130);self.lista.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        self.investigacao=QSplitter(Qt.Vertical);self.area_trabalho=QSplitter(Qt.Horizontal);layout.addWidget(self.area_trabalho,1);self.area_trabalho.addWidget(self.investigacao);pagina_widget=QWidget();pv=QVBoxLayout(pagina_widget);pv.setContentsMargins(0,0,0,0);pv.addWidget(self.lista,1);nav=QHBoxLayout();self.pagina_anterior=QPushButton('Anterior');self.pagina_seguinte=QPushButton('Próxima página');self.contagem_pagina=QLabel();nav.addWidget(self.pagina_anterior);nav.addWidget(self.contagem_pagina);nav.addWidget(self.pagina_seguinte);pv.addLayout(nav);self.pagina_anterior.clicked.connect(lambda checked=False:self.mudar_pagina(-1));self.pagina_seguinte.clicked.connect(lambda checked=False:self.mudar_pagina(1));self.investigacao.addWidget(pagina_widget)
        self.lista.setMinimumHeight(75)
        self.cartao=QTextBrowser();self.cartao.setOpenExternalLinks(False);self.investigacao.addWidget(self.cartao)
        self.detalhes=QTreeWidget();self.detalhes.setHeaderLabels(['Detalhes expansíveis','Informação']);self.detalhes.setColumnWidth(0,180);self.detalhes.setWordWrap(True);self.investigacao.addWidget(self.detalhes)
        self.investigacao.setSizes([140,340,100]);self.investigacao.setStretchFactor(1,2)
        self.mostrar_detalhes=QCheckBox('Informações avançadas da ocorrência');self.mostrar_detalhes.toggled.connect(self.detalhes.setVisible);layout.addWidget(self.mostrar_detalhes);self.detalhes.hide()
        linha=QHBoxLayout();layout.addLayout(linha)
        for texto,acao in [('Analisar / anotar',self.anotar),('Próxima ocorrência',self.proxima)]:
            b=QPushButton(texto);b.clicked.connect(acao);linha.addWidget(b)
        linha=QHBoxLayout();layout.addLayout(linha)
        for texto,acao in [('Aproximar mapa',self.aproximar),('Destacar componentes',self.componentes),('Selecionar GIS original',self.origens)]:
            b=QPushButton(texto);b.clicked.connect(acao);linha.addWidget(b)
        linha=QHBoxLayout();layout.addLayout(linha)
        for texto,acao in [('Ajustar extensão dos elementos',self.extensao_elementos),('Remover destaques',self.mapa.limpar)]:
            b=QPushButton(texto);b.clicked.connect(acao);linha.addWidget(b)
        self.aviso=QLabel('Categorias são situações investigáveis, não erros confirmados. Contagens de categorias não são aditivas.');self.aviso.setWordWrap(True);layout.addWidget(self.aviso)
        self.legenda=QLabel('Azul: tubos · Verde: nós · Magenta: dispositivos · Ocre: limites\nLaranja tracejado: possível ligação geométrica, não cadastrada.');self.legenda.setWordWrap(True)
        self.exibir_legenda=QCheckBox('Exibir legenda dos destaques');self.exibir_legenda.setChecked(True);self.exibir_legenda.toggled.connect(self.legenda.setVisible);v.addWidget(self.exibir_legenda);v.addWidget(self.legenda)
        linha=QHBoxLayout();layout.addLayout(linha)
        for texto,acao in [('Inspeção e revisão espacial existente…',self.abrir_legado),('Inventário técnico avançado…',self.legado.abrir_componentes)]:
            b=QPushButton(texto);b.clicked.connect(acao);linha.addWidget(b)
        fontes=QWidget();fv=QVBoxLayout(fontes);self.tabs.addTab(fontes,'CONFIGURAÇÕES E FONTES')
        informacoes=QTreeWidget();informacoes.setHeaderLabels(['Fonte / parâmetro','Valor']);informacoes.setColumnWidth(0,230);fv.addWidget(informacoes)
        meta=self.pacote['resultado']['meta']
        for nome,valor in [('Base integrada',self.base),('Execução integrada',meta['uid']),('Auditoria geométrica',meta['geo']['execucao_uid']),('Topologia',meta['topologia']['execucao_uid']),('Cenário',meta['topologia'].get('cenario')),('CRS',meta['parametros']['crs']),('Distância investigativa (m)',meta['parametros']['distancia_investigativa_m'])]:QTreeWidgetItem(informacoes,[nome,str(valor)])
        QTreeWidgetItem(informacoes,['Configuração preservada','Esta tela não reprocessa, não muda agrupamentos e não altera as fontes.'])
        QTreeWidgetItem(informacoes,['Conclusões e propostas','Análise topológica própria, histórico anexado, propostas sob controle humano; não altera o WaterGEMS.'])
        from .form_decisao import AnaliseDecisao
        self.analise=AnaliseDecisao(self);self.tabs.insertTab(1,self.analise,'HISTÓRICO E PROPOSTAS')
        # O formulário formal legado permanece somente para APIs/histórico antigos.
        self.analise.tabs.setTabVisible(0,False);self.analise.tabs.setCurrentIndex(2);self.analise.salvar_fixo_decisao.hide()
        from .form_operacional import FormResultado,EditorFiltros
        self.resultado_analise=FormResultado(self);self.resultado_scroll=QScrollArea();self.resultado_scroll.setWidgetResizable(True);self.resultado_scroll.setWidget(self.resultado_analise);direita=QWidget();dv=QVBoxLayout(direita);dv.setContentsMargins(0,0,0,0);dv.addWidget(self.resultado_scroll,1);acoes_resultado=QHBoxLayout();acoes_resultado.addWidget(self.resultado_analise.salvar_botao);acoes_resultado.addWidget(self.resultado_analise.proxima_botao);dv.addLayout(acoes_resultado);self.area_trabalho.addWidget(direita);self.area_trabalho.setSizes([500,420])
        self.fila=QComboBox()
        for nome,codigo in [('Em aberto','EM_ABERTO'),('Todas as ocorrências','TODOS'),('Resolvidas','RESOLVIDAS'),('Pendentes','PENDENTES'),('Em análise','EM_ANALISE'),('Necessitam investigação adicional','CONFERENCIA'),('Reavaliação necessária','REAVALIACAO'),('Analisados (resultado)','ANALISADOS')]:self.fila.addItem(nome,codigo)
        filtros.addWidget(QLabel('Fila de trabalho'),11,0);filtros.addWidget(self.fila,11,1)
        self.resultado_filtro=QComboBox();self.resultado_filtro.addItem('Qualquer resultado',None)
        for resultado in op.RESULTADOS:self.resultado_filtro.addItem(resultado,resultado)
        filtros.addWidget(QLabel('Resultado da análise'),12,0);filtros.addWidget(self.resultado_filtro,12,1);self.resultado_filtro.currentIndexChanged.connect(self.filtrar_resultado)
        self.editor_filtros=EditorFiltros(self);filtros.addWidget(self.editor_filtros,13,0,1,2);self.editor_filtros.alterado.connect(self.filtrar);self.fila.currentIndexChanged.connect(self.filtrar)
        from auditoria_fronteiras.tabelas_consulta import TabelaConsulta
        self.elementos_tabela=TabelaConsulta(['Tipo','ID GIS','Camada GIS','Label WG','DomainElementID','Componente','Tipo de vínculo','Diagnóstico','Revisão','ID GIS bruto','Chave GIS','UID WG'])
        self.tabs.insertTab(1,self.elementos_tabela,'ELEMENTOS E VÍNCULOS')
        for c in (9,10,11):self.elementos_tabela.tabela.setColumnHidden(c,True)
        for nome,acao in [('Comparar com auditoria anterior…',self.comparar_versoes),('Exportar acompanhamento…',self.exportar_decisoes),('Gerar relatório de investigação…',self.abrir_relatorio)]:
            b=QPushButton(nome);b.clicked.connect(lambda checked=False,acao=acao:acao());fv.addWidget(b)
        for nome,acao in [('Excluir logicamente local manual',self.excluir_manual),('Restaurar local manual excluído…',self.restaurar_manual),('Recuperar locais manuais de outra investigação…',self.importar_manuais)]:
            b=QPushButton(nome);b.clicked.connect(lambda checked=False,acao=acao:acao());fv.addWidget(b)
        configurar=QPushButton('Abrir seleção de auditorias e fontes…');fv.addWidget(configurar)
        configurar.clicked.connect(self.configurar)
        self.modo.currentIndexChanged.connect(self.trocar_modo)
        for cb in (self.categoria,self.componente,self.regiao,self.revisao,self.revisao_topo,self.fonte,self.prioridade):cb.currentIndexChanged.connect(self.filtrar)
        self.busca.textChanged.connect(self.filtrar);self.lista.itemSelectionChanged.connect(self.selecionar)
        legado.revisao_salva.connect(self.revisao_atualizada)
        self.trocar_modo()
        from .representacoes_manuais import carregar_manuais
        carregar_manuais(self)
        for c in legado.projeto.mapLayers().values():
            if c.customProperty('integracao/uid')==meta['uid'] and c.customProperty('integracao/base')==str(Path(self.base).resolve()):
                callback=lambda *args,c=c:self.inversa(c)
                c.selectionChanged.connect(callback);self._conexoes.append((c,callback))
        from auditoria_fronteiras.ui_comum import adaptar_janela
        adaptar_janela(self)
        if self.atual:self.mostrar_filtros.setChecked(False)
        self.atualizar_recuperacao()

    def atualizar_recuperacao(self):
        from .recuperacao_analises import inventariar
        self._recuperadas=inventariar(self.base,self.pacote,self.casos);self.exibir_recuperacao()

    def exibir_recuperacao(self):
        if not hasattr(self,'_recuperadas'):return
        r=self._recuperadas;modo=self.modo.currentData();n=r['por_perspectiva'].get(modo,0)
        self.carregada.setText(f"INVESTIGAÇÃO CARREGADA · {r['locais_automaticos']} locais automáticos · {r['locais_manuais']} manuais · {r['analises']} análises salvas ({n} nesta perspectiva)\n{r['observacoes']} registros com observações · {r['conjuntos']} conjuntos. Resultados analisados podem estar ocultos pela fila de pendências; use Mostrar todas as análises salvas.")
        self.carregada.setToolTip(f"{r['nome']}\nInvestigação {r['ig_uid']}\nVersão topológica {r['topo_uid']}\nPerspectiva: {modo}\nFiltros: {self.filtros_ativos.text()}")

    def abrir_analises_salvas(self):
        from .recuperacao_analises import abrir_consulta
        return abrir_consulta(self)

    def mostrar_registro_salvo(self,uid,modo):
        if not self.resolver_formularios():return False
        self.modo.setCurrentIndex(self.modo.findData(modo));self.limpar_filtros();self.origem_filtro.setCurrentIndex(0)
        self.fila.setCurrentIndex(self.fila.findData('TODOS'));self.filtrar();self.selecionar_uid(uid);return bool(self.atual and self.atual['uid']==uid and self.modo.currentData()==modo)

    def consultar_rapido(self,n):
        if n in (2,3):self.abrir_analises_salvas()
        elif n==5:self.abrir_redes();self._redes_ui.recuperar()
        elif n in (1,4):
            if not self.resolver_formularios():return
            self.limpar_filtros();self.fila.setCurrentIndex(self.fila.findData('TODOS'));self.origem_filtro.setCurrentIndex(2 if n==4 else 0);self.filtrar()
        self.consulta_rapida.setCurrentIndex(0)

    def revisao_atualizada(self,*args):
        if not self._ativo:return
        self.casos=catalogar(self.pacote)
        from .locais_manuais import casos
        self.casos+=casos(self.base,self.pacote,self.indice_atributos)
        for c in self.casos:
            if self.revisao.findData(c['revisao'])<0:self.revisao.addItem(c['revisao'],c['revisao'])
        self.filtrar()

    def trocar_modo(self):
        if hasattr(self,'analise') and self.tem_edicoes() and not self.resolver_formularios():
            self.modo.blockSignals(True);self.modo.setCurrentIndex(self.modo.findData(self._modo_estavel));self.modo.blockSignals(False);return
        if self.modo.currentData() not in MODOS:
            self.modo.blockSignals(True);self.modo.setCurrentIndex(self.modo.findData(self._modo_estavel));self.modo.blockSignals(False);return
        self._modo_estavel=self.modo.currentData()
        self.componente.blockSignals(True);self.componente.clear();self.componente.addItem('Todos os componentes',None)
        modo=self.modo.currentData();nome='componentes' if modo==MODOS[0] else 'componentes_potenciais'
        for c in self.pacote['resultado'][nome]:self.componente.addItem(f"Componente {c['numero']} · {c['n_tubos']} tubos",c['uid'])
        self.componente.blockSignals(False)
        salvos=self._filtros_sessao.get(modo) or op.carregar_filtros(self.base,self.pacote,modo)
        if hasattr(self,'editor_filtros'):
            self.editor_filtros.carregar(salvos or {'operador':'E','condicoes':[]})
            for widget,key,default in [(self.fila,'fila','EM_ABERTO'),(self.resultado_filtro,'resultado',None)]:
                widget.blockSignals(True);widget.setCurrentIndex(max(0,widget.findData((salvos or {}).get(key,default))));widget.blockSignals(False)
        self.filtrar()
        modo=self.modo.currentData()
        for k,n in CATEGORIAS.items():self.categoria.setItemText(self.categoria.findData(k),f"{n} ({len(filtrar(self.casos,categoria=k,modo=modo))})")

    def filtrar(self):
        if not self._ativo:return
        self._inversos=None
        for c in self.casos:
            h=self._analises.get((c['uid'],self.modo.currentData()),{});sugestao,criterio=op.sugerir(c,self.indice_atributos);c['prioridade_sugerida']=h.get('prioridade_auto',sugestao);c['motivo_prioridade']=h.get('criterio_auto',criterio);c['prioridade_trabalho']=h.get('prioridade_trabalho')
        self._situacoes_acomp={c['uid']:ac.estado(self._acomp.get((c['uid'],self.modo.currentData())),c,self.pacote,self.modo.currentData(),self._contexto_acomp) for c in self.casos}
        novos=filtrar(self.casos,self.categoria.currentData(),self.componente.currentData(),self.regiao.currentData(),self.revisao.currentData(),self.modo.currentData(),self.busca.text(),self.fonte.currentData(),self.prioridade.currentData())
        if self.origem_filtro.currentData():novos=[c for c in novos if c.get('origem','AUTOMATICA')==self.origem_filtro.currentData()]
        from .decisoes import indice_revisoes,registros
        self._revisoes_topologicas=indice_revisoes(self.base,self.pacote['resultado']['meta']['uid'])
        rr=registros(self.base,self.pacote['resultado']['meta']['uid'],modo=self.modo.currentData());analisados={r['occ_uid'] for r in rr}|{u for u,m in self._revisoes_topologicas if m==self.modo.currentData()}
        if self.revisao_topo.currentData()=='ANALISADOS':novos=[c for c in novos if c['uid'] in analisados]
        elif self.revisao_topo.currentData():novos=[c for c in novos if self._revisoes_topologicas.get((c['uid'],self.modo.currentData()),{}).get('situacao','PENDENTE')==self.revisao_topo.currentData()]
        if hasattr(self,'editor_filtros'):
            novos,self._filtros_indeterminados=self.indice_atributos.filtrar(novos,self.editor_filtros.configuracao(),self.modo.currentData())
            escolhido=self.resultado_filtro.currentData()
            if escolhido:novos=[c for c in novos if self._analises.get((c['uid'],self.modo.currentData()),{}).get('resultado','PENDENTE')==escolhido]
            fila=self.fila.currentData()
            if fila=='EM_ABERTO':novos=[c for c in novos if self._situacoes_acomp[c['uid']]!='RESOLVIDO']
            elif fila=='RESOLVIDAS':novos=[c for c in novos if self._situacoes_acomp[c['uid']]=='RESOLVIDO']
            elif fila=='REAVALIACAO':novos=[c for c in novos if self._situacoes_acomp[c['uid']]=='REAVALIACAO_NECESSARIA']
            elif fila in ('PENDENTES','EM_ANALISE'):novos=[c for c in novos if self._situacoes_acomp[c['uid']]!='RESOLVIDO' and op.estado(self._analises.get((c['uid'],self.modo.currentData())))==('PENDENTE' if fila=='PENDENTES' else 'EM ANÁLISE')]
            elif fila=='ANALISADOS':novos=[c for c in novos if not op.pendente(self._analises.get((c['uid'],self.modo.currentData())))]
            elif fila=='CONFERENCIA':novos=[c for c in novos if self._situacoes_acomp[c['uid']]!='RESOLVIDO' and op.estado(self._analises.get((c['uid'],self.modo.currentData())))=='NECESSITA CONFERÊNCIA']
        if hasattr(self,'analise') and self.tem_edicoes() and self.atual and not any(c['uid']==self.atual['uid'] for c in novos):
            if not self.resolver_formularios():
                if self._filtros_estaveis:
                    for w,valor in self._filtros_estaveis:
                        w.blockSignals(True)
                        if isinstance(w,QComboBox):w.setCurrentIndex(w.findData(valor))
                        else:w.setText(valor)
                        w.blockSignals(False)
                if hasattr(self,'editor_filtros') and self._generico_estavel is not None:self.editor_filtros.carregar(self._generico_estavel)
                if hasattr(self,'fila'):self.fila.blockSignals(True);self.fila.setCurrentIndex(self._fila_estavel);self.fila.blockSignals(False)
                self.resultado_filtro.blockSignals(True);self.resultado_filtro.setCurrentIndex(self._resultado_estavel);self.resultado_filtro.blockSignals(False)
                return
        if hasattr(self,'editor_filtros'):self._resultado_estavel=self.resultado_filtro.currentIndex();self._generico_estavel=self.editor_filtros.configuracao();self._fila_estavel=self.fila.currentIndex()
        if hasattr(self,'editor_filtros'):
            self._filtros_sessao[self.modo.currentData()]=dict(self.editor_filtros.configuracao(),fila=self.fila.currentData(),resultado=self.resultado_filtro.currentData())
        novos.sort(key=lambda c:({'Alta':0,'Média':1,'Baixa':2}.get(c.get('prioridade_trabalho') or c.get('prioridade_sugerida',c['prioridade']),1),c['titulo'],c['uid']))
        self.visiveis=novos
        self._filtros_estaveis=[(w,w.currentData() if isinstance(w,QComboBox) else w.text()) for w in (self.categoria,self.componente,self.regiao,self.revisao,self.revisao_topo,self.fonte,self.prioridade,self.busca)]
        ativos=[w.currentText() for w in (self.categoria,self.componente,self.regiao,self.revisao,self.revisao_topo,self.fonte,self.prioridade) if w.currentIndex()>0]
        if self.busca.text():ativos.append('Elemento: '+self.busca.text())
        if hasattr(self,'editor_filtros') and self.editor_filtros.arvore.topLevelItem(0).childCount():ativos.append('Condições genéricas: '+str(self.editor_filtros.arvore.topLevelItem(0).childCount()))
        self.filtros_ativos.setText('Filtros: '+('; '.join(ativos) or 'nenhum')+' · '+self.modo.currentText())
        self.preencher()
        self.exibir_recuperacao()

    def filtrar_resultado(self):
        if self.resultado_filtro.currentData() in op.RESULTADOS[1:4]+(op.RESULTADOS[5],):
            self.fila.blockSignals(True);self.fila.setCurrentIndex(self.fila.findData('TODOS'));self.fila.blockSignals(False)
        self.filtrar()

    def limpar_filtros(self):
        if hasattr(self,'editor_filtros'):self.editor_filtros.carregar({'operador':'E','condicoes':[]})
        if hasattr(self,'fila'):self.fila.blockSignals(True);self.fila.setCurrentIndex(0);self.fila.blockSignals(False)
        if hasattr(self,'resultado_filtro'):self.resultado_filtro.blockSignals(True);self.resultado_filtro.setCurrentIndex(0);self.resultado_filtro.blockSignals(False)
        for w in (self.categoria,self.componente,self.regiao,self.revisao,self.revisao_topo,self.fonte,self.prioridade,self.busca):w.blockSignals(True)
        for w in (self.categoria,self.componente,self.regiao,self.revisao,self.revisao_topo,self.fonte,self.prioridade):w.setCurrentIndex(0)
        self.busca.clear()
        for w in (self.categoria,self.componente,self.regiao,self.revisao,self.revisao_topo,self.fonte,self.prioridade,self.busca):w.blockSignals(False)
        self.filtrar()

    def preencher(self,selecionar_primeiro=True,preservar=True):
        anterior=self.atual['uid'] if self.atual else None
        if preservar:self._pagina=next((i//self._tamanho_pagina for i,c in enumerate(self.visiveis) if c['uid']==anterior),0)
        self._pagina=max(0,min(self._pagina,max(0,(len(self.visiveis)-1)//self._tamanho_pagina)))
        offset=self._pagina*self._tamanho_pagina;self._itens_pagina=self.visiveis[offset:offset+self._tamanho_pagina]
        self.contagem_pagina.setText(f'{offset+1 if self.visiveis else 0}–{offset+len(self._itens_pagina)} de {len(self.visiveis)}');self.pagina_anterior.setEnabled(self._pagina>0);self.pagina_seguinte.setEnabled(offset+len(self._itens_pagina)<len(self.visiveis))
        self.lista.blockSignals(True);self.lista.setRowCount(len(self._itens_pagina))
        for n,c in enumerate(self._itens_pagina):
            situacao=self._revisoes_topologicas.get((c['uid'],self.modo.currentData()),{}).get('situacao','PENDENTE')
            h=self._analises.get((c['uid'],self.modo.currentData()));andamento=ac.ROTULOS[self._situacoes_acomp.get(c['uid'],'EM_ABERTO')]
            for col,texto in enumerate((c['titulo'],c.get('prioridade_trabalho') or c.get('prioridade_sugerida',c['prioridade']),andamento,'; '.join(c['regioes']),h['resultado'] if h else 'Sem resultado; histórico anterior disponível')):
                item=QTableWidgetItem(texto);item.setToolTip(texto);item.setData(Qt.UserRole,c['uid']);self.lista.setItem(n,col,item)
        self.lista.blockSignals(False)
        self.resumo.setText(f"{len(self.visiveis)} casos exibidos / {len(self.casos)} casos únicos. Prioridade é triagem. A lista mostra andamento topológico; a revisão espacial é preservada separadamente.")
        from .decisoes import registros,propostas,CONCLUSOES
        meta=self.pacote['resultado']['meta'];modo=self.modo.currentData();rs=registros(self.base,meta['uid'],modo=modo);hs=[r for (u,m),r in self._revisoes_topologicas.items() if m==modo]
        vistos={r['occ_uid'] for r in rs}|{r['occ_uid'] for r in hs};prelim={r['occ_uid'] for r in rs if r['tipo']=='PRELIMINAR'};confirmados=sum(r['conclusao'] in CONCLUSOES[1:6] for r in hs)
        self.execucao.setText(f"{meta.get('projeto') or meta.get('nome','Investigação')} · {self.modo.currentText()}\nGIS {meta['geo']['execucao_uid'][:8]} · WaterGEMS {meta['topologia']['execucao_uid'][:8]} · cenário {meta['topologia'].get('cenario')}")
        self.execucao.setToolTip(f"Investigação {meta['uid']}\nGIS {meta['geo']['execucao_uid']}\nWaterGEMS {meta['topologia']['execucao_uid']}\nVersões e fontes completas na aba CONFIGURAÇÕES E FONTES")
        self.resumo.setText(self.resumo.text()+f"\nHistórico legado: {len(vistos)} casos · anotações preliminares antigas: {len(prelim)} · conclusões antigas: {confirmados} · propostas: {len(propostas(self.base,meta['uid'],modo=modo))}. Categorias podem se sobrepor; não são contagens de erros comprovados.")
        if hasattr(self,'editor_filtros'):
            hs=list(self._analises.values());self.resumo.setText(self.resumo.text()+f"\nFila: {self.fila.currentText()} · {getattr(self,'_filtros_indeterminados',0)} casos indeterminados nos filtros (não incluídos). Resultados investigativos: {len([h for h in hs if h['modo']==modo])}.")
        texto_detalhado=self.resumo.text();self.resumo.setToolTip(texto_detalhado)
        resolvidas=sum(v=='RESOLVIDO' for v in self._situacoes_acomp.values());reavaliar=sum(v=='REAVALIACAO_NECESSARIA' for v in self._situacoes_acomp.values())
        self.resumo.setText(f"{len(self.visiveis)} de {len(self.casos)} ocorrências · {resolvidas} resolvidas · {len(self.casos)-resolvidas} em aberto ({reavaliar} para reavaliação)\nFila: {self.fila.currentText()} · {getattr(self,'_filtros_indeterminados',0)} indeterminadas nos filtros. RESOLVIDO encerra acompanhamento, sem alterar o resultado técnico.")
        self.atualizar_contexto()
        if self.visiveis and selecionar_primeiro:
            indice=next((i for i,c in enumerate(self._itens_pagina) if c['uid']==anterior),0);self.lista.selectRow(indice);self.selecionar()
        else:
            self.lista.clearSelection();self.lista.setCurrentCell(-1,-1);self.atual=None;self.detalhes.clear();self.cartao.clear();self.mapa.limpar()
            self.analise.carregar(None,self.modo.currentData())
            self.resultado_analise.carregar(None,self.modo.currentData())
            self.elementos_tabela.preencher([])
            self.aviso.setText('Escolha um dos casos relacionados.' if self.visiveis else 'Nenhum caso atende aos filtros. Isso não comprova ausência de problemas na rede.')

    def selecionar(self):
        row=self.lista.currentRow()
        if not self._ativo or row<0 or row>=len(self._itens_pagina):return
        destino=self._itens_pagina[row]
        if self.atual and (destino['uid'],self.modo.currentData())!=self.analise.chave and self.tem_edicoes() and not self.resolver_formularios():
            anterior=next((i for i,c in enumerate(self._itens_pagina) if c['uid']==self.atual['uid']),-1)
            self.lista.blockSignals(True);self.lista.selectRow(anterior);self.lista.blockSignals(False);return
        self.atual=self._itens_pagina[row];c=self.atual;self.detalhes.clear();modo=self.modo.currentData()
        self.analise.carregar(c,modo)
        self.resultado_analise.carregar(c,modo)
        from .inspecao_tabular import elementos_caso
        self.elementos_tabela.preencher(elementos_caso(self.pacote,c,modo,self.analise.head.get('situacao','PENDENTE') if self.analise.head else 'PENDENTE'))
        evidencias_filtro=[]
        if hasattr(self,'editor_filtros'):self.indice_atributos.avaliar(c,self.editor_filtros.configuracao(),modo,evidencias_filtro)
        self._evidencias_filtro=evidencias_filtro
        def grupo(titulo,textos,expandido=True):
            raiz=QTreeWidgetItem(self.detalhes,[titulo]);raiz.setExpanded(expandido)
            for texto in textos:QTreeWidgetItem(raiz,['',str(texto)])
            return raiz
        elementos=c['tubos_gis']+c['elementos']
        evidencias=c['evidencias'] or ['Dados insuficientes para uma interpretação inequívoca.']
        situacao=c['revisao']+' · revisão espacial do local' if c['local_uid'] else 'Não se aplica a um local geométrico único.'
        decisao=self.analise.head
        conclusao=(decisao['situacao']+' · '+decisao['conclusao']) if decisao else 'Conclusão técnica ainda não registrada; use ANÁLISE E DECISÃO.'
        h=self._analises.get((c['uid'],modo))
        if h:conclusao=op.estado(h)+' · '+h['resultado']+' · '+h['motivo']+' · '+h['observacao']
        elif not decisao:conclusao='Sem resultado investigativo. Escolha um resultado ou registre uma observação no formulário ao lado.'
        partes=[f"<h3>{escape(c['titulo'])}</h3>",f"<p>{escape(c['resumo'])}</p>"]
        resumo_elementos=(c['tubos_gis'][:4] if c['tubos_gis'] else c['elementos'][:4])
        tipos=self.pacote['topologia']['modelo']['elementos']
        if c['tubos_gis']:resumo_elementos.append(f"No modelo: {sum(tipos[i]['familia']=='LINK' for i in c['wg_ids'])} tubos; {sum(tipos[i]['familia']=='NO' for i in c['wg_ids'])} nós; {sum(tipos[i]['familia']=='DISPOSITIVO' for i in c['wg_ids'])} dispositivos. Lista completa no detalhe técnico.")
        for titulo,textos in [('Perspectiva selecionada',[c['perspectivas'][modo]['texto']]),
            ('Elementos envolvidos',resumo_elementos),
            ('Evidências principais',evidencias),('Localização',['; '.join(c['regioes']) or 'Área não determinada; use os destaques disponíveis.']),
            ('Próxima verificação',[c['proxima']]),('Situação da análise',['Espacial: '+situacao,'Topológica: '+conclusao])]:
            partes.append('<p><b>'+escape(titulo)+'</b><br>'+'<br>'.join(escape(str(t)) for t in textos)+'</p>')
        self.cartao.setHtml('<style>p {margin:5px 0;} h3 {margin:4px 0;}</style>'+''.join(partes));self.cartao.verticalScrollBar().setValue(0)
        linhas=[]
        for m in MODOS:
            p=c['perspectivas'][m];linhas.append(('Estrutural' if m==MODOS[0] else 'Todas válvulas abertas')+': '+p['texto']);linhas+=p['avisos']
        linhas.append('Active Topology e restrições de dispositivos podem alterar componentes. Sem evidência específica não atribuir a diferença a válvulas fechadas. Estados do cenário indisponíveis.')
        linhas.append('Conexão direta: elementos compartilham um nó cadastrado. Mesmo componente: existe um caminho no grafo, que pode passar por outros trechos e dispositivos. Nenhum desses resultados comprova a operação real.')
        grupo('Comparar perspectivas',linhas,False)
        if self._evidencias_filtro:
            grupo('Atributos avaliados pelos filtros',[str(e['camada'].get('nome') if e['camada'] else 'Fonte ausente')+' · '+ ' / '.join(e['campo'])+' = '+str(e['valor'])+' · atende: '+str(e['atende'])+' · '+str(e['proveniencia']) for e in self._evidencias_filtro],False)
        tecnico=grupo('Detalhamento técnico',[f"Ocorrência {c['uid']}",f"Origem {c['tipo']} / {c['chave']}",f"Elementos nativos: {c['wg_ids']}",f"Identidades GIS: {c['gis_uids']}",*elementos],False)
        for n,t in c['tecnico']:QTreeWidgetItem(tecnico,[n,t])
        for m,us in c['componentes'].items():QTreeWidgetItem(tecnico,[m,'; '.join(us)])
        pend=[self.detalhes.topLevelItem(i) for i in range(self.detalhes.topLevelItemCount())]
        while pend:
            item=pend.pop()
            for col in range(2):item.setToolTip(col,item.text(col))
            pend.extend(item.child(i) for i in range(item.childCount()))
        n=self.mapa.destacar(c,modo)
        # Contexto comprovado dos filtros, sem alterar o pacote/estilos aprovados.
        regionais=[]
        for area in self.indice_atributos.locais.get(c['local_uid'],{}):
            a=self.indice_atributos.areas[area];regionais.append(a['camada']+' · '+str(a.get('exibicao') if a.get('exibicao') is not None else a['chave'])+' · '+', '.join(sorted(self.indice_atributos.locais[c['local_uid']][area])))
            g=self.indice_atributos._contexto_geometrico.get(area)
            if g is not None and not (area.startswith('CTX:') and area[4:] in c['area_uids']):self.mapa.adicionar(g,'#887100',foco=False)
        if regionais:grupo('Regiões com relação identificada',regionais,False)
        n=len(self.mapa.geometrias)
        self.aviso.setText(f"{n} destaques temporários. Azul: tubos; verde: nós; magenta: dispositivos; ocre: limites; laranja tracejado: hipótese espacial, sem criar conexão. Aproximação é explícita." if n else 'Geometria ou CRS insuficiente; consulta técnica disponível, sem posicionamento inventado.')

    def configurar(self):
        if not self.resolver_alteracoes():return
        from .interface_integracao import abrir_integracao
        abrir_integracao()

    def componentes(self):
        if self.atual:self.mapa.destacar(self.atual,self.modo.currentData(),True)

    def aproximar(self):self.aviso.setText(self.mapa.aproximar())
    def extensao_elementos(self):
        self.mapa.centro_local=None;self.aviso.setText(self.mapa.aproximar())

    def origens(self):
        if self.atual:self.aviso.setText(self.mapa.selecionar_gis(self.atual))

    def abrir_legado(self):
        if self.atual and self.atual['local_uid']:
            self.legado.locais.setCurrentIndex(self.legado.locais.findData(self.atual['local_uid']));self.legado.show();self.legado.raise_()
        else:self.aviso.setText('Este caso não tem um local geométrico único. Use Anotar / decidir para registrar a investigação topológica da ocorrência.')

    def anotar(self):
        if self.atual:self.tabs.setCurrentIndex(0);self.resultado_analise.observacoes.setFocus()

    def mudar_pagina(self,delta):
        if not self.resolver_formularios():return
        self._pagina+=delta;self.preencher(preservar=False)

    def selecionar_uid(self,uid):
        i=next((i for i,c in enumerate(self.visiveis) if c['uid']==uid),None)
        if i is None:return
        self._pagina=i//self._tamanho_pagina;self.preencher(preservar=False);self.lista.selectRow(i%self._tamanho_pagina)

    def proxima(self):
        if self.lista.rowCount()==0:return
        linha=self.lista.currentRow()+1
        if linha>=self.lista.rowCount():
            if (self._pagina+1)*self._tamanho_pagina<len(self.visiveis):self.mudar_pagina(1)
            else:self.aviso.setText('Fim da lista filtrada. Ajuste os filtros para consultar outros casos.')
            return
        self.lista.selectRow(linha)

    def inversa(self,camada):
        if not self._ativo or self._sincronizando:return
        if self.tem_edicoes() and not self.resolver_formularios():return
        fs=camada.selectedFeatures()
        if len(fs)!=1:return
        f=fs[0];campos=camada.fields().names();candidatos=[]
        if 'LOC_UID' in campos:candidatos=[c for c in self.casos if c['local_uid']==f['LOC_UID']]
        elif 'WG_ID' in campos:
            try:i=int(f['WG_ID'])
            except (TypeError,ValueError):return
            candidatos=[c for c in self.casos if i in c['wg_ids']]
        elif 'GIS_UID' in campos:candidatos=[c for c in self.casos if f['GIS_UID'] in c['gis_uids']]
        elif 'EVT_UID' in campos:
            us={v['local_uid'] for v in self.pacote['dossie']['local_evento'] if v['evento_uid']==f['EVT_UID']}
            candidatos=[c for c in self.casos if c['local_uid'] in us]
        if not candidatos:
            self.aviso.setText('O elemento selecionado não corresponde a uma ocorrência investigável deste catálogo.');return
        self.visiveis=candidatos;self.preencher(selecionar_primeiro=len(candidatos)==1)
        self.resumo.setText(f'Seleção do mapa: {len(candidatos)} caso(s) relacionado(s). Edite ou limpe os filtros para voltar à lista filtrada.')
        self.aviso.setText('Seleção do mapa: caso identificado inequivocamente.' if len(candidatos)==1 else f'{len(candidatos)} casos relacionados à seleção. Escolha um caso; nenhuma correspondência é presumida.')

    def desativar(self):
        relatorio=getattr(self,'_relatorio_ui',None)
        if relatorio is not None and not sip.isdeleted(relatorio):relatorio.close()
        consulta=getattr(self,'_consulta_analises',None)
        if consulta is not None and not sip.isdeleted(consulta):consulta.close()
        if self._ferramenta_manual and self.legado.canvas:
            ferramenta,anterior=self._ferramenta_manual
            if self.legado.canvas.mapTool() is ferramenta:
                self.legado.canvas.setMapTool(anterior) if anterior else self.legado.canvas.unsetMapTool(ferramenta)
            self._ferramenta_manual=None
        if self._redes_ui:self._redes_ui.close()
        self._ativo=False;self.mapa.fechar()
        if self._iface and self._bloqueador:
            self._iface.unregisterApplicationExitBlocker(self._bloqueador);self._bloqueador.registrado=False;self._bloqueador=None
        for c,fn in self._conexoes:
            if not sip.isdeleted(c):
                try:c.selectionChanged.disconnect(fn)
                except (TypeError,RuntimeError):pass
        self._conexoes=[];self.legado.desativar();self.hide()

    def recarregar_manuais(self,uid=None):
        from .locais_manuais import casos
        from .representacoes_manuais import carregar_manuais
        self.indice_atributos._cache.clear();self.casos=[c for c in self.casos if c['tipo']!='MANUAL']+casos(self.base,self.pacote,self.indice_atributos)
        self.filtrar();carregar_manuais(self)
        if uid:
            caso=next((c for c in self.casos if c.get('manual_uid')==uid),None)
            if caso:self.selecionar_uid(caso['uid'])
        self.atualizar_recuperacao()

    def abrir_redes(self):
        from .ferramentas_investigacao_ui import DialogoRedes
        if self._redes_ui is not None and not sip.isdeleted(self._redes_ui) and self._redes_ui.modo!=self.modo.currentData():
            if not self._redes_ui.close():return
            self._redes_ui.deleteLater();self._redes_ui=None
        if self._redes_ui is None or sip.isdeleted(self._redes_ui):self._redes_ui=DialogoRedes(self)
        self._redes_ui.show();self._redes_ui.raise_();self._redes_ui.activateWindow()

    def excluir_manual(self):
        if not self.atual or self.atual['tipo']!='MANUAL':return
        if not self.resolver_formularios():return
        if QMessageBox.question(self,'Excluir local manual','Excluir da lista ativa preservando todos os vínculos e o histórico?',QMessageBox.Yes|QMessageBox.Cancel)!=QMessageBox.Yes:return
        from .conjuntos_investigacao import salvar
        r=self.atual['manual_registro'];salvar(self.base,self.pacote,'LOCAL_MANUAL',r['dados'],r['vinculos'],uid=r['obj_uid'],esperada=r['uid'],modo=r['modo'],excluido=True);self.recarregar_manuais()

    def importar_manuais(self):
        if not self.resolver_formularios():return
        from .conjuntos_investigacao import importar
        fonte,_=QFileDialog.getOpenFileName(self,'Recuperar locais manuais','','GeoPackage (*.gpkg)')
        if fonte:
            try:
                from .saidas_integracao import reabrir
                pacote=reabrir(fonte);r=importar(fonte,pacote,self.base,self.pacote);self.recarregar_manuais();QMessageBox.information(self,'Recuperação conservadora',str(r)+'\nResultados anteriores não foram transferidos; consulte o histórico na origem.')
            except Exception as e:QMessageBox.warning(self,'Recuperação não aplicada',str(e))

    def restaurar_manual(self):
        if not self.resolver_formularios():return
        from .conjuntos_investigacao import atuais,salvar
        from qgis.PyQt.QtWidgets import QInputDialog
        rs=[r for r in atuais(self.base,self.pacote,'LOCAL_MANUAL',True) if r['excluido']]
        if not rs:QMessageBox.information(self,'Restaurar','Não há locais manuais excluídos nesta investigação.');return
        nomes=[r['dados'].get('titulo','Local manual')+' · '+r['obj_uid'][:8] for r in rs];nome,ok=QInputDialog.getItem(self,'Restaurar local','Escolha um local',nomes,0,False)
        if ok:
            r=rs[nomes.index(nome)]
            try:salvar(self.base,self.pacote,'LOCAL_MANUAL',r['dados'],r['vinculos'],uid=r['obj_uid'],esperada=r['uid'],modo=r['modo']);self.recarregar_manuais(r['obj_uid'])
            except Exception as e:QMessageBox.warning(self,'Restauração não aplicada',str(e))

    def closeEvent(self,event):
        if not self.resolver_alteracoes():event.ignore();return
        if not self.legado.close():event.ignore();return
        self.desativar();event.accept()

    def tem_edicoes(self):
        return self.analise.tem_edicoes() or (hasattr(self,'resultado_analise') and self.resultado_analise.tem_edicoes()) or (self._redes_ui is not None and not sip.isdeleted(self._redes_ui) and self._redes_ui.tem_edicoes())

    def resolver_formularios(self):
        if self._redes_ui is not None and not sip.isdeleted(self._redes_ui) and not self._redes_ui.resolver():return False
        if hasattr(self,'resultado_analise') and not self.resultado_analise.resolver_edicoes():return False
        return self.analise.resolver_edicoes()

    def resolver_alteracoes(self):
        r=getattr(self,'_relatorio_ui',None)
        if r is not None and not sip.isdeleted(r) and r._ocupado:return False
        if not self.resolver_formularios():return False
        if self.legado.tem_edicoes():
            if not self.legado.resolver_edicoes():return False
            # O formulário espacial legado retorna Descartar sem repor valores.
            # Consuma essa decisão uma vez, antes de closeEvent/unload.
            if self.legado.tem_edicoes():self.legado.atualizar()
        return True

    @acompanhada('Comparando versões da investigação integrada')
    def comparar_versoes(self):
        if not self.resolver_alteracoes():return
        caminho,_=QFileDialog.getOpenFileName(self,'Auditoria integrada anterior','','GeoPackage (*.gpkg)')
        if not caminho:return False
        try:
            from .comparacao_decisoes import comparar,salvar_comparacao,selecionar_integracao
            anterior=selecionar_integracao(caminho,self)
            if anterior is None:return
            r=comparar(anterior,self.pacote,self.modo.currentData())
            from .locais_manuais import casos as manuais
            anteriores=catalogar(anterior)+manuais(caminho,anterior);ar=ac.comparar(caminho,anterior,anteriores,self.pacote,self.casos,self.modo.currentData());r['acompanhamento']=ar
            resumo='Acompanhamento: '+str(ar['contagens'])+'\nEquivalentes preservam a resolução; alterações exigem reavaliação.\n'+'\n'.join(f'{k}: {v}' for k,v in r['contagens'].items())+'\nNão transfere conclusões; ausência não comprova correção.'
            if QMessageBox.question(self,'Registrar comparação de versões',resumo,QMessageBox.Save|QMessageBox.Cancel,QMessageBox.Cancel)==QMessageBox.Save:
                salvar_comparacao(self.base,self.pacote,r,caminho);ac.aplicar_comparacao(self.base,self.pacote,self.casos,self.modo.currentData(),ar);self._acomp=ac.indice(self.base,self.pacote);self.filtrar();QMessageBox.information(self,'Comparação registrada',resumo)
        except Exception as e:falha(self,e);QMessageBox.warning(self,'Comparação não registrada',str(e))

    def exportar_decisoes(self):
        if not self.resolver_alteracoes():return
        from .exportacao_decisoes import DialogExportarDecisoes
        self._exportacao=DialogExportarDecisoes(self);self._exportacao.exec_()


    def atualizar_contexto(self):
        meta=self.pacote['resultado']['meta'];pendente=hasattr(self,'resultado_analise') and self.resultado_analise.tem_edicoes()
        self.execucao.setText(f"{getattr(self,'nome_exibicao',None) or meta.get('nome','Investigação')} · {meta.get('projeto','')} · Integrada V{meta.get('versao',1)} · {self.modo.currentText()}\nWaterGEMS {meta['topologia']['execucao_uid'][:12]} · Cenário {meta['topologia'].get('cenario')} · {'Alterações não salvas' if pendente else 'Registros persistidos'}")

    def abrir_relatorio(self):
        from .relatorio_ui import RelatorioDialog
        if not self._ativo:return
        if getattr(self,'_relatorio_ui',None) is None or sip.isdeleted(self._relatorio_ui):self._relatorio_ui=RelatorioDialog(self)
        if getattr(self,'_wna_janelas',None):self._wna_janelas.registrar('relatorio_investigacao',self._relatorio_ui,'relatório de investigação')
        self._relatorio_ui.show();self._relatorio_ui.raise_();self._relatorio_ui.activateWindow()


def abrir_diagnosticos(pacote,base,projeto=None,parent=None,canvas=None,gerenciar_saida=True):
    from .painel_integrado import abrir_painel
    legado=abrir_painel(pacote,base,projeto,parent,canvas);legado.hide()
    painel=PainelDiagnosticos(legado,parent)
    painel.setObjectName('WNA_Diagnosticos_Integrados')
    if canvas is not None:
        try:
            from qgis.utils import iface
            if iface:
                iface.addDockWidget(Qt.RightDockWidgetArea,painel);painel.setMinimumWidth(0)
                painel._iface=iface
                if gerenciar_saida:
                    from qgis.gui import QgsApplicationExitBlockerInterface
                    import weakref
                    referencia=weakref.ref(painel)
                    class Bloqueador(QgsApplicationExitBlockerInterface):
                        verificando=False
                        registrado=True
                        def allowExit(self):
                            p=referencia()
                            if p is None or sip.isdeleted(p) or not p._ativo:return True
                            if self.verificando:return False
                            self.verificando=True
                            try:return bool(p.resolver_alteracoes())
                            except Exception:
                                import traceback
                                from qgis.core import QgsMessageLog,Qgis
                                QgsMessageLog.logMessage(traceback.format_exc(),'Water Network Auditor',Qgis.Critical)
                                QMessageBox.warning(p,'Encerramento adiado','Não foi possível resolver as alterações. O QGIS permanecerá aberto; salve seu trabalho e consulte o painel de mensagens Water Network Auditor.');return False
                            finally:self.verificando=False
                    painel._bloqueador=Bloqueador();iface.registerApplicationExitBlocker(painel._bloqueador)
                    bloqueador=painel._bloqueador
                    def destruido(*args):
                        if bloqueador.registrado:
                            bloqueador.registrado=False
                            try:iface.unregisterApplicationExitBlocker(bloqueador)
                            except RuntimeError:pass
                    painel.destroyed.connect(destruido)
        except ImportError:pass
    painel.show()
    if painel._iface and not painel._iface.mainWindow().property('wna/dock_dimensionado'):
        principal=painel._iface.mainWindow();principal.resizeDocks([painel],[max(280,int(principal.width()*.5))],Qt.Horizontal);principal.setProperty('wna/dock_dimensionado',True)
    return painel
