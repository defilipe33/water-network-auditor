"""Ações complementares do painel; provedores e mapa sempre na GUI."""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,
    QLineEdit,QPlainTextEdit,QPushButton,QDialogButtonBox,QTableWidget,QTableWidgetItem,
    QDoubleSpinBox,QComboBox,QCheckBox,QMessageBox,QFileDialog,QAbstractItemView)
from qgis.core import QgsGeometry,QgsCoordinateReferenceSystem,QgsCoordinateTransform,QgsProject,QgsPointXY
from auditoria_fronteiras.ui_comum import adaptar_janela
from auditoria_fronteiras.atividade import acompanhada,falha
from . import conjuntos_investigacao as storage
from . import locais_manuais as manuais


class DialogoLocal(QDialog):
    def __init__(self,painel,posicao,registro=None,selecionados=()):
        super().__init__(painel);self.painel=painel;self.registro=registro;self.posicao=posicao;self.setWindowTitle('Local manual de investigação');self.resize(750,540)
        v=QVBoxLayout(self);self.form=QFormLayout();v.addLayout(self.form)
        self.titulo=QLineEdit();self.obs=QPlainTextEdit();self.obs.setMaximumHeight(90);self.classificacao=QLineEdit()
        self.x=QDoubleSpinBox();self.y=QDoubleSpinBox()
        for w,n in ((self.x,'x'),(self.y,'y')):w.setRange(-1e10,1e10);w.setDecimals(9);w.setValue(posicao[n])
        self.crs=QLineEdit(posicao['crs']);self.raio=QDoubleSpinBox();self.raio.setRange(0,100000);self.raio.setValue(15);self.raio.setSuffix(' m')
        for nome,w in [('Título (opcional)',self.titulo),('Classificação livre (opcional)',self.classificacao),('Observação (opcional)',self.obs),('X',self.x),('Y',self.y),('CRS do ponto',self.crs),('Raio de candidatos',self.raio)]:self.form.addRow(nome,w)
        aviso=QLabel('Marque os elementos que deseja investigar. Proximidade e associação manual não comprovam conexão. Mover o ponto não refaz vínculos: confira sua seleção.');aviso.setWordWrap(True);v.addWidget(aviso)
        self.buscar=QPushButton('Localizar candidatos próximos');self.buscar.clicked.connect(lambda:self.procurar());v.addWidget(self.buscar)
        self.texto=QLineEdit();self.texto.setPlaceholderText('Filtrar candidatos por Label, ID ou camada');self.texto.textChanged.connect(self.filtrar);v.addWidget(self.texto)
        buscar_id=QPushButton('Procurar identificador no cadastro (independente da proximidade)');buscar_id.clicked.connect(self.procurar_id);v.addWidget(buscar_id)
        self.tabela=QTableWidget(0,5);self.tabela.setHorizontalHeaderLabels(['Relacionar','Origem','Identificador / Label','Camada / Tipo','Distância (m)']);self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers);v.addWidget(self.tabela,1);self.vinculos=[]
        if registro:
            self.titulo.setText(registro['dados'].get('titulo',''));self.obs.setPlainText(registro['dados'].get('observacoes',''))
            self.classificacao.setText(registro['dados'].get('classificacao',''))
            self.adicionar(registro['vinculos'],True)
        self.adicionar(selecionados,True)
        botoes=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);botoes.accepted.connect(self.salvar);botoes.rejected.connect(self.reject);v.addWidget(botoes);adaptar_janela(self)

    def adicionar(self,vs,marcar=False):
        existentes={(v['origem'],v['chave']) for v in self.vinculos}
        for v in vs:
            if (v['origem'],v['chave']) in existentes:continue
            existentes.add((v['origem'],v['chave']));n=len(self.vinculos);self.vinculos.append(v);self.tabela.insertRow(n)
            d=v.get('dados',{});item=QTableWidgetItem();item.setFlags(Qt.ItemIsEnabled|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Checked if marcar else Qt.Unchecked);self.tabela.setItem(n,0,item)
            for col,s in enumerate((v['origem'],str(d.get('label',d.get('id',d.get('exibicao',v['chave'])))),str(d.get('camada',d.get('tipo',''))),str(round(v['distancia_m'],3)) if 'distancia_m' in v else 'Vínculo selecionado'),1):
                item=QTableWidgetItem(s);item.setToolTip(s+'\nChave: '+v['chave']);self.tabela.setItem(n,col,item)
        self.tabela.resizeColumnsToContents()

    def filtrar(self):
        texto=self.texto.text().casefold()
        for n in range(self.tabela.rowCount()):self.tabela.setRowHidden(n,not any(texto in self.tabela.item(n,c).text().casefold() for c in range(1,4)))

    def procurar(self):
        try:self.adicionar(manuais.candidatos(self.painel.pacote,self.painel.indice_atributos,self.x.value(),self.y.value(),self.crs.text(),self.raio.value()))
        except Exception as e:QMessageBox.warning(self,'Busca de candidatos',str(e)+'\nVocê pode salvar o ponto sem vínculos e associá-los depois.')

    def procurar_id(self):
        texto=self.texto.text().strip().casefold()
        if not texto:QMessageBox.information(self,'Procurar elemento','Informe um Label, identificador ou texto da camada no campo de busca.');return
        vs=[]
        for i,e in self.painel.pacote['topologia']['modelo']['elementos'].items():
            if e.get('excluido') is False and (texto==str(i) or texto in str(e['label']).casefold()):vs.append(storage.vinculo_wg(self.painel.pacote,i))
            if len(vs)>=300:break
        for v,g,_,_ in manuais.redes_gis(self.painel.pacote,self.painel.legado.projeto):
            if texto in (str(v['dados'].get('id',''))+' '+v['dados']['camada']).casefold():vs.append(v)
            if len(vs)>=300:break
        for uid,a in self.painel.indice_atributos.areas.items():
            if texto in (str(a.get('exibicao',''))+' '+str(a.get('chave',''))+' '+a['camada']).casefold():vs.append(dict(origem='AREA',chave=uid,natureza='MANUAL',dados=dict(exibicao=a.get('exibicao'),camada=a['camada'],origem=a['origem'])))
            if len(vs)>=300:break
        for c in self.painel.casos:
            if c.get('local_uid') or c.get('manual_uid'):
                if texto in c['titulo'].casefold():vs.append(dict(origem='LOCAL',chave=c.get('manual_uid') or c['local_uid'],natureza='MANUAL',dados=dict(exibicao=c['titulo'])))
            if len(vs)>=300:break
        self.adicionar(vs[:300]);self.filtrar()
        if len(vs)>=300:QMessageBox.information(self,'Resultados limitados','Mostrados até 300 candidatos. Refine a busca para localizar outros elementos.')

    def salvar(self):
        try:
            vs=[v for n,v in enumerate(self.vinculos) if self.tabela.item(n,0).checkState()==Qt.Checked]
            d=dict(titulo=self.titulo.text(),classificacao=self.classificacao.text(),observacoes=self.obs.toPlainText(),x=self.x.value(),y=self.y.value(),crs=self.crs.text())
            if self.registro and any(d[k]!=self.registro['dados'][k] for k in ('x','y','crs')) and self.registro['vinculos']:
                if QMessageBox.question(self,'Posição alterada','Os vínculos existentes serão preservados como associações manuais. Você conferiu os elementos selecionados?',QMessageBox.Yes|QMessageBox.Cancel)!=QMessageBox.Yes:return
            uid,h=storage.salvar(self.painel.base,self.painel.pacote,'LOCAL_MANUAL',d,vs,
                uid=self.registro['obj_uid'] if self.registro else None,esperada=self.registro['uid'] if self.registro else None,modo=self.painel.modo.currentData())
            self.painel.recarregar_manuais(uid);self.accept()
        except Exception as e:QMessageBox.warning(self,'Local não salvo',str(e)+'\nSeus campos foram preservados.')


