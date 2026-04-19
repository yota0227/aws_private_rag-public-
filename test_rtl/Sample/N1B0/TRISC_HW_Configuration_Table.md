# TRISC & TDMA Hardware Configuration Reference

**Version:** 2.0 (RTL-Verified)  
**Date:** 2026-04-09  
**Scope:** TRISC0/1/2/3 and TDMA (Pack/Unpack) inside tt_tensix_neo core  

## Module Hierarchy

```
tt_tensix_neo (Tensix NEO Compute Core)
└── tt_instrn_engine_wrapper (Instruction Engine Wrapper)
    └── tt_instrn_engine (Instruction Engine - contains TRISC & TDMA)
        ├── TRISC0 (instruction_thread0)
        ├── TRISC1 (instruction_thread1)
        ├── TRISC2 (instruction_thread2)
        ├── TRISC3 (instruction_thread3)
        ├── TDMA Pack Engine
        ├── TDMA Unpack Engine
        ├── MOP Sequencer
        ├── CfgExu (Configuration Register Banks)
        ├── SyncExu (Semaphore Hardware)
        └── L1 Client Interface

tt_neo_overlay_wrapper (Overlay/Data Movement Cluster - SEPARATE MODULE)
└── Overlay Stream Controller
    ├── NoC Packet Generator
    └── Stream Status Register File
```

---

## 1. RTL Module Locations

| Component | RTL File | Hierarchy | Purpose |
|-----------|----------|-----------|---------|
| **TRISC Cores** | `tt_instrn_engine.sv` | `tt_tensix_neo → tt_instrn_engine_wrapper → tt_instrn_engine` | Instruction execution (4 threads) |
| **TDMA Pack/Unpack** | `tt_instrn_engine.sv` | Inside tt_instrn_engine | Tensor DMA (format conversion) |
| **Overlay Module** | `tt_neo_overlay_wrapper.sv` | **SEPARATE** - sibling to tt_instrn_engine_wrapper | Data movement orchestration (NoC packets) |
| **MOP Sequencer** | `tt_instrn_engine.sv` | Inside tt_instrn_engine | FPU control loop generation |
| **SyncExu** | `tt_sync_exu.sv` | Inside tt_instrn_engine | Hardware semaphore execution |
| **CfgExu** | `tt_cfg_exu.sv` | Inside tt_instrn_engine | MOP configuration register banks |

---

## 2. TRISC Thread Configuration

| Parameter | TRISC0 | TRISC1 | TRISC2 | TRISC3 | Notes |
|-----------|--------|--------|--------|--------|-------|
| **RTL Module** | `tt_trisc.sv` | `tt_trisc.sv` | `tt_trisc.sv` | `tt_risc_wrapper.sv` | TRISC3 is RV32I general-purpose |
| **Instance Name** | `instruction_thread0` | `instruction_thread1` | `instruction_thread2` | `instruction_thread3` | Inside tt_instrn_engine |
| **Instance Path** | `tt_tensix_neo.tt_instrn_engine_wrapper.tt_instrn_engine.instruction_thread0` | Same pattern with `[1]`, `[2]`, `[3]` | Full path to each thread |
| **Clock Domain** | `i_ai_clk` | `i_ai_clk` | `i_ai_clk` | `i_ai_clk` | All synchronized to AI clock |
| **Reset** | `i_ai_rst_n` (async, active low) | `i_ai_rst_n` | `i_ai_rst_n` | `i_ai_rst_n` | Asynchronous reset for all |

---

## 3. Instruction Memory (IMEM)

