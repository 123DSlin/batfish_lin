"""Explicit protocol dispatch. New protocols register a complete adapter here."""
from .base import ProtocolSliceAdapter
from .bgp import BgpSliceAdapter
from .isis import IsisSliceAdapter
from .models import SymbolicSliceError

_ADAPTERS = {"bgp": BgpSliceAdapter, "isis": IsisSliceAdapter}


def get_protocol_adapter(protocol: str = "bgp") -> ProtocolSliceAdapter:
    name = protocol.strip().lower().replace("-", "").replace("_", "")
    if name not in _ADAPTERS:
        raise SymbolicSliceError(
            f"Unsupported slicing protocol {protocol!r}; registered: {', '.join(_ADAPTERS)}. "
            "Mixed-protocol composition must be implemented explicitly."
        )
    adapter = _ADAPTERS[name]()
    adapter.ensure_supported()
    return adapter
