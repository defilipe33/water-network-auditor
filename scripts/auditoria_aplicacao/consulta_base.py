"""Consulta paginada do snapshot; independe do modelo original e do GIS."""
import json
from qgis.PyQt.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QComboBox,QPushButton,QLabel,QTableWidget,QTableWidgetItem,QAbstractItemView
from auditoria_fronteiras.versoes import abrir_ro
from auditoria_topologica_watergems import bases
from auditoria_fronteiras.atividade import acompanhada,falha


class ConsultaBase(QDialog):
    def __init__(self,base,parent=None):
        super().__init__(parent);self.base=base;self.pagina=0;self.setWindowTitle('Consultar base WaterGEMS persistida');self.resize(850,550)
        v=QVBoxLayout(self);m=bases.metadados(base);self.info=QLabel(f"{m['nome']} · v{m['versao']} · {m['uuid']}\n{m.get('escopo','Dados relevantes extraídos; não contém todos os dados hidráulicos do WaterGEMS.')}");self.info.setWordWrap(True);v.addWidget(self.info)
        l=QHBoxLayout();v.addLayout(l);self.tipo=QComboBox();self.tipo.addItems(['Elementos','Componentes','Diagnósticos']);l.addWidget(self.tipo)
        self.modo=QComboBox();self.modo.addItems(bases.MODOS);l.addWidget(self.modo)
        self.tabela=QTableWidget();self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers);v.addWidget(self.tabela)
        l=QHBoxLayout();v.addLayout(l)
        for nome,delta in [('Página anterior',-1),('Próxima página',1)]:
            b=QPushButton(nome);b.clicked.connect(lambda _,d=delta:self.mudar(d));l.addWidget(b)
        self.rodape=QLabel();l.addWidget(self.rodape)
        self.tipo.currentIndexChanged.connect(self.resetar);self.modo.currentIndexChanged.connect(self.resetar);self.atualizar()
        b=QPushButton('Carregar representação desta versão no mapa');b.clicked.connect(lambda checked=False:self.carregar_mapa());v.addWidget(b)
        from auditoria_fronteiras.ui_comum import adaptar_janela
        adaptar_janela(self)
    def resetar(self):self.pagina=0;self.atualizar()
    @acompanhada('Recuperando camadas da versão WaterGEMS')
    def carregar_mapa(self):
        from qgis.core import QgsProject
        from qgis.PyQt.QtWidgets import QMessageBox
        from auditoria_fronteiras.organizacao_camadas import publicar
        from auditoria_topologica_watergems.saidas import camadas
        try:
            t=bases.restaurar(self.base);m=t['meta_base']
            if not t['metrica']:raise ValueError('Consulta topológica disponível; confirme CRS/unidade antes de carregar geometrias no mapa.')
            for c in camadas(t['modelo'],t['estrutural'],t['geometrias'],m['crs']):publicar(c,QgsProject.instance(),'wg',m['uuid'],self.base,m['projeto'] or m['nome'],m['versao'],None if c.isSpatial() else 'Diagnósticos e auxiliares')
        except Exception as e:falha(self,e);QMessageBox.warning(self,'Camadas não carregadas',str(e))
    def mudar(self,delta):self.pagina=max(0,self.pagina+delta);self.atualizar()
    @acompanhada('Consultando página da base WaterGEMS')
    def atualizar(self):
        with abrir_ro(self.base) as c:
            if self.tipo.currentIndex()==0:
                total=c.execute('select count(*) from WB_ELEMENTOS').fetchone()[0]
                campos=['DomainElementID','Label','Tipo','Família','Ativo','Excluído'];itens=bases.elementos(self.base,200,self.pagina*200)
                linhas=[[r[k] for k in ('id','label','tipo','familia','ativo','excluido')] for r in itens]
            else:
                r=json.loads(c.execute('select dados from WB_RESULTADOS where modo=?',(self.modo.currentText(),)).fetchone()[0])
                chave='componentes' if self.tipo.currentIndex()==1 else 'diagnosticos';itens=r[chave];total=len(itens);itens=itens[self.pagina*200:(self.pagina+1)*200]
                if chave=='componentes':
                    campos=['Componente','Tubulações','Nós','Dispositivos','Fontes de água','Classe'];linhas=[[x['id'],len(x['tubulacoes']),len(x['nos']),x.get('n_dispositivos',0),'; '.join(map(str,x.get('fontes',[]))),x.get('classe_tamanho','')] for x in itens]
                else:
                    campos=['Diagnóstico','Elemento','Relacionado','Descrição'];linhas=[[x.get(k) for k in ('codigo','id','relacionado','descricao')] for x in itens]
        if self.pagina and self.pagina*200>=total:self.pagina=max(0,(total-1)//200);self.atualizar();return
        self.tabela.setColumnCount(len(campos));self.tabela.setHorizontalHeaderLabels(campos);self.tabela.setRowCount(len(linhas))
        for i,linha in enumerate(linhas):
            for j,valor in enumerate(linha):self.tabela.setItem(i,j,QTableWidgetItem('' if valor is None else str(valor)))
        self.tabela.resizeColumnsToContents();self.rodape.setText(f'Página {self.pagina+1} · {total} registros · até 200 por página')
