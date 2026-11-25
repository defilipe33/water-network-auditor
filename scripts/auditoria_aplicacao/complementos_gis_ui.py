"""Edição de origens e relações explícitas usando a identidade do inventário GIS."""

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout)

from .modelo_gis_ui import aviso
from .persistencia_grafo_gis import SITUACOES, DECISOES


def _combo(pares):
    b=QComboBox()
    for k,v in pares.items():b.addItem(v,k)
    return b


def _nome(t):
    return f"{t.get('label') or t.get('id') or 'Sem ID'} · {t['camada']} · parte {t.get('parte',0)+1} · {t['uid'][:8]}"


class EditarComplemento(QDialog):
    escolher_tubos=pyqtSignal()
    escolher_origem=pyqtSignal()
    portas_alteradas=pyqtSignal()

    def __init__(self, parent, tipo, tubos, equipamentos, ponto, anterior=None, candidato=None):
        super().__init__(parent)
        self.tipo=tipo
        self.tubos={t['uid']:t for t in tubos}
        self.equipamentos={t['uid']:t for t in equipamentos}
        self.anterior=anterior or {}
        self.candidato=candidato
        self.ponto=ponto
        self.antes_salvar=None
        self.setWindowTitle('Definir fonte de água' if tipo=='ORIGEM' else 'Registrar conexão GIS')
        self.resize(560,520)
        v=QVBoxLayout(self)
        f=QFormLayout()
        v.addLayout(f)
        self.nome=QLineEdit(self.anterior.get('nome',''))
        f.addRow('Nome opcional',self.nome)
        estados={k:v for k,v in SITUACOES.items() if k!='CADASTRADA'}
        self.estado=_combo(estados)
        self.estado.setCurrentIndex(max(0,self.estado.findData(self.anterior.get('situacao'))))
        f.addRow('Natureza',self.estado)
        self.nota=QLineEdit(self.anterior.get('nota',''))
        f.addRow('Observação opcional',self.nota)
        self.categoria=_combo({'ENTRADA':'Ponto de entrada','RESERVOIR':'Reservatório','TANK':'Tanque'})
        self.categoria.setCurrentIndex(max(0,self.categoria.findData(self.anterior.get('categoria'))))
        self.equipamento=QComboBox()
        self.equipamento.addItem('Elemento complementar',None)
        self.decisao=_combo(DECISOES)
        self.decisao.setCurrentIndex(self.decisao.findData(self.anterior.get('decisao','CANDIDATA')))
        if tipo=='ORIGEM':
            for e in equipamentos:
                self.equipamento.addItem(_nome(e),e['uid'])
            self.equipamento.setCurrentIndex(max(0,self.equipamento.findData(self.anterior.get('equipamento'))))
            f.addRow('Origem cadastrada',self.equipamento)
            f.addRow('Categoria complementar',self.categoria)
            selecionar_origem=QPushButton('Selecionar origem no mapa')
            selecionar_origem.clicked.connect(self.escolher_origem.emit)
            v.addWidget(selecionar_origem)
            self.reusar=QPushButton('Usar associação já declarada')
            self.reusar.clicked.connect(self.reusar_declaracao)
            v.addWidget(self.reusar)
        else:
            f.addRow('Interpretação',self.decisao)

        self.portas=[tuple(p) for p in self.anterior.get('portas',candidato['portas'] if candidato else [])]
        self.busca=QLineEdit()
        self.busca.setPlaceholderText('Pesquisar tubulação por ID, nome, camada ou UUID')
        self.busca.textChanged.connect(self.listar_tubos)
        self.disponiveis=QListWidget()
        if not candidato:
            selecionar_tubos=QPushButton('Selecionar tubulações no mapa')
            selecionar_tubos.setObjectName('Principal')
            selecionar_tubos.clicked.connect(self.escolher_tubos.emit)
            v.addWidget(selecionar_tubos)
            v.addWidget(self.busca)
            v.addWidget(self.disponiveis,1)
            linha=QHBoxLayout()
            v.addLayout(linha)
            self.posicao=_combo({0.:'Início',1.:'Fim',None:'Posição intermediária'})
            linha.addWidget(self.posicao)
            self.fracao=QDoubleSpinBox()
            self.fracao.setRange(.01,99.99)
            self.fracao.setValue(50)
            self.fracao.setSuffix(' %')
            self.fracao.hide()
            self.posicao.currentIndexChanged.connect(lambda:self.fracao.setVisible(self.posicao.currentData() is None))
            linha.addWidget(self.fracao)
            adicionar=QPushButton('Vincular porta selecionada')
            adicionar.clicked.connect(self.adicionar)
            linha.addWidget(adicionar)
        self.vinculos=QListWidget()
        v.addWidget(aviso('Tubulações e posições vinculadas'))
        v.addWidget(self.vinculos,1)
        if not candidato:
            remover=QPushButton('Remover vínculo selecionado')
            remover.clicked.connect(self.remover)
            v.addWidget(remover)
            editar_posicao=QPushButton('Aplicar posição acima ao vínculo selecionado')
            editar_posicao.clicked.connect(self.editar_posicao)
            v.addWidget(editar_posicao)
        self.info=aviso()
        v.addWidget(self.info)
        botoes=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        botoes.accepted.connect(self.validar)
        botoes.rejected.connect(self.reject)
        v.addWidget(botoes)
        self.listar_tubos()
        self.listar_portas()

    def listar_tubos(self):
        from itertools import islice
        termo=self.busca.text().strip().casefold()
        self.disponiveis.clear()
        for t in islice((t for t in self.tubos.values() if termo in (_nome(t)+' '+t['uid']).casefold()),200):
            item=QListWidgetItem(_nome(t))
            item.setData(Qt.UserRole,t['uid'])
            self.disponiveis.addItem(item)

    def listar_portas(self):
        self.vinculos.clear()
        for uid,pos in self.portas:
            t=self.tubos.get(uid)
            self.vinculos.addItem(((_nome(t) if t else uid+' · referência ausente'))+f' — {100*pos:g}%')

    def adicionar(self):
        item=self.disponiveis.currentItem()
        if item:
            pos=self.posicao.currentData()
            porta=(item.data(Qt.UserRole),self.fracao.value()/100 if pos is None else pos)
            self.adicionar_mapa(*porta)

    def adicionar_mapa(self,uid,posicao):
        porta=(uid,posicao)
        if uid in self.tubos and porta not in self.portas:
            self.portas.append(porta)
            self.listar_portas()
            self.portas_alteradas.emit()

    def editar_posicao(self):
        i=self.vinculos.currentRow()
        if i<0:return
        uid,_=self.portas[i]
        pos=self.posicao.currentData()
        porta=(uid,self.fracao.value()/100 if pos is None else pos)
        if porta not in self.portas:
            self.portas[i]=porta
            self.listar_portas()
            self.portas_alteradas.emit()

    def remover(self):
        i=self.vinculos.currentRow()
        if i>=0:
            self.portas.pop(i)
            self.listar_portas()
            self.portas_alteradas.emit()

    def reusar_declaracao(self):
        e=self.equipamentos.get(self.equipamento.currentData(),{})
        ds=[d for d in e.get('declaracoes',[]) if d['portas']]
        if len(ds)!=1:
            self.info.setText('Não há uma declaração única com posições válidas. Escolha as portas explicitamente.')
            return
        self.portas=[tuple(p) for p in ds[0]['portas']]
        self.listar_portas()
        self.portas_alteradas.emit()

    def validar(self):
        minimo=1 if self.tipo=='ORIGEM' else 2
        if len(set(self.portas))<minimo or any(u not in self.tubos for u,_ in self.portas):
            self.info.setText(f'Selecione pelo menos {minimo} porta(s) válida(s).')
            return
        eq=self.equipamentos.get(self.equipamento.currentData())
        if self.tipo=='ORIGEM' and not eq and not self.ponto:
            self.info.setText('Escolha uma origem cadastrada ou use Adicionar origem no mapa.')
            return
        anterior=self.anterior
        self.dados=dict(nome=self.nome.text().strip(), nota=self.nota.text().strip(),
                        situacao='CADASTRADA' if eq else self.estado.currentData(),
                        portas=sorted(self.portas), habilitado=anterior.get('habilitado',True))
        if self.tipo=='ORIGEM':
            self.dados.update(categoria=eq['categoria'] if eq else self.categoria.currentData(),
                              equipamento=eq['uid'] if eq else None, wkb=eq['wkb'] if eq else None,
                              xy=None if eq else self.ponto['xy'], crs=self.ponto['crs'] if self.ponto else None)
        else:
            self.dados.update(decisao=self.decisao.currentData(),candidato=self.candidato['uid'] if self.candidato else None,
                              categoria_candidata=self.candidato.get('tipo') if self.candidato else None)
        if self.antes_salvar is not None:
            try:
                self.antes_salvar(self.dados)
            except (ValueError, OSError, RuntimeError) as erro:
                self.info.setText(str(erro))
                return
        self.accept()
