#!/bin/bash
set -e  # stop the script on any error (a command exits with a non-zero status)

OS=$(uname -s)
ARCH=$(uname -m)

# For Mac
if [ "Darwin" = ${OS} ]; then
    if ! [ -x "$(command -v greadlink)"  ]; then
        brew install coreutils
    fi
    BIN_PATH=$(greadlink -f "$0")
    ROOT_DIR=$(dirname "$BIN_PATH")
# For Linux
else
    BIN_PATH=$(readlink -f "$0")
    ROOT_DIR=$(dirname "$BIN_PATH")
fi

SMT_PATH="${ROOT_DIR}/smts"
BAZELRC_PATH="${ROOT_DIR}/.bazelrc"

echo "Detected system: ${OS} (${ARCH})"

install_for_linux() {
    echo "[*] Installing dependencies for Linux ..."

    # Ensure apt exists (for Debian/Ubuntu only)
    if ! command -v apt-get &> /dev/null; then
        echo "Error: apt-get not found. This script supports only Debian/Ubuntu-based systems."
        exit 1
    fi

    # Update package index
    sudo apt-get update -y

    # Install OpenJDK 11
    echo "[*] Installing OpenJDK 11 ..."
    sudo apt-get install -y openjdk-11-jdk openjdk-11-dbg

    # Install wget
    echo "[*] Installing Wget ..."
    sudo apt-get install -y wget

    # Install Bazelisk (as bazel)
    echo "[*] Installing Bazelisk ..."
    # wget -O- https://github.com/bazelbuild/bazelisk/releases/download/v1.12.2/bazelisk-linux-amd64 \
    #     | sudo tee /usr/local/bin/bazelisk > /dev/null
    wget -O- https://github.com/bazelbuild/bazelisk/releases/download/v1.25.0/bazelisk-linux-amd64 \
        | sudo tee /usr/local/bin/bazelisk > /dev/null
    sudo chmod +x /usr/local/bin/bazelisk
    sudo ln -sf /usr/local/bin/bazelisk /usr/local/bin/bazel

    # Z3 download URL and relevant local directory/file name
    Z3_VERSION="4.14.0"
    Z3_OS="x64-glibc-2.35"
    Z3_BASENAME="z3-${Z3_VERSION}-${Z3_OS}"
    Z3_URL="https://github.com/Z3Prover/z3/releases/download/z3-${Z3_VERSION}/${Z3_BASENAME}.zip"
    Z3_ARCHIVE="${Z3_BASENAME}.zip"
    Z3_DIR="${Z3_BASENAME}"

    # Z3 shared library directory
    Z3_BIN_DIR="/usr/bin"
    Z3_INCLUDE_DIR="/usr/include"
    Z3_LIB_DIR="/usr/lib"

    # Install Z3
    echo "[*] Installing Z3 ..."
    wget "${Z3_URL}"
    unzip "${Z3_ARCHIVE}"
    sudo cp "${Z3_DIR}/bin/z3" "${Z3_BIN_DIR}/z3"
    sudo cp "${Z3_DIR}/bin/libz3.so" "${Z3_LIB_DIR}/libz3.so"
    sudo cp "${Z3_DIR}/bin/libz3java.so" "${Z3_LIB_DIR}/libz3java.so"
    sudo cp "${Z3_DIR}/bin/com.microsoft.z3.jar" "${Z3_LIB_DIR}/com.microsoft.z3.jar"
    # sudo find "${Z3_DIR}/include" -type f -exec cp {} "${Z3_INCLUDE_DIR}" \;
    sudo rsync -a "${Z3_DIR}/include/" "${Z3_INCLUDE_DIR}/" 
    sudo chmod 755 "${Z3_LIB_DIR}/libz3java.so"
    sudo chmod 755 "${Z3_LIB_DIR}/libz3.so"
    rm -r "${Z3_ARCHIVE}" "${Z3_DIR}" 

    echo "[✓] Linux installation completed!"
}

