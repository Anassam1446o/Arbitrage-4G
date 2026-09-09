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

# API Open Data ANFR ("d4c", API "records" v2.0). Endpoint et resource_id
# confirmés à partir d'un appel réel et fonctionnel observé dans un projet
# tiers open-source (RealTux678/Generateur_ANFR, java/A_ANFR_Downloader.java) :
#   https://data.anfr.fr/d4c/api/records/2.0/downloadfile/?format=csv
#     &refine.generation=4G&refine.generation=5G
#     &resource_id=88ef0887-6b0f-4d3f-8545-6d64c8f597da
# resource_id = dataset "observatoire_2g_3g_4g" (sites radio 2G/3G/4G/5G).
# Le endpoint utilisé ici (.../records/2.0/search/) suppose que l'API expose
# un équivalent JSON filtrable par géolocalisation au même endpoint que le
# téléchargement CSV ci-dessus (convention "records/2.0" standard) ; à
# confirmer avec un accès réseau réel (voir README, section ANFR) — mais
# resource_id et noms de champs ci-dessous sont vérifiés, pas devinés.
ANFR_BASE_URL = "https://data.anfr.fr/d4c/api/records/2.0"
ANFR_RESOURCE_ID = "88ef0887-6b0f-4d3f-8545-6d64c8f597da"

# Mapping des libellés exploitant tels qu'ils apparaissent dans le champ
# adm_lb_nom du dataset ANFR vers nos clés internes.
ANFR_OPERATOR_LABELS = {
    "orange": ["ORANGE"],
    "sfr": ["SFR"],
    "bouygues": ["BOUYGUES TELECOM", "BOUYGUES"],
    "free": ["FREE MOBILE", "FREE"],
}

# Noms de champs du dataset ANFR "observatoire_2g_3g_4g", vérifiés à partir
# du même projet tiers (mapping CSV -> champs dans A_Generateur_ANFR.java) :
# adm_lb_nom (opérateur), coordonnees ("lat, lon" en une seule chaîne),
# generation (2G/3G/4G/5G), sta_nm_anfr (identifiant de station).
ANFR_FIELD_OPERATOR = "adm_lb_nom"
ANFR_FIELD_COORDONNEES = "coordonnees"
ANFR_FIELD_GENERATION = "generation"
ANFR_FIELD_STATION_ID = "sta_nm_anfr"
