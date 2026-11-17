from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import google_ads as ga
from .workers import executar

# Modelos informativos, em conformidade com o Provimento OAB 205/2021
# (sem preço, promessa de resultado ou apelo mercantil).
MODELOS = {
    "Trabalhista": {
        "palavras": ["advogado trabalhista", "advogado trabalhista rio de janeiro", "rescisão trabalhista",
                     "verbas rescisórias", "horas extras advogado", "demissão sem justa causa"],
        "titulos": ["Advogado Trabalhista no RJ", "Direitos Trabalhistas", "Orientação Jurídica",
                    "Rescisão e Verbas Rescisórias", "Gomes Advogados", "Atendimento no Rio de Janeiro",
                    "Agende uma Consulta"],
        "descricoes": ["Orientação jurídica em Direito do Trabalho: rescisão, horas extras e FGTS.",
                       "Escritório de advocacia no Rio de Janeiro. Atendimento presencial e online."],
    },
    "Cível / Consumidor": {
        "palavras": ["advogado cível", "advogado direito do consumidor", "advogado rio de janeiro",
                     "indenização danos morais advogado", "cobrança indevida advogado"],
        "titulos": ["Advogado Cível no RJ", "Direito do Consumidor", "Gomes Advogados",
                    "Orientação Jurídica", "Atendimento Online e no RJ", "Agende uma Consulta"],
        "descricoes": ["Atuação em Direito Civil e do Consumidor. Conheça seus direitos.",
                       "Escritório de advocacia no Rio de Janeiro. Atendimento presencial e online."],
    },
    "Previdenciário": {
        "palavras": ["advogado previdenciário", "aposentadoria advogado", "benefício inss negado",
                     "revisão de aposentadoria", "auxílio doença advogado"],
        "titulos": ["Advogado Previdenciário RJ", "Aposentadoria e INSS", "Gomes Advogados",
                    "Orientação Previdenciária", "Benefício Negado pelo INSS", "Agende uma Consulta"],
        "descricoes": ["Orientação em aposentadorias, revisões e benefícios do INSS.",
                       "Escritório de advocacia no Rio de Janeiro. Atendimento presencial e online."],
    },
    "Família": {
        "palavras": ["advogado de família", "advogado divórcio", "pensão alimentícia advogado",
                     "guarda de filhos advogado", "inventário advogado"],
        "titulos": ["Advogado de Família no RJ", "Divórcio e Pensão", "Gomes Advogados",
                    "Orientação Jurídica", "Guarda e Inventário", "Agende uma Consulta"],
        "descricoes": ["Atuação em divórcio, guarda, pensão alimentícia e inventário.",
                       "Escritório de advocacia no Rio de Janeiro. Atendimento presencial e online."],
    },
}


def _linhas(txt: str) -> list[str]:
    return [linha.strip() for linha in txt.splitlines() if linha.strip()]


