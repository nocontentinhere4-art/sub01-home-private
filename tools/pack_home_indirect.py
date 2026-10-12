"""Validate and pack a Cycles light bake as RGBE HDR for the existing web loader."""
import json
import sys
from pathlib import Path

import bpy
import numpy as np

source, destination = map(Path, sys.argv[sys.argv.index("--") + 1:])
destination.mkdir(parents=True, exist_ok=True)
image = bpy.data.images.load(str(source), check_existing=False)
pixels = np.empty(len(image.pixels), dtype=np.float32)
image.pixels.foreach_get(pixels)
rgb = pixels.reshape(-1, 4)[:, :3]
assert np.isfinite(rgb).all() and np.min(rgb) >= 0, "Invalid irradiance values"
assert np.count_nonzero(rgb) > len(rgb) * 0.1, "Empty bake"
stats = {"width": image.size[0], "height": image.size[1],
         "max": float(rgb.max()), "p95": float(np.percentile(rgb.max(axis=1), 95)),
         "nonzero": float(np.mean(rgb.max(axis=1) > 0)),
         "kind": "Cycles diffuse indirect irradiance; direct light and albedo excluded"}
generated = bpy.data.images.new("Packed private light", image.size[0], image.size[1],
                               alpha=False, float_buffer=True)
image = generated
image.colorspace_settings.name = "Non-Color"
image.pixels.foreach_set(pixels)
image.update()
scene = bpy.context.scene
scene.render.image_settings.file_format = "HDR"
scene.render.image_settings.color_mode = "RGB"
scene.view_settings.view_transform = "Raw"
image.save_render(str(destination / "indirect.hdr"), scene=scene)
image.scale(512, round(512 * stats["height"] / stats["width"]))
image.save_render(str(destination / "indirect-lite.hdr"), scene=scene)
assert (destination / "indirect.hdr").read_bytes().startswith(b"#?"), "Not RGBE HDR"
(destination / "indirect.json").write_text(json.dumps(stats, indent=2))
print("PACKED", json.dumps(stats), flush=True)
