from __future__ import annotations
from typing import Any, Dict, List, Sequence, Tuple, Optional

from celery import shared_task
from django.core.cache import cache
from cairosvg import svg2png, svg2pdf

from .modele.salle import Salle
from .modele.eleve import Eleve
from .contraintes.base import Contrainte
from .fabrique_ui import fabrique_contraintes_ui
from .utils_locks import inject_locked_placements_as_exact_constraints
from .utils_svg import svg_from_layout
from .contraintes.unaires import DoitEtreExactementIci
from .contraintes.structurelles import TableDoitEtreVide, SiegeDoitEtreVide
from .modele.position import Position

# Solveurs disponibles : ASP (Clingo) et CP-SAT (OR-Tools)
from .solveurs.asp import SolveurClingo

try:
    # Import conditionnel pour permettre un fallback si OR-Tools n'est pas installé
    from .solveurs.cpsat import SolveurCPSAT

    _HAS_CPSAT = True
except Exception:
    SolveurCPSAT = None  # type: ignore
    _HAS_CPSAT = False


# --------------------------------------------------------------------------- helpers de conversion

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


def _order_ui_ids(students: Sequence[Dict[str, Any]]) -> List[int]:
    """Indices UI stables (ordonnés par id croissant) pour la reconstruction."""
    return [int(s["id"]) for s in sorted(students, key=lambda z: int(z["id"]))]


