"""Assistente e histórico do pacote de importação ModelBuilder."""

from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from uuid import uuid4

from qgis.PyQt.QtCore import Qt
from qgis.PyQt import sip
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QInputDialog,QMessageBox,
    QDoubleSpinBox, QHBoxLayout, QLineEdit, QScrollArea, QStackedWidget, QVBoxLayout, QWidget)
from qgis.core import QgsGeometry,QgsPointXY

from auditoria_fronteiras.modelos import verificar_cancelamento
from auditoria_fronteiras.entradas import digest
from . import cadastro_exportavel as cadastro
from . import conjuntos_modelagem as cm
from . import modelbuilder_conferencia as conferir
from . import modelbuilder_gis as mb
from . import persistencia_grafo_gis as pg
from .manifesto_projeto import pasta_projeto
from .modelo_gis_ui import aviso, botao, formulario
from .publicar_pasta_gis import publicar
from .labels_modelagem import PREFIXOS
from .navegacao_cartografica import navegar_registros
from .seletor_multiplos import escolher,opcoes_corredores
from .tabelas_topologia_gis import TabelaGIS
from .validacao_modelbuilder_gis import linha
from .investigacao_gis import geometria


GRAVIDADES={'CRITICA':'Crítica','AVISO':'Aviso','HIDRAULICA':'Hidráulica','INFORMACAO':'Informação'}


def _combo(pares):
    c=QComboBox()
    for rotulo,k in pares:
        c.addItem(rotulo,k)
    return c


def _revisoes(pagina,tipo):
    return {r['uuid']:r for r in pg.revisoes(pagina._complementos(),pagina._projeto()['uuid'],tipo=tipo)}


def _pasta(p,r=None):
    if r and r.get('relativo'):
        if not p.get('manifesto_wna'):
            raise ValueError('Abra o manifesto .wna antes de acessar o caminho relativo.')
        raiz=Path(p['manifesto_wna']).parent.resolve()
        destino=(raiz/r['pasta']).resolve()
        if not destino.is_relative_to(raiz):
            raise ValueError('A referência relativa está fora da pasta do projeto.')
        return destino
    return Path(r['pasta']) if r else pasta_projeto(p,'EXPORTACOES',Path.home())


