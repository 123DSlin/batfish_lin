#!/bin/bash
# Fix macOS Z3 JNI: Gatekeeper quarantine + dylib install names for System.loadLibrary.
set -euo pipefail

fix_pair() {
  local dir="$1"
  local need_sudo="${2:-0}"
  local z3="${dir}/libz3.dylib"
  local z3j="${dir}/libz3java.dylib"
  if [ ! -f "$z3" ] || [ ! -f "$z3j" ]; then
    echo "  skip missing: $dir"
    return 0
  fi
  echo "  -> $dir"
  local run=()
  if [ "$need_sudo" = "1" ]; then
    run=(sudo)
  fi
  "${run[@]}" xattr -cr "$z3" "$z3j" 2>/dev/null || true
  # Make loadLibrary("z3java") resolve libz3.dylib next to itself
  "${run[@]}" install_name_tool -id @loader_path/libz3.dylib "$z3"
  "${run[@]}" install_name_tool -id @loader_path/libz3java.dylib "$z3j"
  "${run[@]}" install_name_tool -change libz3.dylib @loader_path/libz3.dylib "$z3j" 2>/dev/null || true
  "${run[@]}" install_name_tool -change /usr/local/lib/libz3.dylib @loader_path/libz3.dylib "$z3j" 2>/dev/null || true
  "${run[@]}" codesign --force --sign - "$z3" "$z3j"
}

echo "[*] Fixing Z3 dylibs for macOS JNI ..."
# Prefer user Extensions (no SIP issues for daily use)
mkdir -p "${HOME}/Library/Java/Extensions"
if [ -f /usr/local/lib/libz3.dylib ]; then
  cp -f /usr/local/lib/libz3.dylib /usr/local/lib/libz3java.dylib "${HOME}/Library/Java/Extensions/"
fi
fix_pair "${HOME}/Library/Java/Extensions" 0
fix_pair /usr/local/lib 1
fix_pair /Library/Java/Extensions 1

echo "[*] Quick JNI smoke test ..."
EXT="${HOME}/Library/Java/Extensions"
TMP=$(mktemp -d)
cat > "${TMP}/Smoke.java" <<'EOF'
import com.microsoft.z3.Context;
public class Smoke {
  public static void main(String[] args) {
    Context ctx = new Context();
    System.out.println("Z3 OK");
    ctx.close();
  }
}
EOF
javac -cp /usr/local/lib/com.microsoft.z3.jar "${TMP}/Smoke.java"
java -Djava.library.path="${EXT}" -cp "${TMP}:/usr/local/lib/com.microsoft.z3.jar" Smoke
rm -rf "${TMP}"

echo "[✓] Done. Re-run: ./tools/bazel_test_SmtReachabilityTest.sh"
