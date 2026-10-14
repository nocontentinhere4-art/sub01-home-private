"""Read-only display-referred capture statistics; never infer scene lux from PNG.

Pass named, manually inspected neutral-surface rectangles as --roi name:x,y,w,h.
No image edits, renderer actions, exposure application or automatic ROI selection.
Requires Pillow/numpy. Coordinates exclude browser UI and material boundaries.
"""
import argparse
import hashlib
import json
from pathlib import Path


def measure(image, regions):
    import numpy as np
    from PIL import Image
    path = Path(image)
    rgb = np.asarray(Image.open(path).convert('RGB'), dtype=np.float64) / 255.
    height, width = rgb.shape[:2]
    rows = []
    for name, box in regions:
        x, y, w, h = box
        if min(x, y) < 0 or min(w, h) <= 0 or x+w > width or y+h > height:
            raise ValueError('ROI outside image: ' + name)
        pixels = rgb[y:y+h, x:x+w].reshape(-1, 3)
        linear = np.where(pixels <= .04045, pixels/12.92, ((pixels+.055)/1.055)**2.4)
        luma = linear @ np.array([.2126, .7152, .0722])
        median = np.median(linear, axis=0)
        rows.append({'name': name, 'xywh': box, 'pixel_count': w*h,
                     'median_srgb_8bit': np.median(pixels*255, axis=0).round(2).tolist(),
                     'median_display_linear_rgb': median.round(6).tolist(),
                     'display_linear_luminance_p10_p50_p90': np.percentile(luma, [10, 50, 90]).round(6).tolist(),
                     'median_linear_red_blue_ratio': round(float(median[0]/median[2]), 4) if median[2] > 0 else None,
                     'black_pixel_fraction_all_channels_le_2': float(np.mean(np.all(pixels*255 <= 2, axis=1))),
                     'clipped_pixel_fraction_any_channel_ge_254': float(np.mean(np.any(pixels*255 >= 254, axis=1)))})
    return {'schema': 'sub01-native-lighting-capture-measurement-v1', 'read_only': True,
            'image': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'size': [width, height], 'regions': rows,
            'limitation': 'Display-referred PNG after exposure/tone mapping. Not scene luminance, lux, metered EV100 or proof of neutral source albedo.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image')
    parser.add_argument('--roi', action='append', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    regions = []
    for value in args.roi:
        name, coordinates = value.split(':', 1)
        regions.append((name, list(map(int, coordinates.split(',')))))
    if any(len(box) != 4 for _, box in regions):
        parser.error('Each ROI needs x,y,w,h')
    Path(args.output).write_text(json.dumps(measure(args.image, regions), indent=2) + '\n')
