"""Importação hierárquica e apresentação offline de Selection Sets HMI."""
import json
from pathlib import Path
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QLineEdit,QTreeWidget,QTreeWidgetItem,QFileDialog,QMessageBox,QCheckBox,QInputDialog
from qgis.PyQt import sip
from auditoria_fronteiras.ui_comum import adaptar_janela
from auditoria_fronteiras.atividade import sistema,acompanhada
from . import selection_sets as leitor,selection_sets_persistencia as store


class SelectionSetsDialog(QDialog):
    def __init__(self,painel):
        super().__init__(painel);self.painel=painel;self.worker=None;self.leitura=store.ultima(painel.base,painel.pacote);self.manifesto=None;self.setWindowTitle('SELECTION SETS WATERGEMS');self.resize(950,680)
        v=QVBoxLayout(self);v.addWidget(QLabel('IMPORTAR / ATUALIZAR SELECTION SETS DO WATERGEMS'))
        self.busca=QLineEdit();self.busca.setPlaceholderText('Pesquisar nome original ou caminho');v.addWidget(self.busca);self.busca.textChanged.connect(self.filtrar)
        h=QHBoxLayout();v.addLayout(h)
        for t,fn in [('Selecionar modelo / atualizar…',self.ler),('Recuperar importação salva',self.recuperar),('Importar conjuntos marcados',self.importar)]:b=QPushButton(t);b.clicked.connect(fn);h.addWidget(b)
        self.estado=QLabel('Selecione o SQLite do mesmo modelo da investigação. Nenhum modelo será modificado.');self.estado.setWordWrap(True);v.addWidget(self.estado)
        self.arvore=QTreeWidget();self.arvore.setColumnCount(7);self.arvore.setHeaderLabels(['Nome original','Caminho hierárquico','Tipo','Elementos declarados','Situação','ID técnico','Quantidade por tipo']);v.addWidget(self.arvore,1)
        self.contorno=QCheckBox('Gerar envolvente aproximada (convex hull), sem representar limite oficial');v.addWidget(self.contorno);self.shp=QCheckBox('Acrescentar cópia Shapefile às camadas GeoPackage');v.addWidget(self.shp)
        h=QHBoxLayout();v.addLayout(h)
        for t,fn in [('Mostrar camadas no QGIS',self.mostrar),('Destacar seleção / zoom explícito',self.destacar),('Filtrar ocorrências por membros',self.aplicar_filtro),('Limpar filtro de conjuntos',self.limpar_filtro),('Relatório ilustrado offline…',self.relatorio),('Relatório com opções de mapa-base…',self.opcoes_relatorio),('Comparar marcados × destaque da árvore',self.comparar),('Comparar com outra investigação…',self.comparar_versoes),('Exportar metadados / diferenças',self.exportar),('Importar lista alternativa CSV…',self.lista_csv)]:b=QPushButton(t);b.clicked.connect(fn);h.addWidget(b)
        self.estado2=QLabel('Pastas e conjuntos são relacionados por IDs, não pelos nomes. Pertencimento não comprova conectividade. Reorganização e estilos na árvore QGIS são locais; salve o projeto para conservá-los.');self.estado2.setWordWrap(True);v.addWidget(self.estado2);b=QPushButton('Fechar');b.clicked.connect(self.close);v.addWidget(b);adaptar_janela(self);self.arvore.setMinimumHeight(220);sistema(painel).vincular(self)
        if self.leitura:self.preencher()
    def selecionados(self):
        ids=[];root=self.arvore.invisibleRootItem()
        def visitar(n):
            if n.data(0,Qt.UserRole) is not None and n.checkState(0)==Qt.Checked:ids.append(n.data(0,Qt.UserRole))
            for k in range(n.childCount()):visitar(n.child(k))
        visitar(root);return set(ids)
    def ids_conjuntos(self,ids=None):
        ids=self.selecionados() if ids is None else set(ids)
        return {r['id'] for r in self.leitura['itens'] if not r['pasta'] and (r['id'] in ids or ids.intersection(r['ancestrais']))}
    def ler(self):
        f,_=QFileDialog.getOpenFileName(self,'Modelo WaterGEMS SQLite','','SQLite (*.sqlite)')
        if not f:return
        p=self.painel.pacote
        def pronto(r):self.leitura=r;self.preencher()
        self.worker=sistema(self.painel).executar_thread('Lendo Selection Sets WaterGEMS','SQLite somente leitura, cenário da base selecionada',lambda cancelar,progresso:leitor.preparar(p,leitor.ler(f,cancelado=cancelar,cenario=p['topologia']['modelo']['cenario'])),pronto,lambda e:self.estado.setText(e+' · modelos e importações anteriores preservados'))
    def preencher(self):
        self.arvore.clear();itens={};rs=self.leitura['itens'];nomes={r['id']:r['nome'] for r in rs}
        for r in sorted(rs,key=lambda r:(len(r['ancestrais']),str(r['id']))):
            pai=itens.get(r.get('pai')) if r['hierarquia']=='RECUPERADA' else None;n=QTreeWidgetItem(pai or self.arvore,[r['nome'],' / '.join(nomes.get(i,str(i)) for i in r['ancestrais']),r['tipo'],str(r['quantidade']),r['situacao']+(' · nome não recuperado' if r.get('nome_resolvido') is False else '')+' · '+r['hierarquia']+' · '+str(r.get('compatibilidade',{})),str(r['id']),str(r.get('por_tipo',{}))]);n.setData(0,Qt.UserRole,r['id']);n.setFlags(n.flags()|Qt.ItemIsUserCheckable|(Qt.ItemIsAutoTristate if r['pasta'] else Qt.NoItemFlags));n.setCheckState(0,Qt.Unchecked);itens[r['id']]=n;n.setToolTip(0,json.dumps(dict(por_tipo=r.get('por_tipo'),erro=r.get('erro'),definicao=r['definicao']),ensure_ascii=False))
        for k in range(7):self.arvore.resizeColumnToContents(k)
        self.arvore.expandToDepth(1);self.estado.setText(str(sum(r['pasta'] for r in rs))+' pastas / '+str(sum(not r['pasta'] for r in rs))+' conjuntos · Modelo '+self.leitura.get('nome_modelo',self.leitura['modelo'])+' · versão '+self.painel.pacote['resultado']['meta']['topologia']['execucao_uid'][:8]+' · cenário '+str(self.leitura['cenario'])+' · hierarquia '+self.leitura['hierarquia']);self.filtrar()
    def filtrar(self):
        texto=self.busca.text().casefold()
        def visitar(n):
            filho=False
            for k in range(n.childCount()):filho=visitar(n.child(k)) or filho
            vis=filho or texto in (n.text(0)+' '+n.text(1)).casefold();n.setHidden(not vis);return vis
        for i in range(self.arvore.topLevelItemCount()):visitar(self.arvore.topLevelItem(i))
    def recuperar(self):
        r=store.ultima(self.painel.base,self.painel.pacote)
        if not r:QMessageBox.information(self,'Sem importações','Nenhuma importação salva nesta investigação.');return
        self.leitura=r;self.preencher()
    def importar(self):
        if not self.leitura:return
        ids=self.ids_conjuntos()
        if not ids and not self.selecionados():QMessageBox.information(self,'Escolha os conjuntos','Marque uma pasta ou um ou mais conjuntos.');return
        def pronto(r):self.leitura=r;self.estado2.setText('Importação salva no histórico existente. '+str(len(ids))+' conjuntos selecionados. '+('Diferenças de versão disponíveis na exportação.' if r.get('comparacao') else ''));self.painel.revisao_atualizada()
        self.worker=sistema(self.painel).executar_thread('Importando Selection Sets','Backup e transação na investigação',lambda cancelar,progresso:store.importar(self.painel.base,self.painel.pacote,self.leitura,ids,cancelar),pronto,lambda e:self.estado2.setText(e+' · versão anterior preservada'))
    @acompanhada('Preparando camadas dos Selection Sets')
    def mostrar(self):
        from .selection_sets_mapa import camadas,carregar
        if not self.leitura:return
        ids=self.ids_conjuntos();regs=store.atuais(self.painel.base,self.painel.pacote);importados={r['dados']['id'] for r in regs}
        if (not ids and not self.selecionados()) or not ids<=importados:QMessageBox.information(self,'Importe primeiro','Selecione conjuntos já importados ou salve a importação antes de gerar camadas.');return
        try:
            for mp in (store.ultima(self.painel.base,self.painel.pacote) or {}).get('apresentacoes',[]):
                if set(mp['ids'])==ids and mp.get('revisoes')==sorted(r['uid'] for r in regs if r['dados']['id'] in ids) and mp['contorno']==self.contorno.isChecked() and Path(mp['manifesto']).is_file():
                    self.manifesto=json.loads(Path(mp['manifesto']).read_text(encoding='utf8'));carregar(self.painel.pacote,self.manifesto);self.estado2.setText('Camadas persistentes recuperadas; estilos, seleção e organização existentes preservados.');return
            pasta=QFileDialog.getExistingDirectory(self,'Pasta de saída das camadas persistentes')
            if not pasta:return
            self.manifesto=camadas(self.painel.base,self.painel.pacote,pasta,ids,self.contorno.isChecked(),self.shp.isChecked(),lambda t,n,total:sistema(self).atual.atualizar(t,n,total),lambda:sistema(self).atual.ponto());carregar(self.painel.pacote,self.manifesto)
            if self.manifesto.get('base'):
                from . import conjuntos_investigacao as obj
                old=obj.atuais(self.painel.base,self.painel.pacote,'IMPORTACAO_SELECTION_WG')[-1];d=dict(old['dados']);d['apresentacoes']=list(d.get('apresentacoes',[]))+[dict(ids=sorted(ids,key=str),revisoes=sorted(r['uid'] for r in regs if r['dados']['id'] in ids),contorno=self.contorno.isChecked(),manifesto=str(Path(self.manifesto['base']).with_suffix('.json')))];obj.salvar(self.painel.base,self.painel.pacote,'IMPORTACAO_SELECTION_WG',d,uid=old['obj_uid'],esperada=old['uid'])
            self.estado2.setText('Camadas próprias carregadas. Edite estilos e organização no QGIS e salve o projeto. Zoom permanece sob seu controle.')
        except Exception as e:QMessageBox.warning(self,'Camadas não publicadas',str(e)+' · fontes originais preservadas');return False
    def destacar(self):
        if not self.painel.pacote['resultado']['meta']['parametros'].get('espacial_habilitado'):QMessageBox.information(self,'Referência espacial pendente','Valide CRS/unidades antes dos destaques; consulta dos conjuntos continua disponível.');return
        ids=store.escopo(self.painel.base,self.painel.pacote,self.ids_conjuntos());m=self.painel.mapa;m.limpar()
        for i in ids:
            g=(self.painel.pacote.get('geometrias') or {}).get(i)
            if g:m.adicionar(g,'#008a80')
        if ids and QMessageBox.question(self,'Aproximar conjuntos','Ajustar a extensão aos elementos destacados?',QMessageBox.Yes|QMessageBox.No)==QMessageBox.Yes:self.painel.mapa.aproximar()
    def aplicar_filtro(self):
        if not self.painel.resolver_formularios():return
        self.painel._ss_escopo=store.escopo(self.painel.base,self.painel.pacote,self.ids_conjuntos());self.painel.filtrar();self.estado2.setText('Filtro por identidade WG: pelo menos um membro. Combina por E com os filtros existentes; não altera o grafo dos corredores.')
    def limpar_filtro(self):self.painel._ss_escopo=None;self.painel.filtrar()
    def comparar(self):
        if not self.leitura:return
        n=self.arvore.currentItem()
        if not n:return
        from .selection_sets_persistencia import comparar_conjuntos
        a=self.ids_conjuntos();b=self.ids_conjuntos([n.data(0,Qt.UserRole)]);regs=store.atuais(self.painel.base,self.painel.pacote);self._comparacao=comparar_conjuntos([r for r in regs if r['dados']['id'] in a],[r for r in regs if r['dados']['id'] in b]);self.estado2.setText(str(len(self._comparacao['comuns']))+' comuns / '+str(len(self._comparacao['somente_a']))+' somente marcados / '+str(len(self._comparacao['somente_b']))+' somente destaque. Exportação conserva os IDs completos.')
    def comparar_versoes(self):
        f,_=QFileDialog.getOpenFileName(self,'Investigação anterior com conjuntos importados','','GeoPackage (*.gpkg)')
        if not f:return
        from .saidas_integracao import reabrir
        def trabalho(cancelar,progresso):
            a=reabrir(f)
            if cancelar():raise InterruptedError('Comparação cancelada')
            return store.comparar_versoes(f,a,self.painel.base,self.painel.pacote)
        def pronto(r):self._comparacao_versoes=r;self.estado2.setText('Comparação persistida: '+str(sum(bool(x['mudancas'] or x['incluidos'] or x['retirados']) for x in r['linhas']))+' itens alterados. Exporte os detalhes ou inclua no relatório; nenhuma conclusão foi transferida.')
        self.worker=sistema(self.painel).executar_thread('Comparando Selection Sets entre versões','Identidades de modelo e conjuntos',trabalho,pronto,lambda e:self.estado2.setText(e))
    def exportar(self):
        if not self.leitura:return
        f,_=QFileDialog.getSaveFileName(self,'Metadados / histórico de diferenças','','JSON (*.json)')
        if f:
            try:
                with open(f,'x',encoding='utf8') as o:json.dump(dict(importacao=self.leitura,comparacao=getattr(self,'_comparacao',None),comparacao_versoes=getattr(self,'_comparacao_versoes',None)),o,ensure_ascii=False,indent=2)
            except Exception as e:QMessageBox.warning(self,'Exportação preservada',str(e))
    @acompanhada('Gerando relatório de Selection Sets')
    def relatorio(self):
        from .selection_sets_relatorio import gerar
        pasta=QFileDialog.getExistingDirectory(self,'Pasta do relatório de conjuntos')
        if pasta:
            try:gerar(self.painel.base,self.painel.pacote,self.ids_conjuntos(),pasta,progresso=lambda t,n,total:sistema(self).atual.atualizar(t,n,total),cancelado=lambda:sistema(self).atual.ponto(),comparacao=getattr(self,'_comparacao',None),comparacao_versoes=getattr(self,'_comparacao_versoes',None));self.estado2.setText('Relatório offline gerado pelo renderizador existente; sem consultas externas.')
            except Exception as e:QMessageBox.warning(self,'Relatório não concluído',str(e)+' · relatórios anteriores preservados');return False
    def opcoes_relatorio(self):
        from qgis.PyQt.QtWidgets import QWidget
        from .selection_sets_relatorio import casos
        from .relatorio_ui import RelatorioDialog
        cs=casos(self.painel.base,self.painel.pacote,self.ids_conjuntos())
        if not cs:QMessageBox.information(self,'Escolha conjuntos','Marque um ou mais conjuntos importados.');return
        self._contexto_relatorio=QWidget(self);c=self._contexto_relatorio;c.base=self.painel.base;c.pacote=self.painel.pacote;c.casos=cs;c.visiveis=cs;c.atual=cs[0];c.modo=self.painel.modo;c.legado=self.painel.legado;c.editor_filtros=self.painel.editor_filtros
        self._relatorio=RelatorioDialog(c);self._relatorio.setWindowTitle('Relatório de Selection Sets — fontes opcionais')
        if getattr(self.painel,'_wna_janelas',None):self.painel._wna_janelas.registrar('relatorio_selection_sets',self._relatorio,'relatório de Selection Sets')
        self._relatorio.show();self._relatorio.raise_()
    def lista_csv(self):
        from .selection_sets_alternativa import ler_csv
        f,_=QFileDialog.getOpenFileName(self,'Lista exportada pelo WaterGEMS','','CSV (*.csv)')
        if not f:return
        try:
            nome,ok=QInputDialog.getText(self,'Nome da lista','Nome do conjunto (hierarquia original não recuperada)')
            if ok:self.leitura=ler_csv(f,self.painel.pacote,nome);self.preencher()
        except Exception as e:QMessageBox.warning(self,'Lista não importada',str(e))
    def tem_edicoes(self):return False
    def closeEvent(self,e):
        if self.worker and not sip.isdeleted(self.worker) and self.worker.isRunning():QMessageBox.information(self,'Operação em andamento','Aguarde ou cancele pelo painel Atividade.');e.ignore();return
        e.accept()
