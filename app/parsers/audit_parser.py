"""Parseur de rapports d'audit (prévisite).

Calibré sur deux formats réels observés (mêmes prestataires que
app/parsers/mes_parser.py, se référer à ce module pour le détail des
différences structurelles Linkt/Adista) :
- Linkt (Praxedo) : tableaux PDF à 2 colonnes, verdict binaire "Le test de
  réception est-il concluant ?" + relevés RSSI/RSRP/RSRQ/SNR par opérateur
  dans un bloc "Mesures Radio".
- Adista (Waycom, gabarit "Prévisite Light") : texte à plat, un verdict
  qualitatif (EXCELLENT/BIEN/MOYEN/MAUVAIS) par opérateur ET par
  emplacement testé (dans la baie, à l'extérieur du bâtiment, au meilleur
  emplacement trouvé en magasin) ; valeurs RSRP/SINR numériques
  uniquement visibles sur des captures d'écran (non extractibles sans OCR).
"""
from __future__ import annotations

import re
from typing import Optional

from app.models import AuditReport, OperatorReading
from app.parsers.common import (
    enrich_adista_readings_with_ocr,
    extract_label_value_pairs,
    extract_line_value,
    extract_text,
    find_address,
    find_operator_metrics_from_pairs,
    find_per_operator_readings,
    find_qualitative_readings_by_operator,
    find_site_code,
    get_label,
    oneline,
)

_ANTENNA_TYPE_RE = re.compile(r"antennes?\s+(cierge|panneau|passive|active|omni\w*)", re.IGNORECASE)

_ENSEIGNE_RE = re.compile(
    r"carrefour\s+(city|express|market|proximit[ée]|hyper\w*|contact)", re.IGNORECASE
)

_EXT_ANTENNA_QUESTION_RE = re.compile(r"INSTALLER UNE ANTENNE EXTERIEURE\s*\?", re.IGNORECASE)
_OUI_NON_TOKEN_RE = re.compile(r"\b(OUI|NON)\b")


def _detect_provider(text: str) -> Optional[str]:
    low = text.lower()
    if "linkt" in low:
        return "linkt"
    if "adista" in low or "waycom" in low:
        return "adista"
    return None


def parse_audit(file_path: str) -> AuditReport:
    text = extract_text(file_path)
    provider = _detect_provider(text)
    if provider == "adista":
        return _parse_adista_audit(file_path, text)
    return _parse_linkt_audit(file_path, text)


def _parse_linkt_audit(file_path: str, text: str) -> AuditReport:
    pairs = extract_label_value_pairs(file_path)

    site_code = oneline(get_label(pairs, "Site", "Code site")) or find_site_code(text)
    adresse = oneline(get_label(pairs, "Adresse"))
    if not adresse:
        adresse = find_address(text)

    enseigne_match = _ENSEIGNE_RE.search((adresse or "") + " " + text[:2000])
    enseigne = enseigne_match.group(0) if enseigne_match else None

    technologies_existantes = get_label(pairs, "Technologies existantes")

    test_concluant = get_label(
        pairs,
        "Le test de réception au niveau des équipements de la baie est il concluant",
        "Le test de réception au niveau des équipements/de la baie est-il concluant ?",
    )
    antenne_type_answer = get_label(
        pairs,
        "Quel type d'antenne(s) est à installer pour améliorer la réception du signal ?",
        "Quel type d antenne s est à installer pour améliorer la réception du signal",
    )

    antenne_preconisee: Optional[bool] = None
    type_antenne = None
    if antenne_type_answer:
        antenne_preconisee = antenne_type_answer.strip().lower().startswith("oui")
        match = _ANTENNA_TYPE_RE.search(antenne_type_answer)
        type_antenne = match.group(1).lower() if match else None
    elif test_concluant:
        antenne_preconisee = test_concluant.strip().lower() == "non"

    meilleur_hno = get_label(
        pairs,
        "Suite aux différents tests menés, pouvez-vous indiquer le HNO avec la meilleure couverture ?",
        "Suite aux différents tests menés pouvez vous indiquer le HNO avec la meilleure couverture",
    )

    commentaire = get_label(pairs, "Commentaire du technicien :", "Commentaire du technicien")
    resultat = get_label(pairs, "Résultat de l'intervention")

    lectures_dicts = find_operator_metrics_from_pairs(pairs)
    if not lectures_dicts:
        lectures_dicts = find_per_operator_readings(text)
    lectures = [OperatorReading(**r) for r in lectures_dicts]

    return AuditReport(
        site_code=site_code,
        adresse=adresse,
        enseigne=enseigne,
        prestataire="linkt",
        antenne_preconisee=antenne_preconisee,
        type_antenne_preconisee=type_antenne,
        commentaire_preconisation=commentaire,
        technologies_existantes=technologies_existantes,
        meilleur_hno_audit=meilleur_hno.lower() if meilleur_hno else None,
        resultat_intervention=resultat,
        lectures=lectures,
        texte_brut=text,
    )


def _parse_adista_audit(file_path: str, text: str) -> AuditReport:
    site_code = extract_line_value(text, "Référence site client") or find_site_code(text)
    adresse = extract_line_value(text, "Adresse")
    resultat = extract_line_value(text, "Résultat de l'intervention")
    commentaire = extract_line_value(text, "Commentaires du technicien")

    enseigne_match = _ENSEIGNE_RE.search(adresse or "")
    enseigne = enseigne_match.group(0) if enseigne_match else None

    antenne_exterieure_autorisee = None
    question_match = _EXT_ANTENNA_QUESTION_RE.search(text)
    if question_match:
        answer_match = _OUI_NON_TOKEN_RE.search(text, question_match.end(), question_match.end() + 400)
        if answer_match:
            antenne_exterieure_autorisee = answer_match.group(1) == "OUI"

    lectures_dicts = find_qualitative_readings_by_operator(text)
    lectures_dicts = enrich_adista_readings_with_ocr(file_path, lectures_dicts)
    lectures = [OperatorReading(**r) for r in lectures_dicts]

    antenne_preconisee = bool(
        re.search(r"antenne\s+(4g\s+)?d[ée]port[ée]e", text, re.IGNORECASE)
    ) or None

    return AuditReport(
        site_code=site_code,
        adresse=adresse,
        enseigne=enseigne,
        prestataire="adista",
        antenne_preconisee=antenne_preconisee,
        antenne_exterieure_autorisee=antenne_exterieure_autorisee,
        commentaire_preconisation=commentaire,
        resultat_intervention=resultat,
        lectures=lectures,
        texte_brut=text,
    )
