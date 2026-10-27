"""Extensão do painel existente; revisões permanecem na cópia integrada."""
from pathlib import Path
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QDialog,QVBoxLayout,QComboBox,QLabel,QTreeWidget,QTreeWidgetItem,QPushButton,QHBoxLayout,QTabWidget)
from qgis.core import QgsProject,QgsVectorLayer,QgsGeometry,QgsCoordinateTransform,QgsCoordinateReferenceSystem
from auditoria_fronteiras.painel import PainelInspecao
from auditoria_fronteiras.inspecao import restaurar
from auditoria_fronteiras.visualizacao import criar_camadas_temporarias,carregar_no_projeto
from auditoria_fronteiras.visualizacao_locais import criar_camadas_locais
from .saidas_integracao import camadas_integradas


class PainelIntegrado(PainelInspecao):
    def __init__(self,pacote,camadas,wg_camadas,projeto,parent=None,canvas=None,base=None):
        self.pacote=pacote;self.wg_camadas=wg_camadas
        self.por_local={l['uid']:l for l in pacote['resultado']['locais']}
        self.pares={p['uid']:p for p in pacote['resultado']['pares']}
        self.elementos=pacote['topologia']['modelo']['elementos']
        super().__init__(pacote['dossie'],camadas,projeto,parent,canvas,base)
        for i,largura in enumerate((210,140,170,360,100)):self.arvore.setColumnWidth(i,largura)
        self.setWindowTitle('Investigação integrada — '+pacote['resultado']['meta']['uid'][:12])
        b=QPushButton('Investigar componentes (isolados, pequenos e extensos)…');b.clicked.connect(self.abrir_componentes)
        self.layout().insertWidget(2,b)

    def atualizar(self):
        super().atualizar()
        uid=self.locais.currentData()
        if not uid or uid not in self.por_local:return
        l=self.por_local[uid]
        for modo,titulo in [('ESTRUTURAL','WaterGEMS — estrutural'),('TODAS_VALVULAS_ABERTAS','WaterGEMS — potencial')]:
            grupo=QTreeWidgetItem(self.arvore,[titulo]);p=l['perspectivas'][modo]
            grupo.setExpanded(modo=='ESTRUTURAL');grupo.setToolTip(0,modo+' — disponibilidade operacional não validada')
            QTreeWidgetItem(grupo,['Classificação',p['classe'],'',p['escopo']])
            for a in l['correspondencias']:
                for i in a['candidatos'] or [None]:
                    e=self.elementos.get(i,{})
                    info='; '.join(f"{n['inicio']} → {n['fim']}" for n in a.get('nos',[]) if n['tubo']==i)
                    item=QTreeWidgetItem(grupo,['Tubo WaterGEMS',str(i) if i is not None else 'Não encontrado',str(e.get('label','')),
                        a['situacao']+' | '+info,a['gis_uid']])
                    if i is not None:item.setData(0,Qt.UserRole,('wg',i))
            for par_uid in p['pares']:
                par=self.pares[par_uid];item=QTreeWidgetItem(grupo,['Par', '; '.join(par['classes']),'',
                    'Nós comuns: '+str(par['nos_compartilhados'])+' | Caminho A→B: '+str(par['caminho_ab'] is not None)+' | B→A: '+str(par['caminho_ba'] is not None),par_uid])
                QTreeWidgetItem(item,['Evidências','','','; '.join(par['motivos'])])
                QTreeWidgetItem(item,['Alternativa','','','Sem nós compartilhados: '+str(par['alternativa_sem_nos_compartilhados'])])
                for i in par['dispositivos']:
                    e=self.elementos[i];c=QTreeWidgetItem(item,['Dispositivo',str(i),str(e['label']),e['tipo']+' — em um exemplo de caminho'])
                    c.setData(0,Qt.UserRole,('wg',i))
        areas={a['uid']:a for a in self.pacote['areas']}
        grupo=QTreeWidgetItem(self.arvore,['Contexto espacial consultado'])
        for a in l['areas']:
            v=areas[a];QTreeWidgetItem(grupo,[v['tipo'],v['exibicao'],v['camada'],'Interseção espacial; não determina controle hidráulico',a])
        grupo=QTreeWidgetItem(self.arvore,['Pendências de validação'])
        for texto in l['pendencias']:QTreeWidgetItem(grupo,[texto])
        pendentes=[self.arvore.topLevelItem(i) for i in range(self.arvore.topLevelItemCount())]
        while pendentes:
            item=pendentes.pop()
            for col in range(5):item.setToolTip(col,item.text(col))
            pendentes.extend(item.child(i) for i in range(item.childCount()))
        self.aviso.setText('Histórico espacial copiado não valida a topologia. Revisões ficam somente nesta cópia; potencial é hipótese parcial.')

    def selecionar_evento(self):
        itens=self.arvore.selectedItems()
        if itens:
            info=itens[0].data(0,Qt.UserRole)
            if info and info[0]=='wg':self.selecionar_wg(info[1]);return
        super().selecionar_evento()

    def selecionar_wg(self,i):
        for c in self.wg_camadas:
            if self.projeto.mapLayer(c.id()) and c.fields().indexFromName('WG_ID')>=0:
                c.selectByIds([f.id() for f in c.getFeatures() if str(f['WG_ID'])==str(i)])

    def abrir_componentes(self):
        from qgis.PyQt import sip
        from auditoria_fronteiras.janelas import registrar_auxiliar
        anterior=getattr(self,'componentes_dialog',None)
        if anterior is None or sip.isdeleted(anterior):self.componentes_dialog=DialogComponentes(self)
        uid=self.pacote['resultado']['meta']['uid'];chave='componentes:'+uid
        g=registrar_auxiliar(self,chave,self.componentes_dialog,'inventário de componentes · '+uid[:8])
        if g:g.mostrar(chave)
        else:self.componentes_dialog.show();self.componentes_dialog.raise_()


