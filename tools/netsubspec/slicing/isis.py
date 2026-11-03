"""Reserved IS-IS adapter; no SPF semantics are claimed or silently approximated."""
from .base import ProtocolSliceAdapter
from .models import UnsupportedSliceProtocol


class IsisSliceAdapter(ProtocolSliceAdapter):
    name = "isis"

    def ensure_supported(self):
        raise UnsupportedSliceProtocol(
            "IS-IS slicing is not implemented: define L1/L2 SPF dependencies, "
            "prefix origins, ECMP and MAIN-RIB boundaries before enabling this adapter"
        )

    def required_input_files(self):
        self.ensure_supported()

    def build_scopes(self, work_dir, declarations):
        self.ensure_supported()

    def build_requirements(self, work_dir, declarations, *, k, vrf):
        self.ensure_supported()

    def create_rules(self, routers, model_igp):
        self.ensure_supported()
