from __future__ import annotations

import json
import uuid
from typing import Any, Dict

from django.http import (
    HttpRequest,
    HttpResponse,
    JsonResponse,
    HttpResponseBadRequest,
    HttpResponseNotAllowed,
)
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

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
