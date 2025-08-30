from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime
from typing import (Tuple, Optional, Mapping, TypedDict)
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET

from .tasks import t_solve_plandeclasse

import json
import uuid
from typing import Any, Dict

from django.http import (
    HttpRequest,
    HttpResponse,
    JsonResponse,
    HttpResponseBadRequest,
    HttpResponseNotAllowed, HttpResponseNotFound,
)
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache

# -----------------------------------------------------------------------------
# Stockage “mémoire” des demandes (DEV UNIQUEMENT).
# Pas de base de données : tout est perdu au redémarrage du processus.
# Ne pas utiliser tel quel en production (les workers ne partagent pas la mémoire).
# -----------------------------------------------------------------------------
_DEMANDES: Dict[str, Dict[str, Any]] = {}


def index(request: HttpRequest) -> HttpResponse:
    """
    Affiche la page du plan de classe.

    Le gabarit contient toute l’interface et s’exécute pour l’instant côté client.
    """
    return render(request, "plandeclasse/index.html")


def sante(request: HttpRequest) -> HttpResponse:
    """
    Sonde de santé très simple (sans DB, sans cache).
    Utile pour les vérifications amont (Nginx/Load Balancer).
    """
    return JsonResponse({"ok": True, "service": "plandeclasse", "version": 1})