def selecionados(painel):
    """Somente camadas com contexto e identidade comprováveis, nunca pelo nome."""
    vs=[];el=painel.pacote['topologia']['modelo']['elementos'];topo=painel.pacote['resultado']['meta']['topologia']['execucao_uid']
    for v,g,cid,fid in manuais.redes_gis(painel.pacote,painel.legado.projeto):
        if fid in painel.legado.projeto.mapLayer(cid).selectedFeatureIds():vs.append(v)
    from auditoria_fronteiras.entradas import digest,valor_python
    fontes={f['origem']:f for f in painel.pacote['dossie']['contexto']['fontes']}
    for origem,fonte in fontes.items():
        camadas=[c for c in painel.legado.projeto.mapLayers().values() if c.isValid() and hasattr(c,'geometryType') and c.geometryType()==2 and c.source()==fonte.get('fonte') and c.providerType()==fonte.get('provedor')]
        if len(camadas)!=1 or not camadas[0].selectedFeatureIds():continue
        camada=camadas[0];contagem={};selecoes=[]
        for f in camada.getFeatures():
            attrs={c.name():valor_python(f[c.name()]) for c in camada.fields()};chave=digest([origem,attrs,bytes(f.geometry().asWkb()).hex()]);contagem[chave]=contagem.get(chave,0)+1
            if f.id() in camada.selectedFeatureIds():selecoes.append((chave,attrs))
        for chave,attrs in selecoes:
            if contagem[chave]!=1:continue
            areas=[(u,a) for u,a in painel.indice_atributos.areas.items() if a['origem']==origem and a['chave'].rsplit('_',1)[0]==chave]
            if len(areas)==1:
                u,a=areas[0];vs.append(dict(origem='AREA',chave=u,natureza='MANUAL',dados=dict(exibicao=a.get('exibicao'),camada=a['camada'],origem=origem)))
    for camada in painel.legado.projeto.mapLayers().values():
        if (camada.customProperty('wna/uid')!=topo and camada.customProperty('wna/topo_uid')!=topo) or 'WG_ID' not in camada.fields().names():continue
        for f in camada.selectedFeatures():
            try:
                i=int(f['WG_ID'])
                if i in el and ('WG_UID' not in camada.fields().names() or f['WG_UID']==el[i]['uid']):vs.append(storage.vinculo_wg(painel.pacote,i))
            except (TypeError,ValueError):pass
    return list({(v['origem'],v['chave']):v for v in vs}.values())


