# Tolerance SR-TE concrete-failure demo input

This directory is the non-configuration input boundary for the first SR-TE tolerance demo.
Router configurations remain under `networks/tolerance_sr_te_demo/configs`; generated scripts and
results must not be written into the network snapshot.

`traffic.json` defines a 20-Gbps ordinary IP flow from X to D and an 80-Gbps SR-policy flow from S
to D. The initial SR split is 50/50. The logical integer parameter `h` denotes the upper-path
percentage and simultaneously makes the lower-path percentage `100-h`.

The first-stage runner will enumerate the no-failure state and every single undirected-link failure,
recompute a concrete stable state, and require every surviving link load to be strictly below 95
Gbps. The `d_x` failure moves the X flow to X-A-D, so A-D carries `20 + 0.8h` Gbps and induces the
expected domain-relative subspec `h <= 93`.

The normalized SR candidate model requires positive configured weights. Endpoint values `h=0` and
`h=100` therefore denote candidate disablement in the logical experiment domain; the initial parsed
configuration uses the valid concrete realization `h=50`.
