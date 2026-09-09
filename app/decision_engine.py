"""Moteur de décision : synthétise audit + MES + environnement ANFR + FTTO
en une recommandation d'arbitrage 4G.

Rappel des règles métier (cf. échanges avec le porteur du projet) :
- Ces sites sont envoyés au moteur PARCE QUE leur 4G est déjà mauvaise :
  l'objectif est toujours de trouver une solution de contournement
  concrète (4G autre opérateur / FTTO / Starlink) — jamais de laisser un
  dossier sans recommandation actionnable.
- La 4G est toujours un lien de secours d'une FTTH déjà en place : on ne
  recommande jamais de FTTH.
- Opérateurs jamais utilisés : Free (aucun partenariat Linkt/Adista).
- Si un opérateur donne un signal correct en MES : pas d'arbitrage, on
  garde ce lien (seul cas où le verdict n'est pas une des 3 technos).
- Si tous les opérateurs testés sont mauvais/moyens mais que l'audit ou
  l'environnement ANFR indique une zone a priori bien couverte : on
  calcule quand même une recommandation concrète, mais on signale en plus
  (investigation_suspectee) qu'un problème d'installation (pose d'antenne,
  câble, choix d'opérateur) est possible et vaut la peine d'être vérifié
  avant d'engager le changement.
- La recommandation d'un autre opérateur 4G est justifiée par
  l'environnement radio ANFR (site le plus proche, distance, système) et
  limitée aux opérateurs disponibles via le prestataire (Linkt :
  Orange/SFR natifs, Bouygues en option ; Adista : Orange/Bouygues
  natifs, SFR en option), sinon FTTO si éligible, sinon Starlink (sous
  réserve du critère toit dégagé + propriété du magasin — sans quoi
  Starlink reste la recommandation par défaut avec un avertissement).
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


def _anfr_map(anfr_summary: list[AnfrSiteSummary]) -> dict[str, AnfrSiteSummary]:
    return {s.operateur: s for s in anfr_summary}


def _rank_by_anfr(operators: list[str], anfr: dict[str, AnfrSiteSummary]) -> list[str]:
    def sort_key(op: str):
        summary = anfr.get(op)
        if summary and summary.distance_min_m is not None:
            return (0, summary.distance_min_m)
        if summary and summary.nb_sites:
            return (1, -summary.nb_sites)
        return (2, 0)

    return sorted(operators, key=sort_key)


def _anfr_justification(op: str, anfr: dict[str, AnfrSiteSummary]) -> Optional[str]:
    summary = anfr.get(op)
    if not summary:
        return f"Aucun site {op.upper()} recensé par l'ANFR dans la zone de recherche (à vérifier manuellement)."
    if summary.distance_min_m is not None:
        systeme_txt = f", {summary.systeme}" if summary.systeme else ""
        return (
            f"Justification ANFR : site {op.upper()} le plus proche à {round(summary.distance_min_m)} m"
            f"{systeme_txt} ({summary.nb_sites} site(s) {op.upper()} recensé(s) dans la zone)."
        )
    return f"Justification ANFR : {summary.nb_sites} site(s) {op.upper()} recensé(s) dans la zone (distance non calculée)."


def _find_alternative_operator(
    mes: MesReport, verdicts: dict[str, str], anfr_summary: list[AnfrSiteSummary]
) -> tuple[Optional[str], list[str]]:
    pool, extra = _candidate_pool(mes.prestataire)
    non_testes = [op for op in pool if op not in verdicts]
    anfr = _anfr_map(anfr_summary)
    non_testes = _rank_by_anfr(non_testes, anfr)
    if not non_testes:
        return None, []

    candidat = non_testes[0]
    notes = [_anfr_justification(candidat, anfr)]
    if candidat == extra:
        notes.append(
            f"Opérateur '{extra}' disponible via {mes.prestataire} sur demande spécifique (hors offre standard à 2 HNO)."
        )
    return candidat, notes


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

    # Aucun opérateur testé n'est satisfaisant : on cherche une solution de
    # contournement concrète dans tous les cas. Si la zone semble a priori
    # couverte (audit/ANFR), on garde le diagnostic "problème d'installation
    # possible" comme avertissement, sans jamais s'arrêter là.
    zone_couverte, raisons_zone = _zone_semble_couverte(audit, anfr_summary, anfr_available, set(verdicts))
    details = list(raisons_zone) + [f"{op} : {v}" for op, v in verdicts.items()]
    if zone_couverte:
        details.append(
            "Pistes à vérifier sur site en parallèle : pose d'antenne non conforme (faux-plafond, sous-sol, "
            "mauvaise orientation), déperdition de signal sur un câble coaxial trop long ou mal serti, "
            "antenne posée en intérieur au lieu d'extérieur, connecteur défectueux."
        )
    avertissement = (
        "⚠ La zone semble a priori couverte en 4G (audit et/ou ANFR) : un problème d'installation est possible, "
        "à vérifier sur site en parallèle de la recommandation ci-dessous. "
        if zone_couverte
        else ""
    )

    candidat_operateur, notes_candidat = _find_alternative_operator(mes, verdicts, anfr_summary)
    if candidat_operateur:
        details.extend(notes_candidat)
        return Recommendation(
            technologie="4G_autre_operateur",
            resume=f"{avertissement}Recommandation : tester {candidat_operateur.upper()}, non testé lors de cette MES.",
            details=details,
            operateur_recommande=candidat_operateur,
            prestataire_recommande=mes.prestataire,
            investigation_suspectee=zone_couverte,
        )

    if ftto.eligible:
        offre_txt = f" ({ftto.offre_recommandee})" if ftto.offre_recommandee else ""
        prix_txt = f" — {ftto.prix_mensuel}" if ftto.prix_mensuel else ""
        details.append(ftto.detail or "Site trouvé éligible dans le fichier FTTO fourni.")
        return Recommendation(
            technologie="FTTO",
            resume=f"{avertissement}Aucun opérateur 4G disponible ne convient et le site est éligible FTTO"
            f"{offre_txt}{prix_txt} : basculer le lien de secours sur FTTO.",
            details=details,
            investigation_suspectee=zone_couverte,
        )

    if ftto.eligible is None:
        details.append(
            ftto.detail or "Éligibilité FTTO non déterminée automatiquement : à vérifier manuellement dans le fichier."
        )
    else:
        details.append(ftto.detail or "Site non éligible FTTO d'après le fichier fourni.")

    if toit_degage_et_proprietaire is False:
        details.append(
            "Critère toit dégagé + propriété du magasin NON rempli : Starlink non installable en l'état "
            "(fréquent sur Carrefour City/Express en centre-ville ou copropriété) — solution à valider "
            "au cas par cas (mât, toit voisin, extension de bail...) avant de confirmer."
        )
    elif toit_degage_et_proprietaire is True:
        details.append("Critère toit dégagé + propriété du magasin confirmé : Starlink installable.")
    else:
        details.append(
            "Critère Starlink (toit dégagé + propriété du magasin) non renseigné : à confirmer manuellement avant validation."
        )

    return Recommendation(
        technologie="Starlink",
        resume=f"{avertissement}Aucune 4G alternative ni FTTO viable : recommandation Starlink "
        f"({config.STARLINK_MONTHLY_PRICE_EUR} €/mois).",
        details=details,
        investigation_suspectee=zone_couverte,
    )
