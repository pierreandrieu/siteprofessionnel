# plandeclasse/views.py
from __future__ import annotations

"""
Vues de l’application "plandeclasse".

Contenu :
- Pages HTML (index), sonde de santé (sante)
- Endpoints DEV de démonstration (demande_creer / demande_statut)
- Démarrage et polling d’une tâche Celery (solve_start / solve_status)
- Export multi-formats (SVG, PNG, PDF, JSON, TXT, ZIP) avec cache éphémère
- Téléchargement d’artefacts avec nom de fichier correct (Content-Disposition)

Points notables :
- Les artefacts sont stockés en cache (ex. Redis via Django cache backend)
  sous une clé éphémère : pc:{token}:{fmt} (+ pc:{token}:{fmt}:name pour le nom).
- On s’assure que le SVG/PNG ont un fond *opaque* blanc pour éviter le damier.
- Les noms exportés suivent le patron :
  <slug_classe>_config=<code>_<JJ-MM>.<ext>
  et pour l’archive : export_<slug_classe>_config=<code>_<JJ-MM>.zip
"""

import io
import json
import re
import uuid
import zipfile
from datetime import datetime
from typing import Any, Dict, Mapping, Optional, Tuple, TypedDict

from django.core.cache import cache
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseNotAllowed,
    HttpResponseNotFound,
    JsonResponse,
)
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

# ---------------------------------------------------------------------------
# STUB DEV — stockage mémoire (ne pas utiliser tel quel en prod)
# ---------------------------------------------------------------------------

_DEMANDES: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Pages basiques
# ---------------------------------------------------------------------------

def index(request: HttpRequest) -> HttpResponse:
    """
    Page principale (SPA) du plan de classe.
    """
    return render(request, "plandeclasse/index.html")


def sante(request: HttpRequest) -> HttpResponse:
    """
    Sonde de santé (sans DB/cache) — utile pour load balancer / monitoring.
    """
    return JsonResponse({"ok": True, "service": "plandeclasse", "version": 1})


# ---------------------------------------------------------------------------
# Endpoints DEV de démonstration (sans base)
# ---------------------------------------------------------------------------

