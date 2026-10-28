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
        self.navegar=True
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
            self.painel.recarregar_manuais(uid if self.navegar else None);self.accept()
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
        super().__init__(painel);self.painel=painel;self.setWindowTitle('Corredores alimentadores · caminhos e conjuntos');self.resize(850,650);self.gerado=None;self.registro=None;self.worker=None
        self.modo=painel.modo.currentData()
        self.vinculos=[];self.baseline=None;v=QVBoxLayout(self);f=QFormLayout();v.addLayout(f)
        self.nome=QLineEdit('Corredores alimentadores');self.metodo=QComboBox()
        for label,codigo in [('Corredores alimentadores','CORREDORES'),('Caminho entre pontos','CAMINHO'),('Seleção cadastral','CADASTRAL'),('Pontes topológicas','PONTES'),('Critério combinado · cadastro e corredores','COMBINADO_CORREDORES'),('Conectividade crítica · cortes topológicos','CRITICA')]:self.metodo.addItem(label,codigo)
        self.combinacao=QComboBox();self.combinacao.addItems(['OU','E'])
        self.pontes=QCheckBox('Pontes apenas na análise específica, nunca incluídas automaticamente nos corredores');self.pontes.setChecked(False);self.pontes.hide()
        self.origens=QLineEdit();self.destinos=QLineEdit();self.origens.setPlaceholderText('IDs de terminais; separados por ;');self.destinos.setPlaceholderText('IDs de terminais; separados por ;')
        self.origens.hide();self.destinos.hide()  # API de compatibilidade; seleção principal é tabular/cartográfica.
        self.criterio_caminho=QComboBox();self.criterio_caminho.addItem('Menor número de arestas','ARESTAS');self.criterio_caminho.addItem('Menor comprimento geométrico validado (m)','COMPRIMENTO')
        self.alternativas=QComboBox()
        for n in range(4):self.alternativas.addItem(str(n)+' alternativas por destino',n)
        for nome,w in [('Nome personalizável',self.nome),('Método',self.metodo),('Combinar cadastro/corredores',self.combinacao),('Critério do caminho',self.criterio_caminho),('Comparar alternativas',self.alternativas)]:f.addRow(nome,w)
        self._form_metodo=f
        from .terminais_ui import SeletorTerminais
        self.origem_ui=SeletorTerminais(self,'Origens · pontos iniciais escolhidos','#009050');self.destino_ui=SeletorTerminais(self,'Destinos','#d52f3f');v.addWidget(self.origem_ui);v.addWidget(self.destino_ui)
        self.regioes_botao=QPushButton('Adicionar destinos dos polígonos selecionados no QGIS');self.regioes_botao.clicked.connect(self.destino_ui.adicionar_regioes);v.addWidget(self.regioes_botao)
        self.orientacao=QLabel();self.orientacao.setWordWrap(True);v.addWidget(self.orientacao)
        linha=QHBoxLayout();v.addLayout(linha)
        for nome,fn in [('Identificar',self.calcular),('Recuperar conjunto',self.recuperar),('Comparar com conjunto',self.comparar),('Acrescentar selecionadas',self.acrescentar),('Destacar selecionadas',self.destacar)]:
            b=QPushButton(nome);b.clicked.connect(lambda checked=False,fn=fn:fn());linha.addWidget(b)
        self.tabela=QTableWidget(0,5);self.tabela.setHorizontalHeaderLabels(['Incluir','DomainElementID','Label','Origem','Critérios']);self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers);v.addWidget(self.tabela,1)
        self.tabela.setColumnCount(12);self.tabela.setHorizontalHeaderLabels(['Incluir','DomainElementID','Label','Origem','Critérios','Rotas escolhidas','Destinos','Classe no conjunto','Comprimento (m)','Diâmetro bruto','Unidade diâmetro','Dispositivos'])
        self.rotas_tabela=QTableWidget(0,5);self.rotas_tabela.setHorizontalHeaderLabels(['Rota','Origem → destino','Custo','Comprimento (m)','Tubos / dispositivos']);self.rotas_tabela.setEditTriggers(QAbstractItemView.NoEditTriggers);self.rotas_tabela.setMaximumHeight(130);v.addWidget(self.rotas_tabela)
        alternativa_botao=QPushButton('Acrescentar à seleção a alternativa escolhida');alternativa_botao.clicked.connect(self.adicionar_alternativa);v.addWidget(alternativa_botao);self.alternativa_botao=alternativa_botao
        local=QPushButton('Criar local manual no destino inalcançável escolhido');local.clicked.connect(self.local_interrupcao);v.addWidget(local);self.local_interrupcao_botao=local
        self.estado=QLabel('Nenhum conjunto calculado. Desmarque linhas para removê-las da seleção final.');self.estado.setWordWrap(True);v.addWidget(self.estado)
        linha=QHBoxLayout();v.addLayout(linha)
        for nome,fn in [('Salvar nova revisão',self.salvar),('Exportar CSV…',self.exportar),('Exportar para WaterGEMS…',self.exportar_completo),('Carregar seleção QGIS',self.camada)]:
            b=QPushButton(nome);b.clicked.connect(lambda checked=False,fn=fn:fn());linha.addWidget(b)
        fechar=QPushButton('Fechar');fechar.clicked.connect(self.close);linha.addWidget(fechar);adaptar_janela(self)
        self.metodo.currentIndexChanged.connect(self.metodo_alterado);self.metodo_alterado()
        from auditoria_fronteiras.atividade import sistema
        sistema(painel).vincular(self)

    def preencher(self,vs):
        self.vinculos=vs;self.tabela.setRowCount(len(vs))
        for n,v in enumerate(vs):
            item=QTableWidgetItem();item.setFlags(Qt.ItemIsEnabled|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Checked);self.tabela.setItem(n,0,item)
            for c,t in enumerate((v['chave'],v['dados']['label'],v['natureza'],'; '.join(v['dados'].get('criterios',[]))),1):
                i=QTableWidgetItem(str(t));i.setToolTip(str(t));self.tabela.setItem(n,c,i)
            m=v['dados'].get('metricas',{})
            for c,k in enumerate(('rotas','destinos','classe','comprimento_m','diametro_bruto','unidade_diametro','dispositivos'),5):
                valor=m.get(k);texto='; '.join(map(str,valor)) if isinstance(valor,list) else '' if valor is None else str(valor);i=QTableWidgetItem(texto);i.setToolTip(texto);self.tabela.setItem(n,c,i)
        self.tabela.resizeColumnsToContents();self.estado.setText(str(len(vs))+' tubulações candidatas. A seleção final é editável; não é classificação hidráulica.')

    def escolhidos(self):return [v for n,v in enumerate(self.vinculos) if self.tabela.item(n,0).checkState()==Qt.Checked]

    def calcular(self):
        from .redes_principais import identificar
        from auditoria_fronteiras.atividade import sistema
        def ids(w):return [int(i.strip()) for i in w.text().split(';') if i.strip()]
        try:
            if not self.resolver():return
            metodo=self.metodo.currentData();condicao=self.painel.editor_filtros.configuracao();origens=ids(self.origens) or self.origem_ui.valores();destinos=ids(self.destinos) or self.destino_ui.valores();modo=self.modo;combinacao=self.combinacao.currentText();criterio=self.criterio_caminho.currentData();alternativas=self.alternativas.currentData()
            if metodo=='LEGADO':raise ValueError('Conjunto da versão anterior: escolha explicitamente o novo método antes de recalcular. Os critérios históricos foram preservados.')
            if metodo in ('CADASTRAL','COMBINADO_CORREDORES') and not condicao:raise ValueError('Configure filtros por atributos no painel antes de identificar pelo cadastro')
            if metodo in ('CORREDORES','CAMINHO','COMBINADO_CORREDORES') and (not origens or not destinos):raise ValueError('Escolha origens e destinos por busca, seleção ou mapa. Junctions são permitidas. Nenhuma ponte será selecionada automaticamente.')
            pacote=self.painel.pacote
            from .corredores import calcular,comprimentos_metricos
            comprimentos=comprimentos_metricos(pacote)
            assinatura_calculo=self.parametros_assinatura()
            def trabalho(cancelar,progresso):
                cb=lambda etapa,n,total:progresso(0,etapa)
                if metodo in ('CORREDORES','CAMINHO','COMBINADO_CORREDORES'):
                    r=calcular(pacote,modo,origens,destinos,criterio,alternativas,'CAMINHO' if metodo=='CAMINHO' else 'CORREDORES',comprimentos,cb,cancelar)
                    if metodo=='COMBINADO_CORREDORES':
                        cadastro=identificar(pacote,modo,'CADASTRAL',condicao,progresso=cb,cancelado=cancelar);a={v['chave']:v for v in r['elementos']};b={v['chave']:v for v in cadastro['elementos']};chaves=set(a)&set(b) if combinacao=='E' else set(a)|set(b)
                        r['elementos']=[a.get(i,b.get(i)) for i in sorted(chaves)];r['criterios']={i:r['criterios'].get(i,[])+cadastro['criterios'].get(i,[]) for i in chaves};r['metodo']='COMBINADO_CORREDORES';r['combinacao']=combinacao;r['condicao']=condicao;r['aviso_continuidade']='A seleção combinada pode remover conectores ou incluir tubos cadastrais fora das rotas. Componentes das rotas não representam necessariamente a seleção editada.'
                    return r
                r=identificar(pacote,modo,'CADASTRAL' if metodo=='CADASTRAL' else 'TOPOLOGICO',condicao,progresso=cb,cancelado=cancelar);r['metodo']=metodo;return r
            def pronto(r):
                self.gerado=r;self.registro=None;self._parametros_calculados=assinatura_calculo
                for e in r['elementos']:e['dados']['criterios']=r['criterios'][e['chave']]
                r['regioes_destinos']=getattr(self,'_regioes_destinos',[]);self.preencher(r['elementos']);self.apresentar_rotas();self.destacar()
            self.worker=sistema(self.painel).executar_thread('Identificando redes principais',modo,
                trabalho,pronto,
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
            if self.gerado and getattr(self,'_parametros_calculados',None)!=self.parametros_assinatura():raise ValueError('Origens, destinos ou parâmetros foram alterados. Recalcule antes de salvar; o conjunto anterior foi preservado.')
            criterios=self.gerado or (self.registro['dados'].get('criterios') if self.registro else {})
            estruturados=criterios if isinstance(criterios,dict) else {}
            escolhidos=self.escolhidos();algoritmo=set(estruturados.get('criterios',{}));finais={v['chave'] for v in escolhidos}
            if estruturados.get('metodo') in ('CORREDORES','CAMINHO','COMBINADO_CORREDORES'):
                from .corredores import resumir_selecao
                criterios=dict(criterios,continuidade_selecao=resumir_selecao(self.painel.pacote,self.modo,[int(v['chave']) for v in escolhidos],criterios.get('origens',[]),criterios.get('destinos',[])))
            dados=dict(nome=self.nome.text(),criterios=criterios,edicoes_manuais=dict(incluidos=sorted(finais-algoritmo),removidos=sorted(algoritmo-finais)))
            uid,h=storage.salvar(self.painel.base,self.painel.pacote,'REDE_PRINCIPAL',dados,self.escolhidos(),
                uid=self.registro['obj_uid'] if self.registro else None,esperada=self.registro['uid'] if self.registro else None,modo=self.modo)
            self.registro=next(r for r in storage.atuais(self.painel.base,self.painel.pacote,'REDE_PRINCIPAL') if r['obj_uid']==uid);self.preencher(self.registro['vinculos']);self.baseline=self.assinatura();self.estado.setText('Conjunto salvo; revisão '+h[:8]+'. Histórico anterior preservado.');self.painel.atualizar_recuperacao();return True
        except Exception as e:falha(self,e);QMessageBox.warning(self,'Conjunto não salvo',str(e));return False

    def recuperar(self):
        rs=storage.atuais(self.painel.base,self.painel.pacote,'REDE_PRINCIPAL')
        from qgis.PyQt.QtWidgets import QInputDialog
        if not rs:self.estado.setText('Nenhum conjunto salvo nesta investigação.');return
        nomes=[r['dados']['nome']+' · '+r['modo']+' · '+r['obj_uid'][:8] for r in rs];nome,ok=QInputDialog.getItem(self,'Conjuntos','Escolha o conjunto e sua perspectiva',nomes,0,False)
        if ok:
            if not self.resolver():return
            self.registro=rs[nomes.index(nome)];self.nome.setText(self.registro['dados']['nome']);self.gerado=None
            self.origem_ui.fechar_captura();self.destino_ui.fechar_captura();self.modo=self.registro['modo']
            if hasattr(self,'_catalogo_terminais'):del self._catalogo_terminais
            self.restaurar_parametros(self.registro['dados'].get('criterios') or {});self.preencher(self.registro['vinculos']);self.apresentar_rotas();self.baseline=self.assinatura()
            self.metodo_alterado();self.setWindowTitle('Corredores e conjuntos · '+self.modo)

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
        criterios=self.criterios_estruturados();metricas=criterios.get('metricas',{})
        for rota in criterios.get('rotas_alternativas',[]):
            for i in rota['tubulacoes']:
                g=(self.painel.pacote.get('geometrias') or {}).get(i)
                if g:self.painel.mapa.adicionar(g,'#a34bb8',True)
        for v in self.escolhidos():
            g=(self.painel.pacote.get('geometrias') or {}).get(int(v['chave']))
            if g:self.painel.mapa.adicionar(g,'#1464dc' if metricas.get(v['chave'],{}).get('compartilhado') else '#e58a13')
        for i in {i for rota in criterios.get('rotas',[]) for i in rota['dispositivos']}:
            g=(self.painel.pacote.get('geometrias') or {}).get(i)
            if g:self.painel.mapa.adicionar(g,'#b817c8')
        self.destacar_terminais(limpar=False)
        self.estado.setText(self.estado.text()+'\nAzul: compartilhado; laranja: ramo/rota; magenta tracejado: alternativa e ponto magenta: dispositivo; verde: origem; vermelho: destino; cinza: inalcançável. Zoom explícito.')

    @acompanhada('Carregando seleção de redes no QGIS')
    def camada(self):
        from .representacoes_manuais import carregar_conjunto
        try:carregar_conjunto(self.painel,self.escolhidos(),self.nome.text(),self.registro)
        except Exception as e:QMessageBox.warning(self,'Seleção QGIS',str(e))

    def exportar_completo(self):
        if not self.registro or self.tem_edicoes():QMessageBox.information(self,'Salvar conjunto','Salve a revisão atual antes de exportar.');return
        try:
            from .exportacao_watergems_ui import ExportarWatergems
            from qgis.PyQt import sip
            if getattr(self,'_exportacao',None) is None or sip.isdeleted(self._exportacao):self._exportacao=ExportarWatergems(self)
            if getattr(self.painel,'_wna_janelas',None):self.painel._wna_janelas.registrar('exportacao_watergems',self._exportacao,'exportação WaterGEMS')
            self._exportacao.show();self._exportacao.raise_()
        except Exception as e:QMessageBox.warning(self,'Exportação indisponível',str(e))

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
        self.origem_ui.fechar_captura();self.destino_ui.fechar_captura()
        event.accept()

    def metodo_alterado(self):
        m=self.metodo.currentData();rotas=m in ('CORREDORES','CAMINHO','COMBINADO_CORREDORES')
        for w in (self.origem_ui,self.destino_ui,self.regioes_botao,self.criterio_caminho,self.alternativas):w.setVisible(rotas)
        self.combinacao.setVisible(m=='COMBINADO_CORREDORES')
        for w in (self.criterio_caminho,self.alternativas,self.combinacao):self._form_metodo.labelForField(w).setVisible(w.isVisibleTo(self))
        self.orientacao.setText('Perspectiva: '+self.modo+'. '+('Escolha origens e destinos (Junctions permitidas). Origem não implica fonte real. Corredores são união das rotas escolhidas, sem pontes periféricas automáticas.' if rotas else 'Cadastro usa os filtros ativos. Pontes/cortes são propriedades estruturais globais, não corredores alimentadores nem criticidade hidráulica.'))

    def restaurar_parametros(self,r):
        r=r if isinstance(r,dict) else {}
        m=r.get('metodo');idx=self.metodo.findData(m)
        if idx<0:
            if self.metodo.findData('LEGADO')<0:self.metodo.addItem('Conjunto legado · consultar critérios históricos','LEGADO')
            idx=self.metodo.findData('LEGADO')
        self.metodo.setCurrentIndex(idx);self.criterio_caminho.setCurrentIndex(max(0,self.criterio_caminho.findData(r.get('criterio_caminho','ARESTAS'))));self.origem_ui.limpar();self.destino_ui.limpar()
        self.alternativas.setCurrentIndex(max(0,self.alternativas.findData(r.get('alternativas_solicitadas',0))));self.combinacao.setCurrentText(r.get('combinacao','OU'));self._regioes_destinos=r.get('regioes_destinos',[])
        for seletor,chave in ((self.origem_ui,'origens'),(self.destino_ui,'destinos')):
            for t in r.get(chave,[]):
                i=t['id'] if isinstance(t,dict) else t[0] if isinstance(t,(tuple,list)) else t;porta=t.get('porta') if isinstance(t,dict) else t[1] if isinstance(t,(tuple,list)) else None
                rows=[v for v in seletor.catalogo()[1].get(i,[]) if porta is None or v['porta']==porta]
                if len(rows)==1:seletor.adicionar(rows)
                else:seletor.adicionar([dict(id=i,porta=porta,label='Terminal a conferir')])

    def parametros_assinatura(self):
        from .decisoes import digest
        return digest([self.metodo.currentData(),self.origem_ui.valores(),self.destino_ui.valores(),self.origens.text(),self.destinos.text(),self.criterio_caminho.currentData(),self.alternativas.currentData(),self.combinacao.currentText(),self.painel.editor_filtros.configuracao() if self.metodo.currentData() in ('CADASTRAL','COMBINADO_CORREDORES') else None])

    def apresentar_rotas(self):
        r=self.criterios_estruturados();rotas=r.get('rotas',[])+r.get('rotas_alternativas',[]);falhas=r.get('destinos_inalcancaveis',[]);self.rotas_tabela.setRowCount(len(rotas)+len(falhas))
        for n,t in enumerate(rotas):
            for c,v in enumerate((t['uid']+(' alternativa' if t['alternativa'] else ''),str(t['origem'])+' → '+str(t['destino']),t['custo'],t['comprimento_m'],str(len(t['tubulacoes']))+' / '+str(len(t['dispositivos'])))):self.rotas_tabela.setItem(n,c,QTableWidgetItem(str(v)))
            self.rotas_tabela.item(n,0).setData(Qt.UserRole,t)
        for n,t in enumerate(falhas,len(rotas)):
            for c,v in enumerate(('INALCANÇÁVEL',str(t['destino']),'—','—',t['motivo'])):
                item=QTableWidgetItem(v);item.setData(Qt.UserRole,t);item.setToolTip(str(t));self.rotas_tabela.setItem(n,c,item)
        self.rotas_tabela.resizeColumnsToContents()
        if rotas or r.get('destinos_inalcancaveis'):
            self.estado.setText(f"{len(self.escolhidos())} tubos · {len(r.get('componentes_selecionados',[]))} componentes das rotas · {len(r.get('destinos_alcancados',[]))} destinos alcançados · {len(r.get('destinos_inalcancaveis',[]))} inalcançáveis. Múltiplas origens podem pertencer a sistemas separados.")
            self.estado.setToolTip(r.get('limitacoes','')+'\n'+str(r.get('destinos_inalcancaveis',[])))
        self.local_interrupcao_botao.setVisible(bool(falhas))
        self.alternativa_botao.setVisible(bool(r.get('rotas_alternativas')))

    def adicionar_alternativa(self):
        n=self.rotas_tabela.currentRow()
        if n<0:return
        r=self.rotas_tabela.item(n,0).data(Qt.UserRole)
        if not r or not r.get('alternativa'):QMessageBox.information(self,'Alternativa','Selecione uma rota alternativa na tabela.');return
        novos={v['chave']:v for v in self.escolhidos()}
        for i in r['tubulacoes']:
            v=storage.vinculo_wg(self.painel.pacote,i);v['dados']['criterios']=['Inclusão manual a partir da alternativa '+r['uid']];novos.setdefault(str(i),v)
        self.preencher(list(novos.values()));self.estado.setText('Alternativa acrescentada por escolha explícita. Salve uma revisão; métricas originais continuam referentes às rotas principais calculadas.')

    def local_interrupcao(self):
        n=self.rotas_tabela.currentRow()
        if n<0:return
        t=self.rotas_tabela.item(n,0).data(Qt.UserRole)
        if not t:QMessageBox.information(self,'Interrupção','Selecione uma linha INALCANÇÁVEL; não será inventado um ponto de ruptura.');return
        d=t['destino'];i=d['id'] if isinstance(d,dict) else d[0] if isinstance(d,(tuple,list)) else d;g=(self.painel.pacote.get('geometrias') or {}).get(i)
        if g is None:QMessageBox.information(self,'Geometria indisponível','Crie um local pelo mapa; não há geometria validada para este destino.');return
        p=g.centroid().asPoint();dialogo=DialogoLocal(self.painel,dict(x=p.x(),y=p.y(),crs=self.painel.pacote['dossie']['contexto']['parametros']['crs']))
        dialogo.navegar=False;dialogo.titulo.setText('Investigar destino sem caminho cadastrado');dialogo.obs.setPlainText(t['motivo']);dialogo.exec_()

    def destacar_terminais(self,limpar=True):
        if limpar:self.painel.mapa.limpar()
        r=self.criterios_estruturados()
        for termos,cor in [(r.get('origens') or self.origem_ui.valores(),'#009050'),(r.get('destinos') or self.destino_ui.valores(),'#d52f3f')]:
            for t in termos:
                i=t['id'] if isinstance(t,dict) else t[0];g=(self.painel.pacote.get('geometrias') or {}).get(i)
                if g:self.painel.mapa.adicionar(g,cor)
        for t in r.get('destinos_inalcancaveis',[]):
            d=t['destino'];i=d['id'] if isinstance(d,dict) else d[0] if isinstance(d,(list,tuple)) else d;g=(self.painel.pacote.get('geometrias') or {}).get(i)
            if g:self.painel.mapa.adicionar(g,'#777777')

    def criterios_estruturados(self):
        valor=self.gerado or (self.registro['dados'].get('criterios') if self.registro else {})
        return valor if isinstance(valor,dict) else {}

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
