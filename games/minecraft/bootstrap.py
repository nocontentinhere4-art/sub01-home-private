"""Prepare a pinned official Minecraft server and Java runtime, without accepting the EULA."""
import hashlib
import json
import platform
import subprocess
import tarfile
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/minecraft"
VERSION = "1.20.1"  # Matches a version explicitly supported by prismarine-viewer.

def read(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()

def fetch(url, path, digest, algorithm):
    if path.exists() and hashlib.new(algorithm, path.read_bytes()).hexdigest() == digest:
        return
    blob = read(url)
    assert hashlib.new(algorithm, blob).hexdigest() == digest, "Download checksum mismatch"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)

def main():
    DATA.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(read("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"))
    record = next(item for item in manifest["versions"] if item["id"] == VERSION)
    metadata_bytes = read(record["url"])
    assert hashlib.sha1(metadata_bytes).hexdigest() == record["sha1"]
    metadata = json.loads(metadata_bytes)
    server = metadata["downloads"]["server"]
    fetch(server["url"], DATA / "server.jar", server["sha1"], "sha1")
    system = {"Darwin": "mac", "Linux": "linux"}[platform.system()]
    architecture = "aarch64" if platform.machine() in ("arm64", "aarch64") else "x64"
    api = f"https://api.adoptium.net/v3/assets/latest/17/hotspot?architecture={architecture}&image_type=jre&os={system}&vendor=eclipse"
    try:
        package = json.loads(read(api))[0]["binary"]["package"]
    except urllib.error.HTTPError:
        release = json.loads(read("https://api.github.com/repos/adoptium/temurin17-binaries/releases/latest"))
        target = "mac" if system == "mac" else "linux"
        archive_record = next(item for item in release["assets"]
            if f"jre_{architecture}_{target}_hotspot" in item["name"] and item["name"].endswith(".tar.gz"))
        checksum_record = next(item for item in release["assets"]
            if item["name"] == archive_record["name"] + ".sha256.txt")
        package = {"link": archive_record["browser_download_url"],
                   "checksum": read(checksum_record["browser_download_url"]).decode().split()[0]}
    archive = DATA / "java.tar.gz"
    fetch(package["link"], archive, package["checksum"], "sha256")
    runtime = DATA / "runtime"
    runtime.mkdir(exist_ok=True)
    if not list(runtime.rglob("bin/java")):
        with tarfile.open(archive) as bundle:
            bundle.extractall(runtime, filter="data")
    java = next(runtime.rglob("bin/java"))
    subprocess.run([str(java), "-version"], check=True)
    properties = DATA / "server.properties"
    if not properties.exists():
        properties.write_text("\n".join([
            "server-ip=127.0.0.1", "server-port=25569", "online-mode=false",
            "enforce-secure-profile=false", "gamemode=survival", "difficulty=normal",
            "level-name=world", "level-seed=SUB-01", "max-players=1",
            "view-distance=4", "simulation-distance=4", "spawn-protection=0",
            "enable-rcon=false", "enable-query=false", "allow-flight=false",
            "motd=SUB-01 private Minecraft world", "sync-chunk-writes=true", "",
        ]))
    eula = DATA / "eula.txt"
    if not eula.exists():
        eula.write_text("# Owner approval required: https://www.minecraft.net/en-us/eula\neula=false\n")
    (DATA / "downloads.json").write_text(json.dumps({
        "version": VERSION, "server_url": server["url"], "server_sha1": server["sha1"],
        "java_url": package["link"], "java_sha256": package["checksum"],
        "java": str(java), "bind": "127.0.0.1", "port": 25569,
    }, indent=2))
    print("Prepared official server", VERSION, "on loopback only; EULA is not accepted.")

if __name__ == "__main__":
    main()
