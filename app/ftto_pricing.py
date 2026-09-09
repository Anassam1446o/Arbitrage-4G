"""Grille tarifaire FTTO (BPU) : chiffre les offres FTTO éligibles pour un
site (cf. app/ftto.py::check_eligibility) et recommande la moins chère —
pas de règle fixe du type "le Burst est toujours prioritaire" : le Burst
est structurellement moins cher quand il est disponible, mais tous les
sites n'y sont pas éligibles, donc on classe simplement par prix réel.

Calibré sur un export réel "BPU" (feuille "Catalogue d'accès") : chaque
ligne est un couple (palier de débit, offre/opérateur), avec le libellé de
l'offre en colonne K ("Commentaires", ex: "Covage ZTD/ZD", "Eurofiber E0",
"Orange O3", "SFR EA Select", "Bouygues FTTE"...) et le prix mensuel HT en
colonne F ("Abonnement").

Consigne du porteur de projet : on prend systématiquement le palier
"FTTO 20 Mbps" pour le prix affiché, quel que soit le débit réellement
nécessaire sur le site.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

import pandas as pd

FIXED_DEBIT_LABEL = "ftto 20 mbps"

# Colonnes du BPU (index pandas, 0-based) : B="Type d'accès", F="Abonnement", K="Commentaires".
_COL_TYPE_ACCES = 1
_COL_ABONNEMENT = 5
_COL_COMMENTAIRE = 10


def _normalize(text) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _strip_ftto_prefix(offer: str) -> str:
    text = re.sub(r"^ftt[oe]\s+", "", offer.strip(), flags=re.IGNORECASE)
    # "Burst" est un qualificatif de gamme (débit garanti + rafale), pas
    # une partie du nom de l'offre/opérateur : à ignorer pour le matching.
    text = re.sub(r"\bburst\b", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def load_price_table(file_path: str) -> dict[str, object]:
    """Renvoie {libellé_normalisé_offre: prix (nombre ou "sur devis")}.

    Les offres FTTO standard n'ont un prix qu'au palier "FTTO 20 Mbps"
    (consigne métier). Les offres Burst n'existent pas à ce palier — ce
    sont des lignes à part dans le BPU (ex: "FTTO 5 Mbps burst 100 Mbps"),
    un seul prix fixe par offre quel que soit le débit garanti : on les
    garde toutes, sans filtre de palier."""
    df = pd.read_excel(file_path, sheet_name=0, header=None)
    prices: dict[str, object] = {}
    for _, row in df.iterrows():
        type_acces = row.get(_COL_TYPE_ACCES)
        if not isinstance(type_acces, str):
            continue
        normalized_type = _normalize(type_acces)
        if normalized_type != FIXED_DEBIT_LABEL and "burst" not in normalized_type:
            continue
        commentaire = row.get(_COL_COMMENTAIRE)
        if not isinstance(commentaire, str) or not commentaire.strip():
            continue
        key = _normalize(commentaire)
        if key not in prices:  # priorité à la première ligne rencontrée (palier 20 Mbps en tête du fichier)
            prices[key] = row.get(_COL_ABONNEMENT)
    return prices


def find_price(price_table: dict[str, object], offer_name: Optional[str]) -> tuple[Optional[object], Optional[str]]:
    """Cherche le prix mensuel HT (palier 20 Mbps) pour une offre FTTO
    (ex: "FTTO Eurofiber E0"). Renvoie (prix, libellé BPU trouvé) — prix
    peut être un nombre ou une chaîne ("sur devis") ; (None, None) si
    aucune correspondance."""
    if not offer_name:
        return None, None

    key = _normalize(_strip_ftto_prefix(offer_name))
    if key in price_table:
        return price_table[key], key

    # Correspondance approximative : tous les mots de l'offre recherchée
    # doivent apparaître dans le libellé BPU candidat.
    key_tokens = set(key.split())
    if not key_tokens:
        return None, None
    for candidate_key, value in price_table.items():
        if key_tokens <= set(candidate_key.split()):
            return value, candidate_key

    return None, None


def format_price(raw_price: object, is_burst: bool = False) -> Optional[str]:
    if raw_price is None:
        return None
    if isinstance(raw_price, (int, float)):
        palier = "offre Burst, prix fixe" if is_burst else "palier 20 Mbps"
        return f"{raw_price:g} € HT/mois ({palier})"
    return str(raw_price)


def build_priced_offers(eligibility, price_file_path: str):
    """Chiffre chaque offre éligible (eligibility.offres_eligibles_brutes),
    les trie de la moins chère à la plus chère (les offres "sur devis" ou
    sans prix trouvé passent en dernier), et fixe offre_recommandee /
    prix_mensuel sur la moins chère. Dégradation silencieuse si le BPU est
    absent/illisible ou si aucune offre éligible n'existe."""
    from app.models import FttoOffreChiffree

    if not eligibility.offres_eligibles_brutes:
        return eligibility

    try:
        table = load_price_table(price_file_path)
    except Exception:
        return eligibility

    priced: list[FttoOffreChiffree] = []
    for offer_name in eligibility.offres_eligibles_brutes:
        raw_price, _matched = find_price(table, offer_name)
        prix_eur = raw_price if isinstance(raw_price, (int, float)) else None
        is_burst = "burst" in offer_name.lower()
        prix_detail = format_price(raw_price, is_burst=is_burst) or "prix non trouvé dans le BPU"
        priced.append(FttoOffreChiffree(offre=offer_name, prix_eur=prix_eur, prix_detail=prix_detail))

    priced.sort(key=lambda o: (o.prix_eur is None, o.prix_eur if o.prix_eur is not None else 0))

    eligibility.offres_chiffrees = priced
    if priced:
        eligibility.offre_recommandee = priced[0].offre
        eligibility.prix_mensuel = priced[0].prix_detail
    return eligibility
