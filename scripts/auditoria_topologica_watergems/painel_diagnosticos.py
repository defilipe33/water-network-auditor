"""Ambiente de diagnóstico: casos legíveis, filtros e mapa; legado disponível."""
from pathlib import Path
from html import escape
from collections import defaultdict
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QDockWidget,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,
    QLabel,QComboBox,QLineEdit,QTableWidget,QTableWidgetItem,QAbstractItemView,
    QTreeWidget,QTreeWidgetItem,QPushButton,QTabWidget,QSplitter,QScrollArea,QTextBrowser,QHeaderView,QCheckBox,QMessageBox,QFileDialog)
from qgis.PyQt import sip
from .diagnosticos import catalogar,filtrar,contagens,CATEGORIAS,MODOS
from .mapa_diagnosticos import MapaDiagnosticos


class PainelDiagnosticos(QDockWidget):
    def __init__(self,legado,parent=None):
        super().__init__('Diagnósticos GIS × WaterGEMS',parent)
        self.legado=legado;self.pacote=legado.pacote;self.base=legado.base;self._ativo=True;self._sincronizando=False
        self.casos=catalogar(self.pacote);self.atual=None;self._inversos=None;self._conexoes=[]
        self._filtros_estaveis=None;self._modo_estavel='ESTRUTURAL';self._bloqueador=None;self._iface=None
        self.mapa=MapaDiagnosticos(self.pacote,legado.projeto,legado.canvas)
        w=QWidget();self.setWidget(w);v=QVBoxLayout(w);self.resize(920,720)
        self.execucao=QLabel('Auditoria integrada · '+self.pacote['resultado']['meta']['uid'][:12]+' · detectar → localizar → investigar');v.addWidget(self.execucao)
        self.tabs=QTabWidget();v.addWidget(self.tabs);diag=QWidget();self.tabs.addTab(diag,'DIAGNÓSTICOS');layout=QVBoxLayout(diag)
        self.resumo=QLabel();self.resumo.setWordWrap(True);layout.addWidget(self.resumo)
        self.mostrar_filtros=QPushButton('Filtros ▾');self.mostrar_filtros.setCheckable(True);self.mostrar_filtros.setChecked(True);layout.addWidget(self.mostrar_filtros)
        self.bloco_filtros=QWidget();filtros=QGridLayout(self.bloco_filtros);layout.addWidget(self.bloco_filtros)
        self.mostrar_filtros.toggled.connect(self.bloco_filtros.setVisible)
        self.filtros_ativos=QLabel();self.filtros_ativos.setWordWrap(True);layout.addWidget(self.filtros_ativos)
        self.categoria=QComboBox();self.categoria.addItem('Todos os tipos',None)
        numeros=contagens(self.casos)['categorias']
        for k,n in CATEGORIAS.items():self.categoria.addItem(f"{n} ({numeros.get(k,0)})",k)
        self.modo=QComboBox();self.modo.addItem('Estrutural',MODOS[0]);self.modo.addItem('Potencial · válvulas abertas',MODOS[1])
        self.modo.addItem('Estados do cenário · indisponível','ESTADOS_DO_CENARIO');self.modo.model().item(2).setEnabled(False)
        self.componente=QComboBox();self.regiao=QComboBox();self.revisao=QComboBox();self.fonte=QComboBox();self.prioridade=QComboBox();self.busca=QLineEdit()
        self.busca.setPlaceholderText('Label, ID cadastral, local ou elemento…')
        limpar=QPushButton('Limpar filtros');limpar.clicked.connect(self.limpar_filtros);filtros.addWidget(limpar,10,0,1,2)
        from .decisoes import SITUACOES
        self.revisao_topo=QComboBox();self.revisao_topo.addItem('Todas as revisões topológicas',None)
        for situacao in SITUACOES:self.revisao_topo.addItem(situacao,situacao)
        self.regiao.addItem('Todas as regiões',None)
        for n in sorted({a for c in self.casos for a in c['regioes']}):self.regiao.addItem(n,n)
        self.revisao.addItem('Todas as revisões espaciais',None)
        for n in sorted({c['revisao'] for c in self.casos}):self.revisao.addItem('Sem revisão por ocorrência' if n=='SEM_REVISAO_POR_OCORRENCIA' else n,n)
        for nome,valor in [('Fonte: qualquer',None),('Com reservatório/tanque',True),('Sem reservatório/tanque',False)]:self.fonte.addItem(nome,valor)
        self.prioridade.addItem('Qualquer prioridade',None)
        for n in ('Alta','Média','Baixa'):self.prioridade.addItem(n,n)
        for k,(nome,widget) in enumerate([('Tipo',self.categoria),('Perspectiva',self.modo),('Componente',self.componente),('Região',self.regiao),('Revisão espacial',self.revisao),('Fonte cadastrada',self.fonte),('Prioridade',self.prioridade),('Elemento',self.busca),('Revisão topológica',self.revisao_topo)]):
            linha=(k//2)*2;col=k%2;filtros.addWidget(QLabel(nome),linha,col);filtros.addWidget(widget,linha+1,col)
        self.lista=QTableWidget(0,3);self.lista.setHorizontalHeaderLabels(['Situação investigável','Prioridade','Revisão topológica'])
        self.lista.setSelectionBehavior(QAbstractItemView.SelectRows);self.lista.setSelectionMode(QAbstractItemView.SingleSelection);self.lista.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.lista.setColumnWidth(1,70);self.lista.setColumnWidth(2,130);self.lista.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch)
        self.lista.setMaximumHeight(130);layout.addWidget(self.lista)
        self.cartao=QTextBrowser();self.cartao.setOpenExternalLinks(False);layout.addWidget(self.cartao,1)
        self.detalhes=QTreeWidget();self.detalhes.setHeaderLabels(['Detalhes expansíveis','Informação']);self.detalhes.setColumnWidth(0,180);self.detalhes.setWordWrap(True);self.detalhes.setMaximumHeight(100);layout.addWidget(self.detalhes)
        linha=QHBoxLayout();layout.addLayout(linha)
        for texto,acao in [('Aproximar mapa',self.aproximar),('Destacar componentes',self.componentes),('Selecionar GIS original',self.origens)]:
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
        self.analise=AnaliseDecisao(self);self.tabs.insertTab(1,self.analise,'ANÁLISE E DECISÃO')
        for nome,acao in [('Comparar com auditoria anterior…',self.comparar_versoes),('Exportar acompanhamento…',self.exportar_decisoes)]:
            b=QPushButton(nome);b.clicked.connect(acao);fv.addWidget(b)
        configurar=QPushButton('Abrir seleção de auditorias e fontes…');fv.addWidget(configurar)
        configurar.clicked.connect(self.configurar)
        self.modo.currentIndexChanged.connect(self.trocar_modo)
        for cb in (self.categoria,self.componente,self.regiao,self.revisao,self.revisao_topo,self.fonte,self.prioridade):cb.currentIndexChanged.connect(self.filtrar)
        self.busca.textChanged.connect(self.filtrar);self.lista.itemSelectionChanged.connect(self.selecionar)
        legado.revisao_salva.connect(self.revisao_atualizada)
        self.trocar_modo()
        if any('AUSENTE' in c['categorias'] for c in self.casos):self.categoria.setCurrentIndex(self.categoria.findData('AUSENTE'))
        for c in legado.projeto.mapLayers().values():
            if c.customProperty('integracao/uid')==meta['uid'] and c.customProperty('integracao/base')==str(Path(self.base).resolve()):
                callback=lambda *args,c=c:self.inversa(c)
                c.selectionChanged.connect(callback);self._conexoes.append((c,callback))

    def revisao_atualizada(self,*args):
        if not self._ativo:return
        self.casos=catalogar(self.pacote)
        for c in self.casos:
            if self.revisao.findData(c['revisao'])<0:self.revisao.addItem(c['revisao'],c['revisao'])
        self.filtrar()

    def trocar_modo(self):
        if hasattr(self,'analise') and self.analise.tem_edicoes() and not self.analise.resolver_edicoes():
            self.modo.blockSignals(True);self.modo.setCurrentIndex(self.modo.findData(self._modo_estavel));self.modo.blockSignals(False);return
        if self.modo.currentData() not in MODOS:
            self.modo.blockSignals(True);self.modo.setCurrentIndex(self.modo.findData(self._modo_estavel));self.modo.blockSignals(False);return
        self._modo_estavel=self.modo.currentData()
        self.componente.blockSignals(True);self.componente.clear();self.componente.addItem('Todos os componentes',None)
        modo=self.modo.currentData();nome='componentes' if modo==MODOS[0] else 'componentes_potenciais'
        for c in self.pacote['resultado'][nome]:self.componente.addItem(f"Componente {c['numero']} · {c['n_tubos']} tubos",c['uid'])
        self.componente.blockSignals(False);self.filtrar()
        modo=self.modo.currentData()
        for k,n in CATEGORIAS.items():self.categoria.setItemText(self.categoria.findData(k),f"{n} ({len(filtrar(self.casos,categoria=k,modo=modo))})")

    def filtrar(self):
        if not self._ativo:return
        self._inversos=None
        novos=filtrar(self.casos,self.categoria.currentData(),self.componente.currentData(),self.regiao.currentData(),self.revisao.currentData(),self.modo.currentData(),self.busca.text(),self.fonte.currentData(),self.prioridade.currentData())
        from .decisoes import indice_revisoes
        self._revisoes_topologicas=indice_revisoes(self.base,self.pacote['resultado']['meta']['uid'])
        if self.revisao_topo.currentData():novos=[c for c in novos if self._revisoes_topologicas.get((c['uid'],self.modo.currentData()),{}).get('situacao','PENDENTE')==self.revisao_topo.currentData()]
        if hasattr(self,'analise') and self.analise.tem_edicoes() and self.atual and not any(c['uid']==self.atual['uid'] for c in novos):
            if not self.analise.resolver_edicoes():
                if self._filtros_estaveis:
                    for w,valor in self._filtros_estaveis:
                        w.blockSignals(True)
                        if isinstance(w,QComboBox):w.setCurrentIndex(w.findData(valor))
                        else:w.setText(valor)
                        w.blockSignals(False)
                return
        self.visiveis=novos
        self._filtros_estaveis=[(w,w.currentData() if isinstance(w,QComboBox) else w.text()) for w in (self.categoria,self.componente,self.regiao,self.revisao,self.revisao_topo,self.fonte,self.prioridade,self.busca)]
        ativos=[w.currentText() for w in (self.categoria,self.componente,self.regiao,self.revisao,self.revisao_topo,self.fonte,self.prioridade) if w.currentIndex()>0]
        if self.busca.text():ativos.append('Elemento: '+self.busca.text())
        self.filtros_ativos.setText('Filtros: '+('; '.join(ativos) or 'nenhum')+' · '+self.modo.currentText())
        self.preencher()

    def limpar_filtros(self):
        for w in (self.categoria,self.componente,self.regiao,self.revisao,self.revisao_topo,self.fonte,self.prioridade,self.busca):w.blockSignals(True)
        for w in (self.categoria,self.componente,self.regiao,self.revisao,self.revisao_topo,self.fonte,self.prioridade):w.setCurrentIndex(0)
        self.busca.clear()
        for w in (self.categoria,self.componente,self.regiao,self.revisao,self.revisao_topo,self.fonte,self.prioridade,self.busca):w.blockSignals(False)
        self.filtrar()

    def preencher(self,selecionar_primeiro=True):
        anterior=self.atual['uid'] if self.atual else None
        self.lista.blockSignals(True);self.lista.setRowCount(len(self.visiveis))
        for n,c in enumerate(self.visiveis):
            situacao=self._revisoes_topologicas.get((c['uid'],self.modo.currentData()),{}).get('situacao','PENDENTE')
            for col,texto in enumerate((c['titulo'],c['prioridade'],situacao)):
                item=QTableWidgetItem(texto);item.setToolTip(texto);item.setData(Qt.UserRole,c['uid']);self.lista.setItem(n,col,item)
        self.lista.blockSignals(False)
        self.resumo.setText(f"{len(self.visiveis)} casos exibidos / {len(self.casos)} casos únicos. Prioridade é triagem. A lista mostra andamento topológico; a revisão espacial é preservada separadamente.")
        if self.visiveis and selecionar_primeiro:
            indice=next((i for i,c in enumerate(self.visiveis) if c['uid']==anterior),0);self.lista.selectRow(indice);self.selecionar()
        else:
            self.lista.clearSelection();self.lista.setCurrentCell(-1,-1);self.atual=None;self.detalhes.clear();self.cartao.clear();self.mapa.limpar()
            self.analise.carregar(None,self.modo.currentData())
            self.aviso.setText('Escolha um dos casos relacionados.' if self.visiveis else 'Nenhum caso atende aos filtros. Isso não comprova ausência de problemas na rede.')

    def selecionar(self):
        row=self.lista.currentRow()
        if not self._ativo or row<0 or row>=len(self.visiveis):return
        destino=self.visiveis[row]
        if self.atual and (destino['uid'],self.modo.currentData())!=self.analise.chave and self.analise.tem_edicoes() and not self.analise.resolver_edicoes():
            anterior=next((i for i,c in enumerate(self.visiveis) if c['uid']==self.atual['uid']),-1)
            self.lista.blockSignals(True);self.lista.selectRow(anterior);self.lista.blockSignals(False);return
        self.atual=self.visiveis[row];c=self.atual;self.detalhes.clear();modo=self.modo.currentData()
        self.analise.carregar(c,modo)
        def grupo(titulo,textos,expandido=True):
            raiz=QTreeWidgetItem(self.detalhes,[titulo]);raiz.setExpanded(expandido)
            for texto in textos:QTreeWidgetItem(raiz,['',str(texto)])
            return raiz
        elementos=c['tubos_gis']+c['elementos']
        evidencias=c['evidencias'] or ['Dados insuficientes para uma interpretação inequívoca.']
        situacao=c['revisao']+' · revisão espacial do local' if c['local_uid'] else 'Sem revisão persistente por ocorrência nesta entrega.'
        decisao=self.analise.head
        conclusao=(decisao['situacao']+' · '+decisao['conclusao']) if decisao else 'Conclusão técnica ainda não registrada; use ANÁLISE E DECISÃO.'
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
        grupo('Comparar perspectivas',linhas,False)
        tecnico=grupo('Detalhamento técnico',[f"Ocorrência {c['uid']}",f"Origem {c['tipo']} / {c['chave']}",f"Elementos nativos: {c['wg_ids']}",f"Identidades GIS: {c['gis_uids']}",*elementos],False)
        for n,t in c['tecnico']:QTreeWidgetItem(tecnico,[n,t])
        for m,us in c['componentes'].items():QTreeWidgetItem(tecnico,[m,'; '.join(us)])
        pend=[self.detalhes.topLevelItem(i) for i in range(self.detalhes.topLevelItemCount())]
        while pend:
            item=pend.pop()
            for col in range(2):item.setToolTip(col,item.text(col))
            pend.extend(item.child(i) for i in range(item.childCount()))
        n=self.mapa.destacar(c,modo)
        self.aviso.setText(f"{n} destaques temporários. Azul: tubos; verde: nós; magenta: dispositivos; ocre: limites; laranja tracejado: hipótese espacial, sem criar conexão. Aproximação é explícita." if n else 'Geometria ou CRS insuficiente; consulta técnica disponível, sem posicionamento inventado.')

    def configurar(self):
        if not self.resolver_alteracoes():return
        from .interface_integracao import abrir_integracao
        abrir_integracao()

    def componentes(self):
        if self.atual:self.mapa.destacar(self.atual,self.modo.currentData(),True)

    def aproximar(self):self.aviso.setText(self.mapa.aproximar())

    def origens(self):
        if self.atual:self.aviso.setText(self.mapa.selecionar_gis(self.atual))

    def abrir_legado(self):
        if self.atual and self.atual['local_uid']:
            self.legado.locais.setCurrentIndex(self.legado.locais.findData(self.atual['local_uid']));self.legado.show();self.legado.raise_()
        else:self.aviso.setText('A revisão existente pertence a locais geométricos. Este caso não tem local único; a conclusão por ocorrência será implementada na segunda entrega.')

    def inversa(self,camada):
        if not self._ativo or self._sincronizando:return
        if self.analise.tem_edicoes() and not self.analise.resolver_edicoes():return
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
        self._ativo=False;self.mapa.fechar()
        if self._iface and self._bloqueador:self._iface.unregisterApplicationExitBlocker(self._bloqueador);self._bloqueador=None
        for c,fn in self._conexoes:
            if not sip.isdeleted(c):
                try:c.selectionChanged.disconnect(fn)
                except (TypeError,RuntimeError):pass
        self._conexoes=[];self.legado.desativar();self.hide()

    def closeEvent(self,event):
        if not self.analise.resolver_edicoes():event.ignore();return
        if not self.legado.close():event.ignore();return
        self.desativar();event.accept()

    def resolver_alteracoes(self):
        return self.analise.resolver_edicoes() and (not self.legado.tem_edicoes() or self.legado.resolver_edicoes())

    def comparar_versoes(self):
        if not self.resolver_alteracoes():return
        caminho,_=QFileDialog.getOpenFileName(self,'Auditoria integrada anterior','','GeoPackage (*.gpkg)')
        if not caminho:return
        try:
            from .comparacao_decisoes import comparar,salvar_comparacao,selecionar_integracao
            anterior=selecionar_integracao(caminho,self)
            if anterior is None:return
            r=comparar(anterior,self.pacote,self.modo.currentData())
            resumo='\n'.join(f'{k}: {v}' for k,v in r['contagens'].items())+'\nNão transfere conclusões; ausência não comprova correção.'
            if QMessageBox.question(self,'Registrar comparação de versões',resumo,QMessageBox.Save|QMessageBox.Cancel,QMessageBox.Cancel)==QMessageBox.Save:
                salvar_comparacao(self.base,self.pacote,r,caminho);QMessageBox.information(self,'Comparação registrada',resumo)
        except Exception as e:QMessageBox.warning(self,'Comparação não registrada',str(e))

    def exportar_decisoes(self):
        if not self.resolver_alteracoes():return
        from .exportacao_decisoes import DialogExportarDecisoes
        self._exportacao=DialogExportarDecisoes(self);self._exportacao.exec_()


def abrir_diagnosticos(pacote,base,projeto=None,parent=None,canvas=None):
    from .painel_integrado import abrir_painel
    legado=abrir_painel(pacote,base,projeto,parent,canvas);legado.hide()
    painel=PainelDiagnosticos(legado,parent)
    if canvas is not None:
        try:
            from qgis.utils import iface
            if iface:
                iface.addDockWidget(Qt.RightDockWidgetArea,painel);painel.setMinimumWidth(480)
                from qgis.gui import QgsApplicationExitBlockerInterface
                class Bloqueador(QgsApplicationExitBlockerInterface):
                    def exitBlocked(self):return not painel.resolver_alteracoes()
                painel._iface=iface;painel._bloqueador=Bloqueador();iface.registerApplicationExitBlocker(painel._bloqueador)
        except ImportError:pass
    painel.show();return painel
