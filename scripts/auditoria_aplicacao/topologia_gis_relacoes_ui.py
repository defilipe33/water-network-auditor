"""Edição, participação e histórico do cadastro complementar GIS."""

from qgis.PyQt.QtCore import Qt
from collections import Counter
import sqlite3

from qgis.PyQt.QtWidgets import QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QInputDialog, QLineEdit, QMessageBox, QVBoxLayout

from . import persistencia_grafo_gis as pg
from .mapa_topologia_gis import pontos_portas
from .tabelas_topologia_gis import ACOMPANHAMENTO, TabelaRelacoes
from .modelo_gis_ui import aviso, botao, expansivel
from .navegacao_cartografica import navegar_registros
from .revisao_sequencial_gis import RevisaoSequencialGIS
from .duplicatas_conexoes_ui import DuplicatasConexoesUI


CANDIDATAS = ('CONEXAO_T', 'CRUZAMENTO', 'EXTREMIDADES_PROXIMAS')
VEREDITOS = (('Confirmar e incluir na hipótese','CONFIRMADA',True),
             ('Confirmar sem incluir','CONFIRMADA',False),
             ('Manter separadas','SEPARADA',True),
             ('Necessita investigação','INDETERMINADA',False))


def acompanhamento_padrao(decisao):
    return 'VERIFICADO' if decisao in ('CONFIRMADA','SEPARADA') else 'NECESSITA_CONFIRMACAO'
TIPOS_CONEXAO = {
    'CONEXAO_T':'Conexões em T', 'EXTREMIDADES_PROXIMAS':'Extremidades próximas',
    'CRUZAMENTO':'Cruzamentos ambíguos', 'DECLARADA':'Conexões declaradas',
    'PROPOSTA':'Conexões propostas', 'PIPE':'Tubulações propostas',
    'INCONSISTENTE':'Referências ou geometrias inconsistentes',
}


