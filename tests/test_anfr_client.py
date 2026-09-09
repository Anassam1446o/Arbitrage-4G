from app.anfr_client import haversine_m, summarize_by_operator


def test_haversine_m_known_distance():
    # Paris (Tour Eiffel) -> Arc de Triomphe, ~1.7 km à vol d'oiseau.
    distance = haversine_m(48.8584, 2.2945, 48.8738, 2.2950)
    assert 1600 < distance < 1900


def test_summarize_by_operator_picks_closest_site():
    records = [
        {"adm_lb_nom": "ORANGE", "coordonnees": "48.8584, 2.2945"},
        {"adm_lb_nom": "ORANGE", "coordonnees": "48.8600, 2.2960", "emr_lb_systeme": "LTE 1800"},
        {"adm_lb_nom": "SFR", "coordonnees": "48.9000, 2.3000"},
    ]
    summary = summarize_by_operator(records, target_lat=48.8584, target_lon=2.2945)
    by_op = {s.operateur: s for s in summary}
    assert by_op["orange"].nb_sites == 2
    assert by_op["orange"].distance_min_m < 10  # le premier enregistrement est le point cible lui-même
    assert by_op["sfr"].nb_sites == 1
    assert by_op["sfr"].distance_min_m > 4000
