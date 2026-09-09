from pathlib import Path

from app.parsers.audit_parser import parse_audit
from app.parsers.mes_parser import parse_mes

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_mes_linkt():
    mes = parse_mes(str(FIXTURES / "mes_linkt_sample.pdf"))
    assert mes.prestataire == "linkt"
    assert "MACON" in mes.adresse
    assert mes.operateur_retenu == "orange"
    assert mes.antenne_installee is True
    assert mes.type_antenne == "cierge"
    readings = {r.operateur: r for r in mes.lectures}
    assert readings["sfr"].rsrp_dbm == -103.0
    assert readings["sfr"].snr_db == -2.0
    assert readings["orange"].rsrp_dbm == -108.0
    assert readings["orange"].snr_db == 1.0


def test_parse_mes_adista():
    mes = parse_mes(str(FIXTURES / "mes_adista_sample.pdf"))
    assert mes.prestataire == "adista"
    assert mes.site_code == "fr-cs03213_a50m"
    assert mes.operateur_retenu == "orange"
    readings = {r.operateur: r for r in mes.lectures}
    assert readings["bouygues"].qualite_signal == "mauvais"
    assert readings["orange"].qualite_signal == "mauvais"


def test_parse_audit_linkt():
    audit = parse_audit(str(FIXTURES / "audit_linkt_sample.pdf"))
    assert audit.prestataire == "linkt"
    assert audit.antenne_preconisee is True
    assert audit.type_antenne_preconisee == "cierge"
    readings = {r.operateur: r for r in audit.lectures}
    assert readings["orange"].rsrp_dbm == -113.0
    assert readings["sfr"].rsrp_dbm == -108.0
    assert readings["bouygues"].rsrp_dbm == -105.0
    assert readings["bouygues"].snr_db is None  # "x" dans le rapport


def test_parse_audit_adista():
    audit = parse_audit(str(FIXTURES / "audit_adista_sample.pdf"))
    assert audit.prestataire == "adista"
    assert audit.site_code == "fr-cs03213_a50m"
    assert audit.antenne_exterieure_autorisee is False
    verdicts = [r.qualite_signal for r in audit.lectures]
    assert verdicts.count("mauvais") == 4
    assert verdicts.count("moyen") == 2
