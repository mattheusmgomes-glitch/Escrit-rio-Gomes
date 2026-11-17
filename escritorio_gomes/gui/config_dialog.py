from __future__ import annotations

import copy
import json

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)


class ConfigDialog(QDialog):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurações")
        self.resize(620, 460)
        self.cfg = copy.deepcopy(cfg)
        self.w: dict[tuple[str, str], QWidget] = {}

        abas = QTabWidget()
        abas.addTab(self._pagina("escritorio", [
            ("nome", "Nome do escritório"), ("advogado", "Advogado(a)"),
            ("oab_numero", "Nº OAB"), ("oab_uf", "UF da OAB"), ("site", "Site (página de destino)"),
        ]), "Escritório")

        p_dje = self._pagina("dje", [("api_url", "URL da API DJEN")])
        f = p_dje.layout()
        dias = QSpinBox(minimum=1, maximum=90, value=int(self.cfg["dje"].get("dias_retroativos", 7)))
        self.w[("dje", "dias_retroativos")] = dias
        f.addRow("Dias retroativos padrão", dias)
        auto = QCheckBox("Buscar novas intimações ao abrir o sistema")
        auto.setChecked(bool(self.cfg["dje"].get("buscar_ao_abrir", True)))
        self.w[("dje", "buscar_ao_abrir")] = auto
        f.addRow(auto)
        extras = QPlainTextEdit(json.dumps(self.cfg["dje"].get("oabs_extras", []), ensure_ascii=False))
        extras.setFixedHeight(60)
        self.w[("dje", "oabs_extras")] = extras
        f.addRow("OABs adicionais (JSON)", extras)
        f.addRow(QLabel('Ex.: [{"numero": "123456", "uf": "RJ"}] — para monitorar colegas do escritório.'))
        abas.addTab(p_dje, "DJE")

        p_ads = self._pagina("google_ads", [
            ("developer_token", "Developer token"), ("client_id", "OAuth Client ID"),
            ("client_secret", "OAuth Client Secret"), ("refresh_token", "Refresh token"),
            ("customer_id", "ID da conta (xxx-xxx-xxxx)"), ("login_customer_id", "ID da MCC (opcional)"),
        ], segredos={"developer_token", "client_secret", "refresh_token"})
        p_ads.layout().addRow(QLabel("Veja no README como obter essas credenciais."))
        abas.addTab(p_ads, "Google Ads")

        p_plat = self._pagina("plataforma", [
            ("base_url", "URL base da API"), ("endpoint_clientes", "Endpoint de clientes"),
            ("auth_header", "Cabeçalho do token"), ("auth_prefix", "Prefixo do token"),
            ("token", "Token de API"), ("campo_id_resposta", "Campo do ID na resposta"),
        ], segredos={"token"})
        f = p_plat.layout()
        ativo = QCheckBox("Enviar clientes para a plataforma do escritório")
        ativo.setChecked(bool(self.cfg["plataforma"].get("ativo")))
        self.w[("plataforma", "ativo")] = ativo
        f.insertRow(0, ativo)
        mapa = QPlainTextEdit(json.dumps(self.cfg["plataforma"].get("mapeamento", {}), ensure_ascii=False, indent=1))
        mapa.setFixedHeight(90)
        self.w[("plataforma", "mapeamento")] = mapa
        f.addRow("Mapeamento de campos (JSON)", mapa)
        f.addRow(QLabel('Ex.: {"nome": "name", "cpf_cnpj": "document", "telefone": "phone"}'))
        abas.addTab(p_plat, "Plataforma")

        botoes = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        botoes.accepted.connect(self._salvar)
        botoes.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(abas)
        lay.addWidget(botoes)

    def _pagina(self, secao: str, campos: list[tuple[str, str]], segredos: set[str] = frozenset()) -> QWidget:
        pg = QWidget()
        f = QFormLayout(pg)
        for chave, rotulo in campos:
            e = QLineEdit(str(self.cfg[secao].get(chave, "")))
            if chave in segredos:
                e.setEchoMode(QLineEdit.PasswordEchoOnEdit)
            self.w[(secao, chave)] = e
            f.addRow(rotulo, e)
        return pg

    def _salvar(self):
        for (secao, chave), w in self.w.items():
            if isinstance(w, QCheckBox):
                self.cfg[secao][chave] = w.isChecked()
            elif isinstance(w, QSpinBox):
                self.cfg[secao][chave] = w.value()
            elif isinstance(w, QPlainTextEdit):
                try:
                    self.cfg[secao][chave] = json.loads(w.toPlainText() or "null") or (
                        {} if chave == "mapeamento" else [])
                except json.JSONDecodeError as e:
                    QMessageBox.warning(self, "JSON inválido", f"{chave}: {e}")
                    return
            else:
                self.cfg[secao][chave] = w.text().strip()
        self.accept()
