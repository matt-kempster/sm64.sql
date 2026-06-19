#!/usr/bin/env python3
"""Build Map-tab level backgrounds from STROOP's MIT-licensed map assets.

STROOP ships top-down PNG maps for every level plus a Config/MapAssociations.xml
that records the world-coordinate rectangle (x1,x2,z1,z2 in the x/z plane) each
image covers. That rectangle is exactly what lets us register an image behind
the Map tab's object scatter.

This script downloads the chosen image per level, downscales it to WebP, and
writes:
  - web/maps/<folder>.webp          (one optimised image per DB level folder)
  - web/maps.js                     (window.SM64_MAPS manifest of world rects)
  - web/maps/STROOP-LICENSE.txt     (the MIT notice, as the licence requires)

Source: https://github.com/SM64-TAS-ABC/STROOP  (MIT, (c) 2019 SM64 TAS & ABC)
Run from the repo root:  python3 tools/build_maps.py

Coordinate convention (from STROOP's XmlConfigParser/MapUtilities): image
left=x1, right=x2, top=z1 (min z), bottom=z2 (max z) -- north up, +z downward.
"""

import io
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

REPO = "SM64-TAS-ABC/STROOP"
BRANCH = "dev"
RAW = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/STROOP/"
OUT = Path("web/maps")
MANIFEST = Path("web/maps.js")
MAX_DIM = 1024
QUALITY = 82

# Our DB level folder -> {decomp area number: chosen image}. Areas match the
# AREA(index) in the level scripts. Where an area has several floor/Y images we
# take the main one; areas STROOP has no image for (e.g. ttm slide sub-areas 3,
# 4) are simply omitted and get no background. "menu" has no map.
PICKS = {
    "bbh": {1: "BBH Floor 1.png"},
    "bitdw": {1: "BitDW.png"},
    "bitfs": {1: "BitFS 1.png"},
    "bits": {1: "BitS 1.png"},
    "bob": {1: "BoB.png"},
    "bowser_1": {1: "Bowser 1.png"},
    "bowser_2": {1: "Bowser 2.png"},
    "bowser_3": {1: "Bowser 3.png"},
    "castle_courtyard": {1: "Castle Courtyard.png"},
    "castle_grounds": {1: "Castle Grounds.png"},
    "castle_inside": {1: "Castle Floor 1 Lower.png", 2: "Castle Floor 2.png", 3: "Castle Basement.png"},
    "ccm": {1: "CCM.png", 2: "CCM Slide.png"},
    "cotmc": {1: "CotMC.png"},
    "ddd": {1: "DDD 1.png", 2: "DDD 2 Sub.png"},
    "hmc": {1: "HMC 1.png"},
    "jrb": {1: "JRB Ship Afloat.png", 2: "JRB Inside Ship.png"},
    "lll": {1: "LLL.png", 2: "LLL Volcano 1.png"},
    "pss": {1: "PSS 1.png"},
    "rr": {1: "RR.png"},
    "sa": {1: "SA.png"},
    "sl": {1: "SL.png", 2: "SL Igloo.png"},
    "ssl": {1: "SSL.png", 2: "SSL Pyramid 1.png"},
    "thi": {1: "THI Huge.png", 2: "THI Tiny.png", 3: "THI Cave 1.png"},
    "totwc": {1: "TotWC.png"},
    "ttc": {1: "TTC 1.png"},
    "ttm": {1: "TTM.png", 2: "TTM Slide 1.png"},
    "vcutm": {1: "VCutM.png"},
    "wdw": {1: "WDW 1 Low.png", 2: "WDW 2.png"},
    "wf": {1: "WF No Tower.png"},
    "wmotr": {1: "WMotR.png"},
}

MIT_NOTICE = """\
The level map images in this directory are derived from STROOP and are used
under the MIT License.

  STROOP — https://github.com/SM64-TAS-ABC/STROOP
  Copyright (c) 2019 SM64 TAS & ABC

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def fetch(path: str) -> bytes:
    url = RAW + urllib.parse.quote(path)
    with urllib.request.urlopen(url) as resp:
        return resp.read()


def load_coords() -> dict:
    """image filename -> (x1, x2, z1, z2) from MapAssociations.xml.

    Each image filename maps to one rectangle in the XML, so the filename alone
    is a safe key.
    """
    root = ET.fromstring(fetch("Config/MapAssociations.xml").decode("utf-8-sig"))
    out = {}
    for m in root.findall("Map"):
        c = m.find("Coordinates")
        out[m.find("Image").get("path")] = (
            float(c.get("x1")),
            float(c.get("x2")),
            float(c.get("z1")),
            float(c.get("z2")),
        )
    return out


def main() -> None:
    coords = load_coords()
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.webp"):  # clean slate so renamed/removed maps don't linger
        old.unlink()
    (OUT / "STROOP-LICENSE.txt").write_text(MIT_NOTICE)

    manifest = {}
    count = 0
    for folder, areas in sorted(PICKS.items()):
        manifest[folder] = {}
        for area, image in sorted(areas.items()):
            if image not in coords:
                raise SystemExit(f"no coordinates for {folder} area {area}: {image!r}")
            x1, x2, z1, z2 = coords[image]

            im = Image.open(io.BytesIO(fetch(f"Resources/Maps/Map Images/{image}")))
            im = im.convert("RGBA")
            longest = max(im.width, im.height)
            if longest > MAX_DIM:
                scale = MAX_DIM / longest
                im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
            name = f"{folder}_{area}.webp"
            im.save(OUT / name, "WEBP", quality=QUALITY, method=6)
            kb = (OUT / name).stat().st_size / 1024
            print(f"{folder:18} a{area} {image:24} {im.width}x{im.height}  {kb:5.0f} KB")
            manifest[folder][str(area)] = {
                "img": f"maps/{name}",
                "x1": x1,
                "x2": x2,
                "z1": z1,
                "z2": z2,
            }
            count += 1

    lines = [
        '"use strict";',
        "// Generated by tools/build_maps.py -- do not edit by hand.",
        "// Per-(level, area) top-down map backgrounds for the Map tab, keyed by",
        "// level folder then area number. Each entry is the world-space rectangle",
        "// (x/z plane) its image covers: left=x1, right=x2, top=z1, bottom=z2",
        "// (north up, +z downward). Images derived from STROOP (MIT, (c) 2019",
        "// SM64 TAS & ABC) -- see maps/STROOP-LICENSE.txt.",
        "window.SM64_MAPS = {",
    ]
    for folder in sorted(manifest):
        entries = ", ".join(
            f'"{area}": {{ img: "{r["img"]}", '
            f'x1: {r["x1"]:g}, x2: {r["x2"]:g}, z1: {r["z1"]:g}, z2: {r["z2"]:g} }}'
            for area, r in sorted(manifest[folder].items())
        )
        lines.append(f'  "{folder}": {{ {entries} }},')
    lines.append("};")
    MANIFEST.write_text("\n".join(lines) + "\n")
    print(f"\nwrote {count} maps across {len(manifest)} levels -> {MANIFEST}")


if __name__ == "__main__":
    main()
