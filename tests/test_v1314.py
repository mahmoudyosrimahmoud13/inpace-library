"""v1.31.4: the Downloads page opened /courses/<id>, a page that doesn't exist, and the app window showed a black
page you couldn't leave. Its links now open the course, and any page that doesn't exist sends you home."""
import io
import re
import zipfile
from pathlib import Path

from starlette.testclient import TestClient

from inpace.app import create_app
from inpace.course import files_from_folder, load_course
from inpace.vault import Vault

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / "inpace" / "static" / "app.js").read_text(encoding="utf-8")
TPL = (ROOT / "inpace" / "templates" / "downloads.html").read_text(encoding="utf-8")


def _app(tmp_path):
    v = Vault(tmp_path / "me")
    c = TestClient(create_app(v))
    c.post("/setup", data={"name": "Mona", "lang": "en"})
    v._set_meta("tour_done", "x")
    return v, c


def _course(v, tmp_path):
    folder = tmp_path / "course"
    (folder / "lessons").mkdir(parents=True)
    (folder / "course.yaml").write_text("id: dl-test\ntitle: Downloads test\nversion: 1\nmodules:\n- id: m1\n  title: One\n"
                                        "  lessons:\n  - id: l1\n    title: First\n    file: lessons/l1.md\n", encoding="utf-8")
    (folder / "lessons" / "l1.md").write_text("# First\n\nHello.\n", encoding="utf-8")
    return v.install_course(load_course(files_from_folder(folder)))


def test_downloads_links_open_the_course_page():
    assert '/courses/${encodeURIComponent(c.course)}/go"' in JS
    assert 'href="/courses/{{ d.course.id }}/go"' in TPL
    # no link anywhere in the Downloads page to the bare /courses/<id> address
    assert not re.search(r'/courses/\$\{encodeURIComponent\(c\.course\)\}"', JS)
    assert 'href="/courses/{{ d.course.id }}"' not in TPL


def test_go_opens_the_course_or_the_course_list(tmp_path):
    v, c = _app(tmp_path)
    course = _course(v, tmp_path)
    r = c.get(f"/courses/{course.id}/go", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/courses"          # not started yet: the course list
    c.post(f"/courses/{course.id}/start", data={})
    jid = v.journey_for_course(course.id)
    if jid:                                                                       # started: its own page
        r = c.get(f"/courses/{course.id}/go", follow_redirects=False)
        assert r.headers["location"] == f"/learn/{jid}"
        assert c.get(r.headers["location"]).status_code == 200


def test_a_page_that_does_not_exist_goes_home_instead_of_a_dead_page(tmp_path):
    v, c = _app(tmp_path)
    r = c.get("/courses/dl-test", headers={"accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert c.get("/no/such/page", headers={"accept": "text/html,application/xhtml+xml"}).status_code == 200  # home


def test_data_requests_still_get_a_plain_404(tmp_path):
    v, c = _app(tmp_path)
    r = c.get("/no/such/thing.json", headers={"accept": "application/json"}, follow_redirects=False)
    assert r.status_code == 404
    r = c.post("/no/such/page", headers={"accept": "text/html"}, follow_redirects=False)
    assert r.status_code in (404, 405)
