"""Owner decision 2026-10-13: no GPS. The map (OSM/Leaflet routes while he is out) and the separate "sees" page are
gone from the private pages; what he sees is the eye (dreams asleep, the street outside). The life routes stay as
backend logic only."""
import re
from pathlib import Path

import live_server

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
PAGES = ["about.html", "diary.html", "index.html", "life.html", "room.html", "world.html", "house/index.html"]


def test_no_nav_link_to_map_or_sees():
    for page in PAGES:
        t = (WEB / page).read_text()
        assert not re.search(r'href="/(world|life)\.html"', t), page
        assert not re.search(r'>\s*(sees|map)\s*</a>', t), page


def test_room_has_no_gps_map():
    t = (WEB / "room.html").read_text()
    for gone in ("leaflet", 'id="map"', "mapcard", "tokyo_routes.json", "tokyo_area.json", "L.map(", "see the map"):
        assert gone not in t, gone
    assert 'if (m.type === "eye_state") { onEyeState(m); return; }' in t


def test_brain_page_eye_card_follows_eye_state():
    t = (WEB / "index.html").read_text()
    assert 'if (m.type === "eye_state") { eyeState(m); return; }' in t
    assert 'eyeMode === "off"' in t and "What he sees" in t


def test_old_addresses_lead_home():
    for old in ("/map", "/life", "/life.html", "/sees", "/world.html"):
        assert live_server.OLD_PATHS[old] == "/", old


def test_life_keeps_its_real_routes_for_the_backend():
    import life
    assert set(life.TOKYO["routes"]) >= {"home-bakery", "home-park"}
