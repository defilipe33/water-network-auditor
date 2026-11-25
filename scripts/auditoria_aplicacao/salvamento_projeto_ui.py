"""Salvamento explícito do projeto e proteção das edições em andamento."""

from pathlib import Path
from copy import deepcopy
import sqlite3

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from . import estado_projeto as estado
from .manifesto_projeto import nome_arquivo
from .trabalhos_projeto import agora


class SalvamentoProjetoUI:
    def _topologia_do_projeto(self):
        pagina = self.__dict__.get('conectividade_gis')
        if pagina is not None and pagina.uid_projeto == self.projetos.dados['ativo']:
            return pagina

    def _editor_exige_decisao(self):
        topo = self._topologia_do_projeto()
        if topo and topo._editor is not None:
            return 'Conclua ou cancele o editor de origens ou conexões antes de salvar o projeto.'
        return ''

    def _outras_pendencias(self):
        from qgis.PyQt import sip
        analise = self.__dict__.get('analise_gis')
        if analise is not None and analise.pendente():
            return 'Há uma decisão em edição na auditoria GIS. Salve-a ou descarte-a na auditoria.'
        painel = self.app.painel
        if painel is not None and not sip.isdeleted(painel) and painel.tem_edicoes():
            return 'Conclua as edições na investigação integrada antes de salvar o projeto.'
        wg = self.app.wg
        if wg is not None and not sip.isdeleted(wg) and (wg._ref_pendente or wg.fonte and not wg.base):
            return 'Conclua a preparação da base WaterGEMS antes de salvar o projeto.'
        if self.app.geo.pendente():
            return 'Conclua a configuração da auditoria geométrica antes de salvar o projeto.'
        return ''

    def _pendencias_projeto(self):
        topo = self._topologia_do_projeto()
        return (self.modelo_gis.pendente() or bool(self._editor_exige_decisao())
                or bool(topo and topo.edicao_pendente()))

    def _atualizar_salvamento(self):
        p = self.projetos.atual()
        salvo = (p or {}).get('sessao_wna', {})
        if not p:
            texto = 'Selecione um projeto'
        elif self._pendencias_projeto() or self._outras_pendencias() or self._falha_salvar == p['uuid']:
            texto = 'Alterações não salvas'
        elif salvo:
            texto = 'Salvo · ' + salvo['data'][:19].replace('T', ' ') + ' UTC'
        else:
            texto = 'Projeto .wna' if p.get('manifesto_wna') else 'Projeto no índice local'
        caminho = (p or {}).get('manifesto_wna')
        self.estado_salvar.setText(texto + (' · '+Path(caminho).name if caminho else ''))
        self.estado_salvar.setToolTip(caminho or texto)
        self.salvar_projeto_b.setEnabled(bool(p))
        if p:
            raiz=self.app.catalogo.raiz
            arq=estado.arquivo(raiz,p,estado.RASCUNHO)
            chave=(p['uuid'],arq,self.marca(arq))
            if chave!=getattr(self,'_chave_rascunho_cabecalho',None):
                try:self._ha_rascunho=bool(estado.ler(raiz,p,estado.RASCUNHO))
                except (OSError,ValueError,TypeError):self._ha_rascunho=False
                self._chave_rascunho_cabecalho=chave
        self.abrir_rascunho_b.setVisible(bool(p and self._ha_rascunho))

    def _validar_referencias_salvamento(self, p):
        faltam = [r['base'] for r in p['bases'] if not Path(r['base']).is_file()]
        if faltam:
            raise ValueError('Arquivo de resultado ausente. Localize em Meus trabalhos. '+faltam[0])
        if arq := p.get('arquivo_complementos'):
            from .persistencia_grafo_gis import identidade
            identidade(arq, p['uuid'])

    def salvar_projeto(self, _checked=False):
        p = self.projetos.atual()
        if not p:
            self.receber_mapa('Crie ou abra um projeto para salvá-lo.')
            return False
        if self.ocupado():
            self.receber_mapa('Aguarde a atividade ou cancele-a para salvar o projeto.')
            return False
        if aviso := self._editor_exige_decisao() or self._outras_pendencias():
            self.receber_mapa(aviso)
            return False
        topo = self._topologia_do_projeto()
        arq = p.get('manifesto_wna')
        migrando = not arq
        if migrando:
            arq,_ = QFileDialog.getSaveFileName(self, 'Escolher local para o arquivo .wna do projeto',
                    str(Path(self.app.catalogo.raiz)/(nome_arquivo(p['nome'])+'.wna')),
                    'Projeto Water Network Auditor (*.wna)')
            if not arq:
                return False
            arq = str(Path(arq).resolve().with_suffix('.wna'))
        try:
            self._validar_referencias_salvamento(p)
            if self.modelo_gis.pendente() and not self.modelo_gis.salvar():
                raise ValueError('Conclua as pendências no Modelo GIS. '+self.modelo_gis.feedback.text())
            # A gravação do Modelo GIS pode substituir o objeto do projeto.
            p = self.projetos.atual()
            if topo and topo.edicao_pendente():
                topo.guardar_rascunho()
            self.salvar_estado_atual(estrito=True)
            raiz = self.app.catalogo.raiz
            rascunho = estado.ler(raiz,p,estado.RASCUNHO)
            sessao = dict(data=agora(), rascunho=rascunho.get('data'))
            if migrando:
                futuro = dict(p,manifesto_wna=arq)
                for tipo in (estado.VISUAL, estado.RASCUNHO):
                    if dados := estado.ler(raiz,p,tipo):
                        existente = estado.ler(raiz,futuro,tipo)
                        if existente and existente != dados:
                            raise ValueError('Já existe estado salvo na pasta escolhida. Escolha outro local.')
                        estado.atualizar(raiz,futuro,tipo,lambda _:dados)
                self.projetos.salvar_manifesto(arq,estado_salvo=sessao)
            else:
                self.projetos.salvar_sessao(sessao)
        except (OSError, ValueError, TypeError, RuntimeError, sqlite3.Error) as erro:
            self._falha_salvar=p['uuid']
            self.receber_mapa('Salvamento do projeto incompleto. '+str(erro))
            self._atualizar_salvamento()
            return False
        self._falha_salvar=None
        self._atualizar_salvamento()
        msg = 'Projeto salvo com sucesso.'
        if rascunho:msg += ' Rascunho da conectividade preservado.'
        self.receber_mapa(msg+'\n'+arq)
        if hasattr(self.app.iface, 'messageBar'):
            self.app.iface.messageBar().pushSuccess('Water Network Auditor',msg)
        return True

    def abrir_rascunho_salvo(self):
        if self.abrir_conectividade():
            self.conectividade_gis.recuperar_rascunho()

    def salvar_projeto_como(self):
        if self.ocupado() or not self.projetos.atual():return
        if not self._resolver_troca_projeto():return
        p=deepcopy(self.projetos.atual())
        opcoes={'Criar cópia independente':'INDEPENDENTE','Mover projeto':'MOVER','Criar pacote portátil':'PORTATIL'}
        rotulo,ok=QInputDialog.getItem(self,'Salvar projeto como','Operação',list(opcoes),editable=False)
        if not ok:return
        modo=opcoes[rotulo]
        nome,ok=QInputDialog.getText(self,'Salvar projeto como','Nome da nova pasta',
                        text=nome_arquivo(p['nome'])+{'PORTATIL':'_portatil','INDEPENDENTE':'_copia','MOVER':''}[modo])
        if not ok or not nome.strip():return
        pasta=QFileDialog.getExistingDirectory(self,'Pasta que receberá a cópia do projeto')
        if not pasta:return
        novo_nome=nome_arquivo(nome)
        destino=Path(pasta)/novo_nome/(novo_nome+'.wna')
        if destino.parent.exists():
            self.receber_mapa('Escolha outra pasta de destino. O destino da cópia deve ser novo.')
            return
        from .modelo_gis import revisoes
        fontes={f['uri'] for rev in revisoes(p) for f in rev.get('fontes',())}
        arquivos=[r['base'] for r in p['bases']]
        if p.get('arquivo_complementos'):arquivos.append(p['arquivo_complementos'])
        aviso=QMessageBox(self)
        aviso.setWindowTitle(rotulo)
        aviso.setTextFormat(Qt.PlainText)
        aviso.setText(f'{len(arquivos)} banco(s) de trabalho e {len(fontes)} referência(s) GIS.\nDestino: {destino}'
                      + ('\nA nova localização se tornará ativa. A anterior ficará disponível para recuperação.'
                         if modo=='MOVER' else ''))
        aviso.setDetailedText('\n'.join([*arquivos,*sorted(fontes)]) or 'Projeto sem arquivos vinculados.')
        incluir=aviso.addButton('Copiar e incluir fontes GIS locais',QMessageBox.ActionRole)
        avancar=aviso.addButton('Copiar mantendo dependências externas',QMessageBox.AcceptRole)
        aviso.addButton(QMessageBox.Cancel)
        aviso.exec_()
        escolha=aviso.clickedButton()
        if escolha not in (incluir,avancar):return
        extras=[(estado.arquivo(self.app.catalogo.raiz,p,t),estado.caminho_relativo(p,t))
                for t in (estado.VISUAL,estado.RASCUNHO)]
        from .copia_projeto import copiar
        def pronto(resultado):
            from qgis.PyQt.QtCore import QTimer
            arquivo,alertas,_=resultado
            QTimer.singleShot(0,lambda:self.concluir_copia_projeto(p,arquivo,modo,alertas))
        self.app.atividades.executar_thread(rotulo,p['nome'],
            lambda parar,etapa:copiar(p,destino,modo,incorporar=escolha==incluir,
                                     cancelar=parar,etapa=etapa,extras=extras),pronto,self.receber_mapa)

    def concluir_copia_projeto(self,original,arquivo,modo,alertas):
        from .manifesto_projeto import ler
        try:
            destino=ler(arquivo)
            externas=destino.get('fontes_externas_na_copia',[])
            msg='Projeto preparado em '+str(arquivo)
            if externas:msg+=f'\n{len(externas)} fontes continuam externas e podem ser necessárias para recalcular.'
            if alertas:msg+='\n'+'\n'.join(alertas)
            self.receber_mapa(msg)
            abrir=modo=='MOVER' or QMessageBox.question(self,'Cópia pronta',msg+'\nAbrir a cópia agora?',
                                    QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes
            if not abrir:return
            if modo=='INDEPENDENTE':
                self.projetos.abrir_manifesto(arquivo)
            else:
                self.projetos.adotar_organizado(arquivo,original)
            self._manifesto_aberto()
        except (ValueError,OSError,sqlite3.Error) as erro:
            self.receber_mapa('Cópia preservada. Não foi possível ativá-la. '+str(erro))

    def resolver_salvamento_projeto(self):
        p = self.projetos.atual()
        if not p or not (self._pendencias_projeto() or self._falha_salvar == p['uuid']):
            return True
        dialogo = QMessageBox(self)
        dialogo.setWindowTitle('Projeto com alterações')
        dialogo.setTextFormat(Qt.PlainText)
        texto = 'Existem alterações não salvas no projeto '+p['nome']+'.'
        if aviso := self._editor_exige_decisao():
            texto += '\n'+aviso
        dialogo.setText(texto)
        salvar = dialogo.addButton('Salvar e continuar',QMessageBox.AcceptRole)
        descartar = dialogo.addButton('Descartar alterações',QMessageBox.DestructiveRole)
        cancelar = dialogo.addButton(QMessageBox.Cancel)
        dialogo.setDefaultButton(cancelar)
        dialogo.exec_()
        if dialogo.clickedButton() is salvar:
            return self.salvar_projeto()
        if dialogo.clickedButton() is descartar:
            if self.modelo_gis.pendente():
                self.modelo_gis.recarregar()
            if topo := self._topologia_do_projeto():
                topo.cancelar_captura(reabrir=False)
                topo.descartar_edicao()
            self._falha_salvar=None
            self._atualizar_salvamento()
            return True
        return False
