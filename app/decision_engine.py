"""Moteur de décision : synthétise audit + MES + environnement ANFR + FTTO
en une recommandation d'arbitrage 4G.

Rappel des règles métier (cf. échanges avec le porteur du projet) :
- La 4G est toujours un lien de secours d'une FTTH déjà en place : on ne
  recommande jamais de FTTH.
- Opérateurs jamais utilisés : Free (aucun partenariat Linkt/Adista).
- Si un opérateur donne un signal correct en MES : pas d'arbitrage, on
  garde ce lien.
- Si tous les opérateurs testés sont mauvais/moyens mais que l'audit ou
  l'environnement ANFR indique une zone a priori bien couverte : suspicion
  d'un problème d'installation (pose d'antenne, câble, choix d'opérateur)
  plutôt qu'un vrai problème de couverture -> recommandation
  "Investiguer" plutôt qu'un changement de technologie.
- Sinon (zone réellement mauvaise) : tenter un autre opérateur 4G
  disponible via le prestataire (Linkt : Orange/SFR natifs, Bouygues en
  option ; Adista : Orange/Bouygues natifs, SFR en option), sinon FTTO si
  éligible, sinon Starlink (sous réserve du critère toit dégagé +
  propriété du magasin).
"""
from __future__ import annotations

from typing import Optional

from app import config
from app.models import AnfrSiteSummary, AuditReport, FttoEligibility, MesReport, Recommendation
from app.signal_quality import classify_signal

_VERDICT_RANK = {"mauvais": 0, "moyen": 1, "bon": 2}


def _collect_verdicts(mes: MesReport) -> dict[str, str]:
    verdicts: dict[str, str] = {}
    for lecture in mes.lectures:
        verdict = lecture.qualite_signal or classify_signal(lecture.rsrp_dbm, lecture.snr_db)
        if not verdict:
            continue
        existing = verdicts.get(lecture.operateur)
        if existing is None or _VERDICT_RANK[verdict] < _VERDICT_RANK[existing]:
            verdicts[lecture.operateur] = verdict

    if mes.operateur_retenu and mes.operateur_retenu not in verdicts and mes.rsrp_routeur_dbm is not None:
        verdict = classify_signal(mes.rsrp_routeur_dbm, mes.snr_routeur_db)
        if verdict:
            verdicts[mes.operateur_retenu] = verdict

    return verdicts


def _best_verdict(verdicts: dict[str, str]) -> Optional[str]:
    if not verdicts:
        return None
    return max(verdicts.values(), key=lambda v: _VERDICT_RANK[v])


def _zone_semble_couverte(
    audit: AuditReport,
    anfr_summary: list[AnfrSiteSummary],
    anfr_available: bool,
    tested_operators: set[str],
) -> tuple[bool, list[str]]:
    raisons: list[str] = []
    couverte = False

    if anfr_available:
        anfr_map = {s.operateur: s.nb_sites for s in anfr_summary}
        for op in tested_operators:
            nb = anfr_map.get(op, 0)
            if nb >= config.ANFR_MIN_SITES_FOR_COVERAGE:
                couverte = True
                raisons.append(
                    f"ANFR recense {nb} site(s) {op} dans un rayon de {config.ANFR_SEARCH_RADIUS_M} m autour de l'adresse."
                )
    else:
        raisons.append("Données ANFR indisponibles pour cette exécution : à vérifier manuellement.")

    for lecture in audit.lectures:
        verdict = lecture.qualite_signal or classify_signal(lecture.rsrp_dbm, lecture.snr_db)
        if verdict == "bon":
            couverte = True
            raisons.append(
                f"Le rapport d'audit (prévisite) mesurait un signal correct pour {lecture.operateur} avant installation."
            )

    return couverte, raisons


def _candidate_pool(prestataire: Optional[str]) -> tuple[list[str], Optional[str]]:
    natifs = config.PROVIDER_NATIVE_OPERATORS.get(prestataire or "", [])
    extra = config.PROVIDER_EXTRA_OPERATOR.get(prestataire or "")
    pool = list(natifs) + ([extra] if extra and extra not in natifs else [])
    if not pool:
        pool = list(config.ALL_OPERATORS)
    return pool, extra


def _rank_by_anfr(operators: list[str], anfr_summary: list[AnfrSiteSummary]) -> list[str]:
    anfr_map = {s.operateur: s.nb_sites for s in anfr_summary}
    return sorted(operators, key=lambda op: -anfr_map.get(op, 0))


