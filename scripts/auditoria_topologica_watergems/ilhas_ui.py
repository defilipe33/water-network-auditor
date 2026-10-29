"""Ilhas e origens: investigação sobre snapshots, usando workers e revisões existentes."""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,QComboBox,QCheckBox,QTableWidget,QTableWidgetItem,QMessageBox,QInputDialog,QDoubleSpinBox,QFileDialog)
from qgis.PyQt import sip
from auditoria_fronteiras.ui_comum import adaptar_janela
from auditoria_fronteiras.atividade import sistema
from . import ilhas,ilhas_persistencia as dados,ilhas_investigacao as inv
from .terminais_ui import SeletorTerminais
from .restricoes_ui import RestricoesPercurso


class IlhasDialog(QDialog):
    def __init__(self,painel):
        super().__init__(painel);self.painel=painel;self.modo='ESTRUTURAL';self.resultado=None;self.worker=None;self._ctx=None;self._candidatos=None;self.registro=None;self.gerado_config=None;self.setWindowTitle('ILHAS SEM ORIGEM');self.resize(900,680)
        v=QVBoxLayout(self);v.addWidget(QLabel('REDES SEM CAMINHO ATÉ ORIGEM DE ABASTECIMENTO'));f=QFormLayout();v.addLayout(f);self.origens=QComboBox()
        for t,k in [('Todos os Reservoirs elegíveis','RESERVOIRS'),('Reservoirs e Tanks elegíveis','RESERVOIRS_TANKS'),('Apenas origens selecionadas','SELECIONADAS'),('Origens personalizadas','PERSONALIZADAS')]:self.origens.addItem(t,k)
        f.addRow('Origens consideradas',self.origens);self.tanks=QCheckBox('Incluir Tanks como hipótese explícita, sem presumir disponibilidade permanente');f.addRow(self.tanks);self.restrita=QCheckBox('Comparar com TODAS_VALVULAS_ABERTAS + Active Topology e restrições');self.restrita.setChecked(True);f.addRow(self.restrita)
        self.seletor=SeletorTerminais(self,'Origens escolhidas · clique, seleção QGIS, Label ou ID','#008a69');v.addWidget(self.seletor);self.restricoes=RestricoesPercurso(self);v.addWidget(self.restricoes);self.restrita.toggled.connect(self.restricoes.setVisible)
        for b in self.restricoes.findChildren(QPushButton):
            if b.text()=='Comparar e destacar diferenças no mapa':b.hide()
        self.percentual=QDoubleSpinBox();self.percentual.setRange(.01,100);self.percentual.setValue(1);self.percentual.setSuffix(' % da rede');self.limiar_tubos=QDoubleSpinBox();self.limiar_tubos.setRange(0,1e8);self.limiar_tubos.setDecimals(0);self.limiar_tubos.setSpecialValueText('Sem limite absoluto');self.limiar_m=QDoubleSpinBox();self.limiar_m.setRange(0,1e10);self.limiar_m.setSpecialValueText('Sem limite absoluto');self.limiar_m.setSuffix(' m');f.addRow('Prioridade alta por participação',self.percentual);f.addRow('Ou quantidade configurada',self.limiar_tubos);f.addRow('Ou comprimento configurado',self.limiar_m)
        h=QHBoxLayout();v.addLayout(h)
        for t,fn in [('Identificar ilhas',self.calcular),('Salvar e integrar diagnósticos',self.salvar),('Recuperar análise',self.recuperar),('Comparar versões/análises',self.comparar)]:b=QPushButton(t);b.clicked.connect(fn);h.addWidget(b)
        self.estado=QLabel('Estrutural: conectividade fraca cadastrada, incluindo inativos. Restrita: alcance dirigido na hipótese selecionada. Nenhuma delas comprova abastecimento real.');self.estado.setWordWrap(True);v.addWidget(self.estado)
        self.incluir_orfaos=QCheckBox('Incluir grupos sem tubulações (nós/dispositivos órfãos)');v.addWidget(self.incluir_orfaos);self.incluir_orfaos.toggled.connect(lambda:self.preencher() if self.resultado else None)
        self.tabela=QTableWidget(0,8);self.tabela.setHorizontalHeaderLabels(['Ilha','Perspectiva','Tubos','Junctions','Dispositivos','Comprimento (m)','Prioridade sugerida','Regiões relacionadas']);self.tabela.setSelectionBehavior(QTableWidget.SelectRows);self.tabela.setSelectionMode(QTableWidget.SingleSelection);self.tabela.setEditTriggers(QTableWidget.NoEditTriggers);v.addWidget(self.tabela,1);self.tabela.itemSelectionChanged.connect(self.destacar)
        h=QHBoxLayout();v.addLayout(h)
        for t,fn in [('Aproximar ilha',self.aproximar),('Analisar / resolver ocorrência',self.analisar_caso),('Exportar para WaterGEMS',self.exportar),('Origem → todos alcançáveis: exportar',self.exportar_alcancaveis),('Salvar inventário CSV',self.csv)]:b=QPushButton(t);b.clicked.connect(fn);h.addWidget(b)
        f=QFormLayout();v.addLayout(f);self.raio=QDoubleSpinBox();self.raio.setRange(.01,10000);self.raio.setValue(10);self.raio.setSuffix(' m');f.addRow('Busca de candidatos geométricos',self.raio);b=QPushButton('Investigar candidatos / referências / bloqueios');b.clicked.connect(self.candidatos);v.addWidget(b);self.cands=QTableWidget(0,4);self.cands.setHorizontalHeaderLabels(['Tipo','Elemento da ilha','Outro elemento','Distância (m) / motivo']);self.cands.setMaximumHeight(130);v.addWidget(self.cands);b=QPushButton('Criar local manual no candidato escolhido');b.clicked.connect(self.local_manual);v.addWidget(b);self.comparacao_tabela=QTableWidget(0,5);self.comparacao_tabela.setHorizontalHeaderLabels(['Ilha anterior','Ilhas atuais','Situação','Tubos antes / depois','Nós antes / depois']);self.comparacao_tabela.setMaximumHeight(150);self.comparacao_tabela.hide();v.addWidget(self.comparacao_tabela);b=QPushButton('Exportar comparação completa JSON');b.clicked.connect(self.exportar_comparacao);v.addWidget(b);b=QPushButton('Fechar');b.clicked.connect(self.close);v.addWidget(b);adaptar_janela(self);self.tabela.setMinimumHeight(200);sistema(painel).vincular(self)
        self.origens.currentIndexChanged.connect(self.tipo_origem);self.tipo_origem()
    def tipo_origem(self):self.seletor.setVisible(self.origens.currentData() in ('SELECIONADAS','PERSONALIZADAS'))
    def cfg(self):
        el=self.painel.pacote['topologia']['modelo']['elementos'];selecionadas=[dict(t,uid=el[t['id']]['uid'],tipo=el[t['id']]['tipo']) for t in self.seletor.valores()];prio=dict(percentual_alta=self.percentual.value())
        if self.limiar_tubos.value():prio['tubos_alta']=self.limiar_tubos.value()
        if self.limiar_m.value():prio['comprimento_alta_m']=self.limiar_m.value()
        return dict(origens=self.origens.currentData(),selecionadas=selecionadas,incluir_tanks=self.tanks.isChecked(),comparar_restricoes=self.restrita.isChecked(),restricoes=self.restricoes.config(),prioridade=prio)
    def calcular(self):
        try:c=ilhas.configuracao(self.cfg())
        except Exception as e:QMessageBox.warning(self,'Confira as origens',str(e));return
        pacote=self.painel.pacote;base=self.painel.base;ctx=self._ctx
        def trabalho(cancelar,progresso):
            def checkpoint(t,n,total):
                if cancelar():raise InterruptedError('Conferência cancelada')
                progresso(0,t)
            contexto=ctx or ilhas.Contexto(pacote,checkpoint);chave=contexto.assinatura(c);cache=dados.carregar(base,pacote,assinatura=chave)
            r=cache or ilhas.analisar(pacote,c,contexto,lambda t,n,total:progresso(0,t),cancelar);return contexto,r,bool(cache)
        def pronto(v):
            self._ctx,self.resultado,cache=v;self.gerado_config=c;self._candidatos=None;self.preencher();self.estado.setText(self.estado.text()+(' · Resultado persistido compatível reutilizado.' if cache else ' · Calcule candidatos sob demanda e salve para incorporar os diagnósticos.'))
        self.worker=sistema(self.painel).executar_thread('Identificando redes sem caminho até origem','Grafo completo',trabalho,pronto,lambda e:self.estado.setText(e+' · análise anterior preservada'))
    def preencher(self):
        r=self.resultado;self.tabela.setSortingEnabled(False);vs=[v for v in r['ilhas'] if v['tubos'] or self.incluir_orfaos.isChecked()];self.tabela.setRowCount(len(vs))
        for n,v in enumerate(sorted(vs,key=lambda v:(-len(v['tubos']),v['uid']))):
            for k,x in enumerate((v['nome'],v['visao'],len(v['tubos']),v['junctions'],v['dispositivos'],v['comprimento_m'] if v['comprimento_m'] is not None else 'Indeterminado',v['prioridade'],'; '.join(v['regioes']))):
                item=QTableWidgetItem();item.setData(Qt.DisplayRole,x);item.setData(Qt.UserRole,v);item.setToolTip(v['motivo']+'\n'+v['criterio_prioridade']);self.tabela.setItem(n,k,item)
        self.tabela.setSortingEnabled(True);self.tabela.sortItems(2,Qt.DescendingOrder);self.tabela.resizeColumnsToContents();o=r['origens_info'];self.estado.setText(f"{r['estado']} · {o['encontradas']} origens encontradas / {o['utilizadas']} utilizadas. "+r.get('motivo',str(r.get('contagens',{})))+'\n'+ '\n'.join(r['avisos']+o['avisos']))
        if self.tabela.rowCount():self.tabela.selectRow(0)
    def atual(self):
        n=self.tabela.currentRow();return self.tabela.item(n,0).data(Qt.UserRole) if n>=0 else None
    def destacar(self):
        v=self.atual()
        if not v or not self.resultado:return
        if getattr(self,'_ilha_candidatos',None)!=v['uid']:self.cands.setRowCount(0);self._linhas_candidatos=[];self._ilha_candidatos=v['uid']
        if not self.painel.pacote['resultado']['meta']['parametros'].get('espacial_habilitado'):self.estado.setText('Inventário topológico disponível; valide CRS/unidades para destaques e proximidade.');return
        c=next(c for c in ilhas.casos(self.painel.pacote,dict(self.resultado,ilhas=[v])));self.painel.mapa.destacar(c);self.destacar_terminais(False)
    def destacar_terminais(self,limpar=True):
        m=self.painel.mapa
        if limpar:m.limpar()
        for t in (self.resultado or {}).get('origens',[]):
            g=(self.painel.pacote.get('geometrias') or {}).get(t['id'])
            if g:m.adicionar(g,'#008a69',foco=False)
    def aproximar(self):self.estado.setText(self.painel.mapa.aproximar())
    def salvar(self,apos=None):
        if not self.resultado:return
        if self.cfg()!=self.gerado_config:QMessageBox.warning(self,'Recalcule a análise','Origens/regras foram alteradas. Recalcule antes de salvar; resultados anteriores preservados.');return
        if not self.painel.resolver_formularios(ignorar_ilhas=True):return
        p=self.painel.pacote;r=self.resultado;base=self.painel.base
        def pronto(r):
            self.resultado=r;self.painel.revisao_atualizada();self.estado.setText('Análise salva e diagnósticos integrados. Revisões e versões anteriores preservadas.');
            if apos:apos()
        self.worker=sistema(self.painel).executar_thread('Salvando inventário de ilhas','Transação no GeoPackage integrado',lambda cancelar,progresso:dados.salvar(base,p,r,cancelado=cancelar),pronto,lambda e:self.estado.setText(e+' · resultados anteriores preservados'))
    def recuperar(self):
        rs=dados.listar(self.painel.base,self.painel.pacote)
        if not rs:self.estado.setText('Nenhuma análise de ilhas persistida nesta investigação.');return
        nomes=[r['nome']+' · '+r['data_utc']+' · '+r['uid'][:8] for r in rs];nome,ok=QInputDialog.getItem(self,'Análises de ilhas','Escolha a análise',nomes,0,False)
        if ok:
            r=dados.carregar(self.painel.base,self.painel.pacote,rs[nomes.index(nome)]['uid'])
            if not r:QMessageBox.warning(self,'Outra versão','Análise histórica de outra versão topológica; abra sua investigação de origem.');return
            dados.ativar(self.painel.base,self.painel.pacote,r['uid']);self.resultado=r;self.carregar_cfg(r['config']);self.gerado_config=self.cfg();self.preencher();self.painel.revisao_atualizada()
    def carregar_cfg(self,c):
        self.origens.setCurrentIndex(self.origens.findData(c['origens']));self.tanks.setChecked(c['incluir_tanks']);self.restrita.setChecked(c['comparar_restricoes']);self.seletor.limpar()
        for t in c['selecionadas']:
            e=self.painel.pacote['topologia']['modelo']['elementos'].get(t['id'],{});self.seletor.adicionar([dict(t,label=e.get('label'))])
        self.restricoes.carregar(c['restricoes']);self.percentual.setValue(c['prioridade'].get('percentual_alta',1));self.limiar_tubos.setValue(c['prioridade'].get('tubos_alta',0));self.limiar_m.setValue(c['prioridade'].get('comprimento_alta_m',0))
    def atual_valido(self):
        if self.resultado and self.cfg()!=self.gerado_config:
            QMessageBox.warning(self,'Configuração pendente','Os resultados correspondem à configuração anterior. Recalcule ou recupere a análise salva antes de utilizar estes resultados.');return False
        return bool(self.resultado)
    def analisar_caso(self):
        if not self.atual_valido():return
        v=self.atual()
        if not v:return
        if not self.resultado.get('uid'):self.salvar(self.analisar_caso);return
        if not self.painel.resolver_formularios():return
        modo='ESTRUTURAL' if v['visao']=='ESTRUTURAL' else 'TODAS_VALVULAS_ABERTAS';self.painel.modo.setCurrentIndex(self.painel.modo.findData(modo));self.painel.categoria.setCurrentIndex(self.painel.categoria.findData('SEM_CAMINHO_ATE_ORIGEM'));self.painel.fila.setCurrentIndex(self.painel.fila.findData('TODOS'));self.painel.selecionar_uid(v['uid']);self.painel.anotar();self.painel.show();self.painel.raise_()
    def exportar(self):
        if not self.atual_valido():return
        v=self.atual()
        if not v:return
        if not self.resultado.get('uid'):self.salvar(self.exportar);return
        from .exportacao_watergems_ui import ExportarWatergems
        self.registro=inv.registro_exportacao(self.painel.pacote,self.resultado,v);self._exportacao=ExportarWatergems(self);self._exportacao.show()
    def exportar_alcancaveis(self):
        if not self.atual_valido():return
        if not self.resultado:return
        from .exportacao_watergems_ui import ExportarWatergems
        v='RESTRITA' if 'RESTRITA' in self.resultado['alcance'] else 'ESTRUTURAL'
        try:self.registro=inv.registro_alcancaveis(self.painel.pacote,self.resultado,v);self._exportacao=ExportarWatergems(self);self._exportacao.show()
        except Exception as e:QMessageBox.warning(self,'Alcance indisponível',str(e))
    def candidatos(self):
        if not self.atual_valido():return
        v=self.atual()
        if not v:return
        p=self.painel.pacote;r=self.resultado;raio=self.raio.value();indice=self._candidatos if self._candidatos and self._candidatos.visao==v['visao'] else None
        def trabalho(cancelar,progresso):
            idx=indice or inv.Candidatos(p,r,v['visao']);return idx,idx.procurar(v,raio,cancelado=cancelar)
        def pronto(result):
            self._candidatos,result=result;self._linhas_candidatos=result['candidatos'];self.cands.setRowCount(len(result['candidatos']))
            for n,c in enumerate(result['candidatos']):
                for k,x in enumerate((c['tipo'],c['ilha_elemento'],c['outro'],c.get('distancia_m') if c.get('distancia_m') is not None else c['motivo'])):self.cands.setItem(n,k,QTableWidgetItem(str(x)))
            self.estado.setText(('Proximidade indisponível: valide CRS/unidades. ' if not result['espacial_disponivel'] else '')+'Candidatos investigativos, sem criar conexões. '+str(result['omitidos'])+' resultados adicionais omitidos pelo limite explícito; refine o raio.')
        self.worker=sistema(self.painel).executar_thread('Investigando candidatos da ilha','CRS métrico validado',trabalho,pronto,lambda e:self.estado.setText(e))
    def local_manual(self):
        n=self.cands.currentRow()
        if n<0:return
        c=self._linhas_candidatos[n]
        if c.get('x') is None:QMessageBox.information(self,'Sem ponto comprovado','Use Adicionar local pelo mapa; nenhuma posição será inventada.');return
        from .ferramentas_investigacao_ui import DialogoLocal
        d=DialogoLocal(self.painel,dict(x=c['x'],y=c['y'],crs=self.painel.pacote['dossie']['contexto']['parametros']['crs']));d.navegar=False;d.titulo.setText('Investigar candidato de ilha sem origem');d.obs.setPlainText(c['motivo'])
        from .conjuntos_investigacao import vinculo_wg
        el=self.painel.pacote['topologia']['modelo']['elementos'];refs=[vinculo_wg(self.painel.pacote,i,'CANDIDATO_INVESTIGATIVO') for i in (c['ilha_elemento'],c.get('outro')) if i in el and el[i].get('excluido') is False];d.adicionar(refs,True);d.exec_()
    def comparar(self):
        if not self.atual_valido():return
        if not self.resultado.get('uid'):self.salvar(self.comparar);return
        if not self.resultado:return
        path,_=QFileDialog.getOpenFileName(self,'Investigações anteriores','','GeoPackage (*.gpkg)')
        if not path:return
        from .saidas_integracao import reabrir
        p=self.painel.pacote;r=self.resultado
        def trabalho(cancelar,progresso):
            anterior=reabrir(path);a=dados.carregar(path,anterior)
            if not a:raise ValueError('A investigação selecionada não possui análise de ilhas ativa')
            from .comparacao_decisoes import salvar_comparacao
            x=inv.comparar(anterior,a,p,r);salvar_comparacao(self.painel.base,p,x,path);return x
        def pronto(x):
            self._comparacao=x;self.comparacao_tabela.show();self.comparacao_tabela.setRowCount(min(200,len(x['linhas'])))
            for n,l in enumerate(x['linhas'][:200]):
                for k,v in enumerate((l.get('anterior'),'; '.join(l['atuais']),l['classe'],str(l.get('tubos_antes'))+' / '+str(l.get('tubos_depois')),str(l.get('nos_antes'))+' / '+str(l.get('nos_depois')))):self.comparacao_tabela.setItem(n,k,QTableWidgetItem(str(v)))
            self.comparacao_tabela.resizeColumnsToContents();self.estado.setText('Comparação persistida no histórico existente: '+x['estado']+'. Primeiros 200 registros; exportação JSON conserva todos. Ausência não comprova correção; nenhuma revisão foi transferida.')
        self.worker=sistema(self.painel).executar_thread('Comparando ilhas entre versões','Identidades técnicas e conjuntos',trabalho,pronto,lambda e:self.estado.setText(e))
    def exportar_comparacao(self):
        if not getattr(self,'_comparacao',None):return
        path,_=QFileDialog.getSaveFileName(self,'Comparação completa','','JSON (*.json)')
        if path:
            import json
            try:
                with open(path,'x',encoding='utf8') as f:json.dump(self._comparacao,f,ensure_ascii=False,indent=2)
            except Exception as e:QMessageBox.warning(self,'Comparação não exportada',str(e))

    def csv(self):
        if not self.atual_valido():return
        if not self.resultado:return
        p,_=QFileDialog.getSaveFileName(self,'Inventário de ilhas','','CSV (*.csv)')
        if not p:return
        import csv
        try:
            with open(p,'x',encoding='utf-8-sig',newline='') as f:
                w=csv.writer(f,delimiter=';');w.writerow(['UUID','ILHA','VISAO','TUBOS','JUNCTIONS','DISPOSITIVOS','COMPRIMENTO_M','PRIORIDADE','MOTIVO','REGIOES'])
                for v in self.resultado['ilhas']:w.writerow([v['uid'],v['nome'],v['visao'],len(v['tubos']),v['junctions'],v['dispositivos'],v['comprimento_m'],v['prioridade'],v['motivo'],'; '.join(v['regioes'])])
        except Exception as e:QMessageBox.warning(self,'Inventário não exportado',str(e))
    def criterios_estruturados(self):return self.resultado or {}
    def tem_edicoes(self):return bool(self.resultado and not self.resultado.get('uid'))
    def resolver(self):
        if not self.tem_edicoes():return True
        x=QMessageBox.question(self,'Análise de ilhas não salva','Salvar antes de trocar o contexto?',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Cancel)
        if x==QMessageBox.Cancel:return False
        if x==QMessageBox.Discard:self.resultado=None;return True
        self.salvar();return False
    def closeEvent(self,e):
        if self.worker and not sip.isdeleted(self.worker) and self.worker.isRunning():QMessageBox.information(self,'Operação em andamento','Aguarde ou cancele pelo painel Atividade.');e.ignore();return
        if self.resultado and not self.resultado.get('uid'):
            x=QMessageBox.question(self,'Análise não salva','Salvar antes de fechar?',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Cancel)
            if x==QMessageBox.Cancel:e.ignore();return
            if x==QMessageBox.Save:self.salvar(self.close);e.ignore();return
        self.seletor.fechar_captura();self.restricoes.seletor.fechar_captura();e.accept()
