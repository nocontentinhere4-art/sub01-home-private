"""One BLAS / OpenMP thread per process unless the environment asks for more (cap_threads).

Why: numpy and scipy ship OpenBLAS with one thread per core (4 here, 16 on the pod), and every OpenBLAS call wakes the
pool, whose threads then spin for a while. brain_sim.py's slow layer makes ten such calls a second (214 x 214 complex
products), so a process started without OPENBLAS_NUM_THREADS=1 keeps several cores busy. Measured on this 4-vCPU box
with live_server.py --demo (BROWSE=0, the child at 25,000 neurons, one viewer, 90 s; load 0.3-4 when each run began):
without the variables the server used 251 % of a core (HOME_ENABLED=0) and 279 % (HOME_ENABLED=1), with 9 threads,
three of them at 78-88 %. With this module and no variables set: 13.3 % and 13.5 %, with 5-7 threads of which one
works. The tick body (p50) went from 7.2 / 9.8 ms to 6.1 ms, and the loop lag (p95) from 3.9 / 5.0 ms to 1.4 ms. Under
load from other processes, the same server before this change had a 35 ms tick body and a 93 ms loop-lag p95
(HOME_ENABLED=1). The Dockerfile sets the variables; a venv start does not.

What cap_threads() does, when the module is imported (idempotent, never imports numpy or torch):
- the environment: OPENBLAS_NUM_THREADS, OMP_NUM_THREADS and MKL_NUM_THREADS get 1 when they are not set (a valid value
  the owner set wins; an invalid one becomes 1). Libraries loaded later read these at their load time;
- the libraries already loaded: numpy creates its pool when it is imported (before brain_sim, in live_server.py), so the
  count is also set on each loaded OpenBLAS, MKL and OpenMP library through its C API. Measured: the 10 Hz slow-layer loop
  drops from 65 % to 0.3 % of a core after the call, with the existing threads left idle;
- torch, when it is already imported (it is never imported here: that costs about a second and 700 MB): its intra-op
  threads follow OMP_NUM_THREADS.
"""
import ctypes
import os
import sys

VARS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
# (set, get) symbol names per build: numpy's bundled OpenBLAS (64-bit ints) and scipy's own have different prefixes
SYMBOLS = {
    "openblas": (("openblas_set_num_threads", "openblas_get_num_threads"),
                 ("openblas_set_num_threads64_", "openblas_get_num_threads64_"),
                 ("scipy_openblas_set_num_threads", "scipy_openblas_get_num_threads"),
                 ("scipy_openblas_set_num_threads64_", "scipy_openblas_get_num_threads64_"),
                 ("scipy_openblas_set_num_threads_64_", "scipy_openblas_get_num_threads_64_")),
    "mkl": (("mkl_set_num_threads", "mkl_get_max_threads"),),
    "omp": (("omp_set_num_threads", "omp_get_max_threads"),),
}
KIND_OF = (("openblas", ("openblas",)), ("mkl", ("mkl_rt", "libmkl")), ("omp", ("gomp", "libomp", "libiomp")))


def _count(var):
    """The thread count the environment asks for (its first number), else 1. Sets the variable to 1 when it is unset
    or not a number, so the libraries that read it later see the same value."""
    raw = os.environ.get(var, "")
    try:
        n = int(raw.split(",")[0])
    except ValueError:
        n = 0
    if n < 1:
        os.environ[var] = "1"
        n = 1
    return n


def _loaded_libraries():
    """Paths of the shared libraries this process has loaded that have a thread pool (Linux: /proc/self/maps)."""
    try:
        with open("/proc/self/maps") as f:
            paths = {p for p in (line.split()[-1] for line in f if ".so" in line) if p.startswith("/")}
    except OSError:
        return []
    out = []
    for path in sorted(paths):
        base = os.path.basename(path)
        for kind, keys in KIND_OF:
            if any(k in base for k in keys):
                out.append((path, kind))
                break
    return out


def _find(lib, kind, pick):
    """The (set, get) function pair of this library, or None: pick=0 for set, 1 for get."""
    for names in SYMBOLS[kind]:
        if hasattr(lib, names[0]) and hasattr(lib, names[1]):
            fn = getattr(lib, names[pick])
            if pick == 0:
                fn.argtypes, fn.restype = [ctypes.c_int], None
            else:
                fn.argtypes, fn.restype = [], ctypes.c_int
            return fn
    return None


def cap_threads():
    """Cap this process's thread pools (module doc). -> {"env": {var: value}, "libraries": [name, ...], "torch": n}"""
    counts = {var: _count(var) for var in VARS}
    wanted = {"openblas": counts["OPENBLAS_NUM_THREADS"], "mkl": counts["MKL_NUM_THREADS"], "omp": counts["OMP_NUM_THREADS"]}
    done = []
    for path, kind in _loaded_libraries():
        try:
            lib = ctypes.CDLL(path)
        except OSError:
            continue
        setter = _find(lib, kind, 0)
        if setter is None:
            continue
        setter(wanted[kind])
        done.append(os.path.basename(path))
    torch_n = None
    torch = sys.modules.get("torch")
    if torch is not None and hasattr(torch, "set_num_threads"):
        try:
            torch.set_num_threads(counts["OMP_NUM_THREADS"])
            torch_n = counts["OMP_NUM_THREADS"]
        except RuntimeError:                       # torch refuses inside a parallel region: keep its own count
            pass
    return {"env": {var: os.environ[var] for var in VARS}, "libraries": done, "torch": torch_n}


def thread_counts():
    """{library name: threads now} for the loaded OpenBLAS / MKL / OpenMP libraries (what cap_threads() set)."""
    out = {}
    for path, kind in _loaded_libraries():
        try:
            lib = ctypes.CDLL(path)
        except OSError:
            continue
        get = _find(lib, kind, 1)
        if get is not None:
            out[os.path.basename(path)] = int(get())
    return out


cap_threads()                                       # on import: brain_sim.py and the spiking entry points import this first
