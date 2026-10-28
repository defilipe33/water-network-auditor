from pathlib import Path
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QGridLayout,QComboBox,QLabel,QLineEdit,QTableWidget,QTableWidgetItem,QPushButton,QFileDialog,QMessageBox,QAbstractItemView,QGroupBox,QInputDialog


class SeletorBases(QDialog):
    def __init__(self,catalogo,parent=None,tipo=None):
        super().__init__(parent);self.catalogo=catalogo;self.tipo=tipo;self.selecionada=None;self.setWindowTitle('Catálogo de bases e investigações');self.resize(950,600)
        v=QVBoxLayout(self);self.busca=QLineEdit();self.busca.setPlaceholderText('Pesquisar nome, município ou modelo…');v.addWidget(self.busca)
        self.filtros={};g=QGridLayout();v.addLayout(g);self.avancados=QGroupBox('Filtros avançados');self.avancados.setCheckable(True);self.avancados.setChecked(False);self.avancado_widget=__import__('qgis.PyQt.QtWidgets',fromlist=['QWidget']).QWidget();ag=QGridLayout(self.avancado_widget);av=QVBoxLayout(self.avancados);av.addWidget(self.avancado_widget);self.avancado_widget.hide();self.avancados.toggled.connect(self.avancado_widget.setVisible);v.addWidget(self.avancados)
        self.itens=catalogo.listar_opcional();self.avisos=QLabel('\n'.join(catalogo.avisos[:3]));self.avisos.setWordWrap(True);v.addWidget(self.avisos)
        for i,(k,nome) in enumerate([('projeto','Município/projeto'),('modelo_uid','Modelo'),('tipo','Tipo'),('versao','Versão'),('data','Data'),('cenario','Cenário'),('hipotese','Hipótese'),('situacao','Situação')]):
            c=QComboBox();c.addItem('Todos',None)
            for valor in sorted({str(r.get(k,'')) for r in self.itens if r.get(k) is not None}):c.addItem(valor,valor)
            dest=g if k in ('projeto','tipo') else ag;dest.addWidget(QLabel(nome),i//2*2,i%2);dest.addWidget(c,i//2*2+1,i%2);self.filtros[k]=c;c.currentIndexChanged.connect(self.atualizar)
        self.secao=QComboBox();self.secao.addItems(['Investigações e bases ativas','Cópias de segurança / recuperação','Arquivadas','Todos os arquivos']);self.secao.currentIndexChanged.connect(self.atualizar);v.addWidget(self.secao);self.tabela=QTableWidget(0,8);self.tabela.setHorizontalHeaderLabels(['Nome / UUID','Projeto','Tipo','Versão','Cenário/hipótese','Arquivo disponível','Situação / classificação','Última alteração'])
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers);self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows);self.tabela.setSelectionMode(QAbstractItemView.SingleSelection);v.addWidget(self.tabela,1)
        l=QHBoxLayout();v.addLayout(l)
        for nome,acao in [('Adicionar arquivo…',self.adicionar),('Reexaminar pasta',self.varrer),('Abrir selecionada',self.abrir),('Cancelar',self.reject)]:
            b=QPushButton(nome);b.clicked.connect(acao);l.addWidget(b)
        gestao=QHBoxLayout();v.addLayout(gestao)
        for nome,acao in [('Limpar filtros',self.limpar),('Renomear',lambda:self.gerir('RENOMEAR')),('Arquivar',lambda:self.gerir('ARQUIVAR')),('Restaurar',lambda:self.gerir('RESTAURAR')),('Retirar do catálogo',lambda:self.gerir('RETIRAR')),('Detalhes',self.detalhes)]:
            b=QPushButton(nome);b.clicked.connect(acao);gestao.addWidget(b)
        mais=QGroupBox('Operações físicas avançadas');mais.setCheckable(True);mais.setChecked(False);mv=QHBoxLayout(mais);remover=QPushButton('Excluir arquivos da investigação…');mv.addWidget(remover);remover.hide();mais.toggled.connect(remover.setVisible);remover.clicked.connect(self.excluir);restaurar=QPushButton('Recuperar arquivo movido…');mv.addWidget(restaurar);restaurar.hide();mais.toggled.connect(restaurar.setVisible);restaurar.clicked.connect(self.recuperar_fisico);v.addWidget(mais)
        self.busca.textChanged.connect(self.atualizar);self.atualizar()
        from auditoria_fronteiras.ui_comum import adaptar_janela
        adaptar_janela(self)
    def atualizar(self):
        self.visiveis=[r for r in self.itens if self.na_secao(r) and (not self.tipo or r['tipo']==self.tipo) and all(c.currentData() is None or str(r.get(k,''))==c.currentData() for k,c in self.filtros.items()) and self.busca.text().casefold() in ' '.join(str(v) for k,v in r.items() if k!='base').casefold()]
        self.tabela.setRowCount(len(self.visiveis))
        for i,r in enumerate(self.visiveis):
            for j,valor in enumerate([r['nome']+' · '+r['uuid'][:8],r.get('projeto',''),r['tipo'],r['versao'],str(r.get('cenario',''))+' / '+r.get('hipotese',''),'Sim' if Path(r['base']).exists() else 'Ausente — localizar ao abrir',r.get('estado_catalogo','ATIVA')+' / '+r.get('classe_arquivo',''),r.get('ultima_alteracao','')]):
                item=QTableWidgetItem(str(valor));item.setToolTip(r['base']+'\nUUID '+r['uuid']);self.tabela.setItem(i,j,item)
        self.tabela.resizeColumnsToContents()
    def adicionar(self):
        p,_=QFileDialog.getOpenFileName(self,'Adicionar base persistente','','GeoPackage (*.gpkg)')
        if p:
            try:
                from auditoria_topologica_watergems.gestao_catalogo import adicionar
                adicionar(self.catalogo,p);self.recarregar()
            except Exception as e:QMessageBox.warning(self,'Arquivo não registrado',str(e))
    def varrer(self):
        avisos=self.catalogo.varrer();self.recarregar()
        if avisos:QMessageBox.information(self,'Arquivos ignorados','\n'.join(avisos[:15]))
    def recarregar(self):
        self.itens=self.catalogo.listar_opcional();self.avisos.setText('\n'.join(self.catalogo.avisos[:3]))
        for k,c in self.filtros.items():
            antes=c.currentData();c.blockSignals(True);c.clear();c.addItem('Todos',None)
            for valor in sorted({str(r.get(k,'')) for r in self.itens if r.get(k) is not None}):c.addItem(valor,valor)
            c.setCurrentIndex(max(0,c.findData(antes)));c.blockSignals(False)
        self.atualizar()
    def abrir(self):
        i=self.tabela.currentRow()
        if i<0:return
        r=self.visiveis[i]
        if not Path(r['base']).is_file():
            p,_=QFileDialog.getOpenFileName(self,'Localizar arquivo movido','','GeoPackage (*.gpkg)')
            if not p:return
            try:self.catalogo.localizar(r['uuid'],r['tipo'],p)
            except Exception as e:QMessageBox.warning(self,'Identidade incompatível',str(e));return
            r=dict(r,base=str(Path(p).resolve()))
        try:
            from auditoria_topologica_watergems.gerenciamento import identificar
            if not any(m['uuid']==r['uuid'] and m['tipo']==r['tipo'] for m in identificar(r['base'])):raise ValueError('O arquivo não contém mais a identidade selecionada. Reexamine a pasta; a versão não foi trocada automaticamente.')
        except Exception as e:QMessageBox.warning(self,'Índice desatualizado',str(e));return
        self.selecionada=r;self.accept()

    def na_secao(self,r):
        sec=self.secao.currentIndex() if hasattr(self,'secao') else 0
        backup=r.get('classe_arquivo') in ('BACKUP_TECNICO','BACKUP_CANDIDATO');arch=r.get('estado_catalogo')=='ARQUIVADA'
        return sec==3 or sec==1 and backup or sec==2 and arch or sec==0 and not backup and not arch
    def atual(self):
        i=self.tabela.currentRow()
        return self.visiveis[i] if i>=0 else None
    def limpar(self):
        self.busca.clear()
        for c in self.filtros.values():c.setCurrentIndex(0)
        self.atualizar()
    def gerir(self,acao):
        from auditoria_topologica_watergems.gestao_catalogo import alterar
        r=self.atual()
        if not r:return
        nome=None
        if acao=='RENOMEAR':
            nome,ok=QInputDialog.getText(self,'Nome de exibição','Não altera o nome físico do GPKG:',text=r['nome'])
            if not ok:return
        if acao=='RETIRAR' and QMessageBox.question(self,'Retirar referência','Retirar somente do catálogo? O arquivo permanece no disco.',QMessageBox.Yes|QMessageBox.No)!=QMessageBox.Yes:return
        try:alterar(self.catalogo,r,acao,nome);self.recarregar()
        except Exception as e:QMessageBox.warning(self,'Catálogo preservado',str(e))
    def detalhes(self):
        import json
        r=self.atual()
        if not r:return
        try:
            from auditoria_topologica_watergems.decisoes import abrir_ro
            dados=dict(r)
            with abrir_ro(r['base']) as c:
                tabelas={x[0] for x in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                dados['contagens']={t:c.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('IGD_ANALISES','IGD_OBJETOS','IGD_PROPOSTAS','IGD_OBJ_HIST') if t in tabelas}
            msg=QMessageBox(self);msg.setWindowTitle('Detalhes da investigação');msg.setText(r['nome']+' · '+r['uuid'][:12]);msg.setDetailedText(json.dumps(dados,ensure_ascii=False,indent=2));msg.exec_()
        except Exception as e:QMessageBox.warning(self,'Detalhes indisponíveis',str(e))
    def excluir(self):
        from auditoria_topologica_watergems.gestao_catalogo import dependencias,recuperar_arquivo
        r=self.atual()
        if not r:return
        ativas=list(getattr(self.catalogo,'bases_ativas',lambda:[])())
        from qgis.core import QgsProject
        ativas += [c.source().split('|')[0] for c in QgsProject.instance().mapLayers().values() if '.gpkg' in c.source().lower()]
        plano=dependencias(self.catalogo,r,ativas)
        texto='Mover para recuperação reversível:\n'+'\n'.join(plano['arquivos'])+'\n'+plano['preservados']
        if plano['bloqueios']:QMessageBox.warning(self,'Operação bloqueada',texto+'\n'+'\n'.join(plano['bloqueios']));return
        if QMessageBox.question(self,'Confirmar arquivos selecionados',texto,QMessageBox.Yes|QMessageBox.No)!=QMessageBox.Yes:return
        try:recuperar_arquivo(self.catalogo,r,ativas,True);self.recarregar()
        except Exception as e:QMessageBox.warning(self,'Arquivos preservados',str(e))

    def recuperar_fisico(self):
        p,_=QFileDialog.getOpenFileName(self,'Manifesto da recuperação reversível',str(self.catalogo.raiz/'RECUPERACAO'),'Manifesto (*.recuperacao.json)')
        if not p:return
        try:
            from auditoria_topologica_watergems.gestao_catalogo import restaurar_arquivo
            restaurar_arquivo(self.catalogo,p);self.recarregar()
        except Exception as e:QMessageBox.warning(self,'Recuperação não aplicada',str(e))
