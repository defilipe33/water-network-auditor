"""Sonda opcional, explícita e local. Não é importada na operação normal.

Registra nomes de operações e contagens; não registra argumentos, SQL ou URIs.
Use somente durante ensaios controlados e feche antes de descarregar o plugin.
"""
from collections import Counter
from functools import wraps
from pathlib import Path
from statistics import median
from time import perf_counter
import cProfile
import json
import threading


class Diagnostico:
    def __init__(self, pasta, habilitado=True):
        self.pasta = Path(pasta)
        self.habilitado = habilitado
        self.chamadas, self.tempos = Counter(), Counter()
        self.resultados, self._originais = [], []
        self._lock = threading.Lock()

    def envolver(self, objeto, nome, rotulo=None):
        if not self.habilitado:
            return
        if any(o is objeto and n == nome for o, n, _ in self._originais):
            return
        original = getattr(objeto, nome)
        chave = rotulo or nome

        @wraps(original)
        def executar(*args, **kwargs):
            inicio = perf_counter()
            from qgis.PyQt.QtCore import QCoreApplication, QThread
            app = QCoreApplication.instance()
            principal = app is not None and QThread.currentThread() == app.thread()
            try:
                return original(*args, **kwargs)
            finally:
                with self._lock:
                    self.chamadas[chave] += 1
                    self.chamadas[chave + (':principal' if principal else ':worker')] += 1
                    self.tempos[chave] += perf_counter() - inicio
        setattr(objeto, nome, executar)
        self._originais.append((objeto, nome, original))

    def medir(self, nome, acao, repeticoes=15):
        if not self.habilitado:
            return acao()
        if repeticoes < 1:
            raise ValueError('Informe ao menos uma repetição.')
        tempos = []
        contadores = self.chamadas.copy()
        for _ in range(repeticoes):
            inicio = perf_counter()
            acao()
            tempos.append(1000 * (perf_counter() - inicio))
        ordenados = sorted(tempos)
        resultado = dict(operacao=nome, repeticoes=repeticoes, primeira_ms=tempos[0],
                         mediana_ms=median(tempos[1:] or tempos),
                         p95_ms=ordenados[min(len(tempos)-1, int(.95*len(tempos)))],
                         pior_ms=max(tempos), chamadas=dict(self.chamadas-contadores))
        self.resultados.append(resultado)
        return resultado

    def perfil(self, nome, acao):
        if not self.habilitado:
            return acao()
        if Path(nome).name != nome or not nome:
            raise ValueError('Use um nome simples para o perfil.')
        self.pasta.mkdir(parents=True, exist_ok=True)
        profiler = cProfile.Profile()
        try:
            return profiler.runcall(acao)
        finally:
            profiler.dump_stats(str(self.pasta / (nome + '.prof')))

    def salvar(self):
        if not self.habilitado:
            return
        self.pasta.mkdir(parents=True, exist_ok=True)
        destino = self.pasta / 'diagnostico.json'
        destino.write_text(json.dumps(dict(operacoes=self.resultados, chamadas=dict(self.chamadas),
                                          tempos_inclusivos_s=dict(self.tempos)), indent=2), encoding='utf8')
        return destino

    def fechar(self):
        for objeto, nome, original in reversed(self._originais):
            setattr(objeto, nome, original)
        self._originais.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.fechar()
