#!/usr/bin/env python3
"""Stop only the authorized home pod at its persisted absolute deadline."""
import json, os, sys, time, urllib.request
from pathlib import Path

POD = "713u6mnmxu4y1a"
ROOT = Path("/workspace/sub01-home-private")

def api(config, query):
    request = urllib.request.Request(
        "https://api.runpod.io/graphql?api_key=" + config["api_key"],
        data=json.dumps({"query": query}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if result.get("errors"):
        raise RuntimeError("Runpod operation rejected")
    return result["data"]

def main():
    config = json.loads((ROOT / "private/control.json").read_text())
    if config["pod_id"] != POD or os.environ.get("RUNPOD_POD_ID", POD) != POD:
        raise RuntimeError("Unauthorized pod")
    deadline = int((ROOT / "logs/budget-20261013-deadline").read_text())
    state = api(config, 'query { pod(input:{podId:"'+POD+'"}) { id name desiredStatus } }')["pod"]
    if state["id"] != POD or state["name"] != "sub01-unreal-preview-migration":
        raise RuntimeError("Unexpected pod identity")
    print("AUTHENTICATED", POD, "deadline", deadline, flush=True)
    if "--check" in sys.argv:
        return
    while time.time() < deadline:
        time.sleep(min(30, max(0, deadline-time.time())))
    while True:
        try:
            result=api(config, 'mutation { podStop(input:{podId:"'+POD+'"}) { id desiredStatus } }')["podStop"]
            if result["id"] == POD and result["desiredStatus"] in ("EXITED", "STOPPED"):
                print("STOP_CONFIRMED", POD, flush=True)
                return
            print("STOP_REQUESTED", result.get("desiredStatus"), flush=True)
        except Exception as error:
            print("STOP_RETRY", type(error).__name__, flush=True)
        time.sleep(15)

if __name__ == "__main__":
    main()
