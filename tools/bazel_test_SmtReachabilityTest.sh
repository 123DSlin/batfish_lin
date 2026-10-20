#!/bin/bash
set -e  # stop the script on any error (a command exits with a non-zero status)

SMT_PROTOCOL_SELECTION=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --protocols)
            if [ "$#" -lt 2 ]; then
                echo "--protocols requires bgp, ospf, isis, or a comma-separated combination" >&2
                exit 2
            fi
            SMT_PROTOCOL_SELECTION="$2"
            shift 2
            ;;
        --protocols=*)
            SMT_PROTOCOL_SELECTION="${1#*=}"
            shift
            ;;
        *)
            echo "Unknown argument: $1" >&2
            echo "Usage: $0 [--protocols bgp[,ospf[,isis]]]" >&2
            exit 2
            ;;
    esac
done

# For Mac
if [ "Darwin" = $(uname -s) ]; then
    if ! [ -x "$(command -v greadlink)"  ]; then
        brew install coreutils
    fi
    BIN_PATH=$(greadlink -f "$0")
    ROOT_DIR=$(dirname $(dirname "$BIN_PATH"))
# For Linux
else
    BIN_PATH=$(readlink -f "$0")
    ROOT_DIR=$(dirname $(dirname "$BIN_PATH"))
fi

BAZEL="bazelisk"

TARGET_EXPRESSION="//projects/allinone:smt_tests"
BAZEL_COMMAND="test"
BAZEL_FLAGS=(
    "--test_filter=org.batfish.minesweeper.smt.SmtReachabilityTest#"
    "--cache_test_results=no"
    "--test_timeout=999999"
    "--strategy=TestRunner=standalone"
    "--spawn_strategy=local"
    "--test_env=JAVA_TOOL_OPTIONS=-Djava.library.path=${HOME}/Library/Java/Extensions"
)
if [ -n "${SMT_PROTOCOL_SELECTION}" ]; then
    BAZEL_FLAGS+=("--test_env=SMT_PROTOCOLS=${SMT_PROTOCOL_SELECTION}")
fi
${BAZEL} ${BAZEL_COMMAND} ${TARGET_EXPRESSION} "${BAZEL_FLAGS[@]}"
