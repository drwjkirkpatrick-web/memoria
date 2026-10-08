"""Step 18: visitor page — generated HTML honors the API contract."""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memoria.visitor_page import render_page, write_page, qr_payload


def test_page_is_self_contained(tmp_path):
    p = write_page(str(tmp_path / "visit.html"), person_id="person_x")
    html = p.read_text(encoding="utf-8")
    # no external assets: no <link>, no <script src>
    assert "<script src" not in html
    assert "<link" not in html
    assert html.startswith("<!DOCTYPE html>")
    assert html.rstrip().endswith("</html>")


def test_page_bakes_in_api_contract(tmp_path):
    html = render_page(api_base="http://192.168.1.5:8093", person_id="person_x")
    assert "http://192.168.1.5:8093" in html
    assert "person_x" in html
    # the routes the page calls must exist in the server
    for route in ("/people", "/ask", "/voice", "/timeline", "/letters"):
        assert f'"{route}' in html or route in html, f"missing route {route}"
    # role defaults to public
    assert '"public"' in html or "public" in html


def test_page_mentions_refusal_path(tmp_path):
    html = render_page()
    # the page must show refusals gently, not as errors
    assert "refused" in html


def test_qr_payload(tmp_path):
    url = qr_payload("http://192.168.1.5:8093", "person_x")
    assert url == "http://192.168.1.5:8093/visit.html?person=person_x&role=public"
