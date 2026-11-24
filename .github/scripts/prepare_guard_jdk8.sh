#!/usr/bin/env bash
# Forge's Mavenizer still uses Java 8 for its access transformer and renamer.
# Keep this build-only toolchain separate from the Java 25 Minecraft toolchain.
set -euo pipefail

destination="${1:?Usage: prepare_guard_jdk8.sh DESTINATION [VERIFIED_ARCHIVE_CANDIDATE]}"
archive="${2:-}"
expected_sha256='27eda854481d20806d918b30cdd417c6bed4fd15882e24f3595dc8ae7fb5d095'
url='https://github.com/adoptium/temurin8-binaries/releases/download/jdk8u514-b01/OpenJDK8U-jdk_x64_linux_hotspot_8u514b01.tar.gz'

verify_archive() {
  # Never extract or execute a response that does not match the vendor pin.
  printf '%s  %s\n' "$expected_sha256" "$archive" | sha256sum --check --strict
}

if [[ -z "$archive" ]]; then
  trap 'rm -f -- "$archive"' EXIT
  # One shared limit covers transport and integrity failures without nested retries.
  for attempt in 1 2 3; do
    archive="$(mktemp "${RUNNER_TEMP:-/tmp}/mcj-guard-jdk8.XXXXXX.tar.gz")"
    if curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
      --connect-timeout 15 --max-time 60 "$url" --output "$archive" && verify_archive; then
      break
    fi
    rm -f -- "$archive"
    archive=''
    if [[ "$attempt" == 3 ]]; then
      printf 'ERROR: Could not download and verify Java 8 after 3 attempts.\n' >&2
      exit 1
    fi
    printf 'WARN: Java 8 download or verification failed (attempt %s of 3); retrying.\n' "$attempt" >&2
    sleep 2
  done
else
  # Caller-supplied candidates are checked once and remain owned by the caller.
  verify_archive
fi

mkdir "$destination"
tar --extract --gzip --file "$archive" --directory "$destination" \
  --strip-components=1 --no-same-owner
"$destination/bin/java" -version
"$destination/bin/javac" -version
