import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_cours_index(client):
    resp = client.get(reverse("cours:index"))
    assert resp.status_code == 200


def test_cours_level_route_exists(client):
    # la route existe, même si pas de fichiers pour ce niveau
    resp = client.get(reverse("cours:level", args=["nsi-premiere"]))
    assert resp.status_code in (200, 404)


def test_cours_detail_404_when_missing(client):
    resp = client.get("/cours/1999-2000/NSI_premiere/foo/bar/baz/")
    assert resp.status_code == 404
