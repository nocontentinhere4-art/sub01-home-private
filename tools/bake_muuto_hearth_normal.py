"""Portable material-only normal from the official photographic Hearth swatch.
Review assumption: photo repeats over .25m, brightness-height strength18um.
This is derived luminance bump, not a measured scanned normal or mesh edit.
"""
from pathlib import Path
from PIL import Image
import numpy as np,json,hashlib
root=Path('/workspace/sub01-home-private/manufacturer-muuto-rest-r1');p=root/'Hearth 6.jpg';a=np.asarray(Image.open(p).convert('RGB'),dtype=np.float64)/255
linear=np.where(a<=.04045,a/12.92,((a+.055)/1.055)**2.4);h=(linear@np.array([.2126,.7152,.0722]))*.000018
# Wrapped central differences respect repeating source swatch UVs.
gx=(np.roll(h,-1,axis=1)-np.roll(h,1,axis=1))/(.5/a.shape[1]);gy=(np.roll(h,-1,axis=0)-np.roll(h,1,axis=0))/(.5/a.shape[0]);n=np.stack((-gx,gy,np.ones_like(gx)),axis=-1);n/=np.linalg.norm(n,axis=-1)[...,None]
Image.fromarray(np.round((n*.5+.5)*255).astype('uint8')).save(root/'Hearth6-derived-normal.png');print('MUUTO_NORMAL_READY')
