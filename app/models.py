from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class OperatorReading(BaseModel):
    """Relevé radio pour un opérateur donné (RSRP/SNR, parfois débit).

    qualite_signal peut être renseigné même sans valeurs numériques (ex:
    rapports Adista où le technicien saisit un verdict "MAUVAIS"/"BON" à
    partir d'une valeur lue sur site mais non restituée en texte natif du
    PDF, uniquement visible sur une photo)."""

    operateur: str  # "orange" | "sfr" | "bouygues"
    rsrp_dbm: Optional[float] = None
    snr_db: Optional[float] = None
    rssi_dbm: Optional[float] = None
    rsrq_db: Optional[float] = None
    debit_down_mbps: Optional[float] = None
    debit_up_mbps: Optional[float] = None
    avec_antenne: Optional[bool] = None
    qualite_signal: Optional[str] = None  # "bon" | "moyen" | "mauvais"


class AuditReport(BaseModel):
    """Rapport de prévisite (audit) : conditions radio avant installation."""

    site_code: Optional[str] = None
    adresse: Optional[str] = None
    enseigne: Optional[str] = None
    antenne_preconisee: Optional[bool] = None
    type_antenne_preconisee: Optional[str] = None
    antenne_exterieure_autorisee: Optional[bool] = None
    commentaire_preconisation: Optional[str] = None
    technologies_existantes: Optional[str] = None
    meilleur_hno_audit: Optional[str] = None
    resultat_intervention: Optional[str] = None
    prestataire: Optional[str] = None
    lectures: list[OperatorReading] = []
    texte_brut: str = ""


class MesReport(BaseModel):
    """Rapport de mise en service (MES) : installation réelle du lien 4G."""

    site_code: Optional[str] = None
    adresse: Optional[str] = None
    prestataire: Optional[str] = None  # "linkt" | "adista"
    operateur_retenu: Optional[str] = None
    antenne_installee: Optional[bool] = None
    type_antenne: Optional[str] = None
    lectures: list[OperatorReading] = []
    rsrp_routeur_dbm: Optional[float] = None
    snr_routeur_db: Optional[float] = None
    resultat_intervention: Optional[str] = None
    texte_brut: str = ""


class AnfrSiteSummary(BaseModel):
    operateur: str
    nb_sites: int
    distance_min_m: Optional[float] = None


class FttoEligibility(BaseModel):
    eligible: Optional[bool] = None
    trouve: bool = False
    detail: Optional[str] = None


class Recommendation(BaseModel):
    technologie: str  # "4G_autre_operateur" | "FTTO" | "Starlink" | "Investiguer" | "OK"
    resume: str
    details: list[str] = []
    operateur_recommande: Optional[str] = None
    prestataire_recommande: Optional[str] = None
