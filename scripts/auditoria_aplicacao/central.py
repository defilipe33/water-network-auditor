"""Central de trabalho: navegação sobre os controladores existentes."""
from pathlib import Path
from qgis.PyQt.QtCore import Qt,QTimer
from qgis.PyQt.QtWidgets import QDockWidget,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QTableWidget,QTableWidgetItem,QTabWidget,QScrollArea,QInputDialog,QMessageBox
from qgis.core import QgsSettings
from .dependencias import avaliar,disponibilidade,recomendar,FERRAMENTAS
from .contexto_trabalho import Projetos,fatos,validar_registro

class CentralTrabalho(QDockWidget):
    def __init__(self,app):
        super().__init__('Water Network Auditor — Central de Trabalho',app.iface.mainWindow());self.app=app;self.setObjectName('WNA_Central');self.projetos=Projetos(app.catalogo.raiz);self.settings=__import__('qgis.PyQt.QtCore',fromlist=['QSettings']).QSettings(str(app.catalogo.raiz/'preferencias_interface.ini'),__import__('qgis.PyQt.QtCore',fromlist=['QSettings']).QSettings.IniFormat);self.pendente=None;self._registros=[];self._requisitos={};self._fatos={}
        self.setAllowedAreas(Qt.LeftDockWidgetArea|Qt.RightDockWidgetArea);w=QWidget();self.setWidget(w);v=QVBoxLayout(w)
        topo=QHBoxLayout();self.barra_topo=topo;v.addLayout(topo);titulo=QLabel('WATER NETWORK AUDITOR');titulo.setStyleSheet('font-size:17px;font-weight:bold;');topo.addWidget(titulo);topo.addStretch();self.nivel=QComboBox();self.nivel.addItems(['Guiado','Avançado']);self.nivel.setCurrentText(self.settings.value('navegacao/nivel','Guiado'));self.nivel.currentTextChanged.connect(self.mudar_nivel);topo.addWidget(self.nivel)
        self.contexto=QLabel();self.contexto.setWordWrap(True);self.contexto.setTextFormat(Qt.PlainText);v.addWidget(self.contexto)
        h=QHBoxLayout();v.addLayout(h);self.projeto=QComboBox();h.addWidget(self.projeto,1)
        for t,fn in [('Criar projeto',self.criar_projeto),('Abrir projeto / recentes',self.abrir_projeto),('Atualizar',self.atualizar)]:b=QPushButton(t);b.clicked.connect(fn);h.addWidget(b)
        self.tabs=QTabWidget();v.addWidget(self.tabs,1);inicio=QWidget();iv=QVBoxLayout(inicio);self.tabs.addTab(inicio,'Começar / continuar')
        self.progresso=QTableWidget(0,2);self.progresso.setHorizontalHeaderLabels(['Pré-requisito','Estado verificado']);self.progresso.setEditTriggers(QTableWidget.NoEditTriggers);iv.addWidget(self.progresso)
        self.recomendacao=QPushButton();self.recomendacao.clicked.connect(lambda:self.acionar(self._recomendado));iv.addWidget(self.recomendacao)
        self.ultima=QPushButton('Retomar última base do projeto');self.ultima.clicked.connect(self.retomar_ultima);iv.addWidget(self.ultima)
        self.pendencias=QLabel();self.pendencias.setWordWrap(True);iv.addWidget(self.pendencias);self.retomar=QPushButton('Retomar operação desejada');self.retomar.clicked.connect(self.retomar_operacao);iv.addWidget(self.retomar);self.retomar.hide()
        self.acoes={}
        grupos=[('Preparar fontes',['gis','continuar_gis','preparar_wg','espacial','correspondencia','integrar']),('Investigar',['continuar','topologia','corredores','ilhas']),('Cenários e conjuntos',['cenarios','selection_sets']),('Apresentar e recuperar',['relatorio','historico'])]
        for nome,chaves in grupos:
            pagina=QWidget();pv=QVBoxLayout(pagina);sc=QScrollArea();sc.setWidgetResizable(True);sc.setWidget(pagina);self.tabs.addTab(sc,nome)
            for chave in chaves:
                titulo,req,ajuda=FERRAMENTAS[chave];b=QPushButton(titulo);b.setToolTip(ajuda+'\nRequisitos: '+(', '.join(req) or 'nenhum resultado prévio'));b.clicked.connect(lambda checked=False,k=chave:self.acionar(k));pv.addWidget(b);self.acoes[chave]=b
                l=QLabel(ajuda);l.setProperty('wna/ajuda_curta',True);l.setWordWrap(True);pv.addWidget(l)
            pv.addStretch()
        pg=QWidget();pv=QVBoxLayout(pg);self.tabs.addTab(pg,'Bases / versões');self.tabela=QTableWidget(0,5);self.tabela.setHorizontalHeaderLabels(['Nome','Tipo','Versão','Cenário','Disponibilidade']);self.tabela.setEditTriggers(QTableWidget.NoEditTriggers);self.tabela.setSelectionBehavior(QTableWidget.SelectRows);pv.addWidget(self.tabela)
        b=QPushButton('Abrir base selecionada');b.clicked.connect(self.abrir_registro);pv.addWidget(b);b=QPushButton('Catálogo: adicionar, localizar arquivos, histórico…');b.clicked.connect(lambda:self.app.catalogar());pv.addWidget(b)
        from .preparacao_guiada import PreparacaoGuiada
        self.preparacao=PreparacaoGuiada(self);self.tabs.insertTab(1,self.preparacao,'Preparação guiada')
        h=QHBoxLayout();v.addLayout(h);self.janelas=QPushButton('Janelas / painéis');self.janelas.setMenu(app.menu_janelas);h.addWidget(self.janelas);b=QPushButton('Ajuda da seção');b.clicked.connect(self.ajuda);h.addWidget(b)
        self.projeto.activated.connect(self.escolher_projeto);self._carregar_projetos();self.tabs.currentChanged.connect(self.guardar_secao);self.tabs.setCurrentIndex(min(int(self.settings.value('navegacao/secao',0)),self.tabs.count()-1))
        self.timer=QTimer(self);self.timer.setInterval(2500);self.timer.timeout.connect(self.atualizar);self.timer.start();self.mudar_nivel(self.nivel.currentText())
    def ocupado(self):return self.app.ocupado or self.app.geo._executando or self.app.atividades.em_execucao() or bool(self.app.wg and self.app.wg.ocupado)
    def _carregar_projetos(self):
        self.projeto.clear();self.projeto.addItem('Projeto não identificado',None)
        for p in self.projetos.dados['projetos']:self.projeto.addItem(p['nome']+' · '+p['uuid'][:8],p['uuid'])
        self.projeto.setCurrentIndex(max(0,self.projeto.findData(self.projetos.dados['ativo'])))
    def criar_projeto(self):
        if self.ocupado() or not self.app.resolver() or not self.app.geo.resolver_pendencias() or not self.app.resolver_configuracao_wg():return
        nome,ok=QInputDialog.getText(self,'Criar projeto de trabalho','Nome do projeto (identidade UUID será criada)')
        if ok and nome.strip():self.projetos.criar(nome);self._carregar_projetos();self.atualizar()
    def abrir_projeto(self):self.projeto.showPopup()
    def escolher_projeto(self,i):
        uid=self.projeto.itemData(i)
        if not uid:return
        if self.ocupado() or not self.app.resolver() or not self.app.geo.resolver_pendencias() or not self.app.resolver_configuracao_wg():self._carregar_projetos();return
        self.projetos.ativar(uid);self.atualizar()
    def mudar_nivel(self,t):
        self.settings.setValue('navegacao/nivel',t)
        if hasattr(self,'preparacao'):self.tabs.setTabVisible(self.tabs.indexOf(self.preparacao),t=='Guiado')
        for l in self.findChildren(QLabel):
            if l.property('wna/ajuda_curta'):l.setVisible(t=='Guiado')
        self.atualizar()
    def guardar_secao(self,n):self.settings.setValue('navegacao/secao',n)
    def atualizar(self):
        if not hasattr(self,'progresso'):return
        if self.ocupado():self.pendencias.setText('Atividade em andamento. Acompanhe etapas e cancelamento em Janelas / painéis.');return
        if self.pendencias.text().startswith('Atividade em andamento.'):self.pendencias.clear()
        try:self._fatos=fatos(self.app);self._requisitos=avaliar(self._fatos);self._recomendado=recomendar(self._requisitos)
        except Exception as e:self.pendencias.setText('Contexto não verificado: '+str(e));return
        nomes={'gis':'Auditoria GIS','wg':'Base WaterGEMS','espacial':'Referência espacial','compatibilidade':'Compatibilidade do projeto','correspondencia':'Correspondências GIS × WG','integrada':'Investigação integrada'};self.progresso.setRowCount(len(nomes))
        for i,(k,n) in enumerate(nomes.items()):
            r=self._requisitos[k];self.progresso.setItem(i,0,QTableWidgetItem(n));it=QTableWidgetItem(r.estado.value);it.setToolTip(r.motivo);self.progresso.setItem(i,1,it)
        self.progresso.resizeColumnsToContents();self.recomendacao.setText('Próxima ação: '+FERRAMENTAS[self._recomendado][0]);p=self.projetos.atual();c=self._fatos.get('contexto',{});self.contexto.setText('Projeto de trabalho: '+(p['nome'] if p else 'não identificado')+'\nModelo: '+str(c.get('modelo','nenhum'))+' · Cenário: '+str(c.get('cenario','não selecionado'))+' · Active Topology: '+str(c.get('alternativa','não resolvida'))+'\nVersão: '+str(c.get('versao','nenhuma'))[:12]+' · Perspectiva: '+str(c.get('perspectiva','não selecionada'))+' · Investigação: '+str(c.get('investigacao','nenhuma')))
        for k,b in self.acoes.items():
            ok,faltas=disponibilidade(k,self._requisitos);b.setText(FERRAMENTAS[k][0]+('' if ok else ' · preparar requisitos…'))
        self.ultima.setVisible(bool(p and p.get('ultima')))
        # Catálogo não é prova de validação. Verificação de abertura ocorre ao
        # selecionar; nenhuma base de outro projeto vira ativa por coincidência.
        self._registros=self.app.catalogo.listar_opcional();refs={(r['uuid'],r['tipo']) for r in (p or {}).get('bases',[])};rs=[r for r in self._registros if not p or (r['uuid'],r['tipo']) in refs];self._visiveis=rs;self.tabela.setRowCount(len(rs))
        for i,r in enumerate(rs):
            for j,x in enumerate((r['nome'],r['tipo'],r.get('versao'),r.get('cenario'),'Disponível — conferir ao abrir' if Path(r['base']).is_file() else 'Ausente — localizar')):self.tabela.setItem(i,j,QTableWidgetItem(str(x)))
        self.tabela.resizeColumnsToContents()
        if hasattr(self,'preparacao') and self.tabs.currentWidget() is self.preparacao:self.preparacao.atualizar()
        if self.pendente:
            ok,faltas=disponibilidade(self.pendente,self._requisitos);self.pendencias.setText('Pronto para retomar.' if ok else 'Para '+FERRAMENTAS[self.pendente][0].lower()+':\n'+'\n'.join(r.motivo for r in faltas));self.retomar.setVisible(True);self.retomar.setEnabled(ok);self.retomar.setText('Retomar: '+FERRAMENTAS[self.pendente][0])
    def acionar(self,chave):
        if self.ocupado():self.app.atividades.exibir();return
        self.atualizar();ok,faltas=disponibilidade(chave,self._requisitos)
        if chave in ('espacial','correspondencia','integrar') and self._fatos.get('wg',{}).get('incorporada'):
            self.pendente=chave
            if QMessageBox.question(self,'Recuperar fonte WaterGEMS','A topologia incorporada permite consultar esta investigação. Para preparar outra integração ou validação, recupere explicitamente a base WaterGEMS correspondente. Abrir o catálogo?',QMessageBox.Ok|QMessageBox.Cancel,QMessageBox.Cancel)==QMessageBox.Ok:self.app.catalogar('TOPOLOGIA_WG')
            return
        if not ok:
            self.pendente=chave;self.pendencias.setText('Para '+FERRAMENTAS[chave][0].lower()+':\n'+'\n'.join(r.motivo for r in faltas));self.retomar.show();self.retomar.setEnabled(False)
            if faltas:
                r=faltas[0];m=QMessageBox(self);m.setWindowTitle('Preparar requisito');m.setText(r.motivo);m.setInformativeText('Sua configuração será preservada. Depois volte à Central e use Retomar.');novo=m.addButton('Preparar / abrir etapa',QMessageBox.AcceptRole);m.addButton(QMessageBox.Cancel);m.exec_()
                if m.clickedButton()==novo:self.executar(r.acao)
            return
        self.pendente=None;self.retomar.hide();self.executar(chave)
    def executar(self,chave):
        a=self.app
        if chave=='gis':a.operacao_gis(0);a.janelas.mostrar('gis')
        elif chave=='continuar_gis':a.catalogar('AUDITORIA_GIS')
        elif chave=='preparar_wg':a.bases()
        elif chave=='continuar':a.catalogar('INTEGRADA') if not a.painel_atual() else a.janelas.mostrar('integrada')
        elif chave=='topologia':
            if a.painel_atual():a.painel.abrir_legado()
            else:a.bases();a.wg.consultar()
        elif chave in ('espacial','correspondencia','integrar'):
            a.bases();a.wg.tabs.setCurrentIndex(2 if chave=='espacial' else 1)
            if chave=='espacial':a.wg.assistente_espacial()
            elif chave=='correspondencia':a.wg.previsualizar()
            else:a.wg.integrar()
        elif chave=='historico':a.catalogar()
        elif chave in ('corredores','ilhas'):a.abrir_topologia(chave)
        elif chave=='cenarios':a.abrir_cenarios()
        elif chave in ('selection_sets','relatorio'):
            if a.painel:a.painel.abrir_selection_sets() if chave=='selection_sets' else a.painel.abrir_relatorio()
    def retomar_operacao(self):
        if self.pendente:self.acionar(self.pendente)
    def retomar_ultima(self):
        p=self.projetos.atual();r=(p or {}).get('ultima')
        if not r:return
        candidato=next((x for x in self.app.catalogo.listar_opcional() if x['uuid']==r['uuid'] and x['tipo']==r['tipo'] and x['base']==r['base']),None)
        if not candidato:QMessageBox.information(self,'Localizar última base','Referência preservada, mas arquivo não localizado no catálogo. Use Bases / versões → Catálogo para relocalizar por UUID.');return
        validacao=validar_registro(candidato)
        if not validacao['valido']:QMessageBox.warning(self,'Base não recuperada',validacao['erro']);return
        self.app.abrir_registro(candidato);self.atualizar()
    def abrir_registro(self):
        n=self.tabela.currentRow()
        if n<0:return
        r=self._visiveis[n];v=validar_registro(r)
        if not v['valido']:QMessageBox.warning(self,'Base não aberta',v['erro']+' Use o catálogo para localizar novamente.');return
        if self.app.abrir_registro(r):self.projetos.vincular(r)
        self.atualizar()
    def ajuda(self):QMessageBox.information(self,'Como continuar','Prepare GIS e WaterGEMS em qualquer ordem. Consulte o grafo sem GIS; valide CRS e correspondências apenas para integração espacial. Reabra resultados existentes para continuar. Alterar o cenário exige a base correspondente e não transfere decisões.')
