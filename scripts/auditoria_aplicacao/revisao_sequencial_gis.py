"""Fila de revisão das candidatas da fotografia de conectividade."""

from collections import Counter

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLineEdit

from .investigacao_gis import geometria
from . import estado_projeto as estado
from .modelo_gis_ui import aviso, botao, expansivel, formulario
from .navegacao_cartografica import acao_disponivel


CATEGORIAS=('CONEXAO_T','EXTREMIDADES_PROXIMAS','CRUZAMENTO')
ACOES=(('Confirmar e incluir','CONFIRMADA',True),
       ('Confirmar sem incluir','CONFIRMADA',False),
       ('Manter separadas','SEPARADA',True),
       ('Necessita investigação','INDETERMINADA',False))


def selecionar(diagnosticos, decisoes, *, tipo=None, pendentes=False, ids=None, entradas=None, area=None):
    return [r['uid'] for r in diagnosticos
            if r['tipo'] in CATEGORIAS and (not tipo or r['tipo']==tipo)
            and (ids is None or r['uid'] in ids)
            and (not pendentes or decisoes.get(r['uid']) not in ('CONFIRMADA','SEPARADA'))
            and (entradas is None or entradas.intersection(r.get('tubos',())))
            and (area is None or ((g:=geometria(r.get('wkb'))) and area.intersects(g)))]


