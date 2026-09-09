"""Configuration centrale : seuils radio, mapping opérateurs/prestataires, endpoints API.

Tous les seuils ci-dessous sont des valeurs télécom usuelles pour de la 4G LTE
en attendant les seuils réels de Carrefour. Ajuste-les ici, rien d'autre à
toucher dans le code pour les faire changer.
"""

# --- Seuils radio (LTE / 4G) --------------------------------------------
# RSRP en dBm, SNR (SINR) en dB, débit en Mbps.
# Une valeur "bonne" doit être >= au seuil "good", une valeur "mauvaise" est
# < au seuil "bad". Entre les deux : zone intermédiaire ("moyen").
RSRP_GOOD_DBM = -95   # signal confortable
RSRP_BAD_DBM = -110   # signal très dégradé, en dessous : quasi inexploitable

SNR_GOOD_DB = 10
SNR_BAD_DB = 0

DEBIT_DOWN_GOOD_MBPS = 10.0
DEBIT_DOWN_BAD_MBPS = 2.0

# Rayon de recherche des sites/antennes ANFR autour de l'adresse (mètres).
ANFR_SEARCH_RADIUS_M = 3000

# Nombre de sites 4G d'un opérateur à moins de ANFR_SEARCH_RADIUS_M pour
# considérer que la zone est "couverte" par cet opérateur.
ANFR_MIN_SITES_FOR_COVERAGE = 1

# --- Prestataires / opérateurs disponibles -------------------------------
# Chaque prestataire ne sait déployer qu'un sous-ensemble d'opérateurs.
# Free n'est jamais utilisé (pas de partenariat).
PROVIDER_NATIVE_OPERATORS = {
    "linkt": ["orange", "sfr"],
    "adista": ["orange", "bouygues"],
}

# Opérateur additionnel accessible via ce prestataire mais nécessitant une
# demande spécifique (hors offre "native" à 2 HNO testés par défaut).
PROVIDER_EXTRA_OPERATOR = {
    "linkt": "bouygues",
    "adista": "sfr",
}

ALL_OPERATORS = ["orange", "sfr", "bouygues"]  # jamais "free"

# --- Starlink --------------------------------------------------------------
STARLINK_MONTHLY_PRICE_EUR = 243

# Types de magasin où le critère "toit dégagé + propriété du magasin" est
# présumé plus souvent favorable (à confirmer manuellement dans tous les cas).
STARLINK_FAVORABLE_STORE_TYPES = ["hypermarché", "hyper", "market"]
STARLINK_UNFAVORABLE_STORE_TYPES = ["city", "express", "contact", "proximité"]

# --- APIs externes ----------------------------------------------------------
BAN_GEOCODE_URL = "https://api-adresse.data.gouv.fr/search/"

# API Open Data ANFR (portail "data4C", format OpenDataSoft Explore v2.1).
# Le nom exact du dataset radio doit être vérifié une fois l'accès réseau
# disponible (voir README section ANFR) ; à défaut il peut être surchargé
# via la variable d'environnement ANFR_DATASET_ID.
ANFR_BASE_URL = "https://data.anfr.fr/d4c/api/explore/v2.1/catalog/datasets"
ANFR_DATASET_ID = "observatoire_2g_3g_4g_par_site"

# Mapping des libellés exploitant tels qu'ils apparaissent dans le jeu de
# données ANFR vers nos clés internes. À ajuster une fois le schéma réel
# vérifié (voir README).
ANFR_OPERATOR_LABELS = {
    "orange": ["ORANGE"],
    "sfr": ["SFR"],
    "bouygues": ["BOUYGUES TELECOM", "BOUYGUES"],
    "free": ["FREE MOBILE", "FREE"],
}

# Noms de champs du dataset ANFR (à vérifier/ajuster une fois l'accès réseau
# disponible : voir README, section "Vérifier le schéma ANFR"). Peuvent être
# surchargés sans toucher au code appelant.
ANFR_FIELD_OPERATOR = "adm_lb_nom"
ANFR_FIELD_LAT = "lat"
ANFR_FIELD_LON = "lon"
ANFR_FIELD_GENERATION = "generation"  # ex: valeur contenant "4G"
