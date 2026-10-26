"""Inspeção expansível, navegação explícita e revisão persistente no QGIS."""
from pathlib import Path
from qgis.PyQt import sip
from qgis.PyQt.QtCore import Qt,pyqtSignal
from qgis.PyQt.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QComboBox,QLabel,
    QTreeWidget,QTreeWidgetItem,QPushButton,QPlainTextEdit,QLineEdit,QFormLayout,
    QFileDialog,QMessageBox,QSplitter,QWidget,QCheckBox,QTabWidget)
from qgis.core import QgsVectorLayer,QgsGeometry,QgsCoordinateTransform
from .inspecao import detalhes_local,contagens
from .apresentacao import legivel
from .entradas import digest,valor_python
from .persistencia import salvar_execucao,salvar_revisao,historico,SITUACOES


def localizar_tubulacoes(dossie,tubos,projeto):
    """FID serve só à seleção atual; correspondência por fonte + assinatura bruta."""
    fontes={f['origem']:f for f in dossie['contexto']['fontes']}
    encontrados={}
    avisos=[]
    por_origem={}
    for tubo in tubos:
        por_origem.setdefault(tubo['origem'],[]).append(tubo)
    for origem,refs in por_origem.items():
        fonte=fontes.get(origem,{})
        camadas=[c for c in projeto.mapLayers().values() if isinstance(c,QgsVectorLayer)
            and c.isValid() and c.providerType()==fonte.get('provedor') and c.source()==fonte.get('fonte')]
        if len(camadas)!=1:
            avisos.append(f"{fonte.get('camada',origem)}: " +
                ('origem ausente' if not camadas else 'múltiplas camadas correspondentes; nenhuma escolhida'))
            continue
        camada=camadas[0]
        procuradas={t['uid'].rsplit('_',1)[0]:t for t in refs}
        assinaturas={k:[] for k in procuradas}
        for f in camada.getFeatures():
            attrs={c.name():valor_python(f[c.name()]) for c in camada.fields()}
            chave=digest([origem,attrs,bytes(f.geometry().asWkb()).hex()])
            if chave in assinaturas:
                assinaturas[chave].append(f.id())
        selecionados=[]
        for chave,tubo in procuradas.items():
            candidatos=assinaturas[chave]
            if len(candidatos)==1:
                selecionados.extend(candidatos)
            else:
                avisos.append(f"{tubo['id_exibido']} / {tubo['camada']}: "+
                    ('feição alterada ou ausente' if not candidatos else 'cópias idênticas ambíguas; nenhuma escolhida'))
        encontrados[camada.id()]=selecionados
    return encontrados,avisos


def aplicar_revisoes(camadas,dossie):
    mapa={l['uid']:l['revisao']['situacao'] for l in dossie['locais']}
    for c in camadas:
        if sip.isdeleted(c):
            continue
        if c.customProperty('auditoria_fronteiras/papel')=='locais':
            indice=c.fields().indexFromName('SITUACAO')
            c.dataProvider().changeAttributeValues({f.id():{indice:mapa[f['LOC_UID']]}
                for f in c.getFeatures() if f['LOC_UID'] in mapa})
            c.triggerRepaint()


