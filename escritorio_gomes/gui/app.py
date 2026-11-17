from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QLabel, QMainWindow, QMessageBox, QStyle, QSystemTrayIcon, QTabWidget,
)

from .. import __version__, config, db
from .ads_tab import AdsTab
from .clientes_tab import ClientesTab
from .config_dialog import ConfigDialog
from .dje_tab import DjeTab


class JanelaPrincipal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = config.load()
        self.conn = db.connect()
        self.setWindowTitle(f"{self.cfg['escritorio']['nome']} — Sistema Integrado")
        self.resize(1360, 820)

        self.abas = QTabWidget()
        self.aba_dje = None
        self.aba_clientes = ClientesTab(self)
        self.aba_dje = DjeTab(self)
        self.aba_ads = AdsTab(self)
        self.abas.addTab(self.aba_dje, "Intimações (DJE)")
        self.abas.addTab(self.aba_clientes, "Clientes")
        self.abas.addTab(self.aba_ads, "Google Ads")
        self.abas.currentChanged.connect(self._mudou_aba)
        self.setCentralWidget(self.abas)
        self.atualizar_contador_dje()

        menu = self.menuBar()
        m_arq = menu.addMenu("&Arquivo")
        a_cfg = QAction("Configurações…", self, shortcut="Ctrl+,")
        a_cfg.triggered.connect(self.abrir_config)
        m_arq.addAction(a_cfg)
        m_arq.addSeparator()
        a_sair = QAction("Sair", self, shortcut="Ctrl+Q")
        a_sair.triggered.connect(self.close)
        m_arq.addAction(a_sair)
        m_aj = menu.addMenu("Aj&uda")
        a_sobre = QAction("Sobre", self)
        a_sobre.triggered.connect(lambda: QMessageBox.about(
            self, "Sobre", f"Sistema Integrado {self.cfg['escritorio']['nome']}\nVersão {__version__}\n\n"
                           f"Dados locais em: {config.APP_DIR}"))
        m_aj.addAction(a_sobre)

        self.lbl_oab = QLabel()
        self.statusBar().addPermanentWidget(self.lbl_oab)
        self._atualizar_rodape()

        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.style().standardIcon(QStyle.SP_FileDialogInfoView), self)
            self.tray.setToolTip(self.windowTitle())
            self.tray.activated.connect(lambda *_: (self.showNormal(), self.activateWindow()))
            self.tray.show()

        if self.cfg["dje"].get("buscar_ao_abrir", True) and self.cfg["escritorio"].get("oab_numero"):
            QTimer.singleShot(800, lambda: self.aba_dje.buscar_djen(silencioso=True))
        # Nova verificação a cada 2 horas com o sistema aberto
        self.timer_dje = QTimer(self, interval=2 * 60 * 60 * 1000)
        self.timer_dje.timeout.connect(lambda: self.aba_dje.buscar_djen(silencioso=True))
        self.timer_dje.start()

    def _atualizar_rodape(self):
        e = self.cfg["escritorio"]
        self.lbl_oab.setText(f"{e.get('advogado', '')} · OAB/{e.get('oab_uf', '')} {e.get('oab_numero', '')}")

    def _mudou_aba(self, _):
        if self.abas.currentWidget() is self.aba_clientes:
            self.aba_clientes.recarregar()

    def status(self, msg: str):
        self.statusBar().showMessage(msg, 10000)

    def notificar(self, titulo: str, msg: str):
        if self.tray:
            self.tray.showMessage(titulo, msg)

    def atualizar_contador_dje(self):
        if not self.aba_dje:
            return
        n = self.conn.execute("SELECT COUNT(*) FROM intimacoes WHERE lida = 0").fetchone()[0]
        self.abas.setTabText(self.abas.indexOf(self.aba_dje), f"Intimações (DJE){f'  [{n}]' if n else ''}")

    def abrir_config(self):
        dlg = ConfigDialog(self.cfg, self)
        if dlg.exec():
            self.cfg = dlg.cfg
            config.save(self.cfg)
            self._atualizar_rodape()
            self.status("Configurações salvas.")

    def closeEvent(self, ev):
        self.conn.close()
        if self.tray:
            self.tray.hide()
        super().closeEvent(ev)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Escritório Gomes")
    app.setStyle("Fusion")
    janela = JanelaPrincipal()
    janela.show()
    sys.exit(app.exec())
