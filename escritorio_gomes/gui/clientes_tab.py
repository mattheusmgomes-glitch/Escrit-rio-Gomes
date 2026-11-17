from __future__ import annotations

import csv

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from .. import clientes as cl
from ..plataforma import PlataformaClient
from .workers import executar


class ClientesTab(QWidget):
    def __init__(self, janela):
        super().__init__()
        self.janela = janela
        self.atual: cl.Cliente | None = None
        self.lista: list[cl.Cliente] = []

        # ---- lista
        self.busca = QLineEdit(placeholderText="Buscar por nome, CPF/CNPJ, e-mail, telefone ou cidade…")
        self.busca.textChanged.connect(self.recarregar)
        self.tabela = QTableWidget(0, 4)
        self.tabela.setHorizontalHeaderLabels(["Nome", "CPF/CNPJ", "Telefone", "Plataforma"])
        self.tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabela.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabela.setSelectionMode(QTableWidget.SingleSelection)
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.itemSelectionChanged.connect(self._selecionou)
        self.total = QLabel()
        btn_export = QPushButton("Exportar CSV")
        btn_export.clicked.connect(self.exportar_csv)

        esq = QWidget()
        le = QVBoxLayout(esq)
        le.addWidget(self.busca)
        le.addWidget(self.tabela)
        rod = QHBoxLayout()
        rod.addWidget(self.total)
        rod.addStretch()
        rod.addWidget(btn_export)
        le.addLayout(rod)

        # ---- formulário
        self.campos: dict[str, QWidget] = {}
        self.tipo = self._combo("tipo", ["PF", "PJ"])
        self.tipo.currentTextChanged.connect(self._ajustar_tipo)
        self._linha("nome")
        self._linha("cpf_cnpj")
        self._linha("rg")
        self._linha("data_nascimento", "DD/MM/AAAA")
        self._combo("estado_civil", cl.ESTADOS_CIVIS)
        self._linha("profissao")
        self._linha("email")
        self._linha("telefone", "(21) 99999-9999")
        self._linha("cep", "00000-000")
        self.campos["cep"].editingFinished.connect(self._cep_auto)
        self._linha("logradouro")
        self._linha("numero")
        self._linha("complemento")
        self._linha("bairro")
        self._linha("cidade")
        self._combo("uf", cl.UFS)
        self._combo("area", [""] + cl.AREAS)
        self._combo("origem", [""] + cl.ORIGENS)
        obs = QTextEdit()
        obs.setFixedHeight(70)
        self.campos["observacoes"] = obs

        g_pessoal = QGroupBox("Dados do cliente")
        f1 = QFormLayout(g_pessoal)
        self.lbl_doc = QLabel("CPF")
        self.lbl_nome = QLabel("Nome completo *")
        f1.addRow("Tipo", self.tipo)
        f1.addRow(self.lbl_nome, self.campos["nome"])
        f1.addRow(self.lbl_doc, self.campos["cpf_cnpj"])
        f1.addRow("RG", self.campos["rg"])
        f1.addRow("Nascimento", self.campos["data_nascimento"])
        f1.addRow("Estado civil", self.campos["estado_civil"])
        f1.addRow("Profissão", self.campos["profissao"])
        f1.addRow("E-mail", self.campos["email"])
        f1.addRow("Telefone/WhatsApp", self.campos["telefone"])

        g_end = QGroupBox("Endereço")
        f2 = QFormLayout(g_end)
        cep_linha = QHBoxLayout()
        cep_linha.addWidget(self.campos["cep"])
        btn_cep = QPushButton("Buscar CEP")
        btn_cep.clicked.connect(self._cep_auto)
        cep_linha.addWidget(btn_cep)
        f2.addRow("CEP", cep_linha)
        f2.addRow("Logradouro", self.campos["logradouro"])
        f2.addRow("Número", self.campos["numero"])
        f2.addRow("Complemento", self.campos["complemento"])
        f2.addRow("Bairro", self.campos["bairro"])
        f2.addRow("Cidade", self.campos["cidade"])
        f2.addRow("UF", self.campos["uf"])

        g_caso = QGroupBox("Atendimento")
        f3 = QFormLayout(g_caso)
        f3.addRow("Área", self.campos["area"])
        f3.addRow("Como chegou", self.campos["origem"])
        f3.addRow("Observações", obs)

        self.status_sync = QLabel()
        self.status_sync.setWordWrap(True)
        b_novo = QPushButton("Novo")
        b_novo.clicked.connect(self.novo)
        b_salvar = QPushButton("Salvar")
        b_salvar.setDefault(True)
        b_salvar.clicked.connect(self.salvar)
        self.b_enviar = QPushButton("Salvar e enviar à plataforma")
        self.b_enviar.clicked.connect(self.enviar_plataforma)
        b_excluir = QPushButton("Excluir")
        b_excluir.clicked.connect(self.excluir)
        botoes = QHBoxLayout()
        for b in (b_novo, b_salvar, self.b_enviar, b_excluir):
            botoes.addWidget(b)

        dir_ = QWidget()
        ld = QVBoxLayout(dir_)
        colunas = QHBoxLayout()
        c1 = QVBoxLayout()
        c1.addWidget(g_pessoal)
        c1.addStretch()
        c2 = QVBoxLayout()
        c2.addWidget(g_end)
        c2.addWidget(g_caso)
        colunas.addLayout(c1)
        colunas.addLayout(c2)
        ld.addLayout(colunas)
        ld.addWidget(self.status_sync)
        ld.addLayout(botoes)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(esq)
        split.addWidget(dir_)
        split.setSizes([480, 880])
        lay = QVBoxLayout(self)
        lay.addWidget(split)

        self.recarregar()
        self.novo()

    # ------------------------------------------------------------ helpers de UI

    def _linha(self, nome: str, placeholder: str = "") -> QLineEdit:
        w = QLineEdit(placeholderText=placeholder)
        self.campos[nome] = w
        return w

    def _combo(self, nome: str, itens: list[str]) -> QComboBox:
        w = QComboBox()
        w.addItems(itens)
        self.campos[nome] = w
        return w

    def _ajustar_tipo(self, tipo: str):
        pj = tipo == "PJ"
        self.lbl_doc.setText("CNPJ" if pj else "CPF")
        self.lbl_nome.setText("Razão social *" if pj else "Nome completo *")

    def _valor(self, nome: str) -> str:
        w = self.campos[nome]
        if isinstance(w, QComboBox):
            return w.currentText()
        if isinstance(w, QTextEdit):
            return w.toPlainText().strip()
        return w.text().strip()

    def _definir(self, nome: str, valor: str):
        w = self.campos[nome]
        valor = valor or ""
        if isinstance(w, QComboBox):
            i = w.findText(valor)
            w.setCurrentIndex(i if i >= 0 else 0)
        elif isinstance(w, QTextEdit):
            w.setPlainText(valor)
        else:
            w.setText(valor)

    # ------------------------------------------------------------ ações

    def recarregar(self):
        self.lista = cl.listar(self.janela.conn, self.busca.text())
        self.tabela.blockSignals(True)
        self.tabela.setRowCount(len(self.lista))
        for i, c in enumerate(self.lista):
            sync = "✔ enviado" if c.plataforma_id else "—"
            for j, v in enumerate((c.nome, c.cpf_cnpj, c.telefone, sync)):
                self.tabela.setItem(i, j, QTableWidgetItem(v or ""))
        self.tabela.blockSignals(False)
        self.total.setText(f"{len(self.lista)} cliente(s)")

    def _selecionou(self):
        linhas = self.tabela.selectionModel().selectedRows()
        if linhas:
            self.carregar(self.lista[linhas[0].row()])

    def carregar(self, c: cl.Cliente):
        self.atual = c
        for nome in cl.CAMPOS_EDITAVEIS:
            self._definir(nome, getattr(c, nome))
        if c.plataforma_id:
            self.status_sync.setText(f"Na plataforma: ID {c.plataforma_id} (enviado em {c.sincronizado_em})")
        else:
            self.status_sync.setText("Ainda não enviado à plataforma do escritório.")

    def novo(self):
        self.atual = None
        self.tabela.clearSelection()
        for nome in cl.CAMPOS_EDITAVEIS:
            self._definir(nome, "")
        self._definir("tipo", "PF")
        self._definir("uf", self.janela.cfg["escritorio"].get("oab_uf", ""))
        self.status_sync.setText("Novo cadastro.")
        self.campos["nome"].setFocus()

    def _coletar(self) -> cl.Cliente:
        dados = {n: self._valor(n) for n in cl.CAMPOS_EDITAVEIS}
        c = cl.Cliente(**dados)
        if self.atual:
            c.id = self.atual.id
            c.plataforma_id = self.atual.plataforma_id
        return c

    def salvar(self) -> cl.Cliente | None:
        try:
            salvo = cl.salvar(self.janela.conn, self._coletar())
        except cl.ValidacaoErro as e:
            QMessageBox.warning(self, "Verifique os dados", str(e))
            return None
        self.recarregar()
        self._selecionar_id(salvo.id)
        self.janela.status(f"Cliente “{salvo.nome}” salvo.")
        return salvo

    def _selecionar_id(self, cid: int):
        for i, c in enumerate(self.lista):
            if c.id == cid:
                self.tabela.selectRow(i)
                self.carregar(c)
                return

    def excluir(self):
        if not self.atual:
            return
        r = QMessageBox.question(self, "Excluir cliente",
                                 f"Excluir “{self.atual.nome}” do cadastro local?\n"
                                 "(O cadastro na plataforma do escritório não é apagado.)")
        if r == QMessageBox.Yes:
            cl.excluir(self.janela.conn, self.atual.id)
            self.recarregar()
            self.novo()

    def enviar_plataforma(self):
        salvo = self.salvar()
        if not salvo:
            return
        plat = PlataformaClient(self.janela.cfg["plataforma"])
        if not plat.configurada:
            QMessageBox.information(self, "Plataforma",
                                    "Cliente salvo localmente.\n\nPara enviar à plataforma do escritório, "
                                    "configure a API em Configurações > Plataforma.")
            return
        self.b_enviar.setEnabled(False)
        self.janela.status("Enviando cliente à plataforma…")

        def ok(remoto_id):
            self.b_enviar.setEnabled(True)
            cl.marcar_sincronizado(self.janela.conn, salvo.id, remoto_id)
            self.recarregar()
            self._selecionar_id(salvo.id)
            self.janela.status(f"Cliente enviado à plataforma (ID {remoto_id}).")

        def falha(msg):
            self.b_enviar.setEnabled(True)
            self.janela.status("Falha ao enviar à plataforma.")
            QMessageBox.critical(self, "Plataforma", msg)

        executar(plat.enviar_cliente, salvo, ao_concluir=ok, ao_falhar=falha)

    def _cep_auto(self):
        cep = self._valor("cep")
        if len(cl.so_digitos(cep)) != 8:
            return

        def ok(end: dict):
            for k, v in end.items():
                if v and not (k == "complemento" and self._valor(k)):
                    self._definir(k, v)
            self.campos["numero"].setFocus()

        executar(cl.buscar_cep, cep, ao_concluir=ok,
                 ao_falhar=lambda m: self.janela.status(f"CEP: {m}"))

    def exportar_csv(self):
        caminho, _ = QFileDialog.getSaveFileName(self, "Exportar clientes", "clientes.csv", "CSV (*.csv)")
        if not caminho:
            return
        with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(cl.CAMPOS_EDITAVEIS + ("plataforma_id", "criado_em"))
            for c in cl.listar(self.janela.conn):
                w.writerow([getattr(c, k) or "" for k in cl.CAMPOS_EDITAVEIS] + [c.plataforma_id or "", c.criado_em])
        self.janela.status(f"Exportado para {caminho}")

    def nomes_clientes(self) -> list[tuple[int, str]]:
        return [(c.id, c.nome) for c in cl.listar(self.janela.conn)]
