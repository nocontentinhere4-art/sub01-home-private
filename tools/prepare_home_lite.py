"""Generate 512px mobile variants before browser decode/upload."""

import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / "web/house/assets"
for folder in ROOT.iterdir():
    # Lightmaps/HDR variants have their own packer; don't generate unused
    # copies of contact-lighting atlases in the general material tree.
    if not folder.is_dir() or folder.name in {"lite", "lighting"}:
        continue
    for image in folder.rglob("*.jpg"):
        out = ROOT / "lite" / image.relative_to(ROOT)
        out.parent.mkdir(parents=True, exist_ok=True)
        im = Image.open(image)
        im.thumbnail((512, 512), Image.Resampling.LANCZOS)
        im.save(out, quality=86)
    for gltf in folder.glob("*.gltf"):
        data = json.loads(gltf.read_text())
        for buffer in data.get("buffers", []):
            buffer["uri"] = "../../" + folder.name + "/" + buffer["uri"]
        out = ROOT / "lite" / gltf.relative_to(ROOT)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, separators=(",", ":")))
print("Mobile textures capped at 512 px; geometry shared with desktop")