@csrf_exempt
def demande_creer(request: HttpRequest) -> HttpResponse:
    """
    DEV : enregistre une "demande" en mémoire et renvoie un identifiant.
    Body JSON attendu (structure similaire à l’état front).
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    try:
        data = json.loads((request.body or b"{}").decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HttpResponseBadRequest("JSON invalide")

    demande_id = str(uuid.uuid4())
    _DEMANDES[demande_id] = {
        "statut": "en_attente",
        "entree": data,
    }
    # Stub : on "termine" immédiatement avec un résultat factice
    _DEMANDES[demande_id]["statut"] = "terminee"
    _DEMANDES[demande_id]["resultat"] = {
        "message": "résultat factice — solveur non branché",
        "placements": data.get("placements", {}),
    }
    return JsonResponse({"demande_id": demande_id, "statut": "en_attente"}, status=201)


def demande_statut(request: HttpRequest, demande_id: uuid.UUID) -> HttpResponse:
    """
    DEV : renvoie le statut (et éventuellement le résultat) de la demande.
    """
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    key = str(demande_id)
    d = _DEMANDES.get(key)
    if not d:
        return JsonResponse({"erreur": "demande inconnue"}, status=404)

    rep: Dict[str, Any] = {"demande_id": key, "statut": d.get("statut", "en_attente")}
    if d.get("statut") == "terminee":
        rep["resultat"] = d.get("resultat", {})
    return JsonResponse(rep)


# ---------------------------------------------------------------------------
# Celery : démarrage + polling
# ---------------------------------------------------------------------------

@csrf_exempt
@require_POST
def solve_start(request: HttpRequest) -> HttpResponse:
    """
    Lance la tâche Celery de résolution :
    - Body : JSON de l’état (schema, students, options, constraints, placements…)
    - Réponse : {"task_id": "..."} à poller via solve_status
    """
    from .tasks import t_solve_plandeclasse

    data: Dict[str, Any] = json.loads(request.body or "{}")
    task = t_solve_plandeclasse.delay(data)
    return JsonResponse({"task_id": task.id})


@require_GET
def solve_status(request: HttpRequest, task_id: str) -> HttpResponse:
    """
    Polling d’état (PENDING / STARTED / SUCCESS / FAILURE).
    En cas de SUCCESS, renvoie aussi le résultat (ex. affectations).
    """
    from celery.result import AsyncResult

    ar = AsyncResult(task_id)
    if ar.state in ("PENDING", "RECEIVED", "STARTED", "RETRY"):
        return JsonResponse({"status": ar.state})
    if ar.state == "SUCCESS":
        return JsonResponse(ar.result)  # type: ignore[return-value]

    # FAILURE
    err = ""
    try:
        err = str(ar.result)
    except Exception:
        pass
    return JsonResponse({"status": "FAILURE", "error": err or "échec."})


# ---------------------------------------------------------------------------
# Export multi-formats (SVG, PNG, PDF, JSON, TXT, ZIP)
# ---------------------------------------------------------------------------

class ExportInput(TypedDict, total=False):
    """
    Entrée attendue côté export (alignée avec le front).
    """
    class_name: str
    svg_markup_student: Optional[str]
    svg_markup_teacher: Optional[str]

    svg_markup: Optional[str]
    schema: list[list[int]]
    students: list[dict[str, Any]]
    options: dict[str, Any]
    constraints: list[dict[str, Any]]
    forbidden: list[str]
    placements: dict[str, int]
    name_view: str
    table_offsets: Dict[str, Dict[str, int]]


class ExportArtifacts(TypedDict, total=False):
    """
    Artefacts calculés pour le téléchargement / la zippette.
    """
    svg: bytes
    png: bytes
    pdf: bytes
    json: bytes
    txt: bytes
    zip: bytes


def _slugify_filename(name: str) -> str:
    """
    Transforme un nom libre en un "slug" sûrfichier :
    "2nde 3 / Salle 102" -> "2nde-3-Salle-102"
    """
    safe = re.sub(r"[^\w\-]+", "-", name, flags=re.UNICODE).strip("-_")
    return safe or "classe"


def _now_stamp() -> str:
    """Horodatage compact AAAAMMJJ-HHMM."""
    dt: datetime = timezone.now()
    return dt.strftime("%Y%m%d-%H%M")


def _day_month_stamp() -> str:
    """Horodatage JJ-MM (ex. 31-08)."""
    dt: datetime = timezone.now()
    return dt.strftime("%d-%m")


def _schema_config(schema: list[list[int]]) -> tuple[str, dict]:
    """
    Calcule un code court pour la configuration de salle.
    Exemple : 7 rangées uniformes [2,3,2] -> "7r232".
    Si rangées hétérogènes -> "Nrmix".
    """
    rows = len(schema)
    if rows == 0:
        return "0r0", {"rows": 0, "capacities": [], "uniform_rows": True}

    cap_row = schema[0]
    uniform = all(r == cap_row for r in schema)
    cap_code = "".join(str(n) for n in cap_row) if uniform else "mix"
    code = f"{rows}r{cap_code or '0'}"
    meta = {"rows": rows, "capacities": cap_row, "uniform_rows": uniform}
    return code, meta


def _build_export_json(data: ExportInput, class_name: str) -> bytes:
    """
    Construit un JSON ré-importable (auto-documenté, versionné).
    """
    code, meta = _schema_config(data.get("schema", []))
    export_obj: Dict[str, Any] = {
        "format": "plandeclasse-export",
        "version": 1,
        "exported_at": timezone.now().isoformat(),
        "class_name": class_name,
        "name_view": data.get("name_view"),
        "room_config_code": code,
        "room_config": meta,
        "schema": data.get("schema", []),
        "students": data.get("students", []),
        "options": data.get("options", {}),
        "constraints": data.get("constraints", []),
        "forbidden": data.get("forbidden", []),
        "placements": data.get("placements", {}),
        "table_offsets": data.get("table_offsets", {}),
    }
    return json.dumps(export_obj, ensure_ascii=False, indent=2).encode("utf-8")


def _ensure_svg_background_white(svg_bytes: bytes) -> bytes:
    """
    S’assure qu’un fond opaque blanc recouvre tout le SVG, afin d’éviter
    l’effet "damier" (transparence) dans les viewers / PNG.
    Implémentation pragmatique par insertion <rect width="100%" height="100%" fill="#fff"/>.
    """
    try:
        s = svg_bytes.decode("utf-8", errors="ignore")
    except Exception:
        return svg_bytes

    # Si un rect couvrant 100% existe déjà, on ne touche pas.
    if re.search(r'<rect[^>]+width=["\']100%["\'][^>]+height=["\']100%["\']', s, flags=re.I):
        return svg_bytes

    m = re.search(r"<svg\b[^>]*>", s, flags=re.I)
    if not m:
        return svg_bytes

    insert = '\n  <rect x="0" y="0" width="100%" height="100%" fill="#ffffff"/>\n'
    s2 = s[: m.end()] + insert + s[m.end():]
    return s2.encode("utf-8")


def _svg_from_payload_or_placeholder(data: ExportInput, class_name: str) -> bytes:
    """
    Prend le SVG autonome envoyé par le front (svg_markup) si présent,
    sinon génère un placeholder simple. Ajoute un fond blanc si besoin.
    """
    svg_markup = data.get("svg_markup")
    if isinstance(svg_markup, str) and svg_markup.strip():
        return _ensure_svg_background_white(svg_markup.encode("utf-8"))

    # Fallback placeholder (DEV uniquement)
    w, h = 1200, 800
    title = f"Plan de classe — {class_name}"
    subtitle = f"{len(data.get('students', []))} élèves, {sum(map(len, data.get('schema', [])))} tables"
    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">
  <rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff"/>
  <rect x="0" y="0" width="{w}" height="56" fill="#111827"/>
  <text x="{w // 2}" y="36" fill="#e5e7eb" font-size="24" font-family="system-ui" text-anchor="middle">{title}</text>
  <text x="{w // 2}" y="76" fill="#374151" font-size="16" font-family="system-ui" text-anchor="middle">{subtitle}</text>
  <text x="24" y="{h - 24}" fill="#6b7280" font-size="12" font-family="monospace">placeholder SVG — remplace par ton rendu réel</text>
</svg>"""
    return svg.encode("utf-8")


