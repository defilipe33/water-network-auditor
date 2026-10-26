from pathlib import Path
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QGridLayout,QComboBox,QLabel,QLineEdit,QTableWidget,QTableWidgetItem,QPushButton,QFileDialog,QMessageBox,QAbstractItemView


class SeletorBases(QDialog):
    def __init__(self,catalogo,parent=None,tipo=None):
        super().__init__(parent);self.catalogo=catalogo;self.tipo=tipo;self.selecionada=None;self.setWindowTitle('Catálogo de bases e investigações');self.resize(950,600)
        v=QVBoxLayout(self);self.busca=QLineEdit();self.busca.setPlaceholderText('Pesquisar nome, município ou modelo…');v.addWidget(self.busca)
        self.filtros={};g=QGridLayout();v.addLayout(g)
        self.itens=catalogo.listar()
        for i,(k,nome) in enumerate([('projeto','Município/projeto'),('modelo_uid','Modelo'),('tipo','Tipo'),('versao','Versão'),('data','Data'),('cenario','Cenário'),('hipotese','Hipótese'),('situacao','Situação')]):
            c=QComboBox();c.addItem('Todos',None)
            for valor in sorted({str(r.get(k,'')) for r in self.itens if r.get(k) is not None}):c.addItem(valor,valor)
            g.addWidget(QLabel(nome),i//2*2,i%2);g.addWidget(c,i//2*2+1,i%2);self.filtros[k]=c;c.currentIndexChanged.connect(self.atualizar)
        self.tabela=QTableWidget(0,6);self.tabela.setHorizontalHeaderLabels(['Nome','Projeto','Tipo','Versão','Cenário/hipótese','Arquivo disponível'])
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers);self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows);self.tabela.setSelectionMode(QAbstractItemView.SingleSelection);v.addWidget(self.tabela,1)
        l=QHBoxLayout();v.addLayout(l)
        for nome,acao in [('Adicionar arquivo…',self.adicionar),('Reexaminar pasta',self.varrer),('Abrir selecionada',self.abrir),('Cancelar',self.reject)]:
            b=QPushButton(nome);b.clicked.connect(acao);l.addWidget(b)
        self.busca.textChanged.connect(self.atualizar);self.atualizar()
    def atualizar(self):
        self.visiveis=[r for r in self.itens if (not self.tipo or r['tipo']==self.tipo) and all(c.currentData() is None or str(r.get(k,''))==c.currentData() for k,c in self.filtros.items()) and self.busca.text().casefold() in ' '.join(str(v) for k,v in r.items() if k!='base').casefold()]
        self.tabela.setRowCount(len(self.visiveis))
        for i,r in enumerate(self.visiveis):
            for j,valor in enumerate([r['nome'],r.get('projeto',''),r['tipo'],r['versao'],str(r.get('cenario',''))+' / '+r.get('hipotese',''),'Sim' if Path(r['base']).exists() else 'Ausente — localizar ao abrir']):
                item=QTableWidgetItem(str(valor));item.setToolTip(r['base']+'\nUUID '+r['uuid']);self.tabela.setItem(i,j,item)
        self.tabela.resizeColumnsToContents()
    def adicionar(self):
        p,_=QFileDialog.getOpenFileName(self,'Adicionar base persistente','','GeoPackage (*.gpkg)')
        if p:
            try:self.catalogo.registrar(p);self.recarregar()
            except Exception as e:QMessageBox.warning(self,'Arquivo não registrado',str(e))
    def varrer(self):
        avisos=self.catalogo.varrer();self.recarregar()
        if avisos:QMessageBox.information(self,'Arquivos ignorados','\n'.join(avisos[:15]))
    def recarregar(self):
        self.itens=self.catalogo.listar()
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
        self.selecionada=r;self.accept()
