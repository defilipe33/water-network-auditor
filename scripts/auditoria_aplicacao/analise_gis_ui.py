"""Análise contextual do cadastro, sem abrir o formulário legado de entradas."""
from pathlib import Path
from uuid import uuid4
import sqlite3

from qgis.PyQt.QtCore import Qt, QTimer, pyqtSlot
from qgis.PyQt.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QLineEdit,
    QDoubleSpinBox, QFileDialog, QPlainTextEdit, QMessageBox, QPushButton, QScrollArea)
from qgis.core import QgsProject, QgsVectorLayer, QgsCoordinateTransformContext
from qgis.gui import QgsProjectionSelectionWidget

from .modelo_gis_ui import aviso, botao, expansivel, formulario, tabela, linha
from .modelo_gis import CATEGORIAS, identificar, revisoes
from .analise_modelo_gis import AREAS, OBJETIVOS, preparar, executar, reservar, persistir, publicar, conferir_contexto


class AnaliseGIS(QWidget):
    def __init__(self, central):
        super().__init__()
        self.central, self.app = central, central.app
        self.objetivo = 'verificar'
        self.base = self.dossie = self.selecionado = None
        self._executando = False
        self._geracao = 0
        self._observadas = set()
        self._pagina = 0
        externo = QVBoxLayout(self); externo.setContentsMargins(0, 0, 0, 0)
        rolagem = self.rolagem = QScrollArea(); rolagem.setWidgetResizable(True)
        conteudo = QWidget(); rolagem.setWidget(conteudo); externo.addWidget(rolagem)
        v = QVBoxLayout(conteudo)
        botao(v, '‹ Investigar minha rede', self.voltar)
        self.titulo = aviso(); self.titulo.setStyleSheet('font-weight:600'); v.addWidget(self.titulo)
        self.descricao = aviso(); v.addWidget(self.descricao)
        self.resumo = aviso(); v.addWidget(self.resumo)
        self.nome = QLineEdit()
        formulario(v).addRow('Nome do trabalho', self.nome)
        _, categorias = expansivel(v, 'Escopo e fontes cadastradas')
        self.areas = {}
        for k in AREAS:
            b = QCheckBox(CATEGORIAS[k].nome); b.setChecked(True); categorias.addWidget(b); self.areas[k] = b
        self.fontes_info = aviso(); categorias.addWidget(self.fontes_info)
        _, avancado = expansivel(v, 'Parâmetros da análise')
        f = formulario(avancado)
        self.crs = QgsProjectionSelectionWidget(); self.crs.setCrs(QgsProject.instance().crs())
        f.addRow('CRS projetado em metros', self.crs)
        self.tolerancia = QDoubleSpinBox(); self.tolerancia.setDecimals(3); self.tolerancia.setRange(0, 100); self.tolerancia.setValue(.01)
        self.continuidade = QDoubleSpinBox(); self.continuidade.setDecimals(3); self.continuidade.setRange(0, 1000); self.continuidade.setValue(1)
        f.addRow('Tolerância geométrica (m)', self.tolerancia)
        f.addRow('Busca de continuidades candidatas (m)', self.continuidade)
        self.agrupamento = QDoubleSpinBox(); self.agrupamento.setDecimals(2); self.agrupamento.setRange(0, 1000); self.agrupamento.setValue(5)
        f.addRow('Organização de locais próximos (m)', self.agrupamento)
        avancado.addWidget(aviso('Agrupar locais organiza a investigação; não conecta tubulações nem remove eventos individuais.'))
        self.pasta = QLineEdit(str(self.app.catalogo.raiz / 'analises_gis')); f.addRow('Pasta dos trabalhos', self.pasta)
        botao(avancado, 'Escolher pasta…', self.escolher_pasta)
        self.executar_b = botao(v, 'Executar análise', self.iniciar); self.executar_b.setObjectName('Principal')
        self.info = aviso(); v.addWidget(self.info)
        self.lista = tabela(['Local', 'Ocorrências', 'Tubulações', 'Situação'])
        self.lista.setMinimumHeight(100); v.addWidget(self.lista, 1)
        self.lista.currentCellChanged.connect(self.escolher_local)
        nav = QHBoxLayout(); v.addLayout(nav)
        botao(nav, 'Anteriores', lambda: self.paginar(-1)); botao(nav, 'Próximos', lambda: self.paginar(1))
        self.pagina_info = aviso(); nav.addWidget(self.pagina_info)
        self.observacao = QPlainTextEdit(); self.observacao.setPlaceholderText('Observação do local — opcional'); self.observacao.setMaximumHeight(70); v.addWidget(self.observacao)
        self._resultado_timer = QTimer(self); self._resultado_timer.setSingleShot(True)
        self._resultado_timer.timeout.connect(self.mostrar_resultados)
        faixa = QHBoxLayout(); v.addLayout(faixa)
        self.salvar_b = botao(faixa, 'Salvar observação', self.salvar_observacao)
        botao(faixa, 'Destacar local', self.destacar)
        botao(faixa, 'Enquadrar', self.central.mapa.aproximar)
        _, saidas = expansivel(v, 'Histórico e exportações')
        botao(saidas, 'Histórico do local', self.historico)
        botao(saidas, 'Exportar Shapefile e tabelas…', self.exportar_shp)
        botao(saidas, 'Abrir visualizador anterior (opcional)', self.abrir_legado)
        self.historico_info = aviso(); saidas.addWidget(self.historico_info)
        self._temporario = None

    @pyqtSlot()
    def mostrar_resultados(self):
        self.rolagem.ensureWidgetVisible(self.observacao, 0, 8)

    def voltar(self):
        if self.resolver():
            self.central.area.setCurrentIndex(self.central.area.findData('investigar'))
            self.central.mudar_area()

    def abrir(self, objetivo):
        if not self.resolver(): return False
        projeto = self.central.projetos.atual() or {}
        contexto = (self.dossie or {}).get('configuracao', {}).get('modelo_gis', {})
        origem = contexto.get('projeto_uid')
        if self.dossie and ((origem and origem != projeto.get('uuid')) or
                            (contexto.get('objetivo') and contexto['objetivo'] != objetivo)):
            self.dossie = self.base = self.selecionado = None
            self.observacao.clear(); self.listar()
        self.objetivo = objetivo
        self.executar_b.setText('Executar análise')
        titulo, _, descricao = OBJETIVOS[objetivo]
        self.titulo.setText(titulo); self.descricao.setText(descricao)
        self.nome.setText(titulo)
        fontes = self.central.modelo_gis.fontes
        redes = [f for f in fontes if f['categoria'] == 'PIPE']
        areas = [f for f in fontes if f['categoria'] in AREAS]
        self.resumo.setText(f'{len(redes)} fonte(s) de tubulações · {len(areas)} fonte(s) de áreas. '
            'Filtros e campos vêm do Modelo GIS. Equipamentos permanecem como contexto, sem conexão inferida.')
        for k, b in self.areas.items(): b.setVisible(any(f['categoria'] == k for f in fontes))
        self.fontes_info.setText('\n'.join(f['nome'] + ' · ' + CATEGORIAS[f['categoria']].nome +
            ' · ' + (f['filtro'] or 'todas as feições') for f in fontes))
        from auditoria_fronteiras.entradas import crs_processamento
        from auditoria_fronteiras import Parametros
        for f in redes:
            try:
                crs_processamento(Parametros(crs=f['crs_wkt'])); self.crs.setCrs(identificar(f, self.central.modelo_gis.camadas()).crs()); break
            except (ValueError, AttributeError): continue
        return True

    def escolher_pasta(self):
        p = QFileDialog.getExistingDirectory(self, 'Pasta dos trabalhos', self.pasta.text())
        if p: self.pasta.setText(p)

    def fonte_mudou(self, *_): self._geracao += 1

    def iniciar(self):
        if self._executando or self.central.ocupado(): return
        if not self.resolver() or not self.central.modelo_gis.resolver(): return
        from auditoria_fronteiras import Parametros
        m = self.central.modelo_gis
        try:
            projeto = self.central.projetos.atual()
            if not projeto: raise ValueError('Crie ou escolha um projeto e configure o Modelo GIS.')
            hist = revisoes(projeto)
            preparacao = preparar(m.fontes, m.camadas(), Parametros(
                crs=self.crs.crs().toWkt(), tolerancia_geometrica=self.tolerancia.value(),
                distancia_continuidade=self.continuidade.value(), distancia_agrupamento=self.agrupamento.value()), QgsProject.instance().transformContext(),
                self.objetivo, [k for k, b in self.areas.items() if b.isChecked()],
                projeto['uuid'], hist[-1]['uuid'] if hist else None)
            for f in m.fontes:
                c = identificar(f, m.camadas())
                if c is not None and isinstance(c, QgsVectorLayer) and c.id() not in self._observadas:
                    self._observadas.add(c.id())
                    for s in ('dataChanged', 'dataSourceChanged', 'updatedFields', 'crsChanged', 'subsetStringChanged'):
                        getattr(c, s).connect(self.fonte_mudou)
            geracao = self._geracao
            temp, destino = reservar(self.pasta.text(), preparacao.parametros.crs)
            self._temporario = temp
            nome, projeto_nome = self.nome.text().strip() or OBJETIVOS[self.objetivo][0], projeto['nome']
            self._executando = True; self.executar_b.setEnabled(False)
            self.info.setText('Analisando as fontes cadastradas. Acompanhe etapas e cancelamento em Janelas / atividades.')
            def trabalho(parar, etapa):
                d = executar(preparacao, nome, projeto_nome, parar, etapa)
                etapa(0, 'Gravando e verificando o trabalho; nenhuma versão parcial será publicada')
                persistir(temp, d, parar)
                return d
            def pronto(d):
                p = self.central.projetos.atual() or {}; rs = revisoes(p)
                conferir_contexto(preparacao, m.fontes, list(m.camadas()), p.get('uuid'), rs[-1]['uuid'] if rs else None)
                if geracao != self._geracao: raise ValueError('Os dados mudaram durante a análise; execute novamente.')
                self.app.atividades.atual.critica('Publicando o trabalho verificado')
                publicar(temp, destino); self._temporario = None
                self.receber(d, destino)
                itens = self.app.catalogo.registrar(destino)
                registro = next(r for r in itens if r['uuid'] == d['execucao_uid'])
                self.central.projetos.vincular(registro)
                self.carregar_camadas()
                self.info.setText(f'Trabalho salvo · {len(d["eventos"])} ocorrências · {len(d["locais"])} locais. '
                    'Cruzamentos e continuidades são indícios geométricos, não conexões comprovadas.\n' + '\n'.join(preparacao.avisos))
                self.finalizar()
            worker = self.app.atividades.executar_thread(OBJETIVOS[self.objetivo][0], projeto_nome, trabalho, pronto, self.falhou)
            operacao = self.app.atividades.atual
            def terminou():
                # O gerenciador descarta resultados recebidos depois de Cancelar.
                # Nesse caso pronto() não roda; restaurar botões e retirar só o temporário próprio.
                if self._executando and operacao.estado == 'CANCELADO':
                    self.falhou('Análise cancelada em ponto seguro.')
            worker.finished.connect(terminou)
        except (ValueError, OSError, RuntimeError, sqlite3.Error) as e: self.falhou(str(e))

    def finalizar(self):
        self._executando = False; self.executar_b.setEnabled(True)

    def falhou(self, texto):
        if self._temporario:
            try: self._temporario.unlink(missing_ok=True)
            except OSError: texto += ' O arquivo temporário foi preservado para diagnóstico.'
            self._temporario = None
        self.info.setText(texto + ' Trabalhos anteriores e fontes originais preservados.')
        self.finalizar()

    def receber(self, dossie, base):
        self.dossie, self.base, self.selecionado = dossie, str(base), None
        self.observacao.clear()
        self._pagina = 0; self.listar()
        self._resultado_timer.start(0)

    def abrir_persistida(self, registro):
        if self.central.ocupado() or not self.resolver(): return False
        from auditoria_fronteiras.persistencia import carregar_execucao
        from auditoria_fronteiras.versoes import abrir_ro
        projeto = self.central.projetos.dados['ativo']
        def trabalho(parar, etapa):
            if parar(): raise InterruptedError('Abertura cancelada.')
            with abrir_ro(registro['base']) as con:
                d = carregar_execucao(registro['base'], registro['uuid'], conexao=con)
            if parar(): raise InterruptedError('Abertura cancelada.')
            return d
        def pronto(d):
            if self.central.projetos.dados['ativo'] != projeto:
                raise ValueError('O projeto mudou durante a abertura. Contexto anterior preservado.')
            contexto = d.get('configuracao', {}).get('modelo_gis', {})
            objetivo = contexto.get('objetivo')
            if objetivo in OBJETIVOS:
                self.objetivo = objetivo
                self.titulo.setText(OBJETIVOS[objetivo][0]); self.descricao.setText(OBJETIVOS[objetivo][2])
            self.receber(d, registro['base']); self.nome.setText(d.get('controle_versao', {}).get('nome', 'Trabalho GIS'))
            self.resumo.setText('Trabalho persistido · fontes e filtros da execução preservados. '
                               'Executar novamente utiliza a configuração atual do Modelo GIS.')
            self.executar_b.setText('Executar nova análise com o cadastro atual')
            self.carregar_camadas(); self.info.setText('Trabalho recuperado, com observações e histórico. Fontes não reprocessadas.')
        self.app.atividades.executar_thread('Abrindo trabalho GIS', registro.get('nome', 'Auditoria GIS'), trabalho, pronto, self.info.setText)
        return True

    def listar(self):
        self.lista.blockSignals(True); self.lista.setRowCount(0)
        itens = (self.dossie or {}).get('locais', [])
        self._visiveis = itens[self._pagina * 200:(self._pagina + 1) * 200]
        for l in self._visiveis:
            r = l['registro']; linha(self.lista, [r['LOCAL'], r['N_EVENTOS'], r['N_TUBOS'], l['revisao']['situacao']])
        self.lista.blockSignals(False)
        self.pagina_info.setText(f'{len(self._visiveis)} de {len(itens)} locais · página {self._pagina + 1}')
        if self._visiveis: self.lista.setCurrentCell(0, 0)

    def paginar(self, delta):
        if not self.resolver(): return
        total = len((self.dossie or {}).get('locais', []))
        self._pagina = max(0, min(max(0, (total - 1) // 200), self._pagina + delta)); self.listar()

    def escolher_local(self, atual, coluna=0, anterior=-1, *_):
        if not self.resolver():
            self.lista.blockSignals(True)
            if anterior >= 0: self.lista.setCurrentCell(anterior, 0)
            self.lista.blockSignals(False); return
        self.selecionado = self._visiveis[atual] if 0 <= atual < len(self._visiveis) else None
        self.observacao.setPlainText(self.selecionado['revisao']['observacoes'] if self.selecionado else '')

    def pendente(self):
        return bool(self.selecionado and self.observacao.toPlainText() != self.selecionado['revisao']['observacoes'])

    def resolver(self):
        if not self.pendente(): return True
        r = QMessageBox.question(self, 'Observação não salva', 'Salvar a observação deste local?',
                                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel)
        if r == QMessageBox.Save: return self.salvar_observacao()
        if r == QMessageBox.Discard:
            self.observacao.setPlainText(self.selecionado['revisao']['observacoes']); return True
        return False

    def salvar_observacao(self):
        if not self.selecionado or not self.base: return False
        from auditoria_fronteiras.persistencia import salvar_revisao
        l = self.selecionado
        try:
            texto = self.observacao.toPlainText().strip()
            if not texto: raise ValueError('Escreva uma observação para registrar.')
            rev = salvar_revisao(self.base, self.dossie['execucao_uid'], l['uid'], 'EM_ANALISE', texto,
                                esperada=l['revisao'].get('uid'))
            l['revisao'] = rev; self.observacao.setPlainText(texto)
            l['registro']['SITUACAO'] = rev['situacao']
            item = self.lista.item(self.lista.currentRow(), 3)
            if item is not None: item.setText(rev['situacao'])
            self.info.setText('Observação salva no histórico deste trabalho.'); return True
        except (ValueError, OSError, RuntimeError, sqlite3.Error) as e:
            self.info.setText(str(e) + ' Texto preservado.'); return False

    def destacar(self):
        if not self.selecionado: return
        from qgis.core import QgsGeometry, QgsPointXY, QgsCoordinateReferenceSystem
        r = self.selecionado['registro']
        g = QgsGeometry.fromPointXY(QgsPointXY(r['X'], r['Y']))
        self.central.mapa.destacar_geometria(g, QgsCoordinateReferenceSystem(self.dossie['contexto']['parametros']['crs']), 'Local ' + str(r['LOCAL']))

    def historico(self):
        if self.selecionado:
            from auditoria_fronteiras.persistencia import historico
            try:
                rs = historico(self.base, self.dossie['execucao_uid'], self.selecionado['uid'])
                self.historico_info.setText('\n'.join(str(r.get('data_utc', r.get('data', ''))) + ' · ' + r['observacoes'] for r in rs) or 'Nenhuma observação registrada.')
            except (ValueError, OSError, sqlite3.Error) as e: self.historico_info.setText(str(e))

    def carregar_camadas(self):
        from auditoria_fronteiras.organizacao_camadas import publicar as organizar
        import json
        uid = self.dossie['execucao_uid']; nome = self.dossie['controle_versao']['nome']
        for tabela_, titulo, papel in [('EVENTOS_FRONTEIRAS', 'Ocorrências geométricas', 'apresentacao'), ('PONTOS_INVESTIGACAO', 'Locais de investigação', 'locais')]:
            c = QgsVectorLayer(self.base + '|layername=' + tabela_, titulo, 'ogr')
            if not c.isValid(): raise ValueError('Não foi possível abrir a camada persistida: ' + titulo)
            c.setCustomProperty('wna/tecnico', tabela_)
            c.setCustomProperty('auditoria_fronteiras/papel', papel)
            c.setCustomProperty('auditoria_fronteiras/execucoes', json.dumps([uid]))
            c.setCustomProperty('auditoria_fronteiras/base', self.base)
            organizar(c, QgsProject.instance(), 'gis', uid, self.base, nome)

    def abrir_legado(self):
        if self.base and self.resolver():
            self.app.abrir_registro(dict(tipo='AUDITORIA_GIS', base=self.base, uuid=self.dossie['execucao_uid']))

    def exportar_shp(self):
        if not self.dossie or self.central.ocupado() or not self.resolver(): return
        pasta = QFileDialog.getExistingDirectory(self, 'Pasta para exportação SHP')
        if not pasta: return
        from copy import deepcopy
        from auditoria_fronteiras.exportacao import exportar_shp
        destino = Path(pasta) / ('SHP_' + uuid4().hex[:12])
        temporario = destino.with_name('.' + destino.name)
        d = deepcopy(self.dossie)
        ctx = QgsCoordinateTransformContext(QgsProject.instance().transformContext())
        def pronto(_):
            if temporario.resolve().parent != destino.resolve().parent or not temporario.name.startswith('.SHP_'):
                raise ValueError('Destino temporário inválido; arquivos preservados.')
            if destino.exists(): raise FileExistsError('Destino já existe; exportação anterior preservada.')
            self.app.atividades.atual.critica('Publicando exportação SHP verificada')
            temporario.rename(destino)
            self.info.setText('Exportação SHP concluída · ' + destino.name)
            self.info.setToolTip(str(destino))
        self.app.atividades.executar_thread('Exportar Shapefile e tabelas', self.nome.text(),
            lambda parar, etapa: exportar_shp(d, temporario, ctx, parar), pronto,
            lambda texto: self.info.setText(texto + ' Exportação não publicada; temporário em ' + str(temporario)))