@csrf_exempt  # Pour le prototype : on acceptera du JSON sans CSRF. À sécuriser plus tard.
def demande_creer(request: HttpRequest) -> HttpResponse:
    """
    Prototype DEV : enregistre une “demande de résolution” et renvoie un identifiant.

    Corps JSON attendu (aligné avec l’état côté front) :
    {
      "schema": [[2,3,2], [2,3,2], ...],
      "students": [{"id": 0, "name": "...", "gender": "F" | "M" | null}, ...],
      "forbidden": ["x,y,s", ...],
      "placements": {"x,y,s": studentId, ...},
      "options": {"prefer_mixage": true, "prefer_alone": true},
      "constraints": [{"type": "...", ...}, ...]
    }

    Réponse :
      201 Created: {"demande_id": "<uuid>", "statut": "en_attente"}
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    try:
        data = json.loads((request.body or b"{}").decode("utf-8"))
        # Petites vérifications rapides (optionnelles)
        _ = data.get("schema")
        _ = data.get("students")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HttpResponseBadRequest("JSON invalide")

    demande_id = str(uuid.uuid4())
    _DEMANDES[demande_id] = {
        "statut": "en_attente",
        "entree": data,
        # En réel : on mettrait ici l’ID de tâche Celery.
    }

    # Dans ce stub DEV, on “termine” immédiatement avec un résultat factice.
    _DEMANDES[demande_id]["statut"] = "terminee"
    _DEMANDES[demande_id]["resultat"] = {
        "message": "résultat factice — solveur non branché",
        "placements": data.get("placements", {}),
    }

    return JsonResponse({"demande_id": demande_id, "statut": "en_attente"}, status=201)


def demande_statut(request: HttpRequest, demande_id: uuid.UUID) -> HttpResponse:
    """
    Prototype DEV : renvoie le statut et, le cas échéant, le résultat d’une demande.

    Exemples de réponses :
      200 OK: {"demande_id": "...", "statut": "en_attente"}
      200 OK: {"demande_id": "...", "statut": "terminee", "resultat": {...}}
      404   : {"erreur": "demande inconnue"}
    """
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    key = str(demande_id)
    d = _DEMANDES.get(key)
    if not d:
        return JsonResponse({"erreur": "demande inconnue"}, status=404)

    reponse: Dict[str, Any] = {"demande_id": key, "statut": d.get("statut", "en_attente")}
    if d.get("statut") == "terminee":
        reponse["resultat"] = d.get("resultat", {})
    return JsonResponse(reponse)


@csrf_exempt
@require_POST
def solve_start(request):
    """
    Lance la tâche Celery. Le body est le JSON de la page (schema, students, options, constraints, etc.).
    Retourne un task_id à poller.
    """
    import json
    data = json.loads(request.body or "{}")
    task = t_solve_plandeclasse.delay(data)
    return JsonResponse({"task_id": task.id})


@require_GET
def solve_status(request, task_id: str):
    """
    Polling d’état : PENDING / STARTED / SUCCESS / FAILURE.
    En cas de SUCCESS, renvoie aussi assignment + URLs de téléchargement.
    """
    from celery.result import AsyncResult
    ar = AsyncResult(task_id)
    if ar.state in ("PENDING", "RECEIVED", "STARTED", "RETRY"):
        return JsonResponse({"status": ar.state})
    if ar.state == "SUCCESS":
        return JsonResponse(ar.result)
    # FAILURE
    err = ""
    try:
        err = str(ar.result)
    except Exception:
        pass
    return JsonResponse({"status": "FAILURE", "error": err or "échec."}, status=200)


# ----------------------------- Types export ---------------------------------

class ExportInput(TypedDict, total=False):
    class_name: str
    svg_markup: Optional[str]
    schema: list[list[int]]
    students: list[dict[str, Any]]
    options: dict[str, Any]
    constraints: list[dict[str, Any]]
    forbidden: list[str]
    placements: dict[str, int]
    name_view: str


class ExportArtifacts(TypedDict, total=False):
    svg: bytes
    png: bytes
    pdf: bytes
    json: bytes
    txt: bytes
    zip: bytes


def _slugify_filename(name: str) -> str:
    """
    Convertit un nom libre en 'slug' sûr pour les fichiers.
    Ex.: "2nde 3 / Salle 102" -> "2nde-3-Salle-102"
    """
    safe: str = re.sub(r"[^\w\-]+", "-", name, flags=re.UNICODE).strip("-_")
    return safe or "classe"


def _now_stamp() -> str:
    """Horodatage compact pour suffixer les fichiers."""
    dt: datetime = timezone.now()
    return dt.strftime("%Y%m%d-%H%M")


def _build_export_json(data: ExportInput, class_name: str) -> bytes:
    """
    Construit le JSON ré-importable avec toutes les infos nécessaires.
    On garde un format auto-documenté, versionné.
    """
    export_obj: Dict[str, Any] = {
        "format": "plandeclasse-export",
        "version": 1,
        "exported_at": timezone.now().isoformat(),
        "class_name": class_name,
        "name_view": data.get("name_view"),
        "schema": data.get("schema", []),
        "students": data.get("students", []),
        "options": data.get("options", {}),
        "constraints": data.get("constraints", []),
        "forbidden": data.get("forbidden", []),
        "placements": data.get("placements", {}),
    }
    return json.dumps(export_obj, ensure_ascii=False, indent=2).encode("utf-8")


def _svg_from_payload_or_placeholder(data: ExportInput, class_name: str) -> bytes:
    """
    Utilise l’SVG autonome envoyé par le front (svg_markup) si présent,
    sinon renvoie un petit placeholder (DEV).
    """
    svg_markup = data.get("svg_markup")
    if isinstance(svg_markup, str) and svg_markup.strip():
        return svg_markup.encode("utf-8")

    # --- fallback placeholder (uniquement si svg_markup est vide/absent) ---
    w: int = 1200
    h: int = 800
    title: str = f"Plan de classe — {class_name}"
    subtitle: str = f"{len(data.get('students', []))} élèves, {sum(map(len, data.get('schema', [])))} tables"
    svg: str = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">
  <rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff"/>
  <rect x="0" y="0" width="{w}" height="56" fill="#111827"/>
  <text x="{w // 2}" y="36" fill="#e5e7eb" font-size="24" font-family="system-ui" text-anchor="middle">{title}</text>
  <text x="{w // 2}" y="76" fill="#374151" font-size="16" font-family="system-ui" text-anchor="middle">{subtitle}</text>
  <text x="24" y="{h - 24}" fill="#6b7280" font-size="12" font-family="monospace">placeholder SVG — remplace par ton rendu réel</text>
</svg>"""
    return svg.encode("utf-8")


def _svg_to_png_pdf(svg_bytes: bytes) -> Tuple[Optional[bytes], Optional[bytes]]:
    """
    Convertit un SVG en PNG et PDF si CairoSVG est disponible.
    Retourne (png, pdf) – peut contenir None si indisponible.
    """
    try:
        import cairosvg  # type: ignore
    except Exception:
        return (None, None)

    png_buf: io.BytesIO = io.BytesIO()
    pdf_buf: io.BytesIO = io.BytesIO()
    # Conversion – exceptions remontent si problème de rendu
    cairosvg.svg2png(bytestring=svg_bytes, write_to=png_buf)
    cairosvg.svg2pdf(bytestring=svg_bytes, write_to=pdf_buf)
    return (png_buf.getvalue(), pdf_buf.getvalue())


