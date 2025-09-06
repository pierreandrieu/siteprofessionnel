# utils_constraints.py (or inside your view)
from plandeclasse.contraintes.types import TypeContrainte
from plandeclasse.contraintes.enregistrement import ContexteFabrique


def normalize_ui_constraint(c, id2name):
    """
    Convertit une contrainte UI (ids) en dict 'code_machine' attendu
    par les fabriques (noms stables, clés 'eleve' / 'a'/'b' nominatifs, etc.).
    """
    t = c.get("type")

    # ---- unaires avec id -> nom ----
    if t in {"front_rows", "back_rows", "solo_table", "empty_neighbor", "no_adjacent", "exact_seat"}:
        sid = c.get("a")
        if sid is None:
            raise ValueError(f"contrainte {t}: id élève manquant (clé 'a').")
        name = id2name[int(sid)]
        if t == "front_rows":
            return {"type": t, "eleve": name, "k": int(c.get("k", 1))}
        if t == "back_rows":
            return {"type": t, "eleve": name, "k": int(c.get("k", 1))}
        if t == "solo_table":
            return {"type": t, "eleve": name}
        if t == "empty_neighbor":
            return {"type": t, "eleve": name}
        if t == "no_adjacent":
            return {"type": t, "eleve": name}
        if t == "exact_seat":
            return {"type": t, "eleve": name, "x": int(c["x"]), "y": int(c["y"]), "seat": int(c["s"])}

    # ---- binaires id -> noms ----
    if t in {"same_table", "far_apart"}:
        a = id2name[int(c["a"])]
        b = id2name[int(c["b"])]
        out = {"type": t, "a": a, "b": b}
        if t == "far_apart":
            out["d"] = int(c.get("d", 2))
        return out

    # ---- structurelles (déjà au bon format côté UI) ----
    if t in {"forbid_seat", "forbid_table"}:
        return dict(c)  # x/y/s ok

    # ignorer les marqueurs UI
    if t in {"_batch_marker_", "_objective_"}:
        return None

    raise ValueError(f"type de contrainte inconnu côté serveur: {t!r}")
