"""Estado operacional da janela; configuração pendente nunca redefine resultados."""
from contextlib import contextmanager
from enum import Enum
from qgis.PyQt.QtCore import Qt,QSignalBlocker
from qgis.PyQt.QtWidgets import QPushButton,QHBoxLayout,QLabel,QMessageBox,QInputDialog,QFileDialog


class Estado(str,Enum):
    SEM_AUDITORIA='SEM_AUDITORIA'
    CONFIGURANDO='CONFIGURANDO'
    CONFIRMANDO='CONFIRMANDO'
    PROCESSANDO='PROCESSANDO'
    CONCLUIDO='CONCLUIDO'
    INSPECIONANDO='INSPECIONANDO'
    PREPARANDO_REPROCESSAMENTO='PREPARANDO_REPROCESSAMENTO'
    PREPARANDO_REAGRUPAMENTO='PREPARANDO_REAGRUPAMENTO'
    ERRO='ERRO'

EDITAVEIS={Estado.SEM_AUDITORIA,Estado.CONFIGURANDO,Estado.PREPARANDO_REPROCESSAMENTO,
    Estado.PREPARANDO_REAGRUPAMENTO}
OCUPADOS={Estado.PROCESSANDO,Estado.CONFIRMANDO}
TRANSICOES={e:set(Estado)-{Estado.CONCLUIDO} for e in Estado}
TRANSICOES[Estado.PROCESSANDO]={Estado.CONCLUIDO,Estado.INSPECIONANDO,Estado.CONFIGURANDO,
    Estado.PREPARANDO_REPROCESSAMENTO,Estado.PREPARANDO_REAGRUPAMENTO,Estado.ERRO}
TRANSICOES[Estado.CONCLUIDO]={Estado.INSPECIONANDO,Estado.ERRO}


