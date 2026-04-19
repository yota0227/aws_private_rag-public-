# SRCS_NUM_ROWS_16B Naming Convention — Why "SRCS"? What Is "16B"?

**Date:** 2026-04-04  
**Purpose:** Explain the RTL parameter naming convention for source register files

---

## TL;DR

```
SRCS_NUM_ROWS_16B = 48

Breakdown:
├─ SRCS = SRC (source registers) in plural
│         ├─ SRCA = Source register file A (for operand A)
│         ├─ SRCB = Source register file B (for operand B)
│         └─ SRCS = Source register file S (Scalar FPU operands)
│
└─ NUM_ROWS_16B = Number of 16-bit (128-bit datum) rows
                = 48 rows × 16 bytes/row = 768 bytes per bank
```

---

## Part 1: What Does "SRCS" Mean?

### SRCS = "Source Registers" (Plural)

Trinity has **THREE source register files**:

| Register | Full Name | Purpose | Size | Users |
|----------|-----------|---------|------|-------|
| **SRCA** | Source Register A | Multiplicand operand | 6 KB | FPU Booth multiplier |
| **SRCB** | Source Register B | Multiplier operand | 4 KB | FPU Booth multiplier |
| **SRCS** | Source Register Scalar | Transcendental operands | 4 KB | SFPU (exp, log, sqrt, gelu) |

### Why Three?

The FPU pipeline has **two parallel paths**:

```
┌──────────────────────────────────────────────────────────┐
│                  FPU (Floating Point Unit)               │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  Path 1: Booth Multiplier (GEMM)                        │
│  ├─ Reads: SRCA (operand A)                             │
│  ├─ Reads: SRCB (operand B)                             │
│  └─ Writes: DEST (result C)                             │
│                                                          │
│  Path 2: SFPU (Scalar transcendental)                   │
│  ├─ Reads: SRCS (scalar operand)                        │
│  ├─ Reads: DEST (for fused operations)                  │
│  └─ Writes: DEST (result)                               │
│                                                          │
│  Both paths can run in PARALLEL without stalling        │
└──────────────────────────────────────────────────────────┘
```

**Key point:** SRCS is independent from SRCA/SRCB. The SFPU:
- Does NOT access SRCA or SRCB
- Only reads/writes DEST
- Enables transcendental ops (exp, log, gelu) to overlap with FPU matrix multiply

### RTL Module Names

```systemverilog
// From tt_tensix_pkg.sv
tt_srca_registers.sv    ← SRCA register file (6 KB)
tt_srcb_registers.sv    ← SRCB register file (4 KB)
tt_srcs_registers.sv    ← SRCS register file (4 KB) [hidden from many docs]
tt_gtile_dest.sv        ← DEST register file (64 KB)
```

---

## Part 2: What Does "NUM_ROWS_16B" Mean?

### The "16B" Part

**16B = 16 bytes = 128 bits** (one full datum width)

Each SRCA/SRCB row holds a **128-bit (16-byte) datum**:

```
SRCA/SRCB datum structure (16-bit notation):
┌──────────────────────┬──────────────────────┐
│  Upper 16 bits       │  Lower 16 bits       │
│  (part of 128-bit)   │  (part of 128-bit)   │
│                      │                      │
│  FP32 exponent/mant  │  FP16B data          │
│  OR 2 × INT8         │  OR 1 × INT16        │
└──────────────────────┴──────────────────────┘

Real size: 128 bits = 16 bytes = "16B" notation
```

### Why "NUM_ROWS_16B" Not Just "NUM_ROWS"?

The naming distinguishes **physical depth** from **logical data units**:

```
SRCS_NUM_ROWS_16B = 48

Physical interpretation:
├─ 48 rows
├─ Each row: 128-bit (16-byte) datum
└─ Total: 48 × 16 bytes = 768 bytes per SRCA bank

Related parameters in RTL (for contrast):
├─ SRCA_NUM_WORDS = 16      ← 16 words per SRCA row (across columns)
├─ SRCA_NUM_WORDS_MMUL = 16 ← Output words per FPU output row
├─ SRCB_NUM_DATUMS = 16     ← 16 datums per SRCB row
└─ SRCB_NUM_WORDS = 64      ← 64 total SRCB words
```

### The "16B" Naming Pattern in RTL

```systemverilog
// tt_tensix_pkg.sv constants

localparam DATUM_WIDTH_HF = 16;          // 16-bit half-float datum
localparam DEST_NUM_ROWS_16B = 1024;     // 1024 rows of 16-byte datums
localparam SRCS_NUM_ROWS_16B = 48;       // 48 rows of 16-byte datums
localparam SRCA_ADDR_WIDTH = $clog2(SRCS_NUM_ROWS_16B);  // 6-bit address
```

**Why use "16B" suffix?** Because it explicitly states the **datum width is 128 bits (16 bytes)**, making the physical depth unambiguous:
- SRCS_NUM_ROWS_16B = 48 → **48 × 128-bit rows = 768 bytes total**
- (vs. just saying "SRCS_NUM_ROWS = 48" which could be ambiguous without context)

---

## Part 3: SRCS_NUM_ROWS_16B in Context

### How It's Used in K=8192 INT8 GEMM

