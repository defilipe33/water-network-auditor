"""Uma única seleção marcada para listas com categorias e busca."""

from collections import defaultdict
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QAbstractItemView,QComboBox,QDialog,QDialogButtonBox,QHBoxLayout,QLineEdit,
    QTreeWidget,QTreeWidgetItem,QVBoxLayout)

from .modelo_gis_ui import aviso,botao


def opcoes_corredores(registros):
    por_id={r['uid']:r for r in registros}
    for r in registros:
        funcoes=set(r.get('funcoes') or ())
        tipo=r.get('tipo')
        pai=por_id.get(r.get('pai'),{})
        grupo=('Troncos' if tipo=='TRONCO' or 'TRONCO' in funcoes else
               'Ramais secundários' if tipo=='RAMAL' and pai.get('tipo')=='RAMAL' else
               'Ramais principais' if tipo=='RAMAL' and pai.get('tipo')=='TRONCO' else
               'Ramais' if tipo=='RAMAL' or 'RAMAL' in funcoes else
               'Alternativas' if tipo in ('ALTERNATIVO','ALTERNATIVA') or funcoes.intersection(('ALTERNATIVO','ALTERNATIVA'))
               else 'Outros corredores')
        yield r['uid'],r.get('nome') or r['uid'][:10],grupo


class SeletorMultiplos(QDialog):
    def __init__(self,parent,titulo,opcoes,marcados=()):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.resize(620,485)
        self.linhas=[]
        self.grupos={}
        v=QVBoxLayout(self)
        self.busca=QLineEdit()
        self.busca.setPlaceholderText('Pesquisar por nome')
        v.addWidget(self.busca)
        self.categoria=QComboBox()
        self.categoria.addItem('Todas as categorias',None)
        v.addWidget(self.categoria)
        self.arvore=QTreeWidget()
        self.arvore.setHeaderHidden(True)
        self.arvore.setSelectionMode(QAbstractItemView.NoSelection)
        v.addWidget(self.arvore,1)
        marcados=set(marcados)
        for uid,nome,*grupos in opcoes:
            grupo=grupos[0] if grupos else None
            pai=self.arvore
            if grupo:
                if grupo not in self.grupos:
                    self.grupos[grupo]=QTreeWidgetItem(self.arvore,[grupo])
                    self.categoria.addItem(grupo,grupo)
                pai=self.grupos[grupo]
            i=QTreeWidgetItem(pai,[str(nome)])
            i.setCheckState(0,Qt.Checked if uid in marcados else Qt.Unchecked)
            self.linhas.append((uid,i,grupo,str(nome).casefold()))
        if sum(g.startswith('Ramais') for g in self.grupos)>1:
            self.categoria.insertItem(1,'Todos os ramais','@RAMAIS')
        self.categoria.setVisible(bool(self.grupos))
        self.arvore.expandAll()
        for rotulos in ((('Selecionar todos','TODOS'),('Limpar seleção','LIMPAR'),('Inverter seleção','INVERTER')),
                        (('Selecionar itens filtrados','VISIVEIS'),)):
            faixa=QHBoxLayout()
            v.addLayout(faixa)
            for texto,acao in rotulos:
                botao(faixa,texto,lambda _,a=acao:self.alterar(a))
        self.resumo=aviso()
        v.addWidget(self.resumo)
        b=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        b.accepted.connect(self.accept)
        b.rejected.connect(self.reject)
        v.addWidget(b)
        self.busca.textChanged.connect(self.filtrar)
        self.categoria.currentIndexChanged.connect(self.filtrar)
        self.arvore.itemChanged.connect(self.contar)
        self.filtrar()

    def filtrar(self,*_):
        termo=self.busca.text().strip().casefold()
        tipo=self.categoria.currentData()
        visiveis=defaultdict(int)
        for _,i,grupo,nome in self.linhas:
            corresponde=not tipo or tipo==grupo or tipo=='@RAMAIS' and (grupo or '').startswith('Ramais')
            aparece=corresponde and termo in nome
            i.setHidden(not aparece)
            if aparece:visiveis[grupo]+=1
        for k,i in self.grupos.items():i.setHidden(not visiveis[k])
        self.contar()

    def alterar(self,acao):
        self.arvore.blockSignals(True)
        for _,i,_,_ in self.linhas:
            if acao=='VISIVEIS' and i.isHidden():continue
            desmarcar=acao=='LIMPAR' or acao=='INVERTER' and i.checkState(0)==Qt.Checked
            i.setCheckState(0,Qt.Unchecked if desmarcar else Qt.Checked)
        self.arvore.blockSignals(False)
        self.contar()

    def selecionados(self):
        return [u for u,i,_,_ in self.linhas if i.checkState(0)==Qt.Checked]

    def contar(self,*_):
        n=sum(not i.isHidden() for _,i,_,_ in self.linhas)
        self.resumo.setText(f'{len(self.selecionados())} marcados · {n} de {len(self.linhas)} itens no filtro')


def escolher(parent,titulo,opcoes,marcados=()):
    dlg=SeletorMultiplos(parent,titulo,opcoes,marcados)
    return dlg.selecionados() if dlg.exec()==QDialog.Accepted else None
