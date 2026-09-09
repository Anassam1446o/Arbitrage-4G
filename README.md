# Arbitrage 4G

Outil d'aide à la décision pour les arbitrages de lien 4G de secours sur les
sites Carrefour (SD-WAN). À partir d'un rapport d'audit (prévisite) et d'un
rapport de Mise en Service (MES), il recommande : garder la 4G en l'état,
tenter un autre opérateur 4G, basculer sur FTTO, basculer sur Starlink, ou
investiguer un problème d'installation plutôt qu'un changement de
technologie.

La 4G est toujours considérée comme un lien de secours d'une FTTH déjà en
place : l'outil ne recommande jamais de FTTH.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Lancer l'application web

```bash
uvicorn app.main:app --reload
```

Puis ouvrir http://localhost:8000 : uploader le rapport de MES (obligatoire),
le rapport d'audit (optionnel mais recommandé) et, si disponible, le fichier
Excel d'éligibilité FTTO. Le critère Starlink (toit dégagé + propriété du
magasin) peut être renseigné manuellement, ou laissé à "je ne sais pas" —
l'outil essaiera alors de le déduire de la réponse du rapport d'audit à la
question "peut-on installer une antenne extérieure ?" (proxy imparfait, à
confirmer).

## Lancer les tests

```bash
pytest tests/ -v
```

Les tests s'appuient sur 4 rapports réels anonymisés (2 sites, Linkt et
Adista, audit + MES pour chacun) dans `tests/fixtures/`.

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
     texte réel pour chaque opérateur et emplacement testé (dans la baie, à
     l'extérieur du bâtiment, au meilleur emplacement trouvé). **Les
     valeurs RSRP/SINR numériques ne sont visibles que sur des captures
     d'écran photographiées et ne sont donc pas extractibles sans OCR** —
     seul le verdict qualitatif est utilisé pour ces rapports.

   Un format non reconnu (autre prestataire, ou rapport HTML) retombe sur un
   parseur générique par expressions régulières.

2. **Qualification du signal** (`app/signal_quality.py`) : reprend telle
   quelle la grille RSRP × SNR utilisée sur le terrain par Adista/Waycom
   (visible dans leurs rapports de MES) pour classer chaque relevé en
   bon / moyen / mauvais — plutôt que d'inventer des seuils.

3. **Environnement radio ANFR** (`app/anfr_client.py`, `app/geocoding.py`) :
   l'adresse du site est géocodée via l'API BAN (api-adresse.data.gouv.fr,
   gratuite, sans clé), puis l'API Open Data ANFR (`data.anfr.fr/d4c/api`)
   est interrogée pour recenser les sites radio à proximité, par opérateur.
   **⚠️ Le schéma exact du dataset (nom du dataset, noms de champs) n'a pas
   pu être vérifié en développement** : l'accès réseau à `data.anfr.fr` est
   bloqué dans l'environnement où ce programme a été écrit. Voir
   "À vérifier avant mise en prod" ci-dessous.

4. **Éligibilité FTTO** (`app/ftto.py`) : lecture d'un fichier Excel fourni
   par l'utilisateur, recherche par code site puis par adresse (correspondance
   approximative). Les noms de colonnes candidats sont dans
   `app/ftto.py::CANDIDATE_*_COLUMNS` — à ajuster une fois le fichier réel
   connu.

5. **Moteur de décision** (`app/decision_engine.py`) :
   - Si un opérateur testé donne un signal "bon" → pas d'arbitrage.
   - Sinon, si l'audit ou l'ANFR suggère que la zone est a priori bien
     couverte → recommandation "Investiguer" (pose d'antenne non conforme,
     déperdition câble, mauvais choix d'opérateur...) plutôt qu'un
     changement de technologie.
   - Sinon (zone réellement mauvaise) : tenter un opérateur 4G non testé
     disponible via le prestataire (Linkt : Orange/SFR natifs — la carte SIM
     du routeur peut basculer à distance entre les deux —, Bouygues en
     option ; Adista : Orange/Bouygues natifs, même principe de bascule à
     distance, SFR en option). Free n'est jamais recommandé (aucun
     partenariat Linkt/Adista).
   - Sinon, FTTO si éligible.
   - Sinon, Starlink (243 €/mois), sous réserve du critère toit
     dégagé + propriété du magasin.

## À vérifier avant mise en prod

- **Endpoint de recherche géographique ANFR** : le `resource_id` du
  dataset ("observatoire_2g_3g_4g") et les noms de champs
  (`adm_lb_nom`, `coordonnees`, `generation`, `sta_nm_anfr`) sont
  **vérifiés** — repris d'un appel réel et fonctionnel
  (`https://data.anfr.fr/d4c/api/records/2.0/downloadfile/...`) observé
  dans le projet tiers open-source
  [RealTux678/Generateur_ANFR](https://github.com/RealTux678/Generateur_ANFR)
  (`java/A_ANFR_Downloader.java` et `A_Generateur_ANFR.java`). Ce qui reste
  à confirmer une fois un accès réseau normal disponible : que
  `.../records/2.0/search/` (utilisé ici avec `geofilter.distance` pour la
  recherche par rayon) existe bien en plus de `.../downloadfile/` et
  répond en JSON avec la forme `{"records": [{"fields": {...}}]}` — sinon
  ajuster `app/anfr_client.py::fetch_nearby_sites`.
- **Fichier Excel FTTO** : fournir un exemple réel pour caler les noms de
  colonnes exacts dans `app/ftto.py`.
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
  config.py            seuils, mapping opérateurs/prestataires, endpoints
  models.py             modèles de données (Pydantic)
  signal_quality.py      grille de qualification RSRP x SNR
  geocoding.py            client API BAN (géocodage d'adresse)
  anfr_client.py           client API Open Data ANFR
  ftto.py                   lecture du fichier Excel d'éligibilité FTTO
  decision_engine.py         moteur de décision / arbitrage
  parsers/
    common.py                helpers d'extraction (texte, tableaux, regex)
    audit_parser.py            parseur rapport d'audit (Linkt + Adista)
    mes_parser.py                parseur rapport de MES (Linkt + Adista)
  main.py                        application web FastAPI
  templates/, static/             interface web
tests/
  fixtures/                       4 rapports réels anonymisés
  test_parsers.py, test_decision_engine.py
```
