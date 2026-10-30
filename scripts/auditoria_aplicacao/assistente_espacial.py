"""Fluxo assistido sobre a referência/persistência existentes; trabalhos longos fora da GUI."""
from copy import deepcopy
import json
import sqlite3
from pathlib import Path
from qgis.core import QgsProject,QgsGeometry,QgsVectorLayer,QgsFeature,QgsField
from qgis.PyQt.QtCore import QThread,pyqtSignal,Qt,QVariant
from qgis.PyQt.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QStackedWidget,
    QWidget,QPushButton,QProgressBar,QComboBox,QLineEdit,QFormLayout,QCheckBox,
    QMessageBox,QFileDialog,QTableWidget,QTableWidgetItem,QDoubleSpinBox,QSpinBox,QGroupBox,QHeaderView,QSizePolicy)
from auditoria_fronteiras.ui_comum import adaptar_janela
from auditoria_fronteiras.tabelas_consulta import TabelaConsulta
from auditoria_topologica_watergems import bases,referencia_espacial as ref,deteccao_espacial as det
from auditoria_topologica_watergems.arquivos import hash_arquivo
from auditoria_topologica_watergems.gerenciamento import registros_gis,sugestao


from auditoria_fronteiras.atividade import Trabalho,sistema


def assinatura_gis(d,cancelar=None):
    fontes=[]
    for f in d['contexto']['fontes']:
        if f.get('modo'):continue
        bases.verificar(cancelar);p=Path(f['fonte'].split('|')[0])
        arquivos=sorted(p.parent.glob(p.stem+'.*')) if p.suffix.lower()=='.shp' else [p]
        # Fontes remotas/memória não têm assinatura reproduzível de arquivo.
        if not p.is_file():return None
        fontes.append(dict(origem=f['origem'],uri=f['fonte'],arquivos={a.name:hash_arquivo(a) for a in arquivos if a.is_file()}))
    return fontes


