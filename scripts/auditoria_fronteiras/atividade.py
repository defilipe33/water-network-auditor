"""Acompanhamento GUI compartilhado; reutiliza workers e checkpoints existentes."""
from contextlib import contextmanager
from time import monotonic
import weakref
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QObject,Qt,QTimer,QEvent,QThread,pyqtSignal
from qgis.PyQt.QtWidgets import (QApplication,QDockWidget,QWidget,QVBoxLayout,QLabel,
    QProgressBar,QPushButton,QPlainTextEdit,QMainWindow)


class Trabalho(QThread):
    pronto=pyqtSignal(object);erro=pyqtSignal(str);progresso=pyqtSignal(int,str);detalhes=pyqtSignal(str)
    def __init__(self,funcao,parent):super().__init__(parent);self.funcao=funcao
    def run(self):
        try:self.pronto.emit(self.funcao(self.isInterruptionRequested,self.progresso.emit))
        except Exception as e:
            import traceback
            self.detalhes.emit(traceback.format_exc());self.erro.emit(str(e))


class Operacao:
    def __init__(self,sistema,titulo,contexto,cancelar=None):
        self.sistema=sistema;self.titulo=titulo;self.contexto=contexto;self.estado='EM_ANDAMENTO';self.etapa='Preparando operação';self.percentual=None;self.cancelar_callback=cancelar;self.solicitado=False;self.detalhes='';self.inicio=monotonic();self._bombeando=False;self._ultima=0
    def atualizar(self,etapa,atual=None,total=None):
        if self.estado not in ('EM_ANDAMENTO','CANCELANDO'):return
        self.etapa=etapa
        # O número é da etapa mensurada. Ao terminar a etapa voltamos a indeterminado;
        # 100% fica reservado à conclusão bem-sucedida da operação inteira.
        self.percentual=int(100*atual/total) if total and atual is not None and 0<=atual<total else None
        self.sistema.desenhar()
    def sinal(self,n,etapa):
        # Sinais legados incluem marcos fixos, não denominadores verificáveis.
        self.atualizar(etapa)
    def cancelar(self):
        if self.cancelar_callback is None or self.estado not in ('EM_ANDAMENTO','CANCELANDO'):return
        self.solicitado=True;self.estado='CANCELANDO';self.cancelar_callback();self.etapa='Cancelamento solicitado; aguardando ponto seguro';self.sistema.desenhar()
    def ponto(self):
        # Bombeamento central, limitado e não recursivo. O filtro bloqueia comandos
        # concorrentes nas interfaces da ferramenta; Cancelar fica no dock próprio.
        agora=monotonic()
        if not self._bombeando and agora-self._ultima>=.08:
            self._ultima=agora;self._bombeando=True
            try:QApplication.processEvents()
            finally:self._bombeando=False
        return self.solicitado
    def critica(self,etapa):
        if self.solicitado:raise InterruptedError('Operação cancelada antes da publicação')
        self.cancelar_callback=None;self.atualizar(etapa+' · aguarde; esta etapa não admite cancelamento')
    def finalizar(self,estado='CONCLUIDO',mensagem='Operação concluída e validada',detalhes=''):
        if self.estado not in ('EM_ANDAMENTO','CANCELANDO'):return
        self.estado=estado;self.etapa=mensagem;self.detalhes=detalhes or self.detalhes;self.percentual=100 if estado=='CONCLUIDO' else None
        self.sistema.desenhar();self.sistema.atual=None


