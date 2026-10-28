"""Exportação explícita, consultas copiáveis e conferência por CSV do WaterGEMS."""
from pathlib import Path
from uuid import uuid4
import csv,json
from qgis.PyQt.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QComboBox,QLineEdit,QCheckBox,QSpinBox,QPushButton,QTableWidget,QTableWidgetItem,QPlainTextEdit,QFileDialog,QMessageBox,QApplication)
from auditoria_fronteiras.ui_comum import adaptar_janela
from . import exportacao_watergems as ex


class ExportarWatergems(QDialog):
    def __init__(self,pai):
        super().__init__(pai);self.pai=pai;self.pacote=pai.painel.pacote;self.registro=pai.registro;self.dados=ex.preparar(self.pacote,self.registro);self.setWindowTitle('Exportar para WaterGEMS');self.resize(850,620);v=QVBoxLayout(self)
        l=QLabel('Elementos distintos do grafo: '+' · '.join(f'{t}: {n}' for t,n in self.dados['contagens'].items()));l.setWordWrap(True);v.addWidget(l)
        self.opcoes={}
        for k,n in [('lista','Lista CSV de elementos'),('percursos','Percurso ordenado'),('queries','Queries por tipo'),('conferencia','Relatório auxiliar de conferência'),('instrucoes','Instruções para Selection Set')]:
            w=QCheckBox(n);w.setChecked(True);self.opcoes[k]=w;v.addWidget(w)
        f=QFormLayout();v.addLayout(f);self.campo=QComboBox();self.campo.addItems(['Label','ID']);self.idcampo=QLineEdit();self.idcampo.setPlaceholderText('Nome real confirmado no Query Builder');self.idok=QCheckBox('Confirmei este campo ID no Query Builder');self.maxit=QSpinBox();self.maxit.setRange(1,10000);self.maxit.setValue(100);self.maxchar=QSpinBox();self.maxchar.setRange(40,100000);self.maxchar.setValue(4000)
        for n,w in [('Campo',self.campo),('Campo ID real',self.idcampo),('',self.idok),('Elementos por lote',self.maxit),('Caracteres por lote',self.maxchar)]:f.addRow(n,w)
        self.tabela=QTableWidget(0,3);self.tabela.setHorizontalHeaderLabels(['Tipo','Lote','Quantidade']);v.addWidget(self.tabela);self.texto=QPlainTextEdit();self.texto.setReadOnly(True);v.addWidget(self.texto)
        self.aviso=QLabel('IN é documentado pela Bentley. Confira campos e sintaxe no Query Builder. Limites de lotes são conservadores configuráveis; não são limites oficiais. Nenhum Selection Set nativo é criado por esta ação.');self.aviso.setWordWrap(True);v.addWidget(self.aviso)
        h=QHBoxLayout();v.addLayout(h)
        for n,fn in [('Gerar consultas',self.consultas),('Copiar expressão',lambda:QApplication.clipboard().setText(self.texto.toPlainText())),('Exportar arquivos…',self.exportar),('Conferir seleção CSV…',self.conferir),('Fechar',self.close)]:b=QPushButton(n);b.clicked.connect(fn);h.addWidget(b)
        self.qs=[];self.tabela.currentCellChanged.connect(self.mostrar);adaptar_janela(self)
    def config(self):return dict({k:w.isChecked() for k,w in self.opcoes.items()},campo=self.campo.currentText(),campo_id=self.idcampo.text().strip(),id_validado=self.idok.isChecked(),max_itens=self.maxit.value(),max_caracteres=self.maxchar.value())
    def consultas(self):
        try:
            c=self.config();self.qs=ex.consultas(self.dados,self.pacote['topologia']['modelo'],c['campo'],c['campo_id'],c['id_validado'],c['max_itens'],c['max_caracteres']);self.tabela.setRowCount(len(self.qs))
            for n,q in enumerate(self.qs):
                for j,k in enumerate(('tipo','lote','quantidade')):self.tabela.setItem(n,j,QTableWidgetItem(str(q[k])))
            self.tabela.resizeColumnsToContents()
            if self.qs:self.tabela.setCurrentCell(0,0)
        except Exception as e:QMessageBox.warning(self,'Consulta não gerada',str(e))
    def mostrar(self,row,*args):
        if 0<=row<len(self.qs):self.texto.setPlainText(self.qs[row]['expressao'])
    def exportar(self):
        pasta=QFileDialog.getExistingDirectory(self,'Pasta para nova exportação')
        if not pasta:return
        try:
            p=Path(pasta)/('WaterGEMS_'+uuid4().hex[:10]);ex.exportar(p,self.pacote,self.registro,self.config());self.aviso.setText('Exportação concluída: '+str(p)+'. '+ '\n'.join(self.dados['avisos']))
        except Exception as e:QMessageBox.warning(self,'Exportação não publicada',str(e))
    def conferir(self):
        p,_=QFileDialog.getOpenFileName(self,'CSV da seleção WaterGEMS: DomainElementID;Label;Tipo','','CSV (*.csv)')
        if not p:return
        try:
            with open(p,encoding='utf-8-sig',newline='') as f:linhas=list(csv.DictReader(f,delimiter=';'))
            r=ex.conferir(self.dados,linhas,self.dados['versao']);msg=QMessageBox(self);msg.setWindowTitle('Conferência da seleção');msg.setText(f"Esperados: {r['esperados']} · Selecionados: {r['selecionados']}\nAusentes: {len(r['ausentes'])} · Adicionais: {len(r['adicionais'])} · Duplicados: {len(r['duplicados'])} · Labels divergentes: {len(r['labels_divergentes'])}\nConfirme que o CSV pertence ao mesmo modelo e versão; o CSV sozinho não comprova a origem.");msg.setDetailedText(json.dumps(r,ensure_ascii=False,indent=2));msg.exec_()
        except Exception as e:QMessageBox.warning(self,'Conferência não realizada',str(e))
