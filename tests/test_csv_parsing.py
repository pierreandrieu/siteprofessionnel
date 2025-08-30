from pathlib import Path


def _extract_gender(cell: str) -> str | None:
    s = (cell or "").strip().lower()
    if s in {"f", "g", "m"}:
        return s.upper()
    if "icon_venus" in s:
        return "F"
    if "icon_mars" in s:
        return "M"
    return None


def test_old_csv_maps_F_G(tmp_path: Path):
    p = Path(__file__).parent / "data" / "pronote_old.csv"
    rows = p.read_text(encoding="utf-8").splitlines()[1:]
    g = [_extract_gender(line.split(";")[3]) for line in rows]
    assert g == ["F", "G"]


def test_new_csv_maps_icons(tmp_path: Path):
    p = Path(__file__).parent / "data" / "pronote_new.csv"
    rows = p.read_text(encoding="utf-8").splitlines()[1:]
    g = [_extract_gender(line.split(";")[3]) for line in rows]
    assert g == ["F", "M"]
