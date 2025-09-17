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

# Solveurs disponibles
from .solveurs.asp import SolveurClingo  # historique ASP (fallback)

try:
    from .solveurs.cpsat import SolveurCPSAT  # type: ignore

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

    Champs reconnus (tous facultatifs) :
      - solver: "cpsat" | "asp"
      - prefer_alone: bool
      - prefer_mixage: bool
      - time_budget_ms: int
      - lock_placements: bool
      - random_seed: int | null
      - shuffle_students: bool
      - tiebreak_random: bool
      - vary_each_run: bool
      - visual_row_order: list[int] | None
      - geometry: dict | None
      - table_offsets: list | dict | None
      - visual_row_map: dict | None   # ← NEW (peut être posé plus tard par t_solve)
    """
    o: Dict[str, Any] = {**(options or {})}

    # rétro-compat
    if "lock_placements" not in o and "respect_existing" in o:
        try:
            o["lock_placements"] = bool(o["respect_existing"])
        except Exception:
            pass

    # scalaires
    o["solver"] = str(o.get("solver", "asp")).lower().strip()
    o["prefer_alone"] = bool(o.get("prefer_alone", True))
    o["prefer_mixage"] = bool(o.get("prefer_mixage", True))
    o["time_budget_ms"] = int(o.get("time_budget_ms", 60_000))
    o["lock_placements"] = bool(o.get("lock_placements", True))
    o["shuffle_students"] = bool(o.get("shuffle_students", False))
    o["tiebreak_random"] = bool(o.get("tiebreak_random", True))

    # graine
    seed_raw: Any = o.get("random_seed", None)
    if seed_raw is None:
        if bool(o.get("vary_each_run", False)):
            import secrets
            o["random_seed"] = secrets.randbelow(2 ** 31 - 1)
        else:
            o["random_seed"] = None
    else:
        try:
            o["random_seed"] = int(seed_raw)
        except Exception:
            o["random_seed"] = None

    # visual_row_order : liste d’entiers ou None
    vro = o.get("visual_row_order", None)
    if isinstance(vro, list):
        try:
            o["visual_row_order"] = [int(v) for v in vro]
        except Exception:
            o["visual_row_order"] = None
    else:
        o["visual_row_order"] = None

    # objets bruts (tolérance)
    if "geometry" in o and not isinstance(o["geometry"], dict):
        o["geometry"] = None
    if "table_offsets" in o and not isinstance(o["table_offsets"], (dict, list)):
        o["table_offsets"] = None

    # visual_row_map est validé plus tard ; on laisse tel quel si présent
    return o


def _make_solver(options: Dict[str, Any]) -> Tuple[Optional[object], Optional[str]]:
    """
    Instancie le solveur depuis `options` et retourne `(solver, err)`.

    - Si l'UI fournit un ordre visuel (`visual_row_order`) OU une géométrie (`geometry`)
      OU des offsets de tables (`table_offsets`) OU une **visual_row_map** (par table),
      on force **CPSAT** (ordre visuel/px).
    - Sinon, on respecte `options["solver"]` (défaut "asp").
    """
    try:
        solver_name: str = str(options.get("solver", "asp")).lower()

        if options.get("visual_row_order") or options.get("geometry") or options.get("table_offsets") or options.get(
                "visual_row_map"):
            solver_name = "cpsat"

        if solver_name == "cpsat":
            if not _HAS_CPSAT:
                return None, "Solveur CPSAT indisponible (OR-Tools non installé)."

            # Import local (évite un import global lourd)
            try:
                from plandeclasse.solveurs.cpsat import SolveurCPSAT, GeomPixels  # type: ignore
            except Exception as e:
                return None, f"Impossible d'importer SolveurCPSAT/OR-Tools: {e}"

            # --- Géométrie (facultative)
            geom_opts = options.get("geometry")
            geom: Optional["GeomPixels"] = None
            if isinstance(geom_opts, dict):
                try:
                    geom = GeomPixels(
                        table_pitch_x=int(geom_opts.get("table_pitch_x", 1)),
                        table_pitch_y=int(geom_opts.get("table_pitch_y", 1)),
                        seat_pitch_x=int(geom_opts.get("seat_pitch_x", 1)),
                        seat_offset_x=int(geom_opts.get("seat_offset_x", 0)),
                        seat_offset_y=int(geom_opts.get("seat_offset_y", 0)),
                    )
                except Exception as e:
                    return None, f"Géométrie invalide dans options['geometry']: {e}"

            # --- Offsets de tables
            table_offsets_raw = options.get("table_offsets")
            table_offsets: Dict[Tuple[int, int], Tuple[int, int]] = {}
            if isinstance(table_offsets_raw, dict):
                for k, v in table_offsets_raw.items():
                    if isinstance(k, str) and "," in k:
                        try:
                            xs, ys = k.split(",", 1)
                            if isinstance(v, (list, tuple)) and len(v) >= 2:
                                table_offsets[(int(xs), int(ys))] = (int(v[0]), int(v[1]))
                            elif isinstance(v, dict):
                                table_offsets[(int(xs), int(ys))] = (int(v.get("dx", 0)), int(v.get("dy", 0)))
                        except Exception:
                            continue
            elif isinstance(table_offsets_raw, list):
                for item in table_offsets_raw:
                    try:
                        if isinstance(item, (list, tuple)) and len(item) >= 4:
                            x, y, dx, dy = item[0], item[1], item[2], item[3]
                            table_offsets[(int(x), int(y))] = (int(dx), int(dy))
                        elif isinstance(item, dict):
                            x, y = int(item.get("x")), int(item.get("y"))
                            dx, dy = int(item.get("dx", 0)), int(item.get("dy", 0))
                            table_offsets[(x, y)] = (dx, dy)
                    except Exception:
                        continue

            # --- Visual row map (par table) — "x,y" -> rang_visuel
            row_map_ui: Optional[Dict[Tuple[int, int], int]] = None
            vrm_raw = options.get("visual_row_map")
            if isinstance(vrm_raw, dict):
                row_map_ui = {}
                for k, v in vrm_raw.items():
                    try:
                        if isinstance(k, str) and "," in k:
                            xs, ys = k.split(",", 1)
                            row_map_ui[(int(xs), int(ys))] = int(v)
                    except Exception:
                        continue

            row_order_ui: Optional[list[int]] = options.get("visual_row_order")

            slv = SolveurCPSAT(
                prefer_alone=bool(options.get("prefer_alone", True)),
                prefer_mixage=bool(options.get("prefer_mixage", True)),
                seed=options.get("random_seed"),
                randomize_order=bool(options.get("shuffle_students", False)),
                tiebreak_random=bool(options.get("tiebreak_random", True)),
                geom=geom,
                table_offsets=table_offsets or None,
                row_order_ui=row_order_ui or None,
                row_map_ui=row_map_ui or None,  # ← NEW
            )
            return slv, None

        # ---------- Solveur ASP (comportement historique grille) ----------
        try:
            from plandeclasse.solveurs.asp import SolveurASP  # type: ignore
        except Exception as e:
            return None, f"Impossible d'importer SolveurASP: {e}"

        slv = SolveurASP()
        return slv, None

    except Exception as e:
        return None, f"Echec _make_solver: {e}"


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
                "ou avec la disposition de la salle. Essayez : diminuer k/d, retirer une "
                "contrainte de groupe, ou libérer quelques sièges interdits, puis relancez."
            ),
        }
    return res, None


def _reconstruct_assignment(eleves: List[Eleve], ui_ids_in_order: List[int], affectation) -> Dict[str, int]:
    """Reconstruit {seatKey -> studentId} à partir de l’ordre stable (trié par id)."""
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
    txt_str = ""  # (optionnel) liste lisible des contraintes

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
      - exécute la résolution,
      - rend l’affectation et prépare les exports en cache.
    """
    # ----------- Lecture du payload brut -----------
    schema: List[List[int]] = payload["schema"]
    students: List[Dict[str, Any]] = payload["students"]
    options_raw: Dict[str, Any] = payload.get("options", {})
    constraints_ui: List[Dict[str, Any]] = payload.get("constraints", [])
    forbidden: List[str] = payload.get("forbidden", [])
    placements: Dict[str, int] = payload.get("placements", {})
    name_view: str = payload.get("name_view", "first")

    # ----------- Normalisation options + enrichissement visuel -----------
    options = _parse_options(options_raw)

    # Raccroche la visual_row_map si envoyée à la racine du payload (front)
    if "visual_row_map" in payload and isinstance(payload["visual_row_map"], dict):
        options["visual_row_map"] = payload["visual_row_map"]

    salle = _build_salle(schema)
    eleves = _eleves_from_payload(students)
    order_ui_ids = _order_ui_ids(students)

    # 1) Contraintes depuis l’UI (on laisse placements vides ici)
    contraintes: List[Contrainte] = _build_constraints(
        salle=salle,
        eleves=eleves,
        students_payload=students,
        constraints_ui=constraints_ui,
        forbidden=forbidden,
        placements={},  # pas de lock ici
        lock_placements=False,  # idem
    )

    # 2) Injection éventuelle des placements “à verrouiller”, sans doublonner les exact déjà présents
    id2eleve = {sid: eleves[i] for i, sid in enumerate(order_ui_ids)}
    if options["lock_placements"] and placements:
        pinned_eleves = {c.eleve for c in contraintes if isinstance(c, DoitEtreExactementIci)}
        pinned_ids = {sid for sid, e in id2eleve.items() if e in pinned_eleves}
        placements_filtres = {k: v for k, v in placements.items() if int(v) not in pinned_ids}
    else:
        placements_filtres = {}

    inject_locked_placements_as_exact_constraints(
        respect_existing=options["lock_placements"],
        placements=placements_filtres,
        id2eleve=id2eleve,
        contraintes=contraintes,
    )

    # 3) Choix du solveur
    slv, err = _make_solver(options)
    if err:
        return {"status": "FAILURE", "error": err}

    # 4) Résolution
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

    # 5) Reconstruction assignment (seatKey -> studentId UI)
    assignment = _reconstruct_assignment(eleves, order_ui_ids, res.affectation)

    # 6) Exports (SVG/PNG/PDF/TXT) en cache mémoire
    downloads = _render_and_cache_exports(
        schema=schema,
        assignment=assignment,
        students=students,
        name_view=name_view,
        forbidden=forbidden,
    )

    # 7) Réponse
    return {
        "status": "SUCCESS",
        "assignment": assignment,
        "download": downloads,
        "solver": "cpsat" if isinstance(slv, (SolveurCPSAT,)) else "asp",
        "time_budget_ms": options["time_budget_ms"],
        "random_seed": options["random_seed"],
        "shuffle_students": options["shuffle_students"],
        "tiebreak_random": options["tiebreak_random"],
    }
