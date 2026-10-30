"""Identidade de projeto e contexto de navegação; sem dados hidráulicos."""
import json,os,time
from pathlib import Path
from uuid import uuid4
from auditoria_fronteiras.versoes import abrir_ro
from auditoria_topologica_watergems import bases
from auditoria_topologica_watergems.referencia_espacial import estado_referencia

class Projetos:
    def __init__(self,raiz):self.path=Path(raiz)/'projetos_wna.json';self.dados=self.ler()
    def ler(self):
        if not self.path.exists():return dict(versao=1,ativo=None,projetos=[])
        d=json.loads(self.path.read_text(encoding='utf8'))
        if d.get('versao')!=1 or not isinstance(d.get('projetos'),list):raise ValueError('Índice de projetos incompatível; arquivo preservado')
        return d
    def salvar(self):
        tmp=self.path.with_name(self.path.name+'.'+uuid4().hex+'.tmp');tmp.write_text(json.dumps(self.dados,ensure_ascii=False,indent=2),encoding='utf8')
        # No Windows, indexadores podem reter o destino durante uma leitura.
        # Não se apaga o índice antigo; erro persistente é comunicado ao chamador.
        for tentativa in range(4):
            try:os.replace(tmp,self.path);break
            except PermissionError:
                if tentativa==3:raise
                time.sleep(.03)
    def criar(self,nome):
        if not nome.strip():raise ValueError('Informe o nome do projeto')
        self.dados=self.ler();p=dict(uuid=uuid4().hex,nome=nome.strip(),bases=[],ultima=None,contexto={});self.dados['projetos'].append(p);self.dados['ativo']=p['uuid'];self.salvar();return p
    def ativar(self,uid):
        self.dados=self.ler()
        if not any(p['uuid']==uid for p in self.dados['projetos']):raise ValueError('Projeto não identificado')
        self.dados['ativo']=uid;self.salvar()
    def atual(self):return next((p for p in self.dados['projetos'] if p['uuid']==self.dados['ativo']),None)
    def contem(self,tipo,uid):
        p=self.atual()
        return not p or any(r['tipo']==tipo and r['uuid']==uid for r in p['bases']) or p.get('em_memoria',{}).get(tipo)==uid
    def vincular(self,registro):
        p=self.atual()
        if not p:return
        identidade=dict(uuid=registro['uuid'],tipo=registro['tipo'],base=registro['base']);p.setdefault('em_memoria',{})[registro['tipo']]=registro['uuid'];p['bases']=[r for r in p['bases'] if (r['uuid'],r['tipo'])!=(identidade['uuid'],identidade['tipo'])]+[identidade];p['ultima']=identidade;self.salvar()


_CACHE={}

def validar_registro(r):
    p=Path(r['base'])
    if not p.is_file():return dict(valido=False,erro='Arquivo ausente ou movido; localize novamente por UUID.')
    chave=(str(p.resolve()),r['uuid'],r['tipo'],p.stat().st_size,p.stat().st_mtime_ns)
    wal=p.with_name(p.name+'-wal')
    chave+=(wal.stat().st_size,wal.stat().st_mtime_ns) if wal.exists() else (None,None)
    if chave in _CACHE:return dict(_CACHE[chave])
    try:
        with abrir_ro(p) as c:
            if c.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Integridade SQLite não confirmada')
            if r['tipo']=='TOPOLOGIA_WG':
                m=bases.metadados(p)
                if m['uuid']!=r['uuid']:raise ValueError('UUID diverge do catálogo')
                if c.execute('SELECT count(*) FROM WB_RESULTADOS').fetchone()[0]!=2:raise ValueError('Perspectivas persistidas incompletas')
                resultado=dict(valido=True,meta=m,base=str(p),uuid=m['uuid']);_CACHE[chave]=resultado;return resultado
            tabela,campo=('IG_EXECUCOES','ig_uid') if r['tipo']=='INTEGRADA' else ('EXECUCOES','exe_uid')
            if not c.execute(f'SELECT 1 FROM {tabela} WHERE {campo}=?',(r['uuid'],)).fetchone():raise ValueError('Execução não encontrada na base')
            resultado=dict(valido=True,base=str(p),uuid=r['uuid']);_CACHE[chave]=resultado;return resultado
    except Exception as e:return dict(valido=False,erro=str(e))


