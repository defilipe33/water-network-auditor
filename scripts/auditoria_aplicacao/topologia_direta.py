"""Acesso topológico independente, com os mesmos algoritmos e sem auditoria fictícia."""
import json
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QDialog,QVBoxLayout,QLabel,QComboBox,QPushButton,QTableWidget,QTableWidgetItem,QFileDialog,QMessageBox
from qgis.PyQt import sip
from qgis.core import QgsProject
from auditoria_fronteiras.atividade import sistema
from auditoria_fronteiras.ui_comum import adaptar_janela
from auditoria_topologica_watergems import bases,corredores,ilhas
from auditoria_topologica_watergems.terminais_ui import SeletorTerminais
from auditoria_topologica_watergems.mapa_diagnosticos import MapaDiagnosticos


def pacote_topologico(t):
    m=t['meta_base'];params=dict(crs=m.get('crs') or '',espacial_habilitado=bool(t.get('metrica')))
    return dict(natureza='CONTEXTO_TOPOLOGICO_SEM_GIS',topologia=t,geometrias=t.get('geometrias') or {},areas=[],dossie=dict(tubulacoes=[],contexto=dict(parametros=params)),resultado=dict(meta=dict(uid='WB:'+m['uuid'],topologia=dict(execucao_uid=m['uuid']),parametros=params),locais=[],componentes=[],componentes_potenciais=[]))

