"""Configuração rápida, prévia e fontes opcionais, sem burocracia de revisão."""
from pathlib import Path
from uuid import uuid4
from qgis.PyQt.QtCore import Qt,QUrl
from qgis.PyQt.QtGui import QPixmap,QDesktopServices
from qgis.PyQt.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QComboBox,QLineEdit,QCheckBox,QDoubleSpinBox,QSpinBox,QPushButton,QLabel,QGroupBox,QScrollArea,QWidget,QFileDialog,QMessageBox,QInputDialog,QTextBrowser)
from qgis.core import QgsProject,QgsRasterLayer,QgsVectorLayer,QgsCoordinateReferenceSystem,QgsCoordinateTransform
from auditoria_fronteiras.ui_comum import adaptar_janela
from auditoria_fronteiras.atividade import sistema
from . import relatorio_investigacao as rel


class RelatorioDialog(QDialog):
    def __init__(self,painel):
        super().__init__(painel);self.painel=painel;self.setWindowTitle('Gerar relatório de investigação');self.resize(860,680);self._ocupado=False;self.extras=[];self._extensao=None;self._externas={};self._geocoder=None
        v=QVBoxLayout(self);scroll=QScrollArea();scroll.setWidgetResizable(True);w=QWidget();scroll.setWidget(w);v.addWidget(scroll,1);f=QFormLayout(w);self.nome=QLineEdit('Relatório de investigação');f.addRow('Nome',self.nome)
        self.escopo=QComboBox()
        for n,k in [('Todas as ocorrências','TODOS'),('Somente analisadas','ANALISADOS'),('Somente pendentes','PENDENTES'),('Correção necessária','CORRECAO'),('Locais manuais','MANUAIS'),('Ocorrência selecionada','SELECAO'),('Filtros ativos (todas as páginas)','FILTROS')]:self.escopo.addItem(n,k)
        f.addRow('Ocorrências',self.escopo);self.imagens=QCheckBox('Incluir mapas');self.imagens.setChecked(True);f.addRow(self.imagens);self.xlsx=QCheckBox('XLSX da mesma seleção');f.addRow(self.xlsx)
        self.base=QComboBox();self.base.addItem('Sem mapa-base',None)
        self.ruas=QComboBox();self.ruas.addItem('Sem camada de ruas',None)
        for c in QgsProject.instance().mapLayers().values():
            if c.isValid():self.base.addItem(c.name(),c)
            if isinstance(c,QgsVectorLayer) and c.isValid() and c.geometryType()==1:self.ruas.addItem(c.name(),c)
        f.addRow('Utilizar mapa-base do projeto',self.base);self.base.currentIndexChanged.connect(self.creditos_base);conexoes=QPushButton('Usar conexões cadastradas no QGIS…');conexoes.clicked.connect(self.conexoes_qgis);f.addRow(conexoes);refresh=QPushButton('Atualizar lista de fontes do projeto');refresh.clicked.connect(self.atualizar_fontes);f.addRow(refresh);b=QPushButton('Selecionar outra fonte…');b.clicked.connect(self.outra_fonte);f.addRow(b)
        self.ruacampo=QComboBox();self.ruas.currentIndexChanged.connect(self.campos_rua);f.addRow('Camada local de logradouros',self.ruas);f.addRow('Campo do nome da rua',self.ruacampo)
        self.localizacao=QCheckBox('Incluir referência de localização');self.localizacao.setChecked(True);f.addRow(self.localizacao);self.manual=QLineEdit();self.manual.setPlaceholderText('Referência manual opcional, sem inventar endereço');f.addRow('Referência manual',self.manual)
        self.cadfonte=QComboBox();self.cadfonte.addItem('Não usar atributo cadastral',None);self.cadcampo=QComboBox()
        fontes={(t['origem'],t['camada']) for t in painel.pacote['dossie']['tubulacoes']}
        for origem,nome in sorted(fontes):self.cadfonte.addItem(nome,origem)
        self.cadfonte.currentIndexChanged.connect(self.campos_cadastrais);f.addRow('Referência cadastral (opcional)',self.cadfonte);f.addRow('Campo explicitamente escolhido',self.cadcampo)
        self.atri=QLineEdit();f.addRow('Atribuição cartográfica',self.atri);self.licenca=QCheckBox('A fonte permite exportação e armazenamento neste relatório');f.addRow(self.licenca)
        self.lote_online=QCheckBox('O provedor permite exportação cartográfica em lote para esta seleção');f.addRow(self.lote_online)
        self.online=QCheckBox('Permitir requisições de mapa ao provedor selecionado');self.online.setToolTip('Envia a área/escala do mapa. Não envia atributos hidráulicos. Sem autorização, use fontes locais.');f.addRow(self.online)
        self.avancado=QGroupBox('Opções avançadas');self.avancado.setCheckable(True);self.avancado.setChecked(False);aw=QWidget();af=QFormLayout(aw);al=QVBoxLayout(self.avancado);al.addWidget(aw);aw.hide();self.avancado.toggled.connect(aw.setVisible);f.addRow(self.avancado)
        self.estilo=QComboBox();self.estilo.addItems(['Estilo da fonte selecionada','Tons de cinza']);self.opacity=QDoubleSpinBox();self.opacity.setRange(0,1);self.opacity.setSingleStep(.1);self.opacity.setValue(.65);self.brilho=QSpinBox();self.brilho.setRange(-255,255);self.contraste=QSpinBox();self.contraste.setRange(-100,100);self.margem=QDoubleSpinBox();self.margem.setRange(0,5);self.margem.setValue(.25);self.minimo=QDoubleSpinBox();self.minimo.setRange(10,100000);self.minimo.setValue(100);self.raio=QDoubleSpinBox();self.raio.setRange(0,1000);self.raio.setValue(100)
        self.contexto=QCheckBox('Incluir mapa complementar de contexto');self.historico=QCheckBox('Incluir histórico');self.tecnico=QCheckBox('Incluir detalhes técnicos');self.paisagem=QCheckBox('Página em paisagem');self.preservar=QCheckBox('Preservar PNGs renderizados (conforme licença)');self.ordem=QComboBox();self.ordem.addItems(['titulo','resultado','prioridade','origem'])
        for n,c in [('Estilo',self.estilo),('Opacidade',self.opacity),('Brilho',self.brilho),('Contraste',self.contraste),('Margem relativa',self.margem),('Extensão mínima (m)',self.minimo),('Busca de ruas (m)',self.raio),('Ordenar/agrupar por',self.ordem),('',self.contexto),('',self.historico),('',self.tecnico),('',self.paisagem),('',self.preservar)]:af.addRow(n,c)
        ext=QPushButton('Usar enquadramento atual do mapa');ext.clicked.connect(self.extensao);af.addRow(ext);lim=QPushButton('Restaurar enquadramento automático');lim.clicked.connect(lambda:setattr(self,'_extensao',None));af.addRow(lim)
        self.externo=QCheckBox('PERMITIR CONSULTAS EXTERNAS DE LOCALIZAÇÃO');self.externo.setChecked(False);af.addRow(self.externo)
        self.endpoint=QLineEdit();self.endpoint.setPlaceholderText('HTTPS corporativo/contratado, compatível com reverse JSON');self.termos=QLineEdit();self.custos=QLineEdit();self.armazenamento=QLineEdit();self.credito=QLineEdit();self.auth=QLineEdit();self.cache=QCheckBox('Provedor permite cache em memória da sessão')
        for n,c in [('Serviço',self.endpoint),('Termos/uso em relatórios',self.termos),('Custos conhecidos',self.custos),('Armazenamento autorizado',self.armazenamento),('Atribuição do serviço',self.credito),('Authcfg QGIS (opcional)',self.auth),('',self.cache)]:af.addRow(n,c)
        self.aviso_externo=QLabel('Consulta somente a ocorrência selecionada, por ação explícita. Envia apenas latitude/longitude, sem IDs, Labels ou topologia. Não é executada em lote ao gerar relatório.');self.aviso_externo.setWordWrap(True);af.addRow(self.aviso_externo);geo=QPushButton('Consultar referência da ocorrência selecionada');geo.clicked.connect(self.geocodificar);af.addRow(geo)
        self.previa_texto=QTextBrowser();self.previa_texto.setMaximumHeight(130);f.addRow(self.previa_texto);self.imagem=QLabel();self.imagem.setAlignment(Qt.AlignCenter);f.addRow(self.imagem)
        self.estado=QLabel('Somente registros salvos entram no relatório. PDF funciona offline; mapas e ruas não comprovam conectividade.');self.estado.setWordWrap(True);v.addWidget(self.estado)
        h=QHBoxLayout();v.addLayout(h)
        for n,fn in [('Prévia de capa/resumo/ocorrência',self.previa),('Gerar PDF…',self.gerar),('Salvar configurações',self.salvar_config),('Fechar',self.close)]:b=QPushButton(n);b.clicked.connect(fn);h.addWidget(b)
        c=rel.carregar_config(painel.base,painel.pacote['resultado']['meta']['uid'])
        for k,widget in [('margem',self.margem),('minimo_m',self.minimo),('opacidade',self.opacity)]:
            if k in c:widget.setValue(c[k])
        adaptar_janela(self)
    def campos_cadastrais(self):
        self.cadcampo.clear();origem=self.cadfonte.currentData()
        self.cadcampo.addItem('')
        campos={k for t in self.painel.pacote['dossie']['tubulacoes'] if t['origem']==origem for k in t.get('atributos',{})}
        self.cadcampo.addItems(sorted(campos))
    def campos_rua(self):
        self.ruacampo.clear();c=self.ruas.currentData()
        if c:self.ruacampo.addItems(c.fields().names())
    def config(self):
        escopo=self.escopo.currentData();ids=[self.painel.atual['uid']] if escopo=='SELECAO' and self.painel.atual else [c['uid'] for c in self.painel.visiveis] if escopo=='FILTROS' else []
        return dict(nome=self.nome.text().strip() or 'Relatório',escopo=escopo,ids=ids,imagens=self.imagens.isChecked(),xlsx=self.xlsx.isChecked(),localizacao=self.localizacao.isChecked(),localizacao_manual=self.manual.text(),historico=self.historico.isChecked(),tecnico=self.tecnico.isChecked(),paisagem=self.paisagem.isChecked(),margem=self.margem.value(),minimo_m=self.minimo.value(),opacidade=self.opacity.value(),brilho=self.brilho.value(),contraste=self.contraste.value(),contexto=self.contexto.isChecked(),preservar_imagens=self.preservar.isChecked(),raio_ruas=self.raio.value(),ordenacao=self.ordem.currentText(),cinza=self.estilo.currentIndex()==1,mapas_online=self.online.isChecked(),lote_online_autorizado=self.lote_online.isChecked(),licenca_exportacao=self.licenca.isChecked(),atribuicao=self.atri.text(),extensao=self._extensao,filtros=self.painel.editor_filtros.configuracao(),referencia_cadastral=dict(origem=self.cadfonte.currentData(),campo=self.cadcampo.currentText()),localizacoes_externas=self._externas)
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
        if c and hasattr(self,'atri') and not self.atri.text().strip():
            m=c.metadata();self.atri.setText('; '.join(m.rights()+m.licenses()))
    def outra_fonte(self):
        provider,ok=QInputDialog.getItem(self,'Fonte cartográfica','Provedor QGIS:',['gdal','wms','ogr'],0,False)
        if not ok:return
        uri,ok=QInputDialog.getText(self,'Fonte cartográfica','Arquivo ou URI QGIS (autenticação por authcfg; não será persistida):')
        if not ok:return
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
        s=sistema(self);s.vincular(self);self._ocupado=True
        try:
            with s.operacao('Gerando relatório ilustrado',self.nome.text(),cancelar=lambda:None) as o:
                ruas=Logradouros(self.ruas.currentData(),self.ruacampo.currentText(),self.painel.pacote['dossie']['contexto']['parametros']['crs'],o.ponto) if self.ruas.currentData() else None
                c=self.base.currentData();return rel.gerar(self.painel.base,self.painel.pacote,self.painel.casos,self.painel.modo.currentData(),pasta,config,[c] if c else [],ruas,o.atualizar,o.ponto)
        finally:self._ocupado=False
    def previa(self):
        try:
            import tempfile
            config=self.config();dados=rel.snapshot(self.painel.base,self.painel.pacote,self.painel.casos,self.painel.modo.currentData(),config)
            if not dados['ocorrencias']:raise ValueError('Nenhuma ocorrência na seleção')
            config.update(escopo='SELECAO',ids=[dados['ocorrencias'][0]['uid']],xlsx=False,preservar_imagens=True);p=Path(tempfile.gettempdir())/('wna_previa_'+uuid4().hex);d=self.executar(p,config)
            self.previa_texto.setPlainText(d['nome']+'\nPrévia de uma ocorrência · '+str(d['contagens'])+'\n'+d['ocorrencias'][0]['localizacao']['texto']);png=p/'mapa_00000.png'
            if png.exists():self.imagem.setPixmap(QPixmap(str(png)).scaled(680,400,Qt.KeepAspectRatio,Qt.SmoothTransformation))
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p/'INVESTIGACAO.pdf')));self.estado.setText('Prévia (capa, resumo e uma ocorrência): '+str(p))
        except Exception as e:QMessageBox.warning(self,'Prévia não gerada',str(e))
    def gerar(self):
        pasta=QFileDialog.getExistingDirectory(self,'Pasta para novo relatório')
        if not pasta:return
        try:
            p=Path(pasta)/('Relatorio_'+uuid4().hex[:10]);self.executar(p,self.config());self.salvar_config();self.estado.setText('Relatório concluído e validado: '+str(p))
        except Exception as e:QMessageBox.warning(self,'Relatório não publicado',str(e)+'\nRelatórios anteriores preservados.')
    def closeEvent(self,e):
        if self._ocupado:e.ignore();return
        e.accept()