def _package_zip(files: Mapping[str, bytes]) -> bytes:
    """
    Crée une archive ZIP en mémoire avec les paires nom -> contenu.
    """
    out: io.BytesIO = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname, blob in files.items():
            zf.writestr(fname, blob)
    return out.getvalue()


def _cache_artifacts_and_urls(
        request: HttpRequest,
        artifacts: ExportArtifacts,
        token: Optional[str] = None,
        ttl_seconds: int = 3600
) -> Dict[str, str]:
    """
    Stocke les artefacts en cache (clé = pc:{token}:{fmt}) et renvoie
    un dict d'URLs de téléchargement vers download_artifact.
    """
    tok: str = token or uuid.uuid4().hex
    fmt_to_url: Dict[str, str] = {}

    for fmt, blob in artifacts.items():
        if not blob:
            continue
        key: str = f"pc:{tok}:{fmt}"
        cache.set(key, blob, ttl_seconds)
        url: str = reverse("plandeclasse:download_artifact", kwargs={"token": tok, "fmt": fmt})
        fmt_to_url[fmt] = url

    return fmt_to_url


@csrf_exempt
@require_POST
def export_plan(request: HttpRequest) -> HttpResponse:
    """
    Génère les artefacts d'export à partir de l'état courant (POST JSON).
    Retourne des URLs éphémères pour PNG, PDF, SVG, JSON et ZIP.
    """
    try:
        data: ExportInput = json.loads((request.body or b"{}").decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "JSON invalide"}, status=400)

    raw_name: str = (data.get("class_name") or "").strip()
    class_name: str = raw_name or "classe"
    slug: str = _slugify_filename(class_name)
    stamp: str = _now_stamp()
    prefix: str = f"{slug}_{stamp}"

    # 1) JSON ré-importable
    json_bytes: bytes = _build_export_json(data, class_name)

    # 2) SVG du front si présent (sinon placeholder)
    svg_bytes: bytes = _svg_from_payload_or_placeholder(data, class_name)

    # 3) PNG/PDF via CairoSVG si dispo
    png_bytes, pdf_bytes = _svg_to_png_pdf(svg_bytes)

    # 4) TXT (contraintes lisibles)
    constraints_human: list[str] = [
        c.get("human") or json.dumps(c, ensure_ascii=False) for c in data.get("constraints", [])
    ]
    txt_bytes: bytes = ("\n".join(constraints_human) + ("\n" if constraints_human else "")).encode("utf-8")

    # 5) ZIP
    files_for_zip: Dict[str, bytes] = {
        f"{prefix}.svg": svg_bytes,
        f"{prefix}.json": json_bytes,
        f"{prefix}.txt": txt_bytes,
    }
    if png_bytes: files_for_zip[f"{prefix}.png"] = png_bytes
    if pdf_bytes: files_for_zip[f"{prefix}.pdf"] = pdf_bytes
    zip_bytes: bytes = _package_zip(files_for_zip)

    # 6) Cache + URLs
    urls: Dict[str, str] = _cache_artifacts_and_urls(
        request,
        artifacts=ExportArtifacts(
            svg=svg_bytes,
            png=png_bytes or b"",
            pdf=pdf_bytes or b"",
            json=json_bytes,
            txt=txt_bytes,
            zip=zip_bytes,
        )
    )

    return JsonResponse({"status": "OK", "download": urls})


@require_GET
def download_artifact(request: HttpRequest, token: str, fmt: str) -> HttpResponse:
    """
    Sert un artefact éphémère depuis Redis (pas de disque, pas de DB).
    fmt ∈ {svg, png, pdf, txt, json, zip}
    """
    key: str = f"pc:{token}:{fmt}"
    blob: Optional[bytes] = cache.get(key)  # type: ignore[assignment]
    if blob is None:
        return HttpResponseNotFound("introuvable ou expiré")

    if fmt == "svg":
        return HttpResponse(blob, content_type="image/svg+xml")
    if fmt == "png":
        return HttpResponse(blob, content_type="image/png")
    if fmt == "pdf":
        return HttpResponse(blob, content_type="application/pdf")
    if fmt == "txt":
        return HttpResponse(blob, content_type="text/plain; charset=utf-8")
    if fmt == "json":
        return HttpResponse(blob, content_type="application/json; charset=utf-8")
    if fmt == "zip":
        return HttpResponse(blob, content_type="application/zip")

    return HttpResponseNotFound("format invalide")
