"""
[MEMO-PDF] v2 — le PDF fabriqué par le serveur (WeasyPrint), rangé dans `uploads/pdf/`, à jour tout seul.

Même gabarit que la vue imprimable [MEMO-PRINT] : le PDF n'est que `print.html` passé à WeasyPrint.
Ce qui est protégé ici :
1. le PDF est un vrai PDF, A5, et les kanji y sont (police CJK embarquée — LE test qui conditionne
   le deploy : un PDF de voyage au Japon sans 入口 ne sert à rien) ;
2. le cache : servi tel quel tant que l'empreinte ne bouge pas, régénéré sinon ;
3. l'empreinte suit le contenu, la structure ET la version du gabarit ;
4. le sweep régénère les périmés, plafonné, et deux workers ne génèrent pas la même cible ;
5. la purge suit le dossier ;
6. l'invité reçoit SA projection, jamais le PDF de l'owner ni rien hors périmètre (invariant 5) ;
7. sans WeasyPrint : 503 propre, et la v1 Imprimer marche toujours ;
8. export inchangé : ni `pdf_cache` ni `pdf/` n'y entrent.

WeasyPrint est RÉEL ici (pas de mock du rendu) : c'est le rendu lui-même qu'on veut éprouver.
"""
import io
import os
import threading

import pytest

pytestmark = pytest.mark.unit

# Import DUR, pas importorskip : le test kanji conditionne le deploy, il ne doit jamais se
# « sauter » en silence faute de dépendance (zéro skip, [CI-HYGIENE]).
import pdfminer.high_level as pdfminer  # noqa: E402


def _texte(pdf_bytes):
    return pdfminer.extract_text(io.BytesIO(pdf_bytes))


def _folder(c, name, parent_id=None, emoji=""):
    r = c.post("/api/projects", json={"name": name, "emoji": emoji})
    assert r.status_code == 201, r.data
    pid = r.get_json()["id"]
    if parent_id is not None:
        r = c.put("/api/projects/%d" % pid, json={"name": name, "parent_id": parent_id})
        assert r.status_code == 200, r.data
    return pid


def _memo(c, title, project_id, **kw):
    body = {"title": title, "content": kw.pop("content", "<p>%s</p>" % title), "project_id": project_id}
    body.update(kw)
    r = c.post("/api/memos", json=body)
    assert r.status_code in (200, 201), r.data
    return r.get_json()["id"]


def _pdf(c, url):
    r = c.get(url)
    assert r.status_code == 200, r.data[:300]
    assert r.mimetype == "application/pdf"
    data = r.get_data()
    assert data[:5] == b"%PDF-"
    return r, data


def _status(c, url):
    r = c.get(url + "/status")
    assert r.status_code == 200, r.data
    return r.get_json()


