# utils pour “verrouiller” les placements existants en contraintes exactes
from typing import Dict, Iterable, List, Mapping, Tuple
from plandeclasse.contraintes.unaires import DoitEtreExactementIci
from plandeclasse.modele.position import Position
from plandeclasse.modele.eleve import Eleve
from plandeclasse.contraintes.base import Contrainte


def inject_locked_placements_as_exact_constraints(
        *,
        respect_existing: bool,
        placements: Mapping[str, int],  # "x,y,s" -> studentId
        id2eleve: Mapping[int, Eleve],  # id élève -> objet Eleve
        contraintes: List[Contrainte],  # sera mutée en place
        forbidden_tables: Iterable[Tuple[int, int]] = (),
        forbidden_seats: Iterable[Tuple[int, int, int]] = (),
) -> None:
    """
    Convertit chaque placement verrouillé en contrainte forte "exact_seat".
    Lève ValueError si un verrou tombe sur une table/siège interdit.
    """
    if not respect_existing or not placements:
        return

    forbT = set(forbidden_tables or [])
    forbS = set(forbidden_seats or [])

    for seat_key, sid in placements.items():
        try:
            x_str, y_str, s_str = seat_key.split(",")
            x, y, s = int(x_str), int(y_str), int(s_str)
        except Exception as exc:
            raise ValueError(f"Clé de siège invalide: {seat_key!r}") from exc

        if (x, y) in forbT:
            raise ValueError(f"Placement verrouillé en (x={x}, y={y}) sur une table interdite.")
        if (x, y, s) in forbS:
            raise ValueError(f"Placement verrouillé en (x={x}, y={y}, s={s}) sur un siège interdit.")

        eleve = id2eleve.get(int(sid))
        if eleve is None:
            raise ValueError(f"Élève id={sid} inconnu pour le placement verrouillé {seat_key!r}.")

        contraintes.append(DoitEtreExactementIci(eleve=eleve, ou=Position(x=x, y=y, siege=s)))