| Parameter | TRISC0 | TRISC1 | TRISC2 | TRISC3 | Notes |
|-----------|--------|--------|--------|--------|-------|
| **IMEM Location (L1)** | `0x06000` | `0x16000` | `0x26000` | `0x36000` | Fixed per Trinity architecture |
| **ICache Depth (entries)** | 256 × 32-bit | 256 × 32-bit | 256 × 32-bit | 512 × 32-bit | TRISC3 has larger I-cache |
| **ICache Size (bytes)** | 1 KB | 1 KB | 1 KB | 2 KB | |
| **ICache Backing** | L1 IMEM region | L1 IMEM region | L1 IMEM region | L1 IMEM region (or private IRAM) | Shared unless `TRISC_IRAM_ENABLE[3]=1` |
| **Instruction Fetch** | 32-bit per cycle | 32-bit per cycle | 32-bit per cycle | 32-bit per cycle | All fixed-width RV32I |
| **Instruction Width** | 32 bits (RV32I + custom) | 32 bits (RV32I + custom) | 32 bits (RV32I + custom) | 32 bits (RV32I) | Standard RISC-V format |
| **ISA Type** | Tensor (custom extensions) | Tensor (custom extensions) | Tensor (custom extensions) | RV32I base (general-purpose) | TRISC3 has full RV32I |
| **Opcode Space** | Custom opcodes | Custom opcodes | Custom opcodes | Standard RV32I opcodes | See opcode_pkg.sv |

---

## 4. TDMA (Tensor DMA) - Inside tt_instrn_engine

**Location:** `tt_tensix_neo → tt_instrn_engine_wrapper → tt_instrn_engine`

**Components:**
- **Pack Engine** — Reads DEST latch-array, formats output, writes to L1 via CSR
- **Unpack Engine** — Reads L1 data, unpacks activation tensors, loads into SRCA/SRCB
- **TDMA Control** — UNPACR/PACR instruction decoders

| Feature | Pack Engine | Unpack Engine | Notes |
|---------|-------------|---------------|-------|
| **Control by** | TRISC2 (PACR instruction) | TRISC0 (UNPACR instruction) | Separate TDMA paths |
| **Input** | DEST latch-array (32 KB) | L1 SRAM (3 MB per cluster) | Read sources |
| **Output** | L1 SRAM or NoC | SRCA/SRCB register files | Write destinations |
| **Format Control** | THCON_PACKER config reg | THCON_UNPACKER config reg | Programmable via WRCFG |
| **Integration** | Part of pack pipeline (TRISC2) | Part of unpack pipeline (TRISC0) | 3-stage FPU pipeline |
| **Clock Domain** | `i_ai_clk` | `i_ai_clk` | Same as TRISC cores |

---

## 5. Local Data Memory (LDM)

| Parameter | TRISC0 | TRISC1 | TRISC2 | TRISC3 | Notes |
|-----------|--------|--------|--------|--------|-------|
| **LDM Size (bytes)** | **4,096 (4 KB)** | **2,048 (2 KB)** | **2,048 (2 KB)** | **4,096 (4 KB)** | Private per-thread SRAM |
| **LDM Width** | 32-bit | 32-bit | 32-bit | 32-bit | Single port, standard access |
| **LDM Depth** | 1024 × 32b | 512 × 32b | 512 × 32b | 1024 × 32b | As bytes / 4 |
| **ECC Type** | SECDED 52/32 | SECDED 52/32 | SECDED 52/32 | SECDED 52/32 | 5 bits per byte |
| **LDM Purpose** | Unpack loop state, counters | Math MOP state | Pack loop variables, pointers, stack | Interrupt stack, boot data, DMA buffers | Per-thread local storage |
| **L1 Address Isolation** | Mapped via address window | Mapped via address window | Mapped via address window | Mapped via address window | Hardware address range check |
| **Bandwidth** | 1 × 32-bit/cycle | 1 × 32-bit/cycle | 1 × 32-bit/cycle | 1 × 32-bit/cycle | Non-blocking write, pipelined |

---

## 4. L1 Access Port