def _svg_pair_from_payload(data: ExportInput, class_name: str) -> Tuple[bytes, bytes]:
    """
    Construit le couple (SVG élève, SVG prof) à partir du payload.

    Priorités :
      1) Si le payload contient svg_markup_student et svg_markup_teacher, on les utilise.
      2) Sinon, si svg_markup (ancien champ) est présent, on s'en sert comme vue élève
         et on fabrique une "vue prof" fallback identique (même SVG).
      3) Sinon, on fabrique deux placeholders identiques.

    Tous les SVG sont passés dans _ensure_svg_background_white pour imposer un fond opaque.
    """
    # 1) Nouveau front : deux vues explicites
    stu = data.get("svg_markup_student")
    tea = data.get("svg_markup_teacher")
    if isinstance(stu, str) and stu.strip() and isinstance(tea, str) and tea.strip():
        return (
            _ensure_svg_background_white(stu.encode("utf-8")),
            _ensure_svg_background_white(tea.encode("utf-8")),
        )

    # 2) Ancien front : un seul SVG (utilisé pour élève + fallback prof)
    legacy = data.get("svg_markup")
    if isinstance(legacy, str) and legacy.strip():
        b = _ensure_svg_background_white(legacy.encode("utf-8"))
        return (b, b)

    # 3) Pas de SVG du front : placeholders identiques
    ph = _svg_from_payload_or_placeholder(data, class_name)
    return (ph, ph)


def _svg_to_png_pdf(svg_bytes: bytes) -> Tuple[Optional[bytes], Optional[bytes]]:
    """
    Convertit SVG -> PNG/PDF via CairoSVG (si installé).
    - PNG forcé en fond blanc (background_color="white") pour éviter la transparence.
    - PDF est naturellement opaque ; on laisse le même paramètre par cohérence.
    """
    try:
        import cairosvg  # type: ignore
    except Exception:
        return (None, None)

    png_buf, pdf_buf = io.BytesIO(), io.BytesIO()
    cairosvg.svg2png(bytestring=svg_bytes, write_to=png_buf, background_color="white")
    cairosvg.svg2pdf(bytestring=svg_bytes, write_to=pdf_buf, background_color="white")
    return png_buf.getvalue(), pdf_buf.getvalue()


def _package_zip(files: Mapping[str, bytes]) -> bytes:
    """
    Construit une archive ZIP en mémoire, à partir d’un mapping nom -> contenu.
    """
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname, blob in files.items():
            zf.writestr(fname, blob)
    return out.getvalue()


