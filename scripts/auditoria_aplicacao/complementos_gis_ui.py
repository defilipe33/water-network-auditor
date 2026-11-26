"""Edição de origens e relações explícitas usando a identidade do inventário GIS."""

from sqlite3 import Error as ErroBanco
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout)

from .modelo_gis_ui import aviso, expansivel
from .navegacao_cartografica import acao_disponivel, navegar_registros
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
    navegar_tubo=pyqtSignal(str,bool)

    def __init__(self, parent, tipo, tubos, equipamentos, ponto, anterior=None, candidato=None):
        super().__init__(parent)
        self.setWindowModality(Qt.NonModal)
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
        self.decisao.setToolTip('Confirmada aceita a conexão na hipótese em que for incluída. Sem conexão mantém as tubulações separadas nessa hipótese.')
        if tipo=='ORIGEM':
            for e in equipamentos:
                self.equipamento.addItem(_nome(e),e['uid'])
            self.equipamento.setCurrentIndex(max(0,self.equipamento.findData(self.anterior.get('equipamento'))))
            f.addRow('Origem cadastrada',self.equipamento)
            f.addRow('Categoria complementar',self.categoria)
            selecionar_origem=QPushButton('Selecionar origem no mapa')
            acao_disponivel(selecionar_origem,'' if self.equipamentos else 'Nenhum equipamento de origem está disponível no escopo.',
                            'Clique em um reservatório, tanque ou origem cadastrada.')
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
            acao_disponivel(selecionar_tubos,'' if self.tubos else 'Nenhuma tubulação está disponível no escopo.',
                            'Clique nos pontos de conexão. Botão direito conclui e Esc restaura os pontos anteriores.')
            selecionar_tubos.clicked.connect(self.escolher_tubos.emit)
            v.addWidget(selecionar_tubos)
            _,avancado=expansivel(v,'Buscar tubulação ou ajustar posição')
            avancado.addWidget(self.busca)
            avancado.addWidget(self.disponiveis,1)
            self.disponiveis.setMaximumHeight(130)
            linha=QHBoxLayout()
            avancado.addLayout(linha)
            self.posicao=_combo({0.:'Início da tubulação (0%)',1.:'Fim da tubulação (100%)',None:'Ponto ao longo da tubulação'})
            self.posicao.setToolTip('Início e fim seguem a ordem dos vértices da geometria GIS. O sentido do escoamento não é conhecido.')
            linha.addWidget(self.posicao)
            self.fracao=QDoubleSpinBox()
            self.fracao.setRange(.01,99.99)
            self.fracao.setValue(50)
            self.fracao.setSuffix(' %')
            self.fracao.hide()
            self.posicao.currentIndexChanged.connect(lambda:self.fracao.setVisible(self.posicao.currentData() is None))
            linha.addWidget(self.fracao)
            self.adicionar_b=QPushButton('Adicionar ponto de conexão')
            self.adicionar_b.clicked.connect(self.adicionar)
            avancado.addWidget(self.adicionar_b)
            self.disponiveis.currentItemChanged.connect(self.atualizar_acoes)
            navegar_registros(self.disponiveis,lambda i,a:self.navegar_tubo.emit(i.data(Qt.UserRole),a),
                              lambda _: [('Adicionar ponto de conexão',self.adicionar)])
        self.vinculos=QListWidget()
        v.addWidget(aviso('Pontos de conexão escolhidos'))
        v.addWidget(self.vinculos,1)
        if not candidato:
            self.remover_b=QPushButton('Remover ponto de conexão')
            self.remover_b.clicked.connect(self.remover)
            v.addWidget(self.remover_b)
            self.editar_posicao_b=QPushButton('Alterar posição da conexão')
            self.editar_posicao_b.clicked.connect(self.editar_posicao)
            avancado.addWidget(self.editar_posicao_b)
            self.vinculos.currentItemChanged.connect(self.atualizar_acoes)
        navegar_registros(self.vinculos,lambda i,a:self.navegar_tubo.emit(i.data(Qt.UserRole)[0],a),
                          (lambda _: [('Remover ponto de conexão',self.remover)]) if not candidato else None)
        self.info=aviso()
        v.addWidget(self.info)
        self.botoes=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        self.botoes.accepted.connect(self.validar)
        self.botoes.rejected.connect(self.reject)
        v.addWidget(self.botoes)
        self.listar_tubos()
        self.listar_portas()

    def configurar_exclusao(self,excluir):
        acao=self.botoes.addButton('Excluir elemento complementar…',QDialogButtonBox.ActionRole)
        acao.clicked.connect(lambda: self.reject() if excluir() else None)

    def atualizar_acoes(self,*_):
        if self.candidato:return
        acao_disponivel(self.adicionar_b,'' if self.disponiveis.currentItem() else
                        'Selecione uma tubulação na lista ou no mapa.')
        motivo='' if self.vinculos.currentItem() else 'Selecione um dos pontos de conexão escolhidos.'
        acao_disponivel(self.remover_b,motivo)
        acao_disponivel(self.editar_posicao_b,motivo)

    def listar_tubos(self):
        from itertools import islice
        termo=self.busca.text().strip().casefold()
        self.disponiveis.clear()
        for t in islice((t for t in self.tubos.values() if termo in (_nome(t)+' '+t['uid']).casefold()),200):
            item=QListWidgetItem(_nome(t))
            item.setData(Qt.UserRole,t['uid'])
            self.disponiveis.addItem(item)
        self.atualizar_acoes()

    def listar_portas(self):
        self.vinculos.clear()
        for uid,pos in self.portas:
            t=self.tubos.get(uid)
            item=QListWidgetItem((_nome(t) if t else uid+' · referência ausente')+f' — {100*pos:g}%')
            item.setData(Qt.UserRole,(uid,pos))
            self.vinculos.addItem(item)
        self.atualizar_acoes()

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
            self.info.setText(f'Selecione pelo menos {minimo} ponto(s) de conexão válido(s).')
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
                if self.antes_salvar(self.dados) is False:return
            except (ValueError, OSError, RuntimeError, ErroBanco) as erro:
                self.info.setText(str(erro))
                return
        self.accept()
