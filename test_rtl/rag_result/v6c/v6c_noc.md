# NoC Subsystem HDD

> **Pipeline ID:** tt_20260221 | **Version:** v6c | **Search:** topic=NoC (17 results)

---

## Modules (9 unique)

| Module | Function |
|--------|----------|
| `tt_noc_repeaters_cardinal` | Cardinal-direction repeaters |
| `noc_arbiter_tree` | Tree-based priority arbitration |
| `tt_noc_secded_chk_corr_116_10` | SECDED ECC (116b+10b) |
| `tt_upf_async_fifo` | Async FIFO for CDC |
| `tt_noc_async_fifo_wr_side_reset` | FIFO reset gen |
| `tt_noc_sync3_pulse` | 3-stage pulse sync |
| `tt_skid_buffer_new_assertion_off` | I/O decoupling |
| `tt_harvest_robust_sync` | Harvest signal sync |
| `tt_niu_mst_timeout` | AXI master timeout |

## Bridge

noc2axi_router_nw_opt + tt_mem_wrap_32x1024_2p_nomask (ATT) + selftest (BIST)

## [NOT IN KB]

Routing algorithms, flit header, AXI gasket 56b, VC buffers, security fence, endpoint map, repeater placement