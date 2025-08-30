from pathlib import Path
import json

from plandeclasse.modele.salle import Salle
from plandeclasse.modele.eleve import Eleve
from plandeclasse.contraintes.base import Contrainte
from plandeclasse.fabrique_ui import fabrique_contraintes_ui


def _eleves_from_students(students):
    return [Eleve(nom=s["name"], genre=s.get("gender") or "") for s in students]


def test_fabrique_ui_translates_constraints():
    payload = json.loads((Path(__file__).parent / "data" / "payload_mix.json").read_text(encoding="utf-8"))
    salle = Salle(payload["schema"])
    eleves = _eleves_from_students(payload["students"])
    contraintes = fabrique_contraintes_ui(
        salle=salle,
        eleves=eleves,
        students_payload=payload["students"],
        constraints_ui=payload["constraints"],
        forbidden_keys=payload["forbidden"],
        placements=payload["placements"],
        respecter_placements_existants=True,
    )
    assert contraintes, "aucune contrainte construite"
    types = {c.type_contrainte().value for c in contraintes}
    assert "front_rows" in types
    assert "far_apart" in types
    assert "same_table" in types
    assert "forbid_seat" in types  # vient de forbidden_keys -> SiegeDoitEtreVide
