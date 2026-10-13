"""Least-privilege environment for the native renderer, without cloud control keys."""
import os
from pathlib import Path

RUNTIME_ENV_KEYS=frozenset({
    'PATH','HOME','USER','LOGNAME','SHELL','LANG','LANGUAGE','LC_ALL','LC_CTYPE','TZ',
    'TMPDIR','TMP','TEMP','LD_LIBRARY_PATH','LD_PRELOAD',
    'DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','XDG_RUNTIME_DIR','XDG_SESSION_TYPE',
    'XDG_DATA_DIRS','XDG_CONFIG_HOME','XDG_CACHE_HOME',
    'NVIDIA_VISIBLE_DEVICES','NVIDIA_DRIVER_CAPABILITIES','CUDA_VISIBLE_DEVICES',
    'CUDA_DEVICE_ORDER','CUDA_HOME','CUDA_PATH',
    '__GLX_VENDOR_LIBRARY_NAME','__NV_PRIME_RENDER_OFFLOAD','__VK_LAYER_NV_optimus',
    'VK_ICD_FILENAMES','VK_DRIVER_FILES','VK_LAYER_PATH','VK_ADD_LAYER_PATH',
    'VK_LOADER_DRIVERS_SELECT','VK_LOADER_DRIVERS_DISABLE','EGL_PLATFORM',
    'SDL_VIDEODRIVER','SDL_AUDIODRIVER','SDL_VIDEO_X11_FORCE_EGL',
    'SDL_VIDEO_X11_DGAMOUSE','SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS',
    'UE-ZenDataPath','UE-LocalDataCachePath',
})

def build_unreal_environment(source=None,token_file=Path('/home/unreal/.sub01-private/operator-token')):
    source=os.environ if source is None else source
    result={name:source[name]for name in RUNTIME_ENV_KEYS if name in source}
    result['SUB01_ADMIN_TOKEN']=Path(token_file).read_text().strip()
    result['SUB01_PC_ORIGIN']=source.get('SUB01_PC_ORIGIN','http://127.0.0.1:8811')
    result['SUB01_HOME_ORIGIN']='http://127.0.0.1:8821'
    result['UE-ZenDataPath']='/workspace/sub01-unreal/cache/zen'
    result['UE-LocalDataCachePath']='/workspace/sub01-unreal/cache/filesystem'
    return result
