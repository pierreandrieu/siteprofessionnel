from datetime import date

from django.utils import timezone


def current_school_year(today: date | None = None) -> str:
    """
    Retourne l'année scolaire courante au format 'YYYY-YYYY'.

    Règle :
      - du 1er août au 31 décembre : "année_courante-(année_courante+1)"
      - du 1er janvier au 31 juillet      : "(année_courante-1)-année_courante"
    """
    d = today or timezone.localdate()
    # (si tu préfères éviter timezone : d = date.today())
    if d.month >= 8:
        start = d.year
        end = d.year + 1
    else:
        start = d.year - 1
        end = d.year
    return f"{start}-{end}"
