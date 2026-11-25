#!/usr/bin/env python3
"""Verify frozen code, then execute the preserved Plus CLI with unchanged arguments."""
from pathlib import Path
import json,os,sys
from verify_baseline import check

result=check()
if result['status']!='PASS':
    print(json.dumps(result,indent=2),file=sys.stderr)
    raise SystemExit(2)
entry=Path(__file__).resolve().parent/'tools/run.py'
os.execv(sys.executable,[sys.executable,'-B',str(entry),*sys.argv[1:]])
