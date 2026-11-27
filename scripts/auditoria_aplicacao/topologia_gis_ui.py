"""Fluxo QGIS para construir, revisar e recuperar topologias GIS."""

import json
from pathlib import Path
from uuid import uuid4

from qgis.PyQt.QtCore import QTimer, Qt
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QAbstractItemView,
    QInputDialog, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QScrollArea, QVBoxLayout, QWidget)
from qgis.core import QgsCoordinateReferenceSystem, QgsGeometry, QgsPointXY, QgsProject
from qgis.gui import QgsProjectionSelectionWidget

from . import persistencia_grafo_gis as pg
from .complementos_gis_ui import EditarComplemento
from . import hipoteses_gis as hg
from .entradas_grafo_gis import ORIGENS, ler, preparar
from .executar_grafo_gis import executar, _declaracoes_existentes
from .grafo_gis import ROTULOS
from .investigacao_gis import geometria
from .modelo_gis import revisoes, identificar, descrever
from .modelo_gis_ui import aviso, botao, expansivel, formulario
from .mapa_topologia_gis import IndiceSelecao, MapaTopologiaGIS, pontos_portas
from .tabelas_topologia_gis import TabelaRelacoes, TabelaGIS, ACOMPANHAMENTO, ESTADO_COMPONENTE
from .topologia_gis_hipoteses_ui import HipotesesGIS
from .topologia_gis_mapa_ui import MapaGIS
from .topologia_gis_relacoes_ui import RelacoesGIS, CANDIDATAS
from . import prioridade_cruzamentos as cruzamentos
from .navegacao_cartografica import acao_disponivel, navegar_registros


def _itens(lista):
    return [lista.item(i) for i in range(lista.count())]


def _marcados(lista):
    return [i.data(Qt.UserRole) for i in _itens(lista) if i.checkState()==Qt.Checked]


def _inserir(lista, titulo, uid, marcado=None):
    item=QListWidgetItem(titulo)
    item.setData(Qt.UserRole,uid)
    if marcado is not None:item.setCheckState(Qt.Checked if marcado else Qt.Unchecked)
    lista.addItem(item)
    return item


