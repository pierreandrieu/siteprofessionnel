# app_plandeclasse/fabrique_ui.py
from __future__ import annotations
from typing import Any, Dict, List, Mapping, Sequence, Set, Tuple

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
    # on s’appuie sur le nom « brut » (CSV) pour correspondre exactement à Eleve.nom
    m: Dict[int, str] = {}
    for s in students:
        sid = int(s["id"])
        nom_brut = str(s.get("name") or f"{s.get('last', '').upper()} {s.get('first', '')}".strip())
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
    Traduit les contraintes issues de l’UI vers tes objets Contrainte,
    en s’appuyant sur ton registre (contrainte_depuis_code).

    - Convertit les IDs d’élèves en noms stables (Eleve.nom) attendus par le registre.
    - Ajoute des `forbid_seat` manquants à partir de `forbidden_keys`.
    - Convertit les placements UI en `exact_seat` (si `respecter_placements_existants`).
    """
    # Index nom -> Eleve pour la fabrique
    index_eleves_par_nom: Dict[str, Eleve] = {e.nom: e for e in eleves}
    ctx = ContexteFabrique(salle=salle, index_eleves_par_nom=index_eleves_par_nom)

    # Id -> nom (stable) via payload UI
    id2nom = _id2nom_map(students_payload)

    out: List[Contrainte] = []

    # 1) contraintes explicites de l’UI
    for c in constraints_ui or []:
        typ: str = str(c.get("type", ""))
        # normalise pour la fabrique:
        code: Dict[str, Any] = {"type": typ}

        if typ in {TypeContrainte.PREMIERES_RANGEES.value,
                   TypeContrainte.DERNIERES_RANGEES.value,
                   TypeContrainte.SEUL_A_TABLE.value,
                   TypeContrainte.VOISIN_VIDE.value,
                   TypeContrainte.EXACT_SEAT.value}:
            # UI stocke 'a' pour l'élève ; la fabrique attend 'eleve'
            sid = int(c.get("a") or c.get("eleve") or c.get("studentId", -1))
            if sid >= 0:
                code["eleve"] = id2nom[sid]
            if "k" in c: code["k"] = int(c["k"])
            if "x" in c: code["x"] = int(c["x"])
            if "y" in c: code["y"] = int(c["y"])
            # UI met 's' ; la fabrique attend 'seat'
            if "s" in c: code["seat"] = int(c["s"])
            if "seat" in c: code["seat"] = int(c["seat"])

        elif typ in {TypeContrainte.ELOIGNES.value,
                     TypeContrainte.MEME_TABLE.value,
                     TypeContrainte.ADJACENTS.value}:
            a_id = int(c["a"])
            b_id = int(c["b"])
            code["a"] = id2nom[a_id]
            code["b"] = id2nom[b_id]
            if "d" in c: code["d"] = int(c["d"])

        elif typ == TypeContrainte.TABLE_INTERDITE.value:
            code["x"] = int(c["x"])
            code["y"] = int(c["y"])

        elif typ == TypeContrainte.SIEGE_INTERDIT.value:
            code["x"] = int(c["x"])
            code["y"] = int(c["y"])
            # 's' UI → 'seat'
            code["seat"] = int(c.get("seat", c.get("s")))

        else:
            # inconnu -> ignore silencieusement
            continue

        out.append(contrainte_depuis_code(code, ctx))

    # 2) sièges interdits additionnels (depuis state.forbidden) sans doublons
    deja = {(int(getattr(c, "x", -999)),
             int(getattr(c, "y", -999)),
             int(getattr(c, "seat", -999)))
            for c in out
            if c.__class__.__name__ == "SiegeDoitEtreVide"}
    for k in (forbidden_keys or []):
        x, y, s = _key_forbid(k)
        if (x, y, s) not in deja:
            out.append(contrainte_depuis_code(
                {"type": TypeContrainte.SIEGE_INTERDIT.value, "x": x, "y": y, "seat": s}, ctx
            ))

    # 3) placements imposés -> exact_seat
    if respecter_placements_existants:
        for k, sid in (placements or {}).items():
            x, y, s = _key_forbid(k)
            code = {
                "type": TypeContrainte.EXACT_SEAT.value,
                "eleve": id2nom[int(sid)],
                "x": x, "y": y, "seat": s,
            }
            out.append(contrainte_depuis_code(code, ctx))

    return out
