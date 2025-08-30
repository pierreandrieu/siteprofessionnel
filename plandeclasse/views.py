from __future__ import annotations

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


@require_GET
def download_artifact(request, token: str, fmt: str):
    """
    Sert un artefact éphémère depuis Redis (pas de disque, pas de DB).
    fmt ∈ {svg, png, pdf, txt}
    """
    key = f"pc:{token}:{fmt}"
    blob = cache.get(key)
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
    return HttpResponseNotFound("format invalide")
