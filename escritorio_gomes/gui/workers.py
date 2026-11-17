"""Execução de tarefas de rede em segundo plano, sem travar a janela."""

from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class _Sinais(QObject):
    ok = Signal(object)
    erro = Signal(str)


class _Tarefa(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.sinais = _Sinais()

    def run(self):
        try:
            resultado = self.fn(*self.args, **self.kwargs)
        except Exception as e:  # noqa: BLE001 - repassa qualquer erro para a interface
            traceback.print_exc()
            self.sinais.erro.emit(str(e) or e.__class__.__name__)
        else:
            self.sinais.ok.emit(resultado)


_ativas: set = set()


def executar(fn, *args, ao_concluir=None, ao_falhar=None, **kwargs) -> None:
    tarefa = _Tarefa(fn, *args, **kwargs)
    _ativas.add(tarefa.sinais)
    if ao_concluir:
        tarefa.sinais.ok.connect(ao_concluir)
    if ao_falhar:
        tarefa.sinais.erro.connect(ao_falhar)
    tarefa.sinais.ok.connect(lambda *_: _ativas.discard(tarefa.sinais))
    tarefa.sinais.erro.connect(lambda *_: _ativas.discard(tarefa.sinais))
    tarefa.setAutoDelete(True)
    QThreadPool.globalInstance().start(tarefa)