class AssistenteModelBuilder(QDialog):
    def __init__(self,pagina,previa):
        super().__init__(pagina)
        self.setWindowTitle('Exportar modelo para WaterGEMS')
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(715,565)
        self.pagina=pagina
        self.projeto=pagina._projeto()
        self.foto=pagina.foto
        self.previa=previa
        self.perfis=_revisoes(pagina,'MODELBUILDER_PERFIL')
        self.conjuntos={u:r for u,r in _revisoes(pagina,'CONJUNTO_WG').items() if not r.get('arquivado') and
                        r['topologia_uid']==previa['manifesto']['execucao']}
        self.escopo_chaves=None
        self.origens_escopo=list(previa['manifesto']['origens'])
        self.conjuntos_ids=[]
        self._etapas=[]
        self._validado=None
        self._operacao=None
        v=QVBoxLayout(self)
        self.titulo_etapa=aviso()
        v.addWidget(self.titulo_etapa)
        self.tabs=QStackedWidget()
        v.addWidget(self.tabs)
        selecao=self._aba('Origem e escopo')
        m=previa['manifesto']
        totais=m['contagens']
        hip=m.get('hipotese') or {}
        selecao.addWidget(aviso(f"{self.projeto['nome']} · {hip.get('nome','Hipótese temporária')} · revisão "
            f"{str(hip.get('rev') or '—')[:12]}\nExecução {m['execucao'][:12]} · cadastro {str(m['modelo_cadastral_rev'])[:12]}\n"
            f"{totais['conexoes_aplicadas']} conexões aplicadas · {totais['complementares']} Pipes complementares"))
        self.escopo=_combo((('Cadastro completo','COMPLETO'),('Participantes da hipótese','HIPOTESE'),
            ('Rede alcançável pelas origens selecionadas','ALCANCAVEL'),('Corredores calculados','CORREDORES'),
            ('Blocos calculados','BLOCOS'),('Áreas cadastradas','AREAS'),('Conjuntos personalizados','CONJUNTOS')))
        form=formulario(selecao)
        form.addRow('Escopo',self.escopo)
        self.escopo.currentIndexChanged.connect(self._mudar_escopo)
        self.escolher_escopo_b=botao(selecao,'Escolher elementos do escopo…',lambda:self._acao(self._escolher_escopo))
        self.escolher_escopo_b.setVisible(False)
        self.selecao_resumo=aviso('O cadastro completo inclui Pipes isolados e fora da hipótese.')
        selecao.addWidget(self.selecao_resumo)
        selecao.addStretch()
        dados=self._aba('Elementos e atributos')
        self.perfis_combo=_combo([('Novo perfil',None),*((r['nome']+' · '+u[:8],u) for u,r in self.perfis.items())])
        form=formulario(dados)
        form.addRow('Perfil salvo',self.perfis_combo)
        self.nome=QLineEdit('Preparação GIS')
        form.addRow('Nome do perfil',self.nome)
        self.destino=_combo((v,v) for v in mb.DESTINOS)
        self.destino.setCurrentText('2026')
        form.addRow('Versão de destino',self.destino)
        self.modo=_combo((('Criar modelo de teste','NOVO'),('Preparar atualização','ATUALIZAR')))
        form.addRow('Operação',self.modo)
        self.modelo=QLineEdit()
        form.addRow('Identidade do modelo de destino',self.modelo)
        self.anterior=QLineEdit()
        self.anterior.setReadOnly(True)
        form.addRow('Pacote de referência',self.anterior)
        botao(dados,'Localizar pacote ModelBuilder anterior…',self.localizar_anterior)
        self.observado=QLineEdit()
        self.observado.setReadOnly(True)
        form.addRow('FlexTables do destino (opcional)',self.observado)
        botao(dados,'Localizar CSV para a prévia de atualização…',self.localizar_observado)
        nomes={t:t.title() for t in mb.PROPRIEDADES}
        self.tipos={}
        self.campos={}
        atribuiveis=defaultdict(set)
        for r in previa['cadastro']:
            atribuiveis[r['categoria']].update(r.get('atributos_originais') or {})
        for tipo,props in mb.PROPRIEDADES.items():
            incluir=QCheckBox(nomes[tipo])
            incluir.setChecked(tipo in ('PIPE','JUNCTION'))
            incluir.setEnabled(tipo not in ('PIPE','JUNCTION'))
            dados.addWidget(incluir)
            self.tipos[tipo]=incluir
            f=formulario(dados)
            self.campos[tipo]={}
            for propriedade,(rotulo,unidade) in props.items():
                c=_combo([('Em branco',None),*((k,k) for k in sorted(atribuiveis[tipo]))])
                u=_combo((x,x) for x in (('C',) if unidade=='C' else ('m','cm','mm','km','ft')))
                f.addRow(rotulo,c)
                f.addRow('Unidade do campo',u)
                self.campos[tipo][propriedade]=(c,u)
        dados.addWidget(aviso('A chave técnica, o Label previsto, o GIS-ID original e os nós Start/Stop são inclusos. '
            'Reservoirs e Tanks precisam de atributos e vínculo verificados. Os demais equipamentos seguem no inventário.'))
        self.perfis_combo.currentIndexChanged.connect(self._aplicar_perfil)
        self.preservar_label=QCheckBox('Reutilizar Labels cadastrais curtos e únicos quando disponíveis')
        self.preservar_label.setChecked(True)
        dados.addWidget(self.preservar_label)
        campos_prefixos=formulario(dados)
        self.prefixos={}
        for tipo,prefixo in PREFIXOS.items():
            entrada=QLineEdit(prefixo)
            entrada.setMaxLength(6)
            campos_prefixos.addRow('Prefixo '+tipo.title(),entrada)
            self.prefixos[tipo]=entrada
        botao(dados,'Salvar perfil no projeto',lambda:self._acao(self._salvar_perfil))
        etapa3=self._aba('Atividade e conjuntos')
        self.atividade=_combo((('Manter atividade da prévia','PREVIA'),('Ativos na hipótese','HIPOTESE'),('Tudo a definir','INDEFINIDA')))
        f=formulario(etapa3)
        f.addRow('Atividade pretendida',self.atividade)
        botao(etapa3,'Incluir conjuntos salvos…',self.escolher_conjuntos)
        etapa3.addWidget(aviso('A regra de atividade é independente do alcance. As exceções por Pipe físico continuam aplicáveis.'))
        etapa3.addStretch()
        final=self._aba('Validação e exportação')
        f=formulario(final)
        self.formato=_combo((('Shapefile e tabelas','ESRI Shapefile'),('GeoPackage e tabelas','GPKG'),('CSV com WKT','CSV')))
        f.addRow('Formato',self.formato)
        self.tolerancia=QDoubleSpinBox()
        self.tolerancia.setRange(0,1)
        self.tolerancia.setDecimals(4)
        self.tolerancia.setValue(.001)
        self.tolerancia.setSuffix(' m')
        f.addRow('Tolerância de conferência',self.tolerancia)
        self.aneis=QCheckBox('Segmentar anéis simples com nó original verificado')
        final.addWidget(self.aneis)
        self.parcial=QCheckBox('Exportar apenas elementos válidos e registrar as exclusões')
        self.parcial.setEnabled(False)
        final.addWidget(self.parcial)
        self.destino_pacote=QLineEdit()
        self.destino_pacote.setReadOnly(True)
        f.addRow('Pasta de destino',self.destino_pacote)
        botao(final,'Escolher pasta…',self.escolher_pasta)
        self.validacao=aviso(f"Prévia · {totais['originais_materializados']} de {totais['pipes_originais']} Pipes físicos · {totais['segmentos']} segmentos · "
            f"{totais['pipes_divididos']} divididos\n{totais['fora_da_hipotese']} segmentos fora da hipótese · "
            f"{totais['sem_origem']} sem origem · {totais['atividade'].get('INATIVO',0)} previstos como inativos\n"
            f"{totais['junctions']} nós · {totais['equipamentos']} equipamentos inventariados · {totais['sem_diametro']} sem diâmetro.\n"
            +( 'Existem lacunas. Consulte a tabela de pendências antes de importar.' if m['lacunas'] else 'O pacote inclui uma ficha de conferência para o ModelBuilder.'))
        final.addWidget(self.validacao)
        self.tabela_pendencias=TabelaGIS()
        self.tabela_pendencias.colunas(('Gravidade','Tipo','ID GIS ou UID','Camada','Ocorrência'))
        self.tabela_pendencias.setMinimumHeight(180)
        self.filtro_pendencias=_combo((('Todas as pendências',None),
            *((nome,('gravidade',k)) for k,nome in GRAVIDADES.items()),
            ('Pipes',('tipo','PIPE')),('Junctions',('tipo','JUNCTION')),
            ('Equipamentos',('classe','EQUIPAMENTO')),('Atributos',('classe','ATRIBUTO')),
            ('Topologia e conexões',('classe','TOPOLOGIA')),('Cobertura',('classe','COBERTURA'))))
        self._pendencias=[]
        self._linhas_pendencia=[]
        final.addWidget(self.filtro_pendencias)
        final.addWidget(self.tabela_pendencias)
        self.filtro_pendencias.currentIndexChanged.connect(self._listar_pendencias)
        navegar_registros(self.tabela_pendencias,self._localizar_pendencia,self._menu_pendencia,pagina.central.mapa.limpar)
        botao(final,'Diâmetros por fonte…',self.diametros)
        botao(final,'Conferir importações ou reabrir pacotes…',self.abrir_historico)
        final.addStretch()
        self.status=aviso()
        v.addWidget(self.status)
        botoes=QHBoxLayout()
        v.addLayout(botoes)
        self.voltar_b=botao(botoes,'‹ Voltar',lambda:self.tabs.setCurrentIndex(self.tabs.currentIndex()-1))
        self.proximo_b=botao(botoes,'Próximo ›',lambda:self._acao(self.proximo))
        self.validar_b=botao(botoes,'Validar',lambda:self._acao(self.validar))
        self.exportar_b=botao(botoes,'Exportar pacote',lambda:self._acao(self.exportar))
        botao(botoes,'Cancelar',self.cancelar)
        self.tabs.currentChanged.connect(self._mostrar_etapa)
        self._mostrar_etapa()

    def abrir_historico(self):
        self._historico=HistoricoModelBuilder(self.pagina,self)
        self._historico.open()

    def _aba(self,nome):
        scroll=QScrollArea()
        scroll.setWidgetResizable(True)
        w=QWidget()
        layout=QVBoxLayout(w)
        scroll.setWidget(w)
        self.tabs.addWidget(scroll)
        self._etapas.append(nome)
        return layout

    def _mostrar_etapa(self,*_):
        i=self.tabs.currentIndex()
        self.titulo_etapa.setText(f'Etapa {i+1} de {len(self._etapas)} · {self._etapas[i]}')
        self.voltar_b.setEnabled(i>0)
        self.proximo_b.setVisible(i<len(self._etapas)-1)
        self.validar_b.setVisible(i==len(self._etapas)-1)
        self.exportar_b.setVisible(i==len(self._etapas)-1)

    def proximo(self):
        i=self.tabs.currentIndex()
        if i==0:
            self._escopo()
        elif i==1:
            perfil=self._perfil()
            if perfil['modo']=='ATUALIZAR' and not self.anterior.text():
                raise ValueError('Localize o pacote anterior para comparar a atualização.')
        elif i==2:
            escopo=self._escopo()
            if escopo is not None:
                chaves=set(escopo)
                por_uid={p['uid']:p for p in self.previa['pipes']}
                chaves.update(('JUNCTION',por_uid[u][k]) for t,u in escopo if t=='PIPE' for k in ('no_a','no_b'))
                if any((e['tipo'],e['uid']) not in chaves for u in self.conjuntos_ids for e in self.conjuntos[u]['membros']):
                    raise ValueError('Alguns membros dos conjuntos selecionados ficaram fora do escopo. Reveja a etapa 1 ou a seleção de conjuntos.')
        self.tabs.setCurrentIndex(i+1)

    def cancelar(self):
        if self._operacao is not None and self._operacao is self.pagina.app.atividades.atual:
            self._operacao.cancelar()
            return
        self.reject()

    def _mudar_escopo(self,*_):
        self.escopo_chaves=None
        self.escolher_escopo_b.setVisible(self.escopo.currentData() not in ('COMPLETO','HIPOTESE'))
        self.selecao_resumo.setText('Confira os elementos e os conjuntos quando mudar o escopo.')

    def escolher_pasta(self):
        sugestao=_pasta(self.projeto)
        if self.projeto.get('manifesto_wna'):
            sugestao.mkdir(parents=True,exist_ok=True)
        pasta=QFileDialog.getExistingDirectory(self,'Destino do pacote ModelBuilder',str(sugestao))
        if pasta:self.destino_pacote.setText(pasta)

    def diametros(self):
        linhas=[]
        for r in self.previa['manifesto'].get('fontes',{}).values():
            d=r.get('diametro')
            if d:
                n=d['contagens']
                linhas.append(f"{r['nome']} · {d['campo'] or 'campo não mapeado'} · {d['unidade'] or 'unidade a confirmar'}\n"
                              f"{n.get('VALIDO',0)} válidos de {sum(n.values())} Pipes lidos · "+
                              ', '.join(f'{v} {k.lower().replace("_"," ")}' for k,v in n.items() if k!='VALIDO'))
        janela=QMessageBox(self)
        janela.setWindowTitle('Diâmetros por fonte')
        janela.setText('\n\n'.join(linhas) or 'O inventário não contém uma contagem por fonte.')
        modelo=janela.addButton('Abrir Modelo GIS',QMessageBox.ActionRole)
        janela.addButton('Fechar',QMessageBox.RejectRole)
        janela.exec()
        if janela.clickedButton() is modelo:
            c=self.pagina.central
            c.area.setCurrentIndex(c.area.findData('preparar'))
            self.reject()

    def _acao(self,fn):
        try:
            return fn()
        except (OSError,ValueError,RuntimeError,sqlite3.Error) as erro:
            self.status.setText(str(erro))

    def _perfil(self):
        campos={t:{k:dict(campo=c.currentData(),unidade=u.currentData()) for k,(c,u) in ps.items() if c.currentData()}
                for t,ps in self.campos.items()}
        return mb.validar_perfil(dict(versao=mb.VERSAO,nome=self.nome.text().strip(),destino=self.destino.currentData(),
            modo=self.modo.currentData(),modelo_destino=self.modelo.text().strip(),tipos=[t for t,b in self.tipos.items()
            if b.isChecked()],campos=campos,politica_remocao='PRESERVAR',preservar_label=self.preservar_label.isChecked(),
            prefixos={t:w.text().strip() for t,w in self.prefixos.items()}))

    def _salvar_perfil(self):
        d=dict(self._perfil(),opcoes=dict(escopo=self.escopo.currentData(),formato=self.formato.currentData(),
            tolerancia=self.tolerancia.value(),atividade=self.atividade.currentData(),aneis=self.aneis.isChecked(),
            execucao=self.foto['uuid'],chaves=sorted(self.escopo_chaves) if self.escopo_chaves is not None else None,
            conjuntos=self.conjuntos_ids,origens=self.origens_escopo,anterior=self.anterior.text(),
            observado=self.observado.text()))
        anterior=self.perfis.get(self.perfis_combo.currentData(),{})
        r=pg.salvar_revisao(self.pagina._complementos(True),self.projeto['uuid'],'MODELBUILDER_PERFIL',d,
                            anterior.get('uuid'),anterior.get('rev'))
        u=r['uuid']
        self.perfis[u]=r
        idx=self.perfis_combo.findData(u)
        if idx<0:
            self.perfis_combo.addItem(r['nome']+' · '+u[:8],u)
            idx=self.perfis_combo.count()-1
        self.perfis_combo.setCurrentIndex(idx)
        self.status.setText('Perfil salvo · revisão '+r['rev'][:8])

    def _aplicar_perfil(self,*_):
        r=self.perfis.get(self.perfis_combo.currentData())
        if not r:
            return
        self.nome.setText(r['nome'])
        self.destino.setCurrentIndex(self.destino.findData(r['destino']))
        self.modo.setCurrentIndex(self.modo.findData(r['modo']))
        self.modelo.setText(r.get('modelo_destino',''))
        self.preservar_label.setChecked(r.get('preservar_label',True))
        for t,w in self.prefixos.items():w.setText(r.get('prefixos',{}).get(t,PREFIXOS[t]))
        for t,ps in self.campos.items():
            self.tipos[t].setChecked(t in r['tipos'])
            for k,(c,u) in ps.items():
                a=r['campos'].get(t,{}).get(k,{})
                c.setCurrentIndex(max(0,c.findData(a.get('campo'))))
                u.setCurrentIndex(max(0,u.findData(a.get('unidade'))))
        if op:=r.get('opcoes'):
            for combo,k in ((self.escopo,'escopo'),(self.formato,'formato'),(self.atividade,'atividade')):
                combo.setCurrentIndex(max(0,combo.findData(op.get(k))))
            self.tolerancia.setValue(op.get('tolerancia',.001))
            self.aneis.setChecked(op.get('aneis',False))
            self.anterior.setText(op.get('anterior',''))
            self.observado.setText(op.get('observado',''))
            if op.get('execucao')==self.foto['uuid']:
                self.escopo_chaves={tuple(k) for k in op['chaves']} if op.get('chaves') is not None else None
                self.conjuntos_ids=[u for u in op.get('conjuntos',()) if u in self.conjuntos]
                self.origens_escopo=[u for u in op.get('origens',self.previa['manifesto']['origens'])
                                    if u in self.foto['origens_validas']]
            else:
                self.escopo_chaves=None
                self.conjuntos_ids=[]
                self.origens_escopo=list(self.previa['manifesto']['origens'])
                self.status.setText('Perfil recuperado. Confira o escopo e os conjuntos para esta execução.')

    def localizar_anterior(self):
        pasta=QFileDialog.getExistingDirectory(self,'Pacote exportado anteriormente')
        if pasta:
            self.anterior.setText(pasta)

    def localizar_observado(self):
        arq,_=QFileDialog.getOpenFileName(self,'CSV do modelo de destino','','CSV (*.csv)')
        if arq:self.observado.setText(arq)

    def escolher_conjuntos(self):
        ids=escolher(self,'Conjuntos para este pacote',
            [(u,r['nome'],r['categoria']) for u,r in self.conjuntos.items()],self.conjuntos_ids)
        if ids is None:return
        self.conjuntos_ids=ids
        self.status.setText(f'{len(ids)} conjuntos selecionados.')
        return ids

    def _escolher_escopo(self):
        modo=self.escopo.currentData()
        macro=self.pagina.macro_integral or {}
        d=self.pagina.dados or {}
        if modo in ('CORREDORES','BLOCOS'):
            chave='corredores' if modo=='CORREDORES' else 'blocos'
            registros=[*macro.get(chave,()),*d.get('agrupamento' if modo=='CORREDORES' else 'blocos',{}).get(chave,())]
            if modo=='BLOCOS':
                registros.extend(macro.get('detalhados',()))
            grupos={r['uid']:r for r in registros}
            opcoes=(opcoes_corredores(list(grupos.values())) if modo=='CORREDORES' else
                    ((u,r.get('nome') or u[:10],r.get('tipo') or 'Blocos') for u,r in grupos.items()))
            ids=escolher(self,'Elementos do escopo',opcoes)
            if ids is None:return
            self.escopo_chaves=cm.por_segmentos(self.foto,{i for u in ids for i in grupos[u]['segmentos']})
        elif modo=='AREAS':
            ids=escolher(self,'Áreas em interseção espacial',
                [(r['uid'],str(r.get('label') or r.get('id') or r['uid'][:10])) for r in self.foto.get('areas',())])
            if ids is None:return
            partes={t['uid'] for t in self.foto['tubos'] if set(t.get('zonas_uids',())).intersection(ids)}
            self.escopo_chaves={('PIPE',r['uid']) for r in self.previa['pipes'] if r['parte'] in partes}
        elif modo=='CONJUNTOS':
            if self.escolher_conjuntos() is None:return
            self.escopo_chaves={(r['tipo'],r['uid']) for u in self.conjuntos_ids for r in self.conjuntos[u]['membros']}
        elif modo=='ALCANCAVEL':
            ids=escolher(self,'Origens da rede alcançável',
                [(u,f"{self.pagina._nomes([u])} · {u[:10]}") for u in sorted(self.foto['origens_validas'])],
                self.origens_escopo)
            if ids is None:return
            self.origens_escopo=ids
            self.selecao_resumo.setText(f'{len(ids)} origens selecionadas.')
            return
        else:
            self.selecao_resumo.setText('O escopo usa a condição cadastral e as origens selecionadas na prévia.')
            return
        self.selecao_resumo.setText(f'{len(self.escopo_chaves)} elementos selecionados.')

    def _escopo(self):
        modo=self.escopo.currentData()
        if modo=='COMPLETO':return None
        if modo=='HIPOTESE':
            return {('PIPE',r['uid']) for r in self.previa['pipes'] if r['participacao']=='INCLUIDO'}
        if modo=='ALCANCAVEL':
            if not self.origens_escopo:
                raise ValueError('Selecione origens válidas para usar a rede alcançável.')
            if any(p.get(k) is None for p in self.previa['pipes'] for k in ('no_a','no_b')):
                raise ValueError('Há pontas ausentes na fotografia. Valide primeiro com o cadastro completo.')
            if set(self.origens_escopo)==set(self.previa['manifesto']['origens']):
                alcancaveis={('PIPE',r['uid']) for r in self.previa['pipes'] if r['condicao_topologica']=='COM_ORIGEM'}
            else:
                condicao=cadastro._condicao(self.foto,self.origens_escopo,None)
                alcancaveis={('PIPE',r['uid']) for r in self.previa['pipes'] if
                    r['participacao']=='INCLUIDO' and any(c[0]=='COM_ORIGEM' for c in condicao.get(r['parte'],()))}
            if not alcancaveis:raise ValueError('Nenhum Pipe alcançável pelas origens selecionadas.')
            return alcancaveis
        if not self.escopo_chaves:
            raise ValueError('Escolha os elementos que serão exportados neste escopo.')
        return self.escopo_chaves

    def _configuracao(self):
        if self.pagina.foto is not self.foto or self.pagina._projeto()['uuid']!=self.projeto['uuid']:
            raise ValueError('O contexto mudou. Reabra o assistente.')
        perfil=self._perfil()
        escopo=self._escopo()
        cfg=dict(perfil=perfil,escopo=self.escopo.currentData(),tolerancia_m=self.tolerancia.value(),
                 segmentar_aneis=self.aneis.isChecked())
        anterior=self.anterior.text()
        observado=self.observado.text()
        if perfil['modo']=='ATUALIZAR' and not anterior:
            raise ValueError('Localize o pacote de referência para comparar a atualização.')
        selecoes=[self.conjuntos[u] for u in self.conjuntos_ids]
        regra=self.atividade.currentData()
        dados=self.previa
        if cfg['escopo']=='ALCANCAVEL':
            dados=dict(dados,manifesto=dict(dados['manifesto'],origens=list(self.origens_escopo)))
        assinatura=digest([cfg,sorted(escopo or ()),dados['manifesto']['origens'],
                           [(r['uuid'],r['rev']) for r in selecoes],regra,anterior,observado])
        if regra!='PREVIA':
            excecoes=dados['manifesto'].get('atividades_explicitas',{})
            dados=dict(dados,pipes=[dict(r,atividade=excecoes.get(r['original'],
                'ATIVO' if regra=='HIPOTESE' and r['participacao']=='INCLUIDO' else 'A_DEFINIR')) for r in dados['pipes']])
        return cfg,escopo,selecoes,dados,assinatura,anterior,observado

    def _carregar_anterior(self,cfg,anterior,observado):
        if cfg['perfil']['modo']=='ATUALIZAR':
            m0,originais=mb.ler_pacote(anterior)
            if m0['projeto']!=self.projeto['uuid']:
                raise ValueError('O pacote anterior pertence a outro projeto.')
            cfg['componentes_anteriores']=originais
            cfg['referencia_anterior']=m0['assinatura_csv']
            if observado:cfg['observado']=conferir.ler_evidencia(observado)

    def validar(self):
        cfg,escopo,selecoes,dados,assinatura,anterior,observado=self._configuracao()
        cfg['base_labels']=self.pagina._complementos()
        self._validado=None
        def tarefa(parar,_):
            self._carregar_anterior(cfg,anterior,observado)
            return cadastro.validar_modelbuilder(dados,cfg,selecoes=selecoes,escopo=escopo,cancelar=parar)
        def pronto(rs):
            if sip.isdeleted(self):return
            self._pendencias,m=rs
            self._validado=(assinatura,m)
            self._listar_pendencias()
            self.parcial.setEnabled(bool(m['excluidos']))
            self.parcial.setChecked(False)
            cont=' · '.join(f'{GRAVIDADES[k]}: {n}' for k,n in m['gravidades'].items()) or 'Sem pendências'
            preparados=' · '.join(f'{n} {k.title()}'+('s' if n!=1 else '') for k,n in m['quantidades'].items()) or 'Nenhum elemento preparado'
            self.status.setText(preparados+'\n'+cont)
        self._executar('Validar topologia e atributos',tarefa,pronto)

    def _executar(self,titulo,funcao,pronto):
        if self.pagina.tarefa(titulo,funcao,pronto):
            self._operacao=self.pagina.app.atividades.atual

    def _listar_pendencias(self,*_):
        filtro=self.filtro_pendencias.currentData()
        self.tabela_pendencias.limpar()
        self._linhas_pendencia=[r for r in self._pendencias if not filtro or r.get(filtro[0])==filtro[1]]
        for r in self._linhas_pendencia:
            uid=r.get('uid') or '—'
            chave=r.get('gis_id')
            self.tabela_pendencias.inserir((GRAVIDADES[r['gravidade']],r['tipo'],chave if chave is not None else uid[:12],
                                          r.get('camada'),r['motivo']))

    def _localizar_pendencia(self,i,aproximar):
        if not i.isValid() or self.pagina.foto is not self.foto:return
        r=self._linhas_pendencia[i.row()]
        u=r.get('uid')
        g=None
        if r['tipo']=='PIPE' and (p:=next((p for p in self.previa['pipes'] if p['uid']==u),None)):
            g=linha(p)
        elif (n:=next((n for n in self.previa['nos'] if n['uid']==u),None)) and len(n.get('xy') or ())==2:
            g=QgsGeometry.fromPointXY(QgsPointXY(*n['xy']))
        elif (e:=next((e for e in self.previa['equipamentos'] if e['uid']==u),None)):
            g=geometria(e.get('wkb'))
        if not g:
            self.status.setText('Geometria indisponível para esta pendência. Consulte o registro e as relações.')
            return
        self.pagina.central.mapa.destacar_investigacao([('tubo' if r['tipo']=='PIPE' else 'local',g)],
            self.pagina.crs_foto,aproximar,toda_extensao=True)

    def _menu_pendencia(self,i):
        r=self._linhas_pendencia[i.row()]
        def consultar():
            dados=dict(r)
            QMessageBox.information(self,'Diagnóstico e relações',json.dumps(dados,ensure_ascii=False,indent=2,default=str))
        def revisar():
            c=self.pagina.central
            if not c.abrir_conectividade():return
            t=c.conectividade_gis
            por_id={d['uid']:d for d in self.foto.get('diagnosticos',())}
            rel=next((x['candidato'] for x in r.get('relacoes',()) if x.get('candidato') in por_id),None)
            if rel and (t.dados or {}).get('uuid')==self.foto['uuid']:
                t.selecionar_resultado_uid(rel,por_id[rel]['tipo'])
            else:
                t.status.setText('Abra a execução usada no pacote e confira as portas na tabela de conexões.')
        return [('Consultar diagnóstico e relações…',consultar),('Revisar na conectividade',revisar)]

    def exportar(self):
        cfg,escopo,selecoes,dados,assinatura,anterior,observado=self._configuracao()
        if not self._validado or self._validado[0]!=assinatura:
            raise ValueError('Valide a configuração atual antes de exportar.')
        m=self._validado[1]
        if m['excluidos'] and not self.parcial.isChecked():
            raise ValueError('Há elementos críticos. Revise as pendências ou marque a exportação parcial.')
        cfg['parcial']=self.parcial.isChecked()
        formato=self.formato.currentData()
        if not self.destino_pacote.text():
            self.escolher_pasta()
        pasta=self.destino_pacote.text()
        if not pasta:return
        base=self.pagina._complementos(True)
        projeto_uid=self.projeto['uuid']
        raiz=Path(self.projeto['manifesto_wna']).parent.resolve() if self.projeto.get('manifesto_wna') else None
        def executar(parar,etapa):
            self._carregar_anterior(cfg,anterior,observado)
            dst=cadastro.exportar(dados,Path(pasta),formato,parar,etapa,selecoes=selecoes,modelbuilder=cfg,escopo=escopo,base_labels=base)
            m=json.loads((dst/'MODELBUILDER.json').read_text(encoding='utf-8'))
            relativo=bool(raiz and dst.resolve().is_relative_to(raiz))
            p=str(dst.resolve().relative_to(raiz)) if relativo else str(dst.resolve())
            r=pg.salvar_revisao(base,projeto_uid,'MODELBUILDER_EXPORTACAO',
               dict(projeto_uid=projeto_uid,topologia_uid=m['execucao'],pasta=p,relativo=relativo,
                    assinatura=m['assinatura_csv'],metadata=m,estado=m['estado']))
            return dst,r
        def pronto(rs):
            dst,r=rs
            texto=f"Pacote {r['uuid'][:8]} · {r['estado'].lower().replace('_',' ')}\n{dst}"
            self.pagina.status.setText(texto)
            if not sip.isdeleted(self):self.status.setText(texto)
        self._executar('Exportar para ModelBuilder',executar,pronto)


