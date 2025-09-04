# app_plandeclasse/tasks.py
from __future__ import annotations
from typing import Any, Dict, List, Sequence

from celery import shared_task
from django.core.cache import cache

from cairosvg import svg2png, svg2pdf

from .modele.salle import Salle
from .modele.eleve import Eleve
from .contraintes.base import Contrainte
from .fabrique_ui import fabrique_contraintes_ui
from .utils_svg import svg_from_layout

# Solveurs disponibles : ASP (Clingo) et CP-SAT (OR-Tools)
from .solveurs.asp import SolveurClingo

try:
    # Import conditionnel pour permettre un fallback si OR-Tools n'est pas installé
    from .solveurs.cpsat import SolveurCPSAT

    _HAS_CPSAT = True
except Exception:
    SolveurCPSAT = None  # type: ignore
    _HAS_CPSAT = False


def _build_salle(schema: List[List[int]]) -> Salle:
    """Construit un objet Salle à partir du schéma UI."""
    return Salle(schema)


def _eleves_from_payload(students: Sequence[Dict[str, Any]]) -> List[Eleve]:
    """
    Convertit le payload UI en objets Eleve.
    Important : 'name' (texte brut CSV) est utilisé pour correspondre exactement à Eleve.nom.
    Le genre est passé tel quel (permet F/G, f/m, féminin/masculin ...).
    """
    out: List[Eleve] = []
    for s in sorted(students, key=lambda z: int(z["id"])):
        nom_brut = str(s.get("name") or f"{s.get('last', '').upper()} {s.get('first', '')}".strip())
        genre = str(s.get("gender") or "")
        out.append(Eleve(nom=nom_brut, genre=genre))
    return out


@shared_task(bind=True)
def t_solve_plandeclasse(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tâche asynchrone de résolution :
      - traduit le payload UI en salle/élèves/contraintes,
      - choisit un solveur (ASP ou CP-SAT) selon options,
      - exécute la résolution avec éventuel budget temps,
      - rend l’affectation et prépare les exports (SVG/PNG/PDF/TXT) en cache.
    """
    # ----------- Lecture du payload -----------
    schema: List[List[int]] = payload["schema"]
    students: List[Dict[str, Any]] = payload["students"]  # id, name, first, last, gender
    options: Dict[str, Any] = payload.get("options", {})
    constraints_ui: List[Dict[str, Any]] = payload.get("constraints", [])
    forbidden: List[str] = payload.get("forbidden", [])
    placements: Dict[str, int] = payload.get("placements", {})
    name_view: str = payload.get("name_view", "first")

    # Budget temps (ms) optionnel côté UI ; défaut 60 s
    budget_ms: int = int(options.get("time_budget_ms", 60_000))

    # ----------- Modèles métier -----------
    salle = _build_salle(schema)
    eleves = _eleves_from_payload(students)

    # Mapping de reconstruction : index solveur -> id UI stable
    order_ui_ids = [int(s["id"]) for s in sorted(students, key=lambda z: int(z["id"]))]

    # ----------- Contrainte(s) depuis l’UI -----------
    contraintes: List[Contrainte] = fabrique_contraintes_ui(
        salle=salle,
        eleves=eleves,
        students_payload=students,
        constraints_ui=constraints_ui,
        forbidden_keys=forbidden,
        placements=placements,
        respecter_placements_existants=True,
    )

    # ----------- Choix du solveur -----------
    solver_name: str = str(options.get("solver", "asp")).lower().strip()
    if solver_name == "cpsat":
        if not _HAS_CPSAT:
            return {"status": "FAILURE", "error": "Solveur CPSAT indisponible (OR-Tools non installé)."}
        # Options de préférences identiques à ASP pour cohérence d’UI
        slv = SolveurCPSAT(  # type: ignore[call-arg]
            prefer_alone=bool(options.get("prefer_alone", True)),
            prefer_mixage=bool(options.get("prefer_mixage", True)),
        )
    else:
        # Solveur ASP (Clingo)
        slv = SolveurClingo(
            prefer_alone=bool(options.get("prefer_alone", True)),
            prefer_mixage=bool(options.get("prefer_mixage", True)),
            models=1,
        )

    # ----------- Résolution -----------
    res = slv.resoudre(salle, eleves, contraintes, budget_temps_ms=budget_ms)

    if res.affectation is None:
        return {
            "status": "FAILURE",
            "error": (
                "Aucune solution trouvée. Vos contraintes sont incompatibles entre elles "
                "ou avec la disposition de la salle. Essayez l’une des pistes suivantes : "
                "modifiez les valeurs des paramètres k ou d pour vos contraintes, "
                "retirer une contrainte de groupe, libérer quelques sièges "
                "interdits, puis relancez."
            ),
        }

    # ----------- Reconstruction assignment (seatKey -> studentId UI) -----------
    assignment: Dict[str, int] = {}
    for idx, e in enumerate(eleves):
        pos = res.affectation.get(e)
        if pos is not None:
            k = f"{pos.x},{pos.y},{pos.siege}"
            assignment[k] = order_ui_ids[idx]

    # ----------- Exports (SVG/PNG/PDF/TXT) en cache mémoire -----------
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
        # Écho optionnel pour debug/traçabilité (non nécessaire côté UI)
        "solver": "cpsat" if solver_name == "cpsat" else "asp",
        "time_budget_ms": budget_ms,
    }
