#!/usr/bin/env python3
"""Verify the immutable archive and, optionally, the original working-tree sources."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-only',action='store_true',help='verify preserved code even if current sources intentionally changed')
    args=parser.parse_args()
    base=Path(__file__).resolve().parent
    repo=base.parents[2]
    manifest=json.loads((base/'manifest.json').read_text())
    expected=manifest['files']
    for name in expected:
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('invalid archived source path')
    archive=base/manifest['archive']['file']
    errors=[]
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=manifest['archive']['sha256']:
        errors.append('archive checksum mismatch')
    with tarfile.open(archive,'r:gz') as bundle:
        members=bundle.getmembers()
        if len(members)!=len(expected) or {m.name for m in members}!=set(expected):
            errors.append('archive file inventory mismatch')
        for item in members:
            record=expected.get(item.name)
            if record is None or not item.isfile() or item.size!=record['bytes']:
                errors.append('invalid archive entry: '+item.name)
                continue
            content=bundle.extractfile(item).read()
            if hashlib.sha256(content).hexdigest()!=record['sha256']:
                errors.append('archived source checksum mismatch: '+item.name)
    changed=[]
    if not args.archive_only:
        for name,record in expected.items():
            path=repo/name
            if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:
                changed.append(name)
    result=dict(status='PASS' if not errors and not changed else 'FAIL',
                archive_verified=not errors,archived_files=len(expected),
                current_sources_checked=not args.archive_only,changed_sources=changed,errors=errors)
    print(json.dumps(result,indent=2))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
