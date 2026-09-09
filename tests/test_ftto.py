from pathlib import Path

from app.ftto import check_eligibility, extract_code_dsr
from app.ftto_pricing import build_priced_offers

DATA_FILE = Path(__file__).parent.parent / "app" / "data" / "ftto_eligibilite.csv"
PRICE_FILE = Path(__file__).parent / "fixtures" / "ftto_prix_sample.xlsx"


def test_extract_code_dsr():
    assert extract_code_dsr("FR-CS00891_7499_MACON - LACRETELLE") == "FR-CS00891"
    assert extract_code_dsr("fr-cs03213_a50m") == "FR-CS03213"
    assert extract_code_dsr("pas de code ici") is None


def test_check_eligibility_found_and_eligible():
    result = check_eligibility(str(DATA_FILE), site_code="FR-AT00023")
    assert result.trouve is True
    assert result.eligible is True
    assert "FTTO Eurofiber E0" in result.offres_eligibles_brutes
    assert result.offres_disponibles["FTTO Orange"] == "FTTO ORANGE O1"
    assert result.offres_disponibles["FTTO Axione"] == "NON"
    # "NON" ne doit pas apparaître comme offre éligible
    assert "NON" not in result.offres_eligibles_brutes


def test_check_eligibility_not_found_returns_nc():
    result = check_eligibility(str(DATA_FILE), site_code="FR-ZZ00000")
    assert result.trouve is False
    assert result.eligible is None
    assert "NC" in result.detail


def test_build_priced_offers_recommends_cheapest():
    result = check_eligibility(str(DATA_FILE), site_code="FR-AT00023")
    result = build_priced_offers(result, str(PRICE_FILE))

    assert len(result.offres_chiffrees) == len(result.offres_eligibles_brutes)
    prices = [o.prix_eur for o in result.offres_chiffrees if o.prix_eur is not None]
    assert prices == sorted(prices)  # trié du moins cher au plus cher
    assert result.offre_recommandee == result.offres_chiffrees[0].offre
    # Eurofiber E0 est l'offre la moins chère du BPU (83 €) parmi les
    # options éligibles de ce site.
    assert "Eurofiber E0" in result.offre_recommandee
    assert result.prix_mensuel is not None and "83" in result.prix_mensuel
