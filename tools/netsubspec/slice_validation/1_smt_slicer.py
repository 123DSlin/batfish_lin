#!/usr/bin/env python3
"""Compatibility entry for experiments; use the production protocol-adapted slicer.

Keep the importable helpers used by existing validation scripts/tests available.
All slicing code lives in ../1_smt_slicer.py and ../slicing/; no second copy of
protocol rules is maintained here. Validation consistency modules remain local.
"""
import importlib.util as _import_util
from pathlib import Path as _Path
import sys as _sys

_root = _Path(__file__).resolve().parents[1]
if str(_root) not in _sys.path:
    _sys.path.append(str(_root))
_name = "_netsubspec_production_device_slicer"
if _name not in _sys.modules:
    _spec = _import_util.spec_from_file_location(_name, _root / "1_smt_slicer.py")
    _module = _import_util.module_from_spec(_spec)
    _sys.modules[_name] = _module
    _spec.loader.exec_module(_module)
else:
    _module = _sys.modules[_name]
for _key, _value in vars(_module).items():
    if not _key.startswith("__"):
        globals()[_key] = _value

if __name__ == "__main__":
    raise SystemExit(main())