class EstadoOperacional:
    def iniciar_estados(self,layout):
        self.estado=Estado.SEM_AUDITORIA
        self.transicoes=[]
        self._restaurando=0
        self._modo_fixo=None
        self._plano_operacao=None
        self._config_inicial=None
        self._formulario_resultado=None
        self.estado_info=QLabel();self.estado_info.setWordWrap(True);layout.addWidget(self.estado_info)
        linha=QHBoxLayout()
        self.trocar_operacao=QPushButton('Trocar operação / voltar ao início…')
        self.trocar_operacao.clicked.connect(self.escolher_operacao)
        linha.addWidget(self.trocar_operacao)
        self.acoes_contexto={}
        for texto,modo in [('NOVA AUDITORIA',0),('REPROCESSAR ESTA AUDITORIA',3),('REGERAR LOCAIS',2)]:
            b=QPushButton(texto);b.clicked.connect(lambda _,m=modo:self.iniciar_operacao(m))
            self.acoes_contexto[modo]=b;linha.addWidget(b)
        layout.addLayout(linha)
        self.continuar_inspecao=QPushButton('CONTINUAR INSPEÇÃO')
        self.continuar_inspecao.clicked.connect(self.voltar_inspecao)
        layout.addWidget(self.continuar_inspecao)
        self.retomar=QPushButton('Retomar configuração após erro')
        self.retomar.clicked.connect(self.retomar_configuracao);layout.addWidget(self.retomar)

    @contextmanager
    def restaurando(self):
        self._restaurando+=1
        try:
            yield
        finally:
            self._restaurando-=1

    def formulario(self):
        if not hasattr(self,'redes'):
            return None
        tabelas=[]
        for t in (self.redes,self.limites):
            tabelas.append([(t.item(l,0).data(Qt.UserRole),int(t.item(l,0).checkState()),
                tuple(t.cellWidget(l,c).currentData() for c in range(2,t.columnCount())))
                for l in range(t.rowCount())])
        return dict(tabelas=tabelas,nome=self.nome_auditoria.text(),projeto=self.projeto_auditoria.text(),
            tolerancia=self.tolerancia.value(),continuidade=self.continuidade.value(),
            agrupar=self.agrupar.isChecked(),busca=self.distancia_locais.value(),
            extensao=self.extensao_locais.value(),crs=self.crs.crs().toWkt())

    def restaurar_formulario(self,f):
        if f is None:
            return
        from qgis.core import QgsCoordinateReferenceSystem
        with self.restaurando():
            for tabela,linhas in zip((self.redes,self.limites),f['tabelas']):
                mapa={uid:(check,valores) for uid,check,valores in linhas}
                for linha in range(tabela.rowCount()):
                    item=tabela.item(linha,0);v=mapa.get(item.data(Qt.UserRole))
                    item.setCheckState(Qt.CheckState(v[0]) if v else Qt.Unchecked)
                    if v:
                        for col,valor in enumerate(v[1],2):
                            combo=tabela.cellWidget(linha,col);indice=combo.findData(valor)
                            if indice>=0:
                                combo.setCurrentIndex(indice)
            self.nome_auditoria.setText(f['nome']);self.projeto_auditoria.setText(f['projeto'])
            self.tolerancia.setValue(f['tolerancia']);self.continuidade.setValue(f['continuidade'])
            self.agrupar.setChecked(f['agrupar']);self.distancia_locais.setValue(f['busca'])
            self.extensao_locais.setValue(f['extensao']);self.crs.setCrs(QgsCoordinateReferenceSystem(f['crs']))

    def monitorar_configuracao(self):
        self._monitorando=True
        self.redes.itemChanged.connect(self.configuracao_alterada)
        self.limites.itemChanged.connect(self.configuracao_alterada)
        for w in (self.nome_auditoria,self.projeto_auditoria):
            w.textChanged.connect(self.configuracao_alterada)
        for w in (self.tolerancia,self.continuidade,self.distancia_locais,self.extensao_locais):
            w.valueChanged.connect(self.configuracao_alterada)
        self.agrupar.toggled.connect(self.configuracao_alterada)
        self.crs.crsChanged.connect(self.configuracao_alterada)
        self._config_inicial=self.formulario()
        self.aplicar_estado()

    def configuracao_alterada(self,*_):
        if self._restaurando or not getattr(self,'_monitorando',False) or not hasattr(self,'executar'):
            return
        if self.estado not in EDITAVEIS:
            # Também protege mudanças programáticas involuntárias em controles bloqueados.
            congelado=getattr(self,'_formulario_em_execucao',None) if self.estado in OCUPADOS else None
            self.restaurar_formulario(congelado or self._formulario_resultado or self._config_inicial)
            self.aplicar_estado()
            return
        if self._modo_fixo is None:
            self._modo_fixo=self.modalidade.currentIndex()
        if self.estado==Estado.SEM_AUDITORIA:
            self.definir_estado(self.estado_configuracao())
        self._plano_operacao=None
        self.aplicar_estado()

    def pendente(self):
        def aplicada(f):
            if f is None:
                return None
            return dict(f,tabelas=[sorted([r for r in t if r[1]==int(Qt.Checked)]) for t in f['tabelas']])
        return self.estado in EDITAVEIS and aplicada(self.formulario())!=aplicada(self._config_inicial)

    def estado_configuracao(self):
        return {2:Estado.PREPARANDO_REAGRUPAMENTO,3:Estado.PREPARANDO_REPROCESSAMENTO}.get(
            self.modalidade.currentIndex(),Estado.CONFIGURANDO)

    def definir_estado(self,novo):
        novo=Estado(novo)
        if novo!=self.estado:
            if novo not in TRANSICOES[self.estado]:
                raise RuntimeError('Transição operacional inválida: '+self.estado.value+' → '+novo.value)
            self.transicoes.append((self.estado.value,novo.value))
            self.estado=novo
        self.aplicar_estado()

    def aplicar_estado(self):
        if not hasattr(self,'executar'):
            return
        ocupado=self.estado in OCUPADOS or self._executando
        edicao=self.estado in EDITAVEIS and not ocupado
        modo=self.modalidade.currentIndex()
        entradas=edicao and modo in (0,3)
        inspecao=self.estado in (Estado.CONCLUIDO,Estado.INSPECIONANDO,Estado.ERRO)
        self.modalidade.setEnabled(self._modo_fixo is None and not ocupado)
        for w in (self.abas,self.atualizar,self.tolerancia,self.continuidade,self.crs):
            w.setEnabled(entradas)
        self.abas.setVisible(self.estado in EDITAVEIS and modo in (0,3))
        self.atualizar.setVisible(self.estado in EDITAVEIS and modo in (0,3))
        self.configuracao_ativa.setVisible(bool(self.dossie) and self.estado not in EDITAVEIS)
        self.agrupar.setEnabled(edicao and modo!=1)
        for w in (self.distancia_locais,self.extensao_locais):
            w.setEnabled(edicao and modo!=1 and self.agrupar.isChecked())
        self.nome_auditoria.setReadOnly(not edicao);self.projeto_auditoria.setReadOnly(not edicao)
        self.executar.setEnabled(not ocupado)
        self.executar.setText('CONTINUAR INSPEÇÃO' if inspecao and self.dossie else
            ('Executar nova auditoria…','Selecionar auditoria…','Regerar somente os locais…',
             'Confirmar e reprocessar…')[modo])
        self.selecionar_auditoria.setEnabled(not ocupado and modo!=0 and not inspecao)
        for w in (self.trocar_operacao,self.reabrir,self.fechar):
            w.setEnabled(not ocupado)
        for m,w in self.acoes_contexto.items():
            w.setEnabled(not ocupado and (m==0 or bool(self.dossie)))
        self.continuar_inspecao.setEnabled(bool(self.dossie) and not ocupado)
        self.retomar.setVisible(self.estado==Estado.ERRO)
        self.retomar.setEnabled(not ocupado)
        for w in (self.inspecionar,self.exportar,self.exportar_geo):
            w.setEnabled(bool(self.dossie) and not ocupado)
        self.detalhes_excel.setEnabled(not ocupado)
        self.estado_info.setText('Estado: '+self.estado.value+(
            ' — CONFIGURAÇÃO PENDENTE DE EXECUÇÃO. Resultados ativos permanecem anteriores.' if self.pendente()
            else ' — Resultados vinculados à configuração preservada.' if self.dossie else ''))
        if self.dossie:
            c=self.dossie.get('controle_versao',{})
            self.origem_info.setText(f"Execução ativa: {c.get('nome','Auditoria')} | {self.dossie['execucao_uid']}\n"
                f"{len(self.dossie['eventos'])} eventos / {len(self.dossie['locais'])} locais; "
                f"busca {self.dossie['analise']['opcoes']['distancia']} m; "
                f"extensão {self.dossie['analise']['opcoes']['extensao_maxima']} m. "
                'Alterar a lista de fontes não atualiza estes resultados.')

    def aceitar_modalidade(self):
        modo=self.modalidade.currentIndex()
        if self._modo_fixo is not None and modo!=self._modo_fixo and not self._restaurando:
            bloqueio=QSignalBlocker(self.modalidade)
            self.modalidade.setCurrentIndex(self._modo_fixo)
            del bloqueio
            self.status.setText('Use Trocar operação ou uma ação explícita. A execução ativa foi preservada.')
            return False
        return True

    def resolver_pendencias(self):
        if self.estado in OCUPADOS or self._executando:
            return False
        if self.pendente() and QMessageBox.question(self,'Configuração não aplicada',
                'Descartar a configuração ainda não executada? Os resultados ativos serão preservados.',
                QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)!=QMessageBox.Yes:
            return False
        if self.painel and self.painel.tem_edicoes():
            if not self.painel.resolver_edicoes():
                return False
            if self.painel.tem_edicoes():
                self.painel.atualizar()
        return True

    def escolher_operacao(self):
        from .fluxos import MODALIDADES
        if self.estado in OCUPADOS or self._executando:
            return
        escolha,ok=QInputDialog.getItem(self,'Iniciar outro fluxo','Operação:',MODALIDADES,0,False)
        if ok:
            self.iniciar_operacao(MODALIDADES.index(escolha),usar_ativa=False)

    def garantir_origem(self):
        if not self.dossie:
            return False
        base=self.painel.base if self.painel and self.painel.dossie is self.dossie else self.base_revisao
        if not base:
            caminho,_=QFileDialog.getSaveFileName(self,'Preservar execução de origem para versionamento','',
                'GeoPackage (*.gpkg)')
            if not caminho:
                return False
            if not caminho.lower().endswith('.gpkg'):
                caminho+='.gpkg'
            from .persistencia import salvar_execucao
            salvar_execucao(caminho,self.dossie)
            self.vincular_base(caminho);base=caminho
        from .persistencia import carregar_execucao
        self.auditoria_origem=carregar_execucao(base,self.dossie['execucao_uid'])
        self.base_origem=str(base)
        return True

    def iniciar_operacao(self,modo,usar_ativa=True):
        if not self.resolver_pendencias():
            return False
        formulario=self.formulario();fixo=self._modo_fixo;estado=self.estado
        contexto=(self.auditoria_origem,self.base_origem,self._origens_configuradas.copy(),self._config_inicial)
        try:
            if self.painel and not self.painel.close():
                return False
            if modo in (2,3) and usar_ativa and not self.garantir_origem():
                return False
            with self.restaurando():
                self._modo_fixo=modo
                self.modalidade.setCurrentIndex(modo)
                self._plano_operacao=None
                self.definir_estado(self.estado_configuracao())
                if modo in (2,3) and usar_ativa:
                    self.restaurar_configuracao(self.auditoria_origem,resolver=modo==3)
                elif modo==0:
                    self.auditoria_origem=None;self.base_origem=None;self._origens_configuradas={}
                    for t in (self.redes,self.limites):
                        for l in range(t.rowCount()):
                            t.item(l,0).setCheckState(Qt.Unchecked)
                    self.nome_auditoria.clear();self.projeto_auditoria.clear()
            self._config_inicial=self.formulario()
            self.aplicar_estado()
            if modo in (1,2,3) and not usar_ativa:
                if not self.escolher_auditoria():
                    with self.restaurando():
                        self._modo_fixo=fixo
                        self.modalidade.setCurrentIndex(fixo if fixo is not None else 0)
                        self.restaurar_formulario(formulario)
                    self.auditoria_origem,self.base_origem,self._origens_configuradas,self._config_inicial=contexto
                    self.estado=estado;self.aplicar_estado()
                    return False
            return True
        except Exception as erro:
            with self.restaurando():
                self._modo_fixo=fixo
                self.modalidade.setCurrentIndex(fixo if fixo is not None else 0)
                self.restaurar_formulario(formulario)
            self.estado=estado;self.aplicar_estado()
            self.auditoria_origem,self.base_origem,self._origens_configuradas,self._config_inicial=contexto
            QMessageBox.warning(self,'Operação não iniciada',str(erro))
            return False

    def voltar_inspecao(self):
        if not self.dossie or not self.resolver_pendencias():
            return False
        self.restaurar_formulario(self._formulario_resultado)
        self.definir_estado(Estado.INSPECIONANDO)
        return True

    def retomar_configuracao(self):
        if self.estado==Estado.ERRO:
            self.definir_estado(self.estado_configuracao())

    def confirmar_processamento(self,redes=None,limites=None,parametros=None,regeneracao=False):
        """Sempre explícito na interface; nenhuma dependência de plataforma/offscreen."""
        from .ciclo import perfil
        modo=2 if regeneracao else self.modalidade.currentIndex()
        if modo in (2,3):
            plano=self.escolher_politica(self.auditoria_origem,
                parametros.crs if parametros else self.auditoria_origem['contexto']['parametros']['crs'])
            if plano is None:
                return False
        else:
            plano=dict(modo='NOVA',destino=None,confirmado=False)
        from .fluxos import MODALIDADES
        linhas=[f'Auditoria: {self.nome_auditoria.text() or "(sem nome)"}',
            'Modalidade: '+MODALIDADES[modo],
            'Execução de origem: '+(self.auditoria_origem['execucao_uid'] if modo in (2,3) else 'Nenhuma'),
            'Política: '+plano['modo'],'Destino: '+str(plano['destino'] or 'Camadas temporárias do projeto; persistência/exportação posterior')]
        fontes=perfil(self.auditoria_origem)['fontes'] if modo==2 else []
        if modo==2:
            linhas += [f"{'Limite' if f['modo'] else 'Rede'}: {f['camada']} | {f.get('modo') or ''} | "
                f"ID: {f.get('campo_id')} | exibição: {f.get('campo_nome')}" for f in fontes]
            g=perfil(self.auditoria_origem)['geometria']
            linhas += [f"Geometria preservada: CRS {g['crs']}; tolerância {g['tolerancia_geometrica']} m; continuidade {g['distancia_continuidade']} m.",
                'O núcleo geométrico não será executado.']
        else:
            linhas += [f'Rede: {c.camada.name()} | ID: {c.campo_id}' for c in redes]
            linhas += [f'Limite: {c.camada.name()} | {c.modo.value} | ID: {c.campo_id} | exibição: {c.campo_nome}' for c in limites]
            linhas += [f'CRS: {parametros.crs}; tolerância: {parametros.tolerancia_geometrica} m; continuidade: {parametros.distancia_continuidade} m.']
        o=self.opcoes_agrupamento()
        linhas += [f'Agrupamento habilitado: {o.habilitado}; busca: {o.distancia} m; extensão máxima: {o.extensao_maxima} m.',
            'Funcionalidade: auditoria espacial; sem associação de equipamentos ou alteração hidráulica.']
        if not self.mostrar_comparacao('Confirmar operação e destino',linhas,'Confirmar e executar'):
            return False
        self._plano_operacao=plano
        return True
