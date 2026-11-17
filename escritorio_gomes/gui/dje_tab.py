from __future__ import annotations

import csv
from datetime import date

from PySide6.QtCore import QDate, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QSplitter,
    QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget,
)

from .. import clientes as cl
from .. import dje
from .workers import executar


def _qdate(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


def _pydate(q: QDate) -> date:
    return date(q.year(), q.month(), q.day())


def _br(iso: str | None) -> str:
    if iso and len(iso) >= 10 and iso[4] == "-":
        return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"
    return iso or ""


class DjeTab(QWidget):
    def __init__(self, janela):
        super().__init__()
        self.janela = janela
        self.linhas = []
        self.atual = None
        esc = janela.cfg["escritorio"]

        # ---- busca no DJEN
        hoje = date.today()
        dias = int(janela.cfg["dje"].get("dias_retroativos", 7))
        self.de = QDateEdit(_qdate(hoje), calendarPopup=True, displayFormat="dd/MM/yyyy")
        self.de.setDate(self.de.date().addDays(-dias))
        self.ate = QDateEdit(_qdate(hoje), calendarPopup=True, displayFormat="dd/MM/yyyy")
        self.oab = QLineEdit(esc.get("oab_numero", ""))
        self.oab.setMaximumWidth(90)
        self.oab_uf = QComboBox()
        self.oab_uf.addItems(cl.UFS)
        self.oab_uf.setCurrentText(esc.get("oab_uf", "RJ"))
        self.parte = QLineEdit(placeholderText="Nome da parte (opcional)")
        self.processo = QLineEdit(placeholderText="Nº do processo (opcional)")
        self.tribunal = QLineEdit(placeholderText="Ex.: TJRJ, TRT1")
        self.tribunal.setMaximumWidth(110)
        self.b_buscar = QPushButton("Buscar no DJEN")
        self.b_buscar.clicked.connect(self.buscar_djen)

        g = QGroupBox("Buscar intimações no Diário de Justiça Eletrônico Nacional (CNJ)")
        lg = QHBoxLayout(g)
        for rot, w in (("De", self.de), ("até", self.ate), ("OAB", self.oab), ("/", self.oab_uf),
                       ("", self.parte), ("", self.processo), ("Tribunal", self.tribunal)):
            if rot:
                lg.addWidget(QLabel(rot))
            lg.addWidget(w)
        lg.addWidget(self.b_buscar)

        # ---- lista local
        self.filtro = QLineEdit(placeholderText="Filtrar intimações salvas (texto, parte, processo, cliente)…")
        self.filtro.textChanged.connect(self.recarregar)
        self.so_nao_lidas = QCheckBox("Somente não lidas")
        self.so_nao_lidas.toggled.connect(self.recarregar)
        self.tabela = QTableWidget(0, 6)
        self.tabela.setHorizontalHeaderLabels(["Data", "Tribunal", "Processo", "Tipo", "Cliente", "Prazo"])
        self.tabela.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.tabela.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabela.setSelectionMode(QTableWidget.SingleSelection)
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.itemSelectionChanged.connect(self._selecionou)
        self.resumo = QLabel()
        b_csv = QPushButton("Exportar CSV")
        b_csv.clicked.connect(self.exportar_csv)

        esq = QWidget()
        le = QVBoxLayout(esq)
        topo = QHBoxLayout()
        topo.addWidget(self.filtro)
        topo.addWidget(self.so_nao_lidas)
        le.addLayout(topo)
        le.addWidget(self.tabela)
        rod = QHBoxLayout()
        rod.addWidget(self.resumo)
        rod.addStretch()
        rod.addWidget(b_csv)
        le.addLayout(rod)

        # ---- detalhe
        self.cabecalho = QLabel()
        self.cabecalho.setWordWrap(True)
        self.cabecalho.setTextFormat(Qt.RichText)
        self.cabecalho.setMinimumHeight(80)
        self.cabecalho.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.texto = QTextBrowser()
        self.texto.setFont(QFont("Consolas", 10))
        self.b_link = QPushButton("Abrir no tribunal")
        self.b_link.clicked.connect(self._abrir_link)
        self.b_lida = QPushButton("Marcar como lida")
        self.b_lida.setMinimumWidth(170)
        self.b_lida.clicked.connect(self._alternar_lida)
        self.cliente = QComboBox()
        b_vinc = QPushButton("Vincular processo ao cliente")
        b_vinc.clicked.connect(self._vincular)
        self.dias_prazo = QSpinBox(minimum=0, maximum=120, value=15, suffix=" dias úteis")
        b_calc = QPushButton("Calcular")
        b_calc.clicked.connect(self._calcular_prazo)
        self.prazo = QLineEdit(placeholderText="DD/MM/AAAA")
        self.obs = QLineEdit(placeholderText="Providência, responsável…")
        b_salvar = QPushButton("Salvar anotações")
        b_salvar.clicked.connect(self._salvar_anotacoes)

        dir_ = QWidget()
        ld = QVBoxLayout(dir_)
        ld.addWidget(self.cabecalho)
        ld.addWidget(self.texto, 1)
        acoes = QHBoxLayout()
        acoes.addWidget(self.b_link)
        acoes.addWidget(self.b_lida)
        acoes.addStretch()
        ld.addLayout(acoes)
        form = QFormLayout()
        lc = QHBoxLayout()
        lc.addWidget(self.cliente, 1)
        lc.addWidget(b_vinc)
        form.addRow("Cliente", lc)
        lp = QHBoxLayout()
        lp.addWidget(self.dias_prazo)
        lp.addWidget(b_calc)
        lp.addWidget(QLabel("Vencimento"))
        lp.addWidget(self.prazo)
        form.addRow("Prazo", lp)
        form.addRow("Observação", self.obs)
        ld.addLayout(form)
        ld.addWidget(b_salvar)
        aviso = QLabel("Prazo estimado em dias úteis (CPC arts. 219 e 224), sem feriados locais "
                       "ou suspensões do tribunal — confira sempre.")
        aviso.setWordWrap(True)
        aviso.setStyleSheet("color: gray; font-size: 11px;")
        ld.addWidget(aviso)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(esq)
        split.addWidget(dir_)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

        lay = QVBoxLayout(self)
        lay.addWidget(g)
        lay.addWidget(split, 1)
        self.recarregar()
        self._mostrar(None)

    # ------------------------------------------------------------ DJEN

    def buscar_djen(self, silencioso: bool = False):
        cfg = self.janela.cfg
        client = dje.DjenClient(cfg["dje"].get("api_url") or dje.API_PADRAO)
        inicio, fim = _pydate(self.de.date()), _pydate(self.ate.date())
        oabs = []
        if self.oab.text().strip():
            oabs.append((self.oab.text().strip(), self.oab_uf.currentText()))
        if not (self.parte.text().strip() or self.processo.text().strip()):
            for extra in cfg["dje"].get("oabs_extras") or []:
                oabs.append((str(extra.get("numero", "")), extra.get("uf", "")))
        parte, proc, trib = self.parte.text().strip(), self.processo.text().strip(), self.tribunal.text().strip()

        def tarefa():
            resultado = []
            if oabs:
                for numero, uf in oabs:
                    resultado += client.buscar(oab_numero=numero, oab_uf=uf, inicio=inicio, fim=fim,
                                               nome_parte=parte, numero_processo=proc, tribunal=trib)
            else:
                resultado = client.buscar(inicio=inicio, fim=fim, nome_parte=parte,
                                          numero_processo=proc, tribunal=trib)
            return resultado

        def ok(itens):
            self.b_buscar.setEnabled(True)
            novas = dje.salvar_intimacoes(self.janela.conn, itens)
            self.recarregar()
            msg = f"DJEN: {len(itens)} intimação(ões) no período, {novas} nova(s)."
            self.janela.status(msg)
            if novas:
                self.janela.notificar("Novas intimações", msg)
            elif not silencioso:
                QMessageBox.information(self, "DJEN", msg)

        def falha(m):
            self.b_buscar.setEnabled(True)
            self.janela.status("Falha na consulta ao DJEN.")
            if not silencioso:
                QMessageBox.critical(self, "DJEN", m)

        self.b_buscar.setEnabled(False)
        self.janela.status("Consultando o DJEN…")
        executar(tarefa, ao_concluir=ok, ao_falhar=falha)

    # ------------------------------------------------------------ lista

    def recarregar(self):
        sel = self.atual["id"] if self.atual else None
        self.linhas = dje.listar(self.janela.conn, self.so_nao_lidas.isChecked(), self.filtro.text())
        self.tabela.blockSignals(True)
        self.tabela.setRowCount(len(self.linhas))
        nao_lidas = 0
        for i, r in enumerate(self.linhas):
            valores = (_br(r["data_disponibilizacao"]), r["tribunal"], dje.formatar_cnj(r["numero_processo"] or ""),
                       r["tipo_comunicacao"], r["cliente_nome"] or "", r["prazo"] or "")
            for j, v in enumerate(valores):
                item = QTableWidgetItem(v or "")
                if not r["lida"]:
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                self.tabela.setItem(i, j, item)
            nao_lidas += 0 if r["lida"] else 1
        self.tabela.blockSignals(False)
        self.resumo.setText(f"{len(self.linhas)} intimação(ões) — {nao_lidas} não lida(s)")
        self.janela.atualizar_contador_dje()
        if sel:
            for i, r in enumerate(self.linhas):
                if r["id"] == sel:
                    self.tabela.blockSignals(True)
                    self.tabela.selectRow(i)
                    self.tabela.blockSignals(False)
                    self.atual = r
                    break

    def _selecionou(self):
        linhas = self.tabela.selectionModel().selectedRows()
        if not linhas:
            return
        r = self.linhas[linhas[0].row()]
        self._mostrar(r)
        if not r["lida"]:
            dje.marcar_lida(self.janela.conn, r["id"])
            self.recarregar()
            self._mostrar(self.atual)

    def _mostrar(self, r):
        self.atual = r
        if r is None:
            self.cabecalho.setText("Selecione uma intimação para ver o conteúdo.")
            self.texto.clear()
            return
        partes = (r["destinatarios"] or "").replace("\n", "; ")
        self.cabecalho.setText(
            f"<b>{dje.formatar_cnj(r['numero_processo'] or '')}</b> — {r['tribunal']} — {r['orgao']}<br>"
            f"{r['tipo_comunicacao']} / {r['tipo_documento']} — {r['classe']}<br>"
            f"Disponibilizada em {_br(r['data_disponibilizacao'])}<br>"
            f"Destinatários: {partes}")
        self.texto.setPlainText(r["texto"] or "")
        self.b_link.setEnabled(bool(r["link"]))
        self.b_lida.setText("Marcar como não lida" if r["lida"] else "Marcar como lida")
        self.prazo.setText(r["prazo"] or "")
        self.obs.setText(r["observacao"] or "")
        self.cliente.clear()
        self.cliente.addItem("— nenhum —", None)
        for cid, nome in self.janela.aba_clientes.nomes_clientes():
            self.cliente.addItem(nome, cid)
        idx = self.cliente.findData(r["cliente_id"])
        self.cliente.setCurrentIndex(max(idx, 0))

    # ------------------------------------------------------------ ações

    def _abrir_link(self):
        if self.atual and self.atual["link"]:
            QDesktopServices.openUrl(QUrl(self.atual["link"]))

    def _alternar_lida(self):
        if self.atual:
            dje.marcar_lida(self.janela.conn, self.atual["id"], not self.atual["lida"])
            self.recarregar()
            self._mostrar(self.atual)

    def _vincular(self):
        if not self.atual:
            return
        cid = self.cliente.currentData()
        if not cid or not self.atual["numero_processo"]:
            return
        cl.vincular_processo(self.janela.conn, self.atual["numero_processo"], cid)
        self.recarregar()
        self.janela.status("Processo vinculado ao cliente — próximas intimações serão associadas automaticamente.")

    def _calcular_prazo(self):
        if not self.atual or not self.atual["data_disponibilizacao"]:
            return
        try:
            base = date.fromisoformat(self.atual["data_disponibilizacao"][:10])
        except ValueError:
            return
        venc = dje.prazo_dias_uteis(base, self.dias_prazo.value())
        self.prazo.setText(venc.strftime("%d/%m/%Y"))

    def _salvar_anotacoes(self):
        if self.atual:
            dje.atualizar_anotacoes(self.janela.conn, self.atual["id"], self.prazo.text().strip(), self.obs.text().strip())
            self.recarregar()
            self.janela.status("Anotações salvas.")

    def exportar_csv(self):
        caminho, _ = QFileDialog.getSaveFileName(self, "Exportar intimações", "intimacoes.csv", "CSV (*.csv)")
        if not caminho:
            return
        with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["data", "tribunal", "orgao", "processo", "tipo", "cliente", "destinatarios",
                        "prazo", "observacao", "link", "texto"])
            for r in self.linhas:
                w.writerow([_br(r["data_disponibilizacao"]), r["tribunal"], r["orgao"],
                            dje.formatar_cnj(r["numero_processo"] or ""), r["tipo_comunicacao"],
                            r["cliente_nome"] or "", (r["destinatarios"] or "").replace("\n", "; "),
                            r["prazo"] or "", r["observacao"] or "", r["link"] or "", r["texto"] or ""])
        self.janela.status(f"Exportado para {caminho}")