| Parameter | TRISC0 | TRISC1 | TRISC2 | TRISC3 | Notes |
|-----------|--------|--------|--------|--------|-------|
| **L1 Data Width** | **128-bit** | **128-bit** | **128-bit** | **128-bit** | Per-thread, 4 × 32-bit words |
| **L1 Access Type** | READ, WRITE, AT_PARTIALW, AT_RISCV | READ, WRITE, AT_PARTIALW, AT_RISCV | READ, WRITE, AT_PARTIALW, AT_RISCV | READ, WRITE, AT_PARTIALW, AT_RISCV | Atomic ops supported |
| **L1 Outstanding Reqs** | 16 (32 in large mode) | 16 (32 in large mode) | 16 (32 in large mode) | 16 (32 in large mode) | MAX_L1_REQ parameter |
| **L1 Address Range Check** | Yes (`i_trisc_l1_start_addr[0]` / `_end_addr[0]`) | Yes (`i_trisc_l1_start_addr[1]` / `_end_addr[1]`) | Yes (`i_trisc_l1_start_addr[2]` / `_end_addr[2]`) | Yes (`i_trisc_l1_start_addr[3]` / `_end_addr[3]`) | Per-thread window programmed at boot |
| **L1 ECC** | SECDED per 128b | SECDED per 128b | SECDED per 128b | SECDED per 128b | Single-bit correct, double-bit detect |
| **L1 Latency** | 4–8 cycles | 4–8 cycles | 4–8 cycles | 4–8 cycles | Includes arbitration and memory access |
| **ICache Fetch Latency** | 1–2 cycles | 1–2 cycles | 1–2 cycles | 1–2 cycles | Hardware prefetch supported |

---

## 5. GPR (General-Purpose Register) File

| Parameter | TRISC0 | TRISC1 | TRISC2 | TRISC3 | Notes |
|-----------|--------|--------|--------|--------|-------|
| **GPR Count** | 32 (x0–x31) | 32 (x0–x31) | 32 (x0–x31) | 32 (x0–x31) | Standard RV32I convention |
| **GPR Width** | 32-bit | 32-bit | 32-bit | 32-bit | All integer registers |
| **Read Ports** | 2 (async) | 2 (async) | 2 (async) | 2 (async) | Dual-read per cycle |
| **Write Ports** | 1 (sync) | 1 (sync) | 1 (sync) | 1 (sync) | Single write per cycle |
| **ECC** | Optional parity (Trinity TFD mode) | Optional parity | Optional parity | Optional parity | GPR file protection |
| **MMIO Access** | Yes, `0x0080D000` | Yes, `0x0080D000` | Yes, `0x0080D000` | Yes, `0x0080D000` | Firmware-visible register access |

---

## 6. Synchronization Hardware

| Parameter | TRISC0 | TRISC1 | TRISC2 | TRISC3 | Notes |
|-----------|--------|--------|--------|--------|-------|
| **Semaphore Count** | 32 shared | 32 shared | 32 shared | 32 shared | Per-tile, not per-thread |
| **Semaphore Width** | 4-bit saturating | 4-bit saturating | 4-bit saturating | 4-bit saturating | Range 0–15 per semaphore |
| **SEMINIT Support** | Yes | Yes | Yes | Yes | Initialize semaphore bounds |
| **SEMGET Support** | Yes (stalls on 0) | Yes (stalls on 0) | Yes (stalls on 0) | Yes (stalls on 0) | Hardware pipeline freeze via SyncExu |
| **SEMPOST Support** | Yes | Yes | Yes | Yes | Increment counter |
| **SEMWAIT Support** | Yes | Yes | Yes | Yes | Wait for condition |
| **Hardware SEMPOST** | Yes (from FPU/TDMA) | Yes (from FPU/TDMA) | Yes (from FPU/TDMA) | No | Auto-post on MOP completion |
| **Stall Mechanism** | Gate-level pipeline freeze | Gate-level pipeline freeze | Gate-level pipeline freeze | Gate-level pipeline freeze | Zero power while stalled |
| **Arbitration** | SyncExu unit | SyncExu unit | SyncExu unit | SyncExu unit | Handles simultaneous access |

---

## 7. FPU Access (TRISC1/TRISC2 primary)