class TopologiaDireta(QDialog):
    def __init__(self,app,base,pacote,ferramenta):
        super().__init__(app.iface.mainWindow());self.app=app;self.base=base;self.pacote=pacote;self.painel=self;self.legado=type('Mapa',(),dict(canvas=app.iface.mapCanvas(),projeto=QgsProject.instance()))();self.mapa=MapaDiagnosticos(pacote,QgsProject.instance(),app.iface.mapCanvas());self.worker=None;self.resultado=None;self._salvo=True;self.modo='TODAS_VALVULAS_ABERTAS';self.setWindowTitle('Análise topológica — sem auditoria GIS');self.resize(880,650)
        v=QVBoxLayout(self);self.contexto=QLabel();self.contexto.setWordWrap(True);v.addWidget(self.contexto);self.tipo=QComboBox();self.tipo.addItems(['Corredores alimentadores','Ilhas sem origem']);self.tipo.setCurrentIndex(1 if ferramenta=='ilhas' else 0);v.addWidget(self.tipo);self.perspectiva=QComboBox();self.perspectiva.addItems(bases.MODOS);self.perspectiva.setCurrentIndex(1);v.addWidget(self.perspectiva);self.perspectiva.currentTextChanged.connect(self.mudar)
        self.origens=SeletorTerminais(self,'Origens escolhidas — não comprova fonte real','#008a69');self.destinos=SeletorTerminais(self,'Destinos','#f58900');v.addWidget(self.origens);v.addWidget(self.destinos)
        self.origem_ilhas=QComboBox();self.origem_ilhas.addItems(['Reservoirs elegíveis','Reservoirs e Tanks — hipótese explícita','Apenas origens escolhidas']);v.addWidget(self.origem_ilhas)
        self.criterio=QComboBox();self.criterio.addItem('Menor quantidade de arestas','ARESTAS');self.criterio.addItem('Menor comprimento (somente métrica validada)','COMPRIMENTO');v.addWidget(self.criterio)
        self.regras=QTableWidget(0,2);self.regras.setHorizontalHeaderLabels(['Equipamento disponível','Regra no grafo de trabalho']);tipos=sorted({e['tipo'] for e in pacote['topologia']['modelo']['elementos'].values() if e['familia']=='DISPOSITIVO' and e['excluido'] is False});self.regras.setRowCount(len(tipos));self._regras={}
        for n,t in enumerate(tipos):
            c=QComboBox();c.addItems(['PERMITIR','EVITAR','BLOQUEAR']);self.regras.setItem(n,0,QTableWidgetItem(t));self.regras.setCellWidget(n,1,c);self._regras[t]=c
        v.addWidget(self.regras);self.estado=QLabel('Grafo completo da versão; não recortado por setor. Resultado não comprova abastecimento ou operação hidráulica.');self.estado.setWordWrap(True);v.addWidget(self.estado);self.tabela=QTableWidget(0,3);self.tabela.setHorizontalHeaderLabels(['Grupo / destino','Tubulações','Situação']);v.addWidget(self.tabela)
        for t,fn in [('Calcular sobre a base',self.calcular),('Destacar resultado (sem zoom)',self.destacar_resultado),('Exportar resultado topológico JSON…',self.exportar),('Aproximar resultado (explícito)',lambda:self.mapa.aproximar()),('Fechar',self.close)]:b=QPushButton(t);b.clicked.connect(fn);v.addWidget(b)
        self.tipo.currentIndexChanged.connect(self.exibir);self.exibir();self.mudar(self.modo);adaptar_janela(self);sistema(app.geo).vincular(self)
    def exibir(self):
        ilha=self.tipo.currentIndex()==1;self.destinos.setVisible(not ilha);self.origem_ilhas.setVisible(ilha);self.criterio.setVisible(not ilha)
    def mudar(self,modo):
        self.modo=modo;self._catalogo_terminais=None
        if hasattr(self,'_catalogo_terminais'):del self._catalogo_terminais
        self.origens.limpar();self.destinos.limpar();m=self.pacote['topologia']['meta_base'];self.contexto.setText(m['projeto']+' · '+m['nome']+' · Cenário '+str(m['cenario'])+' · Active Topology '+str(self.pacote['topologia']['modelo']['alternativas'].get('3'))+' · versão '+str(m['versao'])+' · '+modo+'\nSem investigação GIS associada. Nenhuma revisão é transferida.')
    def destacar_terminais(self):
        self.mapa.limpar()
        if not self.pacote['resultado']['meta']['parametros']['espacial_habilitado']:return
        for seletor,cor in ((self.origens,'#008a69'),(self.destinos,'#dc3b30')):
            for t in seletor.valores():self.mapa.adicionar(self.pacote['geometrias'].get(t['id']),cor)
    def destacar_resultado(self):
        if self.resultado is None:return
        self.destacar_terminais()
        if not self.pacote['resultado']['meta']['parametros']['espacial_habilitado']:self.estado.setText('Consulta disponível; valide CRS/unidades para destaques.');return
        if 'ilhas' in self.resultado:
            n=self.tabela.currentRow();ids=self.resultado['ilhas'][n]['membros'] if n>=0 else []
        else:ids=[int(i) for i in self.resultado['metricas']]
        for i in ids:self.mapa.adicionar(self.pacote['geometrias'].get(i),'#1769ed')
    def calcular(self):
        if sistema(self).em_execucao():return
        p=self.pacote;orig=self.origens.valores();dest=self.destinos.valores();modo=self.modo;restricoes=dict(regras={t:c.currentText() for t,c in self._regras.items()});ilha=self.tipo.currentIndex()==1;criterio=self.criterio.currentData();tipo=self.origem_ilhas.currentIndex()
        def trabalho(cancelar,progresso):
            if ilha:return ilhas.analisar(p,dict(origens=['RESERVOIRS','RESERVOIRS_TANKS','PERSONALIZADAS'][tipo],incluir_tanks=tipo==1,selecionadas=[dict(t,uid=p['topologia']['modelo']['elementos'][t['id']]['uid'],tipo=p['topologia']['modelo']['elementos'][t['id']]['tipo']) for t in orig],comparar_restricoes=modo=='TODAS_VALVULAS_ABERTAS',restricoes=restricoes),progresso=lambda t,n,total:progresso(0,t),cancelado=cancelar)
            return corredores.calcular(p,modo,orig,dest,criterio=criterio,restricoes=restricoes,progresso=lambda t,n,total:progresso(0,t),cancelado=cancelar)
        def pronto(r):
            self.resultado=r;self._salvo=False;linhas=[(v['nome'],len(v['tubos']),v['visao']) for v in r['ilhas']] if ilha else [(str(v['destino']),len(v['tubulacoes']),'ALCANÇADO') for v in r['rotas']]+[(str(v['destino']),0,v['motivo']) for v in r['destinos_inalcancaveis']];self.tabela.setRowCount(len(linhas))
            for n,l in enumerate(linhas):
                for k,x in enumerate(l):self.tabela.setItem(n,k,QTableWidgetItem(str(x)))
            self.estado.setText(r.get('motivo') or 'Resultado calculado no grafo completo. Exporte a evidência; decisões e RESOLVIDO continuam na investigação integrada.')
        self.worker=sistema(self).executar_thread('Calculando conectividade independente','Versão e cenário selecionados',trabalho,pronto,lambda e:self.estado.setText(e+' · bases preservadas'))
    def exportar(self):
        if self.resultado is None:return
        f,_=QFileDialog.getSaveFileName(self,'Resultado de consulta — não é uma investigação GIS','','JSON (*.json)')
        if f:
            try:
                with open(f,'x',encoding='utf8') as a:json.dump(dict(natureza='ANALISE_TOPOLOGICA_SEM_GIS',contexto=self.pacote['topologia']['meta_base'],resultado=self.resultado),a,ensure_ascii=False,indent=2,default=str)
                self._salvo=True
            except Exception as e:QMessageBox.warning(self,'Resultado não exportado',str(e))
    def resolver(self):
        if self._salvo or self.resultado is None:return True
        x=QMessageBox.question(self,'Resultado apenas em memória','Exportar a consulta antes de trocar o contexto ou fechar?',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Cancel)
        if x==QMessageBox.Cancel:return False
        if x==QMessageBox.Save:self.exportar();return self._salvo
        self._salvo=True;return True
    def closeEvent(self,e):
        if self.worker and not sip.isdeleted(self.worker) and self.worker.isRunning():e.ignore();self.estado.setText('Aguarde ou cancele no acompanhamento antes de fechar.');return
        if not self.resolver():e.ignore();return
        self.origens.fechar_captura();self.destinos.fechar_captura();self.mapa.fechar();e.accept()