class TopologiaGIS(QScrollArea,HipotesesGIS,MapaGIS,RelacoesGIS):
    def __init__(self, central):
        super().__init__(central)
        self.central=central
        self.app=central.app
        self.uid_projeto=None
        self.dados=None
        self.registros={}
        self._historicas=[]
        self._por_revisao={}
        self._hip_ativa=None
        self._pinos={}
        self._edicao_limpa=None
        self._resultado_historico=False
        self._editor=None
        self._finalizar_ferramenta=None
        self._ordem_coluna=None
        self._filtro_relacao=None
        self.mapa_gis=MapaTopologiaGIS()
        self._timer_mapa=QTimer(self)
        self._timer_mapa.setSingleShot(True)
        self._timer_mapa.timeout.connect(self._atualizar_mapa)
        self._ferramenta=None
        self._lista_resultados=[]
        self._pagina=0
        self.setWidgetResizable(True)
        w=QWidget()
        self.setWidget(w)
        v=QVBoxLayout(w)
        botao(v,'‹ Investigar minha rede',self.voltar)
        self.retorno_estrutura_b=botao(v,'‹ Escolher análise para redes estruturantes',
                                      lambda:self.central.abrir_estrutura())
        self.retorno_estrutura_b.hide()
        self.status=aviso('Topologia GIS · conectividade estrutural')
        v.addWidget(self.status)
        self.config_b, cfg=expansivel(v,'Configuração da análise')
        self.config_b.setChecked(True)
        self.nome=QLineEdit('Conectividade GIS')
        f=formulario(cfg)
        f.addRow('Nome da análise de conectividade',self.nome)
        self.crs=QgsProjectionSelectionWidget()
        f.addRow('CRS projetado em metros',self.crs)
        self.tolerancia=QDoubleSpinBox()
        self.tolerancia.setRange(0,100)
        self.tolerancia.setDecimals(3)
        self.tolerancia.setValue(.20)
        self.tolerancia.setSuffix(' m')
        self.tolerancia.setToolTip('Distância em metros para procurar pontos de ligação próximos.')
        f.addRow('Tolerância de conexão',self.tolerancia)
        self.aproximadas=QCheckBox('Inferir união de pontas próximas quando inequívoca')
        self.aproximadas.setToolTip('Une extremidades inequívocas dentro da tolerância. Ligações em T exigem revisão explícita.')
        cfg.addWidget(self.aproximadas)
        self.limite=QDoubleSpinBox()
        self.limite.setRange(1,100000)
        self.limite.setValue(200)
        self.limite.setSuffix(' mm')
        f.addRow('Diâmetro mínimo para destacar redes principais (mm)',self.limite)
        self.limite.setToolTip('Critério de diagnóstico e prioridade. A topologia usa todos os trechos do escopo. A classificação de adução é um critério cadastral separado.')
        self.estrategia=aviso()
        cfg.addWidget(self.estrategia)
        cfg.addWidget(aviso('Redes consideradas. Marque as fontes conforme as classificações do Modelo GIS.'))
        self.redes=QListWidget()
        self.redes.setMaximumHeight(120)
        cfg.addWidget(self.redes)
        navegar_registros(self.redes,self._navegar_fonte_gis,limpar=self.central.mapa.limpar)
        self.redes.itemChanged.connect(self._configuracao_alterada)
        self.crs.crsChanged.connect(self._configuracao_alterada)
        self.tolerancia.valueChanged.connect(self._configuracao_alterada)
        self.limite.valueChanged.connect(self._configuracao_alterada)
        self.aproximadas.toggled.connect(self._configuracao_alterada)
        self.unidades={}
        self.unidade=QComboBox()
        for k,n in [(None,'Não confirmada'),('mm','mm'),('cm','cm'),('m','m'),('pol','polegadas')]:
            self.unidade.addItem(n,k)
        f2=formulario(cfg)
        f2.addRow('Unidade do diâmetro da fonte selecionada',self.unidade)
        self.unidade.activated.connect(self.salvar_unidade)
        self.redes.currentItemChanged.connect(self.mostrar_unidade)
        self.tipo_escopo=QComboBox()
        for n,k in [('Todos os tipos',''),('Adução','ADUCAO'),('Distribuição','DISTRIBUICAO'),
                    ('Complementar','COMPLEMENTAR'),('Outra','OUTRA')]:
            self.tipo_escopo.addItem(n,k)
        self.tipo_escopo.activated.connect(self.selecionar_tipo)
        f2.addRow('Marcar redes por tipo',self.tipo_escopo)
        self.orig_b, orig=expansivel(v,'Origens de abastecimento')
        orig.addWidget(aviso('Marque as origens que participarão da hipótese em edição. Cada origem precisa de pontos de conexão válidos.'))
        self.participantes=TabelaRelacoes()
        self.participantes.colunas(('Nome','Tipo','Natureza','Tubulações','Revisão','Acompanhamento','Hipóteses'))
        self.participantes.horizontalHeaderItem(0).setToolTip('Marque para considerar nesta hipótese')
        self.participantes.setMaximumHeight(145)
        self.participantes.itemChanged.connect(self.alterou_participacao)
        self.participantes.currentCellChanged.connect(lambda *_:self.detalhar_relacao())
        orig.addWidget(self.participantes)
        navegar_registros(self.participantes,self._navegar_relacao,self._menu_relacao,self.central.mapa.limpar)
        self.mostrar_excluidos=QCheckBox('Mostrar complementos excluídos')
        self.mostrar_excluidos.toggled.connect(lambda _:self.atualizar_complementos())
        orig.addWidget(self.mostrar_excluidos)
        self.relacao_info=aviso()
        orig.addWidget(self.relacao_info)
        atalhos=QHBoxLayout();orig.addLayout(atalhos)
        self.destacar_relacao_b=botao(atalhos,'Destacar no mapa',lambda:self.destacar_relacao())
        self.aproximar_relacao_b=botao(atalhos,'Aproximar origem',lambda:self.destacar_relacao(aproximar=True))
        self.origem_gis_b=botao(orig,'Adicionar origem cadastrada…',lambda:self.editar('ORIGEM'))
        self.origem_mapa_b=botao(orig,'Adicionar origem no mapa',lambda:self.capturar())
        self.editar_relacao_b=botao(orig,'Editar elemento selecionado…',self.editar_selecionado)
        self.reposicionar_b=botao(orig,'Reposicionar origem complementar selecionada',self.reposicionar)
        _, mais_rel=expansivel(orig,'Opções do elemento')
        self.alternar_elemento_b=botao(mais_rel,'Ativar ou desativar no cadastro…',self.alternar_elemento)
        self.adotar_revisao_b=botao(mais_rel,'Usar revisão mais recente nesta hipótese',self.adotar_revisao_atual)
        self.historico_elemento_b=botao(orig,'Histórico do elemento selecionado',self.historico_elemento)
        self.relocalizar_b=botao(orig,'Localizar GeoPackage de complementos…',self.relocalizar_complementos)
        self.relocalizar_b.hide()
        self.iniciar_tabela_conexoes(v)
        self.hipoteses=QComboBox()
        self.hipoteses_b, hip=expansivel(v,'Hipóteses e reexecução')
        formulario(hip).addRow('Hipótese e revisão',self.hipoteses)
        self.hipotese_info=aviso()
        hip.addWidget(self.hipotese_info)
        self.hipoteses.activated.connect(self.aplicar_hipotese)
        hip.addWidget(aviso('Uma hipótese guarda a configuração. Cada execução salva uma fotografia calculada dessa revisão.'))
        self.salvar_hip_b=botao(hip,'Salvar revisão da hipótese…',lambda:self.salvar_hipotese())
        self.nova_hip_b=botao(hip,'Salvar como nova hipótese…',lambda:self.salvar_hipotese(nova=True))
        self.reexecutar_b=botao(hip,'Reexecutar análise com estas alterações…',self.reexecutar)
        self.comparar_b=botao(hip,'Comparar duas execuções…',self.comparar)
        botao(hip,'Execuções desta hipótese…',self.abrir_execucoes_hipotese)
        self.recuperar_rascunho_b=botao(hip,'Recuperar rascunho de hipótese…',self.recuperar_rascunho)
        botao(v,'Abrir análise de conectividade salva…',lambda:self.central.listar_execucoes_salvas())
        self.executar_b=botao(v,'Executar e salvar análise de conectividade',self.executar_configuracao_atual)
        self.executar_b.setObjectName('Principal')
        self.resumo=aviso()
        v.addWidget(self.resumo)
        self.categoria=QComboBox()
        self.categoria.currentIndexChanged.connect(self.mudar_resultados)
        self.ordem=QComboBox()
        self.ordem.setToolTip('Prioridade: primeiro os sem origem alcançável, depois comprimento, diâmetro, candidatas e quantidade de trechos.')
        for chave in ('Prioridade', 'Comprimento', 'Diâmetro', 'Categoria'):
            self.ordem.addItem(chave)
        self.ordem.activated.connect(self.mudar_resultados)
        f3=formulario(v)
        f3.addRow('Categoria',self.categoria)
        f3.addRow('Ordenar',self.ordem)
        self.filtro_cruzamentos=QComboBox()
        for k,nome in cruzamentos.FILTROS.items():
            self.filtro_cruzamentos.addItem(nome,k)
        self.filtro_cruzamentos.currentIndexChanged.connect(self.mudar_resultados)
        self.limiar_cruzamentos=QDoubleSpinBox()
        self.limiar_cruzamentos.setRange(0,100)
        self.limiar_cruzamentos.setDecimals(3)
        self.limiar_cruzamentos.setSuffix(' m')
        self.limiar_cruzamentos.setToolTip('Distância ao longo do Pipe. Altera a prioridade sem recalcular ou modificar a hipótese.')
        self.limiar_cruzamentos.setKeyboardTracking(False)
        self.limiar_cruzamentos.valueChanged.connect(self.reclassificar_cruzamentos)
        f3.addRow('Revisão de cruzamentos',self.filtro_cruzamentos)
        f3.addRow('Distância à extremidade',self.limiar_cruzamentos)
        self._campos_cruzamentos=(self.filtro_cruzamentos,self.limiar_cruzamentos,
                                 f3.labelForField(self.filtro_cruzamentos),f3.labelForField(self.limiar_cruzamentos))
        for campo in self._campos_cruzamentos:campo.hide()
        self._prioridade_cruzamentos={}
        self.busca=QLineEdit()
        self.busca.setPlaceholderText('Filtrar por ID, situação, setor ou zona')
        self.busca.editingFinished.connect(self.mudar_resultados)
        v.addWidget(self.busca)
        self.resultados=TabelaGIS()
        self.resultados.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.resultados.setMaximumHeight(210)
        self.resultados.currentCellChanged.connect(self.detalhar)
        self.resultados.horizontalHeader().sectionClicked.connect(self.ordenar_resultados)
        v.addWidget(self.resultados)
        navegar_registros(self.resultados,self._navegar_resultado,self._menu_resultado,self.central.mapa.limpar,
                          self._enquadrar_varios)
        nav=QHBoxLayout();v.addLayout(nav)
        self.pagina_anterior_b=botao(nav,'‹ Anterior',lambda:self.paginar(-1))
        self.pagina_info=aviso()
        nav.addWidget(self.pagina_info,1)
        self.proxima_pagina_b=botao(nav,'Próxima ›',lambda:self.paginar(1))
        self.detalhes=aviso()
        v.addWidget(self.detalhes)
        _, mapa=expansivel(v,'Mapa e legenda')
        mapa.addWidget(aviso('Use a árvore de camadas para ajustar a visibilidade. Fontes são triângulos, pentágonos ou losangos. Círculo verde indica conexão confirmada. Contornos tracejados representam hipóteses ou propostas. As linhas auxiliares representam vínculos topológicos.'))
        self.consultar_mapa_b=botao(mapa,'Consultar elemento no mapa',lambda:self.consultar_mapa())
        self.revisar_mapa_b=botao(mapa,'Revisar conexão pelo mapa',lambda:self.consultar_mapa(revisar=True))
        self.destacar_b=botao(mapa,'Destacar seleção',self.destacar)
        self.aproximar_b=botao(mapa,'Aproximar seleção',lambda:self.destacar(aproximar=True))
        _, decisoes=expansivel(v,'Decisões e acompanhamento')
        self.acompanhamento=QComboBox()
        for k,n in ACOMPANHAMENTO.items():self.acompanhamento.addItem(n,k)
        formulario(decisoes).addRow('Situação',self.acompanhamento)
        self.anotar_b=botao(decisoes,'Salvar situação e observação…',self.anotar)
        self.revisar_b=botao(decisoes,'Revisar conexão selecionada…',self.revisar_conexao)
        self.historico_b, historico=expansivel(v,'Histórico')
        self.historico_resultado_b=botao(historico,'Histórico do resultado selecionado',self.historico_resultado)
        _, av=expansivel(v,'Exportações')
        self.exportar_gpkg_b=botao(av,'Exportar GeoPackage e tabelas…',lambda:self.exportar('GPKG'))
        self.exportar_shp_b=botao(av,'Exportar Shapefile e tabelas…',lambda:self.exportar('ESRI Shapefile'))
        botao(av,'Prévia de Pipes e Junctions em GeoPackage…',self.exportar_previa)
        self.historico=QPlainTextEdit()
        self.historico.setReadOnly(True)
        self.historico.setMaximumHeight(160)
        self.historico.hide()
        historico.addWidget(self.historico)
        self.comparacao=TabelaGIS()
        self.comparacao.colunas(('Diferença','Antes','Depois','Trechos'))
        self.comparacao.setMaximumHeight(150)
        self.comparacao.currentCellChanged.connect(self.detalhar_diferenca)
        navegar_registros(self.comparacao,lambda i,a:self.destacar_diferenca(i.row(),aproximar=a),
                          limpar=self.central.mapa.limpar)
        hip.addWidget(self.comparacao)
        self.comparacao.hide()
        self._atualizar_acoes()

    def _atualizar_acoes(self):
        r=self._registro_selecionado()
        resultado=self._selecionado()
        falta_relacao='' if r else 'Selecione uma fonte ou conexão na tabela.'
        falta_resultado='' if resultado else ('Selecione um resultado na tabela.' if self.dados else
                                               'Execute uma análise ou abra um resultado salvo.')
        redes='' if self._redes_marcadas() else 'Marque pelo menos uma fonte de tubulações.'
        cadastrado='' if r and r['tipo']=='ORIGEM' and pg.complemento_editavel(r) else 'Selecione uma origem complementar.'
        outra='' if self.dados and self._outras_execucoes() else 'Abra um resultado e salve outra execução do mesmo projeto.'
        mapa='' if self.mapa_gis.registros else 'Adicione ou carregue elementos cartográficos para consultar.'
        tem_conexao=getattr(self,'_tem_conexoes_mapa',False)
        controles=(
            (self.destacar_relacao_b,falta_relacao,'Destaca a fonte, as tubulações e os pontos vinculados disponíveis.'),
            (self.aproximar_relacao_b,falta_relacao,'Prioriza o ponto da fonte quando ela está afastada da rede.'),
            (self.editar_relacao_b,falta_relacao or self._motivo_edicao(r),'Edita os dados e pontos de conexão do complemento.'),
            (self.reposicionar_b,cadastrado or self._motivo_edicao(r),'Muda a posição da origem complementar.'),
            (self.historico_elemento_b,falta_relacao,'Consulta as revisões deste elemento.'),
            (self.adotar_revisao_b,falta_relacao,'Carrega a última revisão no rascunho da hipótese.'),
            (self.alternar_elemento_b,falta_relacao or self._motivo_edicao(r),'Altera a disponibilidade no cadastro.'),
            (self.origem_gis_b,redes,'Associe uma origem cadastrada aos pontos de conexão da rede.'),
            (self.origem_mapa_b,redes,'Posicione no mapa uma origem complementar.'),
            (self.adicionar_conexao_b,redes,'Escolha os pontos da ligação no mapa. A rede GIS original é preservada.'),
            (self.executar_b,redes,'Calcula conectividade topológica no escopo indicado.'),
            (self.salvar_hip_b,redes,'Acrescenta uma revisão à hipótese em edição.'),
            (self.nova_hip_b,redes,'Grava uma hipótese independente com os parâmetros atuais.'),
            (self.reexecutar_b,redes,'Escolha entre execução temporária, nova revisão ou nova hipótese.'),
            (self.comparar_b,outra,'Compara dois resultados imutáveis e localiza suas diferenças.'),
            (self.consultar_mapa_b,mapa,'Identifica o registro representado pelo elemento clicado.'),
            (self.revisar_mapa_b,mapa or ('' if tem_conexao else 'Nenhuma conexão representada no mapa.'),'Abre a revisão da conexão selecionada.'),
            (self.destacar_b,falta_resultado,'Realça as geometrias relacionadas.'),
            (self.aproximar_b,falta_resultado,'Enquadra o resultado selecionado.'),
            (self.anotar_b,falta_resultado,'Salva situação e observação opcional.'),
            (self.revisar_b,falta_resultado or ('' if resultado and resultado.get('tipo') in CANDIDATAS else
                                               'Selecione uma conexão candidata para revisá-la.'),'Abra a revisão detalhada.'),
            (self.historico_resultado_b,falta_resultado,'Consulta as revisões do resultado selecionado.'),
            (self.exportar_gpkg_b,'' if self.dados else falta_resultado,'Exporta a execução para GeoPackage.'),
            (self.exportar_shp_b,'' if self.dados else falta_resultado,'Exporta a execução para Shapefile e tabelas.'),
        )
        for controle,motivo,dica in controles:acao_disponivel(controle,motivo,dica)

    def _indicar_rascunho(self):
        pendente=self.edicao_pendente()
        salvo=getattr(self,'_edicao_preservada',None)
        texto=('Hipótese modificada · alterações por salvar.' if pendente else
               'Rascunho preservado.' if salvo else '')
        self.hipotese_info.setText(texto)
        self.hipotese_info.setVisible(bool(texto))

    def _navegar_fonte_gis(self,indice,aproximar):
        fonte=self.por_fonte.get(indice.data(Qt.UserRole))
        if fonte:self.central.mapa.destacar(fonte,aproximar=aproximar)

    def _navegar_relacao(self,indice,aproximar):
        r=self._relacao_na_linha(indice)
        if r:self.destacar_relacao(aproximar,r)

    def _projeto(self):
        return self.central.projetos.atual()

    def _revisao(self):
        return next(reversed(revisoes(self._projeto())),{})

    def _revisao_operacional(self,hip=None):
        hip=hip or self._hip_ativa
        if not hip or hip.get('formato')!=hg.FORMATO:return self._revisao()
        uid=hip['configuracao']['modelo_rev']
        modelo=next((r for r in revisoes(self._projeto()) if r['uuid']==uid),None)
        if modelo is None:
            raise ValueError('A revisão do Modelo GIS fixada nesta hipótese está indisponível.')
        return modelo

    def _listar_redes(self,revisao):
        fontes=[f for f in revisao.get('fontes',[]) if f['categoria']=='PIPE']
        self.estrategia.setText('Estratégia de Junctions do Modelo GIS: '+revisao.get('estrategia','COMBINAR').lower()+'.')
        self.por_fonte={f['uid']:f for f in fontes}
        anteriores={i.data(Qt.UserRole):i.checkState()==Qt.Checked for i in _itens(self.redes)}
        bloqueado=self.redes.blockSignals(True)
        try:
            self.redes.clear()
            for f in fontes:
                _inserir(self.redes,f["nome"]+' · '+(f['classificacao'] or 'Sem classificação'),f['uid'],
                         anteriores.get(f['uid'],True))
        finally:self.redes.blockSignals(bloqueado)
        if fontes:self.redes.setCurrentRow(0)

    def _pasta(self):
        p=self._projeto()
        return (Path(p['manifesto_wna']).parent if p.get('manifesto_wna')
                else self.app.catalogo.raiz/'topologia_gis'/p['uuid'])

    def _base_complementos(self, criar=False):
        p=self._projeto()
        if p.get('arquivo_complementos'):
            return Path(p['arquivo_complementos'])
        if not criar:
            return None
        from .manifesto_projeto import pasta_projeto
        pasta=pasta_projeto(p,'MODELO',self._pasta())
        pasta.mkdir(parents=True,exist_ok=True)
        arq=pasta/('complementos_'+p['uuid'][:12]+'.gpkg')
        if not arq.exists():
            pg.criar_complementos(arq,p['uuid'])
        pg.revisoes(arq,p['uuid'])
        p['arquivo_complementos']=str(arq.resolve())
        self.central.projetos.salvar()
        return arq

    def abrir(self, origens=False):
        p=self._projeto()
        if p['uuid']!=self.uid_projeto:
            self.uid_projeto=p['uuid']
            self.dados=None
            self._hip_ativa=None
            self._pinos={}
            self._edicao_limpa=None
            self._edicao_preservada=None
            self._rascunho_restaurado=None
            self._resultado_historico=False
            self.comparacao.limpar()
            self.comparacao.hide()
            self.unidades={}
            self.redes.clear()
            self.participantes.clear()
            self.conexoes_lista.clear()
            self._candidatas_tabela={}
            self.hipoteses.clear()
            self.crs.setCrs(QgsProject.instance().crs())
            self.resumo.clear()
            self.status.setText('Topologia GIS · conectividade estrutural')
            self.config_b.setChecked(True)
            self.historico.hide()
            self.listar_categorias()
        r=self._com_erro(self._revisao_operacional) or self._revisao()
        self._listar_redes(r)
        fontes=self.por_fonte.values()
        if self._edicao_limpa is None:
            from auditoria_fronteiras import Parametros
            from auditoria_fronteiras.entradas import crs_processamento
            for crs in (self.crs.crs(), *(QgsCoordinateReferenceSystem(f['crs_wkt']) for f in fontes)):
                try:
                    self.crs.setCrs(crs_processamento(Parametros(crs=crs.toWkt())))
                    break
                except ValueError:
                    continue
        self.atualizar_complementos()
        if self._edicao_limpa is None:self._edicao_limpa=self._assinatura_edicao()
        self.orig_b.setChecked(origens or self.orig_b.isChecked())
        self.mostrar_contexto()
        self._indicar_rascunho()

    def voltar(self):
        if not self.resolver_edicao():return
        self.cancelar_captura()
        self.central.mudar_area()

    def selecionar_tipo(self):
        escolha=self.tipo_escopo.currentData()
        for i in _itens(self.redes):
            f=self.por_fonte[i.data(Qt.UserRole)]
            i.setCheckState(Qt.Checked if not escolha or f['classificacao']==escolha else Qt.Unchecked)

    def mostrar_unidade(self,item,*_):
        chave=item.data(Qt.UserRole) if item else None
        fonte=self.por_fonte.get(chave,{})
        self.unidade.setEnabled(bool(fonte.get('campos_mapeados',{}).get('diametro')))
        self.unidade.setCurrentIndex(max(0,self.unidade.findData(self.unidades.get(chave))))

    def salvar_unidade(self):
        item=self.redes.currentItem()
        if item:self.unidades[item.data(Qt.UserRole)]=self.unidade.currentData()
        self._resultado_historico=False
        self.agendar_mapa()

    def _selecionados(self):
        return [*_marcados(self.participantes),*_marcados(self.conexoes_lista)]

    def _redes_marcadas(self):
        return _marcados(self.redes)

    def atualizar_complementos(self,escolhidos=None):
        marcados=set(self._selecionados() if escolhidos is None else escolhidos)
        preferida=self._hip_ativa['rev'] if self._hip_ativa else None
        anterior=self._registro_selecionado()
        self.hipoteses.clear()
        self.hipoteses.addItem('Hipótese temporária',None)
        self.relocalizar_b.hide()
        try:
            self._historicas=pg.revisoes(self._base_complementos(),self.uid_projeto)
        except (OSError,ValueError,__import__('sqlite3').Error) as e:
            self._historicas=[]
            self.relocalizar_b.show()
            self.status.setText('Cadastro de complementos indisponível. '+str(e))
        self._por_revisao={r['rev']:r for r in self._historicas}
        self.registros={r['uuid']:r for r in self._historicas}
        participacoes={}
        for r in reversed(self._historicas):
            if r['tipo']!='HIPOTESE':continue
            rotulo=' · revisão '+r['rev'][:8] if r.get('formato')==hg.FORMATO else ' · 1.16.0'
            self.hipoteses.addItem(r['nome']+rotulo,r['rev'])
            for uid,rev in r.get('vinculos',{}).items():
                participacoes.setdefault((uid,rev),set()).add(r['nome'])
        self._participacoes=participacoes
        self._por_candidata={}
        relacoes={**self.registros,**self._pinos}
        for r in self.registros.values():
            if r.get('candidato') and not r.get('excluido') and not r.get('substituida_por'):
                self._por_candidata.setdefault(r['candidato'],[]).append(r)
        self.participantes.blockSignals(True)
        self.participantes.setSortingEnabled(False)
        self.participantes.clear()
        for r in relacoes.values():
            if r['tipo'] != 'ORIGEM':continue
            excluido=bool(r.get('excluido'))
            if excluido and not self.mostrar_excluidos.isChecked():continue
            ativo=r.get('habilitado',True) and not excluido
            titulo=r.get('nome') or r.get('categoria') or 'Conexão '+r['uuid'][:8]
            if excluido:titulo+=' · excluído'
            elif not ativo:titulo+=' · desativado'
            nomes=', '.join(sorted(participacoes.get((r['uuid'],r['rev']),())))
            tipo=r.get('categoria') or 'Origem declarada'
            item=self.participantes.inserir((titulo,tipo,pg.SITUACOES[r['situacao']],len({p[0] for p in r['portas']}),r['rev'][:8],
                ACOMPANHAMENTO.get(r.get('acompanhamento'),'Pendente'),nomes),r['uuid'])
            item.setCheckState(Qt.Checked if r['uuid'] in marcados and (ativo or r['uuid'] in self._pinos) else Qt.Unchecked)
            if not ativo:item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
            if anterior and anterior['uuid']==r['uuid']:self.participantes.setCurrentCell(item.row(),0)
        self.participantes.setSortingEnabled(True)
        self.participantes.blockSignals(False)
        self.preencher_conexoes(relacoes, marcados)
        self.hipoteses.setCurrentIndex(max(0,self.hipoteses.findData(preferida)))
        self.detalhar_relacao()
        self._indicar_rascunho()
        self.agendar_mapa()

    def alterou_participacao(self,item):
        if item.column()!=0:return
        uid=item.data(Qt.UserRole)
        if item.checkState()==Qt.Checked and self.registros.get(uid,{}).get('excluido'):
            tabela=item.tableWidget()
            estado=tabela.blockSignals(True)
            item.setCheckState(Qt.Unchecked)
            tabela.blockSignals(estado)
            self.status.setText('Recupere o complemento antes de incluí-lo em outra hipótese.')
        self._resultado_historico=False
        if self.categoria.currentData()=='CRUZAMENTO':self.mudar_resultados(preservar=True)
        self.detalhar_relacao()
        self.detalhar_conexao()
        self._indicar_rascunho()
        self.agendar_mapa()

    def detalhar_relacao(self,r=None):
        r=r or self._registro_selecionado()
        self._atualizar_acoes()
        if not r:
            self.relacao_info.clear()
            return
        ids=getattr(self,'tubos',{})
        vinculos=', '.join(str(ids.get(uid,{}).get('id') or uid[:8])+f' ({pos*100:g}%)' for uid,pos in r['portas'])
        nomes=', '.join(sorted(self._participacoes.get((r['uuid'],r['rev']),()))) or 'Nenhuma revisão salva'
        estado='Incluída' if r['uuid'] in self._selecionados() else 'Fora da hipótese em edição'
        self.relacao_info.setText(f"{r.get('nome') or r.get('categoria') or 'Conexão'} · {estado} · revisão {r['rev'][:8]}"
                                 f"\nTubulações: {vinculos}\nHipóteses: {nomes}")

    def relocalizar_complementos(self):
        if self.central.ocupado():return
        path,_=QFileDialog.getOpenFileName(self,'Localizar complementos GIS','','GeoPackage (*.gpkg)')
        if not path:return
        def localizar():
            pg.revisoes(path,self.uid_projeto)
            self._projeto()['arquivo_complementos']=str(Path(path).resolve())
            self.central.projetos.salvar()
            self.atualizar_complementos()
            self.mostrar_contexto()
        self._com_erro(localizar)



    def _salvar(self,tipo,dados,anterior=None):
        anterior=anterior or {}
        r=pg.salvar_revisao(self._base_complementos(True),self.uid_projeto,tipo,dados,
                            anterior.get('uuid'),anterior.get('rev'))
        self.atualizar_complementos()
        self.mostrar_contexto()
        return r



    def _com_erro(self,fn):
        import sqlite3
        try:return fn()
        except (OSError,ValueError,RuntimeError,sqlite3.Error) as e:self.status.setText(str(e))

    def _preparacao(self):
        return preparar(self._revisao_operacional().get('fontes',[]),list(self.central.modelo_gis.camadas()),
                        self.crs.crs().toWkt(),QgsProject.instance().transformContext(),
                        set(_marcados(self.redes)),self.unidades)

    def _inventario_para_editar(self,pronto):
        prep=self._com_erro(self._preparacao)
        if prep is None:return
        def trabalho(parar,etapa):
            tubos,_,eq,_,_=ler(prep,parar,etapa)
            _declaracoes_existentes([f for f,_,_ in prep[0]],tubos,eq)
            origens=[e for e in eq if e['categoria'] in ORIGENS]
            etapa(0,'Indexando elementos disponíveis no mapa')
            return tubos,origens,prep[1].toWkt(),(IndiceSelecao(tubos,parar),IndiceSelecao(origens,parar))
        # A seleção/cartografia permanece no thread principal.
        self.app.atividades.executar_thread('Carregar elementos GIS',self._projeto()['nome'],trabalho,pronto,self.status.setText)

    def editar(self,tipo,anterior=None,ponto=None,candidato=None):
        if self.central.ocupado():return
        if self._editor is not None:
            self._editor.show()
            self._editor.raise_()
            return
        def dialogo(tubos,eq,crs,indices=None):
            atual=self.registros.get(anterior['uuid']) if anterior else None
            local=ponto
            if local is None and anterior and anterior.get('xy'):
                local={k:anterior[k] for k in ('xy','crs')}
            dlg=EditarComplemento(self,tipo,tubos,eq,local,anterior,candidato)
            if indices is not None:
                dlg._indice_tubos,dlg._indice_equipamentos=indices
            self._editor=dlg
            crs_editor=QgsCoordinateReferenceSystem(crs)
            dlg.escolher_tubos.connect(lambda:self.selecionar_no_editor(dlg,crs))
            dlg.escolher_origem.connect(lambda:self.selecionar_no_editor(dlg,crs,origem=True))
            dlg.portas_alteradas.connect(lambda:self._destacar_tubos_editor(dlg,crs_editor))
            dlg.navegar_tubo.connect(lambda uid,aproximar:self._destacar_tubo_editor(dlg,uid,crs_editor,aproximar))
            if anterior and pg.complemento_editavel(anterior):
                dlg.configurar_exclusao(lambda:self.excluir_relacao(anterior))
            def salvar(dados):
                if tipo=='ORIGEM' and dados.get('equipamento'):dados['crs']=crs
                if tipo=='CONEXAO':
                    dados['crs']=crs
                    if candidato and candidato.get('wkb'):dados['wkb']=candidato['wkb']
                dados['pontos_rede']=pontos_portas(dados['portas'],dlg.tubos)
                dados['crs_rede']=crs
                dados['geometrias_rede']={}
                for uid,_ in dados['portas']:
                    t=dlg.tubos[uid]
                    g=t.get('geom')
                    wkb=bytes(g.asWkb()).hex() if g else t.get('wkb')
                    if wkb:dados['geometrias_rede'][uid]=wkb
                if tipo=='CONEXAO' and not atual and not candidato:
                    if not self.confirmar_distincao_manual(dlg,dados):return False
                novo=self._salvar(tipo,dados,atual)
                self._atualizar_rascunho_relacao(novo)
                self.status.setText('Revisão salva. Marque a relação para reexecutar. Hipóteses anteriores preservam suas revisões.')
            def terminou(_):
                self._editor=None
                self.cancelar_captura(reabrir=False)
                self.central.mapa.limpar()
                self._atualizar_acoes()
                dlg.deleteLater()
            dlg.antes_salvar=salvar
            dlg.finished.connect(terminou)
            dlg.show()
        if candidato and self.dados:
            dialogo(self.dados['tubos'],[],self.dados['crs'])
        else:
            self._inventario_para_editar(lambda inventario:dialogo(*inventario))

    def _registro_selecionado(self):
        i=self.participantes.currentItem()
        if not i:return None
        uid=i.data(Qt.UserRole)
        return self._relacao_por_id(uid)

    def _candidato_da_relacao(self,r):
        if not r.get('candidato'):return None
        return dict(uid=r['candidato'],portas=r['portas'],tipo=r.get('categoria_candidata'),wkb=r.get('wkb'))

    def editar_selecionado(self):
        r=self._registro_selecionado()
        if r:self._editar_relacao(r)

    def alternar_elemento(self,r=None):
        r=r if isinstance(r,dict) else self._registro_selecionado()
        if r and not self.central.ocupado():
            if r.get('excluido'):
                self.status.setText('Recupere o complemento antes de alterar sua disponibilidade.')
                return
            atual=self.registros.get(r['uuid'])
            if atual and atual['rev']!=r['rev']:
                self.status.setText('A hipótese fixou uma revisão anterior. Adote a revisão atual antes de editar o cadastro.')
                return
            novo=self._com_erro(lambda:self._salvar(r['tipo'],dict(r,habilitado=not r.get('habilitado',True)),r))
            if novo:
                self._pinos.pop(r['uuid'],None)
                self._resultado_historico=False
                self.atualizar_complementos()

    def reposicionar(self):
        r=self._registro_selecionado()
        if r and r['tipo']=='ORIGEM' and not r.get('equipamento'):
            self.capturar(r)



    def iniciar(self,modo=None,*,ao_concluir=None):
        if self.central.ocupado() or self._editor is not None or not self.central.modelo_gis.resolver():return
        self.cancelar_captura()
        def iniciar():
            prep=self._preparacao()
            p=self._projeto()
            projeto_uid=p['uuid']
            rev=self._revisao_operacional()
            participantes=self._participantes_exatos(repetir=modo!='temporaria')
            grupos=[r['candidato'] for r in participantes if r.get('candidato')]
            if len(grupos)!=len(set(grupos)):
                raise ValueError('Selecione apenas uma interpretação por conexão candidata.')
            parametros=self._parametros()
            config=hg.configuracao(prep,rev.get('uuid'),parametros)
            hip=self._hip_ativa if modo!='temporaria' else None
            if hip:self._validar_configuracao_fixada(hip,config,participantes)
            contexto=dict(projeto_uid=projeto_uid,projeto=p['nome'],modelo_rev=rev.get('uuid'),
                          nome=self.nome.text().strip() or 'Conectividade GIS',
                          hipotese=hip,configuracao=config)
            from .manifesto_projeto import pasta_projeto
            pasta=pasta_projeto(p,'TOPOLOGIA_GIS',self._pasta()/'resultados')
            pasta.mkdir(parents=True,exist_ok=True)
            destino=pasta/('topologia_gis_'+uuid4().hex[:16]+'.gpkg')
            self.status.setText('Análise de conectividade em andamento. Acompanhe em Janelas.')
            def trabalho(parar,etapa):
                inventario=ler(prep,parar,etapa)
                assinatura=hg.assinatura_inventario(inventario)
                if hip and assinatura!=hip['assinatura_inventario']:
                    raise ValueError('O conteúdo das fontes mudou desde a revisão salva. Restaure as fontes ou crie nova revisão.')
                d=executar(prep,contexto,parametros,participantes,parar,etapa,inventario=inventario)
                d['assinatura_inventario']=assinatura
                d['assinaturas_fontes']=hg.assinaturas_fontes(inventario,(f['uid'] for f in d['fontes']))
                etapa(0,'Gravando execução verificada')
                pg.salvar_execucao(destino,d,parar)
                return d
            def pronto(d):
                if self._projeto()['uuid']!=projeto_uid:
                    raise ValueError('O projeto mudou. O resultado pode ser recuperado pelo arquivo gravado.')
                r=self.app.catalogo.registrar(destino)[0]
                self.central.projetos.vincular(r)
                self.central._catalogo_lido=None
                self.receber(d)
                self.central.atualizar_continuacao()
            worker=self.app.atividades.executar_thread('Analisar conectividade',p['nome'],trabalho,pronto,self.status.setText)
            if ao_concluir:
                from qgis.PyQt.QtCore import QTimer
                op=self.app.atividades.atual
                def retornar():
                    if op.estado=='CONCLUIDO' and self.dados and self.dados['projeto_uid']==projeto_uid:
                        resultado=self.dados
                        QTimer.singleShot(0,lambda:ao_concluir(resultado))
                worker.finished.connect(retornar)
            return worker
        return self._com_erro(iniciar)

    def executar_configuracao_atual(self):
        if self._hip_ativa and self._edicao_limpa!=self._assinatura_edicao():
            self.reexecutar()
        else:self.iniciar()

    def reabrir(self,r,cartografar=False,aproximar=False):
        uid=self.uid_projeto
        def carregar(parar,etapa):
            from .contexto_trabalho import validar_registro
            validacao=validar_registro(r)
            if not validacao['valido']:raise ValueError(r['base']+' · '+validacao['erro'])
            return pg.carregar(r['base'],r['uuid'],uid)
        worker=self.app.atividades.executar_thread('Reabrir topologia GIS',r.get('nome','Conectividade GIS'),
            carregar,
            lambda d:self.receber(d,restaurar_configuracao=True),self.status.setText)
        if cartografar:
            operacao=self.app.atividades.atual
            worker.finished.connect(lambda:self.destacar(aproximar=aproximar)
                                    if operacao.estado=='CONCLUIDO' and self.dados['uuid']==r['uuid'] else None)
        return worker

    def receber(self,d,restaurar_configuracao=False):
        if d['projeto_uid']!=self.uid_projeto or d['projeto_uid']!=self._projeto()['uuid']:
            raise ValueError('O projeto ativo mudou durante a abertura.')
        self.dados=d
        self.limiar_cruzamentos.blockSignals(True)
        self.limiar_cruzamentos.setValue(d['parametros']['tolerancia'])
        self.limiar_cruzamentos.blockSignals(False)
        self._prioridade_cruzamentos=cruzamentos.classificar(d)
        self._comparadas=None
        self.comparacao.hide()
        self._resultado_historico=True
        self._vereditos_foto={r['candidato']:r for r in d['participantes']
                              if r['tipo']=='CONEXAO' and r.get('candidato')}
        self.tubos={t['uid']:t for t in d['tubos']}
        self.nos={n['uid']:n for n in d['nos']}
        self.componentes={g['uid']:g for g in d['componentes']}
        self.componentes_tubo={t:g for g in d['componentes'] for t in g['tubos']}
        self.comps_origens={r['uuid']:r for r in d['participantes'] if r['tipo']=='ORIGEM'}
        if restaurar_configuracao:
            self._rascunho_restaurado=None
            hip=d.get('hipotese')
            self._hip_ativa=hip if hip and hip.get('formato')==hg.FORMATO else None
            if self._hip_ativa:
                modelo=next((r for r in revisoes(self._projeto()) if r['uuid']==hip['configuracao']['modelo_rev']),None)
                if modelo is not None:self._listar_redes(modelo)
            self._pinos={r['uuid']:r for r in d['participantes']}
            self.nome.setText(self.central.nome_analise('TOPOLOGIA_GIS',d['uuid'],d['nome']))
            self.crs.setCrs(QgsCoordinateReferenceSystem(d['crs']))
            self.tolerancia.setValue(d['parametros']['tolerancia'])
            self.limite.setValue(d['parametros']['limite_mm'])
            self.aproximadas.setChecked(d['parametros']['inferir_proximas'])
            self.unidades=dict(d['unidades'])
            redes={f['uid'] for f in d['fontes'] if f['categoria']=='PIPE'}
            for i in _itens(self.redes):
                i.setCheckState(Qt.Checked if i.data(Qt.UserRole) in redes else Qt.Unchecked)
            self.atualizar_complementos(escolhidos=self._pinos)
            self.mostrar_unidade(self.redes.currentItem())
            self._edicao_limpa=self._assinatura_edicao()
            self._edicao_preservada=None
            self._indicar_rascunho()
        self._resultado_historico=True
        self.status.setText(d['nome'])
        self.config_b.setChecked(False)
        self.listar_categorias()
        self._resultados_por_uid={r['uid']:r for r in [*d['componentes'],*d['diagnosticos']]}
        self.preencher_conexoes({**self.registros,**self._pinos},set(self._selecionados()))
        if self.revisao_seq_b.isChecked():self._abrir_revisao_seq(True)
        self.mostrar_contexto()
        self.agendar_mapa()

    def mostrar_contexto(self):
        if not self.dados:return
        d=self.dados
        antigos={f['uid']:f for f in d['fontes']}
        atual={f['uid']:f for f in self._revisao().get('fontes',[])}
        alterou=d['modelo_rev']!=self._revisao().get('uuid')
        camadas=list(self.central.modelo_gis.camadas())
        for uid,f in antigos.items():
            presente=atual.get(uid)
            c=identificar(presente,camadas) if presente else None
            try:
                if c is None or descrever(c)['assinatura']!=f['assinatura']:alterou=True
            except ValueError:
                alterou=True
        alterou |= any(self.registros.get(r['uuid'],{}).get('rev')!=r['rev'] for r in d['participantes'])
        g=d['componentes']
        c=[v for v in g if v['situacao']=='SEM_ORIGEM_ALCANCAVEL']
        s=f"Execução aberta · {d['nome']} · {d['uuid'][:8]}\n"
        s+=f"{len(g)} componente(s) · {len(d['tubos'])} parte(s) de tubulação · {len(d['ramos'])} ramificação(ões)"
        s+=f"\nOrigens com portas válidas: {len(d['origens_validas'])}/{len(self.comps_origens)}."
        s+=(f" Sem ligação a essas origens: {len(c)} componente(s) · {sum(v['comprimento_m'] for v in c):.2f} m."
            if d['origens_validas'] else ' Acesso a origens ainda indeterminado.')
        if alterou:s+='\nAs fontes ou relações mudaram ou estão indisponíveis. A execução preserva a configuração anterior.'
        if d['avisos']:s+='\n'+'\n'.join(d['avisos'])
        if hip:=d.get('hipotese'):
            s+='\nHipótese da execução · '+hip['nome']+' · revisão '+(hip.get('rev') or '—')[:8]
        else:
            s+='\nConfiguração temporária da execução.'
        self.resumo.setText(s)

    def listar_categorias(self):
        from collections import Counter
        self.categoria.blockSignals(True)
        self.categoria.clear()
        if self.dados:
            cont=Counter(r['tipo'] for r in self.dados['diagnosticos'])
            self.categoria.addItem(f"Todos os componentes ({len(self.dados['componentes'])})",'COMPONENTES')
            for k,n in ROTULOS.items():
                if k=='CONEXAO_T':n='Conexões em T'
                self.categoria.addItem(f'{n} ({cont[k]})',k)
        self.categoria.blockSignals(False)
        self.mudar_resultados()

    def _rotulo_tubo(self,uid):
        t=self.tubos.get(uid,{})
        return f"{t.get('id') or uid[:8]} · {t.get('camada','Fonte anterior')}"

    def _acompanhamento(self,r):
        if r.get('tipo') in CANDIDATAS:
            atuais=self._por_candidata.get(r['uid'],())
            if len(atuais)>1:return 'Múltiplas interpretações'
            if atuais:return ACOMPANHAMENTO.get(atuais[0].get('acompanhamento'),'Pendente')
            if r.get('tipo')=='CRUZAMENTO' and r['uid'] not in self._decisoes_resultado:
                return ('Não revisado · baixa prioridade' if self._prioridade_cruzamentos.get(r['uid'],{}).get('nivel')=='BAIXA'
                        else 'Não revisado')
        return ACOMPANHAMENTO.get(self._decisoes_resultado.get(r['uid'],{}).get('acompanhamento'),'Pendente')

    def reclassificar_cruzamentos(self,limite):
        if self.dados:
            self._prioridade_cruzamentos=cruzamentos.classificar(self.dados,limite)
            self.mudar_resultados(preservar=True)

    def cruzamento_revisado(self,r):
        return bool(self._por_candidata.get(r['uid']) or self._vereditos_foto.get(r['uid']) or
                    r.get('situacao') in ('CONFIRMADA','SEPARADA','INDETERMINADA'))

    def _acompanhamento_foto(self,r):
        anterior=getattr(self,'_vereditos_foto',{}).get(r['uid'],{})
        return ACOMPANHAMENTO.get(anterior.get('acompanhamento'),'Sem revisão na fotografia')

    def _colunas_resultados(self):
        categoria=self.categoria.currentData()
        if categoria in ('COMPONENTES','COMPONENTE_INDEPENDENTE','SEM_ORIGEM'):
            return ('ID','Situação topológica','Tubulações','Comprimento (m)','Maior Ø (mm)','Acima do limite (m)',
                    'Origens alcançáveis','Candidatas','Acompanhamento')
        if categoria=='REDE_PRINCIPAL':
            return ('Componente','Trechos','Extensão relevante (m)','Maior Ø (mm)','Origens','Critério','Prioridade','Acompanhamento')
        cols=('ID','Tubulação que termina' if categoria=='CONEXAO_T' else 'Tubulação A',
                'Tubulação receptora' if categoria=='CONEXAO_T' else 'Tubulação B',
                'Distância (m)','Componentes','Interpretação atual','Acompanhamento atual')
        if categoria=='CRUZAMENTO':
            return (*cols,'Acompanhamento na fotografia','Prioridade','Motivo','Extremidade (m)','Acesso às origens',
                    'Participação no rascunho')
        return (*cols,'Acompanhamento na fotografia') if categoria in CANDIDATAS else cols

    def _valores(self,r):
        categoria=self.categoria.currentData()
        g=self.componentes.get(r.get('componente',r['uid']),{})
        origens=', '.join((self.comps_origens[o].get('nome') or o[:8]) for o in g.get('origens',[]))
        situacao=self._acompanhamento(r)
        if categoria in ('COMPONENTES','COMPONENTE_INDEPENDENTE','SEM_ORIGEM'):
            return (g['uid'][:8],ESTADO_COMPONENTE[g['situacao']],g['quantidade_tubos'],g['comprimento_m'],
                    g.get('max_mm'),g['faixas_m']['A partir do limite'],origens,len(g['candidatas']),situacao)
        if categoria=='REDE_PRINCIPAL':
            prioridade=getattr(self,'_prioridade',{}).get(r['uid'])
            return (r['componente'][:8],len(r['tubos']),r['comprimento_m'],r.get('max_mm'),origens,r['criterio'],prioridade,situacao)
        ts=r['tubos']
        ponta=r.get('tubulacao_termina')
        receptora=r.get('tubulacao_receptora')
        if categoria=='CONEXAO_T' and not ponta:
            ponta=next((u for u,f in r.get('portas',[]) if f in (0,1)),None)
            receptora=next((u for u,f in r.get('portas',[]) if 0<f<1),None)
        a=ponta or (ts[0] if ts else None)
        b=receptora or (ts[1] if len(ts)>1 else None)
        componentes=r.get('componentes') or sorted({self.componentes_tubo[u]['uid'] for u in ts if u in self.componentes_tubo})
        vals=(r['uid'][:8],self._rotulo_tubo(a) if a else None,self._rotulo_tubo(b) if b else None,
                r.get('distancia_m'),', '.join(u[:8] for u in componentes),
                self._interpretacao_atual(r),situacao)
        if categoria=='CRUZAMENTO':
            p=self._prioridade_cruzamentos.get(r['uid'],{})
            rel=self._veredito_atual(r)
            acesso=' · '.join(f'{u[:8]}: {ESTADO_COMPONENTE[s]}' for u,s in p.get('acessos',{}).items())
            return (*vals,self._acompanhamento_foto(r),cruzamentos.ROTULOS.get(p.get('nivel')),p.get('motivo'),
                    p.get('extremidade_m'),acesso,
                    'Incluída' if rel and rel['uuid'] in self._participacao_resultados else 'Fora')
        return (*vals,self._acompanhamento_foto(r)) if categoria in CANDIDATAS else vals

    def ordenar_resultados(self,coluna):
        atual=self._ordem_coluna
        descendente=not atual[1] if atual and atual[0]==coluna else False
        self._ordem_coluna=(coluna,descendente)
        self.resultados.horizontalHeader().setSortIndicator(coluna,Qt.DescendingOrder if descendente else Qt.AscendingOrder)
        self.resultados.horizontalHeader().setSortIndicatorShown(True)
        self.mudar_resultados(preservar=True)

    def mudar_resultados(self,*_,preservar=False):
        anterior=self._selecionado() if preservar else None
        self._pagina=0
        categoria=self.categoria.currentData()
        for campo in self._campos_cruzamentos:campo.setVisible(categoria=='CRUZAMENTO')
        self._participacao_resultados=set(self._selecionados()) if categoria=='CRUZAMENTO' else set()
        if categoria!=getattr(self,'_ultima_categoria',None):
            self._ultima_categoria=categoria
            self._ordem_coluna=None
            self.resultados.horizontalHeader().setSortIndicatorShown(False)
        d=self.dados
        if d and categoria:
            self._decisoes_resultado={r['alvo']:r for r in self.registros.values()
                                     if r['tipo']=='DECISAO' and r.get('execucao')==d['uuid']}
            candidatos=(d['componentes'] if categoria=='COMPONENTES' else
                        [c for c in d['diagnosticos'] if c['tipo']==categoria])
            chaves={
                'Prioridade':lambda r:(bool(r.get('origens')), -r.get('comprimento_m',0), -(r.get('max_mm') or 0),
                                       -len(r.get('candidatas',[])),-len(r['tubos']),r['uid']),
                'Comprimento':lambda r:(-r.get('comprimento_m',0),r['uid']),
                'Diâmetro':lambda r:(-(r.get('max_mm') or 0),r['uid']),
                'Categoria':lambda r:(r.get('tipo',r['situacao']),r['uid']),
            }
            if categoria=='REDE_PRINCIPAL':
                self._prioridade={r['uid']:i+1 for i,r in enumerate(sorted(candidatos,key=chaves['Prioridade']))}
            if categoria=='CRUZAMENTO':
                filtro=self.filtro_cruzamentos.currentData()
                candidatos=[r for r in candidatos if cruzamentos.atende(self._prioridade_cruzamentos.get(r['uid']),filtro,
                                                                         self.cruzamento_revisado(r))]
                chaves['Prioridade']=lambda r:(cruzamentos.ORDEM.get(self._prioridade_cruzamentos.get(r['uid'],{}).get('nivel'),3),r['uid'])
            termo=self.busca.text().strip().casefold()
            if termo:
                candidatos=[r for r in candidatos if termo in ' '.join((r['uid'],self._acompanhamento(r),
                    *(str(x) for x in self._valores(r) if x is not None),
                    *(z for t in r['tubos'] for z in self.tubos[t].get('zonas',[])))).casefold()]
            self._lista_resultados=sorted(candidatos,key=chaves[self.ordem.currentText()])
            if self._ordem_coluna:
                coluna,desc=self._ordem_coluna
                def chave(r):
                    v=self._valores(r)[coluna]
                    if categoria=='CRUZAMENTO' and coluna==8:
                        return (False,cruzamentos.ORDEM.get(self._prioridade_cruzamentos.get(r['uid'],{}).get('nivel'),3))
                    return (v is None, str(v).casefold() if isinstance(v,str) or v is None else v)
                self._lista_resultados.sort(key=chave,reverse=desc)
        else:self._lista_resultados=[]
        self.resultados.colunas(self._colunas_resultados())
        pos=next((i for i,r in enumerate(self._lista_resultados) if anterior and r['uid']==anterior['uid']),None)
        if pos is not None:self._pagina=pos//200
        self.paginar(0)
        if pos is not None:self.resultados.setCurrentCell(pos%200,0)

    def paginar(self,delta):
        n=len(self._lista_resultados)
        self._pagina=max(0,min(self._pagina+delta,(n-1)//200))
        bloqueado=self.resultados.blockSignals(True)
        self.resultados.limpar()
        for r in self._lista_resultados[200*self._pagina:200*(self._pagina+1)]:
            self.resultados.inserir(self._valores(r),r['uid'])
        self.resultados.blockSignals(bloqueado)
        total=max(1,(n+199)//200)
        self.pagina_info.setText(f'{self._pagina+1}/{total} · {n} resultado(s)')
        acao_disponivel(self.pagina_anterior_b,'Primeira página.' if self._pagina==0 else '', 'Página anterior')
        acao_disponivel(self.proxima_pagina_b,'Não há outra página.' if self._pagina+1>=total else '', 'Próxima página')
        if n:self.resultados.setCurrentCell(0,0)
        else:
            sem_t=self.categoria.currentData()=='CONEXAO_T' and not self.busca.text().strip()
            self.detalhes.setText('Nenhuma extremidade próxima do interior de outra tubulação foi identificada nas fontes e tolerância utilizadas.'
                                  if sem_t else 'Nenhum resultado nesta categoria e filtro.')
        self._atualizar_acoes()

    def selecionar_resultado_uid(self,uid,categoria):
        indice=self.categoria.findData(categoria)
        if indice<0:return False
        self.busca.clear()
        self.categoria.setCurrentIndex(indice)
        if categoria=='CRUZAMENTO':
            self.filtro_cruzamentos.setCurrentIndex(self.filtro_cruzamentos.findData('TODOS'))
        self.mudar_resultados()
        pos=next((i for i,r in enumerate(self._lista_resultados) if r['uid']==uid),None)
        if pos is None:return False
        self._pagina=pos//200
        self.paginar(0)
        self.resultados.setCurrentCell(pos%200,0)
        self.ensureWidgetVisible(self.resultados)
        return True

    def _selecionado(self):
        i=self.resultados.currentRow()
        pos=200*self._pagina+i
        return self._lista_resultados[pos] if i>=0 and pos<len(self._lista_resultados) else None

    def detalhar(self,*_):
        r=self._selecionado()
        self._atualizar_acoes()
        if r is None:return
        g=self.componentes.get(r.get('componente',r['uid']))
        partes=[]
        if g:
            origens=', '.join(self.comps_origens[o].get('nome') or self.comps_origens[o]['categoria'] for o in g['origens'])
            partes.append(f"{g['quantidade_tubos']} tubulações · {len(g['nos'])} nós")
            partes.append(f"Conexões candidatas neste componente: {len(g['candidatas'])}")
            partes.append('Maior diâmetro: '+(f"{g['max_mm']:g} mm" if g['max_mm'] else 'indisponível'))
            partes.append('Comprimento por faixa: '+ ' · '.join(f'{k}: {v:.2f} m' for k,v in g['faixas_m'].items()))
            partes.append('Origens alcançáveis: '+(origens or 'nenhuma na hipótese'))
            if g['uid']==self.dados['componentes'][0]['uid']:partes.append('Maior componente por extensão no escopo analisado.')
            perto=g.get('origem_mais_proxima')
            if perto:
                nome=self.comps_origens[perto['uuid']].get('nome') or perto['uuid'][:8]
                partes.append(f"Origem mais próxima geometricamente: {nome} · {perto['distancia_m']:.2f} m")
            if g.get('componentes_candidatos'):
                partes.append('Outros componentes junto de candidatas: '+', '.join(u[:8] for u in g['componentes_candidatos'][:12]))
            if g['zonas']:partes.append('Interseções espaciais: '+', '.join(g['zonas']))
        if 'distancia_m' in r:
            partes.append(f"Distância: {r['distancia_m']:.3f} m · alternativas: {r.get('concorrentes',0)}")
        if r.get('tipo')=='CONEXAO_T':
            partes.append('Nós cadastrais ou pontas próximas do ponto projetado: '+
                          str(len(r.get('junctions_proximas',[]))+len(r.get('pontas_proximas',[]))))
            partes.append('Pontos escolhidos: '+', '.join(f'{self._rotulo_tubo(u)} ({p*100:g}%)' for u,p in r.get('portas',[])))
        if r.get('tipo') in CANDIDATAS:
            partes.append('Componentes envolvidos: '+', '.join(u[:8] for u in r.get('componentes',[])))
            partes.append('Interpretação: '+self._interpretacao_atual(r))
        if (p:=self._prioridade_cruzamentos.get(r['uid'])):
            partes.append(f"Prioridade {cruzamentos.ROTULOS[p['nivel']].lower()} · {p['motivo']}")
        if r['tubos']:
            partes.append('Tubulações: '+', '.join(str(self.tubos[t].get('id') or t[:8]) for t in r['tubos'][:12]))
        if r.get('motivo') or r.get('criterio'):partes.append(r.get('motivo') or r['criterio'])
        if g and g.get('nos'):
            partes.append('Nós: '+', '.join(u[:8] for u in g['nos'][:8]))
        decisao=(self._veredito_atual(r) if r.get('tipo') in CANDIDATAS else None) or self._decisoes_resultado.get(r['uid'],{})
        estado=decisao.get('acompanhamento','PENDENTE')
        self.acompanhamento.setCurrentIndex(max(0,self.acompanhamento.findData(estado)))
        partes.append('Acompanhamento atual · '+self._acompanhamento(r))
        if r.get('tipo') in CANDIDATAS:
            partes.append('Acompanhamento na fotografia · '+self._acompanhamento_foto(r))
            if decisao.get('tipo')=='CONEXAO':
                partes.append(f"Revisão atual {decisao['rev'][:8]} · "+(
                    'marcada no rascunho' if decisao['uuid'] in self._selecionados() else 'fora do rascunho'))
        if decisao.get('nota'):partes.append('Observação: '+decisao['nota'])
        hip=self.dados.get('hipotese')
        partes.append('Hipótese: '+(hip['nome']+' · '+hip['rev'][:8] if hip else 'Execução temporária'))
        self.detalhes.setText(f"Página {self._pagina+1} · {len(self._lista_resultados)} resultados\n"+'\n'.join(partes))

    def _registro_resultado(self,indice):
        item=self.resultados.item(indice.row(),0)
        return getattr(self,'_resultados_por_uid',{}).get(item.data(Qt.UserRole)) if item else None

    def _navegar_resultado(self,indice,aproximar):
        r=self._registro_resultado(indice)
        if r:self.destacar(aproximar=aproximar,registros=[r])

    def _enquadrar_varios(self,indices):
        rs=[r for i in indices if (r:=self._registro_resultado(i))]
        if rs:self.destacar(aproximar=True,registros=rs,toda_extensao=True)

    def _menu_resultado(self,indice):
        r=self._registro_resultado(indice)
        if not r:return ()
        acoes=[('Enquadrar toda a extensão',lambda:self.destacar(aproximar=True,registros=[r],toda_extensao=True))]
        if r.get('tipo') in CANDIDATAS:
            try:
                motivo=self._motivo_edicao(self._registro_da_candidata(r))
            except ValueError as erro:
                motivo=str(erro)
            motivo=motivo or ('' if r.get('portas') else 'A candidata não possui pontos de conexão confiáveis.')
            acoes.append(('Conferir conexão…',lambda:self.conferir_conexao(r),motivo))
            if (p:=self._prioridade_cruzamentos.get(r['uid'])) and p['referencia_t']:
                acoes.append(('Abrir conexão em T relacionada',lambda:self.selecionar_resultado_uid(p['referencia_t'],'CONEXAO_T')))
            acoes.extend((rotulo+'…',lambda d=d,incluir=incluir:self.conferir_conexao(r,(d,incluir)),motivo)
                for rotulo,d,incluir in [('Confirmar e incluir','CONFIRMADA',True),
                    ('Confirmar sem incluir','CONFIRMADA',False),
                    ('Manter tubulações separadas','SEPARADA',True),
                    ('Registrar como indeterminada','INDETERMINADA',False)])
            acoes.append(('Abrir editor detalhado…',lambda:self.revisar_conexao(r=r),motivo))
            rel=self._com_erro(lambda:self._registro_da_candidata(r)) if not motivo else None
            if rel:
                marcado=rel['uuid'] in self._selecionados()
                acoes.extend([
                    ('Retirar da hipótese em edição' if marcado else 'Incluir na hipótese em edição',
                     lambda:self._marcar_relacao(rel['uuid'],not marcado),'' if marcado else self._motivo_participacao(rel)),
                    ('Histórico da conexão',lambda:self._mostrar_historico(rel['uuid'])),
                ])
        if r.get('tipo') not in CANDIDATAS:
            acoes.append(('Alterar situação e observação…',lambda:self.anotar(r=r,escolher_situacao=True)))
        acoes.append(('Histórico do diagnóstico da execução',lambda:self._mostrar_historico(self._id_resultado(r))))
        return acoes

    def destacar(self,checked=False,aproximar=False,registros=None,toda_extensao=None):
        if registros is None:registros=[self._selecionado()]
        registros=[r for r in registros if r]
        if not registros or self.central.ocupado():
            self.status.setText('Selecione um resultado disponível para consultar no mapa.')
            return
        d=self.dados
        from .mapa_topologia_gis import geometria_referencia
        crs=QgsCoordinateReferenceSystem(d['crs'])
        def mostrar():
            ids=dict.fromkeys(t for r in registros for t in r['tubos'])
            tubos=[g for t in ids if (g:=geometria(self.tubos.get(t,{}).get('wkb')))]
            grupos=[('tubo',QgsGeometry.collectGeometry(tubos))] if tubos else []
            componentes=[g for r in registros if (g:=self.componentes.get(r.get('componente',r['uid'])))]
            nos=dict.fromkeys(u for g in componentes for u in g['nos'])
            pontos=[QgsPointXY(*self.nos[u]['xy']) for u in nos if u in self.nos]
            if pontos:grupos.append(('local',QgsGeometry.fromMultiPointXY(pontos)))
            grupos.extend(('evento',g) for r in registros if (g:=geometria(r.get('wkb'))))
            for uid in dict.fromkeys(u for c in componentes for u in c['origens']):
                g=geometria_referencia(self.comps_origens[uid],crs)
                if g:grupos.append(('equipamento',g))
            total=bool(componentes) if toda_extensao is None else toda_extensao
            if not self.central.mapa.destacar_investigacao(grupos,crs,aproximar,toda_extensao=total):
                self.status.setText('Geometria indisponível para esta seleção.')
        self._com_erro(mostrar)

    def revisar_conexao(self,checked=False,r=None):
        r=r or self._selecionado()
        if not r or r.get('tipo') not in CANDIDATAS:
            self.status.setText('Selecione uma conexão candidata antes de revisar.')
            return
        def abrir():
            anterior=self._registro_da_candidata(r)
            motivo=self._motivo_edicao(anterior)
            if motivo:raise ValueError(motivo)
            self.editar('CONEXAO',anterior,candidato=r)
        self._com_erro(abrir)

    def _id_resultado(self,r=None):
        from auditoria_fronteiras.entradas import digest
        r=r or self._selecionado()
        return digest([self.dados['uuid'],r['uid']]) if r else None

    def anotar(self,checked=False,r=None,escolher_situacao=False):
        alvo=r or self._selecionado()
        if alvo and alvo.get('tipo') in CANDIDATAS:
            return self.conferir_conexao(alvo)
        uid=self._id_resultado(alvo)
        if not uid or self.central.ocupado():return
        anterior=self.registros.get(uid,dict(uuid=uid))
        estado=self.acompanhamento.currentData()
        if escolher_situacao:
            codigos=list(ACOMPANHAMENTO)
            rotulos=list(ACOMPANHAMENTO.values())
            atual=anterior.get('acompanhamento','PENDENTE')
            escolhido,ok=QInputDialog.getItem(self,'Acompanhamento do resultado','Situação',rotulos,codigos.index(atual),False)
            if not ok:return
            estado=codigos[rotulos.index(escolhido)]
        txt,ok=QInputDialog.getMultiLineText(self,'Observação do resultado','Observação',anterior.get('nota',''))
        if ok:
            r=self._com_erro(lambda:self._salvar('DECISAO',dict(nota=txt,execucao=self.dados['uuid'],
                                               alvo=alvo['uid'],acompanhamento=estado),anterior))
            if r:self.selecionar_resultado_uid(alvo['uid'],self.categoria.currentData())

    def _mostrar_historico(self,uid):
        if not uid or self.central.ocupado():return
        def mostrar():
            rs=pg.revisoes(self._base_complementos(),self.uid_projeto,uid)
            def resumo(r):
                estado=ACOMPANHAMENTO.get(r.get('acompanhamento')) or pg.DECISOES.get(r.get('decisao'))
                estado='Excluído do cadastro' if r.get('excluido') else estado
                return r['data_utc']+' · '+(estado or ('Habilitado' if r.get('habilitado',True) else 'Desabilitado'))+(
                    '\n'+r['nota'] if r.get('nota') else '')
            self.historico.setPlainText('\n\n'.join(resumo(r) for r in rs) or 'Nenhuma revisão registrada.')
            self.historico_b.setChecked(True)
            self.historico.show()
            self.ensureWidgetVisible(self.historico)
        self._com_erro(mostrar)

    def historico_resultado(self):
        self._mostrar_historico(self._id_resultado())

    def historico_elemento(self):
        r=self._registro_selecionado()
        if r:self._mostrar_historico(r['uuid'])

    def _outras_execucoes(self):
        return [r for r in (self._projeto() or {}).get('bases',[])
                if r['tipo']=='TOPOLOGIA_GIS' and r['uuid']!=(self.dados or {}).get('uuid')]

    def comparar(self,checked=False,*,referencia=None):
        d=self.dados
        if not d or self.central.ocupado():return
        rs=self._outras_execucoes()
        if not rs:
            self.status.setText('Salve outra execução deste projeto para comparar hipóteses.')
            return
        if referencia is None:
            nomes=[r.get('nome',Path(r['base']).name)+' · '+r['uuid'][:8] for r in rs]
            nome,ok=QInputDialog.getItem(self,'Comparar hipóteses','Execução de referência',nomes,editable=False)
            if not ok:return
            referencia=rs[nomes.index(nome)]
        r=referencia
        def trabalho(parar,etapa):
            antiga=pg.carregar(r['base'],r['uuid'],d['projeto_uid'])
            return antiga,hg.comparar_execucoes(antiga,d)
        def pronto(dados):
            antiga,diff=dados
            self._comparadas=(antiga,d)
            self._comparacao_antes={t['uid']:t for t in antiga['tubos']}
            self._comparacao_depois={t['uid']:t for t in d['tubos']}
            self.comparacao.blockSignals(True)
            self.comparacao.limpar()
            for linha in diff['diferencas']:
                self.comparacao.inserir((linha['nome'],linha['antes'],linha['depois'],len(linha['tubos'])),linha)
            self.comparacao.blockSignals(False)
            self.comparacao.show()
            a,b=diff['componentes']
            antes,depois=diff['sem_origem_m']
            def medida(n):return 'indeterminado' if n is None else f'{n:.2f} m'
            self.status.setText(f"Componentes {a} → {b} · {diff['unioes']} união(ões) · {diff['divisoes']} divisão(ões). "
                                f"Sem origem {medida(antes)} → {medida(depois)}. "
                                f"Entre trechos comuns, {diff['passou_alcancar_m']:.2f} m ganharam acesso e "
                                f"{diff['deixou_alcancar_m']:.2f} m perderam acesso a uma origem.")
        self.app.atividades.executar_thread('Comparar topologias GIS',d['nome'],trabalho,pronto,self.status.setText)

    def detalhar_diferenca(self,linha,*_):
        item=self.comparacao.item(linha,0) if linha>=0 else None
        if item:
            r=item.data(Qt.UserRole)
            self.status.setText(f"{r['nome']} · {len(r['tubos'])} trecho(s). Duplo clique para aproximar.")

    def destacar_diferenca(self,linha,*_,aproximar=False):
        item=self.comparacao.item(linha,0) if linha>=0 else None
        if item is None:return
        r=item.data(Qt.UserRole)
        a,b=self._comparadas
        from .mapa_topologia_gis import _transformar,geometria_referencia
        crs_b=QgsCoordinateReferenceSystem(b['crs'])
        def mostrar():
            grupos=[]
            for foto,inventario,papel,simbolo in ((a,self._comparacao_antes,'evento','evento'),(b,self._comparacao_depois,'tubo','equipamento')):
                crs=QgsCoordinateReferenceSystem(foto['crs'])
                gs=[_transformar(g,crs,crs_b) for uid in r['tubos'] if uid in inventario
                    for g in [geometria(inventario[uid]['wkb'])] if g is not None]
                if gs and (papel=='tubo' or r['tipo'] in ('AUSENTE','DIVIDIDO','PERDEU')):
                    grupos.append((papel,QgsGeometry.collectGeometry(gs)))
                rel=next((o for o in foto['participantes'] if o['uuid']==r.get('relacao')),None)
                if rel:
                    g=geometria_referencia(rel,crs_b)
                    if g:grupos.append((simbolo,g))
            if not self.central.mapa.destacar_investigacao(grupos,crs_b,aproximar,toda_extensao=True):
                self.status.setText('Geometria indisponível para esta diferença.')
        self._com_erro(mostrar)

    def exportar(self,formato):
        if not self.dados or self.central.ocupado():return
        pasta=QFileDialog.getExistingDirectory(self,'Pasta de exportação',str(self._pasta()))
        if not pasta:return
        from .exportar_grafo_gis import exportar
        d=self.dados
        self.app.atividades.executar_thread('Exportar topologia GIS',d['nome'],
            lambda parar,etapa:exportar(d,pasta,formato,parar,etapa),
            lambda destino:self.status.setText('Exportação salva em '+str(destino)),self.status.setText)

    def exportar_previa(self):
        if not self.dados or self.central.ocupado():
            self.status.setText('Abra ou execute uma análise de conectividade.')
            return
        pasta=QFileDialog.getExistingDirectory(self,'Pasta da prévia topológica')
        if not pasta:return
        from .topologia_derivada import exportar
        foto=self.dados
        self.app.atividades.executar_thread('Gerar prévia da topologia',foto['nome'],
            lambda parar,etapa:exportar(foto,pasta,parar,etapa),
            lambda caminho:self.status.setText('Prévia salva em '+str(caminho)),self.status.setText)