class DialogComponentes(QDialog):
    def __init__(self,painel):
        super().__init__(painel);self.painel=painel;self.pagina=0
        self.setWindowTitle('Componentes — investigação por evidências');self.resize(900,620)
        l=QVBoxLayout(self);self.modo=QComboBox();self.modo.addItems(['ESTRUTURAL','TODAS_VALVULAS_ABERTAS']);l.addWidget(self.modo)
        self.porte=QComboBox();self.porte.addItems(['TRIVIAL_SEM_TUBO','UM_TUBO','REDE_2_A_99_TUBOS','REDE_EXTENSA_100_MAIS','TODOS']);l.addWidget(self.porte)
        self.componentes=QComboBox();self.componentes.setMinimumContentsLength(30);self.componentes.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon);l.addWidget(self.componentes)
        self.resumo=QLabel();self.resumo.setWordWrap(True);l.addWidget(self.resumo)
        self.arvore=QTreeWidget();self.arvore.setHeaderLabels(['Elemento','ID / Label','Informações','Chave']);l.addWidget(self.arvore,1)
        from auditoria_fronteiras.tabelas_consulta import TabelaConsulta
        self.membros_tabela=TabelaConsulta(['Tipo','ID GIS da auditoria','Camada GIS','Label WG','DomainElementID','Componente','Vínculo','Diagnóstico','Chave GIS de correspondência'])
        self.tabs_dados=QTabWidget();l.removeWidget(self.arvore);l.addWidget(self.tabs_dados,1)
        self.tabs_dados.addTab(self.membros_tabela,'Membros em colunas');self.tabs_dados.addTab(self.arvore,'Evidências completas')
        for i,w in enumerate((220,200,350,100)):self.arvore.setColumnWidth(i,w)
        linha=QHBoxLayout();self.mais=QPushButton('Carregar mais 200 membros');self.mais.clicked.connect(self.carregar_mais);linha.addWidget(self.mais)
        zoom=QPushButton('Aproximar componente');zoom.clicked.connect(self.aproximar);linha.addWidget(zoom);l.addLayout(linha)
        self.modo.currentIndexChanged.connect(self.preencher);self.porte.currentIndexChanged.connect(self.preencher);self.componentes.currentIndexChanged.connect(self.exibir)
        self.arvore.itemSelectionChanged.connect(self.selecionar);self.preencher()
        from auditoria_fronteiras.ui_comum import adaptar_janela
        adaptar_janela(self)

    def preencher(self):
        r=self.painel.pacote['resultado'];pot=self.modo.currentText()!='ESTRUTURAL'
        self.cs=r['componentes_potenciais'] if pot else r['componentes'];self.ms=r['membros_potenciais'] if pot else r['membros']
        self.componentes.blockSignals(True);self.componentes.clear()
        for c in self.cs:
            if self.porte.currentText() in ('TODOS',c['porte']):self.componentes.addItem(f"{c['numero']} — {c['n_tubos']} tubos / {c['n_dispositivos']} dispositivos — {c['uid'][:12]}",c['uid'])
        self.componentes.blockSignals(False);self.exibir()

    def exibir(self):
        self.arvore.clear();uid=self.componentes.currentData();self.pagina=0
        self.atual=next((c for c in self.cs if c['uid']==uid),None)
        if not self.atual:self.resumo.setText('Sem componentes nesta faixa.');self.membros_tabela.preencher([]);return
        c=self.atual;self.resumo.setText(f"{c['porte']} | {c['n_nos']} nós | {c['n_tubos']} tubos | {c['n_dispositivos']} dispositivos | "+c['interpretacao_fonte'])
        for titulo,ids in [('Reservatórios',c['reservatorios']),('Tanques',c['tanques']),('Bombas (energia)',c['bombas']),('Extremidades',c['extremidades'])]:
            grupo=QTreeWidgetItem(self.arvore,[titulo])
            for i in ids[:200]:
                e=self.painel.elementos[i];v=QTreeWidgetItem(grupo,[e['tipo'],str(i)+' / '+str(e['label']),'Cadastro',str(i)]);v.setData(0,Qt.UserRole,i)
        grupo=QTreeWidgetItem(self.arvore,['Referências incompletas'])
        for d in c['referencias_incompletas']:QTreeWidgetItem(grupo,[d['codigo'],str(d['id'])])
        grupo=QTreeWidgetItem(self.arvore,['Outros componentes próximos'])
        QTreeWidgetItem(grupo,['Distância',str(c['distancia_m'])+' m' if c['distancia_m'] is not None else 'Não determinada','Proximidade não cria conexão'])
        for u in c['vizinhos']:QTreeWidgetItem(grupo,['Componente',u])
        areas={a['uid']:a for a in self.painel.pacote['areas']};grupo=QTreeWidgetItem(self.arvore,['Áreas relacionadas'])
        for a in c['areas']:
            v=areas[a];QTreeWidgetItem(grupo,[v['tipo'],v['exibicao'],v['camada'],'Interseção cadastral'])
        grupo=QTreeWidgetItem(self.arvore,['Origem das conexões'])
        for fonte,n in c['origens_conexoes'].items():QTreeWidgetItem(grupo,[fonte,str(n)+' tubulações'])
        grupo=QTreeWidgetItem(self.arvore,['Correspondências GIS'])
        correspondencias=[a for a in self.painel.pacote['resultado']['associacoes_componentes'] if a['comp_uid']==uid]
        QTreeWidgetItem(grupo,['Tubos validados',str(c.get('n_tubos_gis_validados',0)),c.get('cobertura_gis','Não determinada')])
        for a in correspondencias[:20]:QTreeWidgetItem(grupo,['GIS ↔ WaterGEMS',str(a['chave'])+' ↔ '+str(a['wg_id']),a['origem'],a['gis_uid']])
        self.grupo_membros=QTreeWidgetItem(self.arvore,['Membros (paginados)']);self.lista_membros=[m for m in self.ms if m['comp_uid']==uid];self.carregar_mais()
        for k in range(self.arvore.topLevelItemCount()):
            g=self.arvore.topLevelItem(k)
            if 0<g.childCount()<=10:g.setExpanded(True)

    def carregar_mais(self):
        if not self.atual:return
        for m in self.lista_membros[self.pagina:self.pagina+200]:
            v=QTreeWidgetItem(self.grupo_membros,[m['tipo'],str(m['id'])+' / '+str(m['label']),'; '.join(m['diagnosticos']),str(m['id'])]);v.setData(0,Qt.UserRole,m['id'])
        self.pagina+=200;self.mais.setEnabled(self.pagina<len(self.lista_membros))
        d=self.painel.pacote['dossie'];ts={t['uid']:t for t in d['tubulacoes']};fontes={f['origem']:f['camada'] for f in d['contexto']['fontes']}
        assocs={a['wg_id']:a for a in self.painel.pacote['resultado']['associacoes_componentes'] if a['comp_uid']==self.atual['uid']}
        linhas=[]
        for m in self.lista_membros[:self.pagina]:
            a=assocs.get(m['id'],{});t=ts.get(a.get('gis_uid'),{})
            linhas.append([m['tipo'],t.get('id_exibido'),fontes.get(a.get('origem')),m['label'],m['id'],self.atual['numero'],'INEQUIVOCA' if a else 'SEM_CORRESPONDENCIA_PRESERVADA','; '.join(m['diagnosticos']),a.get('chave')])
        self.membros_tabela.preencher(linhas)

    def selecionar(self):
        itens=self.arvore.selectedItems()
        if itens:
            i=itens[0].data(0,Qt.UserRole)
            if isinstance(i,int):self.painel.selecionar_wg(i)

    def aproximar(self):
        if not self.atual or not self.painel.canvas:return
        gs=[self.painel.pacote['geometrias'][i] for i in self.atual['nos']+self.atual['tubos'] if i in (self.painel.pacote.get('geometrias') or {})]
        if not gs:self.resumo.setText('Referência espacial não validada: aproximação bloqueada.');return
        caixa=QgsGeometry.collectGeometry(gs).boundingBox();caixa.grow(10)
        t=QgsCoordinateTransform(QgsCoordinateReferenceSystem(self.painel.pacote['resultado']['meta']['parametros']['crs']),self.painel.canvas.mapSettings().destinationCrs(),self.painel.projeto)
        self.painel.canvas.setExtent(t.transformBoundingBox(caixa));self.painel.canvas.refresh()