install_for_macos() {
    echo "[*] Installing dependencies for macOS ..."

    # Check for Homebrew
    if ! command -v brew &> /dev/null; then
        echo "[*] Homebrew not found. Installing Homebrew ..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi

    # Ensure coreutils (for greadlink)
    if ! command -v greadlink &> /dev/null; then
        echo "[*] Installing coreutils ..."
        brew install coreutils
    fi

    # Install OpenJDK 11
    echo "[*] Installing OpenJDK 11 ..."
    brew install openjdk@11
    # Set JAVA_HOME zsh and bash
    JAVA_HOME="$(brew --prefix openjdk@11)/libexec/openjdk.jdk/Contents/Home"
    export PATH="$JAVA_HOME/bin:$PATH"
    echo "export JAVA_HOME=${JAVA_HOME}" >> ~/.zshrc
    echo "export JAVA_HOME=${JAVA_HOME}" >> ~/.bashrc

    # Install wget
    echo "[*] Installing wget ..."
    brew install wget

    # Install Bazelisk (as bazel)
    echo "[*] Installing Bazelisk ..."
    brew install bazelisk
    # Ensure 'bazel' points to bazelisk
    brew link --overwrite bazelisk

    # Z3 download URL and relevant local directory/file name
    Z3_VERSION="4.14.0"
    # Official asset name is arm64-osx-..., not arm-osx-...
    Z3_OS="arm64-osx-13.7.2"
    Z3_BASENAME="z3-${Z3_VERSION}-${Z3_OS}"
    Z3_URL="https://github.com/Z3Prover/z3/releases/download/z3-${Z3_VERSION}/${Z3_BASENAME}.zip"
    Z3_ARCHIVE="${Z3_BASENAME}.zip"
    Z3_DIR="${Z3_BASENAME}"

    # Z3 shared library directory
    Z3_BIN_DIR="/usr/local/bin"
    Z3_INCLUDE_DIR="/usr/local/include"
    Z3_LIB_DIR="/usr/local/lib"

    # Install Z3
    echo "[*] Installing Z3 ..."
    wget "${Z3_URL}"
    unzip "${Z3_ARCHIVE}"
    sudo cp "${Z3_DIR}/bin/z3" "${Z3_BIN_DIR}/z3"
    sudo cp "${Z3_DIR}/bin/libz3.dylib" "${Z3_LIB_DIR}/libz3.dylib"
    sudo cp "${Z3_DIR}/bin/libz3java.dylib" "${Z3_LIB_DIR}/libz3java.dylib"
    sudo cp "${Z3_DIR}/bin/com.microsoft.z3.jar" "${Z3_LIB_DIR}/com.microsoft.z3.jar"
    sudo rsync -a "${Z3_DIR}/include/" "${Z3_INCLUDE_DIR}/"
    sudo chmod 755 ${Z3_LIB_DIR}/libz3.dylib
    sudo chmod 755 ${Z3_LIB_DIR}/libz3java.dylib
    rm -rf "${Z3_ARCHIVE}" "${Z3_DIR}"

    # Copy into Java Extensions and fix @loader_path so System.loadLibrary("z3java") works
    echo "[*] Configuring Z3 JNI for macOS ..."
    mkdir -p "${HOME}/Library/Java/Extensions"
    cp -f "${Z3_LIB_DIR}/libz3.dylib" "${Z3_LIB_DIR}/libz3java.dylib" "${HOME}/Library/Java/Extensions/"
    if [ -x "${ROOT_DIR}/tools/fix_z3_macos_gatekeeper.sh" ]; then
        "${ROOT_DIR}/tools/fix_z3_macos_gatekeeper.sh" || true
    fi

    echo "[✓] macOS installation completed!"
}

update_bazelrc_for_linux() {
    echo "[*] Updating Bazel configuration ..."
    echo "[*] SMT path: ${SMT_PATH}"
    echo "[*] Bazelrc file: ${BAZELRC_PATH}"

    echo "[*] Deleting and recreating .bazelrc ..."
    rm -f "${BAZELRC_PATH}"

    cat > "${BAZELRC_PATH}" <<EOF
# Automatically generated by install.sh
common --enable_bzlmod=false
build --sandbox_writable_path=${SMT_PATH}/ \\
      --action_env=SMT_DIRECTORY_PREFIX=${SMT_PATH}/ \\
      --explicit_java_test_deps
EOF

    echo "[✓] .bazelrc updated successfully!"
}

update_bazelrc_for_macos() {
    echo "[*] Updating Bazel configuration for macOS ..."
    echo "[*] SMT path: ${SMT_PATH}"
    echo "[*] Bazelrc file: ${BAZELRC_PATH}"

    echo "[*] Deleting and recreating .bazelrc ..."
    rm -f "${BAZELRC_PATH}"

    cat > "${BAZELRC_PATH}" <<EOF
# Automatically generated by install.sh (macOS)
common --enable_bzlmod=false
build --sandbox_writable_path=${SMT_PATH}/ \\
      --action_env=SMT_DIRECTORY_PREFIX=${SMT_PATH}/ \\
      --explicit_java_test_deps

# Z3 JNI: run tests outside sandbox; load libs from Java Extensions
test --strategy=TestRunner=standalone
test --spawn_strategy=local
test --test_env=JAVA_TOOL_OPTIONS=-Djava.library.path=\${HOME}/Library/Java/Extensions
EOF

    echo "[✓] .bazelrc updated successfully for macOS!"
}

case "${OS}" in
    "Linux")
        install_for_linux
        update_bazelrc_for_linux
        ;;
    "Darwin")
        if [[ "arm64" == "${ARCH}" ]]; then
            install_for_macos
            update_bazelrc_for_macos
        else
            echo "Unsupported ${OS} architecture: ${ARCH}"
            exit 1
        fi
        ;;
    *)
        echo "Unsupported system: ${OS}"
        exit 1
        ;;
esac

echo "🎉 All done!"
