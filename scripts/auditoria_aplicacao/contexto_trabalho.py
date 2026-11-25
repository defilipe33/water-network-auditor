"""Identidade de projeto e contexto de navegação; sem dados hidráulicos."""
import json,os,time
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from auditoria_fronteiras.versoes import abrir_ro
from auditoria_topologica_watergems import bases
from auditoria_topologica_watergems.referencia_espacial import estado_referencia

class Projetos:
    def __init__(self,raiz):
        self.path=Path(raiz)/'projetos_wna.json'
        self.dados=self.ler()
        self._original=deepcopy(self.dados)

    @staticmethod
    @contextmanager
    def trava(caminho):
        from qgis.PyQt.QtCore import QLockFile
        lock=QLockFile(str(caminho)+'.lock')
        if not lock.tryLock(1000):
            raise ValueError('O projeto está sendo salvo em outra sessão. Tente novamente.')
        try:
            yield
        finally:
            lock.unlock()

    def ler(self):
        if not self.path.exists():return dict(versao=1,ativo=None,projetos=[])
        d=json.loads(self.path.read_text(encoding='utf8'))
        if d.get('versao')!=1 or not isinstance(d.get('projetos'),list):raise ValueError('Índice de projetos incompatível; arquivo preservado')
        from .manifesto_projeto import ler
        for i,p in enumerate(d['projetos']):
            caminho=p.get('manifesto_wna')
            if caminho and Path(caminho).is_file():
                try:
                    lido=ler(caminho)
                    if lido['uuid']==p['uuid']:
                        d['projetos'][i]=lido
                except (ValueError,OSError):
                    # O índice local conserva a referência para recuperar o arquivo.
                    continue
        return d
    def salvar(self):
        self.gravar(self.dados)
    def gravar(self,dados):
        from .manifesto_projeto import gravar, ler
        from contextlib import ExitStack
        with self.trava(self.path), ExitStack() as locks:
            disco=self.ler()
            antigos={p['uuid']:p for p in self._original['projetos']}
            atuais={p['uuid']:p for p in disco['projetos']}
            novos={p['uuid']:p for p in dados['projetos']}
            tocados={u for u in antigos.keys() | novos.keys() if novos.get(u)!=antigos.get(u)}
            for u in sorted(tocados):
                p=novos.get(u,{})
                caminho=p.get('manifesto_wna')
                if caminho:locks.enter_context(self.trava(caminho))
            atuais={p['uuid']:p for p in self.ler()['projetos']}
            for u in tocados:
                if atuais.get(u)!=antigos.get(u):
                    raise ValueError('O projeto mudou em outra sessão. Reabra antes de salvar.')
            for u in tocados:
                p=novos.get(u)
                caminho=(p or {}).get('manifesto_wna')
                if caminho:
                    if not Path(caminho).is_file():
                        raise ValueError('Arquivo .wna indisponível. Abra o arquivo em sua nova localização.')
                    publicado=ler(caminho)
                    if publicado['uuid']!=u:
                        raise ValueError('O arquivo .wna registrado possui outra identidade.')
                    if u in antigos and antigos[u].get('manifesto_wna')==caminho:
                        gravar(caminho,p)
                        p=ler(caminho)
                if p is None:atuais.pop(u,None)
                else:atuais[u]=p
            novo=dict(dados,projetos=list(atuais.values()))
            self._gravar_indice(novo)
            self._original=deepcopy(novo)

    def abrir_manifesto(self,caminho):
        from .manifesto_projeto import ler
        with self.trava(self.path):
            p=ler(caminho)
            dados=self.ler()
            existentes=[r for r in dados['projetos'] if r['uuid']==p['uuid']]
            if existentes:
                antigo=existentes[0]
                ref=antigo.get('manifesto_wna')
                if ref and ref!=p['manifesto_wna'] and Path(ref).exists():
                    raise ValueError('Já existe outro arquivo .wna ativo com esta identidade. Abra o original registrado.')
            dados['projetos']=[r for r in dados['projetos'] if r['uuid']!=p['uuid']]+[p]
            dados['ativo']=p['uuid']
            self._gravar_indice(dados)
            self._original=deepcopy(dados)
            return p

    def salvar_manifesto(self,caminho,nome=None,estado_salvo=None):
        from .manifesto_projeto import gravar, ler
        p=dict(uuid=uuid4().hex,nome=nome.strip(),bases=[],ultima=None,contexto={},layout=1) if nome else self.atual()
        if p is None:raise ValueError('Selecione um projeto.')
        caminho=Path(caminho).resolve()
        if caminho.suffix.lower()!='.wna':
            caminho=caminho.with_suffix('.wna')
        if p.get('manifesto_wna'):
            raise ValueError('O projeto já possui um arquivo .wna.')
        with self.trava(self.path):
            dados=self.ler()
            atual=next((r for r in dados['projetos'] if r['uuid']==p['uuid']),None)
            if not nome and atual!=p:
                raise ValueError('O projeto mudou em outra sessão. Reabra antes da migração.')
            if estado_salvo is not None:p=dict(p, layout=1, sessao_wna=estado_salvo)
            gravar(caminho,p,exclusivo=True)
            registrado=ler(caminho)
            dados['projetos']=[r for r in dados['projetos'] if r['uuid']!=p['uuid']]+[registrado]
            dados['ativo']=p['uuid']
            self._gravar_indice(dados)
            self._original=deepcopy(dados)
            return registrado

    def salvar_sessao(self, sessao):
        dados=deepcopy(self.dados)
        p=next(r for r in dados['projetos'] if r['uuid']==dados['ativo'])
        p['sessao_wna']=sessao
        self.gravar(dados)

    def _gravar_indice(self,dados):
        tmp=self.path.with_name(self.path.name+'.'+uuid4().hex+'.tmp')
        # No Windows, indexadores podem reter o destino durante uma leitura.
        # Não se apaga o índice antigo; erro persistente é comunicado ao chamador.
        try:
            with tmp.open('x',encoding='utf8') as arq:
                json.dump(dados,arq,ensure_ascii=False,indent=2)
                arq.flush()
                os.fsync(arq.fileno())
            for tentativa in range(4):
                try:os.replace(tmp,self.path);break
                except PermissionError:
                    if tentativa==3:raise
                    time.sleep(.03)
            self.dados=dados
        finally:
            tmp.unlink(missing_ok=True)
    def criar(self,nome):
        if not nome.strip():raise ValueError('Informe o nome do projeto')
        self.dados=self.ler();self._original=deepcopy(self.dados);p=dict(uuid=uuid4().hex,nome=nome.strip(),bases=[],ultima=None,contexto={});self.dados['projetos'].append(p);self.dados['ativo']=p['uuid'];self.salvar();return p
    def ativar(self,uid):
        self.dados=self.ler()
        self._original=deepcopy(self.dados)
        if not any(p['uuid']==uid for p in self.dados['projetos']):raise ValueError('Projeto não identificado')
        self.dados['ativo']=uid;self.salvar()
    def atual(self):return next((p for p in self.dados['projetos'] if p['uuid']==self.dados['ativo']),None)
    def contem(self,tipo,uid):
        p=self.atual()
        return not p or any(r['tipo']==tipo and r['uuid']==uid for r in p['bases']) or p.get('em_memoria',{}).get(tipo)==uid
    def vincular(self,registro,*,atualizar_ultimo=True):
        from .trabalhos_projeto import chave, referencia
        if not registro.get('base'):
            if p:=self.atual():p.setdefault('em_memoria',{})[registro['tipo']]=registro['uuid']
            return
        dados=deepcopy(self.dados)
        p=next((r for r in dados['projetos'] if r['uuid']==dados['ativo']),None)
        if not p:return
        if registro.get('projeto_uid') and registro['projeto_uid']!=p['uuid']:
            raise ValueError('O trabalho pertence a outro projeto.')
        identidade=referencia(registro)
        p.setdefault('em_memoria',{})[identidade['tipo']]=identidade['uuid']
        for i, anterior in enumerate(p['bases']):
            if chave(anterior)!=chave(identidade):continue
            vinculo=dict(anterior,**identidade)
            if anterior['base']!=vinculo['base']:
                from .trabalhos_projeto import agora
                vinculo['localizacoes']=[*anterior.get('localizacoes',[]),
                                       dict(caminho=anterior['base'],data=agora())]
            p['bases'][i]=vinculo
            p['bases']=[x for j,x in enumerate(p['bases']) if j==i or chave(x)!=chave(vinculo)]
            if p.get('ultima') and chave(p['ultima'])==chave(vinculo):p['ultima']=vinculo
            break
        else:
            p['bases'].append(identidade)
            if atualizar_ultimo:p['ultima']=identidade
        if dados!=self.dados:
            self.gravar(dados)

    def adotar_organizado(self, caminho, anterior):
        """Muda a referência do índice somente após publicar o novo manifesto."""
        from .manifesto_projeto import ler
        with self.trava(self.path):
            dados=self.ler()
            antigo=next((r for r in dados['projetos'] if r['uuid']==anterior['uuid']),None)
            if antigo!=anterior:
                raise ValueError('O projeto mudou em outra sessão. O manifesto preparado está disponível para conferência.')
            p=ler(caminho)
            if p['uuid']!=anterior['uuid']:
                raise ValueError('O manifesto organizado possui outra identidade.')
            dados['projetos']=[p if r['uuid']==p['uuid'] else r for r in dados['projetos']]
            dados['ativo']=p['uuid']
            self._gravar_indice(dados)
            self._original=deepcopy(dados)

    def atualizar_organizado(self,anterior,novo):
        if self.atual()!=anterior or novo['uuid']!=anterior['uuid']:
            raise ValueError('O projeto mudou durante a organização. Confira o backup das referências.')
        dados=deepcopy(self.dados)
        dados['projetos']=[novo if r['uuid']==novo['uuid'] else r for r in dados['projetos']]
        self.gravar(dados)


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
            tabelas={'INTEGRADA':('IG_EXECUCOES','ig_uid'),'TOPOLOGIA_GIS':('TG_EXECUCAO','uuid'),
                     'ESTRUTURA_GIS':('TG_ESTRUTURA','uuid')}
            tabela,campo=tabelas.get(r['tipo'],('EXECUCOES','exe_uid'))
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