class AdsTab(QWidget):
    def __init__(self, janela):
        super().__init__()
        self.janela = janela
        self.campanhas: list[dict] = []

        # ---- campanhas existentes
        self.periodo = QComboBox()
        for rot, val in (("Últimos 7 dias", "LAST_7_DAYS"), ("Últimos 30 dias", "LAST_30_DAYS"),
                         ("Este mês", "THIS_MONTH"), ("Mês passado", "LAST_MONTH"), ("Hoje", "TODAY")):
            self.periodo.addItem(rot, val)
        self.periodo.setCurrentIndex(1)
        self.b_atualizar = QPushButton("Atualizar")
        self.b_atualizar.clicked.connect(self.atualizar)
        self.b_ativar = QPushButton("Ativar")
        self.b_ativar.clicked.connect(lambda: self._status(True))
        self.b_pausar = QPushButton("Pausar")
        self.b_pausar.clicked.connect(lambda: self._status(False))
        self.tabela = QTableWidget(0, 9)
        self.tabela.setHorizontalHeaderLabels(["Campanha", "Status", "Orç./dia", "Impressões", "Cliques",
                                               "CTR", "CPC médio", "Custo", "Conversões"])
        self.tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabela.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabela.setSelectionMode(QTableWidget.SingleSelection)
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela.verticalHeader().setVisible(False)
        self.totais = QLabel()

        g1 = QGroupBox("Campanhas no Google Ads")
        l1 = QVBoxLayout(g1)
        barra = QHBoxLayout()
        barra.addWidget(QLabel("Período"))
        barra.addWidget(self.periodo)
        barra.addWidget(self.b_atualizar)
        barra.addStretch()
        barra.addWidget(self.b_ativar)
        barra.addWidget(self.b_pausar)
        l1.addLayout(barra)
        l1.addWidget(self.tabela)
        l1.addWidget(self.totais)

        # ---- nova campanha
        self.modelo = QComboBox()
        self.modelo.addItem("— escolher modelo —")
        self.modelo.addItems(list(MODELOS))
        self.modelo.currentTextChanged.connect(self._aplicar_modelo)
        self.nome = QLineEdit(placeholderText="Ex.: Trabalhista - RJ - Pesquisa")
        self.orcamento = QDoubleSpinBox(prefix="R$ ", minimum=1, maximum=100000, value=30, decimals=2)
        self.cpc = QDoubleSpinBox(prefix="R$ ", minimum=0.1, maximum=500, value=3, decimals=2)
        self.url = QLineEdit(janela.cfg["escritorio"].get("site", ""), placeholderText="https://seusite.com.br")
        self.locais = QLineEdit("Rio de Janeiro", placeholderText="Separe por vírgula: Rio de Janeiro, Niterói")
        self.correspondencia = QComboBox()
        for rot, val in (("Frase", "PHRASE"), ("Exata", "EXACT"), ("Ampla", "BROAD")):
            self.correspondencia.addItem(rot, val)
        self.palavras = QPlainTextEdit(placeholderText="Uma palavra-chave por linha")
        self.titulos = QPlainTextEdit(placeholderText=f"3 a 15 títulos, um por linha (máx. {ga.LIMITE_TITULO} caracteres)")
        self.descricoes = QPlainTextEdit(placeholderText=f"2 a 4 descrições, uma por linha (máx. {ga.LIMITE_DESCRICAO} caracteres)")
        for w in (self.palavras, self.titulos, self.descricoes, self.url):
            w.textChanged.connect(self._previa)
        self.previa = QLabel()
        self.previa.setWordWrap(True)
        self.previa.setTextFormat(Qt.RichText)
        self.previa.setStyleSheet("border: 1px solid #ccc; border-radius: 6px; padding: 8px; background: palette(base);")
        self.alertas = QLabel()
        self.alertas.setWordWrap(True)
        self.b_criar = QPushButton("Criar campanha (pausada)")
        self.b_criar.clicked.connect(self.criar)

        g2 = QGroupBox("Novo anúncio de pesquisa")
        l2 = QHBoxLayout(g2)
        form = QFormLayout()
        form.addRow("Modelo", self.modelo)
        form.addRow("Nome da campanha", self.nome)
        form.addRow("Orçamento diário", self.orcamento)
        form.addRow("CPC máximo", self.cpc)
        form.addRow("Página de destino", self.url)
        form.addRow("Locais", self.locais)
        form.addRow("Correspondência", self.correspondencia)
        form.addRow("Palavras-chave", self.palavras)
        l2.addLayout(form, 1)
        col = QVBoxLayout()
        col.addWidget(QLabel("Títulos"))
        col.addWidget(self.titulos)
        col.addWidget(QLabel("Descrições"))
        col.addWidget(self.descricoes)
        col.addWidget(QLabel("Prévia"))
        col.addWidget(self.previa)
        col.addWidget(self.alertas)
        col.addWidget(self.b_criar)
        l2.addLayout(col, 1)

        split = QSplitter(Qt.Vertical)
        split.addWidget(g1)
        split.addWidget(g2)
        split.setStretchFactor(1, 2)
        lay = QVBoxLayout(self)
        lay.addWidget(split)
        self._previa()

    def _servico(self) -> ga.GoogleAdsService | None:
        svc = ga.GoogleAdsService(self.janela.cfg["google_ads"])
        if not svc.configurado:
            QMessageBox.information(self, "Google Ads",
                                    "Configure as credenciais da API em Configurações > Google Ads.\n"
                                    "Veja o passo a passo no README.")
            return None
        return svc

    # ------------------------------------------------------------ campanhas

    def atualizar(self):
        svc = self._servico()
        if not svc:
            return
        self.b_atualizar.setEnabled(False)
        self.janela.status("Carregando campanhas do Google Ads…")

        def ok(lista):
            self.b_atualizar.setEnabled(True)
            self.campanhas = lista
            self.tabela.setRowCount(len(lista))
            tot = {"impressoes": 0, "cliques": 0, "custo": 0.0, "conversoes": 0.0}
            for i, c in enumerate(lista):
                st = {"ENABLED": "Ativa", "PAUSED": "Pausada"}.get(c["status"], c["status"])
                vals = (c["nome"], st, f"R$ {c['orcamento_diario']:.2f}", f"{c['impressoes']:,}".replace(",", "."),
                        str(c["cliques"]), f"{c['ctr']:.2f}%", f"R$ {c['cpc_medio']:.2f}",
                        f"R$ {c['custo']:.2f}", f"{c['conversoes']:.1f}")
                for j, v in enumerate(vals):
                    self.tabela.setItem(i, j, QTableWidgetItem(v))
                for k in tot:
                    tot[k] += c[k]
            self.totais.setText(f"Total: {tot['impressoes']} impressões · {tot['cliques']} cliques · "
                                f"R$ {tot['custo']:.2f} investidos · {tot['conversoes']:.1f} conversões")
            self.janela.status(f"{len(lista)} campanha(s) carregada(s).")

        def falha(m):
            self.b_atualizar.setEnabled(True)
            self.janela.status("Falha no Google Ads.")
            QMessageBox.critical(self, "Google Ads", m)

        executar(svc.listar_campanhas, self.periodo.currentData(), ao_concluir=ok, ao_falhar=falha)

    def _status(self, ativar: bool):
        linhas = self.tabela.selectionModel().selectedRows()
        svc = self._servico()
        if not linhas or not svc:
            return
        camp = self.campanhas[linhas[0].row()]
        acao = "ativar" if ativar else "pausar"
        if QMessageBox.question(self, "Google Ads", f"Deseja {acao} a campanha “{camp['nome']}”?") != QMessageBox.Yes:
            return
        executar(svc.alterar_status, camp["id"], ativar, ao_concluir=lambda _: self.atualizar(),
                 ao_falhar=lambda m: QMessageBox.critical(self, "Google Ads", m))

    # ------------------------------------------------------------ nova campanha

    def _aplicar_modelo(self, nome: str):
        m = MODELOS.get(nome)
        if not m:
            return
        self.nome.setText(f"{nome.split(' /')[0]} - RJ - Pesquisa")
        self.palavras.setPlainText("\n".join(m["palavras"]))
        self.titulos.setPlainText("\n".join(m["titulos"]))
        self.descricoes.setPlainText("\n".join(m["descricoes"]))

    def _previa(self):
        tit = _linhas(self.titulos.toPlainText())
        desc = _linhas(self.descricoes.toPlainText())
        dominio = self.url.text().replace("https://", "").replace("http://", "").split("/")[0] or "seusite.com.br"
        titulo = " | ".join(tit[:3]) or "Título 1 | Título 2 | Título 3"
        descricao = " ".join(desc[:2]) or "Descrição do anúncio."
        self.previa.setText(f"<small><b>Patrocinado</b> · {dominio}</small><br>"
                            f"<span style='color:#1a0dab;font-size:15px'>{titulo}</span><br>"
                            f"<span>{descricao}</span>")
        problemas = [f"⚠ Título com {len(t)} caracteres (máx. {ga.LIMITE_TITULO}): {t}"
                     for t in tit if len(t) > ga.LIMITE_TITULO]
        problemas += [f"⚠ Descrição com {len(d)} caracteres (máx. {ga.LIMITE_DESCRICAO})"
                      for d in desc if len(d) > ga.LIMITE_DESCRICAO]
        problemas += ["⚠ OAB: " + a for a in ga.verificar_conformidade_oab(tit + desc)]
        self.alertas.setText("<br>".join(problemas))
        self.alertas.setStyleSheet("color: #b00020;" if problemas else "")

    def criar(self):
        nova = ga.NovaCampanha(
            nome=self.nome.text().strip(),
            orcamento_diario=self.orcamento.value(),
            url_final=self.url.text().strip(),
            palavras_chave=_linhas(self.palavras.toPlainText()),
            titulos=_linhas(self.titulos.toPlainText()),
            descricoes=_linhas(self.descricoes.toPlainText()),
            locais=[x.strip() for x in self.locais.text().split(",") if x.strip()],
            cpc_maximo=self.cpc.value(),
            correspondencia=self.correspondencia.currentData(),
        )
        try:
            alertas = nova.validar()
        except ga.GoogleAdsErro as e:
            QMessageBox.warning(self, "Verifique o anúncio", str(e))
            return
        if alertas:
            r = QMessageBox.warning(self, "Atenção — Provimento OAB 205/2021",
                                    "Possíveis termos vedados:\n\n" + "\n".join(alertas) + "\n\nCriar mesmo assim?",
                                    QMessageBox.Yes | QMessageBox.No)
            if r != QMessageBox.Yes:
                return
        svc = self._servico()
        if not svc:
            return
        self.b_criar.setEnabled(False)
        self.janela.status("Criando campanha no Google Ads…")

        def ok(campaign_id):
            self.b_criar.setEnabled(True)
            self.janela.conn.execute(
                "INSERT INTO campanhas (google_id, nome, orcamento_diario, palavras_chave, url_final) VALUES (?,?,?,?,?)",
                (campaign_id, nova.nome, nova.orcamento_diario, "\n".join(nova.palavras_chave), nova.url_final))
            self.janela.conn.commit()
            QMessageBox.information(self, "Google Ads",
                                    f"Campanha criada (ID {campaign_id}) e deixada PAUSADA.\n"
                                    "Revise e ative quando quiser começar a veicular.")
            self.atualizar()

        def falha(m):
            self.b_criar.setEnabled(True)
            self.janela.status("Falha ao criar campanha.")
            QMessageBox.critical(self, "Google Ads", m)

        executar(svc.criar_campanha, nova, ao_concluir=ok, ao_falhar=falha)