| Parameter | TRISC0 | TRISC1 | TRISC2 | TRISC3 | Notes |
|-----------|--------|--------|--------|--------|-------|
| **FPU Config Bus** | No direct write | Yes (128-bit `cfg_reg`) | No direct write | Yes (128-bit `cfg_reg`) | Per-thread config register interface |
| **MOP Issue** | No | **Yes** (`MOP` instruction) | No | No | TRISC1 issues MOP for math |
| **MOP_CFG** | No | **Yes** (program CfgExu dual-bank) | No | No | Configure next MOP pre-load |
| **SRCA/SRCB Read** | Via UNPACR | Implicit (FPU datapath) | No | No | TRISC0 fills via unpacker |
| **DEST Read** | No | No | **Yes** (via PACR) | No | TRISC2 drains via packer |
| **SFPU Control** | No | Yes (SFPU instructions) | No | **Yes** (kernel control) | TRISC3 manages SFPU sequencing |
| **Math Pipeline** | No access | Full control | No access | Kernel-level control | TRISC1 drives per-cycle |

---

## 8. TDMA (Tensor DMA) Access

| Parameter | TRISC0 | TRISC1 | TRISC2 | TRISC3 | Notes |
|-----------|--------|--------|--------|--------|-------|
| **UNPACR Issue** | **Yes** (trigger unpacker) | No | No | No | TRISC0 loads L1 → SRCA/SRCB |
| **PACR Issue** | No | No | **Yes** (trigger packer) | No | TRISC2 drains DEST → L1 |
| **TDMA Config Write** | Yes (`WRCFG` THCON_UNPACKER) | No | Yes (`WRCFG` THCON_PACKER) | No | Configure pack/unpack format |
| **L1→SRCA/SRCB** | Initiator (UNPACR) | Passive (reads result) | N/A | N/A | Unpack path |
| **DEST→L1** | N/A | Producer (math output) | Initiator (PACR) | N/A | Pack path |
| **Format Conversion** | Input to unpacker | Output to SFPU | Input to packer | Kernel control | Per-operation specification |

---

## 9. Watchdog & Timeout

| Parameter | TRISC0 | TRISC1 | TRISC2 | TRISC3 | Notes |
|-----------|--------|--------|--------|--------|-------|
| **PC Buffer Timeout** | `pc_buff_timeout` counter | `pc_buff_timeout` counter | `pc_buff_timeout` counter | `pc_buff_timeout` counter | Fires if PC doesn't advance |
| **Instruction Buffer Timeout** | `ibuffer_timeout` counter | `ibuffer_timeout` counter | `ibuffer_timeout` counter | `ibuffer_timeout` counter | Fires if instruction buffer stalls |
| **Timeout Action** | Interrupt to TRISC3 (`o_trisc_timeout_intp`) | Interrupt to TRISC3 | Interrupt to TRISC3 | Self-interrupt capability | Hung kernel detection |
| **Reset PC Override** | Programmable by TRISC3 | Programmable by TRISC3 | Programmable by TRISC3 | Programmable by TRISC3 | `o_trisc_reset_pc` register |

---

## 10. Instruction Extensions (TRISC0/1/2 only)

| Instruction Type | TRISC0 | TRISC1 | TRISC2 | TRISC3 | RTL File |
|------------------|--------|--------|--------|--------|----------|
| **Standard RV32I** | Yes | Yes | Yes | Yes | RV32I specification |
| **Custom ALU** (ADDGPR, BITWOPGPR, CMPGPR) | Yes | Yes | Yes | No | `tt_t6_opcode_pkg.sv` |
| **Sync** (SEMGET, SEMPOST, SEMWAIT, SEMINIT) | Yes | Yes | Yes | Yes | `tt_sync_exu.sv` |
| **Atomic** (ATCAS, ATINCGET, ATGETM, etc.) | Yes | Yes | Yes | **Yes** (TRISC3 only) | `tt_risc_wrapper.sv` |
| **TDMA** (UNPACR, PACR, PACRNL) | **Yes** (UNPACR) | No | **Yes** (PACR) | No | `tt_instrn_engine.sv` |
| **Config** (RDCFG, WRCFG, CFGSHIFTMASK) | Yes | Yes | Yes | Yes | `tt_t6_opcode_pkg.sv` |
| **FPU** (MOP, MOP_CFG, MVMUL, ELWADD, DOTP) | No | **Yes** (MOP, MOP_CFG, SFPU) | No | **Yes** (SFPU kernel control) | `tt_instrn_engine.sv` |
| **Vector** (TRISC0 only, if enabled) | Yes (if `TRISC_VECTOR_ENABLE[0]=1`) | No | No | No | `DISABLE_VECTOR_UNIT` param |

