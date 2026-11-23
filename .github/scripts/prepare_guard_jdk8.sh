#!/usr/bin/env bash
# Forge's Mavenizer still uses Java 8 for its access transformer and renamer.
# Keep this build-only toolchain separate from the Java 25 Minecraft toolchain.
set -euo pipefail

destination="${1:?Usage: prepare_guard_jdk8.sh DESTINATION [VERIFIED_ARCHIVE_CANDIDATE]}"
archive="${2:-}"
expected_sha256='27eda854481d20806d918b30cdd417c6bed4fd15882e24f3595dc8ae7fb5d095'
url='https://github.com/adoptium/temurin8-binaries/releases/download/jdk8u514-b01/OpenJDK8U-jdk_x64_linux_hotspot_8u514b01.tar.gz'

if [[ -z "$archive" ]]; then
  archive="$(mktemp "${RUNNER_TEMP:-/tmp}/mcj-guard-jdk8.XXXXXX.tar.gz")"
  trap 'rm -f "$archive"' EXIT
  curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
    --connect-timeout 15 --max-time 60 --retry 2 --retry-delay 2 --retry-max-time 30 \
    "$url" --output "$archive"
fi

# This is the vendor-published SHA256. Never extract or execute an unchecked response.
printf '%s  %s\n' "$expected_sha256" "$archive" | sha256sum --check --strict
mkdir "$destination"
tar --extract --gzip --file "$archive" --directory "$destination" \
  --strip-components=1 --no-same-owner
"$destination/bin/java" -version
"$destination/bin/javac" -version
