"""Leitor WaterGEMS somente leitura. Alternativas são resolvidas por elemento.

Nomes de tabelas deste adaptador correspondem ao esquema HMI observado nos dois
modelos. Ausência de dado NÃO equivale a ativo, aberto ou conexão inexistente.
"""
import hashlib
from pathlib import Path
import sqlite3


def identificador(nome):
    return '"' + nome.replace('"', '""') + '"'


class Banco:
    def __init__(self, caminho):
        self.caminho = Path(caminho).resolve()
        self.con = sqlite3.connect(self.caminho.as_uri() + '?mode=ro', uri=True)
        self.con.row_factory = sqlite3.Row
        self.con.execute('PRAGMA query_only=ON')
        self.tabelas = {r[0] for r in self.con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        obrigatorias = {'HMIScenario', 'HMIAlternative', 'HMIScenarioAlternative',
                        'HMIDomainElement', 'HMIModelingElement', 'HMIDomainDataSet'}
        if not obrigatorias <= self.tabelas:
            self.close()
            raise ValueError('Esquema HMI incompleto: ' + str(sorted(obrigatorias-self.tabelas)))
        self.cenarios = {r['ScenarioID']: r for r in self.linhas('HMIScenario')}
        self.alternativas = {r['AlternativeID']: r for r in self.linhas('HMIAlternative')}
        self.atribuicoes = self.linhas('HMIScenarioAlternative')
        self.rotulos = {r['ElementID']: r for r in self.linhas('HMIModelingElement')}
        self.dominio = {r['DomainElementID']: r for r in self.linhas('HMIDomainElement')}
        # GUID do projeto, e não o caminho da cópia, compõe a identidade.
        projetos = self.linhas('HMIDomainDataSet')
        if len(projetos)!=1:
            self.close()
            raise ValueError('Banco com múltiplos projetos: selecione um snapshot de projeto único')
        self.projeto = hashlib.sha256(repr([(r.get('DomainDataSetID'), r.get('Guid'))
                                         for r in projetos]).encode()).hexdigest()[:24]
        self.ativo = projetos[0].get('ActiveScenarioID') if len(projetos) == 1 else None
        self.avisos = []

    def close(self):
        self.con.close()

    def linhas(self, tabela):
        if tabela not in self.tabelas:
            return []
        return [dict(r) for r in self.con.execute('SELECT * FROM ' + identificador(tabela))]

    def cadeia_cenarios(self, cenario):
        vistos = set()
        while cenario is not None:
            if cenario in vistos or cenario not in self.cenarios:
                raise ValueError('Herança de cenários cíclica ou referência ausente')
            vistos.add(cenario)
            r = self.cenarios[cenario]
            if r['IsDeleted']:
                raise ValueError('Cenário excluído na cadeia de herança')
            yield cenario
            cenario = r['ParentID']

    def cadeia_alternativas(self, cenario, tipo):
        usadas=set()
        for c in self.cadeia_cenarios(cenario):
            candidatas = [a for a in self.atribuicoes
                          if a['ScenarioID'] == c and a['AlternativeTypeID'] == tipo]
            if len(candidatas) > 1:
                raise ValueError('Mais de uma alternativa do mesmo tipo no cenário')
            escolhida=candidatas[0]['AlternativeID'] if candidatas else None
            vistos=set()
            while escolhida is not None:
                if escolhida in vistos or escolhida not in self.alternativas:
                    raise ValueError('Herança de alternativas cíclica ou referência ausente')
                if escolhida in usadas:break
                vistos.add(escolhida);usadas.add(escolhida)
                r=self.alternativas[escolhida]
                if r['IsDeleted'] or r['AlternativeTypeID']!=tipo:
                    raise ValueError('Alternativa excluída ou de tipo incompatível')
                yield escolhida
                escolhida=r['ParentID']

    def resolver(self, tabela, cenario, tipo, ids=None):
        """Primeira LINHA aplicável por elemento; nulos explícitos não são herdados."""
        if tabela not in self.tabelas:
            self.avisos.append('Tabela ausente: ' + tabela)
            return {}
        resultado = {}
        selecionados=None if ids is None else sorted(set(ids))
        if selecionados==[]:return resultado
        cadeia=list(self.cadeia_cenarios(cenario))
        atribuicoes=[(c,a['AlternativeID']) for c in cadeia for a in self.atribuicoes
                      if a['ScenarioID']==c and a['AlternativeTypeID']==tipo]
        for alt in self.cadeia_alternativas(cenario, tipo):
            origem=dict(tabela=tabela,alternativa=alt,cenario_solicitado=cenario,
                cenario_atribuicao=atribuicoes[0][0] if atribuicoes else None,
                cenario_fonte=next((c for c,a in atribuicoes if a==alt),None))
            lotes=[None] if selecionados is None else [selecionados[i:i+900] for i in range(0,len(selecionados),900)]
            for lote in lotes:
                consulta='SELECT * FROM '+identificador(tabela)+' WHERE AlternativeID=?'
                parametros=(alt,)
                if lote is not None:
                    consulta+=' AND DomainElementID IN ('+','.join('?' for _ in lote)+')'
                    parametros+=(tuple(lote))
                for linha in self.con.execute(consulta,parametros):
                    r=dict(linha);r['_origem_resolucao']=origem
                    resultado.setdefault(r['DomainElementID'],r)
        return resultado

    def listar_cenarios(self):
        return [dict(id=k, nome=self.rotulos.get(k, {}).get('Label') or str(k),
                     pai=v['ParentID'], ativo=k == self.ativo)
                for k, v in self.cenarios.items() if not v['IsDeleted']]

    def ler(self, cenario):
        list(self.cadeia_cenarios(cenario))
        familias = [('BaseLink', 'LINK'), ('BaseIdahoNode', 'NO'),
                    ('BaseDirectedNode', 'DISPOSITIVO'), ('CustomerNode', 'CONSUMIDOR')]
        tipos = ['IdahoPipe', 'IdahoJunction', 'IdahoReservoir', 'AirValve', 'IdahoHydrant',
                 'ConventionalTank', 'IdahoTank', 'TCV', 'FCV', 'PRV', 'PBV', 'PSV', 'GPV',
                 'CheckValve', 'StandardPump', 'VariableSpeedPumpBattery', 'CustomerNode']
        tipos_por_id = {}
        for t in tipos:
            for r in self.linhas(t):
                tipos_por_id.setdefault(r['DomainElementID'], t)
        elementos = {}
        for base, familia in familias:
            ids = self.linhas(base)
            geometria = self.resolver(base+'_HmiDataSetGeometry_Data', cenario, 1)
            ativo = self.resolver(base+'_HMIActiveTopology_Data', cenario, 3)
            topologia = self.resolver(base+'_HMIDataSetTopology_Data', cenario, 2) if familia in ('LINK','DISPOSITIVO') else {}
            for r in ids:
                i = r['DomainElementID']
                d, m = self.dominio.get(i), self.rotulos.get(i)
                excluido = None if d is None or m is None else bool(d['IsDeleted'] or m['IsDeleted'])
                if d and d.get('IsPrototype'):
                    continue
                a = ativo.get(i, {}).get('HMIActiveTopologyIsActive')
                elementos[i] = dict(id=i, uid=f'{self.projeto}:{i}', tipo=tipos_por_id.get(i, base),
                    familia=familia, label=(m or {}).get('Label'), excluido=excluido,
                    ativo=None if a not in (0,1) else bool(a),
                    cadastro_modeling=dict(m or {}),cadastro_dominio=dict(d or {}),
                    geometria=geometria.get(i,{}).get('HMIGeometry'),
                    topologia=topologia.get(i,{}), atributos={}, estados={},
                    alternativas=dict(geometria=geometria.get(i,{}).get('AlternativeID'),
                        ativa=ativo.get(i,{}).get('AlternativeID'),
                        topologia=topologia.get(i,{}).get('AlternativeID')))
                elementos[i]['proveniencia']={nome:dados.get(i,{}).get('_origem_resolucao')
                    for nome,dados in [('geometria',geometria),('ativa',ativo),('topologia',topologia)]}
        for tabela in sorted(self.tabelas):
            # Somente as famílias de atributos pertinentes; nunca resultados de simulação.
            if tabela.endswith('_InitialSettings_Data'):
                tipo, destino = 21, 'estados'
            elif tabela.endswith('_Physical_Data') or 'UserDefinedExtensions' in tabela and tabela.endswith('_Data'):
                tipo, destino = (100 if 'UserDefinedExtensions' in tabela else 4), 'atributos'
            else:
                continue
            cols = {r[1] for r in self.con.execute('PRAGMA table_info('+identificador(tabela)+')')}
            if not {'DomainElementID','AlternativeID'} <= cols:
                continue
            for i, r in self.resolver(tabela, cenario, tipo).items():
                if i in elementos:
                    elementos[i][destino][tabela] = r
        return dict(projeto=self.projeto, banco=str(self.caminho), cenario=cenario,
                    cenarios=self.listar_cenarios(), alternativas={str(t):list(self.cadeia_alternativas(cenario,t))
                        for t in (1,2,3,4,21,100)}, elementos=elementos,
                    avisos=sorted(set(self.avisos)), esquema=sorted(self.tabelas))
