"""Ações de revisão e reexecução da hipótese em edição."""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QInputDialog, QMessageBox
from qgis.core import QgsCoordinateReferenceSystem

from . import hipoteses_gis as hg
from . import persistencia_grafo_gis as pg
from .entradas_grafo_gis import ler
from . import estado_projeto as estado
from .trabalhos_projeto import agora


class HipotesesGIS:
    def _parametros(self):
        return dict(tolerancia=self.tolerancia.value(),estrategia=self._revisao_operacional().get('estrategia','COMBINAR'),
                    inferir_proximas=self.aproximadas.isChecked(),limite_mm=self.limite.value())

    def _assinatura_edicao(self):
        ativos=tuple(sorted(self._selecionados()))
        pinos=tuple((u,self._pinos[u]['rev']) for u in ativos if u in self._pinos)
        return (ativos,pinos,tuple(sorted(self._redes_marcadas())),self.crs.crs().toWkt(),
                self.tolerancia.value(),self.limite.value(),self.aproximadas.isChecked(),
                tuple(sorted(self.unidades.items())))

    def resolver_edicao(self):
        if self._editor is not None:
            escolha=QMessageBox.question(self,'Edição de relação','Concluir a edição antes de trocar de contexto?',
                             QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Cancel)
            if escolha!=QMessageBox.Discard:return False
            self._editor.reject()
        if self._edicao_limpa is None or self._assinatura_edicao()==self._edicao_limpa:return True
        msg=QMessageBox(self)
        msg.setWindowTitle('Hipótese em edição')
        msg.setText('A configuração tem alterações ainda não salvas.')
        salvar=msg.addButton('Salvar revisão…',QMessageBox.AcceptRole)
        rascunho=msg.addButton('Preservar rascunho',QMessageBox.ActionRole)
        descartar=msg.addButton('Descartar alterações',QMessageBox.DestructiveRole)
        cancelar=msg.addButton(QMessageBox.Cancel)
        msg.setDefaultButton(cancelar)
        msg.exec_()
        escolha=msg.clickedButton()
        if escolha==salvar:
            self.salvar_hipotese()
            return False
        if escolha==rascunho and not self._com_erro(self.guardar_rascunho):return False
        if escolha not in (rascunho,descartar):return False
        if self._hip_ativa and self._hip_ativa.get('formato')==hg.FORMATO:
            self._aplicar(self._hip_ativa)
        else:
            redes=set(self._edicao_limpa[2])
            wkt,tolerancia,limite,proximas,unidades=self._edicao_limpa[3:]
            self.crs.setCrs(QgsCoordinateReferenceSystem(wkt))
            self.tolerancia.setValue(tolerancia)
            self.limite.setValue(limite)
            self.aproximadas.setChecked(proximas)
            self.unidades=dict(unidades)
            self._pinos={}
            self._marcar_escopo(self.redes,redes)
            self._marcar_escopo(self.participantes,self._edicao_limpa[0])
            self.mostrar_unidade(self.redes.currentItem())
            self._edicao_limpa=self._assinatura_edicao()
            self.agendar_mapa()
        return True

    def abrir_execucoes_hipotese(self):
        hip=self._por_revisao.get(self.hipoteses.currentData()) or self._hip_ativa
        if not hip:
            self.status.setText('Escolha uma hipótese salva para consultar suas execuções.')
            return
        self.central.listar_execucoes_salvas(hip['uuid'])

    def guardar_rascunho(self):
        ativos,pinos,redes,wkt,tolerancia,limite,proximas,unidades=self._assinatura_edicao()
        refs={u:self.registros[u]['rev'] for u in ativos if u in self.registros}
        refs.update(pinos)
        if refs.keys()!=set(ativos):
            raise ValueError('Há relações em edição sem revisão identificável.')
        rascunho=dict(data=agora(),hipotese_rev=(self._hip_ativa or {}).get('rev'),
                      modelo_rev=self._revisao_operacional().get('uuid'),vinculos=refs,
                      redes=list(redes),crs=wkt,tolerancia=tolerancia,
                      limite_mm=limite,inferir_proximas=proximas,unidades=dict(unidades))
        estado.atualizar(self.app.catalogo.raiz,self._projeto(),estado.RASCUNHO,lambda _:rascunho)
        self._rascunho_restaurado=None
        return True

    def recuperar_rascunho(self):
        if not self.resolver_edicao():return
        def recuperar():
            self._restaurar_rascunho(estado.ler(self.app.catalogo.raiz,self._projeto(),estado.RASCUNHO))
        self._com_erro(recuperar)

    def _restaurar_rascunho(self,d):
        if not d:
            self.status.setText('O projeto ainda não possui um rascunho preservado.')
            return
        rev=d.get('hipotese_rev')
        hip=self._por_revisao.get(rev)
        if rev and not hip:
            raise ValueError('A revisão de hipótese do rascunho está indisponível.')
        modelo=self._revisao_operacional(hip) if hip else self._revisao()
        if modelo.get('uuid')!=d.get('modelo_rev'):
            raise ValueError('O rascunho pertence a outra revisão do Modelo GIS.')
        pinos={}
        for uid,id_rev in d['vinculos'].items():
            r=self._por_revisao.get(id_rev)
            if not r or r['uuid']!=uid or self.registros.get(uid,{}).get('excluido'):
                raise ValueError('Uma relação do rascunho está indisponível ou foi excluída.')
            pinos[uid]=r
        crs=QgsCoordinateReferenceSystem(d['crs'])
        if not crs.isValid() or not set(d['redes'])<={r['uid'] for r in modelo.get('fontes',())}:
            raise ValueError('O CRS ou as fontes do rascunho estão indisponíveis.')
        anterior=self._assinatura_edicao()
        if hip and hip.get('formato')==hg.FORMATO:
            self._aplicar(hip)
        else:
            self._hip_ativa=hip
            self._listar_redes(modelo)
            self._edicao_limpa=anterior
        self._pinos=pinos
        self.crs.setCrs(crs)
        self.tolerancia.setValue(d['tolerancia'])
        self.limite.setValue(d['limite_mm'])
        self.aproximadas.setChecked(d['inferir_proximas'])
        self.unidades=dict(d['unidades'])
        self._marcar_escopo(self.redes,set(d['redes']))
        self.atualizar_complementos(escolhidos=pinos)
        self.mostrar_unidade(self.redes.currentItem())
        self._resultado_historico=False
        self._rascunho_restaurado=d['data']
        self._indicar_rascunho()
        self.status.setText('Rascunho recuperado. Salve uma revisão para tornar a configuração definitiva.')

    @staticmethod
    def _marcar_escopo(tabela, ids):
        bloqueado=tabela.blockSignals(True)
        try:
            for i in range(tabela.count()):
                item=tabela.item(i)
                item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in ids else Qt.Unchecked)
        finally:tabela.blockSignals(bloqueado)

    def _aplicar(self,hip):
        pinos=hg.resolver_vinculos(hip,self._por_revisao)
        modelo=self._revisao_operacional(hip)
        self._hip_ativa=hip
        self._pinos=pinos
        config=hip['configuracao']
        self._listar_redes(modelo)
        self.crs.setCrs(QgsCoordinateReferenceSystem(config['crs']))
        self.unidades=dict(config['unidades'])
        parametros=config['parametros']
        self.tolerancia.setValue(parametros['tolerancia'])
        self.limite.setValue(parametros['limite_mm'])
        self.aproximadas.setChecked(parametros['inferir_proximas'])
        self._marcar_escopo(self.redes,{f['uid'] for f in config['fontes'] if f['categoria']=='PIPE'})
        self.atualizar_complementos(escolhidos=pinos)
        self._edicao_limpa=self._assinatura_edicao()
        self._indicar_rascunho()
        self._resultado_historico=False
        self.status.setText('Hipótese '+hip['nome']+' · revisão '+hip['rev'][:8]+' carregada.')
        self.agendar_mapa()

    def aplicar_hipotese(self):
        destino=self.hipoteses.currentData()
        anterior=self._hip_ativa
        if not self.resolver_edicao():
            self.hipoteses.setCurrentIndex(max(0,self.hipoteses.findData(anterior['rev'] if anterior else None)))
            return False
        hip=self._por_revisao.get(destino)
        if hip and hip.get('formato')==hg.FORMATO:
            self._com_erro(lambda:self._aplicar(hip))
        else:
            self._hip_ativa=hip
            self._pinos={}
            self._listar_redes(self._revisao())
            self.atualizar_complementos(escolhidos=())
            self._edicao_limpa=self._assinatura_edicao()
            self._indicar_rascunho()
            self._resultado_historico=False
            self.status.setText('Hipótese legada. Para fixar revisões atuais, marque as relações e salve uma nova revisão.'
                                if hip else 'Hipótese temporária em edição.')
            self.agendar_mapa()
        return True

    def adotar_revisao_atual(self):
        r=self._registro_selecionado()
        if not r:return
        escolhidos=self._selecionados()
        self._pinos.pop(r['uuid'],None)
        self.atualizar_complementos(escolhidos=escolhidos)
        self._resultado_historico=False
        self.agendar_mapa()

    def _participantes_exatos(self,repetir=False):
        atuais=pg.vigentes(self._base_complementos(),self.uid_projeto)
        for uid in self._selecionados():
            if atuais.get(uid,{}).get('excluido'):
                fixada=(self._hip_ativa or {}).get('vinculos',{}).get(uid)
                if not repetir or not fixada or self._pinos.get(uid,{}).get('rev')!=fixada:
                    raise ValueError('Há um complemento excluído na seleção. Retire-o ou recupere-o antes de gravar ou testar outra hipótese.')
        ativos={**atuais,**self._pinos}
        return pg.selecionar(ativos,self._selecionados())

    def salvar_hipotese(self,nova=False,reexecutar=False):
        if self.central.ocupado():return
        anterior=None if nova else self._hip_ativa
        nome,ok=QInputDialog.getText(self,'Salvar hipótese','Nome',text=(anterior or {}).get('nome',''))
        if not ok or not nome.strip():return
        self._com_erro(lambda:self._gravar_hipotese(nome.strip(),anterior,reexecutar))

    def _gravar_hipotese(self,nome,anterior=None,reexecutar=False):
        prep=self._preparacao()
        participantes=self._participantes_exatos()
        config=hg.configuracao(prep,self._revisao_operacional().get('uuid'),self._parametros())
        def trabalho(parar,etapa):
            return hg.assinatura_inventario(ler(prep,parar,etapa))
        def pronto(assinatura):
            dados=hg.dados_hipotese(nome,self.uid_projeto,config,participantes,assinatura)
            r=self._salvar('HIPOTESE',dados,anterior)
            self._aplicar(r)
            restaurado=getattr(self,'_rascunho_restaurado',None)
            if restaurado:
                try:
                    estado.atualizar(self.app.catalogo.raiz,self._projeto(),estado.RASCUNHO,
                                     lambda d:{} if d.get('data')==restaurado else d)
                    self._rascunho_restaurado=None
                except (ValueError,OSError) as e:
                    self.status.setText('Revisão salva. Não foi possível retirar o rascunho anterior. '+str(e))
        worker=self.app.atividades.executar_thread('Fixar revisão da hipótese',nome,trabalho,pronto,self.status.setText)
        operacao=self.app.atividades.atual
        if reexecutar:
            from qgis.PyQt.QtCore import QTimer
            worker.finished.connect(lambda:QTimer.singleShot(0,lambda:self.iniciar(modo='salva'))
                                     if operacao.estado=='CONCLUIDO' else None)
        return worker

    def reexecutar(self):
        if self.central.ocupado():return
        opcoes=['Executar temporariamente','Salvar como nova hipótese']
        if self._hip_ativa:opcoes.insert(1,'Atualizar hipótese atual')
        opcao,ok=QInputDialog.getItem(self,'Reexecutar análise com estas alterações','Como aplicar a configuração?',
                                    opcoes,editable=False)
        if not ok:return
        if opcao==opcoes[0]:self.iniciar(modo='temporaria')
        else:self.salvar_hipotese(nova=opcao=='Salvar como nova hipótese',reexecutar=True)

    def _validar_configuracao_fixada(self,hip,config,participantes):
        if hip.get('formato')!=hg.FORMATO:
            raise ValueError('A hipótese legada precisa de uma nova revisão explícita para reexecutar.')
        refs={r['uuid']:r['rev'] for r in participantes}
        if config!=hip['configuracao'] or refs!=hip['vinculos']:
            raise ValueError('A configuração ou as fontes diferem da revisão salva. Use Reexecutar com estas alterações.')
