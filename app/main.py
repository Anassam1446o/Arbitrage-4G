from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import config
from app.anfr_client import get_radio_environment
from app.decision_engine import arbitrate
from app.ftto import check_eligibility
from app.geocoding import geocode_address
from app.models import AuditReport, FttoEligibility, MesReport
from app.parsers.audit_parser import parse_audit
from app.parsers.mes_parser import parse_mes

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="Arbitrage 4G")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _save_upload(upload: Optional[UploadFile], tmp_dir: Path) -> Optional[str]:
    if upload is None or not upload.filename:
        return None
    dest = tmp_dir / upload.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    return str(dest)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/analyser", response_class=HTMLResponse)
async def analyser(
    request: Request,
    fichier_audit: UploadFile = File(None),
    fichier_mes: UploadFile = File(None),
    fichier_ftto: UploadFile = File(None),
    toit_starlink: str = Form("inconnu"),
):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        audit_path = _save_upload(fichier_audit, tmp_dir)
        mes_path = _save_upload(fichier_mes, tmp_dir)
        ftto_path = _save_upload(fichier_ftto, tmp_dir)

        if not mes_path:
            return templates.TemplateResponse(
                "index.html",
                {"request": request, "erreur": "Le rapport de Mise en Service est obligatoire."},
            )

        audit: AuditReport = parse_audit(audit_path) if audit_path else AuditReport()
        mes: MesReport = parse_mes(mes_path)

        adresse = mes.adresse or audit.adresse
        geo = geocode_address(adresse) if adresse else None

        anfr_summary: list = []
        anfr_available = False
        if geo:
            anfr_summary, anfr_available = get_radio_environment(geo.lat, geo.lon)

        if ftto_path:
            ftto = check_eligibility(ftto_path, adresse=adresse, site_code=mes.site_code or audit.site_code)
        else:
            ftto = FttoEligibility(eligible=None, trouve=False, detail="Aucun fichier FTTO fourni pour cette analyse.")

        toit_map = {"oui": True, "non": False, "inconnu": None}
        toit_valeur = toit_map.get(toit_starlink, None)
        toit_deduit_de_audit = False
        if toit_valeur is None and audit.antenne_exterieure_autorisee is not None:
            # Proxy imparfait mais utile : le refus/l'accord d'une antenne
            # extérieure par le responsable de site est un bon indicateur
            # (pas une preuve) de faisabilité pour un boîtier Starlink.
            toit_valeur = audit.antenne_exterieure_autorisee
            toit_deduit_de_audit = True

        recommendation = arbitrate(
            audit=audit,
            mes=mes,
            anfr_summary=anfr_summary,
            anfr_available=anfr_available,
            ftto=ftto,
            toit_degage_et_proprietaire=toit_valeur,
        )

        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "audit": audit,
                "mes": mes,
                "geo": geo,
                "anfr_summary": anfr_summary,
                "anfr_available": anfr_available,
                "ftto": ftto,
                "reco": recommendation,
                "starlink_price": config.STARLINK_MONTHLY_PRICE_EUR,
                "toit_deduit_de_audit": toit_deduit_de_audit,
            },
        )
