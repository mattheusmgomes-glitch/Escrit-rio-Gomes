import pytest

from escritorio_gomes import db


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "teste.db")
    yield c
    c.close()