def _parse_options(options: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalise les options et pose les défauts.
    Options reconnues (toutes facultatives) :
      - solver: "cpsat" | "asp"
      - prefer_alone: bool
      - prefer_mixage: bool
      - time_budget_ms: int
      - lock_placements: bool
      - random_seed: int | null
      - shuffle_students: bool
      - tiebreak_random: bool
      - vary_each_run: bool  (si true et random_seed absent ⇒ seed aléatoire)
    """
    o = {**options}
    if "lock_placements" not in o and "respect_existing" in o:
        try:
            o["lock_placements"] = bool(o["respect_existing"])
        except Exception:
            pass
    o["solver"] = str(o.get("solver", "asp")).lower().strip()
    o["prefer_alone"] = bool(o.get("prefer_alone", True))
    o["prefer_mixage"] = bool(o.get("prefer_mixage", True))
    o["time_budget_ms"] = int(o.get("time_budget_ms", 60_000))
    o["lock_placements"] = bool(o.get("lock_placements", True))
    o["shuffle_students"] = bool(o.get("shuffle_students", False))
    o["tiebreak_random"] = bool(o.get("tiebreak_random", True))

    seed_raw = o.get("random_seed", None)
    seed: Optional[int]
    if seed_raw is None:
        # graine aléatoire si demandé
        if bool(o.get("vary_each_run", False)):
            import secrets
            seed = secrets.randbelow(2 ** 31 - 1)
        else:
            seed = None
    else:
        try:
            seed = int(seed_raw)
        except Exception:
            seed = None
    o["random_seed"] = seed
    return o


def _make_solver(options: Dict[str, Any]):
    """
    Instancie le solveur en fonction des options.
    Les options de variabilité n'ont d'effet que pour CP-SAT.
    """
    solver_name = options["solver"]
    if solver_name == "cpsat":
        if not _HAS_CPSAT:
            return None, {"status": "FAILURE", "error": "Solveur CPSAT indisponible (OR-Tools non installé)."}
        slv = SolveurCPSAT(  # type: ignore[call-arg]
            prefer_alone=options["prefer_alone"],
            prefer_mixage=options["prefer_mixage"],
            seed=options["random_seed"],
            randomize_order=options["shuffle_students"],
            tiebreak_random=options["tiebreak_random"],
        )
        return slv, None
    else:
        # Solveur ASP (Clingo) — pas de variabilité spécifique ici
        slv = SolveurClingo(
            prefer_alone=options["prefer_alone"],
            prefer_mixage=options["prefer_mixage"],
            models=1,
        )
        return slv, None


def _build_constraints(
        *,
        salle: Salle,
        eleves: Sequence[Eleve],
        students_payload: Sequence[Dict[str, Any]],
        constraints_ui: Sequence[Dict[str, Any]],
        forbidden: Sequence[str],
        placements: Dict[str, int],
        lock_placements: bool,
) -> List[Contrainte]:
    """Traduit l’UI en contraintes métier via la fabrique."""
    return fabrique_contraintes_ui(
        salle=salle,
        eleves=eleves,
        students_payload=students_payload,
        constraints_ui=constraints_ui,
        forbidden_keys=forbidden,
        placements=placements,
        respecter_placements_existants=lock_placements,
    )


def _solve(
        *,
        slv,
        salle: Salle,
        eleves: List[Eleve],
        contraintes: List[Contrainte],
        time_budget_ms: int,
):
    """Exécute la résolution et remonte une structure de résultat homogène."""
    res = slv.resoudre(salle, eleves, contraintes, budget_temps_ms=time_budget_ms)
    if res.affectation is None:
        return None, {
            "status": "FAILURE",
            "error": (
                "Aucune solution trouvée. Vos contraintes sont incompatibles entre elles "
                "ou avec la disposition de la salle. Essayez l’une des pistes suivantes : "
                "modifier les valeurs des paramètres k ou d, retirer une contrainte de groupe, "
                "ou libérer quelques sièges interdits, puis relancez."
            ),
        }
    return res, None


def _reconstruct_assignment(eleves: List[Eleve], ui_ids_in_order: List[int], affectation) -> Dict[str, int]:
    """
    Reconstruit {seatKey -> studentId} en se basant sur l’ordre stable (trié par id)
    et sur la map affectation {Eleve -> Position}.
    """
    assignment: Dict[str, int] = {}
    for idx, e in enumerate(eleves):
        pos = affectation.get(e)
        if pos is None:
            continue
        k = f"{pos.x},{pos.y},{pos.siege}"
        assignment[k] = ui_ids_in_order[idx]
    return assignment


def _render_and_cache_exports(
        *,
        schema: List[List[int]],
        assignment: Dict[str, int],
        students: Sequence[Dict[str, Any]],
        name_view: str,
        forbidden: Sequence[str],
) -> Dict[str, Any]:
    """Génère SVG/PNG/PDF/TXT, met en cache, renvoie les URLs de téléchargement."""
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
    txt_str = ""  # la liste lisible des contraintes est déjà côté UI ; on peut la passer à part si voulu

    import secrets
    token = secrets.token_urlsafe(16)
    cache.set(f"pc:{token}:svg", svg, timeout=3600)
    cache.set(f"pc:{token}:png", png_bytes, timeout=3600)
    cache.set(f"pc:{token}:pdf", pdf_bytes, timeout=3600)
    cache.set(f"pc:{token}:txt", txt_str.encode("utf-8"), timeout=3600)

    return {
        "token": token,
        "svg": f"/plandeclasse/download/{token}/svg",
        "png": f"/plandeclasse/download/{token}/png",
        "pdf": f"/plandeclasse/download/{token}/pdf",
        "txt": f"/plandeclasse/download/{token}/txt",
    }


# --------------------------------------------------------------------------- tâche principale

@shared_task(bind=True)
def t_solve_plandeclasse(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tâche asynchrone de résolution :
      - traduit le payload UI en salle/élèves/contraintes,
      - choisit un solveur (ASP ou CP-SAT) selon options,
      - exécute la résolution avec éventuel budget temps,
      - rend l’affectation et prépare les exports (SVG/PNG/PDF/TXT) en cache.
    """
    # ----------- Lecture du payload brut -----------
    schema: List[List[int]] = payload["schema"]
    students: List[Dict[str, Any]] = payload["students"]  # id, name, first, last, gender
    options_raw: Dict[str, Any] = payload.get("options", {})
    constraints_ui: List[Dict[str, Any]] = payload.get("constraints", [])
    forbidden: List[str] = payload.get("forbidden", [])
    placements: Dict[str, int] = payload.get("placements", {})
    name_view: str = payload.get("name_view", "first")

    # ----------- Normalisation options + modèles métier -----------
    options = _parse_options(options_raw)
    salle = _build_salle(schema)
    eleves = _eleves_from_payload(students)
    order_ui_ids = _order_ui_ids(students)
    if placements and not options_raw.get("lock_placements", False):
        options_raw["lock_placements"] = True

    # ----------- Contrainte(s) depuis l’UI -----------
    contraintes: List[Contrainte] = _build_constraints(
        salle=salle,
        eleves=eleves,
        students_payload=students,
        constraints_ui=constraints_ui,
        forbidden=forbidden,
        placements={},
        lock_placements=False,
    )
    # ----------- Verrouillage des placements existants (exact_seat) -----------
    # mapping id UI -> objet Eleve (même ordre que _order_ui_ids)
    id2eleve = {sid: eleves[i] for i, sid in enumerate(order_ui_ids)}

    inject_locked_placements_as_exact_constraints(
        respect_existing=options["lock_placements"],
        placements=placements,
        id2eleve=id2eleve,
        contraintes=contraintes,
    )
    nb_exact = sum(1 for c in contraintes if isinstance(c, DoitEtreExactementIci))
    print(f"[solve] Placements verrouillés injectés : {nb_exact}")
    # ----------- Choix du solveur -----------
    slv, err = _make_solver(options)
    if err:
        return err

    # ----------- Résolution -----------
    res, err = _solve(
        slv=slv,
        salle=salle,
        eleves=eleves,
        contraintes=contraintes,
        time_budget_ms=options["time_budget_ms"],
    )
    if err:
        return err
    assert res is not None

    # ----------- Reconstruction assignment (seatKey -> studentId UI) -----------
    assignment = _reconstruct_assignment(eleves, order_ui_ids, res.affectation)

    # ----------- Exports (SVG/PNG/PDF/TXT) en cache mémoire -----------
    downloads = _render_and_cache_exports(
        schema=schema,
        assignment=assignment,
        students=students,
        name_view=name_view,
        forbidden=forbidden,
    )

    # ----------- Réponse -----------
    return {
        "status": "SUCCESS",
        "assignment": assignment,
        "download": downloads,
        "solver": "cpsat" if options["solver"] == "cpsat" else "asp",
        "time_budget_ms": options["time_budget_ms"],
        "random_seed": options["random_seed"],
        "shuffle_students": options["shuffle_students"],
        "tiebreak_random": options["tiebreak_random"],
    }