---

## 11. Register File Access

| Memory Target | TRISC0 | TRISC1 | TRISC2 | TRISC3 | Mechanism |
|---------------|--------|--------|--------|--------|-----------|
| **L1 (instruction fetch)** | ✓ | ✓ | ✓ | ✓ | 32-bit ICache backed by L1 IMEM |
| **L1 (data read/write)** | ✓ | ✓ | ✓ | ✓ | 128-bit direct port |
| **LDM (private)** | ✓ | ✓ | ✓ | ✓ | 32-bit private SRAM |
| **SRCA register file** | ✓ (write, via UNPACR) | ✓ (read, via FPU) | ✗ | ✗ | TDMA unpack path |
| **SRCB register file** | ✓ (write, via UNPACR) | ✓ (read, via FPU) | ✗ | ✗ | TDMA unpack path |
| **DEST register file** | ✗ | ✓ (write, via FPU) | ✓ (read, via PACR) | ✗ | TDMA pack/math paths |
| **SRCS (SFPU)** | ✗ | ✓ (read, via SFPU) | ✗ | ✓ (write, via SFPU) | Scalar FPU operands |
| **FPU config registers** | ✗ | ✓ (via `cfg_reg` bus) | ✗ | ✓ (via `cfg_reg` bus) | 128-bit MMIO interface |
| **Semaphore registers** | ✓ | ✓ | ✓ | ✓ | Hardware sync unit |
| **External DRAM** | ✗ direct | ✗ direct | ✗ direct | ✗ direct | Via overlay stream CSR only |
| **NoC overlay regs** | ✓ (32-bit CSR write) | ✓ | ✓ | ✓ | TRISC-initiated DMA control |

---

## 12. Clock Gating & Power Control

| Feature | TRISC0 | TRISC1 | TRISC2 | TRISC3 | Notes |
|---------|--------|--------|--------|--------|-------|
| **Per-Thread Clock Gate** | `i_ai_clk` controlled by wrapper | `i_ai_clk` controlled by wrapper | `i_ai_clk` controlled by wrapper | `i_ai_clk` controlled by wrapper | Via DFX clock gating mux |
| **Instruction Issue Gate** | Yes (via `instrn_sem_stall[0]`) | Yes (via `instrn_sem_stall[1]`) | Yes (via `instrn_sem_stall[2]`) | Yes (via `instrn_sem_stall[3]`) | Gate-level when semaphore=0 |
| **L1 Access Gate** | Via instruction fetch | Via L1 port arbiter | Via L1 port arbiter | Via L1 port arbiter | No dedicated per-thread gate |
| **Independent Enable** | Yes per RTL params | Yes per RTL params | Yes per RTL params | Yes per RTL params | Each thread can be gated |
| **Power Saving Strategy** | Stall on SEMGET(0) | Stall on SEMGET(0) | Stall on SEMGET(0) | Stall on SEMGET(0) | Zero-power wait for synchronization |

---

## 13. RTL Instantiation Parameters

| Parameter | Value | Impact |
|-----------|-------|--------|
| `THREAD_COUNT` | `4` | Instantiates TRISC0–TRISC3 |
| `TRISC_IRAM_ENABLE` | `4'b0000` (default) | Bit[i] = 1 → private IRAM for TRISC[i]; 0 = shared L1 |
| `TRISC_VECTOR_ENABLE` | `4'b0001` (default) | Bit 0 = 1 → TRISC0 has vector extension; bits 1–3 scalar |
| `TRISC_FP_ENABLE` | `4'b1111` (default) | All four TRISCs have FP extension; enables custom FPU extensions |
| `DISABLE_VECTOR_UNIT` | Inverted by `TRISC_VECTOR_ENABLE` | Historical parameter; see N1B0_NPU_HDD §2.3.3 |
| `LOCAL_MEM_SIZE_BYTES[0]` | `4096` (TRISC0) | LDM capacity in bytes |
| `LOCAL_MEM_SIZE_BYTES[1]` | `2048` (TRISC1) | LDM capacity in bytes |
| `LOCAL_MEM_SIZE_BYTES[2]` | `2048` (TRISC2) | LDM capacity in bytes |
| `LOCAL_MEM_SIZE_BYTES[3]` | `4096` (TRISC3) | LDM capacity in bytes |

