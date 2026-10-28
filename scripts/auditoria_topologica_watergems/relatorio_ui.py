"""Configuração rápida, prévia e fontes opcionais, sem burocracia de revisão."""
from pathlib import Path
from uuid import uuid4
from qgis.PyQt.QtCore import Qt,QUrl,QTimer
from qgis.PyQt.QtGui import QPixmap,QDesktopServices
from qgis.PyQt.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QComboBox,QLineEdit,QCheckBox,QDoubleSpinBox,QSpinBox,QPushButton,QLabel,QGroupBox,QScrollArea,QWidget,QFileDialog,QMessageBox,QInputDialog,QTextBrowser)
from qgis.core import QgsProject,QgsRasterLayer,QgsVectorLayer,QgsCoordinateReferenceSystem,QgsCoordinateTransform
from auditoria_fronteiras.ui_comum import adaptar_janela
from auditoria_fronteiras.atividade import sistema
from . import relatorio_investigacao as rel


class RelatorioDialog(QDialog):
    def __init__(self,painel):
        super().__init__(painel);self.painel=painel;self.setWindowTitle('Gerar relatório');self.resize(800,650);self._ocupado=False;self.extras=[];self._extensao=None;self._externas={};self._geocoder=None
        v=QVBoxLayout(self);v.addWidget(QLabel('GERAR RELATÓRIO'));scroll=QScrollArea();scroll.setWidgetResizable(True);w=QWidget();scroll.setWidget(w);v.addWidget(scroll,1);self.scroll=scroll;f=QFormLayout(w)
        self.escopo=QComboBox()
        for n,k in [('Todas as ocorrências','TODOS'),('Somente analisadas','ANALISADOS'),('Somente pendentes','PENDENTES'),('Correção necessária','CORRECAO'),('Locais manuais','MANUAIS'),('Ocorrência selecionada','SELECAO'),('Filtros ativos (todas as páginas)','FILTROS')]:self.escopo.addItem(n,k)
        f.addRow('Ocorrências incluídas',self.escopo);self.acompanhamento=QComboBox()
        for n,k in [('Incluir resolvidas','TODAS'),('Excluir resolvidas (em aberto)','EM_ABERTO'),('Somente resolvidas','RESOLVIDAS')]:self.acompanhamento.addItem(n,k)
        f.addRow('Acompanhamento',self.acompanhamento)
        pasta=QWidget();ph=QHBoxLayout(pasta);ph.setContentsMargins(0,0,0,0);self.destino=QLineEdit(str(Path(painel.base).parent));ph.addWidget(self.destino);escolher=QPushButton('Escolher…');escolher.clicked.connect(self.escolher_destino);ph.addWidget(escolher);f.addRow('Pasta de destino',pasta)
        self.imagens=QCheckBox('Incluir mapas');self.imagens.setChecked(True);f.addRow(self.imagens)
        self.basemap_modo=QComboBox()
        for n,k in [('Automático (offline)','AUTOMATICO'),('Sem mapa-base','NENHUM'),('Selecionar fonte','SELECIONAR')]:self.basemap_modo.addItem(n,k)
        f.addRow('Mapa-base',self.basemap_modo)
        self.fontes_widget=QWidget();sf=QFormLayout(self.fontes_widget);sf.setContentsMargins(0,0,0,0);self.base=QComboBox();self.base.addItem('Escolha uma fonte',None)
        self.ruas=QComboBox();self.ruas.addItem('Automático quando disponível',None)
        for c in QgsProject.instance().mapLayers().values():
            if c.isValid():self.base.addItem(c.name(),c)
            if isinstance(c,QgsVectorLayer) and c.isValid() and c.geometryType()==1:
                from .fontes_relatorio import remota
                if not remota(c):self.ruas.addItem(c.name(),c)
        sf.addRow('Fonte',self.base);self.fonte_info=QLabel();self.fonte_info.setWordWrap(True);sf.addRow(self.fonte_info)
        for texto,fn in [('Conexões do QGIS…',self.conexoes_qgis),('Atualizar fontes',self.atualizar_fontes),('Outra fonte…',self.outra_fonte)]:b=QPushButton(texto);b.clicked.connect(fn);sf.addRow(b)
        f.addRow(self.fontes_widget)
        self.localizacao=QCheckBox('Automática quando disponível (cadastro ou ruas locais)');self.localizacao.setChecked(True);f.addRow('Referência de localização',self.localizacao);self.xlsx=QCheckBox('PDF + XLSX da mesma seleção');f.addRow('Formato: PDF',self.xlsx)
        self.avancado=QGroupBox('Opções avançadas');self.avancado.setCheckable(True);self.avancado.setChecked(False);self.advanced_widget=QWidget();af=QFormLayout(self.advanced_widget);al=QVBoxLayout(self.avancado);al.addWidget(self.advanced_widget);self.advanced_widget.hide();self.avancado.toggled.connect(self.advanced_widget.setVisible);f.addRow(self.avancado)
        self.nome=QLineEdit('Relatório de investigação');af.addRow('Nome do relatório',self.nome)
        self.ruacampo=QComboBox();self.ruas.currentIndexChanged.connect(self.campos_rua);af.addRow('Camada de logradouros',self.ruas);af.addRow('Campo do nome da rua',self.ruacampo)
        self.manual=QLineEdit();self.manual.setPlaceholderText('Usada se as fontes automáticas não identificarem a localização');af.addRow('Localização manual',self.manual)
        self.cadfonte=QComboBox();self.cadfonte.addItem('Automático (campos específicos de localização)',None);self.cadcampo=QComboBox()
        for origem,nome in sorted({(t['origem'],t['camada']) for t in painel.pacote['dossie']['tubulacoes']}):self.cadfonte.addItem(nome,origem)
        self.cadfonte.currentIndexChanged.connect(self.campos_cadastrais);af.addRow('Referência cadastral',self.cadfonte);af.addRow('Campo escolhido',self.cadcampo)
        self.atri=QLineEdit();af.addRow('Créditos cartográficos',self.atri);self.licenca=QCheckBox('O uso e a exportação desta fonte são permitidos');af.addRow(self.licenca);self.lote_online=QCheckBox('O serviço permite vários mapas nesta exportação');af.addRow(self.lote_online);self.online=QCheckBox('Autorizar o envio da área do mapa a este serviço');af.addRow(self.online)
        self.estilo=QComboBox();self.estilo.addItems(['Estilo da fonte','Tons de cinza']);self.opacity=QDoubleSpinBox();self.opacity.setRange(0,1);self.opacity.setValue(.65);self.brilho=QSpinBox();self.brilho.setRange(-255,255);self.contraste=QSpinBox();self.contraste.setRange(-100,100);self.margem=QDoubleSpinBox();self.margem.setRange(0,5);self.margem.setValue(.25);self.minimo=QDoubleSpinBox();self.minimo.setRange(10,100000);self.minimo.setValue(100);self.raio=QDoubleSpinBox();self.raio.setRange(0,1000);self.raio.setValue(100)
        self.contexto=QCheckBox('Mapa complementar de contexto');self.historico=QCheckBox('Histórico');self.tecnico=QCheckBox('Detalhes técnicos');self.paisagem=QCheckBox('Página em paisagem');self.preservar=QCheckBox('Preservar PNGs (conforme licença)');self.ordem=QComboBox();self.ordem.addItems(['titulo','resultado','prioridade','origem'])
        for n,c in [('Estilo',self.estilo),('Opacidade',self.opacity),('Brilho',self.brilho),('Contraste',self.contraste),('Margem',self.margem),('Extensão mínima (m)',self.minimo),('Busca de ruas (m)',self.raio),('Ordenar por',self.ordem),('',self.contexto),('',self.historico),('',self.tecnico),('',self.paisagem),('',self.preservar)]:af.addRow(n,c)
        for n,fn in [('Usar enquadramento atual do mapa',self.extensao),('Restaurar enquadramento automático',lambda:setattr(self,'_extensao',None))]:b=QPushButton(n);b.clicked.connect(fn);af.addRow(b)
        self.externo=QCheckBox('PERMITIR CONSULTAS EXTERNAS DE LOCALIZAÇÃO');af.addRow(self.externo);self.endpoint=QLineEdit();self.endpoint.setPlaceholderText('Serviço HTTPS autorizado');self.termos=QLineEdit();self.custos=QLineEdit();self.armazenamento=QLineEdit();self.credito=QLineEdit();self.auth=QLineEdit();self.cache=QCheckBox('O serviço permite cache da sessão')
        for n,c in [('Serviço',self.endpoint),('Termos',self.termos),('Custos',self.custos),('Armazenamento',self.armazenamento),('Atribuição',self.credito),('Authcfg QGIS',self.auth),('',self.cache)]:af.addRow(n,c)
        self.aviso_externo=QLabel('Consulta unitária por ação explícita. Envia apenas coordenadas; nunca IDs, Labels ou topologia.');self.aviso_externo.setWordWrap(True);af.addRow(self.aviso_externo);b=QPushButton('Consultar localização da ocorrência selecionada');b.clicked.connect(self.geocodificar);af.addRow(b)
        self.previa_texto=QTextBrowser();self.previa_texto.setMaximumHeight(100);self.previa_texto.hide();f.addRow(self.previa_texto);self.imagem=QLabel();self.imagem.setAlignment(Qt.AlignCenter);f.addRow(self.imagem)
        self.estado=QLabel('Pronto para gerar offline. Sem fonte adequada, o mapa mostra apenas a investigação. Somente análises salvas entram no relatório.');self.estado.setWordWrap(True);v.addWidget(self.estado)
        h=QHBoxLayout();v.addLayout(h)
        for n,fn in [('Prévia de uma ocorrência',self.previa),('GERAR RELATÓRIO',self.gerar),('Salvar opções',self.salvar_config),('Fechar',self.close)]:b=QPushButton(n);b.clicked.connect(fn);h.addWidget(b)
        self.basemap_modo.currentIndexChanged.connect(self.modo_base);self.base.currentIndexChanged.connect(self.creditos_base);self.imagens.toggled.connect(self.modo_base);self.modo_base()
        c=rel.carregar_config(painel.base,painel.pacote['resultado']['meta']['uid'])
        for k,widget in [('margem',self.margem),('minimo_m',self.minimo),('opacidade',self.opacity)]:
            if k in c:widget.setValue(c[k])
        if c.get('logradouros'):
            from .decisoes import digest
            pref=c['logradouros']
            for i in range(1,self.ruas.count()):
                camada=self.ruas.itemData(i)
                if digest([camada.providerType(),camada.source()])==pref.get('origem'):
                    self.ruas.setCurrentIndex(i);self.ruacampo.setCurrentText(pref.get('campo',''));break
        adaptar_janela(self)
    def escolher_destino(self):
        p=QFileDialog.getExistingDirectory(self,'Pasta de destino',self.destino.text())
        if p:self.destino.setText(p)
    def modo_base(self):
        self.fontes_widget.setVisible(self.imagens.isChecked() and self.basemap_modo.currentData()=='SELECIONAR');self.basemap_modo.setEnabled(self.imagens.isChecked())
    def campos_cadastrais(self):
        self.cadcampo.clear();origem=self.cadfonte.currentData()
        self.cadcampo.addItem('')
        campos={k for t in self.painel.pacote['dossie']['tubulacoes'] if t['origem']==origem for k in t.get('atributos',{})}
        self.cadcampo.addItems(sorted(campos))
    def campos_rua(self):
        self.ruacampo.clear();c=self.ruas.currentData()
        if c:
            from .localizacao_relatorio import campos_localizacao
            self.ruacampo.addItem('');self.ruacampo.addItems(c.fields().names());campos=campos_localizacao(c.fields().names())
            if len(campos)==1:self.ruacampo.setCurrentText(campos[0])
    def config(self):
        from .decisoes import digest
        ruas=self.ruas.currentData();pref=dict(origem=digest([ruas.providerType(),ruas.source()]),campo=self.ruacampo.currentText()) if ruas else {}
        escopo=self.escopo.currentData();ids=[self.painel.atual['uid']] if escopo=='SELECAO' and self.painel.atual else [c['uid'] for c in self.painel.visiveis] if escopo=='FILTROS' else []
        return dict(nome=self.nome.text().strip() or 'Relatório',escopo=escopo,ids=ids,situacao_acompanhamento=self.acompanhamento.currentData(),imagens=self.imagens.isChecked(),xlsx=self.xlsx.isChecked(),localizacao=self.localizacao.isChecked(),localizacao_manual=self.manual.text(),historico=self.historico.isChecked(),tecnico=self.tecnico.isChecked(),paisagem=self.paisagem.isChecked(),margem=self.margem.value(),minimo_m=self.minimo.value(),opacidade=self.opacity.value(),brilho=self.brilho.value(),contraste=self.contraste.value(),contexto=self.contexto.isChecked(),preservar_imagens=self.preservar.isChecked(),basemap_modo=self.basemap_modo.currentData(),raio_ruas=self.raio.value(),ordenacao=self.ordem.currentText(),cinza=self.estilo.currentIndex()==1,mapas_online=self.online.isChecked(),lote_online_autorizado=self.lote_online.isChecked(),licenca_exportacao=self.licenca.isChecked(),atribuicao=self.atri.text(),extensao=self._extensao,filtros=self.painel.editor_filtros.configuracao(),logradouros=pref,referencia_cadastral=dict(origem=self.cadfonte.currentData(),campo=self.cadcampo.currentText()),localizacoes_externas=self._externas)
    def conexoes_qgis(self):
        from qgis.utils import iface
        if iface:iface.openDataSourceManagerPage('wms');self.estado.setText('Escolha a conexão existente no QGIS e adicione a camada desejada. Depois atualize a lista de fontes; credenciais permanecem no QGIS.')
        else:QMessageBox.information(self,'Conexões','Use o gerenciador de fontes do QGIS e atualize esta lista.')
    def atualizar_fontes(self):
        vistos={self.base.itemData(i).id() for i in range(self.base.count()) if self.base.itemData(i)}
        for c in QgsProject.instance().mapLayers().values():
            if c.isValid() and c.id() not in vistos:self.base.addItem(c.name(),c)
    def creditos_base(self):
        c=self.base.currentData()
        if c:
            from .fontes_relatorio import remota
            self.basemap_modo.setCurrentIndex(self.basemap_modo.findData('SELECIONAR'));self.licenca.setChecked(False);self.lote_online.setChecked(False);self.online.setChecked(False);m=c.metadata();self.atri.setText('; '.join(m.rights()+m.licenses()));self.fonte_info.setText(('Serviço externo: exige autorização antes de enviar a área do mapa.' if remota(c) else 'Fonte local: sem consulta de coordenadas a serviço externo.')+' A presença no projeto não comprova permissão de exportação.')
    def outra_fonte(self):
        provider,ok=QInputDialog.getItem(self,'Fonte cartográfica','Provedor QGIS:',['gdal','wms','ogr'],0,False)
        if not ok:return
        uri,ok=QInputDialog.getText(self,'Fonte cartográfica','Arquivo ou URI QGIS (autenticação por authcfg; não será persistida):')
        if not ok:return
        from .fontes_relatorio import uri_remota
        if uri_remota(provider,uri) and QMessageBox.question(self,'Consultar fonte externa','Carregar esta fonte pode consultar o serviço para ler seus metadados. Deseja permitir essa consulta? A exportação de mapas ainda dependerá das permissões da fonte.',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        c=QgsVectorLayer(uri,'Referência cartográfica',provider) if provider=='ogr' else QgsRasterLayer(uri,'Referência cartográfica',provider)
        if not c.isValid():QMessageBox.warning(self,'Fonte indisponível','Confira URI, provedor e autenticação no QGIS.');return
        self.extras.append(c);self.base.addItem(c.name(),c);self.base.setCurrentIndex(self.base.count()-1)
    def extensao(self):
        canvas=self.painel.legado.canvas
        if not canvas:return
        crs=QgsCoordinateReferenceSystem(self.painel.pacote['dossie']['contexto']['parametros']['crs']);r=QgsCoordinateTransform(canvas.mapSettings().destinationCrs(),crs,QgsProject.instance()).transformBoundingBox(canvas.extent());self._extensao=[r.xMinimum(),r.yMinimum(),r.xMaximum(),r.yMaximum()];self.estado.setText('Enquadramento atual copiado para o relatório; o mapa não foi modificado.')
    def geocodificar(self):
        from .localizacao_relatorio import Geocodificador
        caso=self.painel.atual
        if not caso:QMessageBox.information(self,'Localização','Selecione uma ocorrência no painel.');return
        try:
            _,p=rel.geometrias_caso(self.painel.pacote,caso)
            if p is None:raise ValueError('Sem ponto confiável; use descrição manual.')
            if not self._geocoder:self._geocoder=Geocodificador()
            c=dict(endpoint=self.endpoint.text(),termos=self.termos.text(),custos=self.custos.text(),armazenamento=self.armazenamento.text(),atribuicao=self.credito.text(),cache_permitido=self.cache.isChecked(),authcfg=self.auth.text());pt=p.asPoint();r=self._geocoder.consultar(pt.x(),pt.y(),self.painel.pacote['dossie']['contexto']['parametros']['crs'],c,self.externo.isChecked());self._externas[caso['uid']]=r;self.estado.setText(r['texto'])
        except Exception as e:QMessageBox.warning(self,'Referência não obtida',str(e))
    def salvar_config(self):rel.salvar_config(self.painel.base,self.painel.pacote['resultado']['meta']['uid'],self.config());self.estado.setText('Preferências salvas; nenhuma análise ou versão hidráulica foi modificada.')
    def executar(self,pasta,config):
        from .localizacao_relatorio import Logradouros
        preparado=self.preparar_fontes(config)
        if preparado is None:return None
        config,bases=preparado
        s=sistema(self);s.vincular(self);self._ocupado=True
        try:
            with s.operacao('Gerando relatório ilustrado',self.nome.text(),cancelar=lambda:None) as o:
                camada,campo=self.logradouros();ruas=Logradouros(camada,campo,self.painel.pacote['dossie']['contexto']['parametros']['crs'],o.ponto) if camada else None
                return rel.gerar(self.painel.base,self.painel.pacote,self.painel.casos,self.painel.modo.currentData(),pasta,config,bases,ruas,o.atualizar,o.ponto,ao_falhar_basemap=self.continuar_sem_base)
        finally:self._ocupado=False
    def logradouros(self):
        from .localizacao_relatorio import sugerir_logradouros
        c=self.ruas.currentData()
        if c:return c,self.ruacampo.currentText()
        candidatos=sugerir_logradouros(QgsProject.instance().mapLayers().values())
        if len(candidatos)==1:return candidatos[0]
        return None,None
    def preparar_fontes(self,config):
        from .fontes_relatorio import resolver,BasemapPendente
        dados=rel.snapshot(self.painel.base,self.painel.pacote,self.painel.casos,self.painel.modo.currentData(),config)
        if not dados['ocorrencias']:raise ValueError('Nenhuma ocorrência nesta seleção.')
        bases=list(QgsProject.instance().layerTreeRoot().layerOrder()) if config.get('basemap_modo')=='AUTOMATICO' else [self.base.currentData()] if self.base.currentData() else []
        if config.get('imagens') and config.get('basemap_modo')=='SELECIONAR' and not bases:
            self.estado.setText('Escolha uma fonte ou use Automático / Sem mapa-base.');return None
        try:
            fontes,c=resolver(bases,config,len(dados['ocorrencias']));return c,fontes
        except BasemapPendente as e:
            msg=QMessageBox(self);msg.setWindowTitle('Escolha como continuar');msg.setText(str(e));msg.setInformativeText('A investigação e a seleção serão preservadas. Nenhuma consulta foi enviada.');sem=msg.addButton('Gerar sem mapa-base',QMessageBox.AcceptRole);outra=msg.addButton('Selecionar outra fonte',QMessageBox.ActionRole);configurar=msg.addButton('Configurar fonte autorizada',QMessageBox.ActionRole);uma=msg.addButton('Somente uma ocorrência',QMessageBox.ActionRole) if e.uma_ocorrencia else None;msg.addButton('Cancelar',QMessageBox.RejectRole);msg.exec_();escolha=msg.clickedButton()
            if escolha==sem:return dict(config,basemap_modo='NENHUM',avisos_basemap=['Mapa-base não utilizado por escolha do usuário: '+str(e)]),[]
            if escolha==outra:self.basemap_modo.setCurrentIndex(self.basemap_modo.findData('SELECIONAR'));self.base.setFocus()
            elif escolha==configurar:self.avancado.setChecked(True);self.estado.setText('Confira a permissão real e os créditos da fonte. Fontes com restrição explícita não podem ser liberadas por uma caixa de seleção.');self.licenca.setFocus()
            elif uma is not None and escolha==uma:
                itens=[r['titulo']+' · '+r['uid'][:8] for r in dados['ocorrencias']];item,ok=QInputDialog.getItem(self,'Uma ocorrência','Escolha a ocorrência para este relatório:',itens,0,False)
                if ok:return self.preparar_fontes(dict(config,escopo='SELECAO',ids=[dados['ocorrencias'][itens.index(item)]['uid']]))
            return None
    def continuar_sem_base(self,motivo):
        msg=QMessageBox(self);msg.setWindowTitle('Mapa-base indisponível');msg.setText(motivo);msg.setInformativeText('Continuar mantém tubulações, dispositivos, limites e a seleção de ocorrências. O relatório registrará que o mapa-base não foi utilizado.');continuar=msg.addButton('Continuar sem mapa-base',QMessageBox.AcceptRole);msg.addButton('Cancelar relatório',QMessageBox.RejectRole);msg.exec_();return msg.clickedButton()==continuar
    def previa(self):
        try:
            import tempfile
            config=self.config();dados=rel.snapshot(self.painel.base,self.painel.pacote,self.painel.casos,self.painel.modo.currentData(),config)
            if not dados['ocorrencias']:raise ValueError('Nenhuma ocorrência na seleção')
            uid=self.painel.atual['uid'] if self.painel.atual and any(r['uid']==self.painel.atual['uid'] for r in dados['ocorrencias']) else dados['ocorrencias'][0]['uid']
            config.update(escopo='SELECAO',ids=[uid],xlsx=False,preservar_imagens=True);p=Path(tempfile.gettempdir())/('wna_previa_'+uuid4().hex);d=self.executar(p,config)
            if d is None:return
            self.previa_texto.show()
            self.previa_texto.setPlainText(d['ocorrencias'][0]['titulo']+'\nAcompanhamento: '+d['ocorrencias'][0]['acompanhamento']+' · Resultado: '+d['ocorrencias'][0]['resultado']+'\n'+d['ocorrencias'][0]['localizacao']['texto']);png=p/'mapa_00000.png'
            if png.exists():
                pix=QPixmap(str(png)).scaled(620,330,Qt.KeepAspectRatio,Qt.SmoothTransformation);self.imagem.setPixmap(pix);self.imagem.setMinimumSize(pix.size())
            self.previa_texto.setFixedHeight(80)
            self.scroll.widget().layout().activate();self.scroll.ensureWidgetVisible(self.imagem,0,0)
            QTimer.singleShot(0,lambda:self.scroll.ensureWidgetVisible(self.imagem,0,0))
            self._ultima_previa=p;self.estado.setText('Prévia pronta: capa, resumo e uma ocorrência. Use a rolagem para consultar o mapa.');self.estado.setToolTip(str(p))
        except Exception as e:QMessageBox.warning(self,'Prévia não gerada',str(e))
    def gerar(self):
        pasta=self.destino.text().strip()
        if not pasta:self.escolher_destino();pasta=self.destino.text().strip()
        if not pasta:return
        try:
            p=Path(pasta)/('Relatorio_'+uuid4().hex[:10]);dados=self.executar(p,self.config())
            if dados is None:return
            self.salvar_config();self.estado.setText('Relatório concluído e validado: '+str(p))
        except Exception as e:QMessageBox.warning(self,'Relatório não publicado',str(e)+'\nRelatórios anteriores preservados.')
    def closeEvent(self,e):
        if self._ocupado:e.ignore();return
        e.accept()
