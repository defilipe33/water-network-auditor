"""Índice de leitura dos vínculos existentes. Geometrias só são decodificadas sob demanda."""
from collections import defaultdict
from qgis.core import QgsGeometry

SITUACOES = {'PENDENTE':'Pendente','EM_ANALISE':'Em análise','VERIFICADO':'Verificado',
             'DESCARTADO':'Descartado','NECESSITA_CONFIRMACAO':'Necessita confirmação','MISTO':'Situações mistas'}
DESCRICOES = {
 'CRUZAMENTO':'A tubulação atravessa uma fronteira poligonal. Isso não comprova interligação hidráulica.',
 'TRAVESSIA':'A tubulação atravessa uma fronteira poligonal. Isso não comprova interligação hidráulica.',
 'TRANSICAO':'Foi identificada uma transição geométrica entre regiões cadastradas.',
 'TANGENCIA':'A tubulação toca a fronteira; o contato não comprova passagem entre regiões.',
 'COINCIDENCIA':'Um trecho da tubulação coincide geometricamente com a fronteira.',
 'EXTREMIDADE':'Uma extremidade da tubulação está junto à fronteira analisada.',
 'CONTINUIDADE_POTENCIAL':'Extremidades próximas constituem uma continuidade candidata; não uma conexão confirmada.',
 'AMBIGUA':'Os dados geométricos não permitem uma classificação inequívoca.'}


def geometria(hexadecimal):
    try:
        g=QgsGeometry(); g.fromWkb(bytes.fromhex(hexadecimal or ''))
        return g if not g.isNull() and not g.isEmpty() else None
    except (ValueError,RuntimeError,TypeError): return None


def descricao(evento):
    t=evento['tecnico']; k=t['classificacao']
    return DESCRICOES.get(k,'Indício geométrico classificado como '+k+'. Consulte os detalhes técnicos; não há conclusão hidráulica automática.')


class IndiceInvestigacao:
    def __init__(self,dossie,revisoes=None):
        self.d=dossie; self.revisoes=revisoes or {}
        self.locais={l['uid']:l for l in dossie['locais']}
        self.eventos={e['uid']:e for e in dossie['eventos']}
        self.tubos={t['uid']:t for t in dossie['tubulacoes']}
        self.poligonos={p['chave']:p for p in dossie['poligonos']}
        self.ordens=[{u:n for n,u in enumerate(m)} for m in (self.eventos,self.tubos,self.poligonos)]
        self.ev_tubos=defaultdict(set); self.ev_polis=defaultdict(set); self.ev_locais=defaultdict(set)
        for r in dossie['evento_rede']: self.ev_tubos[r['evento_uid']].add(r['tubo_uid'])
        for r in dossie['evento_poligono']: self.ev_polis[r['evento_uid']].add(r['pol_uid'])
        self.textos={}; self.classes={}; self.tipos={}
        for uid,l in self.locais.items():
            eventos=[self.eventos[u] for u in l['eventos'] if u in self.eventos]
            self.classes[uid]={e['tecnico']['classificacao'] for e in eventos}
            self.tipos[uid]={e['tecnico'].get('modo') for e in eventos}
            tubos=set().union(*(self.ev_tubos[e['uid']] for e in eventos)) if eventos else set()
            self.textos[uid]=' '.join([str(l['registro']['LOCAL']),*(str(self.tubos[t].get('id_exibido',''))+' '+self.tubos[t]['camada'] for t in tubos)]).casefold()
            for e in eventos:self.ev_locais[e['uid']].add(uid)

    def detalhes(self,uid,evento=None):
        l=self.locais[uid]; ids=[evento] if evento is not None else l['eventos']
        if evento is not None and evento not in l['eventos']:raise ValueError('Ocorrência fora do local selecionado.')
        es=[self.eventos[u] for u in sorted(ids,key=lambda u:self.ordens[0].get(u,-1)) if u in self.eventos]
        tubos=set().union(*(self.ev_tubos[e['uid']] for e in es)) if es else set()
        polis=set().union(*(self.ev_polis[e['uid']] for e in es)) if es else set()
        return dict(local=l,eventos=es,tubulacoes=[self.tubos[u] for u in sorted(tubos,key=self.ordens[1].get)],poligonos=[self.poligonos[u] for u in sorted(polis,key=self.ordens[2].get)])

    def situacao(self,uid):
        l=self.locais[uid]
        if not any(u in self.revisoes for u in l['eventos']):return l['revisao']['situacao']
        estados={self.revisoes.get(u,{}).get('situacao','PENDENTE') for u in l['eventos']}
        return next(iter(estados)) if len(estados)==1 else 'MISTO'

    def filtrar(self,busca='',situacao='',classe='',tipo=''):
        busca=busca.casefold().strip()
        return [l for uid,l in self.locais.items() if (not busca or busca in self.textos[uid])
                and (not situacao or self.situacao(uid)==situacao)
                and (not classe or classe in self.classes[uid])
                and (not tipo or tipo in self.tipos[uid])]