```
SRCS_NUM_ROWS_16B = 48  (this is the key constant)

For INT8_2x packing:
  K_tile = SRCS_NUM_ROWS_16B × 2 = 48 × 2 = 96 INT8 per pass
  
For K=8192:
  Passes = ⌈8192 / 96⌉ = 86 passes per GEMM
```

### Physical Interpretation

```
SRCA register file (6 KB total):
  ├─ Bank 0: 48 rows × 128 bits = 768 bytes
  ├─ Bank 1: 48 rows × 128 bits = 768 bytes (double-buffered)
  └─ Total: 1,536 bytes = 1.5 KB per pair

Per row:
  ├─ 4 column sets (for 4 output rows)
  ├─ 16 datums per set (for 16 output cols)
  └─ Per row reads: 4 × 16 = 64 datums × 16 bits = 128 bits ✓
```

### RTL Address Calculation

```systemverilog
// From tt_tensix_pkg.sv
localparam SRCS_NUM_ROWS_16B = 48;
localparam SRCS_ADDR_WIDTH = $clog2(SRCS_NUM_ROWS_16B);  // = 6 bits

// In firmware/MOP tag:
wire [SRCS_ADDR_WIDTH-1:0] srca_rd_addr;  // 6-bit address, range 0-47
// This selects one of 48 rows per read operation
```

---

## Part 4: Comparison With Other Register Files

### Related Naming Conventions

| Parameter | Value | Interpretation |
|-----------|-------|-----------------|
| `SRCS_NUM_ROWS_16B` | 48 | 48 rows of 16-byte datums (SRCA/SRCB depth) |
| `DEST_NUM_ROWS_16B` | 1024 | 1024 rows of 16-byte datums (DEST depth) |
| `SRCA_NUM_WORDS_MMUL` | 16 | 16 words per SRCA row (output column count) |
| `SRCA_NUM_SETS` | 4 | 4 column sets (output row count) |
| `SRCB_NUM_DATUMS` | 16 | 16 datums per SRCB row |

### The "NUM_ROWS_16B" vs "NUM_WORDS" Distinction

```
"NUM_ROWS_16B" = Physical address/row count
  └─ Used for row selection (address calculation)
     Example: srca_rd_addr selects one of 48 rows

"NUM_WORDS" = Width or element count within a row
  └─ Used for bit-width or element counting
     Example: SRCA_NUM_WORDS_MMUL = 16 columns
```

---

## Part 5: Complete Naming Breakdown

### SRCS_NUM_ROWS_16B = 48

```
┌─────────────────────────────────────────────────┐
│ SRCS_NUM_ROWS_16B = 48                          │
├─────────────────────────────────────────────────┤
│                                                 │
│ SRCS         ← SRC(source) registers in plural │
│              ├─ SRCA: operand A                │
│              ├─ SRCB: operand B                │
│              └─ SRCS: scalar FPU operands      │
│                                                 │
│ NUM_ROWS     ← Number of addressable rows      │
│                                                 │
│ 16B          ← Each row is 16 bytes (128 bits) │
│                                                 │
│ = 48 ← Specific value: 48 rows per bank        │
│                                                 │
│ Result:                                         │
│   48 rows × 128 bits = 6,144 bits = 768 bytes │
│   (per bank)                                    │
└─────────────────────────────────────────────────┘
```

### Physical Layout in RTL

```
SRCA register file structure:

┌────────────────────────────────────────────┐
│ SRCA Bank 0 (768 bytes)                    │
├────────────────────────────────────────────┤
│ Row 0:  [set_0|set_1|set_2|set_3]  × 16   │ ← 128 bits
│ Row 1:  [set_0|set_1|set_2|set_3]  × 16   │ ← 128 bits
│ ...                                        │
│ Row 47: [set_0|set_1|set_2|set_3]  × 16   │ ← 128 bits
└────────────────────────────────────────────┘

Address bits:
  SRCS_ADDR_WIDTH = $clog2(48) = 6 bits → selects rows 0-47
  Set bits = 2 bits → selects 4 column sets
  Column bits = 4 bits → selects 16 datums per set
```

---

## Summary Table

| Aspect | Value | Meaning |
|--------|-------|---------|
| **SRCS** | Source Registers | SRC plural; includes SRCA, SRCB, SRCS |
| **NUM_ROWS** | 48 | 48 addressable rows per SRCA bank |
| **16B** | 128 bits | Each row is 16 bytes (128-bit datum) |
| **Total per bank** | 768 bytes | 48 rows × 16 bytes |
| **Total both banks** | 1,536 bytes | Double-buffered for zero-stall prefetch |
| **Address width** | 6 bits | Selects one of 48 rows (0-47) |
| **K_tile (INT8_2x)** | 96 INT8 | 48 rows × 2 INT8/row (from packing) |
| **K passes (K=8192)** | 86 | ⌈8192 / 96⌉ |

---

## Conclusion

**SRCS_NUM_ROWS_16B = 48** means:
- **SRCS**: Three source register files (A, B, and Scalar)
- **NUM_ROWS**: 48 addressable rows
- **16B**: Each row holds one 16-byte (128-bit) datum
- **Total**: 48 rows/bank → enables K_tile=96 INT8 for INT8_2x packing → 86 passes for K=8192 GEMM

The "16B" suffix is intentional naming — it disambiguates the physical depth from logical element counts.
