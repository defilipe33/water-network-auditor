"""Preferências e exceções de percurso, usando os seletores e histórico existentes."""
from copy import deepcopy
import json
from pathlib import Path
from qgis.PyQt.QtCore import Qt,QLocale
from qgis.PyQt.QtWidgets import (QGroupBox,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,
    QComboBox,QLabel,QPushButton,QTableWidget,QTableWidgetItem,QCheckBox,QInputDialog,QMessageBox,QFileDialog)
from .terminais_ui import SeletorTerminais
from . import restricoes_percurso as rp,conjuntos_investigacao as st


class SeletorEquipamentos(SeletorTerminais):
    def catalogo(self):
        rows=[dict(id=i,uid=e['uid'],label=e.get('label'),tipo=e['tipo'],porta='*') for i,e in self.pacote['topologia']['modelo']['elementos'].items() if e.get('familia')=='DISPOSITIVO' and e.get('excluido') is False]
        return rows,{r['id']:[r] for r in rows}


class RestricoesPercurso(QGroupBox):
    def __init__(self,dono):
        super().__init__('RESTRIÇÕES DE PERCURSO',dono);self.dono=dono;self.excecoes={};self.estados={};self.ausentes={};self._perfil=None;self.registro=None;self._contexto=rp.contexto(self.pacote)
        self.setCheckable(True);self.setChecked(False);v=QVBoxLayout(self);self.corpo=QWidget();v.addWidget(self.corpo);self.corpo.hide();self.toggled.connect(self.corpo.setVisible);v=QVBoxLayout(self.corpo);f=QFormLayout();v.addLayout(f)
        self.perfis=QComboBox();f.addRow('Perfil',self.perfis);self._recarregar_perfis();self.perfis.currentIndexChanged.connect(self.escolher_perfil)
        self.regras={}
        for tipo in rp.categorias(self.pacote):
            c=QComboBox();c.addItems(rp.ACOES);f.addRow('Bombas / boosters ('+tipo+')' if tipo in ('StandardPump','VariableSpeedPumpBattery') else tipo,c);self.regras[tipo]=c
        self.criterio=QComboBox();self.criterio.addItem('Menos equipamentos evitados; depois o critério de caminho','LEXICOGRAFICA');self.criterio.addItem('Somente o critério de caminho (EVITAR apenas informativo)','CUSTO');f.addRow('Otimização',self.criterio)
        self.bloquear=QCheckBox('Bloquear fechados/indisponíveis com estado validado ou hipótese manual');f.addRow(self.bloquear)
        self.informe=QLabel('PERMITIR não remove barreiras da perspectiva. EVITAR usa ordem lexicográfica, sem penalidade hidráulica. Bombas/boosters são elementos do modelo, não polígonos próximos. Estados efetivos e controles ainda não validados.');self.informe.setWordWrap(True);v.addWidget(self.informe)
        avancado=QGroupBox('Exceções individuais / hipóteses de estado');avancado.setCheckable(True);avancado.setChecked(False);av=QVBoxLayout(avancado);conteudo=QWidget();av.addWidget(conteudo);conteudo.hide();avancado.toggled.connect(conteudo.setVisible);v.addWidget(avancado);av=QVBoxLayout(conteudo)
        self.seletor=SeletorEquipamentos(dono,'Selecionar equipamentos por tabela, Label, ID ou mapa','#b817c8');av.addWidget(self.seletor)
        h=QHBoxLayout();av.addLayout(h);self.acao=QComboBox();self.acao.addItems(rp.ACOES);h.addWidget(self.acao);self.estado=QComboBox();self.estado.addItem('Sem hipótese de estado',None)
        for e in rp.ESTADOS:self.estado.addItem(e+' (informação manual / hipótese)',e)
        h.addWidget(self.estado);b=QPushButton('Aplicar aos equipamentos escolhidos');b.clicked.connect(self.aplicar);av.addWidget(b)
        self.tabela=QTableWidget(0,5);self.tabela.setHorizontalHeaderLabels(['ID','Label','Tipo','Regra individual','Estado / origem']);self.tabela.setMaximumHeight(150);av.addWidget(self.tabela);b=QPushButton('Remover regras/estados das linhas selecionadas');b.clicked.connect(self.remover);av.addWidget(b)
        h=QHBoxLayout();v.addLayout(h)
        for nome,fn in [('Salvar / renomear perfil',self.salvar),('Excluir perfil',self.excluir),('Importar perfil JSON',self.importar),('Exportar perfil JSON',self.exportar)]:
            b=QPushButton(nome);b.clicked.connect(fn);h.addWidget(b)
        b=QPushButton('Comparar e destacar diferenças no mapa');b.clicked.connect(self.destacar);v.addWidget(b);self.comparacao=QTableWidget(0,3);self.comparacao.setHorizontalHeaderLabels(['Medida','Sem restrições adicionais','Com restrições']);self.comparacao.setMaximumHeight(170);v.addWidget(self.comparacao)

    @property
    def pacote(self):return self.dono.painel.pacote
    def _recarregar_perfis(self):
        self.perfis.blockSignals(True);self.perfis.clear()
        for n in ('Sem restrições adicionais','Evitar PRVs','Sem boosters / bombas','Evitar equipamentos de controle','Restrições personalizadas'):self.perfis.addItem(n,n)
        for r in st.atuais(self.dono.painel.base,self.pacote,'PERFIL_RESTRICOES'):self.perfis.addItem(r['dados']['nome']+' · '+r['obj_uid'][:8],r)
        self.perfis.blockSignals(False)
    def config(self):
        return dict(regras=dict(self.ausentes,**{t:w.currentText() for t,w in self.regras.items()}),excecoes=list(self.excecoes.values()),estados=list(self.estados.values()),otimizacao=self.criterio.currentData(),bloquear_indisponiveis=self.bloquear.isChecked(),perfil=deepcopy(self._perfil),contexto=deepcopy(self._contexto))
    def carregar(self,c):
        c=c or {};self._contexto=c.get('contexto',rp.contexto(self.pacote));self.excecoes={int(r['id']):deepcopy(r) for r in c.get('excecoes',[])};self.estados={int(r['id']):deepcopy(r) for r in c.get('estados',[])};self._perfil=c.get('perfil');self.ausentes={t:a for t,a in c.get('regras',{}).items() if t not in self.regras}
        for t,w in self.regras.items():
            acao=c.get('regras',{}).get(t,'PERMITIR')
            if w.findText(acao)<0:w.addItem(acao)
            w.setCurrentText(acao)
        criterio=c.get('otimizacao','LEXICOGRAFICA')
        if self.criterio.findData(criterio)<0:self.criterio.addItem('Critério a conferir: '+str(criterio),criterio)
        self.criterio.setCurrentIndex(self.criterio.findData(criterio));self.bloquear.setChecked(c.get('bloquear_indisponiveis',False));self.preencher()
        indice=next((i for i in range(self.perfis.count()) if self._perfil and isinstance(self.perfis.itemData(i),dict) and self.perfis.itemData(i)['obj_uid']==self._perfil['uid'] and self.perfis.itemData(i)['uid']==self._perfil['revisao']),None)
        self.registro=self.perfis.itemData(indice) if indice is not None else None
        if indice is None and self._perfil:
            self.perfis.addItem('Perfil histórico · '+self._perfil['uid'][:8]+' / '+self._perfil['revisao'][:8],None);indice=self.perfis.count()-1
        if indice is None:indice=4 if any(a!='PERMITIR' for a in c.get('regras',{}).values()) or self.excecoes or self.estados else 0
        self.perfis.blockSignals(True);self.perfis.setCurrentIndex(indice);self.perfis.blockSignals(False)
    def escolher_perfil(self):
        p=self.perfis.currentData()
        if p is None:return
        self.registro=p if isinstance(p,dict) else None
        if isinstance(p,dict):
            c=deepcopy(p['dados']['restricoes']);c['perfil']=dict(uid=p['obj_uid'],revisao=p['uid'],topo_uid=p['topo_uid']);self.carregar(c);self.registro=p
        else:
            regras={t:'EVITAR' if p=='Evitar equipamentos de controle' and t in ('PRV','TCV','FCV','PBV','PSV','GPV') or p=='Evitar PRVs' and t=='PRV' else 'BLOQUEAR' if p=='Sem boosters / bombas' and t in ('StandardPump','VariableSpeedPumpBattery') else 'PERMITIR' for t in self.regras};self.carregar(dict(regras=regras));self.perfis.blockSignals(True);self.perfis.setCurrentIndex(self.perfis.findData(p));self.perfis.blockSignals(False)
    def aplicar(self):
        for t in self.seletor.terminais:
            r=rp.referencia(self.pacote,t['id']);self.excecoes[r['id']]=dict(r,acao=self.acao.currentText())
            if self.estado.currentData():self.estados[r['id']]=dict(r,estado=self.estado.currentData(),origem='MANUAL')
        self.seletor.limpar();self.preencher()
    def preencher_item(self,n,c,v):
        i=QTableWidgetItem(str(v));i.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable);i.setToolTip(str(v));self.tabela.setItem(n,c,i)
    def preencher(self):
        ids=sorted(set(self.excecoes)|set(self.estados));self.tabela.setRowCount(len(ids))
        for n,i in enumerate(ids):
            r=self.excecoes.get(i) or self.estados[i];e=self.estados.get(i,{})
            for k,v in enumerate((i,r.get('label'),r['tipo'],self.excecoes.get(i,{}).get('acao','Regra da categoria'),e.get('estado','')+' / '+e.get('origem',''))):self.preencher_item(n,k,v)
        self.tabela.resizeColumnsToContents()
        try:
            rp.normalizar(self.pacote,self.config());self.informe.setText('Regras investigativas; EVITAR minimiza passagens antes do custo. Estados manuais são hipóteses. Tipos ausentes conservados no perfil: '+(', '.join(self.ausentes) or 'nenhum')+'. Controles operacionais não validados.')
        except ValueError as e:self.informe.setText(str(e))
    def remover(self):
        for n in {i.row() for i in self.tabela.selectedIndexes()}:
            chave=int(self.tabela.item(n,0).text());self.excecoes.pop(chave,None);self.estados.pop(chave,None)
        self.preencher()
    def salvar(self):
        nome,ok=QInputDialog.getText(self,'Salvar perfil','Nome do perfil',text=self.registro['dados']['nome'] if self.registro else 'Restrições personalizadas')
        if not ok:return
        try:
            uid,h=rp.salvar_perfil(self.dono.painel.base,self.pacote,nome,self.config(),self.registro,modo=self.dono.modo);self._perfil=dict(uid=uid,revisao=h,topo_uid=rp.contexto(self.pacote)['topo_uid']);self._recarregar_perfis();self.perfis.setCurrentIndex(next(i for i in range(self.perfis.count()) if isinstance(self.perfis.itemData(i),dict) and self.perfis.itemData(i)['obj_uid']==uid))
        except Exception as e:QMessageBox.warning(self,'Perfil não salvo',str(e))
    def excluir(self):
        if not self.registro:return
        if QMessageBox.question(self,'Excluir perfil','Retirar este perfil da lista? O histórico e os corredores que o utilizaram serão preservados.',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        try:rp.salvar_perfil(self.dono.painel.base,self.pacote,self.registro['dados']['nome'],self.registro['dados']['restricoes'],self.registro,True,self.dono.modo);self.registro=None;self._recarregar_perfis();self.escolher_perfil()
        except Exception as e:QMessageBox.warning(self,'Perfil preservado',str(e))
    def importar(self):
        p,_=QFileDialog.getOpenFileName(self,'Importar perfil','','JSON (*.json)')
        if not p:return
        try:
            c=json.loads(Path(p).read_text(encoding='utf8'));self.carregar(c);self.registro=None;rp.normalizar(self.pacote,c)
        except Exception as e:QMessageBox.warning(self,'Confira o perfil importado',str(e)+'\nRegras incompatíveis permanecem visíveis e bloqueiam o cálculo até serem conferidas ou removidas.')
    def exportar(self):
        p,_=QFileDialog.getSaveFileName(self,'Exportar perfil','','JSON (*.json)')
        if not p:return
        try:
            c=rp.normalizar(self.pacote,self.config())
            with Path(p).open('x',encoding='utf8') as f:json.dump(c,f,ensure_ascii=False,indent=2)
        except Exception as e:QMessageBox.warning(self,'Perfil não exportado',str(e))
    def apresentar(self,r):
        c=r.get('comparacao_restricoes',{});a,b=c.get('sem_restricoes',{}),c.get('com_restricoes',{});linhas=[('Comprimento da união (m)','comprimento_m'),('Tubulações distintas','tubulacoes'),('Dispositivos','dispositivos'),('Destinos alcançados','destinos_alcancados'),('Destinos inalcançáveis','destinos_inalcancaveis'),('Componentes da seleção','componentes')];self.comparacao.setRowCount(len(linhas))
        for n,(titulo,k) in enumerate(linhas):
            for j,v in enumerate((titulo,a.get(k),b.get(k))):
                item=QTableWidgetItem('Indeterminado' if v is None else QLocale().toString(v,'f',2) if isinstance(v,float) else str(v));item.setToolTip(str(v));self.comparacao.setItem(n,j,item)
        extras=[('Equipamentos evitados em relação à referência',c.get('equipamentos_evitados',[])),('EVITAR, mas utilizados',c.get('evitados_utilizados',[])),('Tubulações adicionadas',c.get('adicionados',[])),('Tubulações removidas',c.get('removidos',[]))]
        self.comparacao.setRowCount(len(linhas)+len(extras))
        for n,(titulo,ids) in enumerate(extras,len(linhas)):
            for j,v in enumerate((titulo,'—',len(ids))):
                item=QTableWidgetItem(str(v));item.setToolTip('; '.join(str(self.pacote['topologia']['modelo']['elementos'].get(i,{}).get('label'))+' ['+str(i)+']' for i in ids));self.comparacao.setItem(n,j,item)
        self.comparacao.resizeColumnsToContents();self.comparacao.setToolTip('Equipamentos evitados: '+str(c.get('equipamentos_evitados',[]))+'\nUsados apesar de EVITAR: '+str(c.get('evitados_utilizados',[]))+'\nAdicionados: '+str(c.get('adicionados',[]))+'\nRemovidos: '+str(c.get('removidos',[]))+'\nEstado desconhecido não implica aberto ou fechado.')
    def destacar(self):
        if not self.pacote['resultado']['meta']['parametros'].get('espacial_habilitado'):
            self.dono.estado.setText('Comparação topológica disponível. Valide CRS/unidades para destacar diferenças no mapa.');return
        c=self.dono.criterios_estruturados().get('comparacao_restricoes',{});m=self.dono.painel.mapa;m.limpar()
        for chave,cor,tracejado in [('comuns','#1464dc',False),('adicionados','#00aaaa',False),('removidos','#cc4422',True)]:
            for i in c.get(chave,[]):
                g=(self.pacote.get('geometrias') or {}).get(i)
                if g:m.adicionar(g,cor,tracejado)
        self.dono.destacar_terminais(False);self.dono.estado.setText('Comparação: azul = comuns; ciano = adicionados; vermelho tracejado = removidos. Sem zoom automático. Alternativa topológica não comprova viabilidade hidráulica.')