class Atividades(QObject):
    def __init__(self,principal):
        super().__init__(principal);self.atual=None;self.ultima=None;self._alvos=[];self.workers=[]
        self.dock=QDockWidget('Atividade — Water Network Auditor',principal);self.dock.setObjectName('WNA_Atividades');w=QWidget();self.dock.setWidget(w);v=QVBoxLayout(w)
        self.titulo=QLabel();self.contexto=QLabel();self.estado=QLabel();self.etapa=QLabel()
        for l in (self.titulo,self.contexto,self.estado,self.etapa):l.setWordWrap(True);v.addWidget(l)
        self.barra=QProgressBar();v.addWidget(self.barra);self.cancelar=QPushButton('Cancelar com segurança');v.addWidget(self.cancelar);self.cancelar.clicked.connect(lambda:self.atual.cancelar() if self.atual else None)
        self.detalhes=QPlainTextEdit();self.detalhes.setReadOnly(True);self.detalhes.setMaximumHeight(120);self.detalhes.hide();v.addWidget(self.detalhes)
        b=QPushButton('Detalhes técnicos');b.setCheckable(True);b.toggled.connect(self.detalhes.setVisible);v.addWidget(b)
        if isinstance(principal,QMainWindow):principal.addDockWidget(Qt.BottomDockWidgetArea,self.dock)
        else:self.dock.setWindowFlags(Qt.Tool);self.dock.resize(500,220)
        self.dock.hide();self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.exibir)
        QApplication.instance().installEventFilter(self)
    def vincular(self,w):
        if not any(ref() is w for ref in self._alvos):self._alvos.append(weakref.ref(w))
        w._wna_atividades=self
    def em_execucao(self):return self.atual is not None or any(not sip.isdeleted(t) and t.isRunning() for t in self.workers)
    def eventFilter(self,obj,event):
        if self.atual is not None and event.type() in (QEvent.MouseButtonPress,QEvent.MouseButtonRelease,QEvent.KeyPress,QEvent.KeyRelease):
            alvos=[ref() for ref in self._alvos if ref() is not None and not sip.isdeleted(ref())]
            if isinstance(obj,QWidget) and any((obj is w or w.isAncestorOf(obj)) and obj.window()==w.window() for w in alvos):return True
        return False
    def iniciar(self,titulo,contexto='',cancelar=None):
        if self.em_execucao():raise RuntimeError('Outra operação está em andamento; aguarde o ponto seguro de conclusão')
        self.atual=self.ultima=Operacao(self,titulo,contexto,cancelar);self.desenhar();self.timer.start(400);return self.atual
    def exibir(self):
        if self.atual:self.dock.show()
    def desenhar(self):
        o=self.atual or self.ultima
        if o is None:return
        self.titulo.setText(o.titulo);self.contexto.setText(o.contexto);self.estado.setText(o.estado.replace('_',' '));self.etapa.setText(o.etapa)
        self.cancelar.setEnabled(o.cancelar_callback is not None and o.estado=='EM_ANDAMENTO')
        self.cancelar.setToolTip('Interrupção cooperativa; aguarda a etapa atual.' if o.cancelar_callback else 'Esta etapa não possui cancelamento seguro; aguarde sua conclusão.')
        self.barra.setRange(0,100 if o.percentual is not None else 0)
        if o.percentual is not None:self.barra.setValue(o.percentual)
        self.detalhes.setPlainText(o.detalhes)
    @contextmanager
    def operacao(self,titulo,contexto='',cancelar=None):
        import traceback
        o=self.iniciar(titulo,contexto,cancelar)
        try:
            yield o
        except Exception as e:
            estado='CANCELADO' if isinstance(e,InterruptedError) or type(e).__name__=='Cancelado' else 'ERRO'
            o.finalizar(estado,str(e)+' · versões anteriores preservadas',traceback.format_exc());self.dock.show();raise
        else:
            if o.solicitado:o.finalizar('CANCELADO','Cancelamento concluído em ponto seguro')
            else:o.finalizar()
    def executar_thread(self,titulo,contexto,funcao,pronto,erro=None):
        t=Trabalho(funcao,self);o=self.iniciar(titulo,contexto,t.requestInterruption);self.workers.append(t)
        t.progresso.connect(o.sinal)
        t.detalhes.connect(lambda texto:setattr(o,'detalhes',texto))
        def receber(dado):
            try:
                if o.solicitado or t.isInterruptionRequested():o.finalizar('CANCELADO','Carregamento cancelado; contexto anterior preservado');return
                o.atualizar('Preparando apresentação dos resultados');resultado=pronto(dado)
                o.finalizar('CANCELADO','Apresentação não aplicada; contexto anterior preservado') if resultado is False else o.finalizar()
            except Exception as e:falhou(str(e))
        def falhou(texto):
            o.finalizar('CANCELADO' if o.solicitado or t.isInterruptionRequested() else 'ERRO',texto+' · contexto anterior preservado',o.detalhes or texto);self.dock.show()
            if erro:erro(texto)
        def terminou():
            if t in self.workers:self.workers.remove(t)
            t.deleteLater()
        t.pronto.connect(receber);t.erro.connect(falhou);t.finished.connect(terminou);t.start();return t
    def fechar(self):
        if self.em_execucao():return False
        self.timer.stop();QApplication.instance().removeEventFilter(self);self.dock.close();return True


