"""Edição, participação e histórico do cadastro complementar GIS."""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QInputDialog, QMessageBox

from . import persistencia_grafo_gis as pg
from .mapa_topologia_gis import pontos_portas
from .tabelas_topologia_gis import ACOMPANHAMENTO


CANDIDATAS = ('CONEXAO_T', 'CRUZAMENTO', 'EXTREMIDADES_PROXIMAS')


class RelacoesGIS:
    def _motivo_edicao(self,r):
        if self.central.ocupado():
            return 'Aguarde a conclusão da atividade atual.'
        if self._editor is not None:
            return 'Conclua a edição que já está aberta.'
        if r and r.get('excluido'):
            return 'Recupere o complemento antes de editá-lo.'
        if r and (atual:=self.registros.get(r['uuid'])) and atual['rev']!=r['rev']:
            return 'Use a revisão mais recente no rascunho antes de editar este registro histórico.'
        return ''

    def _relacao_na_linha(self,indice):
        i=self.participantes.item(indice.row(),0)
        return self._relacao_por_id(i.data(Qt.UserRole)) if i else None

    def _relacao_por_id(self,uid):
        return self._pinos.get(uid,self.registros.get(uid))

    def _editar_relacao(self,r):
        motivo=self._motivo_edicao(r)
        if motivo:
            self.status.setText(motivo)
        else:
            self.editar(r['tipo'],r,candidato=self._candidato_da_relacao(r))

    def _menu_relacao(self,indice):
        r=self._relacao_na_linha(indice)
        if not r:return ()
        uid=r['uuid']
        fonte=r['tipo']=='ORIGEM'
        ativo=uid in self._selecionados()
        edicao=self._motivo_edicao(r)
        opcoes=[
            ('Enquadrar fonte e tubulações' if fonte else 'Enquadrar toda a extensão',
             lambda:self.destacar_relacao(True,r,extensao=True)),
            ('Editar fonte e ligações…' if fonte else 'Editar conexão…',lambda:self._editar_relacao(r),edicao),
        ]
        if r.get('excluido'):
            indisponivel='Aguarde a atividade atual.' if self.central.ocupado() else ''
            opcoes.append(('Recuperar complemento',lambda:self.excluir_relacao(r,False),indisponivel))
        else:
            opcoes.append(('Retirar da hipótese em edição' if ativo else 'Incluir na hipótese em edição',
                           lambda:self._marcar_relacao(uid,not ativo),
                           '' if ativo else self._motivo_participacao(r)))
            if pg.complemento_editavel(r):
                opcoes.append(('Excluir elemento complementar…',lambda:self.excluir_relacao(r),edicao))
        opcoes.extend([None,('Alterar acompanhamento…',lambda:self.acompanhar_relacao(r),edicao),
                       ('Consultar histórico',lambda:self._mostrar_historico(uid))])
        return opcoes

    def _motivo_participacao(self,r):
        if r.get('excluido') or not r.get('habilitado',True):
            return 'Recupere ou habilite o complemento para incluí-lo.'
        atual=self.registros.get(r['uuid'],r)
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
        for i in range(self.participantes.count()):
            item=self.participantes.item(i)
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

    def _interpretacao_atual(self,r):
        if not self._resultado_historico and r.get('tipo') in CANDIDATAS:
            try:relacao=self._registro_da_candidata(r)
            except ValueError:return 'Múltiplas interpretações'
            if relacao:
                return pg.DECISOES[relacao['decisao']]+(' · em edição' if relacao.get('rev')!=r.get('revisao') else '')
        estado=r['situacao']
        return pg.DECISOES.get(estado,estado.replace('_',' ').capitalize())

    def interpretar_candidata(self,r,decisao):
        def salvar():
            if r.get('tipo') not in CANDIDATAS or not r.get('portas'):
                raise ValueError('Selecione uma candidata com pontos de ligação definidos.')
            anterior=self._registro_da_candidata(r)
            motivo=self._motivo_edicao(anterior)
            if motivo:raise ValueError(motivo)
            crs=self.dados['crs']
            dados=dict(anterior or {}, nome=(anterior or {}).get('nome',''),
                       portas=r['portas'], pontos_rede=pontos_portas(r['portas'],self.tubos),
                       candidato=r['uid'], categoria_candidata=r['tipo'], wkb=r.get('wkb'),
                       crs=crs, crs_rede=crs, situacao=(anterior or {}).get('situacao','INFORMADA'),
                       decisao=decisao)
            novo=self._salvar('CONEXAO',dados,anterior)
            self._atualizar_rascunho_relacao(novo)
            incluido=novo['uuid'] in self._selecionados()
            self.status.setText(pg.DECISOES[decisao]+(' · incluída no rascunho. Reexecute para aplicar.' if incluido else
                ' · fora da hipótese em edição. Inclua a relação na tabela de fontes e conexões para reexecutar.'))
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

    def _atualizar_rascunho_relacao(self,novo):
        marcados=self._selecionados()
        if novo['uuid'] in marcados:self._pinos[novo['uuid']]=novo
        self._resultado_historico=False
        self.atualizar_complementos(escolhidos=marcados)
        if self.dados:self.mudar_resultados(preservar=True)
