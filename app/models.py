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
    emplacement: Optional[str] = None  # "baie" | "exterieur" | "meilleur_emplacement"


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
    systeme: Optional[str] = None  # ex: "LTE 800" — système du site le plus proche


class FttoOffreChiffree(BaseModel):
    offre: str
    prix_eur: Optional[float] = None
    prix_detail: str  # ex: "83 € HT/mois (palier 20 Mbps)", "sur devis", "prix non trouvé dans le BPU"


class FttoEligibility(BaseModel):
    eligible: Optional[bool] = None
    trouve: bool = False
    detail: Optional[str] = None
    offres_disponibles: dict[str, str] = {}  # nom de colonne -> offre proposée (ou "NON"), brut du fichier
    multi_pto: Optional[bool] = None  # dérivé de la colonne "Multi PTO" (colonne O)
    multi_pto_detail: Optional[str] = None
    offres_eligibles_brutes: list[str] = []  # noms d'offres éligibles (colonnes opérateur), dédupliqués
    offres_chiffrees: list[FttoOffreChiffree] = []  # triées du moins cher au plus cher
    offre_recommandee: Optional[str] = None  # l'offre la moins chère parmi les éligibles
    prix_mensuel: Optional[str] = None  # prix de l'offre recommandée (palier 20 Mbps fixe)


class Recommendation(BaseModel):
    technologie: str  # "4G_autre_operateur" | "FTTO" | "Starlink" | "OK"
    resume: str
    details: list[str] = []
    operateur_recommande: Optional[str] = None
    prestataire_recommande: Optional[str] = None
    # Zone a priori couverte (audit/ANFR) mais signal mesuré mauvais : la
    # recommandation ci-dessus reste une solution de contournement
    # concrète, mais un problème d'installation est aussi possible et
    # vaut la peine d'être vérifié sur site avant d'engager le changement.
    investigation_suspectee: bool = False
