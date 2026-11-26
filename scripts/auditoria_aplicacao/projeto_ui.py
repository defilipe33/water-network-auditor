"""Operações sobre o manifesto, referências e resultados já calculados."""

from copy import deepcopy
from pathlib import Path
import sqlite3

from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox

from . import estado_projeto as estado, trabalhos_projeto as tp
from .manifesto_projeto import nome_arquivo, organizar
from .navegacao_cartografica import acao_disponivel
from .tabelas_topologia_gis import TabelaGIS


class TabelaTrabalhos(TabelaGIS):
    def count(self):
        return self.rowCount()

    def setCurrentRow(self, i):
        self.setCurrentCell(i,0)

    def currentItem(self):
        return self.item(self.currentRow(),0)


class GestaoProjetosUI:
    def detalhe_localizacao(self):
        p=self.projetos.atual()
        manifesto=p.get('manifesto_wna') if p else None
        referencia=(manifesto or 'Projeto registrado no índice local — ainda sem arquivo .wna próprio.') if p else 'Selecione um projeto.'
        return f'{referencia}\nPasta de trabalho do Auditor\n{self.app.catalogo.raiz}'

    def mostrar_localizacao(self):
        QMessageBox.information(self,'Localização do projeto',self.detalhe_localizacao())

    def copiar_localizacao(self):
        p=self.projetos.atual() or {}
        caminho=p.get('manifesto_wna') or self.projetos.path
        QApplication.clipboard().setText(str(caminho))
        self.receber_mapa('Caminho copiado.')

    def abrir_pasta_projeto(self):
        p=self.projetos.atual() or {}
        self.abrir_pasta_local(Path(p.get('manifesto_wna') or self.projetos.path).parent)

    def abrir_pasta_local(self,pasta):
        if not pasta.is_dir():
            self.receber_mapa(f'Pasta indisponível: {pasta}')
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(pasta))):
            self.receber_mapa(f'Não foi possível abrir a pasta: {pasta}')

    def organizar_existente(self):
        if not self._resolver_troca_projeto() or not self.projetos.atual():return
        p=deepcopy(self.projetos.atual())
        opcoes=['Atualizar o manifesto no local atual' if p.get('manifesto_wna') else
                'Criar manifesto mantendo os arquivos onde estão','Criar cópia portátil em nova pasta']
        modo,ok=QInputDialog.getItem(self,'Organizar projeto existente',self.detalhe_localizacao(),opcoes,editable=False)
        if not ok:return
        copiar=modo==opcoes[1]
        nome=nome_arquivo(p['nome'])
        if copiar:
            pasta=QFileDialog.getExistingDirectory(self,'Pasta que receberá o projeto portátil')
            if not pasta:return
            destino=Path(pasta)/(nome+'_portatil')/(nome+'.wna')
        elif p.get('manifesto_wna'):
            destino=Path(p['manifesto_wna'])
        else:
            arq,_=QFileDialog.getSaveFileName(self,'Novo manifesto .wna',nome+'.wna','Projeto Water Network Auditor (*.wna)')
            if not arq:return
            destino=Path(arq)
        estados=[(estado.arquivo(self.app.catalogo.raiz,p,t),estado.caminho_relativo(p,t))
                 for t in (estado.VISUAL,estado.RASCUNHO)]
        def pronto(resultado):
            caminho,avisos,atualizado=resultado
            if atualizado is None:self.projetos.adotar_organizado(caminho,p)
            else:self.projetos.atualizar_organizado(p,atualizado)
            self._manifesto_aberto()
            msg=f'Projeto organizado em {caminho}.'
            if avisos:msg+='\n'+ '\n'.join(avisos)
            self.receber_mapa(msg)
        self.app.atividades.executar_thread('Organizar projeto',p['nome'],
            lambda parar,etapa:organizar(p,destino,copiar,parar,etapa,estados),pronto,self.receber_mapa)

    def consultar_arquivos(self):
        p=self.projetos.atual()
        if not p:return
        def trabalho(parar,etapa):
            from auditoria_fronteiras.modelos import verificar_cancelamento
            fichas=[];linhas=[]
            for r in p['bases']:
                verificar_cancelamento(parar)
                etapa(0,'Conferindo '+Path(r['base']).name)
                try:
                    x=tp.conferir(p['uuid'],r)
                    linhas.append(f'{x["nome"]} · verificado\n{x["base"]}')
                    fichas.append(x)
                except (ValueError,OSError,sqlite3.Error) as e:
                    linhas.append(f'{r["base"]} · {e}')
                    fichas.append(dict(r,erro=str(e)))
            if arq:=p.get('arquivo_complementos'):
                from .persistencia_grafo_gis import identidade
                try:
                    identidade(arq,p['uuid'])
                    linhas.append('Complementos e hipóteses · verificado\n'+arq)
                except (ValueError,OSError,sqlite3.Error) as e:
                    linhas.append(f'{arq} · {e}')
            from .modelo_gis import revisoes
            rev=next(reversed(revisoes(p)),{})
            for f in rev.get('fontes',()):
                linhas.append(f'Fonte GIS · {f["nome"]}\n{f.get("uri","")}')
            return fichas,linhas
        def pronto(d):
            fichas,linhas=d
            self._extras_trabalhos.update({tp.chave(r):r for r in fichas})
            self.listar_trabalhos()
            msg=QMessageBox(self)
            msg.setWindowTitle('Arquivos vinculados')
            msg.setTextFormat(Qt.PlainText)
            msg.setText(self.detalhe_localizacao()+f'\n{len(fichas)} trabalhos conferidos.')
            msg.setDetailedText('\n\n'.join(linhas))
            # A janela só é apresentada após a conclusão da tarefa.
            msg.setAttribute(Qt.WA_DeleteOnClose)
            msg.show()
        self.app.atividades.executar_thread('Conferir arquivos vinculados',p['nome'],trabalho,pronto,self.receber_mapa)

    def recuperar_orfaos(self):
        p=self.projetos.atual()
        if not p or self.ocupado():return
        bases=[Path(self.app.catalogo.raiz)/k/p['uuid'] for k in ('topologia_gis','estrutura_gis')]
        if p.get('manifesto_wna'):bases.append(Path(p['manifesto_wna']).parent)
        def pronto(rs):
            from qgis.PyQt.QtCore import QTimer
            QTimer.singleShot(0,lambda:self.escolher_orfao(rs,p['uuid']))
        self.app.atividades.executar_thread('Procurar trabalhos sem referência',p['nome'],
            lambda parar,_:tp.descobrir(p,bases,parar),pronto,self.receber_mapa)

    def escolher_orfao(self,rs,uid):
        if self.ocupado() or (self.projetos.atual() or {}).get('uuid')!=uid:return
        if not rs:
            self.receber_mapa('Nenhum trabalho sem referência foi identificado nas pastas do projeto.')
            return
        rotulos=[f'{r["nome"]} · {r["uuid"][:8]} · {r["base"]}' for r in rs]
        nome,ok=QInputDialog.getItem(self,'Recuperar trabalho sem referência','Arquivo a registrar',rotulos,editable=False)
        if ok:self.confirmar_vinculo(rs[rotulos.index(nome)],None,exigir_projeto=True)

    def confirmar_vinculo(self,r,caminho,exigir_projeto=False):
        p=self.projetos.atual()
        if not p or self.ocupado():return
        def conferir(*_):
            x=tp.conferir(p['uuid'],r,caminho)
            if exigir_projeto and x.get('projeto_uid')!=p['uuid']:
                raise ValueError('A identidade do projeto não está gravada neste arquivo.')
            return x
        def pronto(x):
            self.projetos.vincular(x,atualizar_ultimo=not exigir_projeto)
            self._registros=[a for a in self._registros if tp.chave(a)!=tp.chave(x)]+[x]
            self._extras_trabalhos[tp.chave(x)]=x
            self.listar_trabalhos()
            self.receber_mapa('Referência verificada e registrada no projeto.')
        self.app.atividades.executar_thread('Verificar referência do trabalho',p['nome'],conferir,pronto,self.receber_mapa)

    def registros_projeto(self):
        rs=tp.registros(self.projetos.atual(),self._registros,self._extras_trabalhos)
        visual=self.estados_de_visualizacao()
        return [dict(r,nome=self.nome_analise(r['tipo'],r['uuid'],r['nome'],visual)) for r in rs]

    def nome_analise(self,tipo,uid,nome,visual=None):
        if visual is None:visual=self.estados_de_visualizacao()
        return visual.get(f'{tipo}:{uid}',{}).get('nome_consulta') or nome

    def renomear_analise(self,r):
        p=self.projetos.atual()
        if not p or self.ocupado() or not self.projetos.contem(r['tipo'],r['uuid']):return
        nome,ok=QInputDialog.getText(self,'Renomear análise salva','Nome de apresentação',text=r['nome'])
        if ok and nome.strip():
            self._guardar_visual(p,r['tipo'],r['uuid'],visual={'nome_consulta':nome.strip()})
            self.listar_trabalhos()

    def parametros_analise(self,r):
        import json
        from . import persistencia_grafo_gis as pg
        p=self.projetos.atual()
        uid=p['uuid']
        abrir=pg.carregar if r['tipo']=='TOPOLOGIA_GIS' else pg.carregar_estrutura
        def consultar(*_):
            d=abrir(r['base'],r['uuid'],uid)
            return dict(parametros=d.get('parametros',{}),origens=d.get('fontes') if r['tipo']=='ESTRUTURA_GIS'
                        else d.get('origens_validas'),hipotese=(d.get('hipotese') or {}).get('nome'),
                        configuracao=d.get('configuracao'))
        def pronto(d):
            from qgis.PyQt.QtCore import QTimer
            QTimer.singleShot(0,lambda:QMessageBox.information(
                self,r['nome'],json.dumps(d,ensure_ascii=False,indent=2)))
        self.app.atividades.executar_thread('Consultar parâmetros',p['nome'],consultar,pronto,self.receber_mapa)

    def ultimo_trabalho(self):
        p=self.projetos.atual()
        if p and (r:=p.get('ultima')):
            return next((x for x in self.registros_projeto() if tp.chave(x)==tp.chave(r)),None)
        return next(iter(self.registros_projeto()),None) if p else None

    def atualizar_continuacao(self):
        uid=(self.projetos.atual() or {}).get('uuid')
        if uid!=self._uid_escolhas:
            self._uid_escolhas=uid
            self.escolhas_projeto.setVisible(bool(uid))
        r=self.ultimo_trabalho()
        acao_disponivel(self.continuar_trabalho_b,'' if r else 'Salve pelo menos um trabalho no projeto.')
        if r:
            data=(r.get('data') or '')[:19].replace('T',' ')
            self.ultimo_trabalho_info.setText(f"Último salvo · {r['nome']}\n{tp.ROTULOS.get(r['tipo'],r['tipo'])}"
                                             +(f" · {data} UTC" if data else ''))
        else:self.ultimo_trabalho_info.setText('Nenhum trabalho salvo neste projeto.')

    def continuar_trabalho(self):
        if r:=self.ultimo_trabalho():
            if self.abrir_trabalho(registro=r,cartografar=True):
                self.escolhas_projeto.hide()

    def abrir_analises_projeto(self,tipo=None):
        if isinstance(tipo,str):self.tipo_trabalho.setCurrentIndex(self.tipo_trabalho.findData(tipo))
        self.area.setCurrentIndex(self.area.findData('trabalhos'))
        self.mudar_area()

    def nova_investigacao(self):
        self.area.setCurrentIndex(self.area.findData('investigar'))
        self.mudar_area()

    def listar_execucoes_salvas(self,hipotese_uid=None):
        if not self.projetos.atual():return
        self._filtro_hipotese_uid=hipotese_uid
        self._preservar_filtro_hipotese=True
        try:
            self.tipo_trabalho.setCurrentIndex(self.tipo_trabalho.findData('TOPOLOGIA_GIS'))
            self.pesquisa.clear()
        finally:
            self._preservar_filtro_hipotese=False
        self.area.setCurrentIndex(self.area.findData('trabalhos'))
        self.mudar_area()
        if self.paginas.currentWidget() is self.trabalhos:self.enriquecer_lista(legado=True)

    def enriquecer_lista(self,legado=False):
        p=self.projetos.atual()
        if not p or self.ocupado():return
        rs=[r for r in self.registros_projeto() if r['disponivel'] and not r.get('erro') and
            (not r.get('data') or legado and r['tipo'] in tp.TABELAS and 'hipotese_rev' not in r)]
        if not rs:return
        def trabalho(parar,etapa):
            from auditoria_fronteiras.modelos import verificar_cancelamento
            saida={}
            for r in rs:
                verificar_cancelamento(parar)
                etapa(0,'Lendo metadados de '+r['nome'])
                try:saida[tp.chave(r)]=tp.metadados(p['uuid'],r,legado=legado)
                except (ValueError,OSError,sqlite3.Error) as e:saida[tp.chave(r)]=dict(r,erro=str(e))
            return saida
        def pronto(d):
            self._extras_trabalhos.update(d)
            self.listar_trabalhos()
        self.app.atividades.executar_thread('Ler metadados de trabalhos anteriores',p['nome'],trabalho,pronto,self.receber_mapa)

    def historico_trabalho(self,r):
        dados=[f"{r['nome']} · {r['uuid']}", r['base']]
        for k,titulo in [('hipotese_nome','Hipótese'),('hipotese_rev','Revisão'),('topologia_uid','Execução de origem'),
                         ('referencia','Trabalho de referência'),('componentes','Componentes'),('origens','Fontes'),
                         ('conexoes','Conexões'),('data','Data')]:
            if r.get(k) is not None:dados.append(f'{titulo} · {r[k]}')
        for atual in r.get('localizacoes',()):
            dados.append(f'Localização anterior · {atual["caminho"]} · {atual["data"]}')
        QMessageBox.information(self,'Histórico e dependências','\n'.join(dados))