class HistoricoModelBuilder(QDialog):
    def __init__(self,pagina,parent=None):
        super().__init__(parent or pagina)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle('Exportações e conferência WaterGEMS')
        self.pagina=pagina
        self.projeto=pagina._projeto()
        self.registros=_revisoes(pagina,'MODELBUILDER_EXPORTACAO')
        v=QVBoxLayout(self)
        self.lista=_combo((f"{r['data_utc'][:16]} · {r['estado']} · {u[:8]}",u) for u,r in reversed(list(self.registros.items())))
        v.addWidget(self.lista)
        self.texto=aviso()
        self.texto.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self.texto)
        self.lista.currentIndexChanged.connect(self.descrever)
        botao(v,'Conferir CSV exportado do WaterGEMS…',self.ler)
        botao(v,'Fechar',self.reject)
        self.descrever()

    def descrever(self,*_):
        r=self.registros.get(self.lista.currentData())
        if not r:
            self.texto.setText('Nenhum pacote registrado no projeto.')
            return
        self.texto.setText(str(_pasta(self.projeto,r))+'\n'+r['estado'].replace('_',' ').capitalize()+
            ('\nConferência: '+r['relatorio'] if r.get('relatorio') else ''))

    def ler(self):
        r=self.registros.get(self.lista.currentData())
        if not r:return
        p=_pasta(self.projeto,r)
        if not p.is_dir():
            novo=QFileDialog.getExistingDirectory(self,'Localizar a pasta do pacote exportado')
            if not novo:return
            p=Path(novo)
        arq,_=QFileDialog.getOpenFileName(self,'CSV exportado das tabelas WaterGEMS',str(p),'CSV (*.csv)')
        if not arq:return
        modelo,ok=QInputDialog.getText(self,'Conferir importação','Identidade do modelo de destino')
        if not ok:return
        versao,ok=QInputDialog.getText(self,'Conferir importação','Versão exata do WaterGEMS')
        if not ok:return
        cenario,ok=QInputDialog.getText(self,'Conferir importação','Cenário e alternativa de atividade, se conferidos')
        if not ok:return
        base=self.pagina._complementos()
        projeto_uid=self.projeto['uuid']
        def executar(parar,etapa):
            etapa(0,'Conferindo chaves, nós, coordenadas e propriedades')
            meta,esperado=mb.ler_pacote(p)
            if meta['projeto']!=projeto_uid or meta['assinatura_csv']!=r['assinatura']:
                raise ValueError('O pacote não corresponde ao registro do projeto.')
            evidencias=conferir.ler_evidencia(arq)
            d=conferir.conferir(meta,esperado,evidencias,modelo,versao,cenario=cenario,cancelar=parar)
            destino=p/('Conferencia_'+uuid4().hex[:10])
            with TemporaryDirectory(prefix='.conferencia_',dir=p) as temporario:
                temp=Path(temporario)/'saida'
                temp.mkdir()
                data=datetime.now(timezone.utc).isoformat()
                d['sha256_evidencia']=conferir.salvar_tabela(temp/'correspondencias.gpkg',d,arq,data)
                d['data_utc']=data
                (temp/'reconciliacao.json').write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
                publicar(temp,destino,parar)
            novo=pg.salvar_revisao(base,projeto_uid,'MODELBUILDER_EXPORTACAO',dict(r,estado=d['estado'],
                relatorio=destino.name+'/reconciliacao.json'),r['uuid'],r['rev'])
            return novo,destino
        def pronto(rs):
            novo,destino=rs
            self.pagina.status.setText(str(destino))
            if sip.isdeleted(self):return
            self.registros[novo['uuid']]=novo
            self.lista.setItemText(self.lista.findData(novo['uuid']),novo['estado'])
            self.descrever()
            self.texto.setText(self.texto.text()+'\n'+str(destino))
        self.pagina.tarefa('Conferir modelo WaterGEMS',executar,pronto)