def _cache_artifacts_and_urls(
        request: HttpRequest,
        artifacts: ExportArtifacts,
        names: Optional[Mapping[str, Optional[str]]] = None,
        token: Optional[str] = None,
        ttl_seconds: int = 3600,
) -> Dict[str, str]:
    """
    Stocke chaque artefact en cache et renvoie un dict fmt -> URL de téléchargement.
    Enregistre aussi le nom de fichier (pc:{token}:{fmt}:name) pour l’header.
    """
    tok = token or uuid.uuid4().hex
    fmt_to_url: Dict[str, str] = {}

    for fmt, blob in artifacts.items():
        if not blob:
            continue
        key = f"pc:{tok}:{fmt}"
        cache.set(key, blob, ttl_seconds)

        fname = (names or {}).get(fmt)
        if fname:
            cache.set(f"{key}:name", fname, ttl_seconds)

        url = reverse("plandeclasse:download_artifact", kwargs={"token": tok, "fmt": fmt})
        fmt_to_url[fmt] = url

    return fmt_to_url


@csrf_exempt
@require_POST
def export_plan(request: HttpRequest) -> HttpResponse:
    """
    Génère les artefacts à partir de l’état courant envoyé par le front.

    Entrée (JSON) : ExportInput
      - class_name (obligatoire)
      - svg_markup_student (SVG autonome “vue élève”, recommandé)
      - svg_markup_teacher (SVG autonome “vue prof”, recommandé)
      - (rétro-compat) svg_markup (unique)
      - schema, students, options, constraints, forbidden, placements, name_view

    Sortie (JSON) :
      {
        "status": "OK",
        "download": {
          "student": {"svg": "...", "png": "...", "pdf": "..."},
          "teacher": {"svg": "...", "png": "...", "pdf": "..."},
          "json": "...",
          "zip": "..."
        }
      }
    """
    try:
        data: ExportInput = json.loads((request.body or b"{}").decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "JSON invalide"}, status=400)

    raw_name: str = (data.get("class_name") or "").strip()
    if not raw_name:
        return JsonResponse({"error": "nom de classe requis"}, status=400)

    class_name: str = raw_name
    slug: str = "plan_de_classe_" + _slugify_filename(class_name)

    # Code config (ex. "7r232") + date JJ-MM
    code, _meta = _schema_config(data.get("schema", []))
    stamp: str = _day_month_stamp()

    # Préfixe de base : <classe>_config=<code>_<JJ-MM>
    prefix: str = f"{slug}_config={code}_{stamp}"

    # 1) JSON ré-importable (inchangé)
    json_bytes: bytes = _build_export_json(data, class_name)

    # 2) SVG élève + prof (depuis le payload, avec fallback)
    svg_student_bytes, svg_teacher_bytes = _svg_pair_from_payload(data, class_name)

    # 3) PNG/PDF pour les deux vues (si CairoSVG dispo)
    s_png, s_pdf = _svg_to_png_pdf(svg_student_bytes)
    t_png, t_pdf = _svg_to_png_pdf(svg_teacher_bytes)

    # 4) TXT (contraintes lisibles) — inchangé
    constraints_human = [
        (c.get("human") or json.dumps(c, ensure_ascii=False))
        for c in data.get("constraints", [])
        if str(c.get("type", "")).strip() and not str(c.get("type")).startswith("_")
    ]

    txt_bytes: bytes = ("\n".join(constraints_human) + ("\n" if constraints_human else "")).encode("utf-8")

    # 5) Noms de fichiers publics
    # Vue élève
    s_svg_name: str = f"{prefix}.svg"
    s_png_name: Optional[str] = f"{prefix}.png" if s_png else None
    s_pdf_name: Optional[str] = f"{prefix}.pdf" if s_pdf else None
    # Vue prof (suffixe _vue_prof)
    t_svg_name: str = f"{prefix}_vue_prof.svg"
    t_png_name: Optional[str] = f"{prefix}_vue_prof.png" if t_png else None
    t_pdf_name: Optional[str] = f"{prefix}_vue_prof.pdf" if t_pdf else None
    # Sauvegarde et archive
    json_name: str = f"{prefix}.json"
    txt_name: str = f"{prefix}.txt"
    zip_name: str = f"export_{prefix}.zip"

    # 6) Contenu de l’archive ZIP
    files_for_zip: Dict[str, bytes] = {
        s_svg_name: svg_student_bytes,
        t_svg_name: svg_teacher_bytes,
        json_name: json_bytes,
        txt_name: txt_bytes,
    }
    if s_png:
        files_for_zip[s_png_name] = s_png  # type: ignore[index]
    if s_pdf:
        files_for_zip[s_pdf_name] = s_pdf  # type: ignore[index]
    if t_png:
        files_for_zip[t_png_name] = t_png  # type: ignore[index]
    if t_pdf:
        files_for_zip[t_pdf_name] = t_pdf  # type: ignore[index]

    zip_bytes: bytes = _package_zip(files_for_zip)

    # 7) Mise en cache + URLs de téléchargement (clé "fmt" libre → on nomme explicitement)
    urls_student_teacher: Dict[str, str] = _cache_artifacts_and_urls(
        request,
        artifacts=ExportArtifacts(
            # on sérialise sous des "formats" explicites pour distinguer élève/prof
            **{
                "student_svg": svg_student_bytes,
                "student_png": s_png or b"",
                "student_pdf": s_pdf or b"",
                "teacher_svg": svg_teacher_bytes,
                "teacher_png": t_png or b"",
                "teacher_pdf": t_pdf or b"",
                "json": json_bytes,
                "txt": txt_bytes,
                "zip": zip_bytes,
            }
        ),
        names={
            "student_svg": s_svg_name,
            "student_png": s_png_name,
            "student_pdf": s_pdf_name,
            "teacher_svg": t_svg_name,
            "teacher_png": t_png_name,
            "teacher_pdf": t_pdf_name,
            "json": json_name,
            "txt": txt_name,
            "zip": zip_name,
        },
    )

    # 8) Réponse structurée (front attend .student / .teacher / .json / .zip)
    download_payload: Dict[str, Any] = {
        "student": {
            "svg": urls_student_teacher.get("student_svg"),
            "png": urls_student_teacher.get("student_png"),
            "pdf": urls_student_teacher.get("student_pdf"),
        },
        "teacher": {
            "svg": urls_student_teacher.get("teacher_svg"),
            "png": urls_student_teacher.get("teacher_png"),
            "pdf": urls_student_teacher.get("teacher_pdf"),
        },
        "json": urls_student_teacher.get("json"),
        "zip": urls_student_teacher.get("zip"),
    }

    return JsonResponse({"status": "OK", "download": download_payload})


