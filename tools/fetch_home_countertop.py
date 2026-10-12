"""Prepare pinned CC0 untiled stone maps for the full and light private house."""
import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSET = "marble_slab_012"
URL = "https://f003.backblazeb2.com/file/ambientCG-Web/download/Marble012_uZys50mU/Marble012_1K-JPG.zip"
SHA256 = "b04384c6d49ce73baeb70db7ea4abfe9948fc9b74b9fd92c3766970662bf2c43"


def prepare(blob):
    if hashlib.sha256(blob).hexdigest() != SHA256:
        raise ValueError("The pinned countertop archive changed")
    files = []
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        for kind, source in [("diff", "Color"), ("normal", "NormalGL"), ("rough", "Roughness")]:
            raw = archive.read(f"Marble012_1K-JPG_{source}.jpg")
            image = Image.open(io.BytesIO(raw)).convert("RGB")
            if image.size != (1024, 1024):
                raise ValueError("Unexpected countertop texture dimensions")
            for lite in [False, True]:
                dest = ROOT / "web/house/assets" / ("lite" if lite else "") / ASSET / f"{kind}.jpg"
                dest.parent.mkdir(parents=True, exist_ok=True)
                if lite:
                    image.resize((512, 512), Image.Resampling.LANCZOS).save(dest, quality=88)
                else:
                    dest.write_bytes(raw)
                files.append({"file": str(dest.relative_to(ROOT / "web/house/assets")),
                              "bytes": dest.stat().st_size,
                              "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
                              "dimensions": [512, 512] if lite else [1024, 1024]})
    manifest = {"asset": ASSET, "original": "Marble012", "source": "https://ambientcg.com/view?id=Marble012",
                "license": "CC0-1.0", "licenseSource": "https://docs.ambientcg.com/license/",
                "archiveUrl": URL, "archiveSha256": SHA256,
                "preparation": "Original untiled procedural marble maps; original 1K JPG and 512px Lanczos copies. OpenGL normals.",
                "files": files}
    (ROOT / "web/house/assets" / ASSET / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    with urllib.request.urlopen(URL, timeout=60) as response:
        prepare(response.read())
