# N1B0 FPU Grid Mapping Visual Guide
**Version:** 1.0  
**Date:** 2026-04-08  
**Purpose:** Explain the 3D spatial layout of G-Tile, M-Tile, and Columns  

---

## Quick Reference: What Each Term Means

| Term | What It Is | Location | Quantity | Purpose |
|------|-----------|----------|----------|---------|
| **NEO (Tile)** | Complete FPU unit | One per cluster | 48 per chip | Independent compute tile |
| **G-Tile** | Column container | Horizontal split | 2 per NEO | Groups 8 M-Tiles together |
| **M-Tile** | Booth column | Vertical slice | 16 per NEO | One MAC column |
| **Column** | Same as M-Tile | X-axis (horizontal) | 16 per NEO | Processes same SRCB[col] for all rows |
| **Row** | Output dimension | Y-axis (vertical) | 8 per column | Produces different DEST rows |
| **FP-Lane** | Physical MAC | Inside M-Tile | 256 per NEO | Actual multiply-add circuits |

---

## The Grid: One NEO Laid Out in 2D

```
                      ← SRCA broadcast (same row value to all columns) →
                      ← SRCB broadcast (same column value to all rows) →

             0    1    2    3    4    5    6    7  │  8    9   10   11   12   13   14   15
           ┌────┬────┬────┬────┬────┬────┬────┬────┼────┬────┬────┬────┬────┬────┬────┬────┐
         0 │ M0 │ M1 │ M2 │ M3 │ M4 │ M5 │ M6 │ M7 │ M8 │ M9 │M10 │M11 │M12 │M13 │M14 │M15 │
           ├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┤
         1 │ M0 │ M1 │ M2 │ M3 │ M4 │ M5 │ M6 │ M7 │ M8 │ M9 │M10 │M11 │M12 │M13 │M14 │M15 │
           ├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┤
         2 │ M0 │ M1 │ M2 │ M3 │ M4 │ M5 │ M6 │ M7 │ M8 │ M9 │M10 │M11 │M12 │M13 │M14 │M15 │
           ├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┤
O        3 │ M0 │ M1 │ M2 │ M3 │ M4 │ M5 │ M6 │ M7 │ M8 │ M9 │M10 │M11 │M12 │M13 │M14 │M15 │
U          ├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┤
T        4 │ M0 │ M1 │ M2 │ M3 │ M4 │ M5 │ M6 │ M7 │ M8 │ M9 │M10 │M11 │M12 │M13 │M14 │M15 │
P          ├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┤
U        5 │ M0 │ M1 │ M2 │ M3 │ M4 │ M5 │ M6 │ M7 │ M8 │ M9 │M10 │M11 │M12 │M13 │M14 │M15 │
T          ├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┤
           │ M0 │ M1 │ M2 │ M3 │ M4 │ M5 │ M6 │ M7 │ M8 │ M9 │M10 │M11 │M12 │M13 │M14 │M15 │
         6 ├────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┼────┤
           │ M0 │ M1 │ M2 │ M3 │ M4 │ M5 │ M6 │ M7 │ M8 │ M9 │M10 │M11 │M12 │M13 │M14 │M15 │
         7 └────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┴────┘

             └────────────  G-TILE[0]  ────────────┘  └────────────  G-TILE[1]  ────────────┘
                    (8 M-Tiles)                             (8 M-Tiles)
            
Legend:
  M0..M15 = M-Tile instance at (column, row) = (0,0), (1,0), ..., (15,7)
  Each cell represents ONE M-Tile
  
Column Orientation:
  • Column 0 = M0 (all 8 rows)
  • Column 1 = M1 (all 8 rows)
  • ... etc ...
  • Column 15 = M15 (all 8 rows)
```

---

## Understanding "Column" (What Is a Column?)

### **Column = One M-Tile = One Vertical Booth Multiplier**

