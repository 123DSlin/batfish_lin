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

OUTPUT_DIR="$(sed -n 's/^SYMBOLIC_OUTPUT_DIRECTORY=//p' "${REACHABILITY_LOG}" | tail -1)"
if [[ -z "${OUTPUT_DIR}" || ! -d "${OUTPUT_DIR}" ]]; then
  cat "${REACHABILITY_LOG}" >&2
  echo "Reachability run did not report its symbolic output directory" >&2
  exit 1
fi

for output_file in symbolic_route.txt symbolic_route_k_pruned.txt smt_encoding.smt2; do
  if [[ ! -s "${OUTPUT_DIR}/${output_file}" ]]; then
    echo "Required output is missing or empty: ${OUTPUT_DIR}/${output_file}" >&2
    exit 1
  fi
done

for output_file in \
  0_model_igp.txt \
  0_hostnames.txt \
  0_interfaces.txt \
  0_ebgp_neighbors.txt \
  0_communities_index.txt \
  0_dst_ips.txt \
  0_used_overall_best.txt \
  0_unused_control_forwarding.txt \
  0_overall_history_enum.txt \
  0_properties_variables.txt \
  0_key_prefixlists.txt \
  0_unmatched_communities.txt; do
  if [[ ! -e "${OUTPUT_DIR}/${output_file}" ]]; then
    echo "Required encoding index is missing: ${OUTPUT_DIR}/${output_file}" >&2
    exit 1
  fi
done

echo "Generated ${OUTPUT_DIR}"