def iniciar_local(painel,editar=False,por_selecao=False):
    if not painel.resolver_formularios():return
    registro=painel.atual.get('manual_registro') if editar and painel.atual else None
    if editar and not registro:QMessageBox.information(painel,'Local manual','Selecione um local de origem MANUAL.');return
    canvas=painel.legado.canvas
    if registro:
        d=registro['dados'];DialogoLocal(painel,{k:d[k] for k in ('x','y','crs')},registro,selecionados(painel)).exec_();return
    if not canvas:QMessageBox.information(painel,'Mapa indisponível','Abra a investigação no QGIS para escolher a posição.');return
    if por_selecao:
        vs=selecionados(painel)
        if not vs:QMessageBox.information(painel,'Selecionar elementos','Selecione feições de fontes identificáveis desta investigação ou base topológica.');return
        gs=[]
        for v in vs:
            if v['origem']=='WG':g=(painel.pacote.get('geometrias') or {}).get(int(v['chave']))
            elif v['origem']=='GIS' and v['dados'].get('geometria_wkb'):
                g=QgsGeometry();g.fromWkb(bytes.fromhex(v['dados']['geometria_wkb']))
            elif v['origem']=='AREA':g=painel.indice_atributos._contexto_geometrico.get(v['chave'])
            else:g=None
            if g is not None and not g.isEmpty():gs.append(g)
        if not gs:QMessageBox.information(painel,'Posição não determinada','Os elementos têm identidade, mas não geometria de referência disponível. Use Adicionar local e clique no mapa.');return
        p=QgsGeometry.collectGeometry(gs).centroid().asPoint();crs=painel.pacote['dossie']['contexto']['parametros']['crs'];DialogoLocal(painel,dict(x=p.x(),y=p.y(),crs=crs),selecionados=vs).exec_();return
    from qgis.gui import QgsMapToolEmitPoint
    anterior=canvas.mapTool()
    class Capturar(QgsMapToolEmitPoint):
        def keyPressEvent(self,event):
            if event.key()==Qt.Key_Escape:
                canvas.setMapTool(anterior) if anterior else canvas.unsetMapTool(self)
                painel._ferramenta_manual=None;painel.aviso.setText('Captura cancelada; nenhum local criado.')
            else:super().keyPressEvent(event)
    ferramenta=Capturar(canvas);painel._ferramenta_manual=(ferramenta,anterior)
    def clicou(p,botao):
        if botao!=Qt.LeftButton:return
        canvas.setMapTool(anterior) if anterior else canvas.unsetMapTool(ferramenta)
        painel._ferramenta_manual=None
        crs=canvas.mapSettings().destinationCrs()
        DialogoLocal(painel,dict(x=p.x(),y=p.y(),crs=crs.authid() or crs.toWkt()),selecionados=selecionados(painel)).exec_()
    ferramenta.canvasClicked.connect(clicou);canvas.setMapTool(ferramenta);painel.aviso.setText('Clique no mapa para criar um local manual. Esc ou outra ferramenta cancela a captura. Nenhum evento será criado.')


