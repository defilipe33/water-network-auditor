"""Unificação operacional; reaproveita as janelas e suas guardas de estado."""
from pathlib import Path
from uuid import uuid4
from qgis.PyQt.QtWidgets import QPushButton,QHBoxLayout,QGridLayout,QWidget,QFileDialog,QMessageBox,QDialog,QProgressDialog,QApplication,QSizePolicy,QCheckBox,QGroupBox,QMenu
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsProject
from qgis.PyQt import sip
from auditoria_fronteiras.interface import AuditoriaFronteirasDialog
from auditoria_fronteiras.estados import Estado,OCUPADOS
from auditoria_fronteiras.persistencia import exportar_gpkg
from auditoria_topologica_watergems.gerenciamento import Catalogo,sugestao,preparar_integracao
from auditoria_topologica_watergems.saidas_integracao import salvar_gpkg,reabrir
from auditoria_topologica_watergems.painel_diagnosticos import abrir_diagnosticos
from .catalogo_ui import SeletorBases
from .watergems_ui import WatergemsDialog
from auditoria_fronteiras.janelas import Janelas
from auditoria_fronteiras.atividade import Atividades,etapa,Progresso as QProgressDialog


class Aplicacao:
    def __init__(self,iface,raiz):
        self.iface=iface;self.catalogo=Catalogo(raiz);self.painel=None;self.wg=None;self.ocupado=False;self._resolvendo_saida=False
        self.geo=AuditoriaFronteirasDialog(iface.mainWindow(),QgsProject.instance());self.geo.setWindowTitle('Auditoria de Redes — GIS & WaterGEMS')
        self.janelas=Janelas(iface.mainWindow());self.atividades=Atividades(iface.mainWindow());self.atividades.vincular(self.geo)
        self.janelas.registrar('gis',self.geo,'auditoria GIS');self.janelas.registrar('atividade',self.atividades.dock,'acompanhamento de operações')
        self.menu_janelas=QMenu('Janelas / painéis',iface.mainWindow());self.menu_janelas.aboutToShow.connect(lambda:self.janelas.preencher_menu(self.menu_janelas))
        self.botao_janelas(self.geo)
        self._catalogo_antigo=None
        import auditoria_fronteiras.catalogo as cat
        self._catalogo_antigo=cat.CATALOGO_APLICACAO;cat.CATALOGO_APLICACAO=self.catalogo.raiz/'auditorias_recentes.json'
        w=QGroupBox('Iniciar ou continuar');linha=QGridLayout(w);self.navegacao={}
        for i,(texto,acao,ajuda) in enumerate([
            ('Nova auditoria GIS',lambda:self.operacao_gis(0),'Analisa novas entradas. Alterações pendentes são resolvidas antes de trocar o contexto.'),
            ('Continuar auditoria GIS…',lambda:self.operacao_gis(1),'Reabre eventos, locais e revisões sem recalcular.'),
            ('Analisar com WaterGEMS…',self.analisar,'Associa a auditoria GIS à topologia persistida do modelo; não altera o WaterGEMS.'),
            ('Continuar investigação integrada…',lambda:self.catalogar('INTEGRADA'),'Reabre diagnósticos, anotações, conclusões e propostas existentes.'),
            ('Bases WaterGEMS / atualizar…',self.bases,'Uma base topológica é uma cópia de consulta. Atualizar cria outra versão; preserva a anterior e não transfere conclusões automaticamente.'),
            ('Comparar versões…',self.comparar,'Confronta investigações ou versões WaterGEMS. Uma ocorrência ausente não é uma correção comprovada.')]):
            b=QPushButton(texto);b.clicked.connect(acao);b.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred);b.setToolTip(ajuda);linha.addWidget(b,i//2,i%2);self.navegacao[texto]=b
        self.geo.layout().insertWidget(0,w)
        self.limpar_ao_sair=QCheckBox('Remover somente temporárias da ferramenta ao encerrar');self.limpar_ao_sair.setToolTip('Opcional: remove representações de validação marcadas pela ferramenta; não apaga arquivos ou camadas persistentes.');self.geo.layout().insertWidget(1,self.limpar_ao_sair)
    def botao_janelas(self,w):
        b=QPushButton('Janelas / painéis');b.setMenu(self.menu_janelas);w.layout().insertWidget(0,b)
    def abrir(self):self.janelas.mostrar('gis')
    def mostrar_integracao(self):
        if self.painel and not sip.isdeleted(self.painel):return self.publicar(self.painel.pacote,self.painel.base)
        return False
    def operacao_gis(self,modo):
        if self.ocupado or self.atividades.em_execucao() or (self.wg and self.wg.ocupado) or not self.resolver():return
        self.geo.iniciar_operacao(modo,usar_ativa=False)
    def comparar(self):
        if self.ocupado or self.atividades.em_execucao() or self.geo._executando or not self.resolver():return
        if self.painel and self.painel._ativo:self.painel.comparar_versoes()
        else:
            self.bases()
            if self.wg and not self.wg.ocupado:
                if not self.wg.base:self.wg.abrir_base()
                if self.wg.base:self.wg.comparar()
    def resolver(self):
        if self.painel is not None and sip.isdeleted(self.painel):self.painel=None
        return not self.painel or self.painel.resolver_alteracoes()
    def validar_geo(self):
        g=self.geo
        if self.ocupado or self.atividades.em_execucao() or g._executando or g.estado in OCUPADOS:raise ValueError('Aguarde ou cancele o processamento em andamento')
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
        self.catalogo.registrar_opcional(g.base_revisao);return True
    def analisar(self):
        try:
            if self.validar_geo():self.bases()
        except Exception as e:QMessageBox.warning(self.geo,'Auditoria ainda não disponível',str(e))
    def bases(self):
        if self.ocupado or self.geo._executando:return
        if self.atividades.em_execucao():
            if self.wg and not sip.isdeleted(self.wg):self.janelas.mostrar('watergems')
            return
        if self.wg is None or sip.isdeleted(self.wg):
            self.wg=WatergemsDialog(self);self.janelas.registrar('watergems',self.wg,'configuração WaterGEMS');self.atividades.vincular(self.wg);self.botao_janelas(self.wg)
        self.wg.atualizar_geo();self.janelas.mostrar('watergems')
    def catalogar(self,tipo=None):
        if self.ocupado or self.atividades.em_execucao() or not self.resolver() or self.geo._executando:return
        d=SeletorBases(self.catalogo,self.geo,tipo=tipo)
        if d.exec_()!=QDialog.Accepted:return
        r=d.selecionada
        try:
            if r['tipo']=='TOPOLOGIA_WG':self.bases();self.wg.usar_base(r['base'])
            elif r['tipo']=='INTEGRADA':
                self.atividades.executar_thread('Abrindo investigação integrada',r['nome'],
                    lambda cancelar,progresso:reabrir(r['base'],r['uuid'],cancelar,progresso),
                    lambda pacote:self.publicar(pacote,r['base']),lambda e:QMessageBox.warning(self.geo,'Investigação não aberta',e+'\nA versão anterior permanece disponível.'))
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
        anterior=(self.geo.base_revisao,self.geo.dossie['execucao_uid']) if self.geo.dossie and self.geo.base_revisao else None
        # A auditoria exibida na janela principal deve ser a mesma do painel.
        # O fluxo existente resolve rascunhos e mantém o contexto ao cancelar.
        if not self.geo.abrir_auditoria(str(base),pacote['dossie']['execucao_uid']):return False
        self.geo.voltar_inspecao()
        try:novo=abrir_diagnosticos(pacote,base,QgsProject.instance(),self.iface.mainWindow(),self.iface.mapCanvas(),gerenciar_saida=False)
        except Exception as e:
            if anterior:self.geo.abrir_auditoria(*anterior)
            QMessageBox.warning(self.geo,'Investigação não aberta',str(e)+'\nAs versões anteriores foram preservadas. Reabra a fonte correta ou restaure uma cópia íntegra.');return False
        if self.painel:self.painel.desativar()
        self.painel=novo
        self.janelas.registrar('integrada',novo,'investigação integrada',self.mostrar_integracao);self.atividades.vincular(novo);self.botao_janelas(novo.widget())
        self.janelas.registrar('inspecao',novo.legado,'inspeção espacial');self.atividades.vincular(novo.legado)
        if modo in ('ESTRUTURAL','TODAS_VALVULAS_ABERTAS'):novo.modo.setCurrentIndex(novo.modo.findData(modo))
        self.catalogo.registrar_opcional(base);self.janelas.ocultar('gis');self.janelas.ocultar('watergems');self.janelas.mostrar('integrada')
        if hasattr(self.iface,'messageBar'):self.iface.messageBar().pushInfo('Investigação integrada ativa','Auditoria GIS e configuração WaterGEMS estão em segundo plano. Recupere-as em Janelas / painéis, no menu do complemento ou no painel.')
        return True
    def integrar(self,base_wg,mapeamento,tolerancia,modo):
        if not self.validar_geo():return
        g=self.geo;c=g.dossie.get('controle_versao',{});p,_=QFileDialog.getSaveFileName(self.wg,'Nova investigação — nome livre',str(sugestao(self.catalogo.raiz,c.get('projeto','Projeto'),'Integrada')),'GeoPackage (*.gpkg)')
        if not p:return
        if not p.lower().endswith('.gpkg'):p+='.gpkg'
        if Path(p).exists():raise FileExistsError('Não substituir investigação existente')
        progresso=QProgressDialog('Preparando investigação e prova cadastral…','Cancelar',0,0,self.wg);progresso.setWindowModality(Qt.ApplicationModal);progresso.show()
        def cancelar():return progresso.wasCanceled()
        self.ocupado=True
        try:
            pasta=Path(p).parent/'_tecnicos'/uuid4().hex;pasta.parent.mkdir(parents=True,exist_ok=True)
            pacote=preparar_integracao(g.base_revisao,g.dossie['execucao_uid'],base_wg,pasta,mapeamento,tolerancia,cancelar=cancelar)
            n=len({a['gis_uid'] for l in pacote['resultado']['locais'] for a in l['correspondencias'] if a['situacao']=='INEQUIVOCA'})
            resumo=f"GIS: {g.dossie['execucao_uid']}\nBase WaterGEMS: {pacote['topologia']['meta_base']['uuid']}\nPerspectiva inicial: {modo}\nTubulações GIS únicas com correspondência inequívoca: {n}\nDestino: {p}\nSem correção automática e sem transferência de conclusões."
            progresso.hide()
            if QMessageBox.question(self.wg,'Confirmar publicação da investigação',resumo,QMessageBox.Ok|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Ok:return
            pacote['resultado']['meta']['nome']=Path(p).stem;pacote['resultado']['meta']['hipotese']=modo
            progresso.setLabelText('Gravando e validando a nova investigação integrada')
            progresso.show()
            salvar_gpkg(pacote,p,cancelar)
            # Somente na criação de nova investigação, nunca ao abrir uma versão
            # histórica: preserva manuais e sinaliza vínculos a reconciliar.
            if self.painel:
                from auditoria_topologica_watergems.conjuntos_investigacao import importar
                from auditoria_topologica_watergems.decisoes import digest
                origem=self.painel.pacote
                if digest(origem['topologia']['modelo']['projeto'])==digest(pacote['topologia']['modelo']['projeto']):
                    importar(self.painel.base,origem,p,pacote)
            if self.publicar(pacote,p,modo):progresso.concluir()
        except Exception as e:progresso.falhar(e);raise
        finally:self.ocupado=False;progresso.close()
    def encerrar(self):
        if not self.preparar_saida():return False
        if self.limpar_ao_sair.isChecked():
            from auditoria_fronteiras.organizacao_camadas import remover_temporarias
            remover_temporarias(QgsProject.instance())
        if not self.geo.close():return False
        if self.painel and not self.painel.close():self.geo.show();return False
        if self.wg:self.wg.close()
        import auditoria_fronteiras.catalogo as cat
        cat.CATALOGO_APLICACAO=self._catalogo_antigo
        self.atividades.fechar();self.janelas.limpar()
        return True
    def preparar_saida(self):
        if self._resolvendo_saida:return False
        self._resolvendo_saida=True
        try:
            if self.wg is not None and sip.isdeleted(self.wg):self.wg=None
            if self.ocupado or self.atividades.em_execucao() or self.geo._executando or (self.wg and self.wg.ocupado):
                texto='Encerramento adiado: aguarde a conclusão ou cancele o processamento na janela correspondente e tente sair novamente. Nenhuma gravação foi interrompida.'
                self.geo.status.setText(texto)
                if hasattr(self.iface,'messageBar'):self.iface.messageBar().pushWarning('Water Network Auditor',texto)
                return False
            if not self.resolver() or not self.geo.resolver_pendencias():return False
            if self.geo.pendente():
                f=self.geo._formulario_resultado if self.geo.dossie else self.geo._config_inicial
                if f:self.geo.restaurar_formulario(f)
                self.geo._config_inicial=self.geo.formulario()
            return True
        finally:self._resolvendo_saida=False
