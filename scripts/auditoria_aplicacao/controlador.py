"""Unificação operacional; reaproveita as janelas e suas guardas de estado."""
from pathlib import Path
from uuid import uuid4
from qgis.PyQt.QtWidgets import QPushButton,QHBoxLayout,QGridLayout,QWidget,QFileDialog,QMessageBox,QDialog,QProgressDialog,QApplication,QSizePolicy
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsProject
from auditoria_fronteiras.interface import AuditoriaFronteirasDialog
from auditoria_fronteiras.estados import Estado,OCUPADOS
from auditoria_fronteiras.persistencia import exportar_gpkg
from auditoria_topologica_watergems.gerenciamento import Catalogo,sugestao,preparar_integracao
from auditoria_topologica_watergems.saidas_integracao import salvar_gpkg,reabrir
from auditoria_topologica_watergems.painel_diagnosticos import abrir_diagnosticos
from .catalogo_ui import SeletorBases
from .watergems_ui import WatergemsDialog


class Aplicacao:
    def __init__(self,iface,raiz):
        self.iface=iface;self.catalogo=Catalogo(raiz);self.painel=None;self.wg=None;self.ocupado=False
        self.geo=AuditoriaFronteirasDialog(iface.mainWindow(),QgsProject.instance());self.geo.setWindowTitle('Auditoria de Redes — GIS & WaterGEMS')
        self._catalogo_antigo=None
        import auditoria_fronteiras.catalogo as cat
        self._catalogo_antigo=cat.CATALOGO_APLICACAO;cat.CATALOGO_APLICACAO=self.catalogo.raiz/'auditorias_recentes.json'
        w=QWidget();linha=QGridLayout(w)
        for i,(texto,acao) in enumerate([('ANALISAR COM WATERGEMS…',self.analisar),('Catálogo / continuar investigação…',self.catalogar),('Base WaterGEMS / versões…',self.bases)]):
            b=QPushButton(texto);b.clicked.connect(acao);b.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);b.setToolTip(texto);linha.addWidget(b,i//2,i%2)
        self.geo.layout().insertWidget(0,w)
    def abrir(self):self.geo.show();self.geo.raise_()
    def resolver(self):return not self.painel or self.painel.resolver_alteracoes()
    def validar_geo(self):
        g=self.geo
        if self.ocupado or g._executando or g.estado in OCUPADOS:raise ValueError('Aguarde ou cancele o processamento em andamento')
        if not g.dossie:raise ValueError('Crie ou continue uma auditoria geométrica concluída')
        if g.pendente():
            dlg=QMessageBox(g);dlg.setWindowTitle('Configuração geométrica não processada');dlg.setText('Os resultados não incluem as alterações pendentes. Escolha explicitamente o próximo passo.')
            executar=dlg.addButton('Executar configuração',QMessageBox.AcceptRole);descartar=dlg.addButton('Descartar e usar resultados anteriores',QMessageBox.DestructiveRole);dlg.addButton(QMessageBox.Cancel);dlg.exec_()
            if dlg.clickedButton()==executar:g.executar_auditoria();return False
            if dlg.clickedButton()!=descartar:return False
            # Reutiliza a configuração que efetivamente produziu os resultados.
            g.restaurar_formulario(g._formulario_resultado);g._config_inicial=g.formulario();g.definir_estado(Estado.INSPECIONANDO)
        if g.estado not in (Estado.INSPECIONANDO,Estado.CONCLUIDO):
            if not g.voltar_inspecao():return False
        if g.painel and g.painel.tem_edicoes() and not g.painel.resolver_edicoes():return False
        if not self.resolver():return False
        if not g.base_revisao:
            c=g.dossie.get('controle_versao',{});s=sugestao(self.catalogo.raiz,c.get('projeto','Projeto'),'AuditoriaGIS')
            p,_=QFileDialog.getSaveFileName(g,'Preservar auditoria concluída — nome livre',str(s),'GeoPackage (*.gpkg)')
            if not p:return False
            if not p.lower().endswith('.gpkg'):p+='.gpkg'
            exportar_gpkg(p,g.dossie);g.vincular_base(p)
        self.catalogo.registrar(g.base_revisao);return True
    def analisar(self):
        try:
            if self.validar_geo():self.bases()
        except Exception as e:QMessageBox.warning(self.geo,'Auditoria ainda não disponível',str(e))
    def bases(self):
        if self.ocupado or self.geo._executando:return
        if self.wg is None:self.wg=WatergemsDialog(self)
        self.wg.atualizar_geo();self.wg.show();self.wg.raise_()
    def catalogar(self):
        if self.ocupado or not self.resolver() or self.geo._executando:return
        d=SeletorBases(self.catalogo,self.geo)
        if d.exec_()!=QDialog.Accepted:return
        r=d.selecionada
        try:
            if r['tipo']=='TOPOLOGIA_WG':self.bases();self.wg.usar_base(r['base'])
            elif r['tipo']=='INTEGRADA':self.publicar(reabrir(r['base'],r['uuid']),r['base'])
            else:
                # O fluxo já implementado lida com descarte, cancelamento e
                # restauração. Substitui apenas o seletor nesta chamada explícita.
                antigo=self.geo.escolher_auditoria
                self.geo.escolher_auditoria=lambda:self.geo.abrir_auditoria(r['base'],r['uuid'])
                try:self.geo.iniciar_operacao(1,usar_ativa=False)
                finally:self.geo.escolher_auditoria=antigo
        except Exception as e:QMessageBox.warning(self.geo,'Base não aberta',str(e))
    def publicar(self,pacote,base,modo=None):
        if not self.resolver():return False
        # A auditoria exibida na janela principal deve ser a mesma do painel.
        # O fluxo existente resolve rascunhos e mantém o contexto ao cancelar.
        if not self.geo.abrir_auditoria(str(base),pacote['dossie']['execucao_uid']):return False
        self.geo.voltar_inspecao()
        novo=abrir_diagnosticos(pacote,base,QgsProject.instance(),self.iface.mainWindow(),self.iface.mapCanvas())
        if self.painel:self.painel.desativar()
        self.painel=novo
        if modo in ('ESTRUTURAL','TODAS_VALVULAS_ABERTAS'):novo.modo.setCurrentIndex(novo.modo.findData(modo))
        self.catalogo.registrar(base);self.geo.hide()
        if self.wg:self.wg.hide()
        return True
    def integrar(self,base_wg,mapeamento,tolerancia,modo):
        if not self.validar_geo():return
        g=self.geo;c=g.dossie.get('controle_versao',{});p,_=QFileDialog.getSaveFileName(self.wg,'Nova investigação — nome livre',str(sugestao(self.catalogo.raiz,c.get('projeto','Projeto'),'Integrada')),'GeoPackage (*.gpkg)')
        if not p:return
        if not p.lower().endswith('.gpkg'):p+='.gpkg'
        if Path(p).exists():raise FileExistsError('Não substituir investigação existente')
        progresso=QProgressDialog('Preparando investigação e prova cadastral…','Cancelar',0,0,self.wg);progresso.setWindowModality(Qt.ApplicationModal);progresso.show()
        def cancelar():QApplication.processEvents();return progresso.wasCanceled()
        self.ocupado=True
        try:
            pasta=Path(p).parent/'_tecnicos'/uuid4().hex;pasta.parent.mkdir(parents=True,exist_ok=True)
            pacote=preparar_integracao(g.base_revisao,g.dossie['execucao_uid'],base_wg,pasta,mapeamento,tolerancia,cancelar=cancelar)
            n=len({a['gis_uid'] for l in pacote['resultado']['locais'] for a in l['correspondencias'] if a['situacao']=='INEQUIVOCA'})
            resumo=f"GIS: {g.dossie['execucao_uid']}\nBase WaterGEMS: {pacote['topologia']['meta_base']['uuid']}\nPerspectiva inicial: {modo}\nTubulações GIS únicas com correspondência inequívoca: {n}\nDestino: {p}\nSem correção automática e sem transferência de conclusões."
            progresso.hide()
            if QMessageBox.question(self.wg,'Confirmar publicação da investigação',resumo,QMessageBox.Ok|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Ok:return
            pacote['resultado']['meta']['nome']=Path(p).stem;pacote['resultado']['meta']['hipotese']=modo
            salvar_gpkg(pacote,p,cancelar);self.publicar(pacote,p,modo)
        finally:self.ocupado=False;progresso.close()
    def encerrar(self):
        if not self.preparar_saida():return False
        if not self.geo.close():return False
        if self.painel and not self.painel.close():self.geo.show();return False
        if self.wg:self.wg.close()
        import auditoria_fronteiras.catalogo as cat
        cat.CATALOGO_APLICACAO=self._catalogo_antigo
        return True
    def preparar_saida(self):
        if self.ocupado or self.geo._executando or (self.wg and self.wg.ocupado):return False
        if not self.resolver() or not self.geo.resolver_pendencias():return False
        if self.geo.pendente():
            f=self.geo._formulario_resultado if self.geo.dossie else self.geo._config_inicial
            if f:self.geo.restaurar_formulario(f)
            self.geo._config_inicial=self.geo.formulario()
        return True
