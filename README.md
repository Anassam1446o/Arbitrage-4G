# Arbitrage 4G

Outil d'aide à la décision pour les arbitrages de lien 4G de secours sur les
sites Carrefour (SD-WAN). Ces sites sont envoyés au moteur *parce que* leur
4G est déjà mauvaise : l'objectif est donc toujours de trouver une solution
de contournement concrète — jamais de laisser un dossier sans recommandation
actionnable. À partir d'un rapport d'audit (prévisite) et d'un rapport de
Mise en Service (MES), l'outil recommande toujours l'une de ces 3
technologies : **4G avec un autre opérateur**, **FTTO** (offre la moins
chère parmi celles éligibles), ou **Starlink**. Quand la zone semble a
priori bien couverte (audit/ANFR) malgré un signal mesuré mauvais, un
avertissement "problème d'installation possible" est ajouté en plus de la
recommandation — jamais à la place.

La 4G est toujours considérée comme un lien de secours d'une FTTH déjà en
place : l'outil ne recommande jamais de FTTH.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### OCR (optionnel mais recommandé)

Les rapports Adista affichent les valeurs RSRP/SINR/débit sur des captures
d'écran (pas en texte natif du PDF). Pour les lire automatiquement, il faut
en plus installer le moteur **Tesseract OCR** sur la machine (les paquets
Python `pytesseract`/`PyMuPDF` déjà dans `requirements.txt` ne suffisent
pas à eux seuls) :

- Windows : https://github.com/UB-Mannheim/tesseract/wiki (installeur),
  puis vérifier `tesseract --version` dans un nouveau terminal.
- macOS : `brew install tesseract`
- Linux (Debian/Ubuntu) : `sudo apt install tesseract-ocr`

Sans Tesseract, l'application fonctionne normalement mais les valeurs
RSRP/SINR/débit des rapports Adista restent vides — seul le verdict
qualitatif (bon/moyen/mauvais) saisi en texte par le technicien est utilisé,
ce qui suffit à piloter la décision.

## Lancer l'application web

```bash
uvicorn app.main:app --reload
```

Puis ouvrir http://localhost:8000 : uploader le rapport de MES (obligatoire)
et le rapport d'audit (optionnel mais recommandé). Le critère Starlink (toit
dégagé + propriété du magasin) peut être renseigné manuellement, ou laissé à
"je ne sais pas" — l'outil essaiera alors de le déduire de la réponse du
rapport d'audit à la question "peut-on installer une antenne extérieure ?"
(proxy imparfait, à confirmer visuellement via le lien satellite fourni dans
le résultat).

L'éligibilité FTTO et sa grille tarifaire sont **intégrées à l'application**
(pas d'upload à chaque analyse) : voir "Données intégrées" ci-dessous pour
les mettre à jour.

## Lancer les tests

```bash
pytest tests/ -v
```

Les tests s'appuient sur des rapports réels anonymisés (2 sites, Linkt et
Adista, audit + MES pour chacun, plus le fichier d'éligibilité FTTO et le
BPU tarifaire) dans `tests/fixtures/`.

## Comment ça marche