---

## 14. Per-Thread Roles & Synchronization

| Thread | Role | Key Instructions | Sync Points | Inner Loop Cycle |
|--------|------|------------------|-------------|------------------|
| **TRISC0** | Unpack (L1→SRCA/SRCB) | UNPACR, WRCFG, SEMPOST | Waits for L1 ready (TRISC3); posts sem0 to TRISC1 | Load tile → SRCA/SRCB |
| **TRISC1** | Math (FPU control) | MOP, MOP_CFG, WRCFG, SEMGET, SEMPOST | Waits sem0 (TRISC0); waits sem1 ready (TRISC2); posts sem1 | Read SRCA, issue MOP, wait DEST |
| **TRISC2** | Pack (DEST→L1) | PACR, PACRNL, WRCFG, SEMGET, SEMPOST | Waits sem1 (TRISC1); optionally posts sem0 to TRISC0 | Read DEST → L1 |
| **TRISC3** | Tile Mgmt (kernel orchestration) | ATCAS, ATGETM, SETDMAREG, full RV32I | Posts sem_kernel_start; waits sem_kernel_done | Manage NoC DMA, interrupts |

---

## 15. Memory Address Map (TRISC-Visible)

| Region | Base Address | Size | Access | Purpose |
|--------|--------------|------|--------|---------|
| **L1 data** | 0x00000000 | 8 MB | RW | Main tensor storage |
| **Local regs** | 0x00800000 | 45 KB | RW | TDMA/ALU/MOP config registers |
| **Tile counters** | 0x0080C000 | 1 KB | RW | Hardware loop counters |
| **GPRs** | 0x0080D000 | 4 KB | RW | GPR file MMIO access |
| **MOP config** | 0x0080E000 | 132 B | WR | MOP bank A/B programming |
| **IBuffer** | 0x0080F000 | 4 KB | RD | Instruction buffer read-back (debug) |
| **PCBuffer** | 0x00810000 | 4 KB | RD | PC buffer read-back (debug) |
| **TRISC Mailbox[0–3]** | 0x00811000–0x00811C00 | 4 KB total | RD | Inter-TRISC mailboxes |
| **Unpack Mailbox[0–2]** | 0x00812000–0x00812800 | 3 KB total | RD | Unpacker argument mailboxes |
| **DEST regs (direct)** | 0x00818000 | 32 KB | RW | DEST register file direct access |
| **Config regs** | 0x00820000 | 3.5 KB | RW | ALU/FPU config registers |
| **Global regs** | 0x01840000 | 8.5 KB | RW | Semaphores, EDC, NoC overlay |
| **Overlay regs** | 0x02000000 | 32 MB | RW | NoC overlay stream control |

---

## 16. Comparison: TRISC0 vs TRISC1 vs TRISC2 vs TRISC3

| Aspect | TRISC0 | TRISC1 | TRISC2 | TRISC3 |
|--------|--------|--------|--------|--------|
| **Primary Role** | Unpack | Math control | Pack | Tile management |
| **ISA Type** | Tensor extensions | Tensor extensions | Tensor extensions | RV32I general-purpose |
| **LDM Size** | 4 KB | 2 KB | 2 KB | 4 KB |
| **FPU Access** | None | Full (MOP) | None | SFPU kernel |
| **TDMA Access** | UNPACR (issue) | None | PACR (issue) | None |
| **Semaphore Role** | Producer (fill) | Consumer/Producer (compute) | Consumer (drain) | Orchestrator (kernel boundary) |
| **Vector Support** | Optional (if enabled) | Scalar only | Scalar only | RV32I (no vector) |
| **Interrupt Handler** | No | No | No | **Yes** |
| **Timeout Recovery** | Via TRISC3 | Via TRISC3 | Via TRISC3 | Self-recovery |
| **Module** | tt_trisc | tt_trisc | tt_trisc | tt_risc_wrapper |

