# Tolerance SR-TE demo with BGP X-B backup

This snapshot extends `tolerance_sr_te_demo` with an X-B link and eBGP sessions from X to D, A,
and B. D originates `5.5.5.5/32`. X applies inbound local preference 200 from D, 100 from A, and
50 from B, so the all-links-up path for the 20-Gbps packet flow is X-D while X-A-D and X-B-D are
lower-priority BGP alternatives.

The IS-IS and SR-TE configuration is retained for the 80-Gbps flow from S. `traffic.json` contains
only flow demand, topology capacity, and the failure model; router behavior remains in `configs/`.
