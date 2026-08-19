# traffic_split_demo — classic IOS shell + ISIS/SR extensions

## Style
Same boilerplate / interface style as `networks/userstudy_networks/userstudy_network`
(`version 15.2`, `ip address`, `GigabitEthernet0/0`, …).

Only **ISIS + SR** use extension syntax Batfish does not fully support today.

## Topology
E = {r1-r2, r2-r3, r1-r3, r1-r4, r3-r4}. Capacity 95 Gbps is for the traffic engine.

## Nodes / SIDs
| Router | Loopback | `isis prefix-sid absolute` |
|--------|----------|----------------------------|
| r1     | 1.1.1.1  | 16001                      |
| r2     | 2.2.2.2  | 16002                      |
| r3     | 3.3.3.3  | 16003                      |
| r4     | 4.4.4.4  | 16004                      |

## Flows / SR-TE (initial)
| Flow | Head-end | Policy       | Paths                         | Weights | Steering                                      |
|------|----------|--------------|-------------------------------|---------|-----------------------------------------------|
| f1   | r1       | POL_F1_TO_R4 | p1: 4.4.4.4; p2: 3.3.3.3→4.4.4.4 | **60:40** (`h0=0.6`) | `ip route 4.4.4.4/32 segment-routing policy …` |
| f2   | r2       | POL_F2_TO_R4 | q1: 1.1.1.1→4.4.4.4; q2: 3.3.3.3→4.4.4.4 | 50:50 | same pattern |

## What Batfish can parse today vs later
| Block | Today | Later extension |
|-------|-------|-----------------|
| hostname / interfaces / `ip address` | yes (IOS) | — |
| classic `router isis` + `ip router isis` | mostly yes | — |
| `segment-routing mpls` / `isis prefix-sid` | no / partial | ISIS-SR |
| `segment-routing traffic-eng` + weights | no | SR-TE |
| `ip route … segment-routing policy` | no | steering |
