"""Ações de revisão e reexecução da hipótese em edição."""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QInputDialog, QMessageBox
from qgis.core import QgsCoordinateReferenceSystem

from . import hipoteses_gis as hg
from . import persistencia_grafo_gis as pg
from .entradas_grafo_gis import ler


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
        escolha=QMessageBox.question(self,'Hipótese em edição','Salvar a configuração desta hipótese?',
            QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Cancel)
        if escolha==QMessageBox.Cancel:return False
        if escolha==QMessageBox.Save:
            self.salvar_hipotese()
            return False
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
