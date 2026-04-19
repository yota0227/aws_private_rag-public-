#!/usr/bin/python3.6
# -*- coding: utf-8 -*-

# Ver 0.01
# 2023-03-31 Harold: Release initial version for generating CMU logic

import re
import sys, getopt
import os
import time
from parse import *
import openpyxl
import subprocess
import fnmatch
from collections import defaultdict
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill, Color
from openpyxl.utils import get_column_letter, coordinate_to_tuple
from openpyxl.worksheet.dimensions import ColumnDimension
from openpyxl.worksheet.dimensions import Dimension


def main(argv):
    #os.system("source /tools/env_synopsys.csh")

    startTime = time.time()

    os.system("find . -name '*.sv' > tempList")
    os.system("find . -name '*.svh' >> tempList")
    os.system("find . -name '*.v' >> tempList")
    os.system("find . -name '*.vh' >> tempList")

    with open("tempList", "r") as tempList:
        for line in tempList:
            newLine = line.rstrip()
            os.system("srun --sym=RTL-VCS vcs +auto3protect " + newLine)

    tempList.close()
    #os.system("find . -name '*.f' -exec sed -i 's/\.sv/.svp/g' {} \;")
    #os.system("find . -name '*.f' -exec sed -i 's/\.svh/.svhp/g' {} \;")
    #os.system("find . -name '*.f' -exec sed -i 's/\.v/.vp/g' {} \;")
    #os.system("find . -name '*.f' -exec sed -i 's/\.vh/.vhp/g' {} \;")

    os.system("find . -name '*.sv' -exec rm -rf {} \;")
    os.system("find . -name '*.svh' -exec rm -rf {} \;")
    os.system("find . -name '*.v' -exec rm -rf {} \;")
    os.system("find . -name '*.vh' -exec rm -rf {} \;")

    with open("tempList", "r") as tempList:
        for line in tempList:
            newLine = line.rstrip()
            os.system("mv " + newLine + "p " + newLine)

    tempList.close()

    endTime = time.time()

    print(f"{endTime - startTime:.5f} sec")

if __name__ == "__main__":
    main(sys.argv)

