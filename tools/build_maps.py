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

# Our DB level folder -> (STROOP numeric level, chosen image). For multi-area /
# multi-floor levels we take the main area's image; "menu" has no map.
PICKS = {
    "bbh": (4, "BBH Floor 1.png"),
    "bitdw": (17, "BitDW.png"),
    "bitfs": (19, "BitFS 1.png"),
    "bits": (21, "BitS 1.png"),
    "bob": (9, "BoB.png"),
    "bowser_1": (30, "Bowser 1.png"),
    "bowser_2": (33, "Bowser 2.png"),
    "bowser_3": (34, "Bowser 3.png"),
    "castle_courtyard": (26, "Castle Courtyard.png"),
    "castle_grounds": (16, "Castle Grounds.png"),
    "castle_inside": (6, "Castle Floor 1 Lower.png"),
    "ccm": (5, "CCM.png"),
    "cotmc": (28, "CotMC.png"),
    "ddd": (23, "DDD 1.png"),
    "hmc": (7, "HMC 1.png"),
    "jrb": (12, "JRB Ship Afloat.png"),
    "lll": (22, "LLL.png"),
    "pss": (27, "PSS 1.png"),
    "rr": (15, "RR.png"),
    "sa": (20, "SA.png"),
    "sl": (10, "SL.png"),
    "ssl": (8, "SSL.png"),
    "thi": (13, "THI Huge.png"),
    "totwc": (29, "TotWC.png"),
    "ttc": (14, "TTC 1.png"),
    "ttm": (36, "TTM.png"),
    "vcutm": (18, "VCutM.png"),
    "wdw": (11, "WDW 1 Low.png"),
    "wf": (24, "WF No Tower.png"),
    "wmotr": (31, "WMotR.png"),
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
    """(level, image) -> (x1, x2, z1, z2) from MapAssociations.xml."""
    root = ET.fromstring(fetch("Config/MapAssociations.xml").decode("utf-8-sig"))
    out = {}
    for m in root.findall("Map"):
        img = m.find("Image").get("path")
        c = m.find("Coordinates")
        out[(int(m.get("level")), img)] = (
            float(c.get("x1")),
            float(c.get("x2")),
            float(c.get("z1")),
            float(c.get("z2")),
        )
    return out


def main() -> None:
    coords = load_coords()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "STROOP-LICENSE.txt").write_text(MIT_NOTICE)

    manifest = {}
    for folder, (level, image) in sorted(PICKS.items()):
        key = (level, image)
        if key not in coords:
            raise SystemExit(f"no coordinates for {folder}: L{level} {image!r}")
        x1, x2, z1, z2 = coords[key]

        im = Image.open(io.BytesIO(fetch(f"Resources/Maps/Map Images/{image}")))
        im = im.convert("RGBA")
        longest = max(im.width, im.height)
        if longest > MAX_DIM:
            scale = MAX_DIM / longest
            im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
        im.save(OUT / f"{folder}.webp", "WEBP", quality=QUALITY, method=6)
        kb = (OUT / f"{folder}.webp").stat().st_size / 1024
        print(f"{folder:18} {image:24} {im.width}x{im.height}  {kb:5.0f} KB")
        manifest[folder] = {"x1": x1, "x2": x2, "z1": z1, "z2": z2}

    lines = [
        '"use strict";',
        "// Generated by tools/build_maps.py -- do not edit by hand.",
        "// Per-level top-down map backgrounds for the Map tab. Each entry is the",
        "// world-space rectangle (x/z plane) its image covers: left=x1, right=x2,",
        "// top=z1, bottom=z2 (north up, +z downward). Images derived from STROOP",
        "// (MIT, (c) 2019 SM64 TAS & ABC) -- see maps/STROOP-LICENSE.txt.",
        "window.SM64_MAPS = {",
    ]
    for folder in sorted(manifest):
        r = manifest[folder]
        lines.append(
            f'  "{folder}": {{ img: "maps/{folder}.webp", '
            f'x1: {r["x1"]:g}, x2: {r["x2"]:g}, z1: {r["z1"]:g}, z2: {r["z2"]:g} }},'
        )
    lines.append("};")
    MANIFEST.write_text("\n".join(lines) + "\n")
    print(f"\nwrote {len(manifest)} maps -> {MANIFEST}")


if __name__ == "__main__":
    main()
