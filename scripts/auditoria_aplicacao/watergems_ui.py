from pathlib import Path
from uuid import uuid4
from qgis.PyQt.QtCore import QThread,pyqtSignal
from qgis.PyQt.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QHBoxLayout,QGridLayout,QWidget,QTabWidget,QPushButton,QLabel,QLineEdit,QComboBox,QFileDialog,QMessageBox,QCheckBox,QDoubleSpinBox,QPlainTextEdit,QApplication,QTableWidget,QTableWidgetItem,QProgressDialog,QInputDialog)
from qgis.PyQt.QtCore import Qt
from auditoria_topologica_watergems import bases
from auditoria_topologica_watergems.gerenciamento import sugestao,registros_gis
from auditoria_topologica_watergems import referencia_espacial as referencias
from auditoria_fronteiras.ui_comum import adaptar_janela
from auditoria_fronteiras.tabelas_consulta import TabelaConsulta
from .catalogo_ui import SeletorBases
from auditoria_fronteiras.atividade import sistema,etapa,Trabalho,Progresso as QProgressDialog
from qgis.PyQt import sip


class Extracao(Trabalho):
    def __init__(self,args,parent=None):
        super().__init__(lambda cancelar,progresso:bases.extrair(**args,cancelar=cancelar,progresso=progresso),parent);self.args=args