```
Column 5 Detailed View:

        SRCB[5] broadcast
        ↓ (same value for all rows)
        
    ┌─────────────┐
    │   Column 5  │  ← This is ONE M-Tile
    │ (M-Tile[5]) │  ← One Booth multiplier
    ├─────────────┤
Row │ ●●  ●●  ●● │  ← 2 FP-Lanes (process 2 INT8 products)
  0 │             │     Output → DEST[row0, col5]
    ├─────────────┤
Row │ ●●  ●●  ●● │  ← 2 FP-Lanes
  1 │             │     Output → DEST[row1, col5]
    ├─────────────┤
Row │ ●●  ●●  ●● │  ← 2 FP-Lanes
  2 │             │     Output → DEST[row2, col5]
    ├─────────────┤
Row │ ●●  ●●  ●● │  ← 2 FP-Lanes
  3 │             │     Output → DEST[row3, col5]
    ├─────────────┤
Row │ ●●  ●●  ●● │  ← 2 FP-Lanes
  4 │             │     Output → DEST[row4, col5]
    ├─────────────┤
Row │ ●●  ●●  ●● │  ← 2 FP-Lanes
  5 │             │     Output → DEST[row5, col5]
    ├─────────────┤
Row │ ●●  ●●  ●● │  ← 2 FP-Lanes
  6 │             │     Output → DEST[row6, col5]
    ├─────────────┤
Row │ ●●  ●●  ●● │  ← 2 FP-Lanes
  7 │             │     Output → DEST[row7, col5]
    └─────────────┘

Per Cycle Throughput (Column 5):
  • 8 rows × 2 FP-Lanes/row = 16 FP-Lane operations
  • In INT8_2x mode: 8 rows × 2 INT8 products/row = 16 INT8 MACs
  
All Columns Active (0-15):
  • 16 columns × 16 INT8 MACs/column = 256 INT8 MACs per G-Tile
  • 2 G-Tiles × 256 = 512 INT8 MACs per NEO (single phase)
  • With dual-phase: 512 × 2 = 1,024 INT8 MACs per NEO
```

**Key Point:** The column runs *vertically* (down all 8 rows). Each column is completely independent from others and operates in parallel.

---

## Understanding "Row" (What Is a Row?)

### **Row = Output Row in GEMM = Different DEST Rows**

```
Row 3 Detailed View (across all columns):

All columns (0-15) process Row 3 simultaneously:

SRCA[row3] = [for all columns 0-15]  (actually SRCA[set1][col] depends on row)
SRCB[col] = [broadcast to row 3]    (each column reads its own SRCB, row 3 uses it)

                     Booth products for Row 3
                     ↓
    Col0  Col1  Col2  Col3  Col4  Col5  Col6  Col7 │ Col8  Col9  Col10 ... Col15
    ──┬──  ──┬──  ──┬──  ──┬──  ──┬──  ──┬──  ──┬──  ──┬── │ ──┬──  ──┬──  ──┬──     ──┬──
      │    │    │    │    │    │    │    │       │    │    │         │
      └─────────────────────────────────────┬─────┴────────────────────────────────┘
                                            │
                        All write to DEST row 3 (different columns)

Per Cycle Output for Row 3:
  • 16 M-Tiles × 2 products/M-Tile = 32 outputs for row 3
  • Distributed across 16 columns of DEST row 3
```

**Key Point:** The row runs *horizontally* (across all 16 columns). Each column's Booth multiplier produces output for the same output row, but different DEST columns.

---

## Understanding "G-Tile" (Container for 8 Columns)

### **G-Tile = Column Container (Groups Columns for Clock Gating)**

```
                G-TILE[0]               G-TILE[1]
        ┌────────────────────┐  ┌────────────────────┐
        │  Columns 0-7       │  │  Columns 8-15      │
        │                    │  │                    │
        │  M0  M1  M2  M3    │  │  M8  M9  M10 M11   │
        │  M4  M5  M6  M7    │  │  M12 M13 M14 M15   │
        │                    │  │                    │
        └────────────────────┘  └────────────────────┘
         ↑                       ↑
         └─ Column 0 starts      └─ Column 8 starts
         └─ 8 columns (0-7)      └─ 8 columns (8-15)
         └─ 128 FP-Lanes         └─ 128 FP-Lanes

G-TILE[0]:
  Shared Register Files (with G-TILE[1]):
    • SRCA: 16 KB (shared)
    • SRCB: 32 KB (shared)
    • SRCS: 384 B (shared)
    • DEST: 32 KB (shared)
  
  Independent Clock Gating:
    • Can gate G-TILE[0] off while G-TILE[1] active
    • Power-saving mechanism
    
G-TILE[1]:
  Same structure as G-TILE[0]
  Independent enable signal
```

**Key Point:** G-Tile is just a container that groups 8 columns for organizational and power-gating purposes. Both G-Tiles share the same register files.

---

## Coordinate System: (Column, Row) Addressing

### **2D Coordinate Mapping**

```
Address Format: M-Tile[column][row]

Example Addresses:

M-Tile[0][0]   = Top-left corner (Column 0, Row 0)
M-Tile[7][0]   = Right edge of G-Tile[0] (Column 7, Row 0)
M-Tile[8][0]   = Left edge of G-Tile[1] (Column 8, Row 0)
M-Tile[15][0]  = Top-right corner (Column 15, Row 0)

M-Tile[5][3]   = Middle column, middle row (Column 5, Row 3)
M-Tile[15][7]  = Bottom-right corner (Column 15, Row 7)

DEST Storage:
  DEST[row][column] = Output at (column, row)
  
  Example: DEST[3][5] = Output at M-Tile[5][3]
           (Row 3 output from Column 5's Booth multiplier)

SRCA/SRCB Access:
  SRCA[set][col][row_addr]    ← Set determined by row index
  SRCB[col]                    ← Broadcast to all rows
  
  Example: SRCA[set=0][col=5]  = Operand for column 5, rows 0-1
           SRCA[set=1][col=5]  = Operand for column 5, rows 2-3
           SRCB[col=5]         = Broadcast to all 8 rows
```