---

## Separation: Tensix NEO vs. Overlay

### Tensix NEO Core (tt_tensix_neo)

**Contains:**
- TRISC0/1/2/3 instruction engines (4 lightweight compute threads)
- TDMA Pack/Unpack engines (tensor format conversion)
- MOP Sequencer (FPU control)
- SyncExu (hardware semaphores)
- CfgExu (FPU configuration banks)
- FPU (G-Tiles, M-Tiles, FP-Lanes)
- SFPU (scalar transcendental ops)

**Clock Domains:** `i_ai_clk` (compute clock)

**File:** `tt_instrn_engine.sv`, `tt_instrn_engine_wrapper.sv`

**Responsibility:** Local computation, tensor manipulation via TDMA, synchronization

---

### Overlay / Data Movement Cluster (tt_neo_overlay_wrapper)

**Separate Module (NOT inside tt_tensix_neo)**

**Contains:**
- Overlay Stream Controller (CSR interface → NoC packet injection)
- Stream Status Register File (progress tracking)
- NoC packet generation logic
- Clock domain crossing (ai_clk ↔ noc_clk ↔ dm_clk)
- L1 memory interface (512-bit side channel)
- SMN security gateway
- EDC integration

**Clock Domains:** `i_ai_clk`, `i_dm_clk`, `i_noc_clk`

**File:** `tt_neo_overlay_wrapper.sv`

**Responsibility:** DRAM ↔ L1 data movement via NoC, autonomous DMA orchestration

---

### Key Distinction

| Aspect | Tensix NEO (tt_tensix_neo) | Overlay (tt_neo_overlay_wrapper) |
|--------|---------------------------|----------------------------------|
| **Location** | Core compute module | Separate cluster-level module |
| **Purpose** | Instruction execution, local compute | DRAM/NoC data movement |
| **Components** | TRISC, TDMA, FPU, SFPU | Stream controller, NOC interface |
| **Clock Domains** | `i_ai_clk` (compute) | `i_ai_clk`, `i_dm_clk`, `i_noc_clk` |
| **RTL Files** | `tt_instrn_engine.sv`, `tt_tensix_neo/...` | `tt_neo_overlay_wrapper.sv` |
| **Interface** | CSR for overlay stream regs | Receives CSR writes, generates NoC packets |
| **TRISC Interaction** | TRISC0/1/2 run here | TRISC writes overlay CSRs to initiate DMA |

**Firmware View:**
- TRISC0/1/2 execute tight inner loops (pack/unpack/math) inside Tensix NEO
- TRISC3 manages DRAM DMA by writing overlay stream CSRs (which trigger Overlay module)
- Overlay autonomously generates NoC packets and manages L1 ↔ DRAM transfers

---

## References

### TRISC & TDMA (Inside Tensix NEO)
- `tt_instrn_engine.sv` — TRISC (4 threads), TDMA pack/unpack, MOP sequencer
- `tt_instrn_engine_wrapper.sv` — Instruction engine wrapper, DFX
- `tt_trisc.sv` — TRISC0/1/2 core implementation
- `tt_risc_wrapper.sv` — TRISC3 RV32I core
- `tt_t6_opcode_pkg.sv` — Custom instruction opcodes
- `tt_sync_exu.sv` — Hardware semaphore execution unit
- `tt_semaphore_reg.sv` — Semaphore register file
- `tt_cfg_exu.sv` — MOP configuration register banks

### Overlay (Separate Module)
- `tt_neo_overlay_wrapper.sv` — Data movement cluster (stream controller, NoC interface)

### Documentation
- `N1B0_NPU_HDD_v1.00.md` §2 (Tensix Compute Tile - TRISC/TDMA)
- `N1B0_NPU_HDD_v1.00.md` §3 (Overlay Engine - Data Movement Cluster)
- `trinity_hierarchy.csv` — Full module hierarchy with RTL paths

