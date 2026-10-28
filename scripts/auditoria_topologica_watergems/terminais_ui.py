"""Seleção explícita de terminais por tabela, identificação, seleção GIS ou mapa."""
from qgis.PyQt.QtCore import Qt,pyqtSignal
from qgis.PyQt.QtWidgets import (QGroupBox,QVBoxLayout,QHBoxLayout,QLineEdit,QPushButton,
    QTableWidget,QTableWidgetItem,QLabel,QAbstractItemView,QInputDialog,QMessageBox,QDoubleSpinBox,QWidget)
from qgis.core import (QgsGeometry,QgsFeature,QgsSpatialIndex,QgsPointXY,
    QgsCoordinateReferenceSystem,QgsCoordinateTransform,QgsUnitTypes)
from .corredores import buscar_terminais,resolver_terminal


class SeletorTerminais(QGroupBox):
    alterado=pyqtSignal()
    def __init__(self,dono,titulo,cor):
        super().__init__(titulo,dono);self.dono=dono;self.cor=cor;self.terminais=[];self._captura=None
        v=QVBoxLayout(self);self.busca=QLineEdit();self.busca.setPlaceholderText('Label exato/parcial ou DomainElementID');v.addWidget(self.busca)
        a=QHBoxLayout();v.addLayout(a)
        for nome,fn in [('Buscar',self.procurar),('Usar seleção QGIS',self.usar_selecao),('Clicar no mapa',self.capturar)]:
            b=QPushButton(nome);b.clicked.connect(lambda checked=False,fn=fn:fn());a.addWidget(b)
        self.tabela=QTableWidget(0,4);self.tabela.setHorizontalHeaderLabels(['ID','Label','Tipo','Porta']);self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows);self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers);self.tabela.setMaximumHeight(100);v.addWidget(self.tabela)
        a=QHBoxLayout();v.addLayout(a)
        b=QPushButton('Adicionar linhas escolhidas');b.clicked.connect(self.adicionar_linhas);a.addWidget(b);b=QPushButton('Limpar terminais');b.clicked.connect(self.limpar);a.addWidget(b)
        self.raio=QDoubleSpinBox();self.raio.setRange(.01,10000);self.raio.setValue(10);self.raio.setSuffix(' m');self.raio.setToolTip('Busca de candidatos ao clique; nenhum nó é escolhido só pela proximidade.');a.addWidget(self.raio)
        self.escolhidos=QLabel('Nenhum terminal selecionado');self.escolhidos.setWordWrap(True);v.addWidget(self.escolhidos)
        self.busca.returnPressed.connect(self.procurar)
        self.setCheckable(True)
        def expandir(b):
            for w in self.findChildren(QWidget):
                if w.parentWidget() is self and w is not self.escolhidos:w.setVisible(b)
        self.toggled.connect(expandir);self.setChecked(False)

    @property
    def pacote(self):return self.dono.painel.pacote
    def catalogo(self):
        if not hasattr(self.dono,'_catalogo_terminais'):
            from collections import defaultdict
            rows=buscar_terminais(self.pacote,self.dono.modo,limite=10**9);indice=defaultdict(list)
            for t in rows:indice[t['id']].append(t)
            self.dono._catalogo_terminais=(rows,indice)
        return self.dono._catalogo_terminais
    def preencher(self,rows):
        self.tabela.setRowCount(len(rows))
        for n,r in enumerate(rows):
            for c,k in enumerate(('id','label','tipo','porta')):
                i=QTableWidgetItem(str(r.get(k,'')));i.setData(Qt.UserRole,r);i.setToolTip(str(r));self.tabela.setItem(n,c,i)
        self.tabela.resizeColumnsToContents()
    def procurar(self):
        texto=self.busca.text().strip().casefold();rows,_=self.catalogo();self.preencher([t for t in rows if not texto or texto==str(t['id']) or texto in str(t['label']).casefold()][:200])
    def adicionar_linhas(self):self.adicionar([self.tabela.item(n,0).data(Qt.UserRole) for n in sorted({i.row() for i in self.tabela.selectedIndexes()})])
    def adicionar(self,rs):
        chaves={(t['id'],t.get('porta')) for t in self.terminais}
        for r in rs:
            k=(r['id'],r.get('porta'))
            if k not in chaves:self.terminais.append(dict(r));chaves.add(k)
        self.escolhidos.setText(f"{len(self.terminais)} terminais: "+'; '.join(str(t.get('label') or t['id'])+' ['+str(t['id'])+' / '+str(t.get('porta',''))+']' for t in self.terminais[:12])+(' …' if len(self.terminais)>12 else ''));self.escolhidos.setToolTip('\n'.join(str(t) for t in self.terminais));self.alterado.emit()
    def limpar(self):self.terminais=[];self.adicionar([])
    def valores(self):return [dict(id=t['id'],porta=t['porta']) for t in self.terminais]
    def usar_selecao(self):
        from .ferramentas_investigacao_ui import selecionados
        rs=selecionados(self.dono.painel);el=self.pacote['topologia']['modelo']['elementos'];candidatos=[]
        for v in rs:
            if v['origem']!='WG':continue
            i=int(v['chave'])
            if el[i]['familia'] not in ('NO','DISPOSITIVO'):continue
            candidatos.extend(self.catalogo()[1].get(i,[]))
        if not candidatos:QMessageBox.information(self,'Terminais','Selecione nós ou dispositivos das camadas desta versão WaterGEMS, ou use busca/clique.');return
        self.preencher(candidatos)
        # Portas múltiplas permanecem candidatas até escolha explícita na tabela.
        unicos=[r for r in candidatos if sum(t['id']==r['id'] for t in candidatos)==1];self.adicionar(unicos)

    def indice(self):
        if not self.pacote['resultado']['meta']['parametros'].get('espacial_habilitado'):raise ValueError('Valide CRS/unidades para escolher terminais pelo mapa; busca topológica continua disponível')
        crs=QgsCoordinateReferenceSystem(self.pacote['dossie']['contexto']['parametros']['crs'])
        if crs.isGeographic() or crs.mapUnits()!=QgsUnitTypes.DistanceMeters:raise ValueError('Escolha espacial requer CRS métrico validado')
        if not hasattr(self.dono,'_indice_terminais'):
            index=QgsSpatialIndex();dados=[];el=self.pacote['topologia']['modelo']['elementos']
            for i,g in (self.pacote.get('geometrias') or {}).items():
                if el[i]['familia'] not in ('NO','DISPOSITIVO') or g.type()!=0 or g.isEmpty():continue
                f=QgsFeature(len(dados));f.setGeometry(g);index.addFeature(f);dados.append((i,QgsGeometry(g)))
            self.dono._indice_terminais=(index,dados,crs)
        return self.dono._indice_terminais

    def capturar(self):
        from qgis.gui import QgsMapToolEmitPoint
        canvas=self.dono.painel.legado.canvas
        if not canvas:QMessageBox.information(self,'Mapa','Mapa não disponível nesta sessão.');return
        try:self.indice()
        except ValueError as e:QMessageBox.information(self,'Mapa',str(e));return
        self.fechar_captura();anterior=canvas.mapTool();seletor=self
        class Ferramenta(QgsMapToolEmitPoint):
            def keyPressEvent(self,event):
                if event.key()==Qt.Key_Escape:seletor.fechar_captura()
                else:super().keyPressEvent(event)
        tool=Ferramenta(canvas);self._captura=(tool,anterior)
        def clicou(p,botao):
            if botao!=Qt.LeftButton:return
            self.fechar_captura()
            try:
                index,dados,crs=self.indice();p=QgsCoordinateTransform(canvas.mapSettings().destinationCrs(),crs,self.dono.painel.legado.projeto).transform(p);g=QgsGeometry.fromPointXY(p);box=g.boundingBox();box.grow(self.raio.value());rows=[]
                for n in index.intersects(box):
                    i,geom=dados[n]
                    if g.distance(geom)<=self.raio.value():rows.extend(self.catalogo()[1].get(i,[]))
                self.preencher(rows)
                if not rows:QMessageBox.information(self,'Terminais','Nenhum terminal disponível no raio informado.');return
                nomes=[str(t['label'])+' · '+str(t['id'])+' / '+t['porta'] for t in rows];nome,ok=QInputDialog.getItem(self,'Confirmar terminal','Escolha o nó/porta; proximidade não comprova conectividade',nomes,0,False)
                if ok:self.adicionar([rows[nomes.index(nome)]]);self.dono.destacar_terminais()
            except Exception as e:QMessageBox.warning(self,'Seleção espacial',str(e))
        tool.canvasClicked.connect(clicou);canvas.setMapTool(tool);self.dono.estado.setText('Clique para escolher um terminal. Verde: origens; vermelho: destinos. Esc cancela; zoom é explícito.')

    def fechar_captura(self):
        if not self._captura:return
        tool,anterior=self._captura;canvas=self.dono.painel.legado.canvas
        if canvas and canvas.mapTool() is tool:canvas.setMapTool(anterior) if anterior else canvas.unsetMapTool(tool)
        self._captura=None

    def adicionar_regioes(self):
        try:
            index,dados,crs=self.indice();rows=[];vistos=set();fontes=[]
            for camada in self.dono.painel.legado.projeto.mapLayers().values():
                if not hasattr(camada,'geometryType') or camada.geometryType()!=2 or not camada.isValid():continue
                for f in camada.selectedFeatures():
                    g=QgsGeometry(f.geometry());g.transform(QgsCoordinateTransform(camada.crs(),crs,self.dono.painel.legado.projeto))
                    if not g.isGeosValid():raise ValueError('Polígono inválido; corrija uma cópia antes de derivar destinos')
                    from auditoria_fronteiras.entradas import valor_python
                    from .decisoes import digest
                    ref=dict(fonte=camada.source(),provedor=camada.providerType(),crs=camada.crs().toWkt(),wkb=bytes(f.geometry().asWkb()).hex(),atributos={k.name():valor_python(f[k.name()]) for k in camada.fields()});fontes.append(dict(ref,assinatura=digest(ref)))
                    for n in index.intersects(g.boundingBox()):
                        i,p=dados[n]
                        if i in vistos or not g.intersects(p):continue
                        # Somente nós de incidência única; dispositivos com portas
                        # distintas exigem escolha explícita, não união de portas.
                        ts=self.catalogo()[1].get(i,[])
                        if len(ts)==1:rows.extend(ts);vistos.add(i)
                        if len(rows)>500:raise ValueError('Mais de 500 destinos nas regiões; refine os polígonos ou selecione um grupo de terminais. Nenhuma amostragem silenciosa aplicada.')
            if not fontes:raise ValueError('Selecione polígonos no QGIS para derivar destinos')
            self.adicionar(rows);self.dono._regioes_destinos=fontes
        except Exception as e:QMessageBox.warning(self,'Destinos por regiões',str(e))
