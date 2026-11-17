"""List USGS 3DEP 1 m DEM tiles over Puerto Rico from the TNM Access API.

Writes <workdir>/island/tiles.json, the input of screen_tiles.py.
Usage: python3 fetch_tiles.py <workdir>
"""

import json
import os
import subprocess
import sys
import urllib.parse

API = "https://tnmaccess.nationalmap.gov/api/v1/products"
BBOX = "-67.35,17.85,-65.15,18.55"
DATASET = "Digital Elevation Model (DEM) 1 meter"


def fetch(offset: int) -> dict:
    q = urllib.parse.urlencode(
        {"datasets": DATASET, "bbox": BBOX, "max": 200, "offset": offset}
    )
    cmd = ["curl", "-sS", "-m", "120", f"{API}?{q}"]
    ca = os.environ.get("CURL_CA_BUNDLE")
    if ca:
        cmd[1:1] = ["--cacert", ca]
    return json.loads(subprocess.run(cmd, capture_output=True, check=True).stdout)


def main() -> None:
    work = sys.argv[1]
    items: list[dict] = []
    while True:
        page = fetch(len(items))
        got = page.get("items", [])
        items += got
        if not got or len(items) >= page.get("total", 0):
            break
    pr = [i for i in items if "PR_" in i["downloadURL"]]
    os.makedirs(os.path.join(work, "island"), exist_ok=True)
    with open(os.path.join(work, "island", "tiles.json"), "w") as f:
        json.dump(pr, f)
    new = sum("D24" in i["downloadURL"] for i in pr)
    print(f"{len(pr)} tiles: {new} D24, {len(pr) - new} 2018")


if __name__ == "__main__":
    main()
