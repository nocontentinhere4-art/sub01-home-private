"""Pinned scanned oak floor and coordinated structural wood, retaining PBR detail."""
import hashlib
import io
import json
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "web/house/assets"
FILES = {
    "diff": ("diff", "e9e25ac7abcc482f73214fda23e2de25"),
    "normal": ("nor_gl", "6a71c23551887b77b29623bb871aefbf"),
    "rough": ("rough", "3609ef0a3155ae90b69395431bf8cec1"),
}
VENEER_FILES = {
    "diff": ("diff", "39a99df4e328d62d74f3122722a64a95"),
    "normal": ("nor_gl", "d05406f5fdaf51f0d7b115b35d9af1b7"),
    "rough": ("rough", "a19b44176a078b9ae93314133848c9aa"),
}


def grade(raw, saturation, gamma, gain):
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    rgb = np.asarray(image, dtype=np.float64) / 255
    linear = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    luminance = linear @ np.array([.2126, .7152, .0722])
    linear = luminance[..., None] * (1 - saturation) + linear * saturation
    linear = np.clip(linear ** gamma * gain, 0, 1)
    rgb = np.where(linear <= .0031308, linear * 12.92, 1.055 * linear ** (1 / 2.4) - .055)
    return Image.fromarray(np.uint8(np.clip(rgb * 255, 0, 255)))


def write_asset(name, maps, source, transform, dimensions=None):
    records = []
    for key, raw in maps.items():
        original = Image.open(io.BytesIO(raw)).convert("RGB")
        image = grade(raw, **transform) if key == "diff" else original
        for lite in [False, True]:
            dest = ASSETS / ("lite" if lite else "") / name / f"{key}.jpg"
            dest.parent.mkdir(parents=True, exist_ok=True)
            output = image.resize((512, 512), Image.Resampling.LANCZOS) if lite else image
            identity = transform == {"saturation": 1, "gamma": 1, "gain": 1}
            if not lite and (key != "diff" or identity):
                dest.write_bytes(raw)
            else:
                output.save(dest, quality=94 if not lite else 88)
            records.append({"file": str(dest.relative_to(ASSETS)), "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
                            "bytes": dest.stat().st_size, "dimensions": list(output.size),
                            "sourceSha256": hashlib.sha256(raw).hexdigest()})
    metadata = {"asset": name, "source": source, "license": "CC0-1.0", "licenseSource": "https://polyhaven.com/license",
                "scanDimensionsMetres": dimensions, "albedoTransform": {"space": "linear-sRGB", **transform},
                "preserved": "Scanned local grain and source normal/roughness variation; no flat replacement, no shader second grade.",
                "files": records}
    (ASSETS / name / "provenance.json").write_text(json.dumps(metadata, indent=2) + "\n")


def main():
    maps = {}
    for key, (suffix, md5) in FILES.items():
        url = f"https://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/oak_wood_planks/oak_wood_planks_{suffix}_1k.jpg"
        with urllib.request.urlopen(url, timeout=60) as response:
            raw = response.read()
        if hashlib.md5(raw).hexdigest() != md5:
            raise ValueError(f"Pinned oak source changed: {key}")
        maps[key] = raw
    write_asset("home_oak_floor", maps, "https://polyhaven.com/a/oak_wood_planks",
                {"saturation": .60, "gamma": .90, "gain": 1.05}, [1.2, 1.2])
    structural = {}
    for key, (suffix, md5) in VENEER_FILES.items():
        url = f"https://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/oak_veneer_01/oak_veneer_01_{suffix}_1k.jpg"
        with urllib.request.urlopen(url, timeout=60) as response:
            raw = response.read()
        if hashlib.md5(raw).hexdigest() != md5:
            raise ValueError(f"Pinned oak veneer source changed: {key}")
        structural[key] = raw
    # The clean source itself supplies the finish, not a grade hiding weathering.
    write_asset("home_oak_veneer", structural, "https://polyhaven.com/a/oak_veneer_01",
                {"saturation": 1, "gamma": 1, "gain": 1}, [1.83, 1.83])


if __name__ == "__main__":
    main()
