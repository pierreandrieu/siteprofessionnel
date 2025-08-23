from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def home(request: HttpRequest) -> HttpResponse:
    """
    Render the public homepage.
    """
    return render(request, "pages/home.html")


def about(request: HttpRequest) -> HttpResponse:
    """
    Render a simple 'about' page (professional profile).
    """
    return render(request, "pages/about.html")
