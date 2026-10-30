"""Exploração de cenário e Active Topology sem inferir união de filhos."""
import json
from qgis.PyQt.QtWidgets import QDialog,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QPushButton,QComboBox,QMessageBox,QFileDialog
from auditoria_fronteiras.versoes import abrir_ro
from auditoria_fronteiras.ui_comum import adaptar_janela
from auditoria_topologica_watergems import bases

class CenariosDialog(QDialog):
    def __init__(self,app):
        super().__init__(app.iface.mainWindow());self.app=app;self.setWindowTitle('Cenários e Active Topology');self.resize(850,560);v=QVBoxLayout(self);self.info=QLabel();self.info.setWordWrap(True);v.addWidget(self.info);self.tabela=QTableWidget(0,4);self.tabela.setHorizontalHeaderLabels(['Cenário','Nome','Pai','Situação na versão aberta']);self.tabela.setEditTriggers(QTableWidget.NoEditTriggers);v.addWidget(self.tabela);self.ajuda=QLabel('Cenário base não é a união dos filhos. A cadeia de Active Topology é resolvida individualmente. Comparação avançada de cenários ainda não implementada.');self.ajuda.setWordWrap(True);v.addWidget(self.ajuda);b=QPushButton('Fechar');b.clicked.connect(self.close);v.addWidget(b);adaptar_janela(self)
        self.versoes=QComboBox();v.insertWidget(2,self.versoes)
        self.tabela.setSelectionBehavior(QTableWidget.SelectRows);self.tabela.itemSelectionChanged.connect(self.listar_bases)
        for texto,acao in [('Abrir cenário / versão selecionada',self.abrir),('Preparar cenário ainda não extraído…',self.preparar)]:
            b=QPushButton(texto);b.clicked.connect(acao);v.insertWidget(v.count()-1,b)
        self.alvos=QComboBox();v.insertWidget(v.count()-1,self.alvos);b=QPushButton('Associar cenário à região / Selection Set');b.clicked.connect(self.associar);v.insertWidget(v.count()-1,b)
        self.aviso=QLabel();self.aviso.setWordWrap(True);v.insertWidget(v.count()-1,self.aviso)
        b=QPushButton('Consultar histórico de associações do projeto');b.clicked.connect(self.historico);v.insertWidget(v.count()-1,b)
        adaptar_janela(self)
    def atualizar(self):
        if self.app.wg and self.app.wg.base and not self.app.painel_atual():
            base=self.app.wg.base;m=bases.metadados(base)
            with abrir_ro(base) as c:modelo=bases.decodificar(json.loads(c.execute('SELECT modelo FROM WB_BASE').fetchone()[0]))
        elif self.app.painel_atual():
            p=self.app.painel.pacote;modelo=p['topologia']['modelo'];ig=p['resultado']['meta'];m=p['topologia'].get('meta_base') or dict(nome='Contexto incorporado à investigação',projeto=ig.get('projeto',''),modelo_uid=modelo['projeto'],versao=ig['topologia'].get('versao','não preservada'))
        else:return
        self.modelo=modelo;self.meta=m;self.info.setText(m['projeto']+' · '+m['nome']+' · versão '+str(m['versao'])+' · cenário '+str(modelo['cenario'])+'\nActive Topology efetiva: '+str(modelo['alternativas'].get('3')))
        rows=modelo.get('cenarios',[]);self.tabela.setRowCount(len(rows))
        for n,r in enumerate(rows):
            for k,x in enumerate((r['id'],r['nome'],r.get('pai'),'Contexto aberto' if r['id']==modelo['cenario'] else 'Requer base correspondente')):self.tabela.setItem(n,k,QTableWidgetItem(str(x)))
        self.tabela.resizeColumnsToContents()
        self.rows=rows;self.alvos.clear();self.alvos.addItem('Associação opcional — escolha um alvo identificado',None)
        p=self.app.painel if self.app.painel_atual() else None
        if p and p.pacote['topologia']['modelo']['projeto']==m['modelo_uid']:
            origem=p.pacote['resultado']['meta']['uid']
            for a in p.pacote.get('areas',[]):self.alvos.addItem(a['camada']+' · '+str(a['exibicao']),dict(origem='AREA',id=a['uid'],investigacao=origem,tipo=a['tipo']))
            from auditoria_topologica_watergems.selection_sets_persistencia import atuais
            for r in atuais(p.base,p.pacote):
                d=r['dados'];self.alvos.addItem('Selection Set · '+d['nome'],dict(origem='SELECTION_SET',id=r['obj_uid'],id_fonte=d['id'],investigacao=origem))
        self.listar_bases()
    def selecionado(self):
        n=self.tabela.currentRow();rs=getattr(self,'rows',[])
        return rs[n] if 0<=n<len(rs) else None
    def listar_bases(self):
        self.versoes.clear();s=self.selecionado()
        if not s:return
        for r in bases_cenario(self.app.catalogo,self.meta['modelo_uid'],s['id']):self.versoes.addItem(f"{r['nome']} · V{r['versao']:03} · {r['uuid'][:8]}",r)
        self.versoes.setToolTip('O caminho completo e os metadados permanecem disponíveis em Bases / versões → Catálogo.')
        self.aviso.setText('Escolha explicitamente a versão; decisões anteriores não serão transferidas.' if self.versoes.count() else 'Sem base persistida para este cenário. Prepare uma extração específica; a investigação atual permanece intacta.')
    def abrir(self):
        r=self.versoes.currentData()
        if not r:self.aviso.setText('Selecione cenário e versão, ou use Preparar cenário.');return
        try:
            if self.app.trocar_base(r):self.atualizar();self.aviso.setText('Contexto alterado. A investigação anterior permanece no catálogo; nenhuma decisão foi transferida.')
        except Exception as e:QMessageBox.warning(self,'Cenário preservado','Base não aberta: '+str(e)+'\nO contexto anterior foi preservado.')
    def preparar(self):
        s=self.selecionado()
        if not s:return
        if not self.app.resolver() or not self.app.geo.resolver_pendencias() or not self.app.resolver_configuracao_wg():return
        fonte,_=QFileDialog.getOpenFileName(self,'Modelo correspondente — somente leitura','','WaterGEMS (*.wtg.sqlite)')
        if not fonte:return
        try:
            from auditoria_topologica_watergems.leitura import Banco
            b=Banco(fonte)
            try:
                if b.projeto!=self.meta['modelo_uid']:raise ValueError('Identidade do modelo difere da base aberta')
            finally:b.close()
            cs,ativo=bases.cenarios_fonte(fonte)
            if s['id'] not in {c['id'] for c in cs}:raise ValueError('Cenário ausente nesta fonte')
            self.app.bases();w=self.app.wg;w.anterior=None;w.fonte=fonte;w.base=None;w.cenario.clear()
            for c in cs:w.cenario.addItem(c['nome'],c['id'])
            w.cenario.setCurrentIndex(w.cenario.findData(s['id']));w._topologia=None;w._prova=None;w._referencia_confirmada=None;w._carregando=True
            w.crs.clear();w.evidencia.clear();w.fator.setValue(1);w.unidade.setCurrentIndex(0);w.espacial.setChecked(False);w._carregando=False;w._ref_pendente=False
            w.identidade.setText('Preparação do cenário '+str(s['id'])+' — nenhuma extração executada');self.app.janelas.mostrar('watergems')
        except Exception as e:QMessageBox.warning(self,'Fonte não preparada',str(e)+'\nAs bases existentes foram preservadas.')
    def associar(self):
        s=self.selecionado();alvo=self.alvos.currentData();r=self.versoes.currentData()
        if not s or not alvo or not r:self.aviso.setText('Selecione cenário, versão e alvo com identidade técnica.');return
        try:
            from .contexto_trabalho import associar_cenario
            associar_cenario(self.app.central.projetos,self.meta['modelo_uid'],s['id'],r['uuid'],alvo);self.aviso.setText('Associação preservada no histórico do projeto; o WaterGEMS não foi alterado.')
        except Exception as e:QMessageBox.warning(self,'Associação não salva',str(e))
    def historico(self):
        p=self.app.central.projetos.atual() or {};rs=p.get('associacoes_cenarios',[]);d=QDialog(self);d.setWindowTitle('Associações explícitas — histórico preservado');d.resize(800,450);v=QVBoxLayout(d);t=QTableWidget(len(rs),5);t.setHorizontalHeaderLabels(['Data UTC','Cenário','Versão','Tipo de alvo','Identidade do alvo']);t.setEditTriggers(QTableWidget.NoEditTriggers);v.addWidget(t)
        for n,r in enumerate(rs):
            for k,x in enumerate((r['data_utc'],r['cenario'],r['versao'],r['alvo']['origem'],r['alvo']['id'])):t.setItem(n,k,QTableWidgetItem(str(x)))
        t.resizeColumnsToContents();b=QPushButton('Fechar');b.clicked.connect(d.accept);v.addWidget(b);adaptar_janela(d);d.exec_()


def bases_cenario(catalogo,modelo,cenario):
    return [r for r in catalogo.listar_opcional() if r['tipo']=='TOPOLOGIA_WG' and r.get('modelo_uid')==modelo and r.get('cenario')==cenario and not r.get('backup_identidade_compartilhada')]
