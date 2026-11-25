"""Protocol-adapted device slicing. BGP is supported; IS-IS is reserved."""
from .base import ProtocolSliceAdapter, ProtocolSliceRules
from .models import DeviceSemanticScope, SymbolicSliceRequirements, SymbolicSliceError, UnsupportedSliceProtocol
from .registry import get_protocol_adapter