@require_GET
def download_artifact(request: HttpRequest, token: str, fmt: str) -> HttpResponse:
    """
    Sert un artefact depuis le cache via {token} et {fmt}.

    {fmt} peut maintenant être n’importe quelle clé
    utilisée lors du cache (ex. "student_svg", "teacher_png", "json", "zip", etc.).
    On récupère le nom public depuis le cache pour déterminer le Content-Type ; à défaut,
    """
    import mimetypes

    key = f"pc:{token}:{fmt}"
    blob: Optional[bytes] = cache.get(key)  # type: ignore[assignment]
    if blob is None:
        return HttpResponseNotFound("introuvable ou expiré")

    # Nom de fichier public (si enregistré au moment du caching)
    filename = cache.get(f"{key}:name")  # ex. "plan..._vue_prof.pdf"
    filename_str = str(filename) if filename else None

    # 1) Tentative de déduction du content-type depuis le nom public
    content_type: Optional[str] = None
    if filename_str:
        guessed, _ = mimetypes.guess_type(filename_str)
        if guessed:
            content_type = guessed
            # encodage explicite pour les types textuels connus
            if content_type == "application/json":
                content_type = "application/json; charset=utf-8"
            elif content_type == "text/plain":
                content_type = "text/plain; charset=utf-8"

    # 2) Fallback : déduction simple depuis le suffixe de fmt (après le dernier "_")
    if not content_type:
        base = fmt.rsplit("_", 1)[-1].lower()  # ex. "teacher_pdf" -> "pdf"
        content_type = {
            "svg": "image/svg+xml",
            "png": "image/png",
            "pdf": "application/pdf",
            "txt": "text/plain; charset=utf-8",
            "json": "application/json; charset=utf-8",
            "zip": "application/zip",
        }.get(base, "application/octet-stream")

    resp = HttpResponse(blob, content_type=content_type)
    # Ajoute un nom de fichier propre si on l’a
    if filename_str:
        resp["Content-Disposition"] = f'attachment; filename="{filename_str}"'
    else:
        # Nom par défaut basé sur le fmt, en dernier ressort
        resp["Content-Disposition"] = f'attachment; filename="plandeclasse-export-{fmt}"'
    return resp