def _find_alternative_operator(
    mes: MesReport, verdicts: dict[str, str], anfr_summary: list[AnfrSiteSummary]
) -> tuple[Optional[str], Optional[str]]:
    pool, extra = _candidate_pool(mes.prestataire)
    non_testes = [op for op in pool if op not in verdicts]
    non_testes = _rank_by_anfr(non_testes, anfr_summary)
    if not non_testes:
        return None, None
    candidat = non_testes[0]
    prestataire_reco = mes.prestataire
    note = None
    if candidat == extra:
        note = f"opérateur '{extra}' disponible via {mes.prestataire} sur demande spécifique (hors offre standard à 2 HNO)."
    return candidat, note


def arbitrate(
    audit: AuditReport,
    mes: MesReport,
    anfr_summary: list[AnfrSiteSummary],
    anfr_available: bool,
    ftto: FttoEligibility,
    toit_degage_et_proprietaire: Optional[bool] = None,
) -> Recommendation:
    verdicts = _collect_verdicts(mes)
    best = _best_verdict(verdicts)

    if best == "bon":
        meilleur_operateur = next(op for op, v in verdicts.items() if v == "bon")
        details = [f"{op} : {v}" for op, v in verdicts.items()]
        resume = f"Signal correct obtenu avec {meilleur_operateur.upper()} : pas d'arbitrage de technologie nécessaire."
        if mes.operateur_retenu and mes.operateur_retenu != meilleur_operateur:
            resume += f" Le routeur est actuellement laissé sur {mes.operateur_retenu.upper()} : vérifier qu'il est bien basculé sur {meilleur_operateur.upper()}."
        return Recommendation(
            technologie="OK",
            resume=resume,
            details=details,
            operateur_recommande=meilleur_operateur,
        )

    zone_couverte, raisons_zone = _zone_semble_couverte(audit, anfr_summary, anfr_available, set(verdicts))

    if zone_couverte:
        details = list(raisons_zone) + [f"{op} : {v}" for op, v in verdicts.items()]
        details.append(
            "Pistes à vérifier sur site : pose d'antenne non conforme (faux-plafond, sous-sol, "
            "mauvaise orientation), déperdition de signal sur un câble coaxial trop long ou mal serti, "
            "antenne posée en intérieur au lieu d'extérieur, connecteur défectueux."
        )
        return Recommendation(
            technologie="Investiguer",
            resume="La zone semble a priori couverte en 4G (audit et/ou ANFR) mais le signal mesuré en MES "
            "reste mauvais : suspicion d'un problème d'installation plutôt qu'un vrai problème de couverture.",
            details=details,
        )

    candidat_operateur, note_candidat = _find_alternative_operator(mes, verdicts, anfr_summary)
    if candidat_operateur:
        details = list(raisons_zone) + [f"{op} : {v}" for op, v in verdicts.items()]
        if note_candidat:
            details.append(note_candidat)
        return Recommendation(
            technologie="4G_autre_operateur",
            resume=f"Aucun opérateur testé n'est satisfaisant : tester {candidat_operateur.upper()}, non testé lors de cette MES.",
            details=details,
            operateur_recommande=candidat_operateur,
            prestataire_recommande=mes.prestataire,
        )

    details = list(raisons_zone) + [f"{op} : {v}" for op, v in verdicts.items()]

    if ftto.eligible:
        details.append(ftto.detail or "Site trouvé éligible dans le fichier FTTO fourni.")
        return Recommendation(
            technologie="FTTO",
            resume="Aucun opérateur 4G ne convient et le site est éligible FTTO : basculer le lien de secours sur FTTO.",
            details=details,
        )

    if ftto.eligible is None:
        details.append(
            ftto.detail or "Éligibilité FTTO non déterminée automatiquement : à vérifier manuellement dans le fichier."
        )
    else:
        details.append(ftto.detail or "Site non éligible FTTO d'après le fichier fourni.")

    if toit_degage_et_proprietaire is True:
        details.append("Critère toit dégagé + propriété du magasin confirmé : Starlink installable.")
        return Recommendation(
            technologie="Starlink",
            resume=f"Aucune 4G alternative ni FTTO viable : recommandation Starlink ({config.STARLINK_MONTHLY_PRICE_EUR} €/mois).",
            details=details,
        )

    if toit_degage_et_proprietaire is False:
        details.append(
            "Critère toit dégagé + propriété du magasin NON rempli : Starlink non installable en l'état "
            "(fréquent sur Carrefour City/Express en centre-ville ou copropriété)."
        )
        return Recommendation(
            technologie="Investiguer",
            resume="Aucune option standard (4G alternative, FTTO, Starlink) n'est viable en l'état : cas à traiter au cas par cas.",
            details=details,
        )

    details.append(
        "Critère Starlink (toit dégagé + propriété du magasin) non renseigné : à confirmer manuellement avant validation."
    )
    return Recommendation(
        technologie="Starlink",
        resume=f"Recommandation par défaut : Starlink ({config.STARLINK_MONTHLY_PRICE_EUR} €/mois), sous réserve de confirmation du critère toit.",
        details=details,
    )
