from cours.views import current_school_year


def school_year(request):
    return {"cur_year": current_school_year()}


def csp_nonce(request):
    return {"csp_nonce": getattr(request, "csp_nonce", "")}