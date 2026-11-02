#!/bin/bash
set -euo pipefail
set +x
cd /data
test -f /mcj/runtime.json
test -f /mcj/guard.sha256
test -f /data/server.properties
grep -qx 'online-mode=true' /data/server.properties
grep -qx 'gamemode=spectator' /data/server.properties
grep -qx 'force-gamemode=true' /data/server.properties
if [[ "$(jq -r '.version' /mcj/runtime.json)" == 26.* ]]; then
  grep -qx 'pause-when-empty-seconds=0' /data/server.properties
fi
(cd /data/mods && sha256sum --check /mcj/guard.sha256)
export TYPE="$(jq -er '.loader | select(. == "FORGE" or . == "NEOFORGE" or . == "FABRIC")' /mcj/runtime.json)"
export VERSION="$(jq -er '.version | select(test("^[0-9]+[.][0-9]+([.][0-9]+)?$"))' /mcj/runtime.json)"
export FORGE_VERSION="$(jq -r '.loader_version // empty' /mcj/runtime.json)"
export FABRIC_LOADER_VERSION="$(jq -r '.loader_version // empty' /mcj/runtime.json)"
export FABRIC_INSTALLER_VERSION="$(jq -r '.installer_version // "1.1.2"' /mcj/runtime.json)"
export NEOFORGE_VERSION="$(jq -r '.loader_version // empty' /mcj/runtime.json)"
export MEMORY="$(jq -er '.memory_mb | select(type == "number" and . >= 1024 and . <= 63488)' /mcj/runtime.json)M"
export RCON_PASSWORD="$(cat /run/secrets/rcon)"
export SKIP_SERVER_PROPERTIES=true
export OVERRIDE_SERVER_PROPERTIES=false
export DUMP_SERVER_PROPERTIES=false
# A normal shutdown saves the worlds. The image runner must not kill Java
# while slow storage is still flushing; the controller reports a pending stop.
export STOP_DURATION=0
exec /start
