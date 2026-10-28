"""Formulário cotidiano sem aprovações e editor tipado de filtros por ocorrência."""
from copy import deepcopy
import json
from qgis.PyQt.QtCore import Qt,pyqtSignal
from qgis.PyQt.QtWidgets import (QWidget,QGroupBox,QVBoxLayout,QFormLayout,QHBoxLayout,QLabel,QComboBox,QPlainTextEdit,QPushButton,QLineEdit,QTreeWidget,QTreeWidgetItem,QMessageBox,QTextBrowser)
from auditoria_fronteiras.atividade import acompanhada,falha
from . import operacional as op
from .filtros import OPERADORES,RELACOES

class FormResultado(QGroupBox):
    def __init__(self,painel):
        super().__init__('RESULTADO DA ANÁLISE',painel);self.painel=painel;self.chave=None;self.head=None;self._baseline=None;self.caso=None
        v=QVBoxLayout(self);f=QFormLayout();v.addLayout(f);self.situacao=QLabel('Selecione uma ocorrência');f.addRow(self.situacao)
        self.resultado=QComboBox();self.resultado.addItem('Sem resultado selecionado',None)
        for r in op.RESULTADOS:self.resultado.addItem(r,r)
        f.addRow('Resultado',self.resultado);self.motivo=QComboBox();self.motivo.setEditable(True);self.motivo.addItem('');self.motivo.addItems(op.MOTIVOS);f.addRow('Motivo opcional',self.motivo)
        self.observacoes=QPlainTextEdit();self.observacoes.setMaximumHeight(95);self.observacoes.setPlaceholderText('Observação opcional. Também pode ser salva sem escolher um resultado.');f.addRow('Observações',self.observacoes)
        self.prioridade=QComboBox();self.prioridade.addItem('Usar prioridade sugerida',None)
        for p in op.PRIORIDADES:self.prioridade.addItem(p,p)
        f.addRow('Prioridade de trabalho',self.prioridade);self.criterio=QLabel();self.criterio.setWordWrap(True);f.addRow(self.criterio)
        linha=QHBoxLayout();v.addLayout(linha);self.salvar_botao=QPushButton('SALVAR');self.proxima_botao=QPushButton('Salvar e próxima');linha.addWidget(self.salvar_botao);linha.addWidget(self.proxima_botao)
        self.salvar_botao.clicked.connect(lambda checked=False:self.salvar());self.proxima_botao.clicked.connect(lambda checked=False:self.salvar(True))
        self.aviso=QLabel('Interpretação investigativa: não comprova comportamento hidráulico e não altera o modelo.');self.aviso.setWordWrap(True);v.addWidget(self.aviso)
        self.historico_grupo=QGroupBox('Histórico desta análise');self.historico_grupo.setCheckable(True);self.historico_grupo.setChecked(False);hv=QVBoxLayout(self.historico_grupo);self.historia=QTextBrowser();self.historia.setMaximumHeight(150);self.historia.hide();hv.addWidget(self.historia);self.historico_grupo.toggled.connect(self.historia.setVisible);v.addWidget(self.historico_grupo)
        for c in (self.resultado,self.motivo,self.prioridade):c.setMinimumContentsLength(12);c.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setEnabled(False)
        self.observacoes.textChanged.connect(painel.atualizar_contexto)
        self.resultado.currentIndexChanged.connect(painel.atualizar_contexto)
        self.motivo.editTextChanged.connect(painel.atualizar_contexto)
        self.prioridade.currentIndexChanged.connect(painel.atualizar_contexto)

    def valores(self):return self.resultado.currentData(),self.motivo.currentText(),self.observacoes.toPlainText(),self.prioridade.currentData()
    def tem_edicoes(self):return self.chave is not None and self._baseline is not None and self.valores()!=self._baseline
    def carregar(self,caso,modo,forcar=False):
        chave=(caso['uid'],modo) if caso else None
        if chave==self.chave and not forcar:return
        self.chave=chave;self.caso=caso;self.modo=modo;self.setEnabled(caso is not None);self.salvar_botao.setEnabled(caso is not None);self.proxima_botao.setEnabled(caso is not None)
        if caso is None:self._baseline=None;self.situacao.setText('Selecione uma ocorrência');return
        self.head=self.painel._analises.get(chave);h=self.head or {};self.resultado.setCurrentIndex(self.resultado.findData(h.get('resultado')));self.motivo.setCurrentText(h.get('motivo',''));self.observacoes.setPlainText(h.get('observacao',''));self.prioridade.setCurrentIndex(self.prioridade.findData(h.get('prioridade_trabalho')))
        sugestao,criterio=op.sugerir(caso,self.painel.indice_atributos);self.criterio.setText('Sugestão: '+h.get('prioridade_auto',sugestao)+' · '+h.get('criterio_auto',criterio));self.situacao.setText(op.estado(h));self._baseline=self.valores();self.atualizar_historico()
    def atualizar_historico(self):
        hs=op.historico(self.painel.base,self.painel.pacote['resultado']['meta']['uid'],self.caso['uid'],self.modo)
        self.historia.setPlainText('\n\n'.join(h['data_utc']+' · '+h['resultado']+'\n'+h['motivo']+'\n'+h['observacao']+'\nPrioridade: '+(h['prioridade_trabalho'] or h['prioridade_auto']) for h in hs) or 'Sem análise investigativa salva. Anotações antigas permanecem em HISTÓRICO E PROPOSTAS.')

    @acompanhada('Salvando análise investigativa')
    def salvar(self,proxima=False,atualizar=True):
        if not self.caso:return False
        if self.head and not self.tem_edicoes():
            if proxima:self.painel.proxima()
            return True
        try:
            uid=self.caso['uid'];antigos=[c['uid'] for c in self.painel.visiveis];pos=antigos.index(uid) if uid in antigos else -1;destino=antigos[pos+1] if pos>=0 and pos+1<len(antigos) else None
            op.salvar(self.painel.base,self.painel.pacote,self.caso,self.modo,*self.valores()[:3],prioridade=self.valores()[3],esperada=self.head['uid'] if self.head else None,contexto=self.painel.indice_atributos)
            self.painel._analises=op.indice(self.painel.base,self.painel.pacote['resultado']['meta']['uid']);self.head=self.painel._analises[(uid,self.modo)];self._baseline=self.valores();self.situacao.setText(op.estado(self.head));self.atualizar_historico();self.aviso.setText('Análise salva no histórico. Nenhuma proposta criada e nenhuma alteração no WaterGEMS.')
            self.painel.atualizar_recuperacao()
            if atualizar:
                self.painel.filtrar()
                if proxima and destino:
                    row=next((i for i,c in enumerate(self.painel.visiveis) if c['uid']==destino),None)
                    if row is not None:self.painel.selecionar_uid(destino)
            return True
        except Exception as e:falha(self,e);QMessageBox.warning(self,'Análise não salva',str(e));return False
    def resolver_edicoes(self):
        if not self.tem_edicoes():return True
        r=QMessageBox.question(self,'Análise não salva','Salvar antes de mudar de ocorrência ou fechar? Cancelar preserva o formulário.',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Cancel)
        if r==QMessageBox.Cancel:return False
        if r==QMessageBox.Discard:self.carregar(self.caso,self.modo,True);return True
        return self.salvar(atualizar=False)

