"""Etapas guiadas: uma única configuração efetiva nos formulários existentes."""
from qgis.PyQt.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QTableWidget,QTableWidgetItem,QGroupBox,QPlainTextEdit,QScrollArea
from qgis.PyQt.QtCore import Qt
from .contexto_trabalho import fatos
from .dependencias import avaliar

class PreparacaoGuiada(QScrollArea):
    def __init__(self,central):
        super().__init__(central);self.central=central;self.app=central.app;self.setWidgetResizable(True);corpo=QWidget();self.setWidget(corpo);v=QVBoxLayout(corpo);self.etapa=QComboBox();self.etapa.addItems(['1 · Objetivo da auditoria GIS','2 · Dados GIS / utilizar auditoria concluída','3 · Modelo, cenário e Active Topology','4 · Referência espacial e correspondências','5 · Conferir e iniciar investigação']);v.addWidget(self.etapa);self.etapa.currentIndexChanged.connect(self.atualizar)
        self.orientacao=QLabel();self.orientacao.setWordWrap(True);v.addWidget(self.orientacao);self.estado=QLabel();self.estado.setWordWrap(True);v.addWidget(self.estado)
        self.tabela=QTableWidget(0,2);self.tabela.setHorizontalHeaderLabels(['Item','Configuração efetiva / estado']);self.tabela.setEditTriggers(QTableWidget.NoEditTriggers);self.tabela.setMinimumHeight(190);v.addWidget(self.tabela,1)
        self.acoes=QHBoxLayout();v.addLayout(self.acoes);self.botoes=[]
        for n in range(3):b=QPushButton();self.botoes.append(b);self.acoes.addWidget(b)
        self.avancados=QGroupBox('Informações avançadas — configuração original completa');self.avancados.setCheckable(True);self.avancados.setChecked(False);av=QVBoxLayout(self.avancados);self.detalhes=QPlainTextEdit();self.detalhes.setReadOnly(True);self.detalhes.hide();av.addWidget(self.detalhes);self.avancados.toggled.connect(self.detalhes.setVisible);v.addWidget(self.avancados)
        h=QHBoxLayout();v.addLayout(h)
        for nome,delta in [('Voltar',-1),('Próxima etapa',1)]:b=QPushButton(nome);b.clicked.connect(lambda checked=False,d=delta:self.etapa.setCurrentIndex(max(0,min(4,self.etapa.currentIndex()+d))));h.addWidget(b)
        self.atualizar()
    def atualizar(self,*args):
        import json
        a=self.app;n=self.etapa.currentIndex();f=fatos(a);rs=avaliar(f);g=a.geo
        textos=[('Escolha o objetivo','TRANSICAO procura mudança de região; PERIMETRO examina travessias individuais. Extremidades, tangências e continuidade são indícios espaciais, sem criar conexões.'),('Selecione ou recupere dados GIS','Use uma auditoria concluída sem reprocessá-la ou configure redes, polígonos, chaves, modos, CRS e tolerâncias. As mesmas opções avançadas continuam no formulário GIS.'),('Prepare ou recupere WaterGEMS','Pode ser feito antes da auditoria GIS. O cenário selecionado define sua Active Topology; um cenário base não é a união dos filhos. Consulta topológica não exige validação espacial.'),('Confira referência e correspondência','Para integrar, utilize somente referência espacial válida e campos GIS escolhidos explicitamente. CRS validado não comprova conectividade hidráulica.'),('Confira e continue','A publicação da investigação será confirmada pelo fluxo existente, após as provas. Voltar entre etapas não recalcula nem apaga configurações.')];titulo,descricao=textos[n];self.orientacao.setText(titulo+'\n'+descricao);self.estado.setText(' | '.join({'gis':'Auditoria GIS','wg':'WaterGEMS','espacial':'Referência espacial','correspondencia':'Correspondência','integrada':'Investigação'}[k]+': '+r.estado.value for k,r in rs.items() if k in ('gis','wg','espacial','correspondencia','integrada')))
        form=g.formulario();linhas=[]
        if n<2:
            linhas=[('Auditoria',form['nome'] or 'Não nomeada'),('Projeto GIS',form['projeto'] or 'Não informado'),('Tolerância geométrica (m)',form['tolerancia']),('Continuidade (m)',form['continuidade']),('Busca / extensão do local (m)',str(form['busca'])+' / '+str(form['extensao'])),('Resultado',rs['gis'].estado.value)]
            for t in (g.redes,g.limites):
                for l in range(t.rowCount()):
                    if t.item(l,0).checkState()==Qt.Checked:linhas.append(('Entrada selecionada',t.item(l,1).text()))
            comandos=[('Criar nova auditoria GIS',lambda:self.central.executar('gis')),('Utilizar auditoria existente',lambda:a.catalogar('AUDITORIA_GIS')),('Configurar / conferir no formulário',lambda:a.janelas.mostrar('gis'))]
        elif n==2:
            c=f.get('contexto',{});linhas=[('Modelo',c.get('modelo','Não selecionado')),('Cenário',c.get('cenario','Não selecionado')),('Cenário pai',c.get('pai','Não determinado')),('Cadeia efetiva de Active Topology',c.get('alternativa','Não resolvida')),('Perspectiva',c.get('perspectiva','Não selecionada')),('Versão',c.get('versao','Não recuperada'))];comandos=[('Preparar modelo',a.bases),('Utilizar base existente',lambda:a.catalogar('TOPOLOGIA_WG')),('Consultar cenário e alternativas',lambda:a.abrir_cenarios())]
        elif n==3:
            linhas=[('Referência espacial',rs['espacial'].estado.value),('Correspondência',rs['correspondencia'].estado.value),('Compatibilidade de projeto',rs['compatibilidade'].estado.value)];comandos=[('Validar referência espacial',lambda:self.central.acionar('espacial')),('Conferir campos e exemplos',lambda:self.central.acionar('correspondencia')),('Abrir configuração WaterGEMS',a.bases)]
        else:
            linhas=[({'gis':'Auditoria GIS','wg':'Base WaterGEMS','espacial':'Referência espacial','correspondencia':'Correspondência','compatibilidade':'Compatibilidade','integrada':'Investigação'}[k],r.estado.value) for k,r in rs.items()];comandos=[('Criar investigação integrada',lambda:self.central.acionar('integrar')),('Continuar investigação salva',lambda:a.catalogar('INTEGRADA')),('Rever configurações',lambda:self.etapa.setCurrentIndex(1))]
        self.tabela.setRowCount(len(linhas))
        for i,(k,x) in enumerate(linhas):self.tabela.setItem(i,0,QTableWidgetItem(str(k)));self.tabela.setItem(i,1,QTableWidgetItem(str(x)))
        self.tabela.resizeColumnsToContents();self.tabela.horizontalHeader().setStretchLastSection(True);self.detalhes.setPlainText(json.dumps(dict(gis=form,contexto=f.get('contexto')),ensure_ascii=False,indent=2,default=str))
        for b,(texto,fn) in zip(self.botoes,comandos):
            try:b.clicked.disconnect()
            except TypeError:pass
            b.setText(texto);b.clicked.connect(lambda checked=False,acao=fn:acao())