class WatergemsDialog(QDialog):
    def __init__(self,app):
        super().__init__(app.iface.mainWindow());self.app=app;self.base=None;self.anterior=None;self.fonte=None;self.trabalho=None;self.ocupado=False;self.setWindowTitle('WaterGEMS — modelo, correspondência e referência espacial');self.resize(860,650)
        self._topologia=None;self._prova=None;self._referencia_confirmada=None;self._ref_pendente=False;self._carregando=False
        v=QVBoxLayout(self);self.geo_info=QLabel();self.geo_info.setWordWrap(True);v.addWidget(self.geo_info)
        self.tabs=QTabWidget();v.addWidget(self.tabs,1)
        modelo=QWidget();self.tabs.addTab(modelo,'1 · Modelo e cenário');mv=QVBoxLayout(modelo)
        l=QGridLayout();mv.addLayout(l)
        for i,(nome,acao) in enumerate([('Selecionar .wtg.sqlite…',self.selecionar),('ABRIR BASE WATERGEMS EXISTENTE…',self.abrir_base),('ATUALIZAR BASE WATERGEMS…',self.atualizar_base)]):
            b=QPushButton(nome);b.clicked.connect(acao);l.addWidget(b,i//2,i%2)
        f=QFormLayout();mv.addLayout(f);self.identidade=QLabel('Nenhuma base selecionada');self.identidade.setWordWrap(True);f.addRow(self.identidade)
        self.nome=QLineEdit();self.projeto=QLineEdit();f.addRow('Nome amigável do modelo',self.nome);f.addRow('Município / projeto',self.projeto)
        self.cenario=QComboBox();f.addRow('Cenário-base',self.cenario)
        self.modo=QComboBox();self.modo.addItems(list(bases.MODOS)+['ESTADOS_DO_CENARIO — indisponível']);self.modo.setCurrentIndex(1);self.modo.model().item(2).setEnabled(False);f.addRow('Perspectiva',self.modo)
        ajuda=QLabel('Primeiro crie ou abra a base topológica. CRS e unidades não são necessários para consultar o grafo. A integração com o mapa só será liberada após confirmação espacial.');ajuda.setWordWrap(True);mv.addWidget(ajuda)
        self.informacao=QPlainTextEdit();self.informacao.setReadOnly(True);mv.addWidget(self.informacao,1)
        refpage=QWidget();self.tabs.addTab(refpage,'3 · CRS e unidades');rv=QVBoxLayout(refpage)
        ajuda=QLabel('CRS identifica a referência das coordenadas GIS; a unidade bruta pertence às coordenadas WaterGEMS. Selecione o CRS métrico confirmado e a conversão correta. Não deduza esses valores pelo município.\nUse evidência anterior compatível ou confira pares cadastrais, coordenadas e uma fonte independente antes de confirmar.');ajuda.setWordWrap(True);rv.addWidget(ajuda)
        b=QPushButton('VALIDAR REFERÊNCIA ESPACIAL DO WATERGEMS…');b.clicked.connect(self.assistente_espacial);rv.addWidget(b)
        self.estado_espacial=QLabel('PENDENTE · crie ou abra uma base topológica. Use o assistente para detectar dados antes de preencher opções avançadas abaixo.');self.estado_espacial.setWordWrap(True);rv.addWidget(self.estado_espacial)
        from qgis.PyQt.QtWidgets import QGroupBox
        self.opcoes_referencia=QGroupBox('Informações avançadas / evidência anterior');self.opcoes_referencia.setCheckable(True);self.opcoes_referencia.setChecked(False);rv.addWidget(self.opcoes_referencia)
        conteudo_ref=QWidget();av=QVBoxLayout(self.opcoes_referencia);av.addWidget(conteudo_ref);av_ref=QVBoxLayout(conteudo_ref);conteudo_ref.setVisible(False);self.opcoes_referencia.toggled.connect(conteudo_ref.setVisible)
        f=QFormLayout();av_ref.addLayout(f)
        self.espacial=QCheckBox('Referência espacial confirmada para esta composição do modelo');self.espacial.setEnabled(False);f.addRow(self.espacial)
        self.crs=QLineEdit();self.crs.setPlaceholderText('CRS projetado em metros, sem suposição automática')
        self.unidade=QComboBox()
        for nome,codigo in [('Não informada',None),('Metros','METRO'),('Pés internacionais','PE_INTERNACIONAL'),('Outra unidade, com fator declarado','OUTRA_DECLARADA')]:self.unidade.addItem(nome,codigo)
        f.addRow('Unidade bruta WaterGEMS',self.unidade)
        self.fator=QDoubleSpinBox();self.fator.setDecimals(10);self.fator.setRange(.000000001,1000000);self.fator.setValue(1)
        self.evidencia=QLineEdit();f.addRow('CRS',self.crs);f.addRow('Fator bruto → metro',self.fator);f.addRow('Evidência de CRS/unidade',self.evidencia)
        self.metodo=QLineEdit('Sem validação');self.metodo.setReadOnly(True);f.addRow('Método de validação',self.metodo)
        self.evidencia.setPlaceholderText('Documento, conferência independente ou validação anterior identificável')
        self.resp_evidencia=QLineEdit();f.addRow('Responsável pela confirmação',self.resp_evidencia)
        for texto,acao in [('Usar o CRS de processamento da auditoria GIS',self.usar_crs_gis),('Verificar evidência existente…',self.verificar_evidencia),('Validar correspondência espacial…',self.validar_espacial),('Consultar detalhes da validação',self.detalhes_validacao)]:
            b=QPushButton(texto);b.clicked.connect(acao);av_ref.addWidget(b)
        rv.addStretch()
        mapage=QWidget();self.tabs.insertTab(1,mapage,'2 · Correspondência GIS × Label');pv=QVBoxLayout(mapage)
        ajuda=QLabel('Selecione a coluna da camada GIS que contém o mesmo identificador utilizado como Label da tubulação no WaterGEMS. Label é o identificador de apresentação do modelo, não DomainElementID. O campo da auditoria geométrica pode ser diferente. Nada é escolhido automaticamente.');ajuda.setWordWrap(True);pv.addWidget(ajuda)
        self.mapas={};self.geo_uid=None;self.mapeamento=QTableWidget(0,5);self.mapeamento.setHorizontalHeaderLabels(['Camada GIS','CRS da entrada GIS','Campo da auditoria','Campo GIS ↔ Label','Campo WaterGEMS']);pv.addWidget(self.mapeamento,1)
        self.tolerancia=QDoubleSpinBox();self.tolerancia.setDecimals(5);self.tolerancia.setRange(0,1000);self.tolerancia.setValue(.01)
        f=QFormLayout();f.addRow('Tolerância da prova geométrica (m)',self.tolerancia);pv.addLayout(f)
        b=QPushButton('Prévia: exemplos, nulos, repetidos e correspondências…');b.clicked.connect(self.previsualizar);pv.addWidget(b)
        consultar=QPushButton('Consultar elementos, componentes e diagnósticos da base…');consultar.clicked.connect(self.consultar);v.addWidget(consultar)
        l=QHBoxLayout();v.addLayout(l)
        for nome,acao in [('Criar base / salvar validação em nova versão…',self.criar),('Comparar com versão anterior',self.comparar),('Abrir diagnósticos integrados…',self.integrar),('Cancelar processamento',self.cancelar)]:
            b=QPushButton(nome);b.clicked.connect(acao);l.addWidget(b)
        for w,sinal in [(self.crs,'textChanged'),(self.evidencia,'textChanged'),(self.fator,'valueChanged')]:getattr(w,sinal).connect(self.invalidar_prova)
        self.tolerancia.valueChanged.connect(self.invalidar_correspondencia)
        self.unidade.currentIndexChanged.connect(self.mudar_unidade)
        self.atualizar_geo()
        adaptar_janela(self)
    def atualizar_geo(self):
        d=self.app.geo.dossie
        uid=d['execucao_uid'] if d else None
        if uid!=self.geo_uid:
            self.mapeamento.setRowCount(0)
            self.mapas={};self.geo_uid=uid
        self.geo_info.setText('Auditoria GIS: nenhuma concluída selecionada.' if not d else f"Auditoria GIS: {d.get('controle_versao',{}).get('nome','Auditoria')}\n{len(d['eventos'])} eventos / {len(d['locais'])} locais; configuração preservada.")
        self.geo_info.setToolTip('Execução GIS: '+str(uid or 'nenhuma')+'\nA auditoria GIS identifica situações espaciais; a investigação integrada consulta também a conectividade cadastrada no modelo.')
        if d:self.geo_info.setText(self.geo_info.text()+f"\nProjeto: {d.get('controle_versao',{}).get('projeto') or 'não informado'} · versão: {d.get('controle_versao',{}).get('versao',1)} · CRS de processamento: {d['contexto']['parametros']['crs']}")
        if d:
            if not self.base and not self.fonte:self.projeto.setText(d.get('controle_versao',{}).get('projeto',''))
            if not self.mapas:
                for fonte in d['contexto']['fontes']:
                    if fonte.get('modo'):continue
                    c=QComboBox();c.addItem('Sem correspondência verificada',None)
                    campos=sorted({k for t in d['tubulacoes'] if t['origem']==fonte['origem'] for k in t['atributos']})
                    for k in campos:c.addItem(k,k)
                    i=self.mapeamento.rowCount();self.mapeamento.insertRow(i)
                    self.mapeamento.setItem(i,0,QTableWidgetItem(fonte['camada']));self.mapeamento.setItem(i,1,QTableWidgetItem(fonte.get('crs_origem') or 'Não informado'));self.mapeamento.setItem(i,2,QTableWidgetItem(fonte['campo_id'] or 'Não informado'));self.mapeamento.setCellWidget(i,3,c);self.mapeamento.setItem(i,4,QTableWidgetItem('Label'))
                    self.mapas[fonte['origem']]=c;c.currentIndexChanged.connect(self.invalidar_correspondencia)
            if uid!=getattr(self,'_geo_previa',None):self._prova=None;self._geo_previa=uid
    def selecionar(self,atualizacao=False):
        if self.ocupado:return
        p,_=QFileDialog.getOpenFileName(self,'Modelo salvo em disco — leitura por snapshot','','WaterGEMS (*.wtg.sqlite)')
        if not p:return
        try:
            cs,ativo=bases.cenarios_fonte(p);self.cenario.clear()
            for c in cs:self.cenario.addItem(c['nome'],c['id'])
            if self.cenario.findData(ativo)>=0:self.cenario.setCurrentIndex(self.cenario.findData(ativo))
            if not atualizacao:self.anterior=None
            self.fonte=p;self.identidade.setText(p+'\nSeleção ainda não extraída; mudanças não salvas no WaterGEMS não são capturadas.');self.base=None
            self._carregando=True;self.crs.clear();self.evidencia.clear();self.unidade.setCurrentIndex(0);self.fator.setValue(1);self._carregando=False
            self._topologia=None;self.invalidar_prova();self.informacao.setPlainText('Crie a base topológica primeiro. Depois confira correspondência e CRS/unidades; essa etapa não exige reabrir o modelo original.')
        except Exception as e:QMessageBox.warning(self,'Modelo não selecionado',str(e))
    def abrir_base(self):
        if self.ocupado:return
        seletor=SeletorBases(self.app.catalogo,self,tipo='TOPOLOGIA_WG')
        if seletor.exec_()==QDialog.Accepted:self.usar_base(seletor.selecionada['base'])
    def usar_base(self,base):
        if hasattr(self.app,'resolver') and str(base)!=self.base and not self.app.resolver():return
        try:m=bases.metadados(base)
        except Exception:
            if QMessageBox.question(self,'Base legada','Importar uma cópia preservando apenas os dados disponíveis? Campos ausentes não serão inventados.',QMessageBox.Ok|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Ok:return
            destino,_=QFileDialog.getSaveFileName(self,'Nova base para importar legado',str(sugestao(self.app.catalogo.raiz,self.projeto.text(),'TopologiaWG')),'GeoPackage (*.gpkg)')
            if not destino:return
            base=bases.importar_legado(base,destino,self.nome.text() or 'Modelo legado',self.projeto.text());m=bases.metadados(base)
        self.app.registrar_navegacao(dict(uuid=m['uuid'],tipo='TOPOLOGIA_WG',base=str(base),nome=m['nome'])) if hasattr(self.app,'registrar_navegacao') else None
        self.base=str(base);self.fonte=None;self._topologia=None;self._prova=None;self._carregando=True;self.nome.setText(m['nome']);self.projeto.setText(m['projeto'])
        self.cenario.clear();self.cenario.addItem('Cenário '+str(m['cenario']),m['cenario']);self.modo.setCurrentIndex(self.modo.findText(m['hipotese']))
        self.identidade.setText(f"{m['nome']} · v{m['versao']:03}\n{m['resumo']['componentes']} componentes estruturais / {m['resumo_potencial']['componentes']} na hipótese aberta.");self.identidade.setToolTip('Base topológica '+m['uuid']+'\n'+str(base)+'\nUma cópia persistente para consulta; o modelo original não é alterado.')
        ref=m['referencia_espacial'];self.crs.setText(ref.get('crs',''));self.fator.setValue(ref.get('fator',1));self.evidencia.setText(ref.get('fonte',''))
        unidade=ref.get('unidade_bruta') or (referencias.unidade_fator(ref['fator']) if ref else None);self.unidade.setCurrentIndex(max(0,self.unidade.findData(unidade)))
        self._carregando=False;self._ref_pendente=False;estado=referencias.estado_referencia(ref)
        self._referencia_confirmada=ref if estado['estado']=='VALIDADO' else None;self.espacial.setChecked(bool(self._referencia_confirmada))
        self.metodo.setText({'DECLARACAO_LEGADA':'Declaração preservada da base anterior','REUSO_CONTEXTUAL_CONFIRMADO':'Reaproveitamento de conteúdo tecnicamente equivalente','VERTICES_E_CONFIRMACAO_DOCUMENTAL':'Chaves únicas, vértices e confirmação documental','ASSISTENTE_METADADOS_E_VERTICES':'Metadados, unidades comparadas e aprovação técnica'}.get(estado['metodo'],'Sem validação'))
        self.estado_espacial.setText(estado['estado']+' · '+estado['metodo']+(' · declaração preservada da base anterior; confira a fonte antes de reutilizar.' if estado['legada'] else '')+'\n'+'; '.join(estado['faltas']))
        self.app.catalogo.registrar_opcional(base);self.informacao.setPlainText('Base recuperada sem extrair o modelo original. Os elementos completos só são carregados ao investigar/comparar.')
        p=getattr(self.app,'painel',None)
        if p is not None and not sip.isdeleted(p) and p._ativo and p.pacote['resultado']['meta']['topologia']['execucao_uid']!=m['uuid']:
            p.desativar();p.hide()
    def atualizar_base(self):
        if self.ocupado:return
        if not self.base:self.abrir_base()
        if not self.base:return
        self.anterior=self.base;self.selecionar(True)
    def criar(self):
        if self.ocupado or sistema(self).em_execucao():return
        if self.base:
            if self._ref_pendente:self.gravar_referencia()
            else:QMessageBox.information(self,'Base existente','Para alterar o modelo use ATUALIZAR BASE WATERGEMS. Para acrescentar CRS/unidade, valide a referência e salve uma nova versão.')
            return
        if not self.fonte or self.cenario.currentData() is None:QMessageBox.warning(self,'Fonte','Selecione um SQLite salvo.');return
        if not self.nome.text().strip() or not self.projeto.text().strip():QMessageBox.warning(self,'Identificação','Informe nome amigável e município/projeto.');return
        versao=bases.metadados(self.anterior)['versao']+1 if self.anterior else 1
        sugest=sugestao(self.app.catalogo.raiz,self.projeto.text(),'TopologiaWG',versao)
        destino,_=QFileDialog.getSaveFileName(self,'Novo GPKG — nomes livres, sem sobrescrita',str(sugest),'GeoPackage (*.gpkg)')
        if not destino:return
        if not destino.lower().endswith('.gpkg'):destino+='.gpkg'
        if Path(destino).exists():QMessageBox.warning(self,'Destino','Escolha arquivo novo.');return
        ref=None  # A primeira extração é topológica; a validação liga-se ao snapshot real.
        resumo=f"Modelo: {self.nome.text()}\nProjeto: {self.projeto.text()}\nCenário: {self.cenario.currentData()}\nHipótese: {self.modo.currentText()}\nOrigem: {self.fonte}\nDestino: {destino}\nSnapshot SQLite consistente será preservado nos arquivos técnicos. A fonte não será alterada."
        if QMessageBox.question(self,'Confirmar extração/versionamento',resumo,QMessageBox.Ok|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Ok:return
        pasta=Path(destino).parent/'_tecnicos'/uuid4().hex;pasta.parent.mkdir(parents=True,exist_ok=True)
        args=dict(fonte=self.fonte,cenario=self.cenario.currentData(),modo=self.modo.currentText(),pasta=pasta,nome=self.nome.text(),projeto=self.projeto.text(),anterior=self.anterior,referencia=ref)
        self.destino=destino;self.ocupado=True;self.trabalho=Extracao(args,self);self.trabalho.pronto.connect(self.pronto);self.trabalho.erro.connect(lambda e:self.informacao.setPlainText('Não publicado: '+e));self.trabalho.finished.connect(self.terminar)
        self._atividade=sistema(self).iniciar('Analisando topologia WaterGEMS',self.nome.text()+' · '+self.projeto.text(),self.cancelar);self.trabalho.progresso.connect(self._atividade.sinal)
        self.trabalho.detalhes.connect(lambda texto:setattr(self._atividade,'detalhes',texto))
        self.trabalho.erro.connect(lambda e:self._atividade.finalizar('CANCELADO' if self.trabalho.isInterruptionRequested() else 'ERRO',e))
        for w in (self.nome,self.projeto,self.cenario,self.modo,self.unidade,self.crs,self.fator,self.evidencia,self.tolerancia,*self.mapas.values()):w.setEnabled(False)
        self.informacao.setPlainText('Extraindo snapshot e cenários. Cancelar preserva versões anteriores.');self.trabalho.start()
    def pronto(self,dados):
        try:
            if self.anterior and not dados['sem_alteracao']:
                r=bases.comparar_contextos(bases.restaurar(self.anterior),dict(meta_base=dados['meta'],modelo=dados['modelo'],estrutural=dados['estrutural']))
                linhas=[f"{k}: {len(v)} elementos" for k,v in r['alterados'].items() if v]
                resumo=f"Elementos adicionados: {len(r['adicionados'])}\nRemovidos: {len(r['removidos'])}\n"+'\n'.join(linhas)+f"\nComponentes divididos: {r['componentes_divididos']}\nFundidos: {r['componentes_fundidos']}\nConfirmar nova versão? A anterior permanece intacta."
                if QMessageBox.question(self,'Alterações efetivamente detectadas',resumo,QMessageBox.Ok|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Ok:
                    self.informacao.setPlainText('Publicação cancelada; snapshot técnico preservado.');return
            self._atividade.atualizar('Gravando e validando nova base topológica')
            def cancelar():return self._atividade.ponto() or self.trabalho.isInterruptionRequested()
            p=bases.persistir(dados,self.destino,cancelar);self.usar_base(p)
            self.anterior=str(p)
            self.informacao.setPlainText('Conteúdo relevante inalterado; base anterior reutilizada, sem nova versão.' if dados['sem_alteracao'] else 'Nova versão validada e publicada. Fontes e versões anteriores intactas.')
            self._atividade.finalizar(mensagem='Base validada e disponível para consulta')
        except Exception as e:
            self.informacao.setPlainText('Não publicado: '+str(e));self._atividade.finalizar('CANCELADO' if self.trabalho.isInterruptionRequested() else 'ERRO',str(e))
    def terminar(self):
        if getattr(self,'_atividade',None) and self._atividade.estado in ('EM_ANDAMENTO','CANCELANDO'):self._atividade.finalizar('CANCELADO','Publicação não aplicada; versões anteriores preservadas')
        self.ocupado=False
        for w in (self.nome,self.projeto,self.cenario,self.modo,self.unidade,self.crs,self.fator,self.evidencia,self.tolerancia,*self.mapas.values()):w.setEnabled(True)
    def cancelar(self):
        if self.trabalho and not sip.isdeleted(self.trabalho) and self.trabalho.isRunning():self.trabalho.requestInterruption();self.informacao.setPlainText('Cancelamento solicitado; aguarde a etapa atual terminar.')
    def comparar(self):
        if self.ocupado:return
        if not self.base:return
        anterior=bases.metadados(self.base).get('base_anterior')
        if not anterior or not Path(anterior).exists():
            seletor=SeletorBases(self.app.catalogo,self,tipo='TOPOLOGIA_WG')
            if seletor.exec_()!=QDialog.Accepted:return
            anterior=seletor.selecionada['base']
        if Path(anterior).resolve()==Path(self.base).resolve():QMessageBox.information(self,'Comparação','Selecione duas versões distintas.');return
        self.ocupado=True
        def pronto(r):self.informacao.setPlainText(__import__('json').dumps(r,ensure_ascii=False,indent=2))
        try:
            self.trabalho=sistema(self).executar_thread('Comparando versões WaterGEMS',self.nome.text(),lambda cancelar,progresso:bases.comparar(anterior,self.base,cancelar,progresso),pronto,lambda e:QMessageBox.warning(self,'Comparação não concluída',e))
            self.trabalho.finished.connect(self.terminar)
        except Exception:self.ocupado=False;raise
    def integrar(self):
        if self.ocupado:return
        if not self.base:QMessageBox.information(self,'Primeiro passo','Crie ou abra uma base topológica antes de integrar. A criação não exige CRS.');return
        if not self._referencia_confirmada:
            j=QMessageBox(self);j.setWindowTitle('Escolha como continuar');j.setText('Integração espacial ainda não liberada. Confirme o CRS métrico, a unidade bruta, o fator e a fonte de evidência na aba CRS e unidades. Nenhum resultado espacial será criado.')
            topo=j.addButton('Continuar somente topológica',QMessageBox.AcceptRole);validar=j.addButton('Validar CRS/unidade',QMessageBox.ActionRole);j.addButton(QMessageBox.Cancel);j.exec_()
            if j.clickedButton()==topo:self.consultar()
            elif j.clickedButton()==validar:self.tabs.setCurrentIndex(2)
            return
        if self._ref_pendente and not self.gravar_referencia():return
        if not self.app.validar_geo():return
        d=self.app.geo.dossie;m=bases.metadados(self.base)
        mapa={k:c.currentData() for k,c in self.mapas.items()}
        fontes={f['origem']:f['camada'] for f in d['contexto']['fontes']}
        resumo=f"Auditoria GIS: {d['execucao_uid']} · {len(d['eventos'])} eventos / {len(d['locais'])} locais\nModelo: {m['nome']} · v{m['versao']}\nCenário: {m['cenario']}\nPerspectiva: {self.modo.currentText()}\nCRS: {self.crs.text()} · unidade: {self.unidade.currentText()} · fator: {self.fator.value()}\nFonte: {self.evidencia.text()}\n"+'\n'.join(f"{fontes.get(k,k)}: Label WG ↔ {v or 'sem mapeamento (insuficiente)'}" for k,v in mapa.items())+'\nSerão gerados componentes, correspondências, diagnósticos e investigação espacial. Estados do cenário permanecem bloqueados. Não haverá correções automáticas.'
        if QMessageBox.question(self,'Resumo antes da integração',resumo,QMessageBox.Ok|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Ok:return
        try:self.app.integrar(self.base,mapa,self.tolerancia.value(),self.modo.currentText())
        except Exception as e:QMessageBox.warning(self,'Investigação não aberta',str(e))

    def dados_referencia(self):
        return dict(crs=self.crs.text().strip(),fator=self.fator.value(),unidade_bruta=self.unidade.currentData(),fonte=self.evidencia.text().strip())
    def invalidar_correspondencia(self,*args):
        if not self._carregando:self._prova=None
    def invalidar_prova(self,*args):
        if self._carregando:return
        self._prova=None;self._referencia_confirmada=None;self._ref_pendente=False;self.espacial.setChecked(False)
        self.metodo.setText('Sem validação confirmada para estes valores')
        estado=referencias.estado_referencia(self.dados_referencia())
        self.estado_espacial.setText(('INCOMPATÍVEL' if estado['estado']=='INCOMPATIVEL' else 'PENDENTE')+' · '+('; '.join(estado['faltas']) or 'valores do formulário ainda não comprovados')+'. A base e os resultados anteriores permanecem intactos.')
    def mudar_unidade(self):
        if self._carregando:return
        u=self.unidade.currentData()
        if u in ('METRO','PE_INTERNACIONAL'):self.fator.setValue(1 if u=='METRO' else .3048)
        self.invalidar_prova()
    def usar_crs_gis(self):
        d=self.app.geo.dossie
        if not d:QMessageBox.information(self,'Cadastro GIS','Abra uma auditoria geométrica para consultar seu CRS de processamento.');return
        self.crs.setText(d['contexto']['parametros']['crs']);self.tabs.setCurrentIndex(2)
        self.informacao.setPlainText('CRS copiado da auditoria GIS, por comando explícito. Isso não confirma as unidades WaterGEMS nem a compatibilidade espacial.')
    def topologia_atual(self):
        if not self.base:raise ValueError('Crie ou abra a base topológica primeiro; não é necessário confirmar CRS para essa etapa.')
        if self._topologia is None:self._topologia=bases.restaurar(self.base)
        return self._topologia
    def verificar_evidencia(self):
        if self.ocupado:return
        try:
            t=self.topologia_atual();itens=[]
            for r in self.app.catalogo.listar(tipo='TOPOLOGIA_WG'):
                if r.get('disponivel') and r.get('modelo_uid')==t['modelo']['projeto']:
                    try:
                        if bases.metadados(r['base']).get('referencia_espacial'):itens.append(r)
                    except (ValueError,OSError):pass
            nomes=[f"{r['nome']} · v{r['versao']} · {r['uuid'][:10]}" for r in itens]+['Selecionar GPKG ou JSON de evidência…']
            nome,ok=QInputDialog.getItem(self,'Evidências disponíveis','Escolha uma referência anterior; identidade e composição serão verificadas:',nomes,0,False)
            if not ok:return
            if nomes.index(nome)<len(itens):p=itens[nomes.index(nome)]['base']
            else:
                p,_=QFileDialog.getOpenFileName(self,'Referência anterior — somente leitura',str(self.app.catalogo.raiz),'Evidência (*.gpkg *.json)')
                if not p:return
            e=referencias.ler_evidencia(p);c=referencias.compatibilidade(t['modelo'],e)
            self._evidencia_anterior=e
            if c['estado']=='INCOMPATIVEL':self.estado_espacial.setText(('VALIDADO (base atual) · candidata incompatível: ' if self._referencia_confirmada else 'INCOMPATÍVEL · ')+'; '.join(c['faltas']));QMessageBox.warning(self,'Evidência incompatível','; '.join(c['faltas'])+'. Nenhum valor foi aplicado.');return
            r=e['referencia']
            if c['estado']=='VALIDADO' and QMessageBox.question(self,'Reutilizar referência compatível',f"Mesma identidade, cenário, alternativas e conteúdo extraído.\nCRS: {r['crs']} · fator: {r['fator']}\nFonte: {r['fonte']}\nConfirmar reaproveitamento em nova versão, preservando a anterior?",QMessageBox.Ok|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Ok:return
            r=e['referencia'];self._carregando=True;self.crs.setText(r.get('crs',''));self.fator.setValue(r.get('fator',1));self.evidencia.setText(r.get('fonte') or 'Arquivo de evidência '+Path(p).name)
            self.unidade.setCurrentIndex(max(0,self.unidade.findData(r.get('unidade_bruta') or referencias.unidade_fator(r.get('fator',1)))));self._carregando=False;self.invalidar_prova()
            if c['estado']!='VALIDADO':
                self.estado_espacial.setText('PENDENTE · '+'; '.join(c['faltas'])+'. Os valores são candidatos; confira a prévia e valide novamente.');return
            self._referencia_confirmada=referencias.referencia_reutilizada(t['modelo'],e,self.resp_evidencia.text());self._ref_pendente=True;self.espacial.setChecked(True)
            self.metodo.setText('Reaproveitamento de conteúdo tecnicamente equivalente')
            self.estado_espacial.setText('VALIDADO · reaproveitamento contextual confirmado. Salve a validação em nova versão antes da integração.')
        except Exception as e:self._carregando=False;QMessageBox.warning(self,'Evidência não recuperada',str(e))
    def previsualizar(self):
        if self.ocupado:return False
        try:
            t=self.topologia_atual();d=self.app.geo.dossie
            if not d:raise ValueError('Abra uma auditoria GIS para selecionar suas colunas. A consulta topológica continua disponível.')
            mapa={k:c.currentData() for k,c in self.mapas.items()}
            if not any(mapa.values()):raise ValueError('Escolha ao menos uma coluna GIS na aba Correspondência. O campo WG é Label; não presuma igualdade com o campo da auditoria.')
            ref=self.dados_referencia();ref=ref if ref['crs'] else None
            from qgis.core import QgsCoordinateReferenceSystem,QgsUnitTypes
            if ref:
                crs=QgsCoordinateReferenceSystem(ref['crs'])
                if not crs.isValid() or crs.isGeographic() or crs.mapUnits()!=QgsUnitTypes.DistanceMeters:raise ValueError('Para comparar coordenadas escolha um CRS projetado em metros, ou deixe o CRS vazio para prévia apenas cadastral.')
            progresso=QProgressDialog('Consultando colunas e comparando candidatos…','Cancelar',0,0,self);progresso.setWindowModality(Qt.ApplicationModal);progresso.show();self.ocupado=True
            def cancelar():return progresso.wasCanceled()
            try:
                regs,avisos=registros_gis(d,mapa,ref['crs'] if ref else None,cancelar)
                prova=referencias.previa(t['modelo'],regs,ref,self.tolerancia.value());prova['avisos']=avisos
                if cancelar():raise InterruptedError('Prévia cancelada; contexto anterior preservado')
                self._prova=prova
                progresso.concluir()
            except Exception as e:progresso.falhar(e);raise
            finally:self.ocupado=False;progresso.close()
            j=QDialog(self);j.setWindowTitle('Prévia GIS × Label — não altera nem conecta elementos');j.resize(900,600);v=QVBoxLayout(j)
            aviso=QLabel('Correspondência cadastral não equivale a vínculo inequívoco sem verificação de geometria. Coordenadas e distâncias desta prévia são candidatas ao CRS/fator escolhido; a confirmação exige fonte independente. Nulos, vazios e zero permanecem distintos.');aviso.setWordWrap(True);v.addWidget(aviso)
            tabs=QTabWidget();v.addWidget(tabs,1)
            resumo=TabelaConsulta(['Camada GIS','Campo GIS','Campo WG','Total','Únicas compatíveis','Valores repetidos','Nulos','Vazios','Não encontrados','Geometria inconsistente']);resumo.preencher([[r[k] for k in ('camada','campo','campo_wg','total','unicas','repetidos','nulos','vazios','nao_encontradas','inconsistencias_geometricas')] for r in prova['camadas']]);tabs.addTab(resumo,'Contagens por camada')
            amostras=TabelaConsulta(['Camada GIS','Campo GIS','Valor GIS bruto','Label WG','DomainElementID','Situação','Erro XY (m)','X GIS','Y GIS','X WG convertido','Y WG convertido','Geometria GIS','Geometria WG bruta']);amostras.preencher(prova['amostras'])
            for c in range(7,13):amostras.tabela.setColumnHidden(c,True)
            tabs.addTab(amostras,'Amostras e coordenadas (Colunas)')
            b=QPushButton('Fechar prévia');b.clicked.connect(j.accept);v.addWidget(b);adaptar_janela(j);self._janela_previa=j;self.app.janelas.registrar('previa',j,'prévia cadastral e espacial');self.app.janelas.mostrar('previa')
            return True
        except Exception as e:QMessageBox.warning(self,'Prévia não concluída',str(e));return False
    def validar_espacial(self):
        if self.ocupado:return
        try:
            if self._prova is None:
                self.previsualizar()
                self.estado_espacial.setText('PENDENTE · examine a prévia, informe unidade/fonte e clique novamente em Validar correspondência espacial para confirmar.');return
            ref=referencias.confirmar_prova(self.topologia_atual()['modelo'],self.dados_referencia(),self._prova,self.resp_evidencia.text())
            if QMessageBox.question(self,'Confirmação técnica explícita','Conferi o CRS e a unidade em fonte independente e examinei os pares/coordenadas da prévia. A prova cadastral e geométrica é complementar e não confirma conectividade. Confirmar a referência registrada?',QMessageBox.Ok|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Ok:return
            self._referencia_confirmada=ref;self._ref_pendente=True;self.espacial.setChecked(True);self.estado_espacial.setText('VALIDADO · vértices e confirmação documental. Salve em nova versão; a base anterior permanece intacta.')
            self.metodo.setText('Chaves únicas, todos os vértices e confirmação documental')
        except Exception as e:QMessageBox.warning(self,'Referência permanece pendente',str(e))
    def detalhes_validacao(self):
        import json
        j=QDialog(self);j.setWindowTitle('Proveniência da referência espacial');j.resize(720,480);v=QVBoxLayout(j)
        t=QPlainTextEdit();t.setReadOnly(True);t.setPlainText(json.dumps(self._referencia_confirmada or self.dados_referencia(),ensure_ascii=False,indent=2));v.addWidget(t)
        b=QPushButton('Fechar');b.clicked.connect(j.accept);v.addWidget(b);adaptar_janela(j);j.show();self._detalhes_validacao=j
    def gravar_referencia(self):
        if self.ocupado or not self.base or not self._ref_pendente or not self._referencia_confirmada:return False
        try:
            m=bases.metadados(self.base);destino,_=QFileDialog.getSaveFileName(self,'Nova versão com evidência — base anterior preservada',str(sugestao(self.app.catalogo.raiz,m['projeto'],'TopologiaWG',m['versao']+1)),'GeoPackage (*.gpkg)')
            if not destino:return False
            if not destino.lower().endswith('.gpkg'):destino+='.gpkg'
            if Path(destino).exists():raise FileExistsError('Escolha um arquivo novo; a base existente não será substituída')
            self.ocupado=True
            try:p=referencias.salvar_referencia(self.base,destino,self._referencia_confirmada)
            finally:self.ocupado=False
            self.usar_base(p);self.informacao.setPlainText('Nova versão espacial validada e registrada. Elementos, eventos, grafo e versões anteriores preservados.');return True
        except Exception as e:QMessageBox.warning(self,'Validação não gravada',str(e));return False
    def consultar(self):
        if self.ocupado or not self.base:return
        from .consulta_base import ConsultaBase
        anterior=getattr(self,'consulta',None)
        if anterior and not sip.isdeleted(anterior) and anterior.base==self.base:self.app.janelas.mostrar('consulta');return
        if anterior:anterior.close()
        self.consulta=ConsultaBase(self.base,self);self.app.janelas.registrar('consulta',self.consulta,'consulta da base WaterGEMS');self.app.atividades.vincular(self.consulta);self.app.janelas.mostrar('consulta')
    def assistente_espacial(self):
        if self.ocupado:return
        anterior=getattr(self,'_assistente',None)
        if anterior and not sip.isdeleted(anterior) and anterior.isVisible():anterior.raise_();return
        if not self.base:
            QMessageBox.information(self,'Base topológica necessária','Crie ou abra a base topológica na primeira aba. O assistente examina essa versão persistida sem reextrair o modelo original.');return
        if not self.app.geo.dossie:
            QMessageBox.information(self,'Referência GIS necessária','Abra uma auditoria GIS concluída para comparar as fontes. A consulta topológica continua disponível.');return
        from .assistente_espacial import AssistenteEspacial
        try:
            self._assistente=AssistenteEspacial(self);self.app.janelas.registrar('assistente',self._assistente,'assistente espacial');self.app.atividades.vincular(self._assistente);self.app.janelas.mostrar('assistente')
        except Exception as e:QMessageBox.warning(self,'Assistente não iniciado','Não foi possível preparar o assistente: '+str(e)+'. O contexto atual e as bases anteriores foram preservados.')
    def closeEvent(self,e):
        if self.ocupado:self.cancelar();e.ignore()
        else:e.accept()
