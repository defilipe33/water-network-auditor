"""Fluxo assistido sobre a referência/persistência existentes; trabalhos longos fora da GUI."""
from copy import deepcopy
import json
import sqlite3
from pathlib import Path
from qgis.core import QgsProject,QgsGeometry,QgsVectorLayer,QgsFeature,QgsField
from qgis.PyQt.QtCore import QThread,pyqtSignal,Qt,QVariant
from qgis.PyQt.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QStackedWidget,
    QWidget,QPushButton,QProgressBar,QComboBox,QLineEdit,QFormLayout,QCheckBox,
    QMessageBox,QFileDialog,QTableWidget,QTableWidgetItem,QDoubleSpinBox,QSpinBox)
from auditoria_fronteiras.ui_comum import adaptar_janela
from auditoria_fronteiras.tabelas_consulta import TabelaConsulta
from auditoria_topologica_watergems import bases,referencia_espacial as ref,deteccao_espacial as det
from auditoria_topologica_watergems.arquivos import hash_arquivo
from auditoria_topologica_watergems.gerenciamento import registros_gis,sugestao


class Trabalho(QThread):
    pronto=pyqtSignal(object);erro=pyqtSignal(str);progresso=pyqtSignal(int,str)
    def __init__(self,funcao,parent):super().__init__(parent);self.funcao=funcao
    def run(self):
        try:self.pronto.emit(self.funcao(self.isInterruptionRequested,self.progresso.emit))
        except Exception as e:self.erro.emit(str(e))


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
        super().__init__(pai);self.pai=pai;self.setWindowTitle('VALIDAR REFERÊNCIA ESPACIAL DO WATERGEMS');self.resize(930,660)
        self.setWindowModality(Qt.WindowModal);self.t=None;self.metadados=None;self.relatorio=None;self.trabalho=None;self.controles=[];self.reuso=None;self.resultado=None;self._publicacao=None;self.mapa=None
        self.d=deepcopy(pai.app.geo.dossie);self.base=pai.base;self.crs_projeto=QgsProject.instance().crs().authid();self.catalogo=pai.app.catalogo.listar_opcional();self.avisos_catalogo=list(pai.app.catalogo.avisos)
        v=QVBoxLayout(self);self.titulo=QLabel();self.titulo.setWordWrap(True);v.addWidget(self.titulo)
        self.paginas=QStackedWidget();v.addWidget(self.paginas,1);self.corpos=[]
        for nome in ['1 · Fontes','2 · Metadados e evidências','3 · Correspondências cadastrais','4 · Unidades e Junctions','5 · Geometrias e estatísticas','6 · Evidências e pendências','7 · Confirmar e salvar']:
            w=QWidget();w.setObjectName(nome);self.corpos.append(QVBoxLayout(w));self.paginas.addWidget(w)
        self.fontes=TabelaConsulta(['Informação','Valor']);self.corpos[0].addWidget(self.fontes)
        aviso=QLabel('\n'.join(self.avisos_catalogo[:3]));aviso.setWordWrap(True);self.corpos[0].addWidget(aviso)
        self.metatabela=TabelaConsulta(['Origem','Campo','Valor bruto','Interpretação','Confiabilidade']);self.corpos[1].addWidget(self.metatabela)
        self.candidatos=TabelaConsulta(['Camada','Campo GIS','Preenchidos','Nulos','Vazios','Repetidos','Exatos WG','Únicos bilaterais','Múltiplos','Não encontrados','Recomendação']);self.corpos[2].addWidget(self.candidatos,1)
        self.selecao=QTableWidget(0,2);self.selecao.setHorizontalHeaderLabels(['Camada GIS','Coluna para confrontar com Label WG']);self.corpos[2].addWidget(self.selecao)
        self.combos={};self.confirmar_campos=QCheckBox('Conferi e confirmo as colunas selecionadas (não são necessariamente o ID da auditoria)');self.corpos[2].addWidget(self.confirmar_campos)
        self.crs=QLineEdit();self.crs.setPlaceholderText('Preenchido pela declaração WaterGEMS ou CRS da auditoria; candidato não comprova datum')
        self.tolerancia=QDoubleSpinBox();self.tolerancia.setDecimals(5);self.tolerancia.setRange(0,1000);self.tolerancia.setValue(pai.tolerancia.value())
        f=QFormLayout();f.addRow('CRS da comparação (projetado, metros)',self.crs);f.addRow('Tolerância dos vértices (m)',self.tolerancia);self.corpos[3].addLayout(f)
        l=QLabel('Serão testados 1,0 (metro) e 0,3048 (pé internacional), sem rotação/translação. A tolerância não será aumentada automaticamente. Junctions de controle são opcionais e exigem contexto técnico, coordenadas observadas e precisão. Uma Junction sozinha não valida o modelo.');l.setWordWrap(True);self.corpos[3].addWidget(l)
        b=QPushButton('Importar observações de Junctions / outra unidade fundamentada (JSON)…');b.clicked.connect(self.importar_controles);self.corpos[3].addWidget(b)
        b=QPushButton('Adicionar Junction observada no WaterGEMS…');b.clicked.connect(self.adicionar_junction);self.corpos[3].addWidget(b)
        self.controles_info=QLabel('Nenhum controle pontual importado.');self.controles_info.setWordWrap(True);self.corpos[3].addWidget(self.controles_info)
        self.fatores=[1.,.3048];self.junctions=TabelaConsulta(['DomainElementID','Label','Fator','X bruto','Y bruto','X convertido','Y convertido','Desvio (m)','Active Topology','Resultado']);self.corpos[3].addWidget(self.junctions,1)
        self.estatisticas=TabelaConsulta(['Fator','Unidade hipotética','Pares compatíveis','Geometrias comparadas','Vértices','Média (m)','Mediana (m)','Máximo (m)','P95 (m)','P99 (m)','Inconsistências']);self.corpos[4].addWidget(self.estatisticas)
        self.mostrar=QPushButton('Mostrar amostras e divergências candidatas no mapa');self.mostrar.clicked.connect(self.mostrar_mapa);self.corpos[4].addWidget(self.mostrar)
        self.avaliacao=QLabel();self.avaliacao.setWordWrap(True);self.corpos[5].addWidget(self.avaliacao)
        f=QFormLayout();self.crs_documental=QLineEdit();self.documento=QLineEdit();self.responsavel=QLineEdit(pai.resp_evidencia.text())
        f.addRow('CRS documental (somente se metadados ausentes)',self.crs_documental);f.addRow('Fonte documental adicional',self.documento);f.addRow('Responsável pela aprovação *',self.responsavel);self.corpos[5].addLayout(f)
        b=QPushButton('Anexar documento de evidência (copiado para a nova versão)…');b.clicked.connect(self.anexar);self.corpos[5].addWidget(b);self.anexo=None
        self.resumo=QLabel();self.resumo.setWordWrap(True);self.corpos[6].addWidget(self.resumo)
        self.aprovar=QCheckBox('Aprovo tecnicamente as evidências apresentadas; compatibilidade espacial não comprova conectividade hidráulica');self.corpos[6].addWidget(self.aprovar)
        self.estado=QLabel('Detectando automaticamente…');self.estado.setWordWrap(True);v.addWidget(self.estado);self.barra=QProgressBar();v.addWidget(self.barra)
        l=QHBoxLayout();v.addLayout(l);self.voltar=QPushButton('Voltar');self.avancar=QPushButton('Avançar');self.sair=QPushButton('Cancelar')
        for b in (self.voltar,self.avancar,self.sair):l.addWidget(b)
        self.voltar.clicked.connect(lambda:self.pagina(max(0,self.paginas.currentIndex()-1)));self.avancar.clicked.connect(self.proximo);self.sair.clicked.connect(self.reject)
        self.crs.textChanged.connect(self.invalidar);self.tolerancia.valueChanged.connect(self.invalidar)
        self.crs_documental.textChanged.connect(self.atualizar_avaliacao);self.documento.textChanged.connect(self.atualizar_avaliacao)
        adaptar_janela(self);self.pagina(0);self.executar(self.detectar,self.detectado)

    def executar(self,funcao,pronto):
        if self.trabalho and self.trabalho.isRunning():return
        self.pai.ocupado=True
        self.paginas.setEnabled(False)
        self.voltar.setEnabled(False);self.avancar.setEnabled(False);self.barra.setRange(0,0)
        self.trabalho=Trabalho(funcao,self);self.trabalho.progresso.connect(self.progresso)
        self.trabalho.pronto.connect(pronto);self.trabalho.erro.connect(self.erro);self.trabalho.finished.connect(self.terminou);self.trabalho.start()
    def progresso(self,n,texto):self.barra.setRange(0,100);self.barra.setValue(n);self.estado.setText(texto)
    def terminou(self):
        self.pai.ocupado=False;self.paginas.setEnabled(True);self.barra.setRange(0,100);self.barra.setValue(100);self.voltar.setEnabled(self.paginas.currentIndex()>0);self.avancar.setEnabled(self.t is not None and self._publicacao is None)
        if self.resultado:self.accept();self.pai.show();self.pai.raise_();self.pai.activateWindow()
    def erro(self,erro):self.estado.setText('Operação não concluída: '+erro+'. A base e as fontes anteriores permanecem intactas.');self.aprovar.setChecked(False)
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
        self.t=dados['t'];self.metadados=dados['metadados'];self.assinatura=dados['assinatura_gis'];self.evidencias=dados['evidencias'];self.gis=dados['gis'];m=self.t['meta_base']
        self.fontes.preencher([['Auditoria GIS',self.d['execucao_uid']],['Base WaterGEMS',m['uuid']],['Modelo',m['nome']],['Cenário',m['cenario']],['Perspectiva',self.pai.modo.currentText()],['Versão',m['versao']],['Assinatura técnica',ref.contexto_modelo(self.t['modelo'])],['CRS do projeto QGIS',self.crs_projeto],['CRS da auditoria',self.gis['crs_auditoria']]])
        linhas=[[r['tabela'],r['campo'],r['bruto'],r['interpretacao'],r['confiabilidade']] for r in self.metadados['registros']]
        linhas += [[r['camada'],'CRS GIS',r['crs'],r['unidade']+' · '+r['origem_informacao'],r['estado']+(' · CRS difere do registrado na auditoria' if r['inconsistencia'] else '')] for r in self.gis['camadas']]
        linhas += [[e['base'],'Evidência anterior',e['referencia']['crs'],e['referencia']['fator'],'CONTEXTO COMPATIVEL'] for e in self.evidencias]
        linhas += [['Catálogo da pasta selecionada','Aviso',aviso,'Base ativa pode ser analisada independentemente do índice','VERIFICAR'] for aviso in self.avisos_catalogo]
        self.metatabela.preencher(linhas);self.crs.setText(self.metadados.get('crs') or self.gis['crs_auditoria'])
        self.candidatos.preencher([[r[k] for k in ('camada','campo','preenchidos','nulos','vazios','repetidos','exatas','unicas','multiplas','nao_encontradas','recomendacao')] for r in dados['campos']])
        for origem in dict.fromkeys(r['origem'] for r in dados['campos']):
            rs=[r for r in dados['campos'] if r['origem']==origem];combo=QComboBox();combo.addItem('Não associar esta camada',None)
            for r in rs:combo.addItem(r['campo']+(' — '+r['recomendacao'] if r['recomendacao'] else ''),r['campo'])
            anterior=self.pai.mapas.get(origem);escolhido=anterior.currentData() if anterior else None
            recomendado=next((r['campo'] for r in rs if r['recomendacao'].startswith('RECOMENDADO')),None)
            combo.setCurrentIndex(max(0,combo.findData(escolhido or recomendado)));combo.currentIndexChanged.connect(self.invalidar)
            i=self.selecao.rowCount();self.selecao.insertRow(i);self.selecao.setItem(i,0,QTableWidgetItem(rs[0]['camada']));self.selecao.setCellWidget(i,1,combo);self.combos[origem]=combo
        r=m.get('referencia_espacial') or {};v=r.get('validacao',{})
        if self.assinatura and v.get('fontes_gis')==self.assinatura and ref.estado_referencia(r,self.t['modelo'])['estado']=='VALIDADO':
            self.reuso=r;self.estado.setText('Validação desta composição e destas fontes recuperada. Pode utilizá-la sem repetir comparações.');self.avancar.setText('Utilizar validação existente')
        else:self.estado.setText(self.metadados['mensagem']+' Recomendações prontas; confira as etapas e confirme as colunas.')
    def invalidar(self,*args):self.relatorio=None;self.reuso=None;self.aprovar.setChecked(False)
    def pagina(self,i):
        self.paginas.setCurrentIndex(i);self.titulo.setText(self.paginas.currentWidget().objectName());self.voltar.setEnabled(i>0);self.avancar.setText('Confirmar e salvar nova versão…' if i==6 else 'Comparar automaticamente' if i==3 else 'Avançar')
        if i in (5,6):self.atualizar_avaliacao()
    def proximo(self):
        if self.reuso and self.paginas.currentIndex()==0:self.pai.usar_base(self.base);self.accept();return
        i=self.paginas.currentIndex()
        if i==2 and (not self.confirmar_campos.isChecked() or not any(c.currentData() for c in self.combos.values())):
            QMessageBox.information(self,'Correspondência pendente','Confira e confirme explicitamente ao menos uma coluna GIS. Empates e repetições não são vínculos inequívocos.');return
        if i==3:
            crs=self.crs.text().strip();mapa={k:c.currentData() for k,c in self.combos.items()};tol=self.tolerancia.value()
            def comparar(cancelar,progresso):
                if self.assinatura!=assinatura_gis(self.d,cancelar):raise ValueError('Fontes GIS mudaram após a detecção; reabra o assistente')
                regs,avisos=registros_gis(self.d,mapa,crs,cancelar,registrar_operacoes=True);r=det.comparar_hipoteses(self.t['modelo'],regs,crs,tol,self.fatores,self.controles,cancelar,progresso)
                if self.assinatura!=assinatura_gis(self.d,cancelar):raise ValueError('Fontes GIS mudaram durante a comparação; resultado não publicado')
                r['mapeamento']=mapa;r['avisos']=avisos;r['transformacoes_gis']=list({g['origem']:g['operacao_crs'] for g in regs}.values());return r
            self.executar(comparar,self.comparado);return
        if i==6:self.salvar();return
        self.pagina(i+1)
    def comparado(self,r):
        self.relatorio=r;self.aprovar.setChecked(False)
        self.estatisticas.preencher([[h[k] for k in ('fator','unidade','compativeis','geometrias_comparadas','vertices_comparados','media_m','mediana_m','maximo_m','p95_m','p99_m','inconsistencias')] for h in r['hipoteses']])
        self.junctions.preencher([[c.get(k) for k in ('id','label','fator','x_bruto','y_bruto','x_convertido','y_convertido','erro_m','ativo','estado')] for h in r['hipoteses'] for c in h['junctions']]);self.pagina(4);self.estado.setText('Hipóteses comparadas. Examine divergências, controles e pendências antes de aprovar.')
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
        documental=self.crs_documental.text().strip() if self.documento.text().strip() else None
        if not md.get('crs') and not documental:
            e=next((e for e in self.evidencias if e['referencia']['crs']==self.relatorio['crs']),None)
            if e:documental=e['referencia']['crs']
        a=det.avaliar(self.t,self.relatorio,md,documental);self.documental_efetivo=documental;self.avaliacao.setText(a['estado']+'\n'+'\n'.join(a['faltas'])+'\nCRS declarado e unidade inferida são evidências diferentes de conectividade hidráulica.')
        self.resumo.setText(f"Base: {self.t['meta_base']['nome']} · {self.t['meta_base']['uuid']}\nCRS comparação: {self.relatorio['crs']}\nFator recomendado: {self.relatorio['fator_recomendado']}\nGIS examinadas: {self.relatorio['gis_examinadas']}; WG: {self.relatorio['wg_examinadas']}\n{a['estado']} · {'; '.join(a['faltas'])}\nA gravação cria nova versão, UUID próprio e JSON relacional. A versão anterior permanece intacta.")
    def salvar(self):
        if self._publicacao or self.resultado or self.trabalho and self.trabalho.isRunning():return
        try:
            ausente=not self.responsavel.text().strip();self.responsavel.setStyleSheet('border: 1px solid #b53030;' if ausente else '')
            if ausente:self.pagina(5);raise ValueError('Informe o responsável (*) pela confirmação definitiva. Os dados preenchidos foram mantidos.')
            self.atualizar_avaliacao();doc=dict(crs=self.documental_efetivo,fonte=self.documento.text().strip())
            if not doc['fonte'] and self.documental_efetivo:
                e=next(e for e in self.evidencias if e['referencia']['crs']==self.documental_efetivo);doc['fonte']=e['referencia']['fonte'];doc['base_evidencia']=e['base'];doc['sha256']=hash_arquivo(e['base'])
            r=det.confirmar_assistida(self.t,self.relatorio,self.metadados,self.aprovar.isChecked(),self.responsavel.text(),doc)
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
