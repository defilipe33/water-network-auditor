"""Formulários de decisão e proposta com rascunhos protegidos por contexto."""
import json
import re
from datetime import datetime
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QWidget,QVBoxLayout,QFormLayout,QHBoxLayout,QLabel,QComboBox,QLineEdit,
    QPlainTextEdit,QPushButton,QCheckBox,QTabWidget,QScrollArea,QMessageBox,QFileDialog,QDialog,QTextBrowser,QGroupBox)
from . import decisoes as db


def combo(valores):
    c=QComboBox();c.addItems(valores);return c


class AnaliseDecisao(QWidget):
    def __init__(self,painel):
        super().__init__(painel);self.painel=painel;self.chave=None;self.caso=None;self.head=None;self.prop=None;self._baseline=None;self._hipotese_preparada=False
        v=QVBoxLayout(self);self.identificacao=QLabel('Selecione uma ocorrência.');self.identificacao.setWordWrap(True);v.addWidget(self.identificacao)
        self.tabs=QTabWidget();v.addWidget(self.tabs)
        def pagina(titulo):
            scroll=QScrollArea();scroll.setWidgetResizable(True);w=QWidget();scroll.setWidget(w);self.tabs.addTab(scroll,titulo);f=QFormLayout(w);f.setFormAlignment(Qt.AlignTop);f.setLabelAlignment(Qt.AlignLeft|Qt.AlignTop);return f
        f=pagina('Decisão técnica');self.situacao=combo(db.SITUACOES);f.addRow('Situação administrativa',self.situacao)
        self.anotacao=QPlainTextEdit();self.anotacao.setMaximumHeight(95);self.anotacao.setPlaceholderText('Observação rápida: exige somente texto.');f.addRow('Anotação rápida',self.anotacao)
        b=QPushButton('Salvar anotação');b.clicked.connect(lambda:self.salvar_registro(False));f.addRow(b)
        self.preliminar=QComboBox();self.preliminar.addItem('Sem interpretação preliminar',None)
        for c in db.PRELIMINARES:self.preliminar.addItem(c,c)
        f.addRow('Classificação preliminar opcional',self.preliminar)
        b=QPushButton('Salvar conclusão preliminar e observação');b.clicked.connect(lambda:self.salvar_registro(True));f.addRow(b)
        b=QPushButton('Salvar somente andamento administrativo');b.clicked.connect(self.salvar_andamento);f.addRow(b)
        principal=f;self.avancadas=QGroupBox('CONFIRMAÇÃO TÉCNICA / EVIDÊNCIAS AVANÇADAS');self.avancadas.setCheckable(True);self.avancadas.setChecked(False);principal.addRow(self.avancadas)
        conteudo=QWidget();f=QFormLayout(conteudo);av=QVBoxLayout(self.avancadas);av.addWidget(conteudo);conteudo.setVisible(False);self.avancadas.toggled.connect(conteudo.setVisible)
        aviso=QLabel('Conclusões definitivas exigem justificativa, responsável, fonte e evidência DOCUMENTAL, OPERACIONAL ou de CAMPO. Hipóteses podem ser salvas acima como preliminares. VERIFICADO é andamento, não correção comprovada.');aviso.setWordWrap(True);f.addRow(aviso)
        self.conclusao=QComboBox();self.conclusao.addItem('Escolha explicitamente a conclusão',None)
        for c in db.CONCLUSOES:self.conclusao.addItem(c,c)
        f.addRow('Conclusão técnica',self.conclusao)
        self.justificativa=QPlainTextEdit();self.justificativa.setMaximumHeight(95);f.addRow('Justificativa / observações',self.justificativa)
        self.responsavel=QLineEdit();f.addRow('Responsável',self.responsavel)
        from qgis.core import QgsSettings
        self.operador=QgsSettings().value('auditoria_redes/operador_padrao','');self.responsavel.setText(self.operador)
        b=QPushButton('Usar este responsável como operador padrão opcional');b.clicked.connect(self.salvar_operador);f.addRow(b)
        self.fonte=combo(('',)+db.FONTES);f.addRow('Fonte da informação',self.fonte)
        self.natureza=combo(db.NATUREZAS);f.addRow('Natureza da evidência',self.natureza)
        self.evidencia=QPlainTextEdit();self.evidencia.setMaximumHeight(85);self.evidencia.setPlaceholderText('Identifique documento, consulta ao modelo, informação operacional ou verificação de campo.');f.addRow('Evidência identificada',self.evidencia)
        self.data=QLabel('Sem revisão topológica salva.');self.data.setMaximumHeight(32);self.data.setAlignment(Qt.AlignLeft|Qt.AlignTop);f.addRow('Última revisão',self.data)
        b=QPushButton('Salvar decisão no histórico');b.clicked.connect(self.salvar_decisao);f.addRow(b)
        b=QPushButton('Usar esta interpretação como hipótese preliminar');b.clicked.connect(self.usar_hipotese);f.addRow(b)
        f=pagina('Propostas');self.seletor=QComboBox();self.seletor.currentIndexChanged.connect(self.trocar_proposta);f.addRow('Proposta desta ocorrência',self.seletor)
        self.tipo=combo(db.TIPOS_PROPOSTA);f.addRow('Tipo de intervenção',self.tipo)
        self.descricao=QPlainTextEdit();self.descricao.setMaximumHeight(75);f.addRow('Descrição',self.descricao)
        self.ids=QLineEdit();self.ids.setPlaceholderText('DomainElementIDs separados por ponto e vírgula');f.addRow('Elementos envolvidos',self.ids)
        self.rotulos=QLabel();self.rotulos.setWordWrap(True);f.addRow('Labels / tipos',self.rotulos);self.ids.textChanged.connect(self.mostrar_rotulos)
        from auditoria_fronteiras.tabelas_consulta import TabelaConsulta
        self.tabela_proposta=TabelaConsulta(['Tipo','Label WaterGEMS','DomainElementID','Identificação']);f.addRow(self.tabela_proposta)
        self.elementos_confirmados=QCheckBox('Conferi as identidades dos elementos e seu papel nesta proposta');f.addRow(self.elementos_confirmados)
        self.prop_just=QPlainTextEdit();self.prop_just.setMaximumHeight(70);f.addRow('Justificativa',self.prop_just)
        self.requisitos=QPlainTextEdit();self.requisitos.setMaximumHeight(70);f.addRow('Requisitos de validação',self.requisitos)
        self.prop_resp=QLineEdit();f.addRow('Responsável',self.prop_resp)
        self.prop_evid=QPlainTextEdit();self.prop_evid.setMaximumHeight(70);f.addRow('Evidência desta alteração',self.prop_evid)
        self.prop_estado=combo(db.ESTADOS_PROPOSTA);f.addRow('Situação da proposta',self.prop_estado)
        self.confirmacao=QCheckBox('Confirmo explicitamente esta aprovação / declaração de aplicação / validação técnica');f.addRow(self.confirmacao)
        self.verificacao_manual=QCheckBox('Realizei verificação técnica adicional e identifiquei a evidência do resultado acima');f.addRow(self.verificacao_manual)
        self.validacao=QLabel('Nenhuma evidência posterior selecionada.');self.validacao.setWordWrap(True);f.addRow(self.validacao);self.validacao_uid=None
        b=QPushButton('Salvar proposta / acrescentar histórico');b.clicked.connect(self.salvar_proposta);f.addRow(b)
        b=QPushButton('Confrontar aplicação com auditoria posterior…');b.clicked.connect(self.verificar);f.addRow(b)
        f=pagina('Histórico e evidências');self.historia=QTextBrowser();self.historia.setOpenExternalLinks(False);f.addRow(self.historia)
        b=QPushButton('Registrar correspondência revisada entre versões…');b.clicked.connect(self.reconciliar);f.addRow(b)
        self.mensagem=QLabel('Revisão topológica independente da revisão espacial. Nenhuma ação escreve no WaterGEMS.');self.mensagem.setWordWrap(True);v.addWidget(self.mensagem)
        self.salvar_fixo_decisao=QPushButton('Salvar decisão no histórico');self.salvar_fixo_decisao.clicked.connect(self.salvar_decisao);v.addWidget(self.salvar_fixo_decisao)
        self.salvar_fixo_proposta=QPushButton('Salvar proposta / histórico');self.salvar_fixo_proposta.clicked.connect(self.salvar_proposta);v.addWidget(self.salvar_fixo_proposta)
        def acoes_fixas(i):self.salvar_fixo_decisao.setVisible(i==0 and self.avancadas.isChecked());self.salvar_fixo_proposta.setVisible(i==1)
        self.tabs.currentChanged.connect(acoes_fixas);acoes_fixas(0)
        self.avancadas.toggled.connect(lambda _:acoes_fixas(self.tabs.currentIndex()))
        from auditoria_fronteiras.ui_comum import configurar_controles
        configurar_controles(self)
        self.setEnabled(False)

    def valores_decisao(self):return (self.situacao.currentText(),self.conclusao.currentData(),self.justificativa.toPlainText(),self.responsavel.text(),self.fonte.currentText(),self.natureza.currentText(),self.evidencia.toPlainText())
    def valores_proposta(self):return (self.tipo.currentText(),self.descricao.toPlainText(),self.ids.text(),self.elementos_confirmados.isChecked(),self.prop_just.toPlainText(),self.requisitos.toPlainText(),self.prop_resp.text(),self.prop_evid.toPlainText(),self.prop_estado.currentText(),self.confirmacao.isChecked(),self.verificacao_manual.isChecked())
    def valores(self):return self.valores_decisao(),self.valores_proposta(),(self.anotacao.toPlainText(),self.preliminar.currentData())
    def tem_edicoes(self):return self.chave is not None and self._baseline is not None and self.valores()!=self._baseline

    def carregar(self,caso,modo,forcar=False):
        chave=(caso['uid'],modo) if caso else None
        if chave==self.chave and not forcar:return
        self.chave=chave;self.caso=caso;self.modo=modo;self.setEnabled(caso is not None)
        if not caso:self._baseline=None;self.identificacao.setText('Selecione uma ocorrência.');return
        p=self.painel.pacote;self.ig=p['resultado']['meta']['uid']
        envolvidos=caso['tubos_gis'] or caso['elementos'];amostra='; '.join(str(x)[:45] for x in envolvidos[:2])
        self.identificacao.setText(caso['titulo']+'\n'+amostra+(f' · +{len(envolvidos)-2} elementos' if len(envolvidos)>2 else ''))
        self.identificacao.setToolTip('Ocorrência '+caso['uid']+'\n'+modo+' · cenário '+str(p['topologia']['modelo']['cenario'])+'\n'+'; '.join(envolvidos)+'\nA hipótese com válvulas abertas não comprova a operação real. Identificadores completos permanecem no detalhamento.')
        hs=db.historico(self.painel.base,self.ig,caso['uid'],modo);self.head=hs[-1] if hs else None
        h=self.head or {}
        self.situacao.setCurrentText(h.get('situacao','PENDENTE'));self.conclusao.setCurrentIndex(self.conclusao.findData(h.get('conclusao')))
        self.anotacao.clear();self.preliminar.setCurrentIndex(0);self._hipotese_preparada=False
        self.justificativa.setPlainText(h.get('justificativa',''));self.responsavel.setText(h.get('responsavel') or self.operador);self.fonte.setCurrentText(h.get('fonte',''))
        self.natureza.setCurrentText(h.get('natureza','INDEFINIDO'));self.evidencia.setPlainText(h.get('evidencia',''));self.mostrar_data(h.get('data_utc'))
        for w in (self.justificativa,self.responsavel,self.fonte,self.natureza,self.evidencia):w.setStyleSheet('')
        self._propostas=db.propostas(self.painel.base,self.ig,caso['uid'],modo)
        self.seletor.blockSignals(True);self.seletor.clear();self.seletor.addItem('Nova proposta · não criada automaticamente',None)
        for pr in self._propostas:self.seletor.addItem(pr['prop_uid'][:10]+' · '+pr['atual']['tipo']+' · '+pr['atual']['situacao'],pr['prop_uid'])
        self.seletor.blockSignals(False);self.carregar_proposta(None)
        linhas=['EVIDÊNCIAS DA OCORRÊNCIA',*caso['evidencias'],'\nREVISÕES TOPOLÓGICAS']
        linhas += [f"{h['data_utc']} | {h['responsavel']} | {h['situacao']} | {h['conclusao']}\n{h['justificativa']}\n{h['fonte']} / {h['natureza']} / {h['evidencia']}\nUUID {h['rev_uid']} / anterior {h['anterior']}" for h in hs]
        for pr in self._propostas:
            linhas.append('\nPROPOSTA '+pr['prop_uid'])
            linhas += [f"{h['data_utc']} | {h['situacao']} | {h['responsavel']}\n{h['descricao']}\n{h['evidencia']}\nHistórico {h['hist_uid']} / anterior {h['anterior']}" for h in pr['historico']]
        linhas += [f"{r['data_utc']} | {r['tipo']} | {r['classificacao'] or ''}\n{r['observacao']}" for r in db.registros(self.painel.base,self.ig,caso['uid'],modo)]
        self.historia.setPlainText('\n\n'.join(linhas));self._baseline=self.valores()

    def carregar_proposta(self,uid):
        self.prop=next((p for p in self._propostas if p['prop_uid']==uid),None);h=self.prop['atual'] if self.prop else {}
        self.tipo.setCurrentText(h.get('tipo',db.TIPOS_PROPOSTA[0]));self.descricao.setPlainText(h.get('descricao',''))
        ids=[e['wg_id'] for e in h['elementos']] if h else [str(i) for i in self.caso['wg_ids']]
        self.ids.setText('; '.join(ids));self.elementos_confirmados.setChecked(bool(h.get('elementos_confirmados',False)))
        self.prop_just.setPlainText(h.get('justificativa',''));self.requisitos.setPlainText(h.get('requisitos',''));self.prop_resp.setText(h.get('responsavel',''))
        self.prop_evid.setPlainText(h.get('evidencia',''));self.prop_estado.setCurrentText(h.get('situacao','RASCUNHO'));self.confirmacao.setChecked(False)
        self.verificacao_manual.setChecked(False)
        self.validacao_uid=None;self.validacao.setText('Confronto posterior precisa ser realizado para o estado atual da proposta.')
        if self.prop:
            vs=db.validacoes(self.painel.base,self.prop['prop_uid'],h['hist_uid'])
            if vs:self.validacao_uid=vs[-1]['uid'];self.validacao.setText(vs[-1]['resultado']+' · evidência persistida; validação final é humana.')

    def trocar_proposta(self):
        if not self.caso or self._baseline is None:return
        uid=self.seletor.currentData();anterior=self.prop['prop_uid'] if self.prop else None
        if self.valores_proposta()!=self._baseline[1]:
            self.seletor.blockSignals(True);self.seletor.setCurrentIndex(self.seletor.findData(anterior));self.seletor.blockSignals(False)
            if not self.resolver_edicoes():return
            # Salvar pode reconstruir a lista; procure novamente o destino escolhido.
            self.seletor.blockSignals(True);self.seletor.setCurrentIndex(self.seletor.findData(uid));self.seletor.blockSignals(False)
        self.carregar_proposta(uid);self._baseline=(self._baseline[0],self.valores_proposta(),self._baseline[2])

    def mostrar_rotulos(self):
        if not self.caso:return
        try:
            ids=self.elementos();el=self.painel.pacote['topologia']['modelo']['elementos']
            self.rotulos.setText('; '.join(f"{i}: {el[i]['label']} / {el[i]['tipo']}" if i in el else f'{i}: NÃO IDENTIFICADO' for i in ids))
            if hasattr(self,'tabela_proposta'):self.tabela_proposta.preencher([[el.get(i,{}).get('tipo'),el.get(i,{}).get('label'),i,'Identificado' if i in el else 'Não identificado'] for i in ids])
        except ValueError:
            self.rotulos.setText('Identificadores inválidos; não serão aprovados.')
            if hasattr(self,'tabela_proposta'):self.tabela_proposta.preencher([])

    def elementos(self):return [int(t) for t in re.split(r'[,;\s]+',self.ids.text().strip()) if t]

    def salvar_decisao(self):
        if not self.caso:return False
        try:
            if self.conclusao.currentData() is None:raise ValueError('Escolha a conclusão explicitamente; use NÃO AVALIADO para salvar uma observação inicial.')
            definitiva=self.conclusao.currentData() in db.CONCLUSOES[1:6] or self.conclusao.currentData()=='NÃO APLICÁVEL'
            campos=[(self.justificativa,self.justificativa.toPlainText()),(self.responsavel,self.responsavel.text()),(self.fonte,self.fonte.currentText()),(self.evidencia,self.evidencia.toPlainText())]
            for w,t in campos:w.setStyleSheet('border: 1px solid #b53030' if definitiva and not t.strip() else '')
            self.natureza.setStyleSheet('border: 1px solid #b53030' if definitiva and self.natureza.currentText() in ('HIPOTESE','INDEFINIDO') else '')
            if definitiva and (any(not t.strip() for _,t in campos) or self.natureza.currentText() in ('HIPOTESE','INDEFINIDO')):raise ValueError('Para confirmar, complete os campos destacados e use evidência documental, operacional ou de campo. Para investigar sem comprovação, use “Usar esta interpretação como hipótese preliminar” ou salve uma anotação rápida.')
            db.salvar_decisao(self.painel.base,self.painel.pacote,self.caso,self.modo,*self.valores_decisao(),esperada=self.head['rev_uid'] if self.head else None)
            self.head=db.historico(self.painel.base,self.ig,self.caso['uid'],self.modo)[-1];self.mostrar_data(self.head['data_utc'])
            self.painel._revisoes_topologicas[(self.caso['uid'],self.modo)]=self.head
            row=self.painel.lista.currentRow()
            if row>=0:self.painel.lista.item(row,2).setText(self.head['situacao'])
            self._baseline=(self.valores_decisao(),self._baseline[1],self._baseline[2]);self.atualizar_historico();self.painel.filtrar();self.mensagem.setText('Decisão topológica acrescentada ao histórico. Revisão espacial preservada.');return True
        except Exception as e:QMessageBox.warning(self,'Decisão não salva',str(e));return False

    def salvar_proposta(self):
        if not self.caso:return False
        try:
            uid,h=db.salvar_proposta(self.painel.base,self.painel.pacote,self.caso,self.modo,self.tipo.currentText(),
                self.descricao.toPlainText(),self.prop_just.toPlainText(),self.requisitos.toPlainText(),self.prop_resp.text(),self.prop_evid.toPlainText(),
                self.elementos(),self.elementos_confirmados.isChecked(),self.prop_estado.currentText(),
                self.prop['prop_uid'] if self.prop else None,self.prop['atual']['hist_uid'] if self.prop else None,self.confirmacao.isChecked(),self.validacao_uid,self.verificacao_manual.isChecked())
            self._propostas=db.propostas(self.painel.base,self.ig,self.caso['uid'],self.modo)
            self.seletor.blockSignals(True);self.seletor.clear();self.seletor.addItem('Nova proposta',None)
            for pr in self._propostas:self.seletor.addItem(pr['prop_uid'][:10]+' · '+pr['atual']['situacao'],pr['prop_uid'])
            self.seletor.setCurrentIndex(self.seletor.findData(uid));self.seletor.blockSignals(False);self.carregar_proposta(uid)
            self._baseline=(self._baseline[0],self.valores_proposta(),self._baseline[2]);self.atualizar_historico();self.painel.filtrar();self.mensagem.setText('Proposta salva. Nenhuma alteração aplicada ao modelo.');return True
        except Exception as e:QMessageBox.warning(self,'Proposta não salva',str(e));return False

    def resolver_edicoes(self):
        if not self.tem_edicoes():return True
        escolha=QMessageBox.question(self,'Alterações topológicas não salvas','Salvar decisão e proposta alteradas antes de mudar de contexto?',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Cancel)
        if escolha==QMessageBox.Cancel:return False
        if escolha==QMessageBox.Discard:self.carregar(self.caso,self.modo,True);return True
        if (self.anotacao.toPlainText(),self.preliminar.currentData())!=self._baseline[2] and not self.salvar_registro(self.preliminar.currentData() is not None):return False
        if self.valores_decisao()!=self._baseline[0] and not self.salvar_decisao():return False
        if self.valores_proposta()!=self._baseline[1] and not self.salvar_proposta():return False
        return not self.tem_edicoes()

    def atualizar_historico(self):
        hs=db.historico(self.painel.base,self.ig,self.caso['uid'],self.modo)
        linhas=['EVIDÊNCIAS DA OCORRÊNCIA',*self.caso['evidencias'],'\nREVISÕES TOPOLÓGICAS']
        linhas += [f"{r['data_utc']} | {r['tipo']} | {r['classificacao'] or ''}\n{r['observacao']}\n{r['responsavel']}" for r in db.registros(self.painel.base,self.ig,self.caso['uid'],self.modo)]
        linhas += [f"{h['data_utc']} | {h['responsavel']} | {h['situacao']} | {h['conclusao']}\n{h['justificativa']}\n{h['fonte']} / {h['natureza']} / {h['evidencia']}\nUUID {h['rev_uid']} / anterior {h['anterior']}" for h in hs]
        for p in db.propostas(self.painel.base,self.ig,self.caso['uid'],self.modo):
            linhas.append('\nPROPOSTA '+p['prop_uid'])
            linhas += [f"{h['data_utc']} | {h['situacao']} | {h['responsavel']}\n{h['descricao']}\n{h['evidencia']}\nHistórico {h['hist_uid']} / anterior {h['anterior']}" for h in p['historico']]
        self.historia.setPlainText('\n\n'.join(linhas))

    def mostrar_data(self,data):
        self.data.setText(datetime.fromisoformat(data).astimezone().strftime('%d/%m/%Y %H:%M:%S %z') if data else 'Sem revisão topológica salva.')
        self.data.setToolTip(data or '')

    def salvar_operador(self):
        from qgis.core import QgsSettings
        self.operador=self.responsavel.text().strip();QgsSettings().setValue('auditoria_redes/operador_padrao',self.operador);self.mensagem.setText('Operador padrão opcional atualizado neste perfil.')
    def salvar_registro(self,preliminar=False):
        if not self.caso:return False
        try:
            c=self.preliminar.currentData() if preliminar else None
            if preliminar and c is None:raise ValueError('Escolha a interpretação preliminar')
            db.salvar_registro(self.painel.base,self.painel.pacote,self.caso,self.modo,self.anotacao.toPlainText(),c,self.operador)
            if preliminar and self._hipotese_preparada:
                # Os dados tentativos foram copiados integralmente para a observação.
                b=self._baseline[0];self.conclusao.setCurrentIndex(self.conclusao.findData(b[1]));self.justificativa.setPlainText(b[2]);self.responsavel.setText(b[3]);self.fonte.setCurrentText(b[4]);self.natureza.setCurrentText(b[5]);self.evidencia.setPlainText(b[6]);self.avancadas.setChecked(False);self._hipotese_preparada=False
                for w in (self.justificativa,self.responsavel,self.fonte,self.natureza,self.evidencia):w.setStyleSheet('')
            self.anotacao.clear();self.preliminar.setCurrentIndex(0);self._baseline=(self._baseline[0],self._baseline[1],('',None));self.atualizar_historico();self.painel.filtrar();self.mensagem.setText('Registro acrescentado. Não representa confirmação técnica nem altera o WaterGEMS.');return True
        except Exception as e:QMessageBox.warning(self,'Observação não salva',str(e));return False
    def usar_hipotese(self):
        if not self.justificativa.toPlainText().strip():QMessageBox.information(self,'Observação necessária','Escreva a observação que fundamenta a interpretação preliminar.');return
        c=self.conclusao.currentData();mapa={'DESCONEXÃO INTENCIONAL':db.PRELIMINARES[1],'CONEXÃO FALTANTE CONFIRMADA':db.PRELIMINARES[0],'CONEXÃO INDEVIDA CONFIRMADA':db.PRELIMINARES[2],'PROBLEMA CADASTRAL CONFIRMADO':db.PRELIMINARES[3]}
        textos=[self.justificativa.toPlainText()]
        for titulo,valor in [('Interpretação tentativa',self.conclusao.currentText()),('Responsável informado',self.responsavel.text()),('Fonte informada',self.fonte.currentText()),('Natureza',self.natureza.currentText()),('Evidência informada',self.evidencia.toPlainText())]:
            if valor.strip():textos.append(titulo+': '+valor)
        self.anotacao.setPlainText('\n'.join(textos));self.preliminar.setCurrentIndex(max(0,self.preliminar.findData(mapa.get(c))));self._hipotese_preparada=True;self.mensagem.setText('Hipótese preparada na anotação rápida; confira e salve a conclusão preliminar. Os detalhes tentativos foram copiados para o texto, sem confirmação definitiva.')
    def salvar_andamento(self):
        if not self.caso:return False
        try:
            h=self.head or {};db.salvar_decisao(self.painel.base,self.painel.pacote,self.caso,self.modo,self.situacao.currentText(),*[h.get(k,d) for k,d in [('conclusao','NÃO AVALIADO'),('justificativa',''),('responsavel',''),('fonte',''),('natureza','INDEFINIDO'),('evidencia','')]],esperada=h.get('rev_uid'))
            self.head=db.historico(self.painel.base,self.ig,self.caso['uid'],self.modo)[-1];b=list(self._baseline[0]);b[0]=self.situacao.currentText();self._baseline=(tuple(b),self._baseline[1],self._baseline[2]);self.atualizar_historico();self.painel.filtrar();self.mensagem.setText('Andamento salvo; a conclusão anterior não foi alterada.');return True
        except Exception as e:QMessageBox.warning(self,'Andamento não salvo',str(e));return False

    def verificar(self):
        if self.tem_edicoes():QMessageBox.information(self,'Salve primeiro','Salve a proposta antes de comparar versões.');return
        if not self.prop:QMessageBox.information(self,'Proposta','Selecione uma proposta salva cuja aplicação foi informada.');return
        caminho,_=QFileDialog.getOpenFileName(self,'Auditoria integrada posterior','','GeoPackage (*.gpkg)')
        if not caminho:return
        try:
            from .comparacao_decisoes import avaliar_proposta,salvar_validacao,selecionar_integracao
            novo=selecionar_integracao(caminho,self)
            if novo is None:return
            r=avaliar_proposta(self.prop,self.painel.pacote,novo)
            self.validacao_uid=salvar_validacao(self.painel.base,self.painel.pacote,self.prop,r,caminho)
            self.validacao.setText(r['resultado']+' · confronto registrado. A validação final exige confirmação humana explícita e evidência.')
            j=QDialog(self);j.setWindowTitle('Evidências do confronto posterior');j.resize(720,420);l=QVBoxLayout(j);t=QPlainTextEdit();t.setReadOnly(True)
            t.setPlainText(f"Resultado: {r['resultado']}\nCenários comparáveis: {r['cenarios_comparaveis']}\nIdentidades preservadas: {r['identidades_preservadas']}\nLigações diretas antes: {r['conexoes_diretas_antes']}\nLigações diretas depois: {r['conexoes_diretas_depois']}\nComposição alterada: {r['composicao_antes']!=r['composicao_depois']}\nNovos diagnósticos dos elementos: {len(r['novos_diagnosticos'])}\n\n{r['conclusao']}\n\nEvidência técnica completa preservada no GPKG e nas exportações.");l.addWidget(t);j.exec_()
        except Exception as e:QMessageBox.warning(self,'Confronto não registrado',str(e))

    def reconciliar(self):
        if self.tem_edicoes() or not self.head:QMessageBox.information(self,'Revisão de destino','Salve uma decisão própria desta ocorrência antes de registrar a correspondência.');return
        try:
            from qgis.PyQt.QtWidgets import QInputDialog
            from .comparacao_decisoes import reconciliar
            with db.abrir_ro(self.painel.base) as con:
                linhas=con.execute('SELECT c.comp_uid,c.ordem,c.classe,c.dados FROM IGD_CORRESPONDENCIAS c JOIN IGD_COMPARACOES p ON p.comp_uid=c.comp_uid WHERE p.ig_destino=?',(self.ig,)).fetchall()
            linhas=[l for l in linhas if self.caso['uid'] in json.loads(l[3])['destinos']]
            if not linhas:raise ValueError('Nenhuma comparação registrada aponta esta ocorrência como candidata')
            nomes=[f'{l[2]} · comparação {l[0][:10]} · item {l[1]}' for l in linhas]
            nome,ok=QInputDialog.getItem(self,'Correspondência entre versões','Selecione a relação que conferiu:',nomes,0,False)
            if not ok:return
            justificativa,ok=QInputDialog.getMultiLineText(self,'Justificativa da reconciliação','Explique a correspondência; a conclusão antiga não será copiada:')
            if not ok:return
            l=linhas[nomes.index(nome)];reconciliar(self.painel.base,l[0],l[1],self.caso['uid'],self.head['rev_uid'],self.responsavel.text(),justificativa,self.evidencia.toPlainText())
            self.mensagem.setText('Correspondência registrada com revisão própria do destino; sem transferir conclusão anterior.')
        except Exception as e:QMessageBox.warning(self,'Reconciliação não registrada',str(e))