def _db(app_module):
    import sqlite3
    conn = sqlite3.connect(app_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _pdf_file(app_module, name):
    return os.path.join(app_module.UPLOAD_DIR, "pdf", name)


@pytest.fixture
def japon(client):
    root = _folder(client, "Voyage Japon", emoji="🗻")
    kyoto = _folder(client, "Activités Kyoto", parent_id=root)
    autre = _folder(client, "Courses")
    ids = {
        "root": root, "kyoto": kyoto, "autre": autre,
        "vol": _memo(client, "Vol AF276", root, due_date="2026-11-01"),
        "temple": _memo(client, "Kinkaku-ji", kyoto, due_date="2026-11-04"),
        "kanji": _memo(client, "Kanji utiles", root, content="<p><b>入口</b> entrée — Déménagement</p>"),
        "lait": _memo(client, "Lait demi-écrémé", autre),
    }
    return client, ids


# ------------------------------------------------------------------------- 1

def test_pdf_dossier_reel_a5_avec_kanji(japon):
    c, ids = japon
    r, data = _pdf(c, "/api/projects/%d/pdf" % ids["root"])
    cd = r.headers.get("Content-Disposition", "")
    assert "attachment" in cd and "Voyage" in cd and ".pdf" in cd, cd
    assert "no-store" in r.headers.get("Cache-Control", "")
    assert r.headers.get("ETag")
    txt = _texte(data)
    for t in ("Vol AF276", "Kinkaku-ji", "Kanji utiles"):
        assert t in txt, "titre du sous-arbre absent du PDF : %s" % t
    assert "Lait demi-écrémé" not in txt
    assert "入口" in txt, "kanji absents du PDF : police CJK non embarquée"
    assert "Déménagement" in txt
    # A5 = 148 × 210 mm = 419,5 × 595,3 pt
    from pdfminer.pdfpage import PDFPage
    pages = list(PDFPage.get_pages(io.BytesIO(data)))
    w, h = pages[0].mediabox[2] - pages[0].mediabox[0], pages[0].mediabox[3] - pages[0].mediabox[1]
    assert abs(w - 419.5) < 2 and abs(h - 595.3) < 2, (w, h)


def test_pdf_memo_seul(japon):
    c, ids = japon
    r, data = _pdf(c, "/api/memos/%d/pdf" % ids["kanji"])
    txt = _texte(data)
    assert "入口" in txt and "Vol AF276" not in txt
    c.delete("/api/memos/%d" % ids["kanji"])
    assert c.get("/api/memos/%d/pdf" % ids["kanji"]).status_code == 404
    assert c.get("/api/projects/99999/pdf").status_code == 404


# ------------------------------------------------------------------------- 2

def test_cache_servi_puis_regenere(japon, app_module):
    c, ids = japon
    url = "/api/projects/%d/pdf" % ids["root"]
    assert _status(c, url)["fresh"] is False          # jamais généré
    _pdf(c, url)
    st = _status(c, url)
    assert st["fresh"] is True and st["size"] > 0 and st["generated_at"]
    chemin = _pdf_file(app_module, app_module._pdf_filename(_db(app_module), "project", ids["root"], 0))
    mt = os.stat(chemin).st_mtime_ns
    _pdf(c, url)
    assert os.stat(chemin).st_mtime_ns == mt, "PDF à jour régénéré pour rien"
    c.put("/api/memos/%d" % ids["vol"], json={"title": "Vol AF276 modifié", "content": "<p>x</p>"})
    assert _status(c, url)["fresh"] is False
    _, data = _pdf(c, url)
    assert "Vol AF276 modifié" in _texte(data)
    assert _status(c, url)["fresh"] is True
    mt = os.stat(chemin).st_mtime_ns
    _pdf(c, url + "?force=1")
    assert os.stat(chemin).st_mtime_ns != mt, "?force=1 n'a pas régénéré"


# ------------------------------------------------------------------------- 3

def test_empreinte_suit_contenu_structure_gabarit_corbeille(japon, app_module, monkeypatch):
    c, ids = japon
    url = "/api/projects/%d/pdf" % ids["root"]

    def perime_apres(geste):
        _pdf(c, url)
        assert _status(c, url)["fresh"] is True
        geste()
        assert _status(c, url)["fresh"] is False, geste.__name__

    def ajout():
        _memo(c, "Nouveau", ids["kyoto"])

    def renommage():
        c.put("/api/projects/%d" % ids["kyoto"], json={"name": "Kyoto bis", "parent_id": ids["root"]})

    def gabarit():
        monkeypatch.setattr(app_module, "PRINT_TEMPLATE_VERSION", app_module.PRINT_TEMPLATE_VERSION + 1)

    def corbeille():
        c.delete("/api/memos/%d" % ids["temple"])

    for g in (ajout, renommage, gabarit, corbeille):
        perime_apres(g)
    _, data = _pdf(c, url)
    assert "Kinkaku-ji" not in _texte(data), "mémo en corbeille dans le PDF (invariant 7)"


def test_empreinte_ignore_le_dossier_voisin(japon):
    c, ids = japon
    url = "/api/projects/%d/pdf" % ids["root"]
    _pdf(c, url)
    _memo(c, "Pain", ids["autre"])
    assert _status(c, url)["fresh"] is True


# ------------------------------------------------------------------------- 4

def test_sweep_genere_les_perimes_puis_rien(japon, app_module):
    c, ids = japon
    n = app_module._pdf_sweep(limit=20, pause=0)
    assert n >= 3, n                                  # root, kyoto, autre (dossiers avec mémos)
    assert _status(c, "/api/projects/%d/pdf" % ids["root"])["fresh"] is True
    assert _status(c, "/api/projects/%d/pdf" % ids["kyoto"])["fresh"] is True
    assert app_module._pdf_sweep(limit=20, pause=0) == 0, "2e passage : rien à régénérer"


def test_sweep_plafond(japon, app_module):
    assert app_module._pdf_sweep(limit=1, pause=0) == 1


def test_claim_deux_workers_une_seule_generation(japon, app_module, monkeypatch):
    c, ids = japon
    vrai = app_module._pdf_write
    appels = []
    porte = threading.Event()

    def lent(*a, **k):
        appels.append(1)
        porte.wait(2)
        return vrai(*a, **k)

    monkeypatch.setattr(app_module, "_pdf_write", lent)
    # Simule deux PROCESSUS : chacun sa connexion, et le verrou de processus neutralisé — seul
    # le claim en base peut alors empêcher la double génération.
    import contextlib
    monkeypatch.setattr(app_module, "_PDF_LOCK", contextlib.nullcontext())
    res = []

    def un_worker():
        res.append(app_module._pdf_ensure_standalone("project", ids["root"]))

    t1 = threading.Thread(target=un_worker)
    t2 = threading.Thread(target=un_worker)
    t1.start()
    t2.start()
    import time
    time.sleep(0.5)
    porte.set()
    t1.join(10)
    t2.join(10)
    assert len(appels) == 1, "deux générations concurrentes de la même cible : claim absent"


# ------------------------------------------------------------------------- 5

def test_purge_avec_le_dossier(japon, app_module):
    c, ids = japon
    _pdf(c, "/api/projects/%d/pdf" % ids["kyoto"])
    db = _db(app_module)
    nom = app_module._pdf_filename(db, "project", ids["kyoto"], 0)
    assert os.path.isfile(_pdf_file(app_module, nom))
    assert c.delete("/api/projects/%d" % ids["kyoto"]).status_code == 204
    assert not os.path.isfile(_pdf_file(app_module, nom))
    db = _db(app_module)
    assert db.execute("SELECT COUNT(*) FROM pdf_cache WHERE kind='project' AND target_id=?",
                      (ids["kyoto"],)).fetchone()[0] == 0


# ------------------------------------------------------------------------- 6

def _share(c, kind, target_id):
    r = c.post("/api/shares", json={"kind": kind, "target_id": target_id})
    assert r.status_code in (200, 201), r.data
    return r.get_json()["token"]


def test_invite_recoit_sa_projection(japon, app_module):
    c, ids = japon
    tok = _share(c, "project", ids["kyoto"])
    _, data = _pdf(c, "/share/%s/project/%d/pdf" % (tok, ids["kyoto"]))
    txt = _texte(data)
    assert "Kinkaku-ji" in txt
    for hors in ("Vol AF276", "Kanji utiles", "Lait demi-écrémé", "Voyage Japon"):
        assert hors not in txt, "hors périmètre dans le PDF invité : %s" % hors
    # dossier parent ou voisin : 404
    assert c.get("/share/%s/project/%d/pdf" % (tok, ids["root"])).status_code == 404
    assert c.get("/share/%s/project/%d/pdf" % (tok, ids["autre"])).status_code == 404
    assert c.get("/share/%s/memo/%d/pdf" % (tok, ids["vol"])).status_code == 404
    _, d2 = _pdf(c, "/share/%s/memo/%d/pdf" % (tok, ids["temple"]))
    assert "Kinkaku-ji" in _texte(d2)
    # fichiers owner et invité DISTINCTS
    _pdf(c, "/api/projects/%d/pdf" % ids["kyoto"])
    db = _db(app_module)
    noms = {r["filename"] for r in db.execute("SELECT filename FROM pdf_cache WHERE target_id=? AND kind='project'",
                                              (ids["kyoto"],)).fetchall()}
    assert len(noms) == 2, noms


def test_invite_pas_de_route_hors_share(app_module):
    rules = [r.rule for r in app_module.app.url_map.iter_rules() if "pdf" in r.rule]
    publiques = [r for r in rules if not r.startswith("/api/")]
    assert publiques and all(r.startswith("/share/") for r in publiques), publiques


# ------------------------------------------------------------------------- 7

def test_repli_sans_weasyprint(japon, app_module, monkeypatch):
    c, ids = japon
    monkeypatch.setattr(app_module, "_weasy", lambda: None)
    r = c.get("/api/projects/%d/pdf" % ids["root"])
    assert r.status_code == 503
    assert "indisponible" in r.get_data(as_text=True)
    assert c.get("/api/version").get_json()["pdf_enabled"] is False
    assert c.get("/print/project/%d" % ids["root"]).status_code == 200
    tok = _share(c, "project", ids["kyoto"])
    assert c.get("/share/%s/project/%d/pdf" % (tok, ids["kyoto"])).status_code == 503
    assert app_module._pdf_sweep(limit=20, pause=0) == 0


def test_weasyprint_importe_paresseusement():
    """L'app doit démarrer sans WeasyPrint : aucun import au niveau module."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "..", "app.py"), encoding="utf-8").read()
    for ligne in src.splitlines():
        if ligne.startswith(("import weasyprint", "from weasyprint")):
            pytest.fail("import weasyprint au niveau module : l'app ne démarre plus sans Pango")


def test_version_annonce_pdf_enabled(client):
    assert client.get("/api/version").get_json()["pdf_enabled"] is True


# ------------------------------------------------------------------------- 8

@pytest.mark.invariant
def test_export_inchange(japon):
    c, ids = japon
    _pdf(c, "/api/projects/%d/pdf" % ids["root"])
    exp = c.get("/api/export").get_json()
    assert exp["version"] == 30
    brut = str(exp)
    assert "pdf_cache" not in brut and "pdf/" not in brut and ".pdf" not in brut