def fatos(app):
    from qgis.PyQt import sip
    f={};g=app.geo;central=getattr(app,'central',None);projetos=central.projetos if central else None
    def pertence(tipo,uid):return projetos is None or projetos.contem(tipo,uid)
    if g.dossie and pertence('AUDITORIA_GIS',g.dossie['execucao_uid']):
        f['gis']=dict(valido=not g._executando and not g.pendente(),uuid=g.dossie['execucao_uid'],base=g.base_revisao,persistido=bool(g.base_revisao))
    painel=app.painel
    if painel and not sip.isdeleted(painel) and painel._ativo and pertence('INTEGRADA',painel.pacote['resultado']['meta']['uid']):
        m=painel.pacote['resultado']['meta'];f['wg']=dict(valido=True,uuid=m['topologia']['execucao_uid'],incorporada=True,base=str(painel.base));f['espacial']=painel.pacote['resultado']['meta']['parametros'].get('espacial_habilitado',False);f['correspondencia']=True;f['compativel']=True;f['integrada']=dict(valido=True,uuid=m['uid'],base=str(painel.base));f['contexto']=contexto_modelo(painel.pacote['topologia']['modelo'],m['topologia']['execucao_uid'],painel.modo.currentData(),m.get('nome','Investigação'))
    w=app.wg
    if f.get('integrada',{}).get('valido'):
        mb=painel.pacote['topologia'].get('meta_base',{});ctx=f['contexto'];ctx['modelo']=mb.get('nome','WaterGEMS incorporado');ctx['versao']=str(mb['versao'])+' · '+mb['uuid'][:8] if mb.get('versao') is not None else 'UUID '+ctx['versao'][:8]
    if w and not sip.isdeleted(w) and w.base:
        try:
            m=bases.metadados(w.base)
            if not pertence('TOPOLOGIA_WG',m['uuid']):return f
            if f.get('integrada',{}).get('valido') and f['wg']['uuid']!=m['uuid']:return f
            r=validar_registro(dict(base=w.base,uuid=m['uuid'],tipo='TOPOLOGIA_WG'));f['wg']=r
            if r['valido']:
                f['espacial']=estado_referencia(m.get('referencia_espacial'))['estado']=='VALIDADO'
                projeto=(g.dossie or {}).get('controle_versao',{}).get('projeto');f['compativel']=(not projeto or not m.get('projeto') or projeto.strip().casefold()==m['projeto'].strip().casefold()) if f.get('gis',{}).get('valido') else None
                f['correspondencia']=bool(w._prova and all(c.currentData() is not None for c in w.mapas.values()))
                if not f.get('contexto'):
                    with abrir_ro(w.base) as c:header=bases.decodificar(json.loads(c.execute('SELECT modelo FROM WB_BASE').fetchone()[0]))
                    f['contexto']=contexto_modelo(header,m['uuid'],w.modo.currentText());f['contexto']['modelo']=m['nome'];f['contexto']['versao']=str(m['versao'])+' · '+m['uuid'][:8]
        except Exception as e:f['wg']=dict(valido=False,erro=str(e))
    return f


def contexto_modelo(modelo,versao,modo,investigacao='Nenhuma'):
    id=modelo['cenario'];cs={c['id']:c for c in modelo.get('cenarios',[])};c=cs.get(id,{})
    return dict(modelo=modelo['projeto'],cenario=id,nome_cenario=c.get('nome',str(id)),pai=c.get('pai'),alternativa=modelo.get('alternativas',{}).get('3') or 'Não preservada neste resultado',versao=versao,perspectiva=modo,investigacao=investigacao,escopo='GLOBAL — CENÁRIO BASE' if c.get('pai') is None and c else 'SETORIAL / CONTEXTO SELECIONADO' if c else 'Classificação de cenário não determinada')


def associar_cenario(projetos,modelo,cenario,versao,alvo):
    if not projetos.atual():raise ValueError('Crie ou selecione um projeto para preservar a associação')
    if alvo.get('origem') not in ('SELECTION_SET','AREA') or not alvo.get('id'):raise ValueError('Selecione uma região ou Selection Set com identidade técnica')
    p=projetos.atual();historico=p.setdefault('associacoes_cenarios',[]);anterior=next((r['uuid'] for r in reversed(historico) if r['modelo']==modelo and r['cenario']==cenario and r['alvo']==alvo),None);r=dict(uuid=uuid4().hex,anterior=anterior,modelo=modelo,cenario=cenario,versao=versao,alvo=alvo)
    from datetime import datetime,timezone
    r['data_utc']=datetime.now(timezone.utc).isoformat();historico.append(r);projetos.salvar();return r
