#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SMT_ROOT="${SMT_DIRECTORY_PREFIX:-${REPO_ROOT}/smts}"
REACHABILITY_LOG="$(mktemp)"
trap 'rm -f "${REACHABILITY_LOG}"' EXIT

mkdir -p "${SMT_ROOT}"
cd "${REPO_ROOT}"

if ! bazel test //projects/allinone:smt_tests \
  --nocache_test_results \
  --test_output=all \
  --test_filter=org.batfish.minesweeper.smt.SmtReachabilityTest#testReachability \
  --strategy=TestRunner=standalone \
  --spawn_strategy=local \
  --test_env="SMT_DIRECTORY_PREFIX=${SMT_ROOT}" \
  >"${REACHABILITY_LOG}" 2>&1; then
  cat "${REACHABILITY_LOG}" >&2
  exit 1
fi

OUTPUT_DIR="$(sed -n 's/^SMT_OUTPUT_DIRECTORY=//p' "${REACHABILITY_LOG}" | tail -1)"
if [[ -z "${OUTPUT_DIR}" || ! -d "${OUTPUT_DIR}" ]]; then
  cat "${REACHABILITY_LOG}" >&2
  echo "Reachability run did not report its SMT output directory" >&2
  exit 1
fi
OUTPUT_FILE="${OUTPUT_DIR}/0_symbolic_routes.txt"

if [[ ! -s "${OUTPUT_FILE}" ]]; then
  echo "Symbolic RIB report was not produced" >&2
  exit 1
fi

echo "Generated ${OUTPUT_FILE}"