1. **Parsing des rapports** (`app/parsers/`) : deux formats réels sont
   gérés nativement, détectés automatiquement par mot-clé dans le texte :
   - **Linkt (Praxedo)** : tableaux PDF à 2 colonnes "libellé / valeur".
     Les relevés RSRP/SNR par opérateur sont soit dans un tableau "Mesures
     Radio" dédié (rapports d'audit), soit dans le commentaire libre du
     technicien (rapports de MES, ex: "Valeur radio SFR avec antenne
     cierge : RSRP -103/ SNR -2").
   - **Adista (Waycom)** : rapports en texte à plat ("checklist"). Un
     verdict qualitatif (EXCELLENT / BIEN / MOYEN / MAUVAIS) est saisi en
     texte réel pour chaque opérateur ET chaque emplacement testé (dans la
     baie, à l'extérieur du bâtiment, au meilleur emplacement trouvé en
     magasin). Les valeurs RSRP/SINR/débit numériques ne sont visibles que
     sur des captures d'écran photographiées : elles sont lues en
     complément par OCR quand Tesseract est installé (voir ci-dessus),
     jamais à la place du verdict qualitatif qui reste la source de vérité
     pour la décision.

   Un format non reconnu (autre prestataire, ou rapport HTML) retombe sur un
   parseur générique par expressions régulières.

2. **Qualification du signal** (`app/signal_quality.py`) : reprend telle
   quelle la grille RSRP × SNR utilisée sur le terrain par Adista/Waycom
   (visible dans leurs rapports de MES) pour classer chaque relevé en
   bon / moyen / mauvais — plutôt que d'inventer des seuils.

3. **Environnement radio ANFR** (`app/anfr_client.py`, `app/geocoding.py`) :
   l'adresse du site est géocodée via l'API BAN (api-adresse.data.gouv.fr,
   gratuite, sans clé), puis l'API Open Data ANFR est interrogée pour
   recenser les sites radio à proximité, par opérateur, avec la distance
   du site le plus proche (calcul de distance à vol d'oiseau) et sa
   technologie — utilisé pour justifier concrètement une recommandation
   "4G autre opérateur" (ex: "site Bouygues le plus proche à 340 m, LTE
   1800"). **Limite connue : pas d'information d'azimut/secteur** (un site
   proche peut très bien ne pas pointer vers le magasin) — cette donnée
   existe dans un autre jeu ANFR (installations radioélectriques, plus
   complexe à intégrer, non vérifié). Un lien direct vers la vue satellite
   Google Maps du site est aussi fourni pour vérification visuelle rapide
   (notamment le critère toit Starlink).
   **⚠️ Voir "À vérifier avant mise en prod" pour le statut de
   vérification de cette API.**

4. **Éligibilité et tarification FTTO** (`app/ftto.py`,
   `app/ftto_pricing.py`) : toutes les offres FTTO éligibles pour le site
   (colonnes opérateur du fichier de suivi, pas seulement la
   "Préconisation" du fichier) sont chiffrées via le BPU et classées de la
   moins chère à la plus chère — la recommandation est toujours l'offre la
   moins chère parmi les éligibles (le Burst, structurellement moins cher,
   ressort donc naturellement en premier quand il est disponible, sans
   règle spéciale à coder). Le statut Multi PTO (OK/KO/inconnu) est aussi
   remonté. Si un site apparaît plusieurs fois dans le fichier, la ligne à
   la date d'éligibilité la plus récente est retenue.

5. **Moteur de décision** (`app/decision_engine.py`) :
   - Si un opérateur testé donne un signal "bon" → pas d'arbitrage, on
     garde ce lien (seul cas où la recommandation n'est pas l'une des 3
     technologies).
   - Sinon, le moteur calcule toujours une recommandation concrète parmi
     les 3 technologies (voir ci-dessous), et ajoute en plus un
     avertissement "problème d'installation possible" quand l'audit ou
     l'ANFR suggère que la zone est a priori bien couverte malgré un
     signal mesuré mauvais (pose d'antenne non conforme, déperdition
     câble, mauvais choix d'opérateur...).
   - D'abord : tenter un opérateur 4G non testé disponible via le
     prestataire (Linkt : Orange/SFR natifs — la carte SIM du routeur peut
     basculer à distance entre les deux —, Bouygues en option ; Adista :
     Orange/Bouygues natifs, même principe, SFR en option). Free n'est
     jamais recommandé (aucun partenariat Linkt/Adista). Le choix entre
     opérateurs candidats est classé par proximité du site ANFR le plus
     proche.
   - Sinon, FTTO si au moins une offre est éligible (la moins chère).
   - Sinon, Starlink (243 €/mois par défaut), sous réserve du critère toit
     dégagé + propriété du magasin — si ce critère est refusé, Starlink
     reste la recommandation par défaut mais avec un avertissement
     explicite à lever avant de valider.

## Données intégrées

Deux fichiers sont packagés dans `app/data/` (pas d'upload à chaque
analyse) — les remplacer par une version à jour puis committer pour les
mettre à jour :

- `app/data/ftto_eligibilite.csv` — export "Suivi_Eligibilités" (CSV,
  séparateur `;`, encodage Windows-1252). Colonne clé : `Code_DSR`
  (format `FR-XXNNNNN`).
- `app/data/ftto_prix.xlsx` — grille tarifaire FTTO (BPU, feuille
  "Catalogue d'accès"). Prix toujours pris au palier **FTTO 20 Mbps**
  (consigne métier), quel que soit le débit réellement nécessaire.

Le chemin peut être surchargé sans toucher au code via les variables
d'environnement `FTTO_FILE_PATH` et `FTTO_PRICE_FILE_PATH`.

## À vérifier avant mise en prod

- **Endpoint de recherche géographique ANFR** : le `resource_id` du
  dataset ("observatoire_2g_3g_4g") et les noms de champs
  (`adm_lb_nom`, `coordonnees`, `generation`, `sta_nm_anfr`,
  `emr_lb_systeme`) sont **vérifiés** — repris d'un appel réel et
  fonctionnel (`https://data.anfr.fr/d4c/api/records/2.0/downloadfile/...`)
  observé dans le projet tiers open-source
  [RealTux678/Generateur_ANFR](https://github.com/RealTux678/Generateur_ANFR)
  (`java/A_ANFR_Downloader.java` et `A_Generateur_ANFR.java`). Ce qui reste
  à confirmer une fois un accès réseau normal disponible : que
  `.../records/2.0/search/` (utilisé ici avec `geofilter.distance` pour la
  recherche par rayon) existe bien en plus de `.../downloadfile/` et
  répond en JSON avec la forme `{"records": [{"fields": {...}}]}` — sinon
  ajuster `app/anfr_client.py::fetch_nearby_sites`.
- **Lien satellite / géocodage** : `app/geocoding.py` (API BAN) n'a pas pu
  être testé en conditions réelles depuis l'environnement de développement
  (accès réseau bloqué) — le code est standard (API publique bien
  documentée) mais un premier test réel est recommandé.
- **OCR Adista** : les regex d'extraction (`app/parsers/common.py`,
  `enrich_adista_readings_with_ocr`) n'ont pas pu être validées sur une
  vraie sortie Tesseract (moteur absent de l'environnement de dev) — à
  vérifier sur un vrai rapport une fois Tesseract installé, et ajuster les
  patterns si le texte OCR réel diffère de ce qui était attendu.
- **Rapports d'un autre prestataire ou d'un audit Adista non "Prévisite
  Light"** : le parseur générique (`_parse_generic` / heuristiques
  regex) prendra le relais mais sera moins précis — fournir un exemple
  réel pour le calibrer précisément, comme cela a été fait pour Linkt et
  Adista.
- **Seuils** (`app/config.py`) : `RSRP_GOOD_DBM`/`RSRP_BAD_DBM` etc. ne sont
  plus utilisés par le moteur de décision (remplacés par la grille terrain
  dans `signal_quality.py`) mais restent disponibles si un usage futur en a
  besoin.

## Structure du projet

```
app/
  config.py            seuils, mapping opérateurs/prestataires, chemins de données
  models.py             modèles de données (Pydantic)
  signal_quality.py      grille de qualification RSRP x SNR
  geocoding.py            client API BAN (géocodage d'adresse)
  anfr_client.py           client API Open Data ANFR (sites + distance)
  ftto.py                   éligibilité FTTO (fichier intégré, app/data/)
  ftto_pricing.py            tarification FTTO (BPU intégré, app/data/)
  decision_engine.py         moteur de décision / arbitrage
  parsers/
    common.py                helpers d'extraction (texte, tableaux, regex, OCR)
    audit_parser.py            parseur rapport d'audit (Linkt + Adista)
    mes_parser.py                parseur rapport de MES (Linkt + Adista)
  main.py                        application web FastAPI
  templates/, static/             interface web
  data/                            fichiers d'éligibilité/tarification FTTO intégrés
tests/
  fixtures/                       rapports réels anonymisés + extraits FTTO
```
