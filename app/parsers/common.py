"""Fonctions communes d'extraction de texte et de valeurs radio, utilisées
par les parseurs de rapports d'audit et de MES (HTML ou PDF)."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Optional

import pdfplumber
from bs4 import BeautifulSoup


def normalize_label(label: str) -> str:
    """Normalise un libellé de champ pour permettre un lookup insensible à
    la casse, aux accents, à la ponctuation et aux retours à la ligne
    (les tableaux PDF cassent souvent un libellé sur 2 lignes)."""
    if not label:
        return ""
    text = label.replace("\n", " ")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_label_value_pairs(file_path: str) -> dict[str, str]:
    """Construit un dict {libellé_normalisé: valeur} à partir des tableaux
    à 2 colonnes d'un rapport PDF ou HTML (format "Rapport d'intervention"
    Linkt/Praxedo notamment). Les valeurs sont concaténées si un même
    libellé apparaît plusieurs fois (tableaux redétectés en doublon par
    pdfplumber)."""
    suffix = Path(file_path).suffix.lower()
    if suffix == ".pdf":
        return _extract_pairs_from_pdf(file_path)
    if suffix in {".html", ".htm"}:
        return _extract_pairs_from_html(file_path)
    return {}


def _extract_pairs_from_pdf(file_path: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    if len(row) >= 2 and row[0] and row[1]:
                        key = normalize_label(row[0])
                        if key and key not in pairs:
                            pairs[key] = row[1].strip()
                    if len(row) >= 4 and row[2] and row[3]:
                        key = normalize_label(row[2])
                        if key and key not in pairs:
                            pairs[key] = row[3].strip()
    return pairs


def _extract_pairs_from_html(file_path: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            texts = [c.get_text(separator=" ", strip=True) for c in cells]
            for i in range(0, len(texts) - 1, 2):
                key = normalize_label(texts[i])
                if key and key not in pairs and texts[i + 1]:
                    pairs[key] = texts[i + 1]
    return pairs


def oneline(value: Optional[str]) -> Optional[str]:
    """Aplati une valeur de cellule multi-lignes (ex: adresse sur 2 lignes
    dans un tableau PDF) en une seule ligne lisible."""
    if value is None:
        return None
    return re.sub(r"\s+", " ", value).strip()


def get_label(pairs: dict[str, str], *candidate_labels: str) -> Optional[str]:
    """Cherche la première correspondance parmi plusieurs libellés
    candidats (variantes possibles d'un même champ selon le prestataire)."""
    for label in candidate_labels:
        value = pairs.get(normalize_label(label))
        if value:
            return value
    return None


_LINE_VALUE_RE_CACHE: dict[str, re.Pattern] = {}


def extract_line_value(text: str, label: str) -> Optional[str]:
    """Pour les rapports en texte à plat (format Adista/Waycom) : cherche
    'label' en début de ligne et renvoie le reste de la ligne."""
    pattern = _LINE_VALUE_RE_CACHE.get(label)
    if pattern is None:
        pattern = re.compile(re.escape(label) + r"\s+(.+)", re.IGNORECASE)
        _LINE_VALUE_RE_CACHE[label] = pattern
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def extract_text(file_path: str) -> str:
    """Extrait le texte brut d'un fichier HTML ou PDF."""
    suffix = Path(file_path).suffix.lower()
    if suffix == ".pdf":
        return _extract_text_from_pdf(file_path)
    if suffix in {".html", ".htm"}:
        return _extract_text_from_html(file_path)
    raise ValueError(f"Format de fichier non supporté : {suffix}")


def _extract_text_from_pdf(file_path: str) -> str:
    chunks = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            chunks.append(page_text)
    return "\n".join(chunks)


def _extract_text_from_html(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n")


# --- Extraction de valeurs radio -----------------------------------------

_OPERATOR_ALIASES = {
    "orange": "orange",
    "sfr": "sfr",
    "bouygues": "bouygues",
    "bouygues telecom": "bouygues",
    "bytel": "bouygues",
    "free": "free",
}

# Libellés "Mesures Radio" tels qu'observés dans les rapports d'audit Linkt :
# "Orange - RSRP (-X dBm)", "SFR SNR (X dB)", "ByTel - RSSI (-X dBm)", etc.
# (comparé sur le libellé normalisé, ex: "orange rsrp x dbm").
_METRIC_LABEL_RE = re.compile(r"^(orange|sfr|bytel|bouygues)\s+(rssi|rsrp|rsrq|snr)\b")

_METRIC_FIELD_MAP = {"rssi": "rssi_dbm", "rsrp": "rsrp_dbm", "rsrq": "rsrq_db", "snr": "snr_db"}

# Repère des lignes du type :
# "Valeur radio SFR avec antenne cierge : RSRP -103/ SNR -2"
# "RSRP SFR : -103 dBm, SNR : -2 dB"
_OPERATOR_READING_RE = re.compile(
    r"(?P<operateur>orange|sfr|bouygues(?:\s+telecom)?)"
    r"[^\n]{0,60}?"
    r"RSRP[^\n\d-]{0,10}(?P<rsrp>-?\d+(?:[.,]\d+)?)"
    r"[^\n]{0,40}?"
    r"SNR[^\n\d-]{0,10}(?P<snr>-?\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)

_SINGLE_RSRP_RE = re.compile(
    r"(?:valeur\s+)?rsrp[^\n\d-]{0,40}?(-?\d+(?:[.,]\d+)?)", re.IGNORECASE
)
_SINGLE_SNR_RE = re.compile(
    r"(?:valeur\s+)?s[in]nr[^\n\d-]{0,40}?(-?\d+(?:[.,]\d+)?)", re.IGNORECASE
)
_DEBIT_DOWN_RE = re.compile(
    r"(?:débit\s+descendant|réception|download)[^\n\d]{0,20}?(\d+(?:[.,]\d+)?)\s*mbit", re.IGNORECASE
)
_DEBIT_UP_RE = re.compile(
    r"(?:débit\s+montant|envoi|upload)[^\n\d]{0,20}?(\d+(?:[.,]\d+)?)\s*mbit", re.IGNORECASE
)

_SITE_CODE_RE = re.compile(r"\bFR[-]?[A-Z]{2}\d{5}[_\-][A-Z0-9_\-]+", re.IGNORECASE)


def _to_float(raw: str) -> Optional[float]:
    if raw is None:
        return None
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def find_operator_metrics_from_pairs(pairs: dict[str, str]) -> list[dict]:
    """Reconstruit les relevés par opérateur à partir d'un tableau "Mesures
    Radio" façon audit Linkt (4 lignes RSSI/RSRP/RSRQ/SNR par opérateur)."""
    metrics: dict[str, dict] = {}
    for normalized_key, value in pairs.items():
        match = _METRIC_LABEL_RE.match(normalized_key)
        if not match:
            continue
        operator_raw, metric = match.groups()
        operator = _OPERATOR_ALIASES.get(operator_raw, operator_raw)
        entry = metrics.setdefault(operator, {"operateur": operator})
        entry[_METRIC_FIELD_MAP[metric]] = _to_float(value)
    return list(metrics.values())


# Format audit/MES Adista/Waycom : question qualifiant le signal d'un
# opérateur, ex: "...QUALIFERIEZ-VOUS LE SIGNAL BOUYGUES DANS LA BAIE ?"
# La réponse (verdict) apparaît plus loin dans le texte, après un bloc de
# consignes et/ou une capture d'écran (image, donc invisible en texte) : la
# distance entre la question et la réponse varie selon le gabarit exact du
# rapport (audit vs MES). On cherche donc le premier verdict qui suit,
# repéré en MAJUSCULES (les réponses saisies dans l'outil le sont
# systématiquement, ce qui évite les faux positifs sur des mots du
# texte libre comme "...ou bien faut-il...").
_QUESTION_OPERATOR_RE = re.compile(
    r"QUALIFERIEZ-VOUS LE SIGNAL\s+(BOUYGUES|ORANGE|SFR)", re.IGNORECASE
)
_VERDICT_TOKEN_RE = re.compile(r"\b(EXCELLENT|BON|BIEN|MOYEN|MAUVAIS)\b")
_VERDICT_SEARCH_WINDOW = 800


def find_qualitative_readings_by_operator(text: str) -> list[dict]:
    """Cherche les verdicts qualitatifs explicitement associés à un
    opérateur (format audit/MES Adista, un verdict par opérateur et par
    emplacement testé : baie, extérieur, meilleur emplacement trouvé)."""
    from app.signal_quality import normalize_qualitative_verdict

    readings = []
    for match in _QUESTION_OPERATOR_RE.finditer(text):
        operator_raw = match.group(1)
        verdict_match = _VERDICT_TOKEN_RE.search(
            text, match.end(), match.end() + _VERDICT_SEARCH_WINDOW
        )
        if not verdict_match:
            continue
        operator = _OPERATOR_ALIASES.get(operator_raw.lower(), operator_raw.lower())
        readings.append(
            {
                "operateur": operator,
                "qualite_signal": normalize_qualitative_verdict(verdict_match.group(1)),
            }
        )
    return readings


def find_per_operator_readings(text: str) -> list[dict]:
    """Cherche les relevés RSRP/SNR mentionnant explicitement un opérateur
    (typiquement dans un commentaire technicien listant les 2 HNO testés)."""
    readings = []
    for match in _OPERATOR_READING_RE.finditer(text):
        operator_raw = match.group("operateur").lower()
        operator = _OPERATOR_ALIASES.get(operator_raw, operator_raw.split()[0])
        readings.append(
            {
                "operateur": operator,
                "rsrp_dbm": _to_float(match.group("rsrp")),
                "snr_db": _to_float(match.group("snr")),
            }
        )
    return readings


def find_single_rsrp(text: str) -> Optional[float]:
    match = _SINGLE_RSRP_RE.search(text)
    return _to_float(match.group(1)) if match else None


def find_single_snr(text: str) -> Optional[float]:
    match = _SINGLE_SNR_RE.search(text)
    return _to_float(match.group(1)) if match else None


def find_debit_down(text: str) -> Optional[float]:
    match = _DEBIT_DOWN_RE.search(text)
    return _to_float(match.group(1)) if match else None


def find_debit_up(text: str) -> Optional[float]:
    match = _DEBIT_UP_RE.search(text)
    return _to_float(match.group(1)) if match else None


def find_site_code(text: str) -> Optional[str]:
    match = _SITE_CODE_RE.search(text)
    return match.group(0).upper() if match else None


def find_labeled_value(text: str, label: str, max_len: int = 120) -> Optional[str]:
    """Cherche 'label' (insensible casse/accents approx) suivi de sa valeur
    sur la même ligne ou la ligne suivante."""
    pattern = re.compile(
        re.escape(label) + r"\s*[:\-]?\s*(.{1,%d})" % max_len, re.IGNORECASE
    )
    match = pattern.search(text)
    if not match:
        return None
    value = match.group(1).strip()
    value = value.split("\n")[0].strip()
    return value or None


def find_address(text: str) -> Optional[str]:
    """Heuristique générique : cherche un motif 'N° rue ... CODEPOSTAL VILLE'."""
    match = re.search(
        r"(\d{1,4}\s+[A-Za-zÀ-ÿ'\.\-]+(?:\s+[A-Za-zÀ-ÿ'\.\-]+){0,4}\s*\n?\s*[A-Za-zÀ-ÿ\-]+\s*\(?\d{5}\)?)",
        text,
    )
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else None