class AssistenteEspacial(QDialog):
    def __init__(self,pai):
        super().__init__(pai);self.pai=pai;self.setWindowTitle('VALIDAR REFERÊNCIA ESPACIAL DO WATERGEMS');self.resize(880,570)
        self.setWindowModality(Qt.WindowModal);self.t=None;self.metadados=None;self.relatorio=None;self.trabalho=None;self.controles=[];self.reuso=None;self.resultado=None;self._publicacao=None;self.mapa=None
        self.d=deepcopy(pai.app.geo.dossie);self.base=pai.base;self.crs_projeto=QgsProject.instance().crs().authid();self.catalogo=pai.app.catalogo.listar_opcional();self.avisos_catalogo=list(pai.app.catalogo.avisos)
        v=QVBoxLayout(self);self.titulo=QLabel();self.titulo.setStyleSheet('font-size:16px;font-weight:600;');self.titulo.setWordWrap(True);v.addWidget(self.titulo)
        self.paginas=QStackedWidget();v.addWidget(self.paginas,1);self.corpos=[]
        self.paginas.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Ignored)
        for nome in ['1 · Identificar os dados','2 · Conferir correspondências','3 · Verificar compatibilidade espacial','4 · Salvar e continuar']:
            w=QWidget();w.setObjectName(nome);self.corpos.append(QVBoxLayout(w));self.paginas.addWidget(w)
        self.identificacao=QLabel('Lendo o modelo e as camadas GIS…');self.identificacao.setWordWrap(True);self.corpos[0].addWidget(self.identificacao)
        self.meta_avancado,layout=self.detalhamento(self.corpos[0],'Informações técnicas das fontes e dos CRSs')
        self.fontes=TabelaConsulta(['Informação','Valor']);layout.addWidget(self.fontes)
        self.metatabela=TabelaConsulta(['Origem','Campo','Valor bruto','Interpretação','Confiabilidade']);layout.addWidget(self.metatabela)
        aviso=QLabel('\n'.join(self.avisos_catalogo[:3]));aviso.setWordWrap(True);self.corpos[0].addWidget(aviso);self.corpos[0].addStretch()
        l=QLabel('Escolha a coluna GIS que contém o Label das tubulações WaterGEMS. Sugestões únicas são exibidas; empates precisam de uma escolha. Uma associação cadastral ainda depende da comparação geométrica.');l.setWordWrap(True);self.corpos[1].addWidget(l)
        self.selecao=QTableWidget(0,2);self.selecao.setHorizontalHeaderLabels(['Camada GIS','Coluna GIS ↔ Label WaterGEMS']);self.selecao.setEditTriggers(QTableWidget.NoEditTriggers);self.selecao.horizontalHeader().setStretchLastSection(True);self.selecao.setMaximumHeight(125);self.corpos[1].addWidget(self.selecao);self.combos={};self._campos=[]
        self.previa_campos=QLabel();self.previa_campos.setWordWrap(True);self.corpos[1].addWidget(self.previa_campos)
        self.amostras=TabelaConsulta(['Camada GIS','Campo','Exemplo GIS','Label WG','Correspondência cadastral']);self.amostras.setMaximumHeight(200);self.corpos[1].addWidget(self.amostras)
        self.campos_avancado,layout=self.detalhamento(self.corpos[1],'Estatísticas de todos os campos disponíveis')
        self.candidatos=TabelaConsulta(['Camada','Campo GIS','Preenchidos','Nulos','Vazios','Repetidos','Exatos WG','Únicos bilaterais','Múltiplos','Não encontrados','Recomendação']);layout.addWidget(self.candidatos);self.corpos[1].addStretch()
        self.avaliacao=QLabel('Selecione os campos GIS e inicie a verificação.');self.avaliacao.setWordWrap(True);self.corpos[2].addWidget(self.avaliacao)
        self.crs=QLineEdit();self.crs.setPlaceholderText('Detectado nas fontes; altere somente se necessário');f=QFormLayout();f.addRow('CRS utilizado na comparação',self.crs);self.corpos[2].addLayout(f)
        self.recomparar=QPushButton('Verificar novamente');self.recomparar.clicked.connect(self.comparar);self.corpos[2].addWidget(self.recomparar)
        self.avancados,layout=self.detalhamento(self.corpos[2],'Opções avançadas e detalhes da verificação')
        self.avancados.toggled.connect(self.ajustar_altura)
        self.tolerancia=QDoubleSpinBox();self.tolerancia.setDecimals(5);self.tolerancia.setRange(0,1000);self.tolerancia.setValue(pai.tolerancia.value());self.crs_documental=QLineEdit();self.crs_documental.setPlaceholderText('Somente se não foi detectado: CRS observado no WaterGEMS');self.documento=QLineEdit();self.documento.setPlaceholderText('Opcional — observação sobre a origem da informação');f=QFormLayout();f.addRow('Tolerância dos vértices (m)',self.tolerancia);f.addRow('CRS observado nas propriedades WaterGEMS',self.crs_documental);f.addRow('Observação da origem (opcional)',self.documento);layout.addLayout(f)
        l=QLabel('Sem metadados ou referência anterior compatível, informe o CRS observado no WaterGEMS. Não use apenas a aparência da sobreposição. Nome de responsável e anexos não são necessários. Metro e pé internacional são hipóteses comparadas, sem rotação ou translação arbitrária.');l.setWordWrap(True);layout.addWidget(l)
        for texto,fn in [('Importar Junctions observadas / unidades adicionais (JSON)…',self.importar_controles),('Adicionar Junction observada…',self.adicionar_junction),('Anexar documento opcional…',self.anexar)]:
            b=QPushButton(texto);b.clicked.connect(fn);layout.addWidget(b)
        self.controles_info=QLabel('Nenhum controle pontual importado. Junctions são opcionais e não validam o modelo isoladamente.');self.controles_info.setWordWrap(True);layout.addWidget(self.controles_info)
        self.fatores=[1.,.3048];self.controles=[];self.anexo=None
        self.estatisticas=TabelaConsulta(['Fator','Unidade hipotética','Pares compatíveis','Geometrias comparadas','Vértices','Média (m)','Mediana (m)','Máximo (m)','P95 (m)','P99 (m)','Inconsistências']);layout.addWidget(self.estatisticas)
        self.junctions=TabelaConsulta(['DomainElementID','Label','Fator','X bruto','Y bruto','X convertido','Y convertido','Desvio (m)','Active Topology','Resultado']);layout.addWidget(self.junctions)
        self.mostrar=QPushButton('Mostrar amostras e divergências candidatas no mapa');self.mostrar.clicked.connect(self.mostrar_mapa);layout.addWidget(self.mostrar);self.corpos[2].addStretch()
        self.resumo=QLabel('A verificação ainda não foi executada.');self.resumo.setWordWrap(True);self.corpos[3].addWidget(self.resumo);self.corpos[3].addStretch()
        self.estado=QLabel('Detectando automaticamente…');self.estado.setWordWrap(True);v.addWidget(self.estado);self.barra=QProgressBar();self.barra.hide();v.addWidget(self.barra)
        l=QHBoxLayout();v.addLayout(l);self.voltar=QPushButton('Voltar');self.avancar=QPushButton('Conferir correspondências');self.sair=QPushButton('Cancelar')
        for b in (self.voltar,self.avancar,self.sair):l.addWidget(b)
        self.voltar.clicked.connect(lambda:self.pagina(max(0,self.paginas.currentIndex()-1)));self.avancar.clicked.connect(self.proximo);self.sair.clicked.connect(self.reject)
        self.crs.textChanged.connect(self.invalidar);self.tolerancia.valueChanged.connect(self.invalidar)
        self.crs_documental.textChanged.connect(self.atualizar_avaliacao);self.documento.textChanged.connect(self.atualizar_avaliacao)
        adaptar_janela(self);self.pagina(0);self.executar(self.detectar,self.detectado)

    @staticmethod
    def detalhamento(layout,titulo):
        grupo=QGroupBox(titulo);grupo.setCheckable(True);grupo.setChecked(False);externo=QVBoxLayout(grupo);conteudo=QWidget();interno=QVBoxLayout(conteudo);externo.addWidget(conteudo);conteudo.hide();grupo.toggled.connect(conteudo.setVisible);layout.addWidget(grupo);return grupo,interno

    def executar(self,funcao,pronto):
        if self.trabalho and self.trabalho.isRunning():return
        self.pai.ocupado=True
        self.paginas.setEnabled(False)
        self.voltar.setEnabled(False);self.avancar.setEnabled(False);self.barra.setRange(0,0);self.barra.show()
        self.trabalho=Trabalho(funcao,self);self.trabalho.progresso.connect(self.progresso)
        self._atividade=sistema(self).iniciar('Validando referência espacial WaterGEMS',str(self.base),self.trabalho.requestInterruption)
        self.trabalho.progresso.connect(self._atividade.sinal)
        self.trabalho.detalhes.connect(lambda texto:setattr(self._atividade,'detalhes',texto))
        self.trabalho.pronto.connect(pronto);self.trabalho.erro.connect(self.erro);self.trabalho.finished.connect(self.terminou);self.trabalho.start()
    def progresso(self,n,texto):self.barra.setRange(0,0);self.estado.setText(texto)
    def terminou(self):
        self.pai.ocupado=False;self.paginas.setEnabled(True);self.barra.setRange(0,100);self.barra.setValue(100 if self.resultado else 0);self.barra.hide();self.voltar.setEnabled(self.paginas.currentIndex()>0);self.avancar.setEnabled(self.t is not None and self._publicacao is None)
        if hasattr(self.pai,'atualizar_acoes'):self.pai.atualizar_acoes()
        if getattr(self,'_atividade',None) and self._atividade.estado in ('EM_ANDAMENTO','CANCELANDO'):
            estado='CANCELADO' if self.trabalho.isInterruptionRequested() else ('CONCLUIDO' if self.resultado else 'ETAPA_CONCLUIDA')
            self._atividade.finalizar(estado,'Nova versão validada e publicada' if self.resultado else 'Etapa concluída; consulte o resultado da verificação e a próxima ação')
        if self.resultado:
            self.accept()
            if hasattr(self.pai.app,'janelas'):self.pai.app.janelas.mostrar('watergems')
            else:self.pai.show();self.pai.raise_();self.pai.activateWindow()
    def erro(self,erro):
        self.estado.setText('Não foi possível concluir: '+erro+'. A base e as fontes anteriores foram preservadas.');self.avaliacao.setText('Verificação não concluída. Confira os parâmetros ou continue somente com a consulta topológica.')
        if getattr(self,'_atividade',None):self._atividade.finalizar('CANCELADO' if self.trabalho.isInterruptionRequested() else 'ERRO',erro)
    def detectar(self,cancelar,progresso):
        t=bases.restaurar(self.base,cancelar);progresso(10,'Lendo declarações espaciais e CRSs GIS')
        md=det.metadados_base(t,cancelar);gis=det.inventario_gis(self.d,self.crs_projeto,cancelar);assinatura=assinatura_gis(self.d,cancelar)
        campos=det.candidatos_campos(self.d,t['modelo'],cancelar,progresso)
        evidencias=[];vistos=set();contexto=ref.contexto_modelo(t['modelo'])
        for c in self.catalogo:
            if c.get('tipo')!='TOPOLOGIA_WG' or c['base'] in vistos or c.get('disponivel') is False:continue
            vistos.add(c['base']);bases.verificar(cancelar)
            try:
                m=bases.metadados(c['base']);r=m.get('referencia_espacial') or {}
                compativel=r.get('validacao',{}).get('contexto_modelo')==contexto
                if r and not r.get('validacao') and m.get('modelo_uid')==t['meta_base']['modelo_uid'] and m.get('cenario')==t['meta_base']['cenario']:
                    compativel=ref.compatibilidade(t['modelo'],ref.ler_evidencia(c['base']))['estado']=='VALIDADO'
                if compativel and ref.estado_referencia(r,t['modelo'])['estado']=='VALIDADO':evidencias.append(dict(base=c['base'],referencia=r))
            except (ValueError,OSError,KeyError,sqlite3.DatabaseError):pass
        return dict(t=t,metadados=md,gis=gis,campos=campos,assinatura_gis=assinatura,evidencias=evidencias)
    def detectado(self,dados):
        self._campos=dados['campos'];self.t=dados['t'];self.metadados=dados['metadados'];self.assinatura=dados['assinatura_gis'];self.evidencias=dados['evidencias'];self.gis=dados['gis'];m=self.t['meta_base']
        self.fontes.preencher([['Auditoria GIS',self.d['execucao_uid']],['Base WaterGEMS',m['uuid']],['Modelo',m['nome']],['Cenário',m['cenario']],['Perspectiva',self.pai.modo.currentText()],['Versão',m['versao']],['Assinatura técnica',ref.contexto_modelo(self.t['modelo'])],['CRS do projeto QGIS',self.crs_projeto],['CRS da auditoria',self.gis['crs_auditoria']]])
        linhas=[[r['tabela'],r['campo'],r['bruto'],r['interpretacao'],r['confiabilidade']] for r in self.metadados['registros']]
        linhas += [[r['camada'],'CRS GIS',r['crs'],r['unidade']+' · '+r['origem_informacao'],r['estado']+(' · CRS difere do registrado na auditoria' if r['inconsistencia'] else '')] for r in self.gis['camadas']]
        linhas += [[e['base'],'Evidência anterior',e['referencia']['crs'],e['referencia']['fator'],'CONTEXTO COMPATIVEL'] for e in self.evidencias]
        linhas += [['Catálogo da pasta selecionada','Aviso',aviso,'Base ativa pode ser analisada independentemente do índice','VERIFICAR'] for aviso in self.avisos_catalogo]
        self.metatabela.preencher(linhas);self.crs.setText(self.metadados.get('crs') or self.gis['crs_auditoria'])
        self.candidatos.preencher([[r[k] for k in ('camada','campo','preenchidos','nulos','vazios','repetidos','exatas','unicas','multiplas','nao_encontradas','recomendacao')] for r in dados['campos']])
        self.identificacao.setText(f"Modelo WaterGEMS: {m['nome']} · versão {m['versao']}\nCenário: {m['cenario']} · Perspectiva: {self.pai.modo.currentText()}\nAuditoria GIS: {self.d.get('controle_versao',{}).get('nome','Auditoria selecionada')}\nCRS GIS: {self.gis['crs_auditoria']}\nCRS WaterGEMS: {self.metadados.get('crs') or 'não identificado — será necessário verificar'}\nPróxima ação: conferir as colunas de correspondência.")
        for origem in dict.fromkeys(r['origem'] for r in dados['campos']):
            rs=[r for r in dados['campos'] if r['origem']==origem];combo=QComboBox();combo.addItem('Não associar esta camada',None)
            for r in rs:combo.addItem(r['campo']+(' — '+r['recomendacao'] if r['recomendacao'] else ''),r['campo'])
            anterior=self.pai.mapas.get(origem);escolhido=anterior.currentData() if anterior else None
            recomendado=next((r['campo'] for r in rs if r['recomendacao'].startswith('RECOMENDADO')),None)
            combo.setCurrentIndex(max(0,combo.findData(escolhido or recomendado)));combo.currentIndexChanged.connect(self.invalidar);combo.currentIndexChanged.connect(self.atualizar_campos)
            i=self.selecao.rowCount();self.selecao.insertRow(i);self.selecao.setItem(i,0,QTableWidgetItem(rs[0]['camada']));self.selecao.setCellWidget(i,1,combo);self.combos[origem]=combo
        r=m.get('referencia_espacial') or {};v=r.get('validacao',{})
        if self.assinatura and v.get('fontes_gis')==self.assinatura and v.get('mapeamento')=={k:c.currentData() for k,c in self.combos.items()} and v.get('estatisticas',{}).get('tolerancia_m')==self.tolerancia.value() and self.crs.text()==r.get('crs') and ref.estado_referencia(r,self.t['modelo'])['estado']=='VALIDADO':
            self.reuso=r;self.estado.setText('Validação desta composição e destas fontes recuperada. Pode utilizá-la sem repetir comparações.');self.avancar.setText('Utilizar validação existente')
        else:self.estado.setText('Dados identificados. Revise os campos sugeridos; não é necessário marcar caixas de confirmação.');self.pagina(1)
        self.atualizar_campos()
    def atualizar_campos(self,*args):
        from collections import Counter
        wg=Counter(e['label'] for e in self.t['modelo']['elementos'].values() if e['familia']=='LINK' and e['excluido'] is False) if self.t else Counter()
        mensagens=[];linhas=[]
        for origem,c in self.combos.items():
            r=next((r for r in self._campos if r['origem']==origem and r['campo']==c.currentData()),None)
            if not r:
                mensagens.append('Camada sem coluna associada; selecione um campo se desejar incluí-la.');continue
            mensagens.append(f"{r['camada']} · {r['campo']}: {r['unicas']} únicas; {r['multiplas']} múltiplas; {r['nulos']} nulas; {r['nao_encontradas']} não encontradas.")
            for exemplo in r.get('exemplos',[]):
                valor=exemplo['valor'];encontrado=valor is not None and bool(str(valor).strip()) and wg[valor]>0
                linhas.append([r['camada'],r['campo'],valor,valor if encontrado else None,'Múltipla / requer revisão' if encontrado and (wg[valor]>1 or exemplo['quantidade']>1) else 'Candidata — verificar geometria' if encontrado else 'Não encontrada'])
        self.previa_campos.setText('\n'.join(mensagens));self.amostras.preencher(linhas)
    def invalidar(self,*args):
        self.relatorio=None;self.reuso=None;self.avaliacao.setText('Parâmetros alterados. Execute a verificação para utilizar estes valores.');self.resumo.setText('Verifique os parâmetros antes de salvar. Nenhuma base foi alterada.')
    def pagina(self,i):
        self.paginas.setCurrentIndex(i);self.titulo.setText(self.paginas.currentWidget().objectName());self.voltar.setEnabled(i>0);self.avancar.setText(['Conferir correspondências','Verificar compatibilidade espacial','Conferir e salvar','Salvar referência espacial'][i])
        if i in (2,3):self.atualizar_avaliacao()
        self.ajustar_altura()
    def ajustar_altura(self,*args):
        if self.isMaximized() or getattr(self,'_wna_lembrar',None) and self._wna_lembrar.isChecked():return
        i=self.paginas.currentIndex();altura=(390,560,560 if self.avancados.isChecked() else 390,330)[i]
        self.resize(self.width(),altura)
    def proximo(self):
        if self.reuso and self.paginas.currentIndex()==0:
            self.pai.usar_base(self.base)
            for origem,campo in self.reuso.get('validacao',{}).get('mapeamento',{}).items():
                if origem in self.pai.mapas:self.pai.mapas[origem].setCurrentIndex(max(0,self.pai.mapas[origem].findData(campo)))
            self.accept();return
        i=self.paginas.currentIndex()
        if i==1:
            if not any(c.currentData() for c in self.combos.values()):QMessageBox.information(self,'Escolha uma coluna GIS','Selecione ao menos uma coluna com identificadores correspondentes ao Label WaterGEMS. Empates não são escolhidos automaticamente.');return
            self.comparar();return
        if i==2:
            self.atualizar_avaliacao()
            if not self.relatorio or self._avaliacao['estado']!='APTO_PARA_CONFIRMACAO':self.estado.setText('Resolva as pendências indicadas no resultado antes de salvar. A consulta topológica continua disponível.');return
        if i==3:self.salvar();return
        self.pagina(i+1)
    def comparar(self):
        if not self.t:return
        crs=self.crs.text().strip();mapa={k:c.currentData() for k,c in self.combos.items()};tol=self.tolerancia.value();self.pagina(2)
        def trabalho(cancelar,progresso):
            if self.assinatura!=assinatura_gis(self.d,cancelar):raise ValueError('Fontes GIS mudaram após a detecção; reabra a verificação')
            regs,avisos=registros_gis(self.d,mapa,crs,cancelar,registrar_operacoes=True);r=det.comparar_hipoteses(self.t['modelo'],regs,crs,tol,self.fatores,self.controles,cancelar,progresso)
            if self.assinatura!=assinatura_gis(self.d,cancelar):raise ValueError('Fontes GIS mudaram durante a comparação; resultado não publicado')
            r['mapeamento']=mapa;r['avisos']=avisos;r['transformacoes_gis']=list({g['origem']:g['operacao_crs'] for g in regs}.values());return r
        self.executar(trabalho,self.comparado)
    def comparado(self,r):
        self.relatorio=r
        self.estatisticas.preencher([[h[k] for k in ('fator','unidade','compativeis','geometrias_comparadas','vertices_comparados','media_m','mediana_m','maximo_m','p95_m','p99_m','inconsistencias')] for h in r['hipoteses']])
        self.junctions.preencher([[c.get(k) for k in ('id','label','fator','x_bruto','y_bruto','x_convertido','y_convertido','erro_m','ativo','estado')] for h in r['hipoteses'] for c in h['junctions']]);self.pagina(2);self.estado.setText('Comparação concluída. Veja o resultado e a próxima ação.')
    def adicionar_junction(self):
        j=QDialog(self);j.setWindowTitle('Junction observada — coordenadas exibidas em metros');v=QVBoxLayout(j);f=QFormLayout();v.addLayout(f)
        id_=QLineEdit();label=QLineEdit();fonte=QLineEdit();x=QDoubleSpinBox();y=QDoubleSpinBox();decimais=QSpinBox();decimais.setRange(0,8);decimais.setValue(2)
        for c in (x,y):c.setDecimals(8);c.setRange(-1e12,1e12)
        for texto,c in [('DomainElementID',id_),('Label observado',label),('X exibido (m)',x),('Y exibido (m)',y),('Casas decimais da apresentação',decimais),('Fonte e data da observação',fonte)]:f.addRow(texto,c)
        l=QHBoxLayout();v.addLayout(l);b=QPushButton('Adicionar controle');l.addWidget(b);b.clicked.connect(j.accept);b=QPushButton('Cancelar');l.addWidget(b);b.clicked.connect(j.reject);adaptar_janela(j)
        if j.exec_()!=QDialog.Accepted:return
        try:
            if not label.text().strip() or not fonte.text().strip():raise ValueError('Label e fonte são necessários; coordenadas isoladas não comprovam identidade')
            c=dict(id=int(id_.text()),label=label.text(),x=x.value(),y=y.value(),decimais=decimais.value(),fonte=fonte.text(),contexto_modelo=ref.contexto_modelo(self.t['modelo']))
            self.controles.append(c);self.invalidar();self.controles_info.setText(f'{len(self.controles)} Junctions observadas, vinculadas ao contexto atual. Compare as hipóteses novamente.')
        except ValueError as e:QMessageBox.warning(self,'Controle não adicionado',str(e))
    def importar_controles(self):
        p,_=QFileDialog.getOpenFileName(self,'Observações documentadas de Junctions / unidades','','JSON (*.json)')
        if not p:return
        try:
            d=json.loads(Path(p).read_text(encoding='utf8'));contexto=ref.contexto_modelo(self.t['modelo'])
            if d.get('contexto_modelo')!=contexto:raise ValueError('Observações pertencem a outro contexto técnico; confirme a versão do modelo')
            controles=[]
            for c in d.get('junctions',[]):
                if not c.get('fonte') or not all(k in c for k in ('id','label','x','y')):raise ValueError('Controle incompleto: ID, Label, coordenadas e fonte são necessários')
                controles.append(dict(c,contexto_modelo=contexto,arquivo_sha256=hash_arquivo(p)))
            fatores=[1.,.3048]
            for f in d.get('outras_unidades',[]):
                if not f.get('fonte') or not f.get('unidade'):raise ValueError('Outra unidade exige fundamento identificado')
                fatores.append(float(f['fator']))
            self.controles=controles;self.fatores=fatores;self.invalidar();self.controles_info.setText(f'{len(controles)} controles com versão e proveniência; {len(fatores)} hipóteses de conversão.');self.anexo=(str(Path(p).resolve()),hash_arquivo(p))
        except Exception as e:QMessageBox.warning(self,'Observações não importadas',str(e))
    def anexar(self):
        p,_=QFileDialog.getOpenFileName(self,'Documento adicional de evidência')
        if p:self.anexo=(str(Path(p).resolve()),hash_arquivo(p));self.documento.setText(Path(p).name)
    def atualizar_avaliacao(self,*args):
        if not self.relatorio:return
        md=self.metadados
        documental=self.crs_documental.text().strip() or None
        if not md.get('crs') and not documental:
            e=next((e for e in self.evidencias if e['referencia']['crs']==self.relatorio['crs']),None)
            if e:documental=e['referencia']['crs']
        a=det.avaliar(self.t,self.relatorio,md,documental);self._avaliacao=a;self.documental_efetivo=documental
        h=next((h for h in self.relatorio['hipoteses'] if h['fator']==self.relatorio['fator_recomendado']),None)
        titulo={'APTO_PARA_CONFIRMACAO':'Verificação concluída — pronto para salvar','PENDENTE':'Verificação pendente','INCOMPATIVEL':'Dados incompatíveis — revise os parâmetros'}[a['estado']]
        detalhe=f"CRS: {self.relatorio['crs']}\nUnidade bruta: {h['unidade'] if h else 'inconclusiva'} · fator: {h['fator'] if h else 'não determinado'}\nCorrespondências válidas: {h['compativeis'] if h else 0} · divergências: {h['inconsistencias'] if h else 'não determinadas'}\nTolerância: {self.relatorio['tolerancia_m']} m"
        self.avaliacao.setText(titulo+'\n'+detalhe+'\n'+('\n'.join(a['faltas']) if a['faltas'] else 'Próxima ação: conferir os parâmetros e salvar. Não é necessário responsável, anexo ou aceite.'))
        self.resumo.setText(titulo+'\n'+self.t['meta_base']['nome']+' · cenário '+str(self.t['modelo']['cenario'])+'\n'+detalhe+'\n'+('\n'.join(a['faltas']) if a['faltas'] else 'Será criada uma nova versão. A base anterior permanece intacta. Compatibilidade espacial não comprova conectividade hidráulica.'))
        if self.paginas.currentIndex()==2 and not md.get('crs') and not documental:self.avancados.setChecked(True)
    def salvar(self):
        if self._publicacao or self.resultado or self.trabalho and self.trabalho.isRunning():return
        try:
            self.atualizar_avaliacao()
            if not self.relatorio:raise ValueError('Execute a verificação espacial antes de salvar')
            doc=dict(crs=self.documental_efetivo,fonte=self.documento.text().strip())
            if self.documental_efetivo and not self.crs_documental.text().strip():
                e=next(e for e in self.evidencias if e['referencia']['crs']==self.documental_efetivo);doc['fonte']=e['referencia']['fonte'];doc['base_evidencia']=e['base'];doc['sha256']=hash_arquivo(e['base'])
            r=det.confirmar_assistida(self.t,self.relatorio,self.metadados,documento=doc)
            r['validacao']['fontes_gis']=self.assinatura;r['validacao']['mapeamento']=self.relatorio['mapeamento'];r['validacao']['transformacoes_gis']=self.relatorio['transformacoes_gis']
            if self.anexo:r['validacao']['anexo']=dict(arquivo=self.anexo[0],sha256=self.anexo[1])
            m=self.t['meta_base'];destino,_=QFileDialog.getSaveFileName(self,'Nova versão topológica validada',str(sugestao(self.pai.app.catalogo.raiz,m['projeto'],'TopologiaWG',m['versao']+1)),'GeoPackage (*.gpkg)')
            if not destino:return
            if not destino.lower().endswith('.gpkg'):destino+='.gpkg'
            def gravar(cancelar,progresso):
                from auditoria_fronteiras.versoes import abrir_ro
                p=ref.salvar_referencia(self.base,destino,r,cancelar)
                with abrir_ro(p) as c:
                    if c.execute('PRAGMA quick_check').fetchone()[0]!='ok' or c.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('A publicação não passou na verificação de integridade')
                return p
            self.executar(gravar,self.salvo)
        except Exception as e:QMessageBox.warning(self,'Validação não salva',str(e))
    def salvo(self,p):
        self._publicacao=str(p)
        try:
            meta=bases.metadados(p)
            if ref.estado_referencia(meta.get('referencia_espacial'))['estado']!='VALIDADO':raise ValueError('A nova base não contém evidência espacial validada')
            self.pai.usar_base(p)
            if Path(self.pai.base).resolve()!=Path(p).resolve():raise ValueError('A janela principal não ativou a versão publicada')
            for origem,campo in self.relatorio['mapeamento'].items():
                if origem in self.pai.mapas:self.pai.mapas[origem].setCurrentIndex(max(0,self.pai.mapas[origem].findData(campo)))
            if 'tolerancia_m' in self.relatorio:self.pai.tolerancia.setValue(self.relatorio['tolerancia_m'])
            self.pai.resp_evidencia.setText(meta.get('referencia_espacial',{}).get('validacao',{}).get('responsavel',''))
            self.resultado=str(p);self.estado.setText('Nova versão salva e configuração atualizada.');self.avancar.setEnabled(False)
        except Exception as e:
            self.avancar.setEnabled(False);QMessageBox.warning(self,'Publicação requer recuperação','A versão foi gravada em '+str(p)+', mas não foi possível ativá-la: '+str(e)+'. Reabra este arquivo; não será criada outra versão por este assistente.')
    def mostrar_mapa(self):
        if not self.relatorio:return
        crs=self.relatorio['crs'];camada=QgsVectorLayer('Point?crs='+crs,'VALIDACAO — coordenadas candidatas (não comprovam datum)','memory');p=camada.dataProvider()
        p.addAttributes([QgsField('FATOR',QVariant.Double),QgsField('ID_WG',QVariant.String),QgsField('ERRO_M',QVariant.Double),QgsField('TIPO',QVariant.String)]);camada.updateFields();fs=[]
        for h in self.relatorio['hipoteses']:
            for a in h['prova']['amostras'][:100]:
                for tipo,x,y in [('GIS',a[7],a[8]),('WG convertido',a[9],a[10])]:
                    if x is None or y is None:continue
                    f=QgsFeature(camada.fields());f.setGeometry(QgsGeometry.fromWkt(f'POINT({x} {y})'));f.setAttributes([h['fator'],str(a[4]),a[6],tipo]);fs.append(f)
            for a in h['divergencias'][:200]:
                f=QgsFeature(camada.fields());f.setGeometry(QgsGeometry.fromWkt(f"POINT({a['x']} {a['y']})"));f.setAttributes([h['fator'],str(a['wg_id']),a['erro_m'],'DIVERGENCIA GIS']);fs.append(f)
        from qgis.core import QgsCategorizedSymbolRenderer,QgsRendererCategory,QgsMarkerSymbol
        categorias=[QgsRendererCategory(tipo,QgsMarkerSymbol.createSimple(dict(name='circle',color=cor,size='2.5')),tipo) for tipo,cor in [('GIS','40,110,220'),('WG convertido','180,40,180'),('DIVERGENCIA GIS','230,120,20')]]
        camada.setRenderer(QgsCategorizedSymbolRenderer('TIPO',categorias))
        p.addFeatures(fs);camada.updateExtents()
        from auditoria_fronteiras.organizacao_camadas import publicar
        camada.setCustomProperty('wna/tecnico','CANDIDATOS_VALIDACAO_'+camada.id())
        camada=publicar(camada,QgsProject.instance(),'wg',self.t['meta_base']['uuid'],self.base,self.t['meta_base']['nome'],self.t['meta_base']['versao'],temporaria=True)
        self.mapa=camada.id();self.estado.setText('Camada temporária de candidatos criada sem alterar fontes ou impor zoom. Remova-a após a investigação.')
    def reject(self):
        if self.trabalho and self.trabalho.isRunning():self.trabalho.requestInterruption();self.estado.setText('Cancelamento solicitado; aguardando ponto seguro, sem publicar resultados.');return
        super().reject()
    def closeEvent(self,e):
        if self.resultado:e.accept()
        elif self.trabalho and self.trabalho.isRunning():self.reject();e.ignore()
        else:e.accept()
