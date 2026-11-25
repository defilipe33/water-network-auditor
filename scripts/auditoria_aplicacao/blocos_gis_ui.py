"""Consulta cartográfica, filtros e exportação de blocos topológicos."""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QComboBox, QFileDialog, QInputDialog, QListWidget, QListWidgetItem
from qgis.core import QgsGeometry

from .modelo_gis_ui import aviso, botao, expansivel, formulario
from .navegacao_cartografica import acao_disponivel


class BlocosGISUI:
    def montar_blocos(self,layout):
        self.blocos_b, v = expansivel(layout,'Mapa de blocos de abastecimento · conectividade GIS')
        f=formulario(v)
        self.detalhe_blocos=QComboBox()
        for rotulo,k in [('Visão macro','MACRO'),('Blocos biconexos detalhados','DETALHADO')]:
            self.detalhe_blocos.addItem(rotulo,k)
        f.addRow('Detalhamento do cálculo',self.detalhe_blocos)
        self.calcular_blocos_b=botao(v,'Calcular e salvar blocos desta execução',
                                    lambda:self.calcular(agrupado=True,blocos=True))
        self.fonte_blocos=QComboBox()
        self.corredor_blocos=QComboBox()
        self.fonte_indisponivel=QComboBox()
        for rotulo,c in [('Filtrar por origem',self.fonte_blocos),('Filtrar por corredor',self.corredor_blocos),
                         ('Testar origem indisponível',self.fonte_indisponivel)]:
            f.addRow(rotulo,c)
            c.currentIndexChanged.connect(self.atualizar_filtros_blocos)
        self.areas_blocos=QListWidget()
        self.areas_blocos.setMaximumHeight(115)
        self.areas_blocos.itemChanged.connect(self.atualizar_filtros_blocos)
        v.addWidget(aviso('Marque áreas para filtrar por interseção. A análise considera o grafo completo.'))
        v.addWidget(self.areas_blocos)
        self.info_blocos=aviso()
        v.addWidget(self.info_blocos)
        self.mostrar_blocos_b=botao(v,'Mostrar blocos filtrados no mapa',self.mostrar_blocos_mapa)
        self.exportar_blocos_b=botao(v,'Exportar blocos filtrados…',lambda:self.exportar_blocos())

    def atualizar_filtros_blocos(self,*_):
        d = (self.dados or {}).get('blocos',{})
        total=d.get('blocos',[])
        fonte=self.fonte_indisponivel.currentData()
        xs=self.blocos_filtrados()
        perdas=sum(b['origens']==[fonte] for b in xs) if fonte else 0
        self.info_blocos.setText(f'{len(xs)} de {len(total)} blocos.'
            +(f' {perdas} perderiam acesso às origens selecionadas.' if fonte else '')
            +(' Distâncias por origem excederam o orçamento de cálculo.' if d and not d['distancias_por_fonte'] else ''))
        if hasattr(self,'tabela') and self.categoria.currentData()=='BLOCOS':
            self.atualizar_tabela()

    def carregar_blocos(self,d):
        macro=(d or {}).get('agrupamento',{})
        for combo,rotulo,linhas in (
            (self.fonte_blocos,'Todas',[(self._nomes([u]),u) for u in (d or {}).get('fontes',())]),
            (self.corredor_blocos,'Todos',[(c['nome'],c['uid']) for c in macro.get('corredores',())]),
            (self.fonte_indisponivel,'Nenhuma',[(self._nomes([u]),u) for u in (d or {}).get('fontes',())]),
        ):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(rotulo,None)
            for n,u in linhas:combo.addItem(n,u)
            combo.blockSignals(False)
        self.areas_blocos.blockSignals(True)
        self.areas_blocos.clear()
        for area in (d or {}).get('foto',{}).get('areas',()):
            i=QListWidgetItem(str(area.get('label') or area.get('id') or area['uid'][:8]))
            i.setData(Qt.UserRole,area['uid'])
            i.setCheckState(Qt.Unchecked)
            self.areas_blocos.addItem(i)
        self.areas_blocos.blockSignals(False)
        self.atualizar_filtros_blocos()

    def blocos_filtrados(self):
        fonte,corredor=self.fonte_blocos.currentData(),self.corredor_blocos.currentData()
        areas={i.data(Qt.UserRole) for j in range(self.areas_blocos.count())
               if (i:=self.areas_blocos.item(j)).checkState()==Qt.Checked}
        return [b for b in (self.dados or {}).get('blocos',{}).get('blocos',())
                if (not fonte or fonte in b['origens']) and (not corredor or corredor in b['corredores'])
                and (not areas or areas.intersection(b['areas']))]

    def tabela_blocos(self):
        indisponivel=self.fonte_indisponivel.currentData()
        cabecalho=('Bloco','Estrutura','Pipes','Extensão (m)','Origens alcançáveis','Corredores',
                   'Ligações','Pipes críticos','Redundância','Áreas','Origens remanescentes')
        def valores(r):
            return (r['nome'],r['tipo'].capitalize(),len(r['pipes']),r['comprimento_m'],
                    self._nomes(r['origens']),len(r['corredores']),len(r['fronteiras']),len(r['criticas']),
                    r['redundancia'].replace('_',' ').capitalize(),
                    ', '.join(self._nome_area(u) for u in r['areas']),
                    self._nomes(u for u in r['origens'] if u!=indisponivel))
        return 'BLOCOS',cabecalho,self.blocos_filtrados(),valores

    def detalhes_bloco(self,r):
        dist=', '.join(f'{self._nomes([u])} {m:.1f} m' for u,m in r['distancias_m'].items()) or '—'
        fonte=r.get('referencia') or {}
        rotas=f"Referência · {self._nomes([fonte['origem']])} · {fonte['distancia_m']:.1f} m." if fonte else 'Sem fonte de referência.'
        return (f"{rotas} Distâncias por fonte · {dist}. {len(r['propostas'])} proposta(s) neste bloco. "
                f"{len(r.get('alternativas',()))} alternativa(s) de corredor passam por aqui. "
                'Acesso topológico sob a hipótese salva.')

    def mostrar_blocos_mapa(self,_checked=False,*,ao_mostrar=None):
        from .representacao_blocos_gis import registros, publicar
        selecionados=self.blocos_filtrados()
        if not selecionados:
            self.status.setText('Selecione um trabalho com blocos e confira os filtros.')
            return
        d,geo=self.dados,self.geo
        def pronto(linhas):
            publicar(d,geo.crs,linhas)
            self.central.agendar_estado_visual()
            if ao_mostrar:ao_mostrar()
        self.tarefa('Preparando a camada de blocos',lambda p,_:registros(geo,selecionados,p),pronto)

    def exportar_blocos(self,r=None):
        if not self.dados or self.central.ocupado():return
        if r:
            blocos=[b for b in self.dados.get('blocos',{}).get('blocos',()) if b['uid']==r['uid']]
        else:blocos=self.blocos_filtrados()
        if not blocos:return
        opcoes=['GeoPackage','Shapefile','CSV']
        formato,ok=QInputDialog.getItem(self,'Exportar blocos','Formato',opcoes,editable=False)
        if not ok:return
        pasta=QFileDialog.getExistingDirectory(self,'Pasta de exportação')
        if not pasta:return
        from .representacao_blocos_gis import exportar
        d,geo=self.dados,self.geo
        self.tarefa('Exportando blocos',lambda p,_:exportar(d,geo,blocos,pasta,formato,p),
                    lambda alvo:self.status.setText('Blocos exportados em '+str(alvo)))

    def itens_bloco(self,r,rota=False):
        geos=[g for i in ((r.get('referencia') or {}).get('segmentos',()) if rota else r['segmentos'])
              if (g:=self.geo.trecho(i))]
        return [('vinculo' if rota else 'tubo',QgsGeometry.collectGeometry(geos))] if geos else []
