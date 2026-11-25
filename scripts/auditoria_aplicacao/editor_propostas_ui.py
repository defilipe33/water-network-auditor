"""Editor cartográfico de traçado e ligações de uma tubulação complementar."""

from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                                QHBoxLayout, QLineEdit, QListWidget, QVBoxLayout)
from qgis.core import QgsCoordinateReferenceSystem, QgsGeometry, QgsPointXY

from .modelo_gis_ui import aviso, botao
from .mapa_topologia_gis import escolher, fracao_clicada
from .persistencia_grafo_gis import SITUACOES
from .tubulacoes_propostas import UNIDADES_DIAMETRO, posicao, validar


class EditorProposta(QDialog):
    def __init__(self, pagina, tubos, crs, indice, anterior=None):
        super().__init__(pagina)
        self.pagina, self.tubos, self.indice = pagina, {t['uid']:t for t in tubos}, indice
        self.crs = QgsCoordinateReferenceSystem(crs)
        self.anterior = anterior or {}
        if self.anterior and QgsCoordinateReferenceSystem(self.anterior['crs'])!=self.crs:
            raise ValueError('Use o CRS em que o traçado foi registrado para revisar este elemento.')
        self.portas = [tuple(p) for p in self.anterior.get('portas',())]
        self.bends = list(self.anterior.get('vertices',())[1:-1])
        self.setWindowTitle('Tubulação complementar')
        v = QVBoxLayout(self)
        self.info = aviso()
        v.addWidget(self.info)
        botao(v,'Escolher saída e chegada no mapa',self.escolher_portas)
        self.vertices = QListWidget()
        self.vertices.setMaximumHeight(120)
        v.addWidget(self.vertices)
        a = QHBoxLayout()
        v.addLayout(a)
        botao(a,'Adicionar bends',lambda:self.editar_mapa())
        botao(a,'Mover selecionado',lambda:self.editar_mapa(self.vertices.currentRow()))
        botao(a,'Remover selecionado',self.remover_vertice)
        botao(a,'Desfazer último',self.desfazer)
        self.snap = QCheckBox('Usar o ajuste a feições configurado no QGIS para os bends')
        v.addWidget(self.snap)
        f = QFormLayout()
        v.addLayout(f)
        self.nome = QLineEdit(self.anterior.get('nome',''))
        self.diametro = QLineEdit(str(self.anterior.get('diametro') or ''))
        self.unidade = QComboBox()
        self.unidade.addItems(list(UNIDADES_DIAMETRO))
        self.unidade.setCurrentText(self.anterior.get('unidade_diametro') or 'mm')
        self.material = QLineEdit(self.anterior.get('material') or '')
        self.rede = QComboBox()
        for rotulo,id_ in (('Não informado',None),('Distribuição','DISTRIBUICAO'),('Adução','ADUCAO'),
                           ('Complementar','COMPLEMENTAR'),('Outra','OUTRA')):
            self.rede.addItem(rotulo,id_)
        self.rede.setCurrentIndex(max(0,self.rede.findData(self.anterior.get('classificacao'))))
        self.natureza = QComboBox()
        for k in ('PROPOSTA','HIPOTETICA','INFORMADA','A_CONFIRMAR'):self.natureza.addItem(SITUACOES[k],k)
        self.natureza.setCurrentIndex(max(0,self.natureza.findData(self.anterior.get('situacao'))))
        self.nota = QLineEdit(self.anterior.get('nota',''))
        for rotulo,campo in (('Nome',self.nome),('Diâmetro',self.diametro),('Unidade',self.unidade),
              ('Material',self.material),('Tipo de rede',self.rede),('Natureza',self.natureza),('Observação',self.nota)):
            f.addRow(rotulo,campo)
        self.participar = QCheckBox('Considerar na hipótese em edição')
        self.participar.setChecked(not anterior or anterior['uuid'] in pagina._selecionados())
        v.addWidget(self.participar)
        caixa = QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        v.addWidget(caixa)
        caixa.accepted.connect(self.salvar)
        caixa.rejected.connect(self.reject)
        self.atualizar()

    def coordenadas(self):
        if len(self.portas)!=2:return []
        (a,fa),(b,fb)=self.portas
        return [posicao(self.tubos[a],fa),*self.bends,posicao(self.tubos[b],fb)]

    def atualizar(self):
        self.vertices.clear()
        self.vertices.addItems([f'{i+1} · {p[0]:.3f}, {p[1]:.3f}' for i,p in enumerate(self.bends)])
        try:
            ps = self.coordenadas()
        except (KeyError,ValueError):
            ps = []
        if ps:
            linha = QgsGeometry.fromPolylineXY([QgsPointXY(*p) for p in ps])
            self.info.setText(f'{linha.length():.2f} m · {len(self.bends)} bends')
            marcadores = QgsGeometry.fromMultiPointXY([QgsPointXY(*p) for p in (ps[0],ps[-1])])
            self.pagina.central.mapa.destacar_investigacao([('vinculo',linha),('evento',marcadores)],self.crs)
        else:
            self.info.setText('Selecione dois pontos de ligação no mapa.')

    def _capturar(self,clique,cancelar,mensagem):
        def mostrar():
            self.atualizar()
            self.show()
            self.raise_()
        def cancelar_e_mostrar():
            cancelar()
            mostrar()
        if self.pagina.iniciar_ferramenta(clique,mostrar,cancelar_e_mostrar):
            self.hide()
            self.pagina._mensagem_captura(mensagem)

    def escolher_portas(self):
        novas = []
        anteriores = list(self.portas)
        def clique(p,sair):
            g,tol = self.pagina._clique_metricas(p,self.crs)
            escolha = escolher(self.pagina,self.indice.consultar(g,tol),
                               lambda e:str(e[2].get('id') or e[1]))
            if escolha is None:return
            _,uid,_,linha=escolha
            porta = (uid,fracao_clicada(linha,g,tol))
            if porta in novas:return
            novas.append(porta)
            if len(novas)==2:
                self.portas=novas
                sair(True)
            else:self.pagina._mensagem_captura('Clique no ponto de chegada. Esc cancela.')
        self._capturar(clique,lambda:setattr(self,'portas',anteriores),'Clique no ponto de saída. Esc cancela.')

    def editar_mapa(self, mover=None):
        if (mover is not None and mover<0) or len(self.portas)!=2:return
        anteriores = list(self.bends)
        def clique(p,sair):
            if self.snap.isChecked():
                ajuste = self.pagina.app.iface.mapCanvas().snappingUtils().snapToMap(p)
                if ajuste.isValid():p=ajuste.point()
            g,_ = self.pagina._clique_metricas(p,self.crs)
            xy = g.asPoint()
            if mover is None:
                self.bends.append([xy.x(),xy.y()])
                self.atualizar()
            else:
                self.bends[mover]=[xy.x(),xy.y()]
                sair(True)
        self._capturar(clique,lambda:setattr(self,'bends',anteriores),
                       'Clique para traçar. Botão direito conclui e Esc cancela.')

    def remover_vertice(self):
        if (i:=self.vertices.currentRow())>=0:
            self.bends.pop(i)
            self.atualizar()

    def desfazer(self):
        if self.bends:
            self.bends.pop()
            self.atualizar()

    def salvar(self):
        try:
            diametro = self.diametro.text().strip()
            dados = dict(self.anterior,nome=self.nome.text().strip(),portas=self.portas,vertices=self.coordenadas(),
                crs=self.crs.toWkt(),situacao=self.natureza.currentData(),material=self.material.text().strip(),
                classificacao=self.rede.currentData(),nota=self.nota.text().strip(),
                habilitado=self.anterior.get('habilitado',True),
                diametro=float(diametro.replace(',','.')) if diametro else None,
                unidade_diametro=self.unidade.currentText())
            validar(dados)
            dados.update(pontos_rede=[dados['vertices'][0],dados['vertices'][-1]],crs_rede=dados['crs'],
                         geometrias_rede={u:self.tubos[u].get('wkb') or bytes(self.tubos[u]['geom'].asWkb()).hex()
                                           for u,_ in self.portas})
            novo = self.pagina._salvar('PIPE',dados,self.anterior)
            self.pagina._atualizar_rascunho_relacao(novo,incluir=self.participar.isChecked())
        except (KeyError,ValueError,OSError,RuntimeError,__import__('sqlite3').Error) as erro:
            self.info.setText(str(erro))
            return
        self.accept()
