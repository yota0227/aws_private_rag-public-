# N1B0 New Test Cases

All 18 tests follow the same firmware pattern as the existing tests in
`data_movement/tests/`. Each test lives in `<test_name>/src/main.cpp` and
`<test_name>/src/test_config.h`.

Reference: `/secure_data_from_tt/20260221/DOC/N1B0/DV_Guide_N1B0_v0.1.md`

---

## Test Index

| # | Test Name | Description | DV Hole IDs |
|---|-----------|-------------|-------------|
| 01 | `edc_sanity_row_harvest` | NOC write+readback between active Tensix rows after one row is harvested (ISO_EN applied). Verifies DOR routing and pattern integrity across the gap. | EDC-H1, EDC-H2 |
| 02 | `edc_sanity_col_harvest` | NOC write+readback between active columns after one column is harvested. Destination column computed by skipping harvested col. | EDC-H3, EDC-H4 |
| 03 | `smn_read_block_test` | SMN read-blocking: same-group tile reads GROUP_RANGE (expect success); diff-group tile reads same range (expect blocked/garbage). Results logged to scratch. | SMN-H1, SMN-H2 |
| 04 | `smn_violation_log_readback` | Diff-group tile issues a cross-group NOC write to trigger a BIU SMN violation. Reads back BIU_VIOLATION_STATUS/ADDR_LO/ADDR_HI/SRC_ID registers and logs them to scratch. | SMN-H3, SMN-H4 |
| 05 | `smn_all_8_ranges` | Exercises all 8 SMN address ranges: same-group tile writes to each range_start (expect success) and diff-group tile writes to range_start+16 (expect blocked). Config provided by Python. | SMN-H5, SMN-H6 |
| 06 | `noc_dor_vs_dynamic_routing` | Writes same payload twice: once with DIM_ORDER=XY and once with DIM_ORDER=YX. Records mcycle counts for both and verifies data integrity on readback. | NOC-H1, NOC-H2 |
| 07 | `all_to_all_write` | Every Tensix tile writes its local data to every other tile's designated region. Barrier via L1 sync flags polled by tile (0,0). Performance logged to PERF_BASE. | NOC-H3, NOC-H4 |
| 08 | `fds_interrupt_mode` | FDS sanity with INTERRUPT_ENABLE=1 on both Dispatch and NEO sides. Status-register polling approximates the interrupt path. Same subgrid layout as fds_sanity. | FDS-H1, FDS-H2 |
| 09 | `fds_multi_epoch` | FDS GO/DONE exchange for up to 16 epochs (NUM_PHASES read from config[0]). Phase count tracked per-tile in scratch registers. | FDS-H3, FDS-H4 |
| 10 | `fds_groupid_zero_reserved` | Dispatch sends GroupID=0 (reserved). Polls GROUPID_COUNT[0] for 10M cycles — no increment expected (logs 0x0001). Then sends VALID_GROUPID=1 and confirms normal handshake. | FDS-H5 |
| 11 | `fds_filter_threshold_corner` | FDS sanity with 1 phase; FILTER_THRESHOLD read from config[0] at runtime. Run twice by Python: once with threshold=0 (passthrough), once with threshold=0xFFFF (max de-glitch). | FDS-H6, FDS-H7 |
| 12 | `att_disabled_passthrough` | Explicitly calls noc_address_translation_table_en(false, false), then writes/reads using raw physical XY coordinates. Verifies raw-address mode is unaffected when ATT is off. | ATT-H1 |
| 13 | `att_partial_table` | Enables ATT send path, fills only 6 of 12 endpoint entries. Issues reads to an in-table endpoint (expect success) and an out-of-table endpoint (log result). | ATT-H2, ATT-H3 |
| 14 | `l1_full_capacity` | Writer tile fills the full 768KB N1B0 L1 of a target tile via 192 x 4KB NOC writes (batched every 16). Target polls a sync flag then verifies all chunk patterns. | L1-H1, L1-H2 |
| 15 | `multi_col_harvest_routing` | Two columns harvested; src=lowest active col, dst=highest active col, both row 0. Verifies NOC write+readback routes correctly around two ISO_EN gaps. Also checks NOC_CONFIG_BROADCAST_COL_DISABLE bits are set for harvested columns. | EDC-H5, HARV-H1 |
| 16 | `noc_vc_backpressure` | Harts 0..(num_vcs-1) on tile (0,0) each use a different VC to send num_bursts x burst_size to tile (3,2). Records per-VC cycle counts in PERF_BASE. | NOC-H5, NOC-H6 |
| 17 | `write_repeat_power_stress` | Hart 0 issues posted NOC writes in a tight loop for stress_cycles cycles, then issues one final non-posted write and waits for ACK to confirm tile liveness. | NOC-H7, PWR-H1 |
| 18 | `iso_en_isolation_check` | Tile (src_col,0) attempts a NOC write to (iso_col,0) (ISO_EN pre-set by Python). Polls for ACK with 50M-cycle timeout. Logs RESULT_BLOCKED (0xB10C0000) if correct, RESULT_ACCESS_SUCCEEDED (0xACCE5500) if ISO not working. Follows with a liveness write to a non-isolated neighbor. | HARV-H2, ISO-H1 |

---

## Common Patterns

- Hart 0 only (`mhartid == 0`) unless the test explicitly uses multi-hart (test 16).
- Config block at `0x100000` written by Python before firmware launch.
- Postcodes written to `mmio::write_dm_scratch(0, ...)` for progress, scratch[1] for PASS/FAIL.
- `POSTCODE_PASS = 0x600DC0DE`, `POSTCODE_FAIL = 0xDEADFA17`.
- All tests call `cache::test_pass(mhartid)` at the end.