class RevisaoSequencialGIS:
    def montar_revisao_sequencial(self,layout):
        self._fila_conexoes=[]
        self._posicao_conexoes=0
        self._uid_fila=None
        self._rascunho_seq=None
        self.revisao_seq_b,v=expansivel(layout,'Revisar conexões em sequência')
        self.revisao_seq_b.toggled.connect(self._abrir_revisao_seq)
        f=formulario(v)
        self.seq_tipo=QComboBox()
        self.seq_tipo.addItem('Todas as candidatas',None)
        for k,n in zip(CATEGORIAS,('Conexões em T','Extremidades próximas','Cruzamentos ambíguos')):
            self.seq_tipo.addItem(n,k)
        f.addRow('Categoria',self.seq_tipo)
        self.seq_componente=QComboBox()
        self.seq_area=QComboBox()
        f.addRow('Componente',self.seq_componente)
        f.addRow('Área GIS',self.seq_area)
        self.seq_pendentes=QCheckBox('Somente pendentes ou indeterminadas')
        self.seq_pendentes.setChecked(True)
        self.seq_selecao=QCheckBox('Somente candidatas selecionadas nas tabelas')
        v.addWidget(self.seq_pendentes)
        v.addWidget(self.seq_selecao)
        botao(v,'Iniciar nova fila',self.iniciar_revisao_sequencial)
        self.seq_retomar_b=botao(v,'Retomar revisão salva',self.retomar_revisao_sequencial)
        self.seq_progresso=aviso()
        self.seq_detalhe=aviso()
        v.addWidget(self.seq_progresso)
        v.addWidget(self.seq_detalhe)
        self.seq_nota=QLineEdit()
        self.seq_nota.setPlaceholderText('Observação opcional para esta decisão')
        v.addWidget(self.seq_nota)
        self.seq_acoes=[]
        for texto,decisao,incluir in ACOES:
            self.seq_acoes.append(botao(v,texto,lambda _,d=decisao,i=incluir:self.decidir_sequencia(d,i)))
        nav=QHBoxLayout()
        v.addLayout(nav)
        self.seq_voltar=botao(nav,'‹ Voltar',lambda:self.mover_revisao(-1))
        self.seq_avancar=botao(nav,'Próxima ›',lambda:self.mover_revisao(1))
        self.seq_pular=botao(v,'Pular por enquanto',lambda:self.mover_revisao(1))
        self.seq_encerrar=botao(v,'Encerrar revisão',lambda:self.revisao_seq_b.setChecked(False))

    def _abrir_revisao_seq(self,aberta):
        if not aberta or not self.dados:return
        if self._uid_fila!=self.dados['uuid']:
            self._fila_conexoes=[]
            self._posicao_conexoes=0
            self._uid_fila=self.dados['uuid']
            self._rascunho_seq=None
        for combo,titulo,registros in (
            (self.seq_componente,'Todos os componentes',self.dados['componentes']),
            (self.seq_area,'Todas as áreas',self.dados.get('areas',()))):
            preferido=combo.currentData()
            combo.clear()
            combo.addItem(titulo,None)
            for r in registros:
                nome=str(r.get('nome') or r.get('label') or r.get('id') or r['uid'][:10])
                combo.addItem(nome,r['uid'])
            combo.setCurrentIndex(max(0,combo.findData(preferido)))
        self._exibir_seq(False)

    def _estado_revisao_seq(self):
        return self.central.estados_de_visualizacao().get(f"TOPOLOGIA_GIS:{self.dados['uuid']}",{}).get('revisao_conexoes')

    def _salvar_revisao_seq(self):
        self.central._guardar_visual(self._projeto(),'TOPOLOGIA_GIS',self.dados['uuid'],estrito=True,visual={
            'revisao_conexoes':dict(fila=self._fila_conexoes,posicao=self._posicao_conexoes,rascunho=self._rascunho_seq)})

    def _decisoes_seq(self):
        return {u:rs[0]['decisao'] for u,rs in self._por_candidata.items() if len(rs)==1}

    def iniciar_revisao_sequencial(self):
        if not self.dados or self.central.ocupado():return
        ids=None
        if self.seq_selecao.isChecked():
            ids={r['uid'] for i in self.resultados.selectedIndexes()
                 if (r:=self._registro_resultado(i)) and r['tipo'] in CATEGORIAS}
            ids.update(r.get('candidato') or r.get('uid') for i in self.conexoes_lista.selectedIndexes()
                       if (r:=self._conexao_da_linha(i.row())))
        grupo=self.componentes.get(self.seq_componente.currentData())
        zona=next((a for a in self.dados.get('areas',()) if a['uid']==self.seq_area.currentData()),None)
        area=geometria(zona.get('wkb')) if zona else None
        if zona and area is None:
            self.seq_progresso.setText('A área selecionada está sem geometria.')
            return
        self._fila_conexoes=selecionar(self.dados['diagnosticos'],self._decisoes_seq(),
            tipo=self.seq_tipo.currentData(),pendentes=self.seq_pendentes.isChecked(),ids=ids,
            entradas=set(grupo['tubos']) if grupo else None,area=area)
        self._posicao_conexoes=0
        self._rascunho_seq=None
        self._com_erro(self._salvar_revisao_seq)
        self._exibir_seq(True)

    def retomar_revisao_sequencial(self):
        if not self.dados or self.central.ocupado():return
        salvo=self._estado_revisao_seq()
        if not salvo:return
        data=salvo.get('rascunho')
        if data and getattr(self,'_rascunho_restaurado',None)!=data:
            def recuperar_participacao():
                d=estado.ler(self.app.catalogo.raiz,self._projeto(),estado.RASCUNHO)
                if d.get('data')==data and self.resolver_edicao():self._restaurar_rascunho(d)
            self._com_erro(recuperar_participacao)
        self._rascunho_seq=data
        self._fila_conexoes=[u for u in salvo['fila'] if u in self._candidatas_tabela]
        self._posicao_conexoes=max(0,min(salvo['posicao'],len(self._fila_conexoes)))
        self._exibir_seq(True)

    def _candidata_seq(self):
        pos=self._posicao_conexoes
        return self._candidatas_tabela.get(self._fila_conexoes[pos]) if pos<len(self._fila_conexoes) else None

    def _exibir_seq(self,aproximar):
        n=len(self._fila_conexoes)
        pos=self._posicao_conexoes
        r=self._candidata_seq()
        decisoes=self._decisoes_seq()
        c=Counter(decisoes.get(u) for u in self._fila_conexoes)
        revisadas=c['CONFIRMADA']+c['SEPARADA']+c['INDETERMINADA']
        texto=f'Conexão {pos+1} de {n}' if r else 'Fim da fila' if n else 'Nenhuma candidata na fila'
        self.seq_progresso.setText(f'{texto} · {revisadas} revisadas ({c["CONFIRMADA"]} confirmadas, '
                                  f'{c["SEPARADA"]} separadas, {c["INDETERMINADA"]} indeterminadas)')
        self.seq_detalhe.setText(self._texto_conexao(r) if r else '')
        antigas=self._por_candidata.get(r['uid'],()) if r else ()
        self.seq_nota.setText(antigas[0].get('nota','') if len(antigas)==1 else '')
        self.seq_nota.setEnabled(bool(r))
        for botao_ in self.seq_acoes:
            acao_disponivel(botao_,'' if r and r.get('portas') and len(antigas)<=1 else
                           'A candidata não possui pontos editáveis ou tem múltiplas interpretações.')
        self.seq_voltar.setEnabled(pos>0)
        self.seq_avancar.setEnabled(bool(r))
        self.seq_pular.setEnabled(bool(r))
        self.seq_retomar_b.setEnabled(bool((self._estado_revisao_seq() or {}).get('fila')))
        if r and aproximar:self.destacar(aproximar=True,registros=[r],toda_extensao=False)

    def mover_revisao(self,delta):
        if self.central.ocupado() or self._uid_fila!=(self.dados or {}).get('uuid'):return
        self._posicao_conexoes=max(0,min(self._posicao_conexoes+delta,len(self._fila_conexoes)))
        self._com_erro(self._salvar_revisao_seq)
        self._exibir_seq(True)

    def decidir_sequencia(self,decisao,incluir):
        r=self._candidata_seq()
        if not r or self._uid_fila!=(self.dados or {}).get('uuid'):return
        if self.interpretar_candidata(r,decisao,incluir=incluir,nota=self.seq_nota.text().strip()):
            if self._com_erro(self.guardar_rascunho):self._rascunho_seq=self._rascunho_restaurado
            self.mover_revisao(1)
