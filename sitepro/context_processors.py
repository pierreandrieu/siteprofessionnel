from cours.views import current_school_year


def school_year(request):
    return {"cur_year": current_school_year()}