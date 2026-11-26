"""Conferência visual e revisão de relações equivalentes."""

from qgis.PyQt.QtCore import QTimer, Qt
from qgis.PyQt.QtWidgets import QDialog, QInputDialog, QMessageBox, QVBoxLayout
from qgis.core import QgsCoordinateReferenceSystem

from . import persistencia_grafo_gis as pg
from .duplicatas_conexoes_gis import ROTULOS, auditar, equivalentes
from .modelo_gis_ui import aviso, botao
from .navegacao_cartografica import navegar_registros
from .tabelas_topologia_gis import TabelaGIS


def _uid(r):
    return r.get('uuid') or r['uid']


def _opcoes(registros):
    return {f"{r.get('nome') or ROTULOS.get(r['tipo'],r['tipo'])} · {_uid(r)[:12]} · "
            f"{pg.DECISOES.get(r.get('decisao'),'Candidata')}":r for r in registros}


class DuplicatasConexoesUI:
    def confirmar_distincao_manual(self,editor,dados):
        tol=self.tolerancia.value()
        crs=QgsCoordinateReferenceSystem(dados['crs_rede'])
        mesmo_crs=self.dados and QgsCoordinateReferenceSystem(self.dados['crs'])==crs
        candidatas=self._candidatas_tabela.values() if mesmo_crs else ()
        conhecidas=[r for r in self.registros.values() if not r.get('crs_rede') or
                    QgsCoordinateReferenceSystem(r['crs_rede'])==crs]
        encontrados=equivalentes(dados,conhecidas,candidatas,editor.tubos,tol)
        if not encontrados:return True
        janela=QMessageBox(editor)
        janela.setWindowTitle('Conexão equivalente encontrada')
        janela.setText(f'{len(encontrados)} registro(s) com as mesmas partes e posições compatíveis.')
        abrir=janela.addButton('Abrir conexão existente',QMessageBox.ActionRole)
        distinta=janela.addButton('Criar relação distinta com justificativa',QMessageBox.ActionRole)
        janela.addButton(QMessageBox.Cancel)
        janela.exec()
        if janela.clickedButton()==abrir:
            opcoes=_opcoes(sorted(encontrados,key=lambda r:('uuid' not in r,_uid(r))))
            nome,ok=QInputDialog.getItem(editor,'Conexões equivalentes','Registro',list(opcoes),0,False)
            if ok:
                editor.reject()
                QTimer.singleShot(0,lambda:self.conferir_conexao(opcoes[nome]))
        elif janela.clickedButton()==distinta:
            motivo,ok=QInputDialog.getText(editor,'Conexão distinta','Qual diferença técnica deve ser registrada?')
            if ok and motivo.strip():
                dados.update(justificativa_distincao=motivo.strip(),equivalentes_verificados=[_uid(r) for r in encontrados],
                             tolerancia_equivalencia_m=tol)
                return True
        return False

    def verificar_conexoes_repetidas(self):
        if self.central.ocupado():return
        if not self.dados:
            self.status.setText('Abra uma execução de conectividade para verificar as posições no grafo.')
            return
        d=self.dados
        p=self._projeto()
        base=self._base_complementos()
        tubos=dict(self.tubos)
        tol=d['parametros']['tolerancia']
        def medir(parar,etapa):
            etapa(0,'Conferindo identidade, posições e revisões')
            historico=pg.revisoes(base,p['uuid'],tipo='CONEXAO') if base else []
            relacoes={r['uuid']:r for r in historico}
            return auditar(d['diagnosticos'],relacoes.values(),tubos,tol,parar,historico=historico)
        def pronto(resultado):
            if self.dados is d and self._projeto()['uuid']==p['uuid']:
                self._mostrar_conexoes_repetidas(*resultado,tol)
        self.app.atividades.executar_thread('Verificar conexões repetidas',p['nome'],medir,pronto,self.status.setText)

    def _mostrar_conexoes_repetidas(self,pares,pendentes,tol):
        dlg=QDialog(self)
        dlg.setWindowTitle('Auditoria de conexões repetidas')
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        v=QVBoxLayout(dlg)
        v.addWidget(aviso(f'{len(pares)} comparações · {len(pendentes)} referências inconclusivas · tolerância {tol:g} m'))
        if pendentes:v.addWidget(aviso('Referências sem validação: '+', '.join(u[:10] for u in pendentes[:10])))
        tabela=TabelaGIS()
        registros={r['uid']:r for r in pares}
        tabela.colunas(('Classificação','Registros','Distância (m)','Relação sugerida'))
        for i,largura in enumerate((280,180,105)):
            tabela.setColumnWidth(i,largura)
        for r in pares:
            tabela.inserir((ROTULOS[r['tipo']],', '.join(_uid(x)[:10] for x in r['registros']),
                           r.get('distancia_m','—'),r['principal'][:10]),r['uid'])
        v.addWidget(tabela)
        def par(i):
            item=tabela.item(i.row(),0) if i.isValid() else None
            return registros.get(item.data(Qt.UserRole)) if item else None
        def localizar(i,aproximar):
            if (r:=par(i)):
                self.destacar(aproximar=aproximar,registros=[
                    dict(x,uid=_uid(x),tubos=[u for u,_ in x.get('portas',())]) for x in r['registros']],
                    toda_extensao=True)
        def menu(i):
            r=par(i)
            if not r:return []
            acoes=[('Revisar '+nome,lambda x=registro:self.conferir_conexao(x))
                   for nome,registro in _opcoes(r['registros']).items()]
            if r['tipo'] in ('EXATA','PROVAVEL','CONFLITO') and all('uuid' in x for x in r['registros']):
                acoes.append(('Escolher relação principal…',lambda:self._consolidar_conexoes(r,dlg,tol)))
            return acoes
        navegar_registros(tabela,localizar,menu,self.central.mapa.limpar)
        botao(v,'Fechar',dlg.reject)
        dlg.resize(810,460)
        dlg.open()

    def _consolidar_conexoes(self,par,dlg,tol):
        opcoes=_opcoes(sorted(par['registros'],key=lambda r:_uid(r)!=par['principal']))
        escolha,ok=QInputDialog.getItem(dlg,'Consolidar conexões','Preservar como relação principal',list(opcoes),0,False)
        if not ok:return
        principal=opcoes[escolha]
        outra=next(r for r in opcoes.values() if r is not principal)
        def salvar():
            if principal.get('excluido') or principal.get('substituida_por') or principal not in equivalentes(
                    outra,[principal],[],self.tubos,tol):
                raise ValueError('As referências precisam ser conferidas novamente.')
            marcados=set(self._selecionados())
            antiga_marcada=outra['uuid'] in marcados
            novo=pg.salvar_revisao(self._base_complementos(),self.uid_projeto,'CONEXAO',
                dict(outra,substituida_por=principal['uuid'],substituida_por_rev=principal['rev'],
                     habilitado=False,auditoria_duplicidade=par['tipo'],tolerancia_equivalencia_m=tol),
                outra['uuid'],outra['rev'],referencia=(principal['uuid'],principal['rev']))
            self._pinos.pop(outra['uuid'],None)
            marcados.discard(outra['uuid'])
            if antiga_marcada and principal.get('habilitado',True) and par['tipo']!='CONFLITO':
                marcados.add(principal['uuid'])
                self._pinos[principal['uuid']]=principal
            self.atualizar_complementos(escolhidos=marcados)
            if self.dados:self.mudar_resultados(preservar=True)
            self.guardar_rascunho()
            self.status.setText(f"Revisão {novo['rev'][:8]} salva. Confira a participação da relação principal no rascunho.")
            dlg.accept()
        self._com_erro(salvar)
