# N1B0 NPU — Chip-Level HDD (Grounded)

> **Pipeline ID:** tt_20260221 | **Version:** v6c | **RAG:** v4.1 + Package Parser v2
> **Rule:** KB-only. Missing = `[NOT IN KB]`.

---

## KB-Confirmed Facts

| Block | Source | Data |
|-------|--------|------|
| Package | claim | 13 localparams: SizeX=4..NumDirections=2 |
| tile_t | claim | 8 members: TENSIX..ROUTER |
| clock_routing_t | claim | 8 fields: ai_clk..power_good |
| noc enums | claim | noc_axis_t, noc_direction_t |
| trinity.sv | module_parse | Ports + instances |
| Clock | claim | tt_clkbuf, tt_clkgater, tt_clkdiv2 |
| DFX | claim | tt_instrn_engine_wrapper_dfx 11in/9out |

## [NOT IN KB]

Top-level port 전체, deep hierarchy, FPU/SFPU/TDMA 내부, NoC algorithms, EDC topology, SRAM inventory, Power management