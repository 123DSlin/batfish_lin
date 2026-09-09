# Tolerance SR-TE concrete-failure demo

Device configurations are stored in `configs/`. The colocated `traffic.json` is experiment input,
not a router configuration; Batfish must continue to parse only files under `configs/`.

`traffic.json` defines demand, topology capacity, and flows only: a 20-Gbps IP flow from X to D and
an 80-Gbps SR-policy flow from S to D. SR candidate weights are the concrete values in the device
configs (initially 50/50). This file does not introduce a symbolic split variable.

Verifying TLPs / subspec may later unbind a chosen SR weight (logically `h` on the upper path and
`100-h` on the lower path) the same way auto-netsubspec unbinds one `Config_*`. That query, and any
expected range such as `h <= 93`, does not belong in the initial traffic input.