---

## One Complete Cycle Execution Example

### **Scenario: Processing INT8 GEMM with Column 5, Row 3**

```
Input Stage:
─────────────

Registers (read combinational):
  SRCA[set1][col=5] = [INT8_B | INT8_A]     (e.g., [127 | 50])
  SRCB[col=5]       = [INT8_D | INT8_C]     (e.g., [100 | 30])
  
  These values read broadcast to ALL rows in column 5

Format Pre-processing (combinational):
  srca_low[5]  = SRCA[set1][5][7:0]   = 50
  srca_high[5] = SRCA[set1][5][15:8]  = 127
  srcb_low[5]  = SRCB[5][7:0]         = 30
  srcb_high[5] = SRCB[5][15:8]        = 100

Compute Stage (Booth Multiplier, Row 3):
──────────────────────────────────────

Booth Column 5, Row 3 (2 FP-Lanes):
  FP-Lane r0: INT8_A × INT8_C = 50 × 30 = 1,500  (→ INT32)
  FP-Lane r1: INT8_B × INT8_D = 127 × 100 = 12,700 (→ INT32)

Accumulation (Read-Modify-Write in same cycle):
──────────────────────────────────────────────

DEST Read:
  current_dest_r0 = DEST[3][5×2+0] = (previous accumulated sum, e.g., 100,000)
  current_dest_r1 = DEST[3][5×2+1] = (previous accumulated sum, e.g., 200,000)

Accumulate:
  new_dest_r0 = 100,000 + 1,500 = 101,500
  new_dest_r1 = 200,000 + 12,700 = 212,700

DEST Write:
  DEST[3][5×2+0] ← 101,500
  DEST[3][5×2+1] ← 212,700

Output:
───────
One NEO produces 256 INT8 MACs in this cycle
(16 columns × 8 rows × 2 lanes = 256)

All accumulations happen in parallel across all 256 FP-Lanes.
```

---

## CSV File Quick Guide

See **FPU_GridMapping.csv** for detailed component-by-component mapping:

| Section in CSV | What It Contains |
|---|---|
| **Component_Type** | G-Tile, M-Tile, FP-Tile, FP-Lane, Register File labels |
| **ID** | Instance number (G-Tile[0], M-Tile[5], etc.) |
| **G-Tile** | Which G-Tile container it belongs to |
| **Column_Index** | Physical column location (0-15 or range 0-7, 8-15) |
| **Purpose** | What the component does |
| **Summary Statistics** | Total counts, throughput numbers |
| **Column Understanding** | What "column" means and examples |
| **Row Understanding** | What "row" means and examples |
| **G-Tile Understanding** | Purpose and function |
| **M-Tile Understanding** | Purpose and function |
| **FP-Lane Understanding** | Purpose and function |

---

## Translation Guide: HDD Terminology → Physical Grid

| HDD Says | Means | Physical Location |
|----------|-------|-------------------|
| "M-Tile mode (INT8 mode)" | FPU operating with INT8 packing | All 16 M-Tiles active, Booth split into 2 INT8s |
| "G-Tile mode (FP32 mode)" | FPU operating with FP32 | All 16 M-Tiles active, Booth processes full 16-bit |
| "256 FP-Lanes per NEO" | 256 physical MAC units | 16 columns × 8 rows × 2 lanes/row |
| "64 FMA/cycle" | Baseline FP32 throughput | 4 active rows × 16 columns × 1 FMA/cycle |
| "512 INT8 MACs/cycle" | Peak INT8 with dual-phase | 256 INT8 (phase 1) + 256 INT8 (phase 2) |
| "One column" | One M-Tile | Vertical slice from row 0-7 |
| "All columns" | All 16 M-Tiles | Full 16×8 grid |
| "One row" | Output M-dimension | Horizontal slice across all columns |

---

**File Location:** `/secure_data_from_tt/20260221/DOC/N1B0/FPU_GRID_VISUAL_GUIDE.md`  
**CSV Location:** `/secure_data_from_tt/20260221/DOC/N1B0/FPU_GridMapping.csv`  
**Updated HDD:** `/secure_data_from_tt/20260221/DOC/N1B0/FPU_HDD_v1.0.md` (Section 1.1)
