from __future__ import annotations
from typing import Dict, List, Tuple, Sequence, Optional
import html

# Types simples pour éviter les imports lourds côté tâche
SeatKey = str  # "x,y,s"


def svg_from_layout(
        schema: List[List[int]],
        placements: Dict[SeatKey, int],
        students: Dict[int, Dict[str, str]],
        name_view: str = "first",
        forbidden: Optional[set[str]] = None,
        width_min: int = 600,
) -> str:
    """
    Génère un SVG autonome (mêmes dimensions que l'UI) à partir du schéma + affectation.

    - schema: [[2,3,2], ...] (rangées)
    - placements: dict seatKey -> studentId
    - students: {sid: {"first":..., "last":...}}
    - name_view: "first" | "last" | "both"
    - forbidden: set de seatKey
    """
    forbidden = forbidden or set()

    padX, padY = 20, 16
    seatW, tableH = 90, 70
    seatGap, colGap, rowGap = 6, 20, 38

    def key(x, y, s):
        return f"{x},{y},{s}"

    # largeur de chaque rangée
    row_widths = []
    for caps in schema:
        tablesW = sum(c * seatW + (c - 1) * seatGap for c in caps)
        between = (len(caps) - 1) * colGap
        row_widths.append(tablesW + between)
    max_row_w = max(row_widths) if row_widths else width_min
    boardW = max(max_row_w, width_min)

    # Y de départ de chaque rangée
    boardY, boardH = padY, 16
    row_origins_y: List[int] = []
    curY = boardY + boardH + 14
    for _ in schema:
        row_origins_y.append(curY)
        curY += tableH + rowGap

    totalWidth = padX * 2 + max_row_w
    totalHeight = (row_origins_y[-1] if row_origins_y else padY + 32) + tableH + padY

    # pattern hachuré pour sièges interdits
    pattern = (
        '<defs>'
        '<pattern id="forbidPattern" patternUnits="userSpaceOnUse" width="8" height="8">'
        '<rect width="8" height="8" fill="#f3f4f6"/>'
        '<path d="M0,8 l8,-8 M-2,2 l4,-4 M6,10 l4,-4" stroke="#cbd5e1" stroke-width="1"/>'
        '</pattern>'
        '</defs>'
    )

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {totalWidth} {totalHeight}">',
        pattern,
        f'<rect x="{padX + (max_row_w - boardW) / 2:.0f}" y="{boardY}" width="{boardW}" height="{boardH}" '
        'fill="#1f2937" stroke="#111827" stroke-width="1.5" rx="6"></rect>',
        f'<text x="{padX + max_row_w / 2:.0f}" y="{boardY - 4}" text-anchor="middle" '
        'fill="#cbd5e1" font-weight="600" font-size="12">tableau</text>',
    ]

    # noms
    def display_name(sid: int) -> str:
        st = students.get(sid, {})
        if name_view == "first":
            return st.get("first", "")
        if name_view == "last":
            return st.get("last", "") or st.get("first", "")
        return (st.get("first", "") + "\n" + st.get("last", "")).strip()

    for y, caps in enumerate(schema):
        tablesW = sum(c * seatW + (c - 1) * seatGap for c in caps)
        between = (len(caps) - 1) * colGap
        rowW = tablesW + between
        ox = padX + (max_row_w - rowW) / 2
        oy = row_origins_y[y]

        # table rect
        parts.append(
            f'<rect x="{ox:.0f}" y="{oy}" width="{rowW - between}" height="{tableH}" '
            'rx="10" fill="#f1f3f5" stroke="#cfd4da"></rect>'
        )

        for x, cap in enumerate(caps):
            table_width = cap * seatW + (cap - 1) * seatGap
            for s in range(cap):
                sx = ox + s * (seatW + seatGap)
                seat_key = key(x, y, s)
                occ = placements.get(seat_key)
                is_forbid = seat_key in forbidden

                classes = []
                fill_attr = ''
                stroke_attr = ''
                if is_forbid:
                    fill_attr = 'fill="url(#forbidPattern)" '
                    stroke_attr = 'stroke="#9aa4b2" stroke-width="2" stroke-dasharray="4 3" '
                elif occ is not None:
                    fill_attr = 'fill="rgba(11,87,208,0.12)" '
                else:
                    fill_attr = 'fill="rgba(0,0,0,0)" '

                parts.append(
                    f'<rect x="{sx:.0f}" y="{oy}" width="{seatW}" height="{tableH}" {fill_attr}{stroke_attr} '
                    '></rect>'
                )

                # diviseur vertical (entre sièges)
                if s < cap - 1:
                    dx = sx + seatW + seatGap / 2 - 0.5
                    parts.append(
                        f'<rect x="{dx:.0f}" y="{oy + 6}" width="1" height="{tableH - 12}" fill="#e2e8f0" opacity="0.9"></rect>'
                    )

                # croix pour interdit
                if is_forbid:
                    pad = 8
                    x1, y1 = sx + pad, oy + pad
                    x2, y2 = sx + seatW - pad, oy + tableH - pad
                    x3, y3 = sx + pad, oy + tableH - pad
                    x4, y4 = sx + seatW - pad, oy + pad
                    parts.append(
                        f'<path d="M{x1},{y1} L{x2},{y2} M{x3},{y3} L{x4},{y4}" '
                        'stroke="#9aa4b2" stroke-width="1.5" stroke-linecap="round" opacity=".9"></path>'
                    )

                # nom si occupé (avec petite logique de 2 lignes)
                if occ is not None:
                    nm = html.escape(display_name(occ))
                    lines = nm.split("\n")
                    cx = sx + seatW / 2
                    cy = oy + tableH / 2
                    # taille de base (le front fait mieux le fitting, ici on simplifie)
                    parts.append(
                        f'<text x="{cx:.0f}" y="{cy:.0f}" text-anchor="middle" fill="#212529" font-weight="600" font-size="14">'
                        + (f'<tspan x="{cx:.0f}" dy="0">{lines[0]}</tspan>' +
                           (f'<tspan x="{cx:.0f}" dy="16">{html.escape(lines[1])}</tspan>' if len(lines) > 1 else ""))
                        + '</text>'
                    )
            ox += table_width + colGap

    parts.append("</svg>")
    return "".join(parts)
