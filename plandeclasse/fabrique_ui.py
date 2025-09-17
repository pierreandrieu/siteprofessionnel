# app_plandeclasse/fabrique_ui.py
from __future__ import annotations
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from .contraintes.registre import ContexteFabrique, contrainte_depuis_code
from .contraintes.base import Contrainte
from .contraintes.types import TypeContrainte
from .modele.eleve import Eleve
from .modele.salle import Salle


# --- helpers ---------------------------------------------------------------

def _key_forbid(k: str) -> Tuple[int, int, int]:
    x, y, s = (int(t) for t in k.split(","))
    return (x, y, s)


def _id2nom_map(students: Sequence[Dict[str, Any]]) -> Dict[int, str]:
    m: Dict[int, str] = {}
    for s in students:
        sid = int(s["id"])
        nom_brut = str(s.get("name") or (f"{s.get('last', '').upper()} {s.get('first', '')}").strip())
        m[sid] = nom_brut
    return m


# --- public ----------------------------------------------------------------

def fabrique_contraintes_ui(
        *,
        salle: Salle,
        eleves: Sequence[Eleve],
        students_payload: Sequence[Dict[str, Any]],
        constraints_ui: Sequence[Dict[str, Any]],
        forbidden_keys: Sequence[str],
        placements: Mapping[str, int],
        respecter_placements_existants: bool = True,
) -> List[Contrainte]:
    """
    Traduit la liste brute des contraintes UI en objets métier via le registre.
    - Propage désormais 'metric' pour front/back rows, et
      'metric'/'en_pixels' pour far_apart.
    - Tolère les clés UI optionnelles et plusieurs formats de clés siège.
    """
    index_eleves_par_nom: Dict[str, Eleve] = {e.nom: e for e in eleves}
    ctx = ContexteFabrique(salle=salle, index_eleves_par_nom=index_eleves_par_nom)
    id2nom = _id2nom_map(students_payload)

    out: List[Contrainte] = []

    for c in constraints_ui or []:
        typ: str = str(c.get("type", "")).strip()
        if typ in {"_batch_marker_", "_objective_", ""}:
            continue

        code: Dict[str, Any] = {"type": typ}

        # ---------- Unaires ----------
        if typ in {
            TypeContrainte.PREMIERES_RANGEES.value,
            TypeContrainte.DERNIERES_RANGEES.value,
            TypeContrainte.SEUL_A_TABLE.value,
            TypeContrainte.VOISIN_VIDE.value,
            TypeContrainte.NO_ADJACENT.value,
            TypeContrainte.EXACT_SEAT.value,
        }:
            sid_raw = c.get("eleve", c.get("a", c.get("studentId")))
            if sid_raw is None:
                continue
            sid = int(sid_raw)
            code["eleve"] = id2nom.get(sid)
            if not code["eleve"]:
                continue

            if "k" in c:
                code["k"] = int(c["k"])

            # propage 'metric' pour front/back rows si présent (grid | px)
            if typ in {TypeContrainte.PREMIERES_RANGEES.value, TypeContrainte.DERNIERES_RANGEES.value}:
                if "metric" in c and str(c["metric"]).strip():
                    code["metric"] = str(c["metric"]).strip().lower()

            # EXACT_SEAT : accepte key="x,y,s" ou bien x/y/s séparés
            if typ == TypeContrainte.EXACT_SEAT.value:
                if "key" in c and isinstance(c["key"], str):
                    xx, yy, ss = _key_forbid(c["key"])
                    code["x"], code["y"], code["seat"] = xx, yy, ss
                else:
                    if "x" in c: code["x"] = int(c["x"])
                    if "y" in c: code["y"] = int(c["y"])
                    if "s" in c: code["seat"] = int(c["s"])
                    if "seat" in c: code["seat"] = int(c["seat"])

        # ---------- Binaires ----------
        elif typ in {
            TypeContrainte.ELOIGNES.value,
            TypeContrainte.MEME_TABLE.value,
            TypeContrainte.ADJACENTS.value,
        }:
            try:
                a_id = int(c["a"])
                b_id = int(c["b"])
            except Exception:
                continue
            code["a"] = id2nom.get(a_id)
            code["b"] = id2nom.get(b_id)
            if not code["a"] or not code["b"]:
                continue

            if "d" in c:  # far_apart
                code["d"] = int(c["d"])
            # propage 'metric' / 'en_pixels' si présents (tolérant)
            if "metric" in c and str(c["metric"]).strip():
                code["metric"] = str(c["metric"]).strip().lower()
            if "en_pixels" in c:
                code["en_pixels"] = bool(c["en_pixels"])

        # ---------- Structurelles ----------
        elif typ == TypeContrainte.TABLE_INTERDITE.value:
            code["x"] = int(c["x"])
            code["y"] = int(c["y"])

        elif typ == TypeContrainte.SIEGE_INTERDIT.value:
            if "key" in c and isinstance(c["key"], str):
                xx, yy, ss = _key_forbid(c["key"])
                code["x"], code["y"], code["seat"] = xx, yy, ss
            else:
                code["x"] = int(c["x"])
                code["y"] = int(c["y"])
                code["seat"] = int(c.get("seat", c.get("s")))

        else:
            continue

        out.append(contrainte_depuis_code(code, ctx))

    # ---------- Sièges interdits additionnels ----------
    deja = {
        (int(getattr(c, "x", -999)), int(getattr(c, "y", -999)), int(getattr(c, "seat", -999)))
        for c in out if c.__class__.__name__ == "SiegeDoitEtreVide"
    }
    for k in (forbidden_keys or []):
        x, y, s = _key_forbid(k)
        if (x, y, s) not in deja:
            out.append(contrainte_depuis_code(
                {"type": TypeContrainte.SIEGE_INTERDIT.value, "x": x, "y": y, "seat": s}, ctx
            ))

    # ---------- Placements imposés -> exact_seat (optionnel) ----------
    if respecter_placements_existants:
        deja_exact = {
            getattr(c, "eleve").nom
            for c in out
            if c.__class__.__name__ == "DoitEtreExactementIci"
        }
        for k, sid in (placements or {}).items():
            x, y, s = _key_forbid(k)
            nom = id2nom.get(int(sid))
            if not nom or nom in deja_exact:
                continue
            out.append(contrainte_depuis_code(
                {"type": TypeContrainte.EXACT_SEAT.value, "eleve": nom, "x": x, "y": y, "seat": s}, ctx
            ))

    return out

