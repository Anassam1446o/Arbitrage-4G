from pathlib import Path

from app.decision_engine import arbitrate
from app.models import AuditReport, FttoEligibility, MesReport, OperatorReading
from app.parsers.audit_parser import parse_audit
from app.parsers.mes_parser import parse_mes

FIXTURES = Path(__file__).parent / "fixtures"


def _no_ftto():
    return FttoEligibility(eligible=None, trouve=False)


def test_recommends_untested_operator_when_zone_looks_bad():
    audit = parse_audit(str(FIXTURES / "audit_linkt_sample.pdf"))
    mes = parse_mes(str(FIXTURES / "mes_linkt_sample.pdf"))
    reco = arbitrate(audit, mes, [], anfr_available=False, ftto=_no_ftto())
    assert reco.technologie == "4G_autre_operateur"
    assert reco.operateur_recommande == "bouygues"


def test_adista_recommends_sfr_when_orange_and_bouygues_bad():
    audit = parse_audit(str(FIXTURES / "audit_adista_sample.pdf"))
    mes = parse_mes(str(FIXTURES / "mes_adista_sample.pdf"))
    reco = arbitrate(audit, mes, [], anfr_available=False, ftto=_no_ftto())
    assert reco.technologie == "4G_autre_operateur"
    assert reco.operateur_recommande == "sfr"


def test_falls_back_to_starlink_when_no_operator_left_and_no_ftto():
    mes = MesReport(
        prestataire="linkt",
        lectures=[
            OperatorReading(operateur="orange", qualite_signal="mauvais"),
            OperatorReading(operateur="sfr", qualite_signal="mauvais"),
            OperatorReading(operateur="bouygues", qualite_signal="mauvais"),
        ],
    )
    audit = AuditReport()
    ftto = FttoEligibility(eligible=False, trouve=True)
    reco = arbitrate(audit, mes, [], anfr_available=False, ftto=ftto, toit_degage_et_proprietaire=True)
    assert reco.technologie == "Starlink"


def test_suspects_installation_issue_when_zone_looks_covered():
    audit = parse_audit(str(FIXTURES / "audit_linkt_sample.pdf"))
    mes = parse_mes(str(FIXTURES / "mes_linkt_sample.pdf"))
    from app.models import AnfrSiteSummary

    anfr_summary = [AnfrSiteSummary(operateur="sfr", nb_sites=5), AnfrSiteSummary(operateur="orange", nb_sites=3)]
    reco = arbitrate(audit, mes, anfr_summary, anfr_available=True, ftto=_no_ftto())
    assert reco.technologie == "Investiguer"