class RelacoesGIS(RevisaoSequencialGIS,DuplicatasConexoesUI):
    def iniciar_tabela_conexoes(self, layout):
        self.conexoes_b, secao = expansivel(layout,'Conexões e continuidade da rede')
        self.filtro_conexoes = QComboBox()
        secao.addWidget(self.filtro_conexoes)
        self.conexoes_lista = TabelaRelacoes()
        self.conexoes_lista.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.conexoes_lista.colunas(('Considerar / nome','Categoria','Interpretação','Acompanhamento','Pontos','Revisão'))
        self.conexoes_lista.setMaximumHeight(200)
        self.conexoes_lista.itemChanged.connect(self.alterou_participacao)
        self.conexoes_lista.currentCellChanged.connect(lambda *_:self.detalhar_conexao())
        self.conexoes_lista.horizontalHeader().sortIndicatorChanged.connect(lambda *_:self.filtrar_conexoes())
        secao.addWidget(self.conexoes_lista)
        navegar_registros(self.conexoes_lista,self._navegar_conexao,self._menu_conexao,self.central.mapa.limpar)
        faixa = QHBoxLayout()
        secao.addLayout(faixa)
        self._pagina_conexoes = 0
        self._candidatas_tabela = {}
        self.pagina_conexoes_info = aviso()
        self.conexoes_ant = botao(faixa,'‹ Anterior',lambda:self.filtrar_conexoes(-1))
        faixa.addWidget(self.pagina_conexoes_info,1)
        self.conexoes_seg = botao(faixa,'Próxima ›',lambda:self.filtrar_conexoes(1))
        self.filtro_conexoes.currentIndexChanged.connect(lambda *_:self.filtrar_conexoes(0))
        self.conexao_info = aviso()
        secao.addWidget(self.conexao_info)
        botao(secao,'Revisar conexão selecionada…',self.revisar_conexao_tabela)
        botao(secao,'Verificar conexões repetidas…',self.verificar_conexoes_repetidas)
        self.montar_revisao_sequencial(secao)
        secao.addWidget(aviso('Uma conexão direta declara uma ligação. Uma tubulação de interligação cria um Pipe complementar.'))
        self.adicionar_conexao_b = botao(secao,'Adicionar conexão entre tubulações…',lambda:self.editar('CONEXAO'))
        botao(secao,'Criar tubulação de interligação…',self.abrir_editor_proposta)

    def _categoria_conexao(self, r):
        if r['tipo']=='PIPE':
            return 'PIPE'
        if r['tipo']=='EQUIPAMENTO_PENDENTE':
            return 'INCONSISTENTE'
        return (r.get('categoria_candidata') or (r['tipo'] if r['tipo'] in CANDIDATAS else
                'PROPOSTA' if r.get('situacao') in ('PROPOSTA','HIPOTETICA') else 'DECLARADA'))

    def preencher_conexoes(self, relacoes, marcados):
        tabela = self.conexoes_lista
        relacoes={u:self.registros.get(u,r) if r['tipo']=='CONEXAO' else r for u,r in relacoes.items()}
        atual = tabela.currentItem()
        selecionada = atual.data(Qt.UserRole) if atual else None
        filtro = self.filtro_conexoes.currentData()
        self._candidatas_tabela = {r['uid']:r for r in (self.dados or {}).get('diagnosticos',())
                                   if r['tipo'] in CANDIDATAS}
        linhas = []
        for uid,r in relacoes.items():
            if r['tipo'] not in ('CONEXAO','PIPE'):
                continue
            if (r.get('excluido') or r.get('substituida_por')) and uid not in marcados and not self.mostrar_excluidos.isChecked():
                continue
            linhas.append((uid,r))
        linhas.extend((f'candidata:{uid}',r) for uid,r in self._candidatas_tabela.items()
                      if uid not in self._por_candidata)
        falhas = {u for u,estado in (self.dados or {}).get('resolucoes_conexoes',{}).items()
                  if estado=='REFERENCIA_ALTERADA'}
        falhas.update(r['uid'] for r in (self.dados or {}).get('diagnosticos',())
                      if r['tipo']=='EQUIPAMENTO_PENDENTE' and r['uid'] in relacoes)
        contagens = Counter()
        tabela.blockSignals(True)
        tabela.setSortingEnabled(False)
        tabela.clear()
        for uid,r in linhas:
            categoria = 'INCONSISTENTE' if uid in falhas else self._categoria_conexao(r)
            if categoria not in TIPOS_CONEXAO:categoria='INCONSISTENTE'
            contagens[categoria] += 1
            relacao = 'uuid' in r
            titulo = r.get('nome') or uid.split(':')[-1][:10]
            if r.get('excluido'):titulo += ' · excluída'
            if r.get('substituida_por'):titulo += ' · substituída'
            interpretacao = pg.DECISOES.get(r.get('decisao'),'Candidata' if not relacao else '—')
            item = tabela.inserir((titulo,TIPOS_CONEXAO[categoria],interpretacao,
                    ACOMPANHAMENTO.get(r.get('acompanhamento'),'Pendente'),len(r.get('portas',())),
                    r.get('rev','')[:8]),uid)
            item.setData(Qt.UserRole+1,categoria)
            if relacao:
                item.setCheckState(Qt.Checked if uid in marcados else Qt.Unchecked)
                if r.get('excluido') or not r.get('habilitado',True):
                    item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
            else:
                item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
            if selecionada==uid:tabela.setCurrentItem(item)
        tabela.setSortingEnabled(True)
        tabela.blockSignals(False)
        self.filtro_conexoes.blockSignals(True)
        self.filtro_conexoes.clear()
        self.filtro_conexoes.addItem(f'Todas as conexões ({len(linhas)})',None)
        for chave,nome in TIPOS_CONEXAO.items():
            self.filtro_conexoes.addItem(f'{nome} ({contagens[chave]})',chave)
        self.filtro_conexoes.setCurrentIndex(max(0,self.filtro_conexoes.findData(filtro)))
        self.filtro_conexoes.blockSignals(False)
        self.filtrar_conexoes()
        self.detalhar_conexao()

    def filtrar_conexoes(self, delta=None):
        tabela = self.conexoes_lista
        filtro = self.filtro_conexoes.currentData()
        linhas = [i for i in range(tabela.count()) if not filtro or tabela.item(i).data(Qt.UserRole+1)==filtro]
        if delta==0:self._pagina_conexoes=0
        elif delta in (-1,1):self._pagina_conexoes+=delta
        atual = tabela.currentRow()
        if delta is None and atual in linhas:self._pagina_conexoes=linhas.index(atual)//100
        ultima = max(0,(len(linhas)-1)//100)
        self._pagina_conexoes = min(ultima,max(0,self._pagina_conexoes))
        inicio = self._pagina_conexoes*100
        visiveis = set(linhas[inicio:inicio+100])
        for i in range(tabela.count()):tabela.setRowHidden(i,i not in visiveis)
        self.pagina_conexoes_info.setText(f'{self._pagina_conexoes+1}/{ultima+1} · {len(linhas)} conexões')
        self.conexoes_ant.setEnabled(self._pagina_conexoes>0)
        self.conexoes_seg.setEnabled(self._pagina_conexoes<ultima)
        if atual not in visiveis:
            tabela.setCurrentCell(min(visiveis) if visiveis else -1,0)

    def _conexao_da_linha(self, linha):
        item = self.conexoes_lista.item(linha)
        if item:
            uid = item.data(Qt.UserRole)
            return (self._candidatas_tabela.get(uid.split(':',1)[1]) if uid.startswith('candidata:')
                    else self.registros.get(uid) or self._relacao_por_id(uid))

    def _navegar_conexao(self,indice,aproximar):
        if r := self._conexao_da_linha(indice.row()):
            if 'uuid' in r:self.destacar_relacao(aproximar,r,extensao=True)
            else:self.destacar(aproximar=aproximar,registros=[r])

    def detalhar_conexao(self):
        r = self._conexao_da_linha(self.conexoes_lista.currentRow())
        self.conexao_info.setText(self._texto_conexao(r) if r else '')

    def _texto_conexao(self,r):
        textos = [TIPOS_CONEXAO.get(self._categoria_conexao(r),'Conexão')]
        for uid,pos in r.get('portas',()):
            t = getattr(self,'tubos',{}).get(uid,{})
            identificador=t.get('id')
            textos.append(f"{identificador if identificador is not None else uid[:8]} · "
                          f"{t.get('camada') or 'Camada indisponível'} · {pos:.1%}")
        dist = r.get('distancia_m')
        if dist is not None:textos.append(f'Distância geométrica {dist:.3f} m')
        if r.get('motivo'):textos.append(r['motivo'])
        rel=r if r.get('tipo')=='CONEXAO' else self._veredito_atual(r)
        if rel:
            textos.append(f"{pg.DECISOES.get(rel.get('decisao'),'—')} · "
                          f"{ACOMPANHAMENTO.get(rel.get('acompanhamento'),'Pendente')} · revisão {rel['rev'][:8]}")
            textos.append('Marcada no rascunho' if rel['uuid'] in self._selecionados() else 'Fora do rascunho')
        h = self._hip_ativa
        textos.append(f"Hipótese em edição · {h['nome']} · {h['rev'][:8]}" if h else 'Hipótese temporária em edição')
        return '\n'.join(textos)

    def _menu_conexao(self,indice):
        r = self._conexao_da_linha(indice.row())
        if not r:return []
        if 'uuid' in r:
            acoes = self._menu_relacao(indice,tabela=self.conexoes_lista)
            if not r.get('excluido') and r['tipo']=='CONEXAO':
                acoes.insert(0,('Rever interpretação…',lambda:self.conferir_conexao(r)))
            return acoes
        motivo = self._motivo_edicao(None) or ('' if r.get('portas') else 'Pontos de ligação indisponíveis.')
        return [
            ('Conferir conexão…',lambda:self.conferir_conexao(r),motivo),
            *((rotulo+'…',lambda d=d,i=i:self.conferir_conexao(r,(d,i)),motivo) for rotulo,d,i in VEREDITOS),
            ('Editar pontos de ligação…',lambda:self.revisar_conexao(r=r),motivo),
            ('Aproximar e destacar',lambda:self._navegar_conexao(indice,True)),
        ]

    def revisar_conexao_tabela(self):
        if r := self._conexao_da_linha(self.conexoes_lista.currentRow()):
            if r['tipo']=='PIPE':self._editar_relacao(r)
            else:self.conferir_conexao(r)

    def conferir_conexao(self,r,escolha=None):
        try:
            anterior=r if 'uuid' in r else self._registro_da_candidata(r)
        except ValueError as erro:
            self.status.setText(str(erro))
            return
        if motivo := self._motivo_edicao(anterior):
            self.status.setText(motivo)
            return
        if len(r.get('portas',()))<2:
            self.status.setText('Escolha pontos de ligação válidos pelo editor.')
            return
        d = QDialog(self)
        d.setWindowTitle('Conferir conexão')
        v = QVBoxLayout(d)
        v.addWidget(aviso(self._texto_conexao(r)))
        v.addWidget(aviso('Verificada indica que a revisão foi concluída pelo usuário. A conferência em campo tem registro próprio.'))
        tipo=QComboBox()
        for texto,decisao,incluir in VEREDITOS:tipo.addItem(texto,(decisao,incluir))
        tipo.addItem('Manter separadas, sem incluir na hipótese',('SEPARADA',False))
        def indice_veredito(valor):
            return next((i for i in range(tipo.count()) if tipo.itemData(i)==valor),-1)
        if anterior and escolha is None:
            decisao=anterior.get('decisao')
            escolha_atual=(decisao,anterior['uuid'] in self._selecionados())
            i=indice_veredito(escolha_atual)
            if i<0:
                tipo.addItem(pg.DECISOES[decisao],escolha_atual)
                i=tipo.count()-1
            tipo.setCurrentIndex(i)
        elif escolha:tipo.setCurrentIndex(max(0,indice_veredito(escolha)))
        else:tipo.setCurrentIndex(indice_veredito(('INDETERMINADA',False)))
        v.addWidget(tipo)
        nota = QLineEdit((anterior or {}).get('nota',''))
        nota.setPlaceholderText('Observação opcional')
        v.addWidget(nota)
        acompanhamento = QComboBox()
        for valor,rotulo in ACOMPANHAMENTO.items():acompanhamento.addItem(rotulo,valor)
        v.addWidget(acompanhamento)
        def definir_padrao():
            acompanhamento.setCurrentIndex(acompanhamento.findData(acompanhamento_padrao(tipo.currentData()[0])))
        tipo.currentIndexChanged.connect(definir_padrao)
        definir_padrao()
        if anterior and escolha is None and (i:=acompanhamento.findData(anterior.get('acompanhamento')))>=0:
            acompanhamento.setCurrentIndex(i)
        def gravar():
            decisao,incluir=tipo.currentData()
            if self.interpretar_candidata(r,decisao,incluir=incluir,nota=nota.text().strip(),
                                         acompanhamento=acompanhamento.currentData()):
                d.accept()
        botao(v,'Salvar decisão',gravar)
        botao(v,'Voltar',d.reject)
        d.exec_()

    def _motivo_edicao(self,r):
        if self.central.ocupado():
            return 'Aguarde a conclusão da atividade atual.'
        if self._editor is not None:
            return 'Conclua a edição que já está aberta.'
        if r and r.get('excluido'):
            return 'Recupere o complemento antes de editá-lo.'
        if r and r.get('substituida_por'):
            return 'Esta relação foi substituída. Consulte a relação principal.'
        if r and (atual:=self.registros.get(r['uuid'])) and atual['rev']!=r['rev']:
            return 'Use a revisão mais recente no rascunho antes de editar este registro histórico.'
        return ''

    def _relacao_na_linha(self,indice,tabela=None):
        i=(self.participantes if tabela is None else tabela).item(indice.row(),0)
        return self._relacao_por_id(i.data(Qt.UserRole)) if i else None

    def _relacao_por_id(self,uid):
        return self._pinos.get(uid,self.registros.get(uid))

    def _editar_relacao(self,r):
        motivo=self._motivo_edicao(r)
        if motivo:
            self.status.setText(motivo)
        elif r['tipo']=='PIPE':
            self.abrir_editor_proposta(anterior=r)
        else:
            self.editar(r['tipo'],r,candidato=self._candidato_da_relacao(r))

    def abrir_editor_proposta(self,_checked=False,*,anterior=None):
        if motivo := self._motivo_edicao(anterior):
            self.status.setText(motivo)
            return
        from .editor_propostas_ui import EditorProposta
        def pronto(inventario):
            tubos,_,crs,indices = inventario
            dlg = EditorProposta(self,tubos,crs,indices[0],anterior)
            self._editor=dlg
            def terminou(_):
                self._editor=None
                self.cancelar_captura(reabrir=False)
                self.central.mapa.limpar()
                self._atualizar_acoes()
                dlg.deleteLater()
            dlg.finished.connect(terminou)
            dlg.show()
        self._inventario_para_editar(pronto)

    def _menu_relacao(self,indice,tabela=None):
        r=self._relacao_na_linha(indice,tabela)
        if not r:return ()
        uid=r['uuid']
        fonte=r['tipo']=='ORIGEM'
        ativo=uid in self._selecionados()
        edicao=self._motivo_edicao(r)
        opcoes=[
            ('Enquadrar fonte e tubulações' if fonte else 'Enquadrar toda a extensão',
             lambda:self.destacar_relacao(True,r,extensao=True)),
            ('Editar fonte e ligações…' if fonte else 'Editar traçado…' if r['tipo']=='PIPE' else 'Editar conexão…',
             lambda:self._editar_relacao(r),edicao),
        ]
        if r.get('excluido'):
            indisponivel='Aguarde a atividade atual.' if self.central.ocupado() else ''
            opcoes.append(('Recuperar complemento',lambda:self.excluir_relacao(r,False),indisponivel))
        else:
            opcoes.append(('Retirar da hipótese em edição' if ativo else 'Incluir na hipótese em edição',
                           lambda:self._marcar_relacao(uid,not ativo),
                           '' if ativo else self._motivo_participacao(r)))
            if not fonte:opcoes.append(('Alterar disponibilidade no cadastro',lambda:self.alternar_elemento(r),edicao))
            if pg.complemento_editavel(r):
                opcoes.append(('Excluir elemento complementar…',lambda:self.excluir_relacao(r),edicao))
        opcoes.extend([None,('Alterar acompanhamento…',lambda:self.acompanhar_relacao(r),edicao),
                       ('Consultar histórico',lambda:self._mostrar_historico(uid))])
        return opcoes

    def _motivo_participacao(self,r):
        if r.get('excluido') or not r.get('habilitado',True):
            return 'Recupere ou habilite o complemento para incluí-lo.'
        atual=self.registros.get(r['uuid'],r)
        if atual.get('substituida_por'):
            return 'A relação foi substituída. Consulte a relação principal.'
        if atual.get('excluido'):
            return 'O complemento foi excluído. Esta revisão continua disponível na hipótese histórica.'
        return ''

    def _marcar_relacao(self,uid,incluir):
        if self.central.ocupado():return
        r=self._relacao_por_id(uid)
        if r is None:return
        motivo=self._motivo_participacao(r) if incluir else ''
        if motivo:
            self.status.setText(motivo)
            return
        for tabela in (self.participantes,self.conexoes_lista):
            for i in range(tabela.count()):
                item=tabela.item(i)
                if item.data(Qt.UserRole)==uid:
                    item.setCheckState(Qt.Checked if incluir else Qt.Unchecked)
                    return

    def excluir_relacao(self,r,excluir=True):
        atual=self.registros.get(r['uuid'])
        if self.central.ocupado() or atual is None:return False
        if not pg.complemento_editavel(atual):
            self.status.setText('A origem cadastrada no GIS pode ser retirada da hipótese.')
            return False
        if atual['rev']!=r['rev']:
            self.status.setText('Selecione a revisão atual para alterar a exclusão.')
            return False
        uid=r['uuid']
        if excluir:
            hipoteses={}
            for h in self._historicas:
                if h['tipo']=='HIPOTESE' and uid in set(h.get('vinculos',{})) | set(h.get('selecionados',())):
                    hipoteses[h['nome']]=hipoteses.get(h['nome'],0)+1
            nomes='\n'.join(f'• {n} ({q} revisão/ões)' for n,q in sorted(hipoteses.items()))
            nome=r.get('nome') or r.get('categoria') or uid[:8]
            texto=(f'Excluir do cadastro em uso: {nome}?\n\n'
                   'Hipóteses salvas que referenciam este complemento:\n'+(nomes or 'Nenhuma.')+
                   '\n\nOs pontos vinculados às tubulações ficam no histórico. '
                   'As tubulações, outras relações e as execuções anteriores permanecem intactas. '
                   'O rascunho atual perderá esta participação. Se necessário, grave uma nova revisão da hipótese.')
            confirmou=QMessageBox.question(self,'Excluir elemento complementar',texto,
                                            QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)
            if confirmou!=QMessageBox.Yes:return False
        novo=self._com_erro(lambda:pg.alterar_exclusao(self._base_complementos(),self.uid_projeto,atual,excluir))
        if novo is None:return False
        self._pinos.pop(uid,None)
        self._resultado_historico=False
        self.atualizar_complementos(escolhidos=set(self._selecionados())-{uid})
        self.status.setText('Complemento excluído do cadastro em uso. Histórico preservado.' if excluir else
                            'Complemento recuperado. Inclua-o na hipótese em edição quando necessário.')
        return True

    def _registro_da_candidata(self,r):
        antigos=self._por_candidata.get(r['uid'],())
        if len(antigos)>1:
            raise ValueError('Há mais de uma relação para esta candidata. Escolha a revisão pela tabela de fontes e conexões.')
        return antigos[0] if antigos else None

    def _veredito_atual(self,r):
        rs=self._por_candidata.get(r['uid'],())
        return rs[0] if len(rs)==1 else None

    def _interpretacao_atual(self,r):
        if r.get('tipo') in CANDIDATAS:
            try:relacao=self._registro_da_candidata(r)
            except ValueError:return 'Múltiplas interpretações'
            if relacao:
                return pg.DECISOES[relacao['decisao']]
        estado=r['situacao']
        return pg.DECISOES.get(estado,estado.replace('_',' ').capitalize())

    def interpretar_candidata(self,r,decisao,*,incluir=None,nota=None,acompanhamento=None):
        def salvar():
            if r.get('tipo') not in (*CANDIDATAS,'CONEXAO') or len(r.get('portas',()))<2:
                raise ValueError('Selecione uma candidata com pontos de ligação definidos.')
            anterior=r if r['tipo']=='CONEXAO' else self._registro_da_candidata(r)
            motivo=self._motivo_edicao(anterior)
            if motivo:raise ValueError(motivo)
            if incluir and anterior and (motivo:=self._motivo_participacao(anterior)):
                raise ValueError(motivo)
            dados=dict(anterior or {})
            if r['tipo'] in CANDIDATAS:
                crs=self.dados['crs']
                dados.update(portas=r['portas'],pontos_rede=pontos_portas(r['portas'],self.tubos),
                    candidato=r['uid'],categoria_candidata=r['tipo'],wkb=r.get('wkb'),crs=crs,crs_rede=crs)
            dados.update(decisao=decisao,situacao=dados.get('situacao','INFORMADA'),
                         acompanhamento=acompanhamento or acompanhamento_padrao(decisao),
                         contexto_veredito=dict(execucao=(self.dados or {}).get('uuid'),
                             hipotese_rev=(self._hip_ativa or {}).get('rev'),incluir=incluir))
            if nota is not None:dados['nota']=nota
            ant=anterior or {}
            novo=pg.salvar_revisao(self._base_complementos(True),self.uid_projeto,'CONEXAO',dados,
                                  ant.get('uuid'),ant.get('rev'))
            try:
                self._atualizar_rascunho_relacao(novo,incluir=incluir)
                self.guardar_rascunho()
            except (ValueError,OSError,RuntimeError,sqlite3.Error) as erro:
                raise ValueError(f"Revisão {novo['rev'][:8]} persistida. A atualização do rascunho requer atenção. {erro}") from erro
            incluido=novo['uuid'] in self._selecionados()
            self.status.setText(f"{pg.DECISOES[decisao]} · {ACOMPANHAMENTO[novo['acompanhamento']]} · "
                f"revisão {novo['rev'][:8]}"+(' · incluída no rascunho. Reexecute para aplicar.' if incluido else
                ' · fora da hipótese em edição.'))
            return True
        return self._com_erro(salvar)

    def acompanhar_relacao(self,r):
        motivo=self._motivo_edicao(r)
        if motivo:
            self.status.setText(motivo)
            return
        estados=list(ACOMPANHAMENTO)
        atual=r.get('acompanhamento','PENDENTE')
        rotulos=list(ACOMPANHAMENTO.values())
        rotulo,ok=QInputDialog.getItem(self,'Acompanhamento','Situação',rotulos,estados.index(atual),False)
        if ok:
            def salvar():
                novo=self._salvar(r['tipo'],dict(r,acompanhamento=estados[rotulos.index(rotulo)]),r)
                self._atualizar_rascunho_relacao(novo)
            self._com_erro(salvar)

    def _atualizar_rascunho_relacao(self,novo,*,incluir=None):
        marcados=set(self._selecionados())
        if incluir is True and not self._motivo_participacao(novo):marcados.add(novo['uuid'])
        elif incluir is False:
            marcados.discard(novo['uuid'])
            self._pinos.pop(novo['uuid'],None)
        if novo['uuid'] in marcados:self._pinos[novo['uuid']]=novo
        self._resultado_historico=False
        self.atualizar_complementos(escolhidos=marcados)
        if self.dados:self.mudar_resultados(preservar=True)