class PainelInspecao(QDialog):
    revisao_salva=pyqtSignal(str)
    def __init__(self,dossie,camadas,projeto,parent=None,canvas=None,base=None):
        super().__init__(parent)
        self.setWindowTitle('Inspeção dos locais — auditoria espacial')
        self.resize(960,680)
        self.dossie=dossie
        self.camadas=camadas
        self.projeto=projeto
        self.canvas=canvas
        self.base=base
        self._ativo=True
        self._sincronizando=False
        self._local_carregado=None
        self._form_baseline=None
        raiz=QVBoxLayout(self)
        self.locais=QComboBox()
        self.locais.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.locais.setMinimumContentsLength(30)
        self.locais.addItem('Selecione um local',None)
        for l in dossie['locais']:
            self.locais.addItem(f"{l['registro']['LOCAL']} — {l['registro']['N_EVENTOS']} eventos — {l['registro']['AREAS']}",l['uid'])
        raiz.addWidget(self.locais)
        self.gerais=QLabel()
        self.gerais.setWordWrap(True)
        raiz.addWidget(self.gerais)
        self.arvore=QTreeWidget()
        self.arvore.setHeaderLabels(['Elemento','Identificação','Camada / origem','Informações','Chave técnica'])
        self.arvore.setColumnWidth(0,110)
        self.arvore.setColumnWidth(1,140)
        self.arvore.setColumnWidth(2,180)
        self.arvore.setColumnWidth(3,320)
        from .tabelas_consulta import TabelaConsulta
        self.dados_tabs=QTabWidget();raiz.addWidget(self.dados_tabs,1)
        self.tubulacoes_tabela=TabelaConsulta(['Tipo','ID GIS','Camada','Setor cadastral','Regiões geométricas','Diâmetro','Material','Chave técnica'])
        self.eventos_tabela=TabelaConsulta(['ID','Classificação','Limite','Área','Região antes','Região depois','Ambiguidade','X','Y','Chave técnica'])
        self.dados_tabs.addTab(self.tubulacoes_tabela,'Tubulações');self.dados_tabs.addTab(self.eventos_tabela,'Eventos');self.dados_tabs.addTab(self.arvore,'Detalhes completos')
        self.tubulacoes_tabela.tabela.setColumnHidden(7,True);self.eventos_tabela.tabela.setColumnHidden(9,True)
        botoes=QHBoxLayout()
        for texto,funcao in [('Destacar local e eventos',self.destacar),
                ('Selecionar tubulações originais',self.selecionar_origens),('Aproximar mapa',self.aproximar)]:
            b=QPushButton(texto)
            b.clicked.connect(funcao)
            botoes.addWidget(b)
        raiz.addLayout(botoes)
        self.situacao=QComboBox()
        self.situacao.addItems(SITUACOES)
        self.observacoes=QPlainTextEdit()
        self.observacoes.setMaximumHeight(70)
        self.responsavel=QLineEdit()
        form=QFormLayout()
        form.addRow('Situação:',self.situacao)
        form.addRow('Responsável (opcional):',self.responsavel)
        form.addRow('Observações:',self.observacoes)
        raiz.addLayout(form)
        self.confirmar_reconciliacao=QCheckBox('Correspondências parciais avaliadas nesta revisão')
        raiz.addWidget(self.confirmar_reconciliacao)
        botoes=QHBoxLayout()
        self.salvar=QPushButton('Salvar revisão…')
        self.salvar.clicked.connect(self.gravar_revisao)
        botoes.addWidget(self.salvar)
        self.ver_historico=QPushButton('Consultar histórico')
        self.ver_historico.clicked.connect(self.mostrar_historico)
        botoes.addWidget(self.ver_historico)
        raiz.addLayout(botoes)
        self.aviso=QLabel('Os status descrevem a revisão. Não confirmam operação hidráulica.')
        self.aviso.setWordWrap(True)
        raiz.addWidget(self.aviso)
        self.locais.currentIndexChanged.connect(self.atualizar)
        self.arvore.itemSelectionChanged.connect(self.selecionar_evento)
        self.camada_locais=next((c for c in camadas if c.customProperty('auditoria_fronteiras/papel')=='locais'),None)
        if self.camada_locais is not None:
            self.camada_locais.selectionChanged.connect(self.selecao_inversa)
        self.atualizar()
        from auditoria_fronteiras.ui_comum import adaptar_janela
        adaptar_janela(self)

    def atualizar(self):
        uid=self.locais.currentData()
        if self._local_carregado and uid!=self._local_carregado and self.tem_edicoes():
            indice_novo=self.locais.currentIndex()
            self.locais.blockSignals(True)
            self.locais.setCurrentIndex(self.locais.findData(self._local_carregado))
            self.locais.blockSignals(False)
            if not self.resolver_edicoes():
                return
            self.locais.blockSignals(True)
            self.locais.setCurrentIndex(indice_novo)
            self.locais.blockSignals(False)
        self.arvore.clear()
        self.salvar.setEnabled(bool(uid))
        for w in (self.situacao,self.observacoes,self.responsavel):
            w.setEnabled(bool(uid))
        if not uid:
            self.tubulacoes_tabela.preencher([]);self.eventos_tabela.preencher([])
            self.confirmar_reconciliacao.setEnabled(False)
            self._local_carregado=None
            self._form_baseline=None
            self.gerais.setText('Selecione um local para consultar seus elementos.')
            return
        d=detalhes_local(self.dossie,uid)
        self.tubulacoes_tabela.preencher([['Tubulação',t['id_exibido'],t['camada'],t['extras'].get('setor'),'; '.join(legivel(p.get('nome') or p.get('id_original')) for p in t['regioes_geometricas']),t['extras'].get('diametro'),t['extras'].get('material'),t['uid']] for t in d['tubulacoes']])
        self.eventos_tabela.preencher([[e['registro'].get(k) for k in ('ID','CLASSIF','TIPO_LIM','AREA','REG_ANTES','REG_DEPOIS','AMBIGUO','X','Y')]+[e['uid']] for e in d['eventos']])
        l=d['local']
        r=l['registro']
        revisao=l['revisao']
        self._revisao_carregada=revisao.get('uid')
        self.situacao.setCurrentText(revisao['situacao'])
        self.observacoes.setPlainText(revisao['observacoes'])
        self.responsavel.setText(revisao['responsavel'])
        self._local_carregado=uid
        self.gerais.setText(f"{r['LOCAL']} | {r['N_EVENTOS']} eventos | {r['N_TUBOS']} tubulações | "
            f"{r['CLASSIF']} | {r['TIPOS_LIM']} | {r['AREAS']} | Ambiguidade: {r['AMBIGUO']} | "
            f"{revisao['situacao']} | X {r['X']:.3f} Y {r['Y']:.3f}")
        grupos={n:QTreeWidgetItem(self.arvore,[n]) for n in ('Tubulações','Eventos','Áreas e limites','Ambiguidades')}
        for t in d['tubulacoes']:
            ex=t['extras']
            reg='; '.join(legivel(p.get('nome') or p.get('id_original')) for p in t['regioes_geometricas'])
            info=(f"Setor cadastral: {legivel(ex.get('setor'),'Não informado')} | "
                  f"Diâmetro: {legivel(ex.get('diametro'),'Não informado')} | Material: {legivel(ex.get('material'),'Não informado')} | "
                  f"Regiões geométricas nas fronteiras: {reg or 'Não disponível'}")
            QTreeWidgetItem(grupos['Tubulações'],['Tubulação',t['id_exibido'],t['camada'],info,t['uid']])
        fontes={f['origem']:f for f in self.dossie['contexto']['fontes']}
        for e in d['eventos']:
            r=e['registro']
            item=QTreeWidgetItem(grupos['Eventos'],['Evento',str(r['ID']),r['TIPO_LIM'],
                f"{r['CLASSIF']} | {r['AREA']} | Tubos: {r['ID_REDE']} | Ambiguidade: {r['AMBIGUO']}",e['uid']])
            item.setData(0,Qt.UserRole,('evento',e['uid']))
            if e['uid'] in l['eventos_ambiguos']:
                motivos=e['tecnico'].get('observacoes',[])
                QTreeWidgetItem(grupos['Ambiguidades'],['Evento',str(r['ID']),r['CLASSIF'],
                    '; '.join(map(str,motivos)) or 'Indicador geral; consulte candidatos e identificação das áreas',e['uid']])
        for p in d['poligonos']:
            fonte=fontes.get(p['origem'],{})
            rel=[e for e in d['eventos'] if any(v['evento_uid']==e['uid'] and v['pol_uid']==p['chave']
                 for v in self.dossie['evento_poligono'])]
            trans='; '.join(dict.fromkeys(f"{e['registro']['REG_ANTES']} → {e['registro']['REG_DEPOIS']}"
                for e in rel if e['tecnico']['modo']=='TRANSICAO'))
            QTreeWidgetItem(grupos['Áreas e limites'],['Polígono',legivel(p.get('id_original')),p['camada'],
                f"Modo: {fonte.get('modo','')} | Campo ID: {fonte.get('campo_id')} | Exibição: {fonte.get('campo_nome')} | {trans}",p['chave']])
        if not l['eventos_ambiguos']:
            QTreeWidgetItem(grupos['Ambiguidades'],['Sem eventos ambíguos'])
        for grupo in grupos.values():
            for n in range(grupo.childCount()):
                item=grupo.child(n)
                for coluna in range(5):
                    item.setToolTip(coluna,item.text(coluna))
        pendentes=[r for r in self.dossie['reconciliacoes'] if r['local_uid']==uid and r['tipo']=='PARCIAL' and r['decisao']=='PENDENTE']
        self.confirmar_reconciliacao.setChecked(False)
        self.confirmar_reconciliacao.setEnabled(bool(pendentes))
        self._form_baseline=self.valores_formulario()
        self.aviso.setText(f'{len(pendentes)} correspondências parciais pendentes de reconciliação. A decisão anterior não foi transferida.'
            if pendentes else 'Os status descrevem a revisão, sem confirmar operação hidráulica.')
        if not self._sincronizando:
            self.destacar()

    def valores_formulario(self):
        return (self.situacao.currentText(),self.observacoes.toPlainText(),self.responsavel.text(),
                self.confirmar_reconciliacao.isChecked())

    def tem_edicoes(self):
        return self._form_baseline is not None and self.valores_formulario()!=self._form_baseline

    def resolver_edicoes(self):
        escolha=QMessageBox.question(self,'Revisão ainda não salva',
            'Salvar as alterações antes de sair deste local?',
            QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Cancel)
        if escolha==QMessageBox.Save:
            self.gravar_revisao()
            return not self.tem_edicoes()
        return escolha==QMessageBox.Discard

    def closeEvent(self,evento):
        if self.tem_edicoes() and not self.resolver_edicoes():
            evento.ignore()
        else:
            if self.tem_edicoes():
                self.atualizar()  # Descartar explicitamente repõe o último registro salvo.
            super().closeEvent(evento)

    def desativar(self):
        """Um painel de outra execução não pode reagir à seleção ou salvar revisões."""
        self._ativo=False
        if self.camada_locais is not None and not sip.isdeleted(self.camada_locais):
            try:
                self.camada_locais.selectionChanged.disconnect(self.selecao_inversa)
            except (TypeError,RuntimeError):
                pass
        self.setEnabled(False)
        self.hide()

    def destacar(self):
        uid=self.locais.currentData()
        if not uid:
            return
        membros=detalhes_local(self.dossie,uid)['local']['eventos']
        self._sincronizando=True
        try:
            for c in self.camadas:
                if sip.isdeleted(c):
                    continue
                if self.projeto.mapLayer(c.id()) is None:
                    continue
                papel=c.customProperty('auditoria_fronteiras/papel')
                if papel=='locais':
                    c.selectByIds([f.id() for f in c.getFeatures() if f['LOC_UID']==uid])
                elif c.name()=='EVENTOS_FRONTEIRAS':
                    c.selectByIds([f.id() for f in c.getFeatures() if f['EVT_UID'] in membros])
        finally:
            self._sincronizando=False

    def selecionar_evento(self):
        itens=self.arvore.selectedItems()
        if not itens:
            return
        info=itens[0].data(0,Qt.UserRole)
        if not info or info[0]!='evento':
            return
        for c in self.camadas:
            if sip.isdeleted(c):
                continue
            if c.name()=='EVENTOS_FRONTEIRAS' and self.projeto.mapLayer(c.id()):
                c.selectByIds([f.id() for f in c.getFeatures() if f['EVT_UID']==info[1]])

    def selecao_inversa(self,*args):
        if self._sincronizando:
            return
        try:
            selecionados=self.camada_locais.selectedFeatures()
            if len(selecionados)==1:
                indice=self.locais.findData(selecionados[0]['LOC_UID'])
                self._sincronizando=True
                self.locais.setCurrentIndex(indice)
                self._sincronizando=False
        except RuntimeError:
            self.aviso.setText('Camada removida; os dados preservados continuam consultáveis.')

    def selecionar_origens(self):
        if not self.locais.currentData():
            return
        tubos=detalhes_local(self.dossie,self.locais.currentData())['tubulacoes']
        encontrados,avisos=localizar_tubulacoes(self.dossie,tubos,self.projeto)
        for camada,ids in encontrados.items():
            if ids:
                self.projeto.mapLayer(camada).selectByIds(ids)
        self.aviso.setText('; '.join(avisos) if avisos else 'Tubulações selecionadas por origem e assinatura técnica completa.')

    def aproximar(self):
        if self.canvas is None or not self.locais.currentData():
            self.aviso.setText('Mapa indisponível nesta sessão; informações continuam consultáveis.')
            return
        r=detalhes_local(self.dossie,self.locais.currentData())['local']['registro']
        from qgis.core import QgsRectangle,QgsCoordinateReferenceSystem
        caixa=QgsRectangle(r['X']-15,r['Y']-15,r['X']+15,r['Y']+15)
        trans=QgsCoordinateTransform(QgsCoordinateReferenceSystem(self.dossie['contexto']['parametros']['crs']),
                                    self.canvas.mapSettings().destinationCrs(),self.projeto)
        self.canvas.setExtent(trans.transformBoundingBox(caixa))
        self.canvas.refresh()

    def gravar_revisao(self):
        if not self._ativo:
            return
        uid=self.locais.currentData()
        if not uid:
            return
        try:
            if not self.base:
                caminho,_=QFileDialog.getSaveFileName(self,'Base GPKG nova ou existente — acrescentar execução','',
                    'GeoPackage (*.gpkg)',options=QFileDialog.DontConfirmOverwrite)
                if not caminho:
                    return
                if not caminho.lower().endswith('.gpkg'):
                    caminho+='.gpkg'
                atualizado=salvar_execucao(caminho,self.dossie)
                self.dossie.clear()
                self.dossie.update(atualizado)
                self.base=caminho
                self._revisao_carregada=detalhes_local(self.dossie,uid)['local']['revisao'].get('uid')
            l=detalhes_local(self.dossie,uid)['local']
            rev=salvar_revisao(self.base,self.dossie['execucao_uid'],uid,self.situacao.currentText(),
                self.observacoes.toPlainText(),self.responsavel.text(),self._revisao_carregada)
            l['revisao']=rev
            l['registro']['SITUACAO']=rev['situacao']
            if self.confirmar_reconciliacao.isChecked():
                from .persistencia import avaliar_reconciliacoes,carregar_execucao
                avaliar_reconciliacoes(self.base,self.dossie['execucao_uid'],uid,rev['uid'])
                self.dossie['reconciliacoes']=carregar_execucao(self.base,self.dossie['execucao_uid'])['reconciliacoes']
            aplicar_revisoes(self.camadas,self.dossie)
            self.atualizar()
            self.aviso.setText('Revisão acrescentada ao histórico: '+str(self.base))
            self.revisao_salva.emit(str(self.base))
        except Exception as erro:
            QMessageBox.warning(self,'Revisão não salva',str(erro))

    def mostrar_historico(self):
        if not self.base or not self.locais.currentData():
            self.aviso.setText('Nenhuma base persistente selecionada.')
            return
        try:
            uid=self.locais.currentData()
            linhas=historico(self.base,self.dossie['execucao_uid'],uid)
            anteriores=[]
            for r in self.dossie['reconciliacoes']:
                if r['local_uid']==uid:
                    from .persistencia import listar_execucoes
                    base_anterior=self.base
                    if r['execucao_anterior'] not in {e[0] for e in listar_execucoes(self.base)}:
                        base_anterior=r.get('base_anterior')
                    try:
                        from pathlib import Path
                        if base_anterior and not Path(base_anterior).is_file():
                            raise FileNotFoundError(base_anterior)
                        hs=historico(base_anterior,r['execucao_anterior'],r['local_anterior']) if base_anterior else []
                    except (OSError,ValueError,RuntimeError):
                        hs=[]
                        anteriores.append('Base anterior indisponível; histórico preservado em '+str(base_anterior))
                    anteriores.append(f"Correspondência {r['tipo']} / {r['decisao']} — execução {r['execucao_anterior']} — local {r['local_anterior']}\n"+
                        '\n'.join(f"{h['data_utc']} | {h['situacao']} | {h['responsavel']} | {h['observacoes']}" for h in hs))
            janela=QDialog(self)
            janela.setWindowTitle('Histórico de revisões')
            janela.resize(760,430)
            layout=QVBoxLayout(janela)
            texto=QPlainTextEdit()
            texto.setReadOnly(True)
            atual='\n\n'.join(f"{r['data_utc']} | {r['situacao']} | {r['responsavel']}\n{r['observacoes']}" for r in linhas)
            texto.setPlainText((atual or 'Sem revisões nesta execução.')+'\n\n'+'\n\n'.join(anteriores))
            layout.addWidget(texto)
            janela.exec()
        except Exception as erro:
            QMessageBox.warning(self,'Histórico',str(erro))
