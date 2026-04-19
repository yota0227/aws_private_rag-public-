#!/usr/bin/python3.6
# -*- coding: utf-8 -*-

# Ver 0.01
# 2023-03-31 Harold: Release initial version for generating CMU logic

import re
import sys, getopt
import os
import shutil
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
    #os.system("/tools/env_synopsys.csh")

    dcHome = os.environ.get('DC_HOME')

    os.system("find . -name '*.sv' > tempList")
    os.system("find . -name '*.svh' >> tempList")
    os.system("find . -name '*.v' >> tempList")
    os.system("find . -name '*.vh' >> tempList")

    execFile = open("execList", 'w')

    with open("tempList", "r") as tempList:
        for line in tempList:
            newLine = line.rstrip()
            #execFile.write("synenc " + newLine + " -ansi" + " -o " + newLine + ".e\n")
            #execFile.write("synenc -r " + dcHome + " " + newLine + " -ansi" + " -o " + newLine + ".e\n")
            execFile.write("/data/tools/Synopsys/syn/U-2022.12-SP6/linux64/syn/bin/synenc -r " + dcHome + " " + newLine + " -ansi\n")

    execFile.close()

    os.system("chmod 777 ./execList")
    os.system("./execList")
    os.system("rm -rf ./execList")

    #os.system("find . -name '*.f' -exec sed -i 's/\.sv/.sv.e/g' {} \;")
    #os.system("find . -name '*.f' -exec sed -i 's/\.svh/.svh.e/g' {} \;")
    #os.system("find . -name '*.f' -exec sed -i 's/\.v/.v.e/g' {} \;")
    #os.system("find . -name '*.f' -exec sed -i 's/\.vh/.vh.e/g' {} \;")

    os.system("find . -name '*.sv' -exec rm -rf {} \;")
    os.system("find . -name '*.svh' -exec rm -rf {} \;")
    os.system("find . -name '*.v' -exec rm -rf {} \;")
    os.system("find . -name '*.vh' -exec rm -rf {} \;")

    with open("tempList", "r") as tempList:
        for line in tempList:
            newLine = line.rstrip()
            os.system("mv " + newLine + ".e " + newLine)

    tempList.close()

if __name__ == "__main__":
    main(sys.argv)