class DialogoRedes(QDialog):
    def __init__(self,painel):
        super().__init__(painel);self.painel=painel;self.setWindowTitle('Identificar redes principais · seleção investigativa');self.resize(850,650);self.gerado=None;self.registro=None;self.worker=None
        self.modo=painel.modo.currentData()
        self.vinculos=[];self.baseline=None;v=QVBoxLayout(self);f=QFormLayout();v.addLayout(f)
        self.nome=QLineEdit('Rede principal');self.metodo=QComboBox();self.metodo.addItems(['CADASTRAL','TOPOLOGICO','COMBINADO']);self.combinacao=QComboBox();self.combinacao.addItems(['OU','E'])
        self.pontes=QCheckBox('Tubulações cuja remoção divide conectividade fraca (não mede vazão)');self.pontes.setChecked(True)
        self.origens=QLineEdit();self.destinos=QLineEdit();self.origens.setPlaceholderText('DomainElementIDs de reservatórios/tanques; separados por ;');self.destinos.setPlaceholderText('DomainElementIDs de nós/dispositivos; separados por ;')
        for nome,w in [('Nome personalizável',self.nome),('Método',self.metodo),('Combinar cadastro/topologia',self.combinacao),('Indicador topológico',self.pontes),('Origens de corredores (opcional)',self.origens),('Destinos (opcional)',self.destinos)]:f.addRow(nome,w)
        aviso=QLabel('Perspectiva: '+self.modo+'. Cadastro: utiliza os filtros genéricos ativos no painel, aplicados a cada tubulação. Métricas: grafo completo desta perspectiva, inclusive além do recorte visual. Pontes são estruturais; corredores respeitam as barreiras/direções já interpretadas. Nenhum resultado hidráulico é inferido.');aviso.setWordWrap(True);v.addWidget(aviso)
        linha=QHBoxLayout();v.addLayout(linha)
        for nome,fn in [('Identificar',self.calcular),('Recuperar conjunto',self.recuperar),('Comparar com conjunto',self.comparar),('Acrescentar selecionadas',self.acrescentar),('Destacar selecionadas',self.destacar)]:
            b=QPushButton(nome);b.clicked.connect(lambda checked=False,fn=fn:fn());linha.addWidget(b)
        self.tabela=QTableWidget(0,5);self.tabela.setHorizontalHeaderLabels(['Incluir','DomainElementID','Label','Origem','Critérios']);self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers);v.addWidget(self.tabela,1)
        self.estado=QLabel('Nenhum conjunto calculado. Desmarque linhas para removê-las da seleção final.');self.estado.setWordWrap(True);v.addWidget(self.estado)
        linha=QHBoxLayout();v.addLayout(linha)
        for nome,fn in [('Salvar nova revisão',self.salvar),('Exportar CSV…',self.exportar),('Carregar seleção QGIS',self.camada)]:
            b=QPushButton(nome);b.clicked.connect(lambda checked=False,fn=fn:fn());linha.addWidget(b)
        fechar=QPushButton('Fechar');fechar.clicked.connect(self.close);linha.addWidget(fechar);adaptar_janela(self)
        from auditoria_fronteiras.atividade import sistema
        sistema(painel).vincular(self)

    def preencher(self,vs):
        self.vinculos=vs;self.tabela.setRowCount(len(vs))
        for n,v in enumerate(vs):
            item=QTableWidgetItem();item.setFlags(Qt.ItemIsEnabled|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Checked);self.tabela.setItem(n,0,item)
            for c,t in enumerate((v['chave'],v['dados']['label'],v['natureza'],'; '.join(v['dados'].get('criterios',[]))),1):
                i=QTableWidgetItem(str(t));i.setToolTip(str(t));self.tabela.setItem(n,c,i)
        self.tabela.resizeColumnsToContents();self.estado.setText(str(len(vs))+' tubulações candidatas. A seleção final é editável; não é classificação hidráulica.')

    def escolhidos(self):return [v for n,v in enumerate(self.vinculos) if self.tabela.item(n,0).checkState()==Qt.Checked]

    def calcular(self):
        from .redes_principais import identificar
        from auditoria_fronteiras.atividade import sistema
        def ids(w):return [int(i.strip()) for i in w.text().split(';') if i.strip()]
        try:
            if not self.resolver():return
            metodo=self.metodo.currentText();condicao=self.painel.editor_filtros.configuracao();origens=ids(self.origens);destinos=ids(self.destinos);modo=self.modo;pontes=self.pontes.isChecked();combinacao=self.combinacao.currentText()
            if metodo in ('CADASTRAL','COMBINADO') and not condicao:raise ValueError('Configure filtros por atributos no painel antes de identificar pelo cadastro')
            pacote=self.painel.pacote
            def pronto(r):
                self.gerado=r;self.registro=None
                for e in r['elementos']:e['dados']['criterios']=r['criterios'][e['chave']]
                self.preencher(r['elementos'])
            self.worker=sistema(self.painel).executar_thread('Identificando redes principais',modo,
                lambda cancelar,progresso:identificar(pacote,modo,metodo,condicao,pontes,origens,destinos,combinacao,
                    progresso=lambda etapa,n,total:progresso(0,etapa),cancelado=cancelar),pronto,
                lambda texto:self.estado.setText(texto+' · conjunto anterior preservado'))
        except Exception as e:QMessageBox.warning(self,'Identificação não iniciada',str(e))

    def acrescentar(self):
        try:
            vs=selecionados(self.painel);el=self.painel.pacote['topologia']['modelo']['elementos'];novos={v['chave']:v for v in self.escolhidos()}
            for v in vs:
                if v['origem']=='WG' and el[int(v['chave'])]['familia']=='LINK':novos.setdefault(v['chave'],v)
            self.preencher(list(novos.values()))
        except Exception as e:QMessageBox.warning(self,'Seleção',str(e))

    @acompanhada('Salvando conjunto de redes e histórico')
    def salvar(self):
        try:
            criterios=self.gerado or (self.registro['dados'].get('criterios') if self.registro else {})
            escolhidos=self.escolhidos();algoritmo=set((criterios or {}).get('criterios',{}));finais={v['chave'] for v in escolhidos}
            dados=dict(nome=self.nome.text(),criterios=criterios,edicoes_manuais=dict(incluidos=sorted(finais-algoritmo),removidos=sorted(algoritmo-finais)))
            uid,h=storage.salvar(self.painel.base,self.painel.pacote,'REDE_PRINCIPAL',dados,self.escolhidos(),
                uid=self.registro['obj_uid'] if self.registro else None,esperada=self.registro['uid'] if self.registro else None,modo=self.modo)
            self.registro=next(r for r in storage.atuais(self.painel.base,self.painel.pacote,'REDE_PRINCIPAL') if r['obj_uid']==uid);self.preencher(self.registro['vinculos']);self.baseline=self.assinatura();self.estado.setText('Conjunto salvo; revisão '+h[:8]+'. Histórico anterior preservado.');return True
        except Exception as e:falha(self,e);QMessageBox.warning(self,'Conjunto não salvo',str(e));return False

    def recuperar(self):
        rs=[r for r in storage.atuais(self.painel.base,self.painel.pacote,'REDE_PRINCIPAL') if r['modo']==self.modo]
        from qgis.PyQt.QtWidgets import QInputDialog
        if not rs:self.estado.setText('Nenhum conjunto salvo nesta investigação.');return
        nomes=[r['dados']['nome']+' · '+r['obj_uid'][:8] for r in rs];nome,ok=QInputDialog.getItem(self,'Conjuntos','Escolha o conjunto',nomes,0,False)
        if ok:
            if not self.resolver():return
            self.registro=rs[nomes.index(nome)];self.nome.setText(self.registro['dados']['nome']);self.gerado=None;self.preencher(self.registro['vinculos']);self.baseline=self.assinatura()

    def comparar(self):
        from qgis.PyQt.QtWidgets import QInputDialog
        rs=storage.atuais(self.painel.base,self.painel.pacote,'REDE_PRINCIPAL')
        if not rs:return
        nomes=[r['dados']['nome']+' · '+r['obj_uid'][:8] for r in rs];nome,ok=QInputDialog.getItem(self,'Comparar conjuntos','Comparar seleção atual com',nomes,0,False)
        if ok:
            r=storage.comparar_conjuntos(rs[nomes.index(nome)],dict(vinculos=self.escolhidos(),topo_uid=self.painel.pacote['resultado']['meta']['topologia']['execucao_uid']))
            self.estado.setText(f"Mantidos: {len(r['mantidos'])}; incluídos: {len(r['incluidos'])}; removidos: {len(r['removidos'])}. Mesma versão: {r['mesma_versao']}.")

    def destacar(self):
        self.painel.mapa.limpar()
        for v in self.escolhidos():
            g=(self.painel.pacote.get('geometrias') or {}).get(int(v['chave']))
            if g:self.painel.mapa.adicionar(g,'#1464dc')
        self.estado.setText('Destaques aplicados sem alterar o zoom ou os estilos originais.')

    @acompanhada('Carregando seleção de redes no QGIS')
    def camada(self):
        from .representacoes_manuais import carregar_conjunto
        try:carregar_conjunto(self.painel,self.escolhidos(),self.nome.text(),self.registro)
        except Exception as e:QMessageBox.warning(self,'Seleção QGIS',str(e))

    def exportar(self):
        from .redes_principais import exportar_csv
        if not self.registro:QMessageBox.information(self,'Salvar conjunto','Salve uma revisão do conjunto antes de exportar.');return
        destino,_=QFileDialog.getSaveFileName(self,'Exportar lista de elementos','','CSV (*.csv)')
        if destino:
            try:
                if self.escolhidos()!=self.registro['vinculos']:raise ValueError('Salve as alterações da seleção antes de exportar')
                exportar_csv(destino,self.painel.pacote,self.registro);self.estado.setText('CSV exportado. Não é importação nativa: confira os IDs e crie o Selection Set por consulta/seleção no WaterGEMS.')
            except Exception as e:QMessageBox.warning(self,'Exportação',str(e))

    def closeEvent(self,event):
        from qgis.PyQt import sip
        if self.worker and not sip.isdeleted(self.worker) and self.worker.isRunning():
            QMessageBox.information(self,'Operação em andamento','Aguarde ou cancele pelo painel Atividade antes de fechar.');event.ignore();return
        if not self.resolver():event.ignore();return
        event.accept()

    def assinatura(self):
        from .decisoes import digest
        return digest([self.nome.text(),self.escolhidos()])

    def tem_edicoes(self):return bool(self.vinculos or self.registro) and self.assinatura()!=self.baseline

    def resolver(self):
        if not self.tem_edicoes():return True
        r=QMessageBox.question(self,'Conjunto não salvo','Salvar as alterações do conjunto?',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel)
        if r==QMessageBox.Cancel:return False
        if r==QMessageBox.Save:return self.salvar()
        self.baseline=self.assinatura();return True
