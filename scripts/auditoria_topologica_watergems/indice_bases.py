"""Ciclo de vida do índice operacional; nunca modifica os GeoPackages indexados."""
from contextlib import closing
from pathlib import Path
import json
import sqlite3
from uuid import uuid4
from .arquivos import hash_arquivo

DDL='CREATE TABLE bases(uuid TEXT,tipo TEXT,base TEXT NOT NULL,dados TEXT NOT NULL,PRIMARY KEY(uuid,tipo,base))'

class ErroCatalogo(RuntimeError):
    def __init__(self,mensagem,caminho):
        super().__init__(f'Catálogo indisponível em {caminho}: {mensagem}. As bases de auditoria não foram alteradas.')

class IndiceSQLite:
    def __init__(self,raiz):
        if raiz is None or not str(raiz).strip():raise ErroCatalogo('selecione explicitamente a pasta de trabalho; o diretório atual não será usado como alternativa','(pasta não informada)')
        self._raiz=Path(raiz).resolve();self._arquivo=self._raiz/'catalogo_bases.sqlite';self.avisos=[];self.problema=None;self._reconstruir=False;self._varrendo=False;self._reconstrucao_tentada=False
        try:
            self._raiz.mkdir(parents=True,exist_ok=True);self.garantir()
        except (ErroCatalogo,OSError) as e:self.problema=str(e);self.advertir(str(e))
    @property
    def raiz(self):return self._raiz
    @property
    def arquivo(self):return self._arquivo
    def advertir(self,texto):
        if texto not in self.avisos:self.avisos.append(texto)
    def caminho_valido(self):
        if not self.raiz.is_dir() or self.raiz.resolve()!=self.raiz or self.arquivo.resolve()!=self.arquivo:
            raise ErroCatalogo('a pasta selecionada desapareceu ou mudou de destino; selecione explicitamente a pasta de trabalho correta',self.arquivo)
    def _abrir_rw(self):return sqlite3.connect(self.arquivo,timeout=3)
    def _abrir_ro(self):return sqlite3.connect(self.arquivo.as_uri()+'?mode=ro',uri=True,timeout=3)
    def traduzir(self,e):
        s=str(e).lower()
        causa='banco SQLite corrompido ou formato inválido; preserve o arquivo e restaure backup ou escolha outra pasta para reconstruir o índice' if any(x in s for x in ('malformed','not a database','encrypted')) else 'sem permissão de gravação; confirme as permissões da pasta selecionada' if any(x in s for x in ('readonly','permission','denied','read-only')) else 'arquivo ocupado por outra sessão; aguarde e tente novamente' if any(x in s for x in ('locked','busy')) else str(e)
        return ErroCatalogo(causa,self.arquivo)
    @staticmethod
    def esquema(con):
        tabelas={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        cols=list(con.execute('PRAGMA table_info(bases)')) if 'bases' in tabelas else []
        atual={r[1] for r in cols}=={'uuid','tipo','base','dados'} and [r[1] for r in sorted(cols,key=lambda r:r[5]) if r[5]]==['uuid','tipo','base']
        return tabelas,cols,atual
    def backup(self):
        destino=self.arquivo.with_name('catalogo_bases.backup_'+uuid4().hex+'.sqlite')
        with closing(self._abrir_ro()) as origem,closing(sqlite3.connect(destino)) as copia:
            origem.backup(copia)
            if copia.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Backup do catálogo não íntegro')
        self.advertir('Backup de migração preservado em '+str(destino));return destino
    def garantir(self):
        """Toda operação verifica o esquema; leitura válida não exige escrita."""
        self.caminho_valido()
        try:
            if self.arquivo.exists() and self.arquivo.stat().st_size:
                with closing(self._abrir_ro()) as con:
                    if con.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise sqlite3.DatabaseError('database malformed')
                    tabelas,cols,atual=self.esquema(con)
                if atual:self.problema=None;return
            with closing(self._abrir_rw()) as con:
                con.execute('BEGIN IMMEDIATE')
                try:
                    tabelas,cols,atual=self.esquema(con)
                    if atual:con.rollback();self.problema=None;return
                    if tabelas:self.backup()
                    legado=None
                    if 'bases' in tabelas:
                        legado='bases_legado_'+uuid4().hex;con.execute('ALTER TABLE bases RENAME TO '+legado)
                    con.execute(DDL)
                    if legado:
                        nomes=[r[1] for r in cols]
                        for linha in con.execute('SELECT * FROM '+legado):
                            r=dict(zip(nomes,linha));bruto=r.get('dados',r.get('metadados'))
                            try:
                                d=json.loads(bruto) if isinstance(bruto,str) else {};uid=r.get('uuid') or d.get('uuid');tipo=r.get('tipo') or d.get('tipo');base=r.get('base',r.get('caminho')) or d.get('base')
                                if not uid or not tipo or not base:raise ValueError('identidade incompleta')
                                d.update(uuid=uid,tipo=tipo,base=base)
                                con.execute('INSERT INTO bases VALUES(?,?,?,?)',(uid,tipo,base,json.dumps(d,ensure_ascii=False)))
                            except (ValueError,TypeError,AttributeError,sqlite3.IntegrityError):self.advertir('Registro legado não interpretável ou duplicado preservado integralmente em '+legado)
                    con.execute('PRAGMA user_version=2');con.commit();self._reconstruir=True
                    self.advertir('Esquema do catálogo inicializado/recuperado na pasta selecionada; bases existentes serão reexaminadas.')
                except Exception:con.rollback();raise
            self.problema=None
        except (sqlite3.Error,OSError,ValueError) as e:
            erro=self.traduzir(e);self.problema=str(erro);raise erro from e
    def conectar(self):
        self.garantir();return closing(self._abrir_rw())
    def registrar_opcional(self,base):
        try:return self.registrar(base)
        except (ErroCatalogo,sqlite3.Error,OSError,ValueError) as e:self.advertir(str(e));return []
    def listar_opcional(self):
        try:return self.listar()
        except (ErroCatalogo,sqlite3.Error,OSError,ValueError) as e:self.advertir(str(e));return []
