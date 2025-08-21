# comments in English
def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.content == b"ok"


def test_homepage(client):
    r = client.get("/")
    assert r.status_code == 200


def test_admin_protected(client):
    r = client.get("/super-portal-f0b2b3/", follow=False)
    assert r.status_code in (301, 302)