def sistema(widget):
    w=widget
    while w is not None:
        s=getattr(w,'_wna_atividades',None)
        if s is not None:return s
        w=w.parentWidget()
    s=Atividades(widget.window());s.vincular(widget);return s


@contextmanager
def etapa(widget,titulo,contexto=''):
    s=sistema(widget)
    if s.atual is not None:
        s.atual.atualizar(titulo);yield s.atual
    else:
        with s.operacao(titulo,contexto) as o:
            o.ponto();yield o


def acompanhada(titulo):
    from functools import wraps
    def decorar(fn):
        @wraps(fn)
        def chamada(self,*args,**kwargs):
            s=sistema(self);ativas=getattr(self,'_wna_chamadas',set())
            if fn.__name__ in ativas and s.atual and s.atual._bombeando:return False
            self._wna_chamadas=ativas;ativas.add(fn.__name__)
            try:
                with etapa(self,titulo,str(getattr(self,'base','') or '')) as o:
                    resultado=fn(self,*args,**kwargs)
                    if resultado is False:o.finalizar('CANCELADO','Operação não aplicada; contexto anterior preservado')
                    return resultado
            finally:ativas.discard(fn.__name__)
        return chamada
    return decorar


class Progresso:
    """Adaptador dos checkpoints GUI existentes, sem outro processamento/modal."""
    def __init__(self,texto,botao,minimo,maximo,parent):
        self.s=sistema(parent);self.o=self.s.iniciar(texto,cancelar=(lambda:None) if botao else None);self.maximo=maximo;self.valor=0;self.texto=texto
    def setWindowTitle(self,t):self.o.titulo=t;self.s.desenhar()
    def setWindowModality(self,*args):pass
    def setMinimumDuration(self,*args):pass
    def setAutoClose(self,*args):pass
    def setAutoReset(self,*args):pass
    def setRange(self,a,b):self.maximo=b;self.o.atualizar(self.texto)
    def setValue(self,n):self.valor=n;self.o.atualizar(self.texto,n,self.maximo)
    def setLabelText(self,t):self.texto=t;self.o.atualizar(t,self.valor,self.maximo)
    def show(self):self.s.exibir();self.o.ponto()
    def hide(self):self.s.dock.hide()
    def deleteLater(self):pass
    def cancel(self):self.o.cancelar()
    def wasCanceled(self):return self.o.ponto()
    def concluir(self):self.o.finalizar()
    def falhar(self,e):self.o.finalizar('CANCELADO' if type(e).__name__ in ('Cancelado','InterruptedError') else 'ERRO',str(e)+' · versões anteriores preservadas')
    def close(self):
        if self.o.estado in ('EM_ANDAMENTO','CANCELANDO'):
            self.o.finalizar('CANCELADO' if self.o.solicitado else 'AGUARDANDO_CONFIRMACAO','Etapa encerrada; publicação não confirmada')


def falha(widget,e):
    s=sistema(widget)
    if s.atual:s.atual.finalizar('ERRO',str(e)+' · versões anteriores preservadas',str(e))