ROTULOS={'IGUAL':'Igual','DIFERENTE':'Diferente','MAIOR':'Maior','MENOR':'Menor','MAIOR_IGUAL':'Maior ou igual','MENOR_IGUAL':'Menor ou igual','ENTRE':'Entre','NULO':'Nulo','NAO_NULO':'Não nulo','CONTEM':'Contém','COMECA':'Começa com','TERMINA':'Termina com','LISTA':'Pertence a uma lista','VAZIO':'Vazio','VERDADEIRO':'Verdadeiro','FALSO':'Falso','ANTES':'Antes','DEPOIS':'Depois'}
RROTULOS={'RELACIONADO':'Relação identificada com o polígono','DENTRO':'Dentro do polígono','INTERSECTA':'Intersecta o polígono','NA_FRONTEIRA':'Na fronteira do polígono','LADOS_DISTINTOS':'Elementos em lados distintos','MESMA_REGIAO':'Envolve a mesma região','REGIOES_DIFERENTES':'Envolve regiões diferentes'}
class EditorFiltros(QGroupBox):
    alterado=pyqtSignal()
    def __init__(self,painel):
        super().__init__('Filtros por atributos e regiões',painel);self.painel=painel;self.contexto=painel.indice_atributos;self.setCheckable(True);self.setChecked(False);v=QVBoxLayout(self);self.conteudo=QWidget();v.addWidget(self.conteudo);self.conteudo.hide();self.toggled.connect(self.conteudo.setVisible);v=QVBoxLayout(self.conteudo);f=QFormLayout();v.addLayout(f)
        self.origem=QComboBox();self.origem.addItems(['GIS','WATERGEMS']);f.addRow('Origem',self.origem);self.camada=QComboBox();f.addRow('Camada / elemento',self.camada);self.campo=QComboBox();f.addRow('Campo',self.campo);self.operador=QComboBox();f.addRow('Operador',self.operador);self.valor=QLineEdit();self.valor2=QLineEdit();f.addRow('Valor (lista: separar por ;)',self.valor);f.addRow('Até',self.valor2)
        self.quantificador=QComboBox()
        for n,k in [('Pelo menos um elemento','QUALQUER'),('Todos os elementos','TODOS'),('Nenhum elemento','NENHUM')]:self.quantificador.addItem(n,k)
        f.addRow('Considerar',self.quantificador);self.relacao=QComboBox()
        for r in RELACOES:self.relacao.addItem(RROTULOS[r],r)
        f.addRow('Relação espacial',self.relacao);self.unidade=QLabel('Valores na unidade bruta indicada pela fonte. Nenhuma conversão implícita.');self.unidade.setWordWrap(True);v.addWidget(self.unidade)
        b=QPushButton('Recuperar geometrias verificadas dos limites');b.clicked.connect(lambda checked=False:self.recuperar());v.addWidget(b)
        b=QPushButton('Adicionar polígonos do projeto para filtrar…');b.clicked.connect(lambda checked=False:self.adicionar_poligonos());v.addWidget(b)
        b=QPushButton('Adicionar condição');b.clicked.connect(self.adicionar);v.addWidget(b)
        self.arvore=QTreeWidget();self.arvore.setHeaderLabels(['Condições / grupos E-OU']);self.arvore.setMaximumHeight(160);v.addWidget(self.arvore);linha=QHBoxLayout();v.addLayout(linha)
        for nome,fn in [('Grupo E',lambda:self.grupo('E')),('Grupo OU',lambda:self.grupo('OU')),('Remover',self.remover),('Limpar',self.limpar)]:
            b=QPushButton(nome);b.clicked.connect(lambda checked=False,fn=fn:fn());linha.addWidget(b)
        b=QPushButton('Salvar filtros desta execução e perspectiva');b.clicked.connect(lambda checked=False:self.salvar());v.addWidget(b)
        self.origem.currentIndexChanged.connect(self.camadas);self.camada.currentIndexChanged.connect(self.campos);self.campo.currentIndexChanged.connect(self.operadores);self.operador.currentIndexChanged.connect(self.controles);self.carregar({'operador':'E','condicoes':[]});self.camadas()
        for combo in (self.origem,self.camada,self.campo,self.operador,self.relacao,self.quantificador):combo.setMinimumContentsLength(12);combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    def camadas(self):
        self.camada.blockSignals(True);self.camada.clear()
        for key,c in self.contexto.camadas.items():
            if c['origem']==self.origem.currentText():self.camada.addItem(c['nome']+' — '+c['natureza']+' · '+key[-8:],key)
        self.camada.blockSignals(False);self.campos()
    def campos(self):
        self.campo.blockSignals(True);self.campo.clear()
        for c in self.contexto.campos(self.camada.currentData()):self.campo.addItem(c['nome']+' ['+c['tipo']+']',c)
        self.campo.blockSignals(False);self.relacao.setEnabled(str(self.camada.currentData()).startswith('GIS_AREA'));self.operadores()
    def operadores(self):
        c=self.campo.currentData() or {};self.operador.clear()
        for op in OPERADORES.get(c.get('tipo'),()):self.operador.addItem(ROTULOS[op],op)
        self.unidade.setText(c.get('unidade','Tipo não disponível')+' · IDs textuais mantêm zeros à esquerda. Campo ausente ou relação não comprovada gera indeterminado, não falso.');self.controles()
    def controles(self):
        op=self.operador.currentData();self.valor.setEnabled(op not in ('NULO','NAO_NULO','VAZIO','VERDADEIRO','FALSO'));self.valor2.setEnabled(op=='ENTRE')
    def carregar(self,dados):
        self.arvore.clear()
        def criar(d,parent):
            if 'condicoes' in d:
                item=QTreeWidgetItem(parent,['Grupo '+d.get('operador','E')]);item.setData(0,Qt.UserRole,dict(operador=d.get('operador','E'),condicoes=[]));item.setExpanded(True)
                for c in d['condicoes']:criar(c,item)
            else:
                c=self.contexto.camadas.get(d['camada'],{});text=c.get('nome','Fonte indisponível')+' · '+' / '.join(d['campo'])+' '+ROTULOS.get(d['operador'],d['operador'])+' '+str(d.get('valor',''))+' '+str(d.get('valor2',''))+' · '+d.get('quantificador','QUALQUER')
                if d.get('relacao')!='RELACIONADO':text+=' · '+RROTULOS.get(d.get('relacao'),'')
                item=QTreeWidgetItem(parent,[text]);item.setData(0,Qt.UserRole,d);item.setToolTip(0,text)
            return item
        criar(deepcopy(dados),self.arvore)
    def configuracao(self):
        def ler(item):
            d=deepcopy(item.data(0,Qt.UserRole))
            if 'condicoes' in d:d['condicoes']=[ler(item.child(i)) for i in range(item.childCount())]
            return d
        return ler(self.arvore.topLevelItem(0))
    def pai_grupo(self):
        it=self.arvore.currentItem() or self.arvore.topLevelItem(0)
        return it if 'condicoes' in it.data(0,Qt.UserRole) else it.parent()
    def adicionar(self):
        c=self.campo.currentData()
        if not c:return
        d=dict(camada=self.camada.currentData(),campo=c['caminho'],operador=self.operador.currentData(),valor=self.valor.text(),valor2=self.valor2.text(),quantificador=self.quantificador.currentData(),relacao=self.relacao.currentData() if self.relacao.isEnabled() else 'RELACIONADO')
        if d['operador']=='LISTA':d['valor']=self.valor.text().split(';')
        # Validar literais sem converter o conteúdo original dos atributos.
        if c['tipo']=='numero' and self.valor.isEnabled():
            from decimal import Decimal,InvalidOperation
            try:
                assert Decimal(d['valor']).is_finite()
                if d['operador']=='ENTRE':assert Decimal(d['valor2']).is_finite() and Decimal(d['valor'])<=Decimal(d['valor2'])
            except (InvalidOperation,AssertionError):QMessageBox.warning(self,'Valores do filtro','Informe números finitos e um intervalo crescente, usando ponto decimal.');return
        it=QTreeWidgetItem(self.pai_grupo(),['Nova condição']);it.setData(0,Qt.UserRole,d);self.carregar(self.configuracao());self.alterado.emit()
    def grupo(self,op):
        it=QTreeWidgetItem(self.pai_grupo(),['Grupo '+op]);it.setData(0,Qt.UserRole,dict(operador=op,condicoes=[]));self.arvore.setCurrentItem(it);it.setExpanded(True)
    def remover(self):
        it=self.arvore.currentItem()
        if it and it.parent():it.parent().removeChild(it);self.alterado.emit()
    def limpar(self):self.carregar({'operador':'E','condicoes':[]});self.alterado.emit()
    @acompanhada('Salvando filtros desta investigação')
    def salvar(self):
        try:op.salvar_filtros(self.painel.base,self.painel.pacote,self.painel.modo.currentData(),dict(self.configuracao(),fila=self.painel.fila.currentData(),resultado=self.painel.resultado_filtro.currentData()),contexto=self.contexto);self.painel.aviso.setText('Filtros salvos nesta execução e perspectiva; outras versões não são alteradas.')
        except Exception as e:falha(self,e);QMessageBox.warning(self,'Filtros não salvos',str(e));return False

    @acompanhada('Recuperando limites por assinatura')
    def recuperar(self):
        try:
            n=self.contexto.recuperar_geometrias(self.painel.legado.projeto);self.campos();self.painel.aviso.setText(f'{n} geometrias de limites recuperadas por assinatura. '+ '; '.join(self.contexto.avisos[-3:]));self.alterado.emit()
        except Exception as e:falha(self,e);QMessageBox.warning(self,'Relações espaciais',str(e));return False
    @acompanhada('Preparando polígonos de referência para filtros')
    def adicionar_poligonos(self):
        from qgis.PyQt.QtWidgets import QInputDialog
        from qgis.core import QgsWkbTypes
        camadas=[c for c in self.painel.legado.projeto.mapLayers().values() if hasattr(c,'geometryType') and c.geometryType()==QgsWkbTypes.PolygonGeometry and not c.customProperty('auditoria_fronteiras/resultado',False)]
        if not camadas:QMessageBox.information(self,'Polígonos','Nenhuma camada poligonal original disponível no projeto.');return False
        nomes=[c.name()+' · '+c.id()[-8:] for c in camadas];nome,ok=QInputDialog.getItem(self,'Polígonos de referência','Camada do projeto',nomes,0,False)
        if not ok:return False
        try:
            key=self.contexto.adicionar_poligonos(camadas[nomes.index(nome)]);self.origem.setCurrentText('GIS');self.camadas();self.camada.setCurrentIndex(self.camada.findData(key));self.painel.aviso.setText('Polígonos adicionados como referência para filtros, com transformação explícita e snapshot próprio. As fontes não foram alteradas.')
        except Exception as e:falha(self,e);QMessageBox.warning(self,'Referência não carregada',str(e));return False