def abrir_painel(pacote,base,projeto=None,parent=None,canvas=None):
    from auditoria_fronteiras.organizacao_camadas import publicar
    projeto=projeto or QgsProject.instance();resultado,analise=restaurar(pacote['dossie'])
    uid=pacote['resultado']['meta']['uid'];base=str(Path(base).resolve())
    conhecidas=[c for c in projeto.mapLayers().values() if c.customProperty('integracao/uid')==uid and c.customProperty('integracao/base')==base]
    geo=[c for c in conhecidas if c.customProperty('integracao/grupo')=='geo']
    wg=[c for c in conhecidas if c.customProperty('integracao/grupo')=='wg']
    meta=pacote['resultado']['meta'];nome=meta.get('projeto') or meta.get('nome','Investigação');versao=meta.get('versao',1)
    if any(not c.isValid() for c in conhecidas):raise ValueError('Resultados carregados contêm camada inválida. Reabra explicitamente a fonte correta; camadas anteriores foram preservadas.')
    vazias=[c for c in projeto.mapLayers().values() if c.customProperty('wna/uid')==uid and c.providerType()=='memory' and c.featureCount()==0 and int(c.customProperty('wna/quantidade',0))>0]
    if geo and len(wg)==3 and not vazias:
        for c in conhecidas:publicar(c,projeto,'integrada',uid,base,nome,versao,'Elementos WaterGEMS' if c in wg else None)
        from auditoria_fronteiras.painel import aplicar_revisoes
        aplicar_revisoes(geo,pacote['dossie'])
        painel=PainelIntegrado(pacote,geo,wg,projeto,parent,canvas,base);painel.show();return painel
    cs=criar_camadas_temporarias(resultado)+criar_camadas_locais(resultado,analise)
    for i,c in enumerate(cs):
        c.setCustomProperty('integracao/uid',uid);c.setCustomProperty('integracao/base',base);c.setCustomProperty('integracao/grupo','geo')
        cs[i]=publicar(c,projeto,'integrada',uid,base,nome,versao,'Relações e auxiliares' if c.customProperty('auditoria_fronteiras/papel')=='tecnica' else None)
    wg=[]
    from .saidas import camadas
    # Novas representações; simbologias e camadas originais não são alteradas.
    for c in camadas(pacote['topologia']['modelo'],pacote['topologia']['estrutural'],pacote.get('geometrias'),
        pacote['resultado']['meta']['parametros']['crs'] if pacote.get('geometrias') else None)[:3]:
        c.setCustomProperty('integracao/uid',uid);c.setCustomProperty('integracao/base',base);c.setCustomProperty('integracao/grupo','wg');wg.append(publicar(c,projeto,'integrada',uid,base,nome,versao,'Elementos WaterGEMS'))
    for c in camadas_integradas(pacote):
        c.setCustomProperty('integracao/base',base);publicar(c,projeto,'integrada',uid,base,nome,versao)
    painel=PainelIntegrado(pacote,cs,wg,projeto,parent,canvas,base);painel.show();return painel
