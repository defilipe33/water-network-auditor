"""Fluxo explícito de seleção de execuções e geração de uma nova versão integrada."""
from pathlib import Path
from uuid import uuid4
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QLineEdit,QPushButton,QLabel,
    QFileDialog,QMessageBox,QDoubleSpinBox,QTableWidget,QTableWidgetItem,QComboBox,QApplication,QCheckBox,QInputDialog)
from qgis.core import QgsProject,QgsVectorLayer,QgsWkbTypes
from auditoria_fronteiras.versoes import listar
from auditoria_fronteiras.seletor_versoes import SeletorVersoes
from .integracao import preparar
from .saidas_integracao import salvar_gpkg,reabrir,exportar_relatorios
from .painel_diagnosticos import abrir_diagnosticos as abrir_painel


class JanelaIntegracao(QDialog):
    def __init__(self,parent=None,canvas=None):
        super().__init__(parent);self.setWindowTitle('Integrar auditoria geométrica e WaterGEMS');self.resize(790,650)
        self.canvas=canvas;self.geo_uid=None;self._executando=False;self._cancelado=False;self.painel=None
        l=QVBoxLayout(self);f=QFormLayout();l.addLayout(f)
        self.geo=QLineEdit();self.geo.setReadOnly(True);b=QPushButton('Selecionar auditoria geométrica persistida…');b.clicked.connect(self.escolher_geo);f.addRow(b,self.geo)
        self.topo=QLineEdit();self.topo.setReadOnly(True);b=QPushButton('Selecionar execução topológica JSON…');b.clicked.connect(lambda:self.escolher(self.topo,'Execução topológica (*.json)'));f.addRow(b,self.topo)
        self.gpkg_topo=QLineEdit();self.gpkg_topo.setReadOnly(True);b=QPushButton('Selecionar GPKG da mesma execução…');b.clicked.connect(lambda:self.escolher(self.gpkg_topo,'GeoPackage (*.gpkg)'));f.addRow(b,self.gpkg_topo)
        self.distancia=QDoubleSpinBox();self.distancia.setRange(0,100000);self.distancia.setDecimals(3);self.distancia.setValue(5)
        self.distancia.setToolTip('Usada apenas para investigar continuidades geométricas já registradas, entre componentes distintos. Não muda o agrupamento nem cria ligação.')
        f.addRow('Distância investigativa (m)',self.distancia)
        l.addWidget(QLabel('Contexto espacial opcional — seleção explícita; não recalcula os eventos:'))
        self.areas=QTableWidget(0,4);self.areas.setHorizontalHeaderLabels(['Área disponível','Campo ID','Campo de exibição','Tipo de limite']);l.addWidget(self.areas,1)
        self.preencher_areas()
        self.xlsx=QCheckBox('Gerar relatório XLSX');self.xlsx.setChecked(True);l.addWidget(self.xlsx)
        self.shp=QCheckBox('Gerar SHPs dos locais integrados e geometrias pendentes');self.shp.setChecked(True);l.addWidget(self.shp)
        self.aviso=QLabel('As duas execuções de origem permanecem intactas. O grafo da execução JSON será confrontado com o GPKG. Estados do cenário permanecem bloqueados.');self.aviso.setWordWrap(True);l.addWidget(self.aviso)
        self.executar=QPushButton('Gerar nova investigação integrada…');self.executar.clicked.connect(self.gerar);l.addWidget(self.executar)
        self.cancelar=QPushButton('Cancelar processamento');self.cancelar.setEnabled(False);self.cancelar.clicked.connect(lambda:setattr(self,'_cancelado',True));l.addWidget(self.cancelar)
        self.reabrir=QPushButton('Reabrir investigação integrada salva…');self.reabrir.clicked.connect(self.abrir_existente);l.addWidget(self.reabrir)

    def escolher(self,alvo,filtro):
        if self._executando:return
        p,_=QFileDialog.getOpenFileName(self,'Selecionar origem somente leitura','',filtro)
        if p:alvo.setText(p)

    def escolher_geo(self):
        if self._executando:return
        p,_=QFileDialog.getOpenFileName(self,'Auditoria geométrica','','GeoPackage (*.gpkg)')
        if not p:return
        try:
            dialog=SeletorVersoes(listar(p),self)
            if dialog.exec_()==QDialog.Accepted:
                r=dialog.selecionada();self.geo_uid=r['execucao_uid'];self.geo.setText(p)
                self.aviso.setText('Execução geométrica selecionada: '+self.geo_uid+'. Resultados integrados ainda não gerados.')
        except Exception as e:QMessageBox.warning(self,'Origem inválida',str(e))

    def preencher_areas(self):
        self.camadas_areas=[]
        for c in QgsProject.instance().mapLayers().values():
            if not isinstance(c,QgsVectorLayer) or not c.isValid() or c.geometryType()!=QgsWkbTypes.PolygonGeometry:continue
            n=self.areas.rowCount();self.areas.insertRow(n);self.camadas_areas.append(c)
            item=QTableWidgetItem(c.name());item.setFlags(Qt.ItemIsEnabled|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Unchecked);self.areas.setItem(n,0,item)
            for col in (1,2):
                combo=QComboBox();combo.addItem('Selecione o campo',None)
                for campo in c.fields():combo.addItem(campo.name(),campo.name())
                self.areas.setCellWidget(n,col,combo)
            self.areas.setItem(n,3,QTableWidgetItem(c.name()))

    def configs_areas(self):
        cs=[]
        for n,c in enumerate(self.camadas_areas):
            if self.areas.item(n,0).checkState()!=Qt.Checked:continue
            a,b=self.areas.cellWidget(n,1).currentData(),self.areas.cellWidget(n,2).currentData()
            if not a or not b:raise ValueError('Escolha ID e exibição para '+c.name())
            cs.append(dict(camada=c,campo_id=a,campo_nome=b,tipo=self.areas.item(n,3).text()))
        return cs

    def cancelado(self):
        QApplication.processEvents();return self._cancelado

    def publicar(self,pacote,caminho):
        antigo=self.painel
        if antigo:
            if hasattr(antigo,'resolver_alteracoes'):
                if not antigo.resolver_alteracoes():return False
            else:
                legado=getattr(antigo,'legado',antigo)
                if legado.tem_edicoes() and not legado.resolver_edicoes():return False
            antigo.hide()
        try:novo=abrir_painel(pacote,caminho,QgsProject.instance(),self,self.canvas)
        except Exception:
            if antigo:antigo.show()
            raise
        if antigo:antigo.desativar()
        self.painel=novo;self.hide();return True

    def gerar(self):
        if self._executando:return
        try:
            if not self.geo_uid or not self.topo.text() or not self.gpkg_topo.text():raise ValueError('Selecione as duas execuções e o GPKG topológico')
            areas=self.configs_areas()
            destino,_=QFileDialog.getSaveFileName(self,'Nova base integrada — não sobrescreve execuções','INVESTIGACAO_'+uuid4().hex[:8]+'.gpkg','GeoPackage (*.gpkg)')
            if not destino:return
            if not destino.lower().endswith('.gpkg'):destino+='.gpkg'
            if Path(destino).exists():raise FileExistsError('Escolha um arquivo novo para preservar as versões')
            texto=f"Geo: {self.geo_uid}\nTopologia: {self.topo.text()}\nDistância investigativa: {self.distancia.value()} m\nÁreas adicionais: {len(areas)}\nDestino: {destino}\nAs origens não serão alteradas."
            if QMessageBox.question(self,'Confirmar nova investigação',texto,QMessageBox.Ok|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Ok:return
            self._executando=True;self._cancelado=False
            for w in self.findChildren(QPushButton):w.setEnabled(False)
            for w in (self.areas,self.distancia,self.xlsx,self.shp):w.setEnabled(False)
            self.cancelar.setEnabled(True);self.aviso.setText('Investigando componentes e locais. Cancelar preserva as origens.')
            pacote=preparar(self.geo.text(),self.geo_uid,self.topo.text(),self.gpkg_topo.text(),self.distancia.value(),areas,cancelar=self.cancelado)
            salvar_gpkg(pacote,destino,self.cancelado)
            avisos=[]
            if self.xlsx.isChecked() or self.shp.isChecked():
                try:exportar_relatorios(pacote,Path(destino).with_suffix('').with_name(Path(destino).stem+'_relatorios'),self.xlsx.isChecked(),self.shp.isChecked())
                except Exception as e:avisos.append('GPKG salvo; relatórios opcionais incompletos: '+str(e))
            self.publicar(pacote,destino)
            self.aviso.setText(str(pacote['resultado']['resumo'])+'\n'+ '\n'.join(avisos))
        except Exception as e:QMessageBox.warning(self,'Integração não publicada',str(e))
        finally:
            self._executando=False
            for w in self.findChildren(QPushButton):w.setEnabled(True)
            for w in (self.areas,self.distancia,self.xlsx,self.shp):w.setEnabled(True)
            self.cancelar.setEnabled(False)

    def abrir_existente(self):
        if self._executando:return
        p,_=QFileDialog.getOpenFileName(self,'Investigação integrada salva','','GeoPackage (*.gpkg)')
        if p:
            try:
                from auditoria_fronteiras.versoes import abrir_ro
                with abrir_ro(p) as con:versoes=con.execute('SELECT ig_uid,data_utc FROM IG_EXECUCOES ORDER BY data_utc DESC').fetchall()
                if len(versoes)>1:
                    nomes=[f"{data} · {uid}" for uid,data in versoes]
                    nome,ok=QInputDialog.getItem(self,'Versão integrada','Selecione a execução:',nomes,0,False)
                    if not ok:return
                    uid=versoes[nomes.index(nome)][0]
                elif versoes:uid=versoes[0][0]
                else:raise ValueError('Nenhuma integração neste arquivo')
                self.publicar(reabrir(p,uid),p)
            except Exception as e:QMessageBox.warning(self,'Reabertura',str(e))

    def closeEvent(self,event):
        if self._executando:self._cancelado=True;event.ignore()
        elif self.painel and not self.painel.close():event.ignore()
        else:event.accept()


_janela=None


def abrir_integracao():
    global _janela
    if _janela is None:
        try:
            from qgis.utils import iface
            canvas=iface.mapCanvas() if iface else None
        except ImportError:canvas=None
        _janela=JanelaIntegracao(canvas=canvas)
    _janela.show();_janela.raise_();return _janela
