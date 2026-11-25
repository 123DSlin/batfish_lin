#!/usr/bin/env python3
"""Verify the frozen, reproduction-validated full-native Plus baseline."""
from pathlib import Path
import hashlib,json


def check():
    base=Path(__file__).resolve().parent
    manifest=json.loads((base/'FROZEN_SOURCE_MANIFEST.json').read_text())
    changed=[]
    for name,record in manifest['files'].items():
        path=base/name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:
            changed.append(name)
    return dict(status='PASS' if not changed else 'FAIL',files_checked=len(manifest['files']),
                changed_files=changed,baseline=manifest['baseline'])


if __name__=='__main__':
    result=check()
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['status']=='PASS' else 1)
