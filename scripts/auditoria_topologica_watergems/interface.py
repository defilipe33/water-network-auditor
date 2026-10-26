"""Primeira interface, independente do painel de auditoria geométrica."""
from pathlib import Path
from qgis.PyQt.QtCore import QThread,pyqtSignal
from qgis.PyQt.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QLineEdit,QPushButton,
    QComboBox,QDoubleSpinBox,QCheckBox,QTextBrowser,QFileDialog,QMessageBox,QHBoxLayout)
from qgis.core import QgsProject
from .leitura import Banco
from .topologia import analisar


class Trabalho(QThread):
    pronto=pyqtSignal(object,object)
    falhou=pyqtSignal(str)

    def __init__(self,caminho,cenario,modo,parent=None):
        super().__init__(parent);self.args=(caminho,cenario,modo)

    def run(self):
        banco=None
        try:
            banco=Banco(self.args[0]);m=banco.ler(self.args[1])
            if self.isInterruptionRequested(): return
            r=analisar(m,self.args[2])
            if not self.isInterruptionRequested(): self.pronto.emit(m,r)
        except Exception as e: self.falhou.emit(str(e))
        finally:
            if banco: banco.close()


class Janela(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle('AUDITORIA TOPOLOGICA WATERGEMS — inicial')
        self.resize(730,680);self.modelo=None;self.resultado=None;self.trabalho=None;self.camadas=[]
        l=QVBoxLayout(self);f=QFormLayout();l.addLayout(f)
        self.banco=QLineEdit();escolher=QPushButton('Selecionar cópia .wtg.sqlite…')
        escolher.clicked.connect(self.selecionar);f.addRow(escolher,self.banco);self.banco.setReadOnly(True)
        self.escolher=escolher
        self.cenario=QComboBox();f.addRow('Cenário',self.cenario)
        self.modo=QComboBox();self.modo.addItems(['ESTRUTURAL','TODAS_VALVULAS_ABERTAS'])
        self.modo.setCurrentIndex(1)
        self.modo.setToolTip('Estados do cenário indisponíveis enquanto códigos/controles não forem validados. Bombas sem estado comprovado ficam bloqueadas na hipótese potencial.')
        f.addRow('Hipótese',self.modo)
        self.espacial=QCheckBox('Habilitar análise espacial com CRS e unidade confirmados');f.addRow(self.espacial)
        self.crs=QLineEdit();self.crs.setPlaceholderText('Ex.: EPSG:31983 — confirmar com a fonte')
        self.fator=QDoubleSpinBox();self.fator.setDecimals(10);self.fator.setRange(.000000001,1000000);self.fator.setValue(1)
        self.fonte=QLineEdit();self.fonte.setPlaceholderText('Fonte que confirma CRS e unidade das coordenadas brutas')
        f.addRow('CRS projetado métrico',self.crs);f.addRow('Fator bruto → metro',self.fator);f.addRow('Confirmação espacial',self.fonte)
        self.distancia=QDoubleSpinBox();self.distancia.setRange(0,10000);self.distancia.setValue(1);f.addRow('Proximidade candidata (m)',self.distancia)
        self.cruzamentos=QCheckBox('Investigar interseções sem nó comum');f.addRow(self.cruzamentos)
        self.executar=QPushButton('Executar leitura e diagnóstico');self.executar.clicked.connect(self.iniciar)
        self.cancelar=QPushButton('Cancelar');self.cancelar.setEnabled(False);self.cancelar.clicked.connect(self.cancelar_trabalho)
        linha=QHBoxLayout();linha.addWidget(self.executar);linha.addWidget(self.cancelar);l.addLayout(linha)
        self.resumo=QTextBrowser();l.addWidget(self.resumo,1)
        linha=QHBoxLayout();self.gpkg=QCheckBox('GPKG');self.shp=QCheckBox('SHP');self.xlsx=QCheckBox('XLSX');self.json=QCheckBox('JSON completo')
        for c in (self.gpkg,self.shp,self.xlsx,self.json): linha.addWidget(c)
        l.addLayout(linha);self.exportar=QPushButton('Exportar formatos selecionados…');self.exportar.setEnabled(False)
        self.exportar.clicked.connect(self.salvar);l.addWidget(self.exportar)
        integrar=QPushButton('Integrar com auditoria geométrica persistida…')
        integrar.clicked.connect(self.abrir_integracao);l.addWidget(integrar)
        self.resumo.setPlainText('Abra uma cópia previamente extraída. Leitura somente leitura.\nESTRUTURAL inclui topologia cadastrada, inclusive elementos inativos, identificados nos atributos.\nTODAS_VALVULAS_ABERTAS preserva Active Topology; bombas indeterminadas não são habilitadas.\nSem confirmação espacial, GPKG conserva coordenadas brutas sem CRS e SHP permanece bloqueado.')

    def selecionar(self):
        p,_=QFileDialog.getOpenFileName(self,'Selecionar cópia WaterGEMS','','WaterGEMS (*.wtg.sqlite)')
        if not p:return
        b=None
        try:
            b=Banco(p);cenarios=b.listar_cenarios()
            self.cenario.clear()
            for c in cenarios:self.cenario.addItem(f"{c['nome']} [{c['id']}]",c['id'])
            idx=self.cenario.findData(b.ativo)
            if idx>=0:self.cenario.setCurrentIndex(idx)
            self.banco.setText(p)
            self.exportar.setEnabled(False)
            self.resumo.setPlainText('Fonte selecionada; execute para gerar resultados desta configuração.')
        except Exception as e:QMessageBox.warning(self,'Leitura',str(e))
        finally:
            if b:b.close()

    def abrir_integracao(self):
        if self.trabalho and self.trabalho.isRunning():return
        from .interface_integracao import abrir_integracao
        self.integracao=abrir_integracao()

    def iniciar(self):
        if not self.banco.text() or self.cenario.currentData() is None:return
        self.exportar.setEnabled(False);self.executar.setEnabled(False);self.cancelar.setEnabled(True)
        self._entradas=[self.escolher,self.cenario,self.modo,self.espacial,self.crs,self.fator,self.fonte,self.distancia,self.cruzamentos]
        for w in self._entradas:w.setEnabled(False)
        self.resumo.setPlainText('Lendo esquema, cenários e alternativas. O modelo original permanece somente leitura…')
        self.trabalho=Trabalho(self.banco.text(),self.cenario.currentData(),self.modo.currentText(),self)
        self.trabalho.pronto.connect(self.publicar);self.trabalho.falhou.connect(lambda e:self.resumo.setPlainText('ERRO: '+e))
        self.trabalho.finished.connect(self.terminar);self.trabalho.start()

    def cancelar_trabalho(self):
        if self.trabalho:self.trabalho.requestInterruption()
        self.resumo.setPlainText('Cancelamento solicitado. A leitura em curso terminará sem publicar resultados parciais.')

    def terminar(self):
        self.executar.setEnabled(True);self.cancelar.setEnabled(False)
        for w in self._entradas:w.setEnabled(True)

    def publicar(self,m,r):
        try:
            from .saidas import camadas
            g=None;crs=None
            if self.espacial.isChecked():
                from .espacial import geometrias,candidatos
                g,avisos=geometrias(m,self.crs.text(),self.fator.value(),self.fonte.text());crs=self.crs.text()
                r['diagnosticos']+=avisos+candidatos(m,g,self.distancia.value(),self.cruzamentos.isChecked())
                from collections import Counter
                r['resumo']['diagnosticos']=dict(Counter(d['codigo'] for d in r['diagnosticos']))
                m['referencia_espacial']=dict(crs=crs,fator=self.fator.value(),fonte=self.fonte.text(),distancia=self.distancia.value())
            novas=camadas(m,r,g,crs)
            for c in novas:QgsProject.instance().addMapLayer(c)
            self.modelo,self.resultado,self.camadas=m,r,novas
            import json
            self.resumo.setPlainText(json.dumps(r['resumo'],ensure_ascii=False,indent=2)+'\n'+r['aviso']+'\nESTADOS_DO_CENARIO e validação WaterGEMS desktop: PENDENTES.\n'+ '\n'.join(m['avisos']))
            self.exportar.setEnabled(True)
        except Exception as e:self.resumo.setPlainText('ERRO: '+str(e))

    def salvar(self):
        if not self.modelo:return
        p=QFileDialog.getExistingDirectory(self,'Pasta de destino — será criada subpasta exclusiva')
        if not p:return
        from uuid import uuid4
        pasta=Path(p)/('TOPOLOGIA_'+uuid4().hex[:10]);pasta.mkdir()
        try:
            from .saidas import exportar_geografico,exportar_json,exportar_xlsx
            if self.gpkg.isChecked():exportar_geografico(self.camadas,pasta/'GPKG','GPKG')
            if self.shp.isChecked():exportar_geografico(self.camadas,pasta/'SHP','SHP')
            if self.xlsx.isChecked():exportar_xlsx(self.modelo,self.resultado,pasta/'DIAGNOSTICO.xlsx')
            if self.json.isChecked():exportar_json(self.modelo,self.resultado,pasta/'DIAGNOSTICO.json')
            QMessageBox.information(self,'Exportação',str(pasta))
        except Exception as e:QMessageBox.warning(self,'Exportação incompleta; arquivos anteriores preservados',str(e))

    def closeEvent(self,event):
        if self.trabalho and self.trabalho.isRunning():
            self.cancelar_trabalho();event.ignore()
        else:event.accept()


_janela=None


def abrir_interface():
    global _janela
    if _janela is None:_janela=Janela()
    _janela.show();_janela.raise_();return _janela
