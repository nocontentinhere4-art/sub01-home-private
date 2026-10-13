#!/usr/bin/env bash
set -euo pipefail
# Execute only on the already authorized GPU server, never on the user's Mac.
task_engine_root=${1:?Pass extracted official Unreal engine root}
task_project_root=${2:?Pass staged Sub01HomeLab directory}
task_editor="$task_engine_root/Engine/Binaries/Linux/UnrealEditor-Cmd"
test -x "$task_editor"
test -f "$task_project_root/Sub01HomeLab.uproject"
if [ "$(id -u)" -eq 0 ]; then
  printf '%s\n' 'Run the official editor as the existing non-root Unreal user.' >&2
  exit 1
fi
mkdir -p "$task_project_root/Saved/Logs"
"$task_editor" "$task_project_root/Sub01HomeLab.uproject" \
  -unattended -NullRHI -NoSound -NoSplash -run=pythonscript \
  -script="$task_project_root/Content/Python/import_home.py" \
  > "$task_project_root/Saved/Logs/home-import.log" 2>&1
test -s "$task_project_root/unreal-home-import.json"
