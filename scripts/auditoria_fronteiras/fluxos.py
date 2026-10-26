"""Fluxos de abertura e versionamento; mantém o formulário e processador existentes."""
from pathlib import Path
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QComboBox,QDialog,QVBoxLayout,QHBoxLayout,QLabel,
    QPushButton,QInputDialog,QFileDialog,QMessageBox,QLineEdit,QPlainTextEdit,QApplication)
from qgis.core import QgsCoordinateReferenceSystem
from .ciclo import perfil,comparar_configuracoes,configuracao_proposta,inicializar
from .catalogo import carregadas,recentes,lembrar,publicar,resolver_fontes
from .versoes import listar,abrir_ro,token,preparar_regeneracao,gravar_versao
from .persistencia import carregar_execucao
from .investigacao import OpcoesLocais
from .estados import EstadoOperacional,Estado,EDITAVEIS,OCUPADOS

MODALIDADES=('NOVA AUDITORIA','CONTINUAR AUDITORIA','REGERAR LOCAIS','REPROCESSAR AUDITORIA')


class FluxosAuditoria(EstadoOperacional):
    def montar_fluxos(self,layout):
        self.auditoria_origem=None
        self.base_origem=None
        self._origens_configuradas={}
        self.modalidade=QComboBox()
        self.modalidade.addItems(MODALIDADES)
        self.modalidade.currentIndexChanged.connect(self.mudar_modalidade)
        self.selecionar_auditoria=QPushButton('Selecionar auditoria existente…')
        self.selecionar_auditoria.clicked.connect(self.escolher_auditoria)
        linha=QHBoxLayout();linha.addWidget(self.modalidade);linha.addWidget(self.selecionar_auditoria)
        layout.addLayout(linha)
        self.iniciar_estados(layout)
        self.origem_info=QLabel('Nova auditoria: selecione as entradas e os parâmetros.')
        self.origem_info.setWordWrap(True);layout.addWidget(self.origem_info)
        self.nome_auditoria=QLineEdit();self.nome_auditoria.setPlaceholderText('Nome da auditoria (opcional)')
        self.projeto_auditoria=QLineEdit();self.projeto_auditoria.setPlaceholderText('Município / projeto (opcional)')
        linha=QHBoxLayout();linha.addWidget(self.nome_auditoria);linha.addWidget(self.projeto_auditoria)
        layout.addLayout(linha)

    def mudar_modalidade(self):
        if not hasattr(self,'executar'):
            return
        if not self.aceitar_modalidade():
            return
        modo=self.modalidade.currentIndex()
        if self.estado==Estado.SEM_AUDITORIA and modo!=0 and self._modo_fixo is None:
            self._modo_fixo=modo
            self.definir_estado(self.estado_configuracao())
        self.aplicar_estado()

    def escolher_auditoria(self):
        if self.estado in OCUPADOS or self._executando:
            return
        try:
            alternativas=['Abrir GeoPackage','Camadas carregadas no projeto','Auditorias recentes']
            escolha,ok=QInputDialog.getItem(self,'Origem da auditoria','Selecionar por:',alternativas,0,False)
            if not ok:
                return
            if escolha==alternativas[0]:
                base,_=QFileDialog.getOpenFileName(self,'Base completa de auditoria','','GeoPackage (*.gpkg)')
                if not base:
                    return
                itens=listar(base)
            elif escolha==alternativas[1]:
                itens,avisos=carregadas(self.projeto)
                if avisos:
                    QMessageBox.information(self,'Limitações das camadas','\n'.join(avisos))
            else:
                itens=recentes()
            if not itens:
                raise ValueError('Nenhuma auditoria completa encontrada. Selecione o GeoPackage persistente.')
            from .seletor_versoes import SeletorVersoes
            seletor=SeletorVersoes(itens,self,self.dossie['execucao_uid'] if self.dossie else None)
            if seletor.exec()!=QDialog.Accepted:
                return
            r=seletor.selecionada();base=r['base']
            if not Path(base).exists():
                base,_=QFileDialog.getOpenFileName(self,'Localizar GPKG movido','','GeoPackage (*.gpkg)')
                if not base:
                    return
                if r['execucao_uid'] not in {x['execucao_uid'] for x in listar(base)}:
                    raise ValueError('O arquivo escolhido não contém a execução selecionada.')
            if self.modalidade.currentIndex()==0:
                self.modalidade.setCurrentIndex(1)
            return self.abrir_auditoria(base,r['execucao_uid'])
        except Exception as erro:
            QMessageBox.warning(self,'Auditoria não aberta',str(erro))

    def abrir_auditoria(self,base,exe):
        if not self.resolver_pendencias():
            return False
        d=carregar_execucao(base,exe)
        from .inspecao import restaurar
        restaurar(d)
        anterior=self.formulario()
        with self.restaurando():
            try:
                self.restaurar_configuracao(d,resolver=self.modalidade.currentIndex()==3)
            except Exception:
                self.restaurar_formulario(anterior)
                raise
        if self.painel and not self.painel.close():
            self.restaurar_formulario(anterior)
            return False
        self.origem_info.setText(f"Origem: {exe} | {len(d['eventos'])} eventos / {len(d['locais'])} locais. "
            f"Agrupamento anterior: distância {d['analise']['opcoes']['distancia']} m; "
            f"extensão {d['analise']['opcoes']['extensao_maxima']} m.")
        try:
            self.publicar_auditoria(d,str(Path(base).resolve()))
        except Exception:
            self.restaurar_formulario(anterior)
            raise
        self.auditoria_origem=d;self.base_origem=str(Path(base).resolve())
        self._modo_fixo=self.modalidade.currentIndex()
        if self.modalidade.currentIndex() in (2,3):
            self.definir_estado(self.estado_configuracao())
        self._config_inicial=self.formulario()
        lembrar(self.base_origem,exe)
        self.mudar_modalidade()
        if self.modalidade.currentIndex()==1:
            self.abrir_painel()
        return True

    def restaurar_configuracao(self,d,resolver=False):
        with self.restaurando():
            return self._restaurar_configuracao(d,resolver)

    def _restaurar_configuracao(self,d,resolver=False):
        p=perfil(d);g=p['geometria'];a=p['agrupamento']
        self.tolerancia.setValue(g['tolerancia_geometrica'])
        self.continuidade.setValue(g['distancia_continuidade'])
        self.crs.setCrs(QgsCoordinateReferenceSystem(g['crs']))
        self.agrupar.setChecked(a['habilitado'])
        self.distancia_locais.setValue(a['distancia']);self.extensao_locais.setValue(a['extensao_maxima'])
        c=d.get('controle_versao',{})
        self.nome_auditoria.setText(c.get('nome',''));self.projeto_auditoria.setText(c.get('projeto',''))
        self._parametros_recuperados=g.copy()
        if not resolver:
            return
        def realocar(f):
            return QFileDialog.getOpenFileName(self,'Localizar fonte: '+f['camada'],'',
                'Dados vetoriais (*.shp *.gpkg);;Todos (*)')[0]
        fontes,avisos=resolver_fontes(p,self.projeto,realocar,permitir_campos_ausentes=True)
        self.atualizar_camadas(interno=True)
        self._origens_configuradas={c.id():origem for origem,c in fontes.items()}
        for tabela in (self.redes,self.limites):
            for linha in range(tabela.rowCount()):
                item=tabela.item(linha,0)
                origem=self._origens_configuradas.get(item.data(Qt.UserRole))
                item.setCheckState(Qt.Checked if origem else Qt.Unchecked)
                if not origem:
                    continue
                f=next(f for f in p['fontes'] if f['origem']==origem)
                valores={2:f.get('campo_id')}
                if tabela is self.limites:
                    valores.update({3:f.get('campo_nome'),4:f.get('modo')})
                else:
                    extras=p.get('campos_interesse',{}).get(origem,{})
                    valores.update({3:extras.get('setor'),4:extras.get('diametro'),5:extras.get('material'),6:f.get('campo_nome')})
                for coluna,v in valores.items():
                    combo=tabela.cellWidget(linha,coluna);indice=combo.findData(v)
                    if indice<0:
                        indice=combo.findData(None)
                        if indice<0:
                            raise ValueError('Configuração indisponível: '+str(v))
                    combo.setCurrentIndex(indice)
        if avisos:
            self.status.setText('\n'.join(avisos))

    def publicar_auditoria(self,d,base,camadas=None):
        from .inspecao import contagens
        from .visualizacao import texto_resumo
        resultado,analise,novas=publicar(d,base,self.projeto,camadas)
        if self.painel:
            self.painel.desativar()
        from qgis.PyQt import sip
        for c in self.camadas_geradas+novas:
            if not sip.isdeleted(c) and c.isValid() and hasattr(c,'removeSelection'):
                c.removeSelection()
        self.resultado,self.analise,self.camadas_geradas=resultado,analise,novas
        self.dossie=d;self.base_revisao=base;self.painel=None
        configuracao=perfil(d)
        linhas=['CONFIGURAÇÃO DOS RESULTADOS ATIVOS (somente leitura)']
        for f in configuracao['fontes']:
            linhas.append(f"{'Limite' if f.get('modo') else 'Rede'}: {f['camada']} | "
                f"modo: {f.get('modo') or 'rede linear'} | ID: {f.get('campo_id') or '(sem campo)'} | "
                f"exibição: {f.get('campo_nome') or '(sem campo)'}")
        g=configuracao['geometria'];o=configuracao['agrupamento']
        linhas.append(f"CRS: {g['crs']}; tolerância: {g['tolerancia_geometrica']} m; continuidade: {g['distancia_continuidade']} m.")
        linhas.append(f"Agrupamento: {o['habilitado']}; busca: {o['distancia']} m; extensão: {o['extensao_maxima']} m.")
        self.configuracao_ativa.setPlainText('\n'.join(linhas))
        self.exportar.setEnabled(True)
        c=contagens(d)
        self.resumo.setPlainText(texto_resumo(self.resultado)+f"\nLocais de investigação: {c['locais']}"
            f"\nEventos ambíguos: {c['eventos_ambiguos']}\nLocais com ambiguidade: {c['locais_ambiguos']}"
            f"\nExecução: {d['execucao_uid']}\nBase: {base or 'ainda não persistida'}")
        self.status.setText('Auditoria disponível para inspeção, revisão e novas exportações.')
        self._modo_fixo=self.modalidade.currentIndex()
        self._config_inicial=self.formulario();self._formulario_resultado=self.formulario()
        if self.estado==Estado.PROCESSANDO:
            self.definir_estado(Estado.CONCLUIDO)
        self.definir_estado(Estado.INSPECIONANDO)

    def opcoes_agrupamento(self):
        return OpcoesLocais(self.agrupar.isChecked(),self.distancia_locais.value(),self.extensao_locais.value())

    def vincular_base(self,base):
        """A primeira revisão/exportação torna as temporárias detectáveis no projeto."""
        import json
        self.base_revisao=str(base)
        for c in self.camadas_geradas:
            ids=json.loads(c.customProperty('auditoria_fronteiras/execucoes','[]'))
            c.setCustomProperty('auditoria_fronteiras/execucoes',json.dumps(sorted(set(ids+[self.dossie['execucao_uid']]))))
            c.setCustomProperty('auditoria_fronteiras/base',str(base))
        lembrar(base,self.dossie['execucao_uid'])

    def mostrar_comparacao(self,titulo,linhas,continuar='Continuar'):
        dlg=QDialog(self);dlg.setWindowTitle(titulo);dlg.resize(730,470)
        layout=QVBoxLayout(dlg);texto=QPlainTextEdit();texto.setReadOnly(True)
        texto.setPlainText('\n'.join(linhas));layout.addWidget(texto)
        botoes=QHBoxLayout();b=QPushButton(continuar);b.clicked.connect(dlg.accept)
        cancelar=QPushButton('Cancelar');cancelar.clicked.connect(dlg.reject)
        botoes.addWidget(b);botoes.addWidget(cancelar);layout.addLayout(botoes)
        return dlg.exec()==QDialog.Accepted

    def salvar_operacao(self,preparada):
        cmp=preparada['comparacao'];origem=preparada['origem'];novo=preparada['novo']
        linhas=[f'{k}: {v}' for k,v in cmp.items() if k not in ('correspondencias','locais_herdaveis')]
        linhas.insert(0,f"Eventos: {len(origem['eventos'])} → {len(novo['eventos'])}. Política confirmada: {self._plano_operacao['modo'] if self._plano_operacao else '(ausente)'}.")
        linhas+=['Mantidos: mesma composição e contexto técnico. Divididos: locais antigos com vários sucessores.',
            'Fundidos: locais novos com vários predecessores. Novos inclui todas as composições alteradas.',
            'Sem correspondência é um subconjunto de novos. Agrupamento desabilitado: nenhum local; eventos preservados.']
        if not self.mostrar_comparacao('Resultado efetivo — comparação entre versões',linhas,'Gravar versão confirmada'):
            return False
        plano=self._plano_operacao
        if plano is None:
            raise RuntimeError('Escolha e confirme a política antes do processamento.')
        modo=plano['modo'];destino=plano['destino'];confirmado=plano['confirmado']
        novo['controle_versao'].update(nome=self.nome_auditoria.text(),projeto=self.projeto_auditoria.text())
        saida=gravar_versao(self.base_origem,origem['execucao_uid'],novo,modo,destino,confirmado,
            token_origem=preparada['token_origem'])
        self.publicar_auditoria(saida['dossie'],saida['base'])
        self.auditoria_origem=self.dossie;self.base_origem=saida['base']
        lembrar(saida['base'],novo['execucao_uid'])
        self.resumo.appendPlainText('\nComparação: '+'; '.join(linhas[:12]))
        if saida['backup']:
            self.resumo.appendPlainText('\nBackup verificado: '+saida['backup']['backup'])
        return True

    def escolher_politica(self,origem,crs):
        nomes=['Criar nova versão (padrão)','Criar nova versão e reconciliar','Substituir versão ativa (com backup)']
        s,ok=QInputDialog.getItem(self,'Salvar versão','Política:',nomes,0,False)
        if not ok:
            return None
        modo=('NOVA','RECONCILIAR','SUBSTITUIR')[nomes.index(s)]
        destino=self.base_origem
        from .versoes import listar
        revisados=sum(bool(l['revisao'].get('uid')) for l in origem['locais'])
        confirmado=False
        if modo=='SUBSTITUIR':
            from .persistencia import historico
            historicos=sum(len(historico(self.base_origem,origem['execucao_uid'],l['uid'])) for l in origem['locais'])
            msg=(f"Execução: {origem['execucao_uid']}\n{len(origem['eventos'])} eventos; {len(origem['locais'])} locais; "
                f"{revisados} locais revisados; {historicos} registros históricos.\nArquivo: {destino}\n"
                'Um backup completo será criado e verificado. A versão anterior permanecerá consultável, '
                'marcada como substituída; a nova será ativa. Confirmar?')
            confirmado=QMessageBox.question(self,'Confirmar substituição',msg,QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes
            if not confirmado:
                return None
        elif crs!=origem['contexto']['parametros']['crs']:
            destino,_=QFileDialog.getSaveFileName(self,'Novo CRS: escolher novo GeoPackage','','GeoPackage (*.gpkg)')
            if not destino:
                return None
            if not destino.lower().endswith('.gpkg'):
                destino+='.gpkg'
        return dict(modo=modo,destino=destino,confirmado=confirmado)

    def executar_regeneracao(self):
        if self._executando or self.estado not in EDITAVEIS:
            return
        if not self.auditoria_origem:
            self.escolher_auditoria()
            return
        if not self.preparar_exportacao():
            return
        if self.painel and not self.painel.close():
            return
        anterior=self.estado
        self._formulario_em_execucao=self.formulario()
        self.definir_estado(Estado.CONFIRMANDO)
        try:
            if not self.confirmar_processamento(regeneracao=True):
                self.definir_estado(anterior)
                return
        except Exception as erro:
            self.definir_estado(Estado.ERRO)
            QMessageBox.warning(self,'Operação não iniciada',str(erro))
            return
        from qgis.PyQt.QtWidgets import QProgressDialog
        progresso=QProgressDialog('Reagrupando eventos persistidos…','Cancelar',0,0,self)
        progresso.setWindowModality(Qt.ApplicationModal);progresso.show()
        self._executando=True
        self.definir_estado(Estado.PROCESSANDO)
        def cancelar():
            QApplication.processEvents()
            return progresso.wasCanceled()
        try:
            preparada=preparar_regeneracao(self.base_origem,self.auditoria_origem['execucao_uid'],
                self.opcoes_agrupamento(),cancelar)
            progresso.close()
            self.salvar_operacao(preparada)
        except Exception as erro:
            from .modelos import Cancelado
            self.definir_estado(anterior if isinstance(erro,Cancelado) else Estado.ERRO)
            QMessageBox.warning(self,'Regeneração não gravada',str(erro)+'\nA versão anterior foi preservada.')
        finally:
            progresso.close();self._executando=False
            if self.estado==Estado.PROCESSANDO:
                self.definir_estado(anterior)
            self.aplicar_estado()

    def preparar_reprocessamento(self,redes,limites,parametros,opcoes):
        if not self.auditoria_origem:
            raise ValueError('Selecione a auditoria de origem antes de reprocessar.')
        proposta=configuracao_proposta(redes,limites,parametros,opcoes,self.campos_inspecao(redes),
            perfil(self.auditoria_origem).get('exportacao'))
        cmp=comparar_configuracoes(perfil(self.auditoria_origem),proposta)
        linhas=[f"{r['categoria']} / {r['item']}: {r['antes']} → {r['depois']}" for r in cmp['diferencas']]
        if cmp['fontes_sem_assinatura_anterior']:
            linhas.append('Base legada sem assinaturas do conteúdo das fontes: equivalência de entrada não comprovada.')
        linhas.append('Um reprocessamento pode alterar eventos, locais e revisões. Quantidades serão conhecidas após a execução.')
        if cmp['recomendar_regerar']:
            pergunta=QMessageBox.question(self,'Preferir regeneração independente?',
                'As alterações detectadas não exigem o núcleo geométrico. Regerar somente os locais? '
                'Escolha Não para forçar o processamento completo.',QMessageBox.Yes|QMessageBox.No|QMessageBox.Cancel,QMessageBox.Yes)
            if pergunta==QMessageBox.Yes:
                self.executar_regeneracao();return None
            if pergunta==QMessageBox.Cancel:
                return None
        if not self.mostrar_comparacao('Configurações antes / depois',linhas,'Executar processamento completo'):
            return None
        with abrir_ro(self.base_origem) as con:
            esperado=token(con,self.auditoria_origem['execucao_uid'])
        return dict(configuracao=proposta,token_origem=esperado)

    def campos_inspecao(self,redes):
        from .entradas import digest
        campos={}
        for config in redes:
            for linha in range(self.redes.rowCount()):
                if self.redes.item(linha,0).data(Qt.UserRole)==config.camada.id():
                    origem=config.chave_origem or digest([config.camada.providerType(),config.camada.source()])
                    campos[origem]={n:self.redes.cellWidget(linha,c).currentData()
                        for n,c in [('setor',3),('diametro',4),('material',5)]}
        return campos
