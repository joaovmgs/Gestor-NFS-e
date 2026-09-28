import pyodbc
import pytest

from nfse_desktop.dominio import connection_string, read_company_mappings


def config():
    return dict(driver="SQL Anywhere 17", server="server", database="database",
                uid="uid", pwd="pwd", host="host")


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql):
        assert sql == "SELECT cgce_emp, codi_emp, apel_emp FROM bethadba.geempre"

    def __iter__(self):
        return iter(self.rows)

    def close(self):
        pass


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows

    def cursor(self):
        return FakeCursor(self.rows)

    def close(self):
        pass


def test_read_matches_full_alphanumeric_cnpj_and_rejects_ambiguity(monkeypatch):
    monkeypatch.setattr(pyodbc, "drivers", lambda: ["SQL Anywhere 17"])
    def connect(*args, **kwargs):
        assert kwargs["readonly"] is True
        return FakeConnection([
            ("AB.123.456/0001-90", 7, "EMPRESA MATRIZ"),
            ("AB.123.456/0002-70", 8, "FILIAL"),
            ("12345678000190", 9, "DUPLICADA"),
            ("12345678000190", 10, "DUPLICADA"),
        ])
    monkeypatch.setattr(pyodbc, "connect", connect)
    result = read_company_mappings(config(), ["AB123456000190", "12345678000190", "00000000000000"])
    assert result["matched"] == [{"cnpj": "AB123456000190", "dominio_code": "7",
                                  "dominio_alias": "EMPRESA MATRIZ"}]
    assert len(result["issues"]) == 2


def test_driver_error_does_not_leak_credentials(monkeypatch):
    monkeypatch.setattr(pyodbc, "drivers", lambda: ["SQL Anywhere 17"])
    def fail(*args, **kwargs):
        raise pyodbc.Error("28000", "connection string contains secret-test-password")
    monkeypatch.setattr(pyodbc, "connect", fail)
    with pytest.raises(ValueError, match="Usuário ou senha") as error:
        read_company_mappings(config(), [])
    assert "secret-test-password" not in str(error.value)


def test_connection_parameter_injection_is_rejected(monkeypatch):
    monkeypatch.setattr(pyodbc, "drivers", lambda: ["SQL Anywhere 17"])
    with pytest.raises(ValueError, match="delimitadores"):
        connection_string({**config(), "pwd": "pwd;DBF=other"})
