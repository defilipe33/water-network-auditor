from pathlib import Path
from uuid import uuid4
from qgis.PyQt.QtCore import QThread,pyqtSignal
from qgis.PyQt.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QHBoxLayout,QPushButton,QLabel,QLineEdit,QComboBox,QFileDialog,QMessageBox,QCheckBox,QDoubleSpinBox,QPlainTextEdit,QApplication)
from auditoria_topologica_watergems import bases
from auditoria_topologica_watergems.gerenciamento import sugestao
from .catalogo_ui import SeletorBases


class Extracao(QThread):
    pronto=pyqtSignal(object);erro=pyqtSignal(str)
    def __init__(self,args,parent=None):super().__init__(parent);self.args=args
    def run(self):
        try:self.pronto.emit(bases.extrair(**self.args,cancelar=self.isInterruptionRequested))
        except Exception as e:self.erro.emit(str(e))


class WatergemsDialog(QDialog):
    def __init__(self,app):
        super().__init__(app.geo);self.app=app;self.base=None;self.anterior=None;self.fonte=None;self.trabalho=None;self.ocupado=False;self.setWindowTitle('Base WaterGEMS e investigação integrada');self.resize(820,720)
        v=QVBoxLayout(self);self.geo_info=QLabel();self.geo_info.setWordWrap(True);v.addWidget(self.geo_info)
        l=QHBoxLayout();v.addLayout(l)
        for nome,acao in [('Selecionar .wtg.sqlite…',self.selecionar),('ABRIR BASE WATERGEMS EXISTENTE…',self.abrir_base),('ATUALIZAR BASE WATERGEMS…',self.atualizar_base)]:
            b=QPushButton(nome);b.clicked.connect(acao);l.addWidget(b)
        f=QFormLayout();v.addLayout(f);self.identidade=QLabel('Nenhuma base selecionada');self.identidade.setWordWrap(True);f.addRow(self.identidade)
        self.nome=QLineEdit();self.projeto=QLineEdit();f.addRow('Nome amigável do modelo',self.nome);f.addRow('Município / projeto',self.projeto)
        self.cenario=QComboBox();f.addRow('Cenário-base',self.cenario)
        self.modo=QComboBox();self.modo.addItems(list(bases.MODOS)+['ESTADOS_DO_CENARIO — indisponível']);self.modo.setCurrentIndex(1);self.modo.model().item(2).setEnabled(False);f.addRow('Perspectiva',self.modo)
        self.espacial=QCheckBox('CRS e unidade confirmados por evidência');f.addRow(self.espacial)
        self.crs=QLineEdit();self.crs.setPlaceholderText('CRS projetado em metros, sem suposição automática')
        self.fator=QDoubleSpinBox();self.fator.setDecimals(10);self.fator.setRange(.000000001,1000000);self.fator.setValue(1)
        self.evidencia=QLineEdit();f.addRow('CRS',self.crs);f.addRow('Fator bruto → metro',self.fator);f.addRow('Evidência de CRS/unidade',self.evidencia)
        self.mapas={};self.geo_uid=None;self.mapeamento=QFormLayout();v.addLayout(self.mapeamento)
        self.tolerancia=QDoubleSpinBox();self.tolerancia.setDecimals(5);self.tolerancia.setRange(0,1000);self.tolerancia.setValue(.01);f.addRow('Tolerância da prova cadastral (m)',self.tolerancia)
        self.informacao=QPlainTextEdit();self.informacao.setReadOnly(True);v.addWidget(self.informacao,1)
        consultar=QPushButton('Consultar elementos, componentes e diagnósticos da base…');consultar.clicked.connect(self.consultar);v.addWidget(consultar)
        l=QHBoxLayout();v.addLayout(l)
        for nome,acao in [('Criar nova versão persistente…',self.criar),('Comparar com versão anterior',self.comparar),('Abrir diagnósticos integrados…',self.integrar),('Cancelar processamento',self.cancelar)]:
            b=QPushButton(nome);b.clicked.connect(acao);l.addWidget(b)
        self.atualizar_geo()
    def atualizar_geo(self):
        d=self.app.geo.dossie
        uid=d['execucao_uid'] if d else None
        if uid!=self.geo_uid:
            while self.mapeamento.rowCount():self.mapeamento.removeRow(0)
            self.mapas={};self.geo_uid=uid
        self.geo_info.setText('Auditoria GIS: nenhuma concluída selecionada.' if not d else f"Auditoria GIS: {d.get('controle_versao',{}).get('nome','Auditoria')} · {d['execucao_uid']}\n{len(d['eventos'])} eventos / {len(d['locais'])} locais; configuração preservada.")
        if d:
            self.projeto.setText(d.get('controle_versao',{}).get('projeto',''))
            if not self.mapas:
                for fonte in d['contexto']['fontes']:
                    if fonte.get('modo'):continue
                    c=QComboBox();c.addItem('Sem correspondência verificada',None)
                    campos=sorted({k for t in d['tubulacoes'] if t['origem']==fonte['origem'] for k in t['atributos']})
                    for k in campos:c.addItem(k,k)
                    self.mapas[fonte['origem']]=c;self.mapeamento.addRow('Label WG ↔ campo GIS / '+fonte['camada'],c)
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
        except Exception as e:QMessageBox.warning(self,'Modelo não selecionado',str(e))
    def abrir_base(self):
        if self.ocupado:return
        seletor=SeletorBases(self.app.catalogo,self,tipo='TOPOLOGIA_WG')
        if seletor.exec_()==QDialog.Accepted:self.usar_base(seletor.selecionada['base'])
    def usar_base(self,base):
        try:m=bases.metadados(base)
        except Exception:
            if QMessageBox.question(self,'Base legada','Importar uma cópia preservando apenas os dados disponíveis? Campos ausentes não serão inventados.',QMessageBox.Ok|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Ok:return
            destino,_=QFileDialog.getSaveFileName(self,'Nova base para importar legado',str(sugestao(self.app.catalogo.raiz,self.projeto.text(),'TopologiaWG')),'GeoPackage (*.gpkg)')
            if not destino:return
            base=bases.importar_legado(base,destino,self.nome.text() or 'Modelo legado',self.projeto.text());m=bases.metadados(base)
        self.base=str(base);self.nome.setText(m['nome']);self.projeto.setText(m['projeto'])
        self.cenario.clear();self.cenario.addItem('Cenário '+str(m['cenario']),m['cenario']);self.modo.setCurrentIndex(self.modo.findText(m['hipotese']))
        self.identidade.setText(f"{m['nome']} · v{m['versao']:03} · {m['uuid']}\n{m['resumo']['componentes']} componentes estruturais / {m['resumo_potencial']['componentes']} na hipótese aberta.")
        ref=m['referencia_espacial'];self.espacial.setChecked(bool(ref));self.crs.setText(ref.get('crs',''));self.fator.setValue(ref.get('fator',1));self.evidencia.setText(ref.get('fonte',''))
        self.app.catalogo.registrar(base);self.informacao.setPlainText('Base recuperada sem extrair o modelo original. Os elementos completos só são carregados ao investigar/comparar.')
    def atualizar_base(self):
        if self.ocupado:return
        if not self.base:self.abrir_base()
        if not self.base:return
        self.anterior=self.base;self.selecionar(True)
    def criar(self):
        if self.ocupado:return
        if not self.fonte or self.cenario.currentData() is None:QMessageBox.warning(self,'Fonte','Selecione um SQLite salvo.');return
        if not self.nome.text().strip() or not self.projeto.text().strip():QMessageBox.warning(self,'Identificação','Informe nome amigável e município/projeto.');return
        versao=bases.metadados(self.anterior)['versao']+1 if self.anterior else 1
        sugest=sugestao(self.app.catalogo.raiz,self.projeto.text(),'TopologiaWG',versao)
        destino,_=QFileDialog.getSaveFileName(self,'Novo GPKG — nomes livres, sem sobrescrita',str(sugest),'GeoPackage (*.gpkg)')
        if not destino:return
        if not destino.lower().endswith('.gpkg'):destino+='.gpkg'
        if Path(destino).exists():QMessageBox.warning(self,'Destino','Escolha arquivo novo.');return
        ref=dict(crs=self.crs.text(),fator=self.fator.value(),fonte=self.evidencia.text()) if self.espacial.isChecked() else None
        resumo=f"Modelo: {self.nome.text()}\nProjeto: {self.projeto.text()}\nCenário: {self.cenario.currentData()}\nHipótese: {self.modo.currentText()}\nOrigem: {self.fonte}\nDestino: {destino}\nSnapshot SQLite consistente será preservado nos arquivos técnicos. A fonte não será alterada."
        if QMessageBox.question(self,'Confirmar extração/versionamento',resumo,QMessageBox.Ok|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Ok:return
        pasta=Path(destino).parent/'_tecnicos'/uuid4().hex;pasta.parent.mkdir(parents=True,exist_ok=True)
        args=dict(fonte=self.fonte,cenario=self.cenario.currentData(),modo=self.modo.currentText(),pasta=pasta,nome=self.nome.text(),projeto=self.projeto.text(),anterior=self.anterior,referencia=ref)
        self.destino=destino;self.ocupado=True;self.trabalho=Extracao(args,self);self.trabalho.pronto.connect(self.pronto);self.trabalho.erro.connect(lambda e:self.informacao.setPlainText('Não publicado: '+e));self.trabalho.finished.connect(self.terminar)
        for w in (self.nome,self.projeto,self.cenario,self.modo,self.espacial,self.crs,self.fator,self.evidencia,self.tolerancia,*self.mapas.values()):w.setEnabled(False)
        self.informacao.setPlainText('Extraindo snapshot e cenários. Cancelar preserva versões anteriores.');self.trabalho.start()
    def pronto(self,dados):
        try:
            if self.anterior and not dados['sem_alteracao']:
                r=bases.comparar_contextos(bases.restaurar(self.anterior),dict(meta_base=dados['meta'],modelo=dados['modelo'],estrutural=dados['estrutural']))
                linhas=[f"{k}: {len(v)} elementos" for k,v in r['alterados'].items() if v]
                resumo=f"Elementos adicionados: {len(r['adicionados'])}\nRemovidos: {len(r['removidos'])}\n"+'\n'.join(linhas)+f"\nComponentes divididos: {r['componentes_divididos']}\nFundidos: {r['componentes_fundidos']}\nConfirmar nova versão? A anterior permanece intacta."
                if QMessageBox.question(self,'Alterações efetivamente detectadas',resumo,QMessageBox.Ok|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Ok:
                    self.informacao.setPlainText('Publicação cancelada; snapshot técnico preservado.');return
            p=bases.persistir(dados,self.destino,lambda:self.trabalho.isInterruptionRequested());self.usar_base(p)
            self.anterior=str(p)
            self.informacao.setPlainText('Conteúdo relevante inalterado; base anterior reutilizada, sem nova versão.' if dados['sem_alteracao'] else 'Nova versão validada e publicada. Fontes e versões anteriores intactas.')
        except Exception as e:self.informacao.setPlainText('Não publicado: '+str(e))
    def terminar(self):
        self.ocupado=False
        for w in (self.nome,self.projeto,self.cenario,self.modo,self.espacial,self.crs,self.fator,self.evidencia,self.tolerancia,*self.mapas.values()):w.setEnabled(True)
    def cancelar(self):
        if self.trabalho:self.trabalho.requestInterruption();self.informacao.setPlainText('Cancelamento solicitado; aguarde a etapa atual terminar.')
    def comparar(self):
        if self.ocupado:return
        if not self.base:return
        anterior=bases.metadados(self.base).get('base_anterior')
        if not anterior or not Path(anterior).exists():
            seletor=SeletorBases(self.app.catalogo,self,tipo='TOPOLOGIA_WG')
            if seletor.exec_()!=QDialog.Accepted:return
            anterior=seletor.selecionada['base']
        if Path(anterior).resolve()==Path(self.base).resolve():QMessageBox.information(self,'Comparação','Selecione duas versões distintas.');return
        try:
            r=bases.comparar(anterior,self.base);self.informacao.setPlainText(__import__('json').dumps(r,ensure_ascii=False,indent=2))
        except Exception as e:QMessageBox.warning(self,'Comparação',str(e))
    def integrar(self):
        if self.ocupado or not self.base:return
        if not self.app.validar_geo():return
        try:self.app.integrar(self.base,{k:c.currentData() for k,c in self.mapas.items()},self.tolerancia.value(),self.modo.currentText())
        except Exception as e:QMessageBox.warning(self,'Investigação não aberta',str(e))
    def consultar(self):
        if self.ocupado or not self.base:return
        from .consulta_base import ConsultaBase
        anterior=getattr(self,'consulta',None)
        if anterior and anterior.base==self.base:anterior.show();anterior.raise_();return
        if anterior:anterior.close()
        self.consulta=ConsultaBase(self.base,self);self.consulta.show()
    def closeEvent(self,e):
        if self.ocupado:self.cancelar();e.ignore()
        else:e.accept()
