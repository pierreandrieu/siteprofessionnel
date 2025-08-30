# app_plandeclasse/tasks.py
from __future__ import annotations
from typing import Any, Dict, List, Sequence

from celery import shared_task
from django.core.cache import cache

from cairosvg import svg2png, svg2pdf

from .modele.salle import Salle
from .modele.eleve import Eleve
from .solveurs.asp import SolveurClingo
from .contraintes.base import Contrainte
from .fabrique_ui import fabrique_contraintes_ui
from .utils_svg import svg_from_layout


def _build_salle(schema: List[List[int]]) -> Salle:
    return Salle(schema)


def _eleves_from_payload(students: Sequence[Dict[str, Any]]) -> List[Eleve]:
    # IMPORTANT : on utilise 'name' (CSV brut) pour coller à Eleve.nom
    out: List[Eleve] = []
    for s in sorted(students, key=lambda z: int(z["id"])):
        nom_brut = str(s.get("name") or f"{s.get('last', '').upper()} {s.get('first', '')}".strip())
        genre = str(s.get("gender") or "")
        out.append(Eleve(nom=nom_brut, genre=genre))
    return out


@shared_task(bind=True)
def t_solve_plandeclasse(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    schema: List[List[int]] = payload["schema"]
    students: List[Dict[str, Any]] = payload["students"]  # doit contenir id, name, first, last, gender
    options: Dict[str, Any] = payload.get("options", {})
    constraints_ui: List[Dict[str, Any]] = payload.get("constraints", [])
    forbidden: List[str] = payload.get("forbidden", [])
    placements: Dict[str, int] = payload.get("placements", {})
    name_view: str = payload.get("name_view", "first")

    salle = _build_salle(schema)
    eleves = _eleves_from_payload(students)

    # mapping d’ordre : id_clingo -> id_UI
    order_ui_ids = [int(s["id"]) for s in sorted(students, key=lambda z: int(z["id"]))]

    # Contraines (UI → objets)
    contraintes: List[Contrainte] = fabrique_contraintes_ui(
        salle=salle,
        eleves=eleves,
        students_payload=students,
        constraints_ui=constraints_ui,
        forbidden_keys=forbidden,
        placements=placements,
        respecter_placements_existants=True,  # change à False si tu veux ignorer les placements imposés
    )

    # Solveur
    slv = SolveurClingo(
        prefer_alone=bool(options.get("prefer_alone", True)),
        prefer_mixage=bool(options.get("prefer_mixage", True)),
        models=1,
    )
    res = slv.resoudre(salle, eleves, contraintes, budget_temps_ms=60_000)
    if res.affectation is None:
        return {"status": "FAILURE", "error": "Aucune solution trouvée."}

    # Reconstruction : seatKey -> studentId (IDs UI)
    assignment: Dict[str, int] = {}
    for sid_clingo, e in enumerate(eleves):
        pos = res.affectation.get(e)
        if pos is not None:
            k = f"{pos.x},{pos.y},{pos.siege}"
            assignment[k] = order_ui_ids[sid_clingo]

    # SVG + exports (en mémoire uniquement)
    students_map = {
        int(s["id"]): {"first": s.get("first", ""), "last": s.get("last", "")}
        for s in students
    }
    svg = svg_from_layout(
        schema=schema,
        placements=assignment,
        students=students_map,
        name_view=name_view,
        forbidden=set(forbidden),
    )
    png_bytes = svg2png(bytestring=svg.encode("utf-8"))
    pdf_bytes = svg2pdf(bytestring=svg.encode("utf-8"))
    txt_str = "\n".join(c.get("human", str(c)) for c in constraints_ui)

    import secrets
    token = secrets.token_urlsafe(16)
    cache.set(f"pc:{token}:svg", svg, timeout=3600)
    cache.set(f"pc:{token}:png", png_bytes, timeout=3600)
    cache.set(f"pc:{token}:pdf", pdf_bytes, timeout=3600)
    cache.set(f"pc:{token}:txt", txt_str.encode("utf-8"), timeout=3600)

    return {
        "status": "SUCCESS",
        "assignment": assignment,
        "download": {
            "token": token,
            "svg": f"/plandeclasse/download/{token}/svg",
            "png": f"/plandeclasse/download/{token}/png",
            "pdf": f"/plandeclasse/download/{token}/pdf",
            "txt": f"/plandeclasse/download/{token}/txt",
        },
    }
