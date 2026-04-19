if {![info exists ::SDC_DIR]} { set ::SDC_DIR {./}}
global SDC_DIR
set ::DESIGN_NAME tt_dispatch_top_east
if {![info exists ::tt_global_is_mapped]} { set ::tt_global_is_mapped 1 }
if {![info exists ::DESIGN_NAME]} { set ::DESIGN_NAME {tt_dispatch_top_east} }
global DESIGN_NAME
global tt_global_is_mapped

# This file contains procs that might be end up being usd in the redo file

################################################################################
# general procs for determining what tool is being run
################################################################################


global TIME_SCALE_FROM_PS
# TIME_SCALE_FROM_PS 1 ps / 0.001 ns
#  ns
#set TIME_SCALE_FROM_PS 0.001
#  ps
set TIME_SCALE_FROM_PS 1

#-------------------------------------------------------------------------------
proc myExecutable {} {
  if {[info vars ::synopsys_program_name] ne {}} {
    return $::synopsys_program_name
  } elseif {[info vars ::argv0] ne {}} {
    return [file tail $::argv0]
  } else {
    return "tempus"
  }
}

#-------------------------------------------------------------------------------
proc isInnovus {} {
  if { [myExecutable] eq "innovus"} { return true }
  #if { [myExecutable] eq "tempus"
  #  && [get_db flow_report_name] eq "opt_signoff"
  #   } { return true }
  return false
}

#-------------------------------------------------------------------------------
proc isTempus {} {
  if {[myExecutable] eq "tempus"} { return true }
  return false
}

#-------------------------------------------------------------------------------
proc isGenus {} {
  if {[myExecutable] eq "genus"} { return true }
  return false
}

#-------------------------------------------------------------------------------
proc isVoltus {} {
  if {[myExecutable] eq "voltus"} { return true }
  return false
}

#-------------------------------------------------------------------------------
proc isCadence {} {
  switch -exact -- [myExecutable] {
    genus   -
    innovus -
    tempus  -
    voltus  { return true }
    default { return false }
  }
  return false
}

#-------------------------------------------------------------------------------
proc isPT {} {
  if {[string match {pt*} [myExecutable]]} { return true }
  return false
}

#-------------------------------------------------------------------------------
proc isDC {} {
  if {[string match {dc*} [myExecutable]] || [string match {fc*} [myExecutable]]} { return true }
  return false
}

#-------------------------------------------------------------------------------
proc isSynopsys {} {
  if {[info vars ::synopsys_program_name] ne {}} { return true }
  return false
}


#-------------------------------------------------------------------------------
if {[info commands sleep] eq {}} {
  proc sleep {N} {
      after [expr {int($N * 1000)}]
  }
}

#-------------------------------------------------------------------------------
# return a unique list of clocks
#    in DC:
#      get_clocks {*_tck* *singlechain*}
#       --> { tck_singlechain vir_tck_singlechain vir_tck_singlechain}
#      getUniqueClocks {*_tck* *singlechain*}
#       --> { tck_singlechain vir_tck_singlechain}
#
proc getUniqueClocks {args} {
  return [get_clocks -quiet [lsort -unique [get_object_name [get_clocks -quiet {*}$args]]]]
}

#-------------------------------------------------------------------------------
# Returns the pins that match the given pre-multi-bit flop name
# Example:
#   getMbitPins hier1/hier2/my_flop_name/D
#   could match and return any (or all) of these
#     hier1/hier2/my_flop_name/D
#     hier1/hier2/CDN_MBIT_my_flop_name_MB_second_flop_name_MB_third_flop_name_MB_fourth_flop_name/D0
#     hier1/hier2/CDN_MBIT_first_flop_name_MB_my_flop_name_MB_third_flop_name_MB_fourth_flop_name/D1
#     hier1/hier2/CDN_MBIT_first_flop_name_MB_second_flop_name_MB_my_flop_name_MB_fourth_flop_name/D2
#     hier1/hier2/CDN_MBIT_first_flop_name_MB_second_flop_name_MB_third_flop_name_MB_my_flop_name/D3
#
#   getMbitPins hier1/hier2/my_flop_name/CK
#   could match either
#     hier1/hier2/my_flop_name/CK
#     hier1/hier2/CDN_MBIT_first_flop_name_MB_second_flop_name_MB_third_flop_name_MB_my_flop_name/CK
proc getMbitPins {pinName} {
  set libPinName [file tail $pinName]
  set cellName [file dirname $pinName]
  set mbitCellName [file tail $cellName]
  set hierName [file dirname $cellName]
  if {$hierName eq "."} {
    set hierName *
  } else {
    set hierName "*$hierName/"
  }
  set results [get_pins -quiet $pinName]
  append_to_collection -unique results [get_pins -quiet -hier  "*/${libPinName}" -filter "full_name=~*$pinName && full_name!~_MB_"]
  set candidates [get_pins -quiet -hier "*/${libPinName}*" -filter "full_name=~${hierName}*${mbitCellName}*/${libPinName}*"]
  foreach_in_collection p $candidates {
    set pName [get_object_name $p]
    if {[string match *_MB_* $pName]} {
      set cName [file dirname $pName]
      set lpName [file tail $pName]
      # remove the CDN_MBIT_part
      lassign [string map {CDN_MBIT_ { }} $cName] preMbit postMbit
      if {$postMbit eq {}} {
        set postMbit $preMbit
        set preMbit {}
      }
      if {$preMbit eq {}} {
        set postMbit [file tail $postMbit]
        set preMbit [file dirname $postMbit]
      }
      if {$preMbit eq "."} {
        set preMbit {}
      } elseif {$preMbit ne {} && ![string match {*/} $preMbit]} {
        append preMbit "/"
      }
      set i 0
      foreach root [string map {_MB_ { }} $postMbit] {
        if {[string match $cellName "${preMbit}$root"]} {
          if { "$lpName" eq "$libPinName"
            || "$lpName" eq "${libPinName}${i}"
          } {
            append_to_collection -unique results $p
          }
        }
        incr i
      }
    }
  }
  return $results
}


#-------------------------------------------------------------------------------
# Returns the pins that match the given pre-multi-bit flop name
# Example:
#   getMbitCells hier1/hier2/my_flop_name
#   could match and return any (or all) of these
#     hier1/hier2/my_flop_name
#     hier1/hier2/CDN_MBIT_my_flop_name_MB_second_flop_name_MB_third_flop_name_MB_fourth_flop_name
#     hier1/hier2/CDN_MBIT_first_flop_name_MB_my_flop_name_MB_third_flop_name_MB_fourth_flop_name
#     hier1/hier2/CDN_MBIT_first_flop_name_MB_second_flop_name_MB_my_flop_name_MB_fourth_flop_name
#     hier1/hier2/CDN_MBIT_first_flop_name_MB_second_flop_name_MB_third_flop_name_MB_my_flop_name
#
#   getMbitCells hier1/hier2/my_flop_name
#   could match either
#     hier1/hier2/my_flop_name
#     hier1/hier2/CDN_MBIT_first_flop_name_MB_second_flop_name_MB_third_flop_name_MB_my_flop_name
proc getMbitCells {cellName} {
  set mbitCellName [file tail $cellName]
  set hierName [file dirname $cellName]
  if {$hierName eq "."} {
    set hierName {}
  } else {
    set hierName "$hierName/"
  }
  set results [get_cells -quiet $cellName]
  if {[sizeof_collection $results] == 0} {
    set results [get_cells -quiet [string map {* /} $cellName]]
  }
  if {[sizeof_collection $results] == 0} {
    append_to_collection -unique results [filter_collection [get_cells -quiet -hier {*_MB_*}] "full_name=~${hierName}*${mbitCellName}*"]
  }
  return $results
}


#------------------------------------------------------------------------------
#  create base pathgroups
#     reg2reg, reg2mem,  mem2reg, in2reg, reg2out, in2out, reg2clkgate, in2clkgate
#  if $per_mem is true
#     mem2reg and reg2meg groups are created for each type of memory
#  if $per_clock is true
#     each of the above (except in2out) is created for each physical clock
proc user_create_base_pathgroups { {per_mem false} {per_clock false} } {
    set top_from_reg [all_registers -clock_pins]
    set top_to_reg [all_registers -data_pins]
    set top_mem [filter_collection [get_cells -hierarchical ]  "is_memory_cell==true" ]
    if {[sizeof_collection $top_mem] > 0} {
      set top_to_reg [remove_from_collection $top_to_reg [get_pins -of $top_mem]]
      set top_from_reg [remove_from_collection $top_from_reg [get_pins -of $top_mem]]
    }
    if {[info commands all_clock_gates] ne {}} {
      set clkgates [all_clock_gates]
    } else {
      if {[isDC]} {
        set clkgates [filter_collection [all_registers] "is_clock_gating_check==true"]
      } else {
        # this is faster than looking for is_clock_gating_check, but only finds ICGs not inferred gaters
        set clkgates [filter_collection [all_registers] "is_integrated_clock_gating_cell==true"]
      }
    }
    set non_clkgates [remove_from_collection [all_registers] $clkgates]
    set real_clocks [lsort -unique [get_object_name [get_clocks -filter defined(sources)]]]
    if {$per_clock} {
      foreach clk $real_clocks {
        puts "-INFO- creating group reg2reg..${clk}" 
        group_path -name reg2reg..${clk} -from $top_from_reg -through $top_to_reg -to [get_clocks $clk]
      }
    } else {
      puts "-INFO- creating group reg2reg" 
      group_path -name reg2reg -from $top_from_reg -through $top_to_reg
    }
    if {[sizeof_collection $top_mem] > 0} {
      user_create_memory_pathgroups $per_mem $per_clock
    }
    if {$per_clock} {
      foreach clk $real_clocks {
        puts "-INFO- creating group reg2out..${clk}"
        group_path -name reg2out..${clk} -from [get_clocks $clk] -through [get_pins -of [all_registers] -filter "pin_direction=~out"] -to   [all_outputs] 
        puts "-INFO- creating group in2reg..${clk}"
        group_path -name in2reg..${clk} -from [remove_from_collection [all_inputs] [all_clocks]] -through [get_pins -of $non_clkgates -filter "pin_direction=~in"] -to [get_clocks $clk]
      }
    } else {
      puts "-INFO- creating group reg2out" 
      group_path -name reg2out -from  [all_registers] -to [all_outputs] 
      puts "-INFO- creating group in2reg" 
      group_path -name in2reg -from [remove_from_collection [all_inputs] [all_clocks]] -to $non_clkgates
    }
    puts "-INFO- creating group in2out" 
    group_path -name in2out   -from [remove_from_collection [all_inputs] [all_clocks]] -to [all_outputs]
    user_create_clkgate_pathgroups $per_clock
  }


#------------------------------------------------------------------------------
#  create separate memory pathgroups (reg2mem, mem2reg, mem2mem )
#
#  if $per_mem is true
#     each of the above is created for each memory size
#       i,e.
#          reg2mem_ln04lpp_s00_mc_rd2r_hsr_lvt_128x136m2b1c1
#          mem2reg_ln04lpp_s00_mc_rd2r_hsr_lvt_128x136m2b1c1
#          mem2mem_ln04lpp_s00_mc_rd2r_hsr_lvt_128x136m2b1c1
#
#  if $per_clock is true
#     each of the above is created for each physical clock
#       i,e.
#          reg2mem_ln04lpp_s00_mc_rd2r_hsr_lvt_128x136m2b1c1..NOCCLK
#          mem2reg_ln04lpp_s00_mc_rd2r_hsr_lvt_128x136m2b1c1..NOCCLK
#          mem2mem_ln04lpp_s00_mc_rd2r_hsr_lvt_128x136m2b1c1..NOCCLK
#
#  called from [user_create_base_pathgroups]
proc user_create_memory_pathgroups { {per_mem false} {per_clock false} } {
    if { [info commands get_property] ne {}
      && [info commands get_attribute] eq {}
      } {
      alias get_attribute get_property
    }
    set top_from_reg [all_registers -clock_pins]
    set top_to_reg [all_registers -data_pins]
    set top_mem [filter_collection [all_registers]  "is_memory_cell==true" ]
    set real_clocks [lsort -unique [get_object_name [get_clocks -filter defined(sources)]]]
    if {[sizeof_collection $top_mem] > 0} {
      set to_reg [remove_from_collection $top_to_reg [get_pins -of $top_mem]]
      set from_non_mem [remove_from_collection $top_from_reg [get_pins -of $top_mem]]
      if {$per_mem} {
        foreach mem [lsort -unique [get_attribute $top_mem ref_name]] {
          if {$per_clock} {
            set my_mem_pins [get_pins -of [filter_collection $top_mem ref_name=~$mem]]
            set my_clock_pins [remove_from_collection -intersect $top_from_reg $my_mem_pins]
            set my_clocks [lsort -unique [get_object_name [get_attribute -quiet $my_clock_pins clocks]]]
            foreach clk $my_clocks {
              puts "-INFO- creating group reg2mem_${mem}..${clk}"
              group_path -name reg2mem_${mem}..${clk} -from $from_non_mem -through  $my_mem_pins -to [get_clocks $clk]
              puts "-INFO- creating group mem2reg_${mem}..${clk}" 
              group_path -name mem2reg_${mem}..${clk} -from [get_clocks $clk] -through $my_mem_pins -to $to_reg
              puts "-INFO- creating group mem2mem_${mem}..${clk}" 
              group_path -name mem2mem_${mem}..${clk} -from [get_clocks $clk] -through $my_mem_pins -to [get_pins -of $top_mem]
            }
          } else {
            puts "-INFO- creating group reg2mem_${mem}"
            group_path -name reg2mem_${mem} -from $from_non_mem -to [filter_collection $top_mem ref_name=~$mem]
            puts "-INFO- creating group mem2reg_${mem}" 
            group_path -name mem2reg_${mem} -from [filter_collection $top_mem ref_name=~$mem] -to $to_reg
            puts "-INFO- creating group mem2mem_${mem}" 
            group_path -name mem2mem_${mem} -from [filter_collection $top_mem ref_name=~$mem] -to [get_pins -of $top_mem]
          }
        }
      } else {
        puts "-INFO- creating group reg2mem"
        group_path -name reg2mem -from $from_non_mem -to $top_mem
        puts "-INFO- creating group mem2reg" 
        group_path -name mem2reg -from $top_mem -to $to_reg
        puts "-INFO- creating group mem2mem" 
        group_path -name mem2mem -from $top_mem -to [get_pins -of $top_mem]
      }
    }
}


#------------------------------------------------------------------------------
# create in2clkgate, reg2clkgate, and mem2clkgate pathgroups
#
#  if $per_clock is true
#     each of the above is created for each physical clock
#       i.e.
#         in2clkgate..AICLK
#         reg2clkgate..AICLK
#         mem2clkgate..AICLK
#
#  called from [user_create_base_pathgroups]
proc user_create_clkgate_pathgroups { {per_clock false} } {
    set top_from_reg [all_registers -clock_pins]
    set top_to_reg [all_registers -data_pins]
    if {[info commands all_clock_gates] ne {}} {
      set clkgates [all_clock_gates]
    } else {
      if {[isDC]} {
        set clkgates [filter_collection [all_registers] "is_clock_gating_check==true"]
      } else {
        # this is faster than looking for is_clock_gating_check, but only finds ICGs not inferred gaters
        set clkgates [filter_collection [all_registers] "is_integrated_clock_gating_cell==true"]
      }
    }
    set non_clkgates [remove_from_collection [all_registers] $clkgates]
    set real_clocks [lsort -unique [get_object_name [get_clocks -filter defined(sources)]]]
    set top_mem [filter_collection [all_registers]  "is_memory_cell==true" ]
    if {[sizeof_collection $top_mem] > 0} {
      set from_mem [remove_from_collection -intersect $top_from_reg [get_pins -of $top_mem]]
    }
    if {$per_clock} {
      foreach clk $real_clocks {
        if {[sizeof_collection $clkgates] > 0} {
          puts "-INFO- creating group in2clkgate..${clk}"
          group_path -name in2clkgate..${clk} -from [remove_from_collection [all_inputs] [all_clocks]] -through [get_pins -of $clkgates -filter "pin_direction=~in"] -to [get_clocks $clk]
          puts "-INFO- creating group reg2clkgate..${clk}" 
          group_path -name reg2clkgate..${clk} -from $top_from_reg -through [get_pins -of $clkgates -filter "pin_direction=~in"] -to [get_clocks $clk]
          if {[sizeof_collection $top_mem] > 0} {
            puts "-INFO- creating group mem2clkgate..${clk}" 
            group_path -name mem2clkgate..${clk} -from $from_mem -through [get_pins -of $clkgates -filter "pin_direction=~in"] -to [get_clocks $clk]
          }
        }
      }
    } else {
      if {[sizeof_collection $clkgates] > 0} {
        puts "-INFO- creating group in2clkgate" 
        group_path -name in2clkgate -from [remove_from_collection [all_inputs] [all_clocks]] -to $clkgates
        puts "-INFO- creating group reg2clkgate" 
        group_path -name reg2clkgate -from $top_from_reg -to $clkgates
        if {[sizeof_collection $top_mem] > 0} {
          puts "-INFO- creating group mem2clkgate" 
          group_path -name mem2clkgate -from $from_mem -to $clkgates
        }
      }
    }
}


#------------------------------------------------------------------------------
# create a separate pathgoup for each hierachy at the give $depth if it contains
#   more than $min_flops registers
#     i.e.
#       apg_hier.hierarchy1
#       apg_hier.hierarchy2
#       ...
#
# if $per_clock is true
#     each of the above is created for each physical clock
#     i.e.
#       apg_hier.hierarchy1..AICLK
#       apg_hier.hierarchy1..NOCCLK
#       apg_hier.hierarchy2..AICLK
#       apg_hier.hierarchy2..NOCCLK
#       ...
#
# if $exclude_memories is false the pathgoroups will include paths to/from
#     memories in those hierarchies as well.
#
# if $exclude_clkgate is false the pathgroups will include paths to clkgates
#     in those hierarchies as well.
#
proc user_create_hier_depth_pathgroups { {depth 1} {min_flops 1000} {per_clock false} {exclude_memories true} {exclude_clkgates true} } {
    if {$depth < 1} {return}
    set top_mem [filter_collection [get_cells -hierarchical ]  "is_memory_cell==true" ]
    set top_from_reg [all_registers -clock_pins]
    set top_to_reg [all_registers -data_pins]
    set real_clocks [lsort -unique [get_object_name [get_clocks -filter defined(sources)]]]
    if {[info commands all_clock_gates] ne {}} {
      set clkgates [all_clock_gates]
    } else {
      if {[isDC]} {
        set clkgates [filter_collection [all_registers] "is_clock_gating_check==true"]
      } else {
        # this is faster than looking for is_clock_gating_check, but only finds ICGs not inferred gaters
        set clkgates [filter_collection [all_registers] "is_integrated_clock_gating_cell==true"]
      }
    }
    if {$exclude_memories && [sizeof_collection $top_mem] > 0} {
      set top_from_reg [remove_from_collection $top_from_reg [get_pins -of $top_mem]]
      set top_to_reg [remove_from_collection $top_to_reg [get_pins -of $top_mem]]
    }
    if {$exclude_clkgates && [sizeof_collection $clkgates] > 0} {
      set top_to_reg [remove_from_collection $top_to_reg [get_pins -of $clkgates]]
    }
    set hier "*"
    set my_depth $depth
    while {$my_depth > 1} {
      append hier "/*"
      incr my_depth -1
    }
    foreach_in_collection cell [get_cells ${hier} -filter "is_hierarchical"] {
      set cname [get_object_name $cell]
      if {[sizeof_collection [filter_collection $top_from_reg "full_name=~$cname/*"]] > $min_flops} {
        set to_reg [filter_collection $top_to_reg "full_name=~$cname/*"]
        set grp_name [regsub -all {/} $cname {.}]
        if {$per_clock} {
          foreach clk $real_clocks {
            puts "-INFO- creating group apg_hier.${grp_name}..${clk}"
            group_path -name apg_hier.${grp_name}..${clk} -from $top_from_reg -through $to_reg -to $clk
          }
        } else {
          puts "-INFO- creating group apg_hier.$grp_name"
          group_path -name apg_hier.$grp_name -from $top_from_reg -to $to_reg
        }
      }
    }
}


#------------------------------------------------------------------------------
#  tool agnostic way to remove all existing pathgroups
proc user_remove_pathgroups { {pg *} } {
  if {$pg eq "-all"} {
    set pg "*"
  }
  if { [isSynopsys] } {
    remove_path_group [get_object_name [get_path_groups $pg]]
  } else {
    foreach g [get_object_name [get_path_groups -include_internal_groups $pg]] {
      reset_path_group -name $g
    }
  }
}

# procs for getting pins, nets and cells in a renaming / hierarchy smashing agnostic way

#------------------------------------------------------------------------------
proc pinGlob {name} {
  if {[llength [file split $name]] < 2} {
    return [cellGlob $name]
  }
  set newname $name
  regsub -all {[\[\]\._/]} [file dirname $name] {?} newname
  append newname / [file tail $name]
  return $newname
}

#------------------------------------------------------------------------------
proc cellGlob {name} {
  set newname $name
  regsub -all {[\[\]\._/]} $name {?} newname
  return $newname
}

#------------------------------------------------------------------------------
proc getPins {name args} {
  set use_hier false
  if {[llength [file split $name]] > 2} {
    set use_hier true
  }
  set pinName [file tail $name]
  set name [pinGlob $name]
  set hierIndex [lsearch -glob $args -hi*]
  if {$hierIndex >= 0} {
    set args [lreplace $args $hierIndex $hierIndex]
    set use_hier true
  }
  set filterIndex [lsearch -glob $args -f*]
  if { $filterIndex >= 0  } {
    incr filterIndex
    lset args $filterIndex "full_name=~$name && ( [lindex $args $filterIndex] )"
  } else {
    lappend args -filter full_name=~$name
  }
  if {$use_hier} {
    return [get_pins -hier */$pinName {*}$args]
  } else {
    return [get_pins */$pinName {*}$args]
  }
}


#------------------------------------------------------------------------------
proc getX {type name args} {
  set use_hier false
  if {[llength [file split $name]] > 1} {
    set use_hier true
  }
  set pinName [file tail $name]
  set name [cellGlob $name]
  set hierIndex [lsearch -glob $args -hi*]
  if {$hierIndex >= 0} {
    set args [lreplace $args $hierIndex $hierIndex]
    set use_hier true
  }
  set filterIndex [lsearch -glob $args -f*]
  if { $filterIndex >= 0  } {
    incr filterIndex
    lset args $filterIndex "full_name=~$name && ( [lindex $args $filterIndex] )"
  } else {
    lappend args -filter full_name=~$name
  }
  if {$use_hier} {
    return [get_$type -hier * {*}$args]
  } else {
    return [get_$type * {*}$args]
  }
}


#------------------------------------------------------------------------------
proc getCells {name args} {return [getX cells $name {*}$args]}


#------------------------------------------------------------------------------
proc getNets  {name args} {return [getX nets  $name {*}$args]}


#--------------------------------------------------------------------------------
# a wrapper around get_object name that does not create warning messages if given
#  an empty collection
proc nameOf {obj} {
  if {$obj eq {}} {
    return {}
  } else {
    return [get_object_name $obj]
  }
}

#--------------------------------------------------------------------------------
# for the given ref_name glob pattern, return a collection that contains all
#   instances whose ref_name matches the given pattern, and their parent and
#   child (non-leaf) instance hierarchies. 
#     i.e parents, grandparents, children grandchildren, etc.
#   if include_children is false child hierarchies are not included
#   if include_parents is false parent hierarchies are not included
proc get_full_family_tree {ref_name_pattern {include_children true} {include_parents true}} {
  set cells [get_cells -quiet -filter ref_name=~$ref_name_pattern]
  set ancestry {}
  set prodginy {}

  foreach c [nameOf $cells] {
    set ancesters [file split $c]

    while { [llength ancesters] > 1} {
      set ancesters [lrange $ancesters 0 end-1]
      append_to_collection ancestry [get_cells [file join {*}$ancesters]]
    }

    if {$include_children} {
      set children [get_cells -quiet -hier -filter "is_hierarchical && full_name=~$c/*"]
      append_to_collection prodginy $children
    }
  }
 
  append_to_collection cells $ancestry
  append_to_collection cells $prodginy
  return $cells
}

#--------------------------------------------------------------------------------
# get synopsys or cadence attributes using synopsys names
proc getAttribute { obj arg args} {
  if { [isSynopsys] } {
    set type [get_attribute -quiet $obj object_type]
  } else {
    set type [get_property -quiet $obj object_class]
  }
  switch -exact -- $type {
    timing_path {
        set cmd_opt_map {
          "startpoint_clock_is_inverted"     "launching_clock_is_inverted"
          "endpoint_clock_is_inverted"       "capturing_clock_is_inverted"
          "common_path_pessimism"            "cppr_adjustment"
        }
        #  "object_class"                    "object_type"
        #  "startpoint"                      "launching_point"
        #  "endpoint"                        "capturing_point"
        #  "startpoint_clock"                "launching_clock"
        #  "endpoint_clock"                  "capturing_clock"
        #  "startpoint_clock_open_edge_type" "launching_clock_open_edge_type"
        #  "endpoint_clock_open_edge_type"   "capturing_clock_open_edge_type"
        #  "endpoint_clock_latency"          "capturing_clock_latency"
        #  "startpoint_clock_latency"        "launching_clock_latency"
        #  "endpoint_setup_time_value"       "setup"
        #  "endpoint_hold_time_value"        "hold"
        #  "crpr_common_point"               "cppr_branch_point"
        #  "common_path_pessimism"           "cppr_adjustment"
        #  "points"                          "timing_points"
    }
    pin         {
        set cmd_opt_map {
           "max_slack"    "slack_max"
           "min_slack"    "slack_min"
           "actual_transition_max" "max_transition"
        }
        #   "object_class" "object_type"
    }
    cell         {
        set cmd_opt_map {
        }
        #   "ref_name"     "ref_lib_cell_name"
        #   "object_class" "object_type"
    }
    default {
        set cmd_opt_map {
           "max_slack"    "slack_max" 
           "min_slack"    "slack_min"
        }
        #   "object_class" "object_type"
    }
  }
  if { [isSynopsys] } { 
      return [get_attribute -quiet $obj $arg ]  
  } else {
      if { [dict exists $cmd_opt_map $arg] } {
        set arg [dict get $cmd_opt_map $arg]
      }
      return [get_property -quiet $obj $arg {*}$args]
  }
}

#--------------------------------------------------------------------------------
proc isObj {thing} {
  if {[isSynopsys]} {
    return [regexp {^_sel\d+$} "$thing"]
  } else {
    if {[is_collection_object $thing]} {
     return 1
    } elseif { ![string match {*:*} $thing] } {
     return 0
    } elseif { ![catch {get_db $thing .obj_type}] } {
     return 1
    } else {
     return 0
    }
  }
}

#--------------------------------------------------------------------------------
proc is_collection_object {thing} {
  if {[isSynopsys]} {
   return [regexp {^_sel\d+$} "$thing"]
  } else {
    if {![string match *:* $thing] && [string match {0x*} $thing]} {
      return true
    }
    return false
  }
}

#--------------------------------------------------------------------------------
# only to be used in cadence
#  convert db objects to collection objects
proc dbToCollection {thing} {
  set result {}
  if {[isObj $thing]} {
    if {[is_collection_object $thing]} {
      set result $thing
    } else {
      regsub {:.*} $thing {} type
      get_db $thing -foreach {
        if {[info exists obj(.obj_type)]} { set type $obj(.obj_type) }
        if {$type eq "inst"} { set type "cell" }
        if {[info commands get_$type] ne {} && [info exists obj(.name)]} {
          set name $obj(.name)
          append_to_collection result [get_$type $name]
        }
      }
    }
  }
  return $result
}

#--------------------------------------------------------------------------------
# return the thing that drives this thing (the source of the clock if thing is a clock)
proc driverOf {thing} {
  set net {}
  if {[isObj $thing]} {
    if {![isSynopsys] && [isObj $thing]} {
      set thing [dbToCollection $thing]
    }
    foreach_in_collection p $thing {
      switch -exact -- [getAttribute $p object_class] {
        net     {append_to_collection net $p}
        pin     -
        port    {append_to_collection net [get_nets -quiet -seg -top -of $p]}
        cell    {append_to_collection net [get_nets -quiet -seg -top -of [get_pins -quiet -of $p -filter pin_direction=~in]]}
        clock   {append_to_collection net [get_nets -quiet -seg -top -of [getAttribute $p sources]]}
        default { puts "Unsupported type: '$type'"; return "" }
      }
    }
  } else {
    set p [getPinOrPort $thing]
    if {[sizeof $p] > 0} {
      set net [get_nets -quiet -seg -top -of $p] 
    } else {
      set net [get_nets -quiet -seg -top $thing]
    }
    if {[sizeof $net] == 0} {
      set p [get_cells -quiet $thing]
      if { [sizeof $p] == 0} {
        set p [get_clocks -quiet $thing]
        if {[sizeof $p] > 0} {
          set net [get_nets -quiet -seg -top -of [getAttribute $p sources]]
        }
      } else {
        set net [get_nets -quiet -seg -top -of [get_pins -quiet -of $p -filter pin_direction=~in]]
      }
    }
  }
  set pins [get_pins -quiet -leaf -of $net -filter pin_direction=~out]
  append_to_collection pins [get_ports -quiet -of $net -filter direction=~in]
  return $pins
}


#--------------------------------------------------------------------------------
# return the leaf pins if the given thing
#  returns:
#    if thing is a hierarchical output pin: its driver(s)
#    if thing is a hierarchical input pin: its fanout leaf pins
#    if thing is a leaf pin: its self
#    if thing is a port: its self
#    if thing is a clock:  the clock endpoints of the clock
#    if thing is a net:  all the leaf pins of the net
#    if thing is a leaf cell:  all of its pins
#    if thing is a hierarcchical cell:  [leafPinOf <all of its pins>]
proc leafPinOf {thing} {
  set nets {}
  set clocks {}
  set ports {}
  set inPins {}
  set outPins {}
  if {[isObj $thing]} {
    if {![isSynopsys] && [isObj $thing]} {
      set thing [dbToCollection $thing]
    }
    foreach_in_collection p $thing {
      switch -exact -- [getAttribute $p object_class] {
        net     { append_to_collection nets   $p }
        port    { append_to_collection ports  $p }
        clock   { append_to_collection clocks $p }
        pin     { 
                  if {[string match in*  [getAttribute $p pin_direction]] } { append_to_collection inPins  $p }
                  if {[string match *out [getAttribute $p pin_direction]] } { append_to_collection outPins $p }
                }
        cell    {
                  append_to_collection inPins  [get_pins -quiet -of $p -filter "pin_direction=~in*"]
                  append_to_collection outPins [get_pins -quiet -of $p -filter "pin_direction=~*out"]
                }
        default { puts "Unsupported type: '$type'"; return "" }
      }
    }
  } else {
    set p [getPinOrPort $thing]
    if {[sizeof $p] > 0} {
      append_to_collection ports  [filter_collection $p "object_class==port"] 
      append_to_collection inPins   [filter_collection $p "object_class==pin && pin_direction=~in*"] 
      append_to_collection outPins  [filter_collection $p "object_class==pin && pin_direction=~*out"] 
    } else {
      set p [get_nets -quiet -seg -top $thing]
      if {[sizeof $p] > 0} {
        append_to_collection nets $p
      } else {
        set p [get_cells -quiet $thing]
        if { [sizeof $p] > 0} {
          append_to_collection inPins  [get_pins -quiet -of $p -filter "pin_direction=~in*"]
          append_to_collection outPins [get_pins -quiet -of $p -filter "pin_direction=~*out"]
        } else {
          set p [get_clocks -quiet $thing]
          if {[sizeof $p] > 0} {
            append_to_collection clocks $p
          }
        }
      }
    }
  }
  set pins {}
  append_to_collection pins -unique $ports
  foreach_in_collection p $nets     {
    append_to_collection -unique pins [get_pins  -quiet -leaf -of [get_nets -quiet -seg $p]]
    append_to_collection -unique pins [get_ports -quiet       -of [get_nets -quiet -seg $p]]
  }
  foreach_in_collection p $outPins  {
    append_to_collection -unique  pins [driverOf $p]
  }
  foreach_in_collection p $inPins   { 
    if {[getAttribute [get_cells -quiet -of $p] is_hierarchical]} {
      set name [file dirname [get_object_name $p]]
      append_to_collection  -unique pins [get_pins -leaf -of [get_nets -seg -of $p] -filter "pin_direction=~in && full_name=~$name/*"]
    } else {
      append_to_collection  -unique pins $p
    }
  }
  if {[sizeof_collection $clocks] > 0} {
    foreach_in_collection p [filter_collection [all_registers -clock_pins] defined(clocks)] {
      foreach_in_collection c $clocks   {
        set name [get_object_name $c]
        if { [lsearch -exact [get_object_name [getAttribute $p clocks]]] >= 0 } {
          append_to_collection  -unique pins $p
        }
      }
    }
  }
  return $pins
}


#--------------------------------------------------------------------------------
proc getPinOrPort {thing} {
  set pins [get_pins -quiet $thing]
  append_to_collection pins [get_ports -quiet $thing]
  return $pins
}

proc cat_file {args} {return}
if {[info commands get_flow_config] eq {}} {
  proc get_flow_config {args} {return {}}
}


### Start - Jungyu Im 20250806
global TIME_SCALE_FROM_PS
set TIME_SCALE_FROM_PS 0.001
set ::LATENCY_MULT 0.001
if {![info exists PRE_SYN]} {
    set PRE_SYN false
}
if {$PRE_SYN} {
    set CLK_MARGIN 0.4
} else {
    set CLK_MARGIN 0
}
# clock periods
if {![info exists USE_ND]} {
    set USE_ND 1
}
if {$USE_ND} {
    set FREQ_AI   1.08
    set FREQ_NOC  0.95
    set FREQ_OVL  1.20
    set FREQ_AXI  1
} else {
    set FREQ_AI   1.212
    set FREQ_NOC  1.066
    set FREQ_OVL  1.347
    set FREQ_AXI  1
}
set ::AICLK_PERIOD          [expr {((1000 / $FREQ_AI  ) * (1 - $CLK_MARGIN)) * $::TIME_SCALE_FROM_PS}]
set ::NOCCLK_PERIOD         [expr {((1000 / $FREQ_NOC ) * (1 - $CLK_MARGIN)) * $::TIME_SCALE_FROM_PS}]
set ::OVLCLK_PERIOD         [expr {((1000 / $FREQ_OVL ) * (1 - $CLK_MARGIN)) * $::TIME_SCALE_FROM_PS}]
set ::ck_feedthru_PERIOD    [expr {((1000             ) * (1 - $CLK_MARGIN)) * $::TIME_SCALE_FROM_PS}]
set ::vir_AICLK_PERIOD      [expr {((1000 / $FREQ_AI  ) * (1 - $CLK_MARGIN)) * $::TIME_SCALE_FROM_PS}]
set ::vir_OVLCLK_PERIOD     [expr {((1000 / $FREQ_OVL ) * (1 - $CLK_MARGIN)) * $::TIME_SCALE_FROM_PS}]
set ::vir_NOCCLK_PERIOD     [expr {((1000 / $FREQ_NOC ) * (1 - $CLK_MARGIN)) * $::TIME_SCALE_FROM_PS}]
    ###set ::NOCCLK_PERIOD [expr {714.0 * $::TIME_SCALE_FROM_PS}]
    ###set ::OVLCLK_PERIOD [expr {500.0 * $::TIME_SCALE_FROM_PS}]
    ###set ::OVL_UNCORE_CLK_PERIOD [expr {1000.0 * $::TIME_SCALE_FROM_PS}]
    ###set ::ck_feedthru_PERIOD [expr {1000.0 * $::TIME_SCALE_FROM_PS}]
    ###set ::vir_NOCCLK_PERIOD [expr {714.0 * $::TIME_SCALE_FROM_PS}]
    ###set ::vir_OVLCLK_PERIOD [expr {500.0 * $::TIME_SCALE_FROM_PS}]

# create_clocks
create_clock -add -name AICLK  -period $::AICLK_PERIOD  [get_ports {i_ai_clk}]
create_clock -add -name NOCCLK -period $::NOCCLK_PERIOD [get_ports {i_nocclk}]
create_clock -add -name OVLCLK -period $::OVLCLK_PERIOD [get_ports {i_dm_clk}]
create_clock -add -name ck_feedthru -period $::ck_feedthru_PERIOD
#create_generated_clock -add -name OVL_UNCORE_CLK -master_clock OVLCLK -divide_by  2 -source {i_dm_clk} [get_pins {tt_dispatch_engine/disp_eng_overlay_noc_wrap/disp_eng_overlay_noc_niu_router/disp_eng_overlay_wrapper/overlay_wrapper/clock_reset_ctrl/d0nt_clk_core_clk_div2/div_reg_reg/q_d_reg/Q}]
create_generated_clock -add -name OVL_UNCORE_CLK -master_clock OVLCLK -divide_by  2 -source {i_dm_clk} [get_pins {tt_dispatch_engine/disp_eng_overlay_noc_wrap/disp_eng_overlay_noc_niu_router/disp_eng_overlay_wrapper/overlay_wrapper/clock_reset_ctrl/d0nt_clk_core_clk_div2/div_reg_reg/u_bos_soc_dffr_lvt/dffr_inst*0*u_dont_touch_dffr/Q}]
create_clock -add -name vir_AICLK -period $::vir_AICLK_PERIOD
create_clock -add -name vir_NOCCLK -period $::vir_NOCCLK_PERIOD
create_clock -add -name vir_OVLCLK -period $::vir_OVLCLK_PERIOD
    #create_clock -add -name OVLCLK -period $::OVLCLK_PERIOD [get_ports {i_dm_clk}]
    #create_clock -add -name ck_feedthru -period $::ck_feedthru_PERIOD
    #create_generated_clock -add -name OVL_UNCORE_CLK -master_clock OVLCLK -divide_by  2 -source {i_dm_clk} [get_pins {disp_eng_overlay_noc_wrap/disp_eng_overlay_noc_niu_router/disp_eng_overlay_wrapper/overlay_wrapper/clock_reset_ctrl/d0nt_clk_core_clk_div2/div_reg_reg/q_d_reg/Q}]
    #create_clock -add -name NOCCLK -period $::NOCCLK_PERIOD [get_ports {i_nocclk}]
    #create_clock -add -name vir_OVLCLK -period $::vir_OVLCLK_PERIOD
    #create_clock -add -name vir_NOCCLK -period $::vir_NOCCLK_PERIOD
#DONE

set_ideal_network -no_propagate [get_port {i_ai_clk}]
set_ideal_network -no_propagate [get_port {i_dm_clk}]
set_ideal_network -no_propagate [get_port {i_nocclk}]
set_ideal_network -no_propagate [get_pins -hierarchical */ECK]
### End - Jungyu Im



set ::my_in_clock_ports  [get_ports -quiet {*} -filter "direction=~in* && defined(clocks)"]
set ::my_out_clock_ports [get_ports -quiet {*} -filter "direction=~*out && defined(clocks)"]

### Start - Jungyu Im 20250925 : modify SDC constraint (set_in/output_delay for DFT ports)
source -e -v $NPU_HOME/HPDF/port.tcl > ./logs/port_test.log

set my_ports [get_ports $filtered_in_ports]
#set my_ports [remove_from_collection [get_ports -quiet { * } -filter "direction=~in*"] $::my_in_clock_ports]
set my_clock [get_clocks -quiet { ck_feedthru }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } {
  puts {-I- setting input delay of 0% of ck_feedthru on *}
  set_input_delay -max -clock $my_clock  [expr { 0 * $::ck_feedthru_PERIOD / 100.0 }] $my_ports
} else {
  puts {-W- skipping input delay 0% of ck_feedthru on *}
}

set my_ports [get_ports $filtered_out_ports]
#set my_ports [remove_from_collection [get_ports -quiet { * } -filter "direction=~*out"] $::my_out_clock_ports]
set my_clock [get_clocks -quiet { ck_feedthru }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } {
  puts {-I- setting output delay of 70% of ck_feedthru on *}
  set_output_delay -max -clock $my_clock  [expr { 70 * $::ck_feedthru_PERIOD / 100.0 }] $my_ports
} else {
  puts {-W- skipping output delay 70% of ck_feedthru on *}
}

set my_ports [get_ports $filtered_in_ports]
#set my_ports [remove_from_collection [get_ports -quiet { * } -filter "direction=~in*"] $::my_in_clock_ports]
set my_clock [get_clocks -quiet { vir_NOCCLK }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } {
  puts {-I- adding additional input delay of 60% of vir_NOCCLK on *}
  set_input_delay -add_delay -max -clock $my_clock  [expr { 60 * $::vir_NOCCLK_PERIOD / 100.0 }] $my_ports 
} else {
  puts {-W- skipping input delay 60% of vir_NOCCLK on *}
}

set my_ports [get_ports $filtered_out_ports]
#set my_ports [remove_from_collection [get_ports -quiet { * } -filter "direction=~*out"] $::my_out_clock_ports]
set my_clock [get_clocks -quiet { vir_NOCCLK }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } {
  puts {-I- adding additional output delay of 60% of vir_NOCCLK on *}
  set_output_delay -add_delay -max -clock $my_clock  [expr { 60 * $::vir_NOCCLK_PERIOD / 100.0 }] $my_ports
} else {
  puts {-W- skipping output delay 60% of vir_NOCCLK on *}
}
### End - Jungyu Im



set my_out_ports [get_ports -quiet { * } -filter "direction=~*out"]
if {  [sizeof_collection $my_out_ports]>0 } { set_load 0.04 $my_out_ports }

set my_in_ports [get_ports -quiet { * } -filter "direction=~in*"]

set my_in_ports [remove_from_collection -intersect [get_ports -quiet { * } -filter "direction=~in*"] $::my_in_clock_ports]

set my_in_ports [get_ports -quiet { * } -filter "direction=~in*"]
set my_out_ports [get_ports -quiet { * } -filter "direction=~*out"]
set my_from_clock [get_clocks -quiet { vir_NOCCLK }]
set my_to_clock [get_clocks -quiet { vir_NOCCLK }]
if { [sizeof_collection $my_from_clock]>0 && [sizeof_collection $my_to_clock]>0 && [sizeof_collection $my_in_ports]>0 && [sizeof_collection $my_out_ports]>0 } { set_false_path -setup -from $my_from_clock -through $my_in_ports -through $my_out_ports -to $my_to_clock }

set my_ports [remove_from_collection [get_ports -quiet { test_si* } -filter "direction=~in*"] $::my_in_clock_ports]
set my_clock [get_clocks -quiet { vir_tessent_ssn_bus_clock_network }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } {
  puts {-I- setting input delay of 50% of vir_tessent_ssn_bus_clock_network on test_si*}
  set_input_delay -max -clock $my_clock  [expr { 50 * $::vir_tessent_ssn_bus_clock_network_PERIOD / 100.0 }] $my_ports
} else {
  puts {-W- skipping input delay 50% of vir_tessent_ssn_bus_clock_network on test_si*}
}

set my_ports [remove_from_collection [get_ports -quiet { test_so* } -filter "direction=~*out"] $::my_out_clock_ports]
set my_clock [get_clocks -quiet { vir_tessent_ssn_bus_clock_network }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } {
  puts {-I- setting output delay of 50% of vir_tessent_ssn_bus_clock_network on test_so*}
  set_output_delay -max -clock $my_clock  [expr { 50 * $::vir_tessent_ssn_bus_clock_network_PERIOD / 100.0 }] $my_ports
} else {
  puts {-W- skipping output delay 50% of vir_tessent_ssn_bus_clock_network on test_so*}
}

set my_ports [get_ports -quiet { i_core_reset_n } -filter "direction=~in*"]
set my_clock [get_clocks -quiet { vir_OVLCLK }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_multicycle_path -setup 3 -from $my_ports -to $my_clock }

set my_ports [get_ports -quiet { i_nocclk_reset_n } -filter "direction=~in*"]
set my_clock [get_clocks -quiet { vir_NOCCLK }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_multicycle_path -setup 4 -from $my_ports -to $my_clock }

set my_ports [remove_from_collection [get_ports -quiet { i_core_reset_n } -filter "direction=~in*"] $::my_in_clock_ports]
set my_clock [get_clocks -quiet { vir_OVLCLK }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } {
  puts {-I- setting input delay of 90% of vir_OVLCLK on i_core_reset_n}
  set_input_delay -max -clock $my_clock  [expr { 90 * $::vir_OVLCLK_PERIOD / 100.0 }] $my_ports
} else {
  puts {-W- skipping input delay 90% of vir_OVLCLK on i_core_reset_n}
}

set my_ports [get_ports -quiet { i_noc_*_size* }]
set my_from_clock [get_clocks -quiet { * }]
set my_to_clock [get_clocks -quiet { * }]
if { [sizeof_collection $my_from_clock]>0 && [sizeof_collection $my_to_clock]>0 && [sizeof_collection $my_ports]>0 } { set_false_path -setup -from $my_from_clock -through $my_ports -to $my_to_clock }

set my_ports [get_ports -quiet { i_local_* }]
set my_from_clock [get_clocks -quiet { * }]
set my_to_clock [get_clocks -quiet { * }]
if { [sizeof_collection $my_from_clock]>0 && [sizeof_collection $my_to_clock]>0 && [sizeof_collection $my_ports]>0 } { set_false_path -setup -from $my_from_clock -through $my_ports -to $my_to_clock }

set my_ports [get_ports -quiet { i_noc_endpoint_* }]
set my_from_clock [get_clocks -quiet { * }]
set my_to_clock [get_clocks -quiet { * }]
if { [sizeof_collection $my_from_clock]>0 && [sizeof_collection $my_to_clock]>0 && [sizeof_collection $my_ports]>0 } { set_false_path -setup -from $my_from_clock -through $my_ports -to $my_to_clock }





set bbox_scan_clocks [get_clocks -quiet {*/*shift_clock* */*scan_* */*tessent*}]
set shift_clocks [get_clocks -quiet {*shift_clock*}]
set shift_clocks [remove_from_collection $shift_clocks $bbox_scan_clocks]
set scan_clocks [get_clocks [lsort -unique [get_object_name [get_clocks -quiet {*shift_clock_* *scan_* *tessent*}]]]]
set scan_clocks [remove_from_collection $scan_clocks [get_clocks -quiet  {*tessent*_tck* *bisr*}]]
set scan_clocks [remove_from_collection $scan_clocks $bbox_scan_clocks]
set scan_pat [lsort -unique [get_object_name $scan_clocks]]
set singlechain_clocks [get_clocks -quiet *singlechain*]

if {[isCadence] && [info commands set_interactive_constraint_modes] ne {}} {
  set_interactive_constraint_modes ${::CONSTRAINT_MODE}
}

set cmd "set_clock_groups -asynchronous"
foreach pat [list \
  {TCK                      vir_TCK                    *_tck*      tck_singlechain*}\
  {*bisr*                                                    }\
  {AICLK*                   vir_AICLK*                       }\
  {AXICLK*                  vir_AXICLK*                      }\
  {NOCCLK*                  vir_NOCCLK*                SMNCLK*      vir_SMNCLK*}\
  {*ck_async*                                                }\
  {SOCCLK*                  vir_SOCCLK*                      }\
  {OVL*CLK*                 vir_OVL*CLK*                     }\
  {SYSCLK*                  vir_SYSCLK*             *CLK_WR0*}\
  {PERIPHCLK*               vir_PERIPHCLK*                   }\
  {SPI_*                    vir_SPI_*                   *DQS*}\
  {I3C*CLK_0                vir_I3C*CLK_0                    }\
  {I3C*CLK_1                vir_I3C*CLK_1                    }\
  {I3C*CLK_2                vir_I3C*CLK_2                    }\
  {I3C*CLK_3                vir_I3C*CLK_3                    }\
  {I3C*CLK_4                vir_I3C*CLK_4                    }\
  {I3C*CLK_5                vir_I3C*CLK_5                    }\
  {I3C*CLK                  vir_I3C*CLK                      }\
  {REFCLK*                  vir_REFCLK*         *DROOPAPBCLK*}\
  {RFCLK*                   vir_RFCLK*                       }\
  {ck_feedthru              vir_ck_feedthru                  }\
  {ck_dummy                 vir_ck_dummy                     }\
  {ck_untimed               vir_ck_untimed                   }\
  {DROOPCLK                 vir_DROOPCLK                     }\
  {OBSCLK*                  vir_OBSCLK*                      }\
  {TELEMETRYCLK             vir_TELEMETRYCLK                 }\
  $scan_pat \
] {
  set clks [get_clocks -quiet $pat]
  if {[sizeof_collection $clks] > 0} {
    lappend cmd -group $clks
  }
}
eval $cmd

if {[sizeof_collection $bbox_scan_clocks] > 0 } {
  set_clock_groups -asynchronous -group $bbox_scan_clocks
}

if {[sizeof_collection $scan_clocks] > 0} {
  foreach pat {
    {TCK           vir_TCK               *_tck*     tck_singlechain*}
    {*bisr*                                    }
    {AICLK*        vir_AICLK*                  }
    {AXICLK*       vir_AXICLK*                 }
    {NOCCLK*       vir_NOCCLK*          SMNCLK*      vir_SMNCLK*}
    {*ck_async*                                }
    {SOCCLK*       vir_SOCCLK*                 }
    {OVL*CLK*      vir_OVL*CLK*                }
    {SYSCLK*       vir_SYSCLK*        *CLK_WR0*}
    {PERIPHCLK*    vir_PERIPHCLK*              }
    {SPI_*         vir_SPI_*              *DQS*}
    {I3C*CLK_0     vir_I3C*CLK_0               }
    {I3C*CLK_1     vir_I3C*CLK_1               }
    {I3C*CLK_2     vir_I3C*CLK_2               }
    {I3C*CLK_3     vir_I3C*CLK_3               }
    {I3C*CLK_4     vir_I3C*CLK_4               }
    {I3C*CLK_5     vir_I3C*CLK_5               }
    {I3C*CLK       vir_I3C*CLK                 }
    {DROOPCLK      vir_DROOPCLK                }
    {REFCLK*       vir_REFCLK*    *DROOPAPBCLK*}
    {RFCLK*        vir_RFCLK*                  }
    {OBSCLK        vir_OBSCLK                  }
    {TELEMETRYCLK  vir_TELEMETRYCLK            }
  } {
    set func_clks [get_clocks -quiet $pat]
    if {[sizeof_collection $func_clks] > 0} {
      set_clock_groups -physically_exclusive -group $func_clks -group $scan_clocks
    }
  }
}

if {[sizeof_collection $singlechain_clocks] > 0} {
  foreach pat {
    {*bisr*                                    }
    {AICLK*        vir_AICLK*                  }
    {AXICLK*       vir_AXICLK*                 }
    {NOCCLK*       vir_NOCCLK*          SMNCLK*      vir_SMNCLK*}
    {*ck_async*                                }
    {SOCCLK*       vir_SOCCLK*                 }
    {OVL*CLK*      vir_OVL*CLK*                }
    {SYSCLK*       vir_SYSCLK*        *CLK_WR0*}
    {PERIPHCLK*    vir_PERIPHCLK*              }
    {SPI_*         vir_SPI_*              *DQS*}
    {I3C_CLK_0       vir_I3C_CLK_0             }
    {I3C_CLK_1       vir_I3C_CLK_1             }
    {I3C_CLK_2       vir_I3C_CLK_2             }
    {I3C_CLK_3       vir_I3C_CLK_3             }
    {I3C_CLK_4       vir_I3C_CLK_4             }
    {I3C_CLK_5       vir_I3C_CLK_5             }
    {I3C_SCAN_CLK_0  vir_I3C_SCAN_CLK_0        }
    {I3C_SCAN_CLK_1  vir_I3C_SCAN_CLK_1        }
    {I3C_SCAN_CLK_2  vir_I3C_SCAN_CLK_2        }
    {I3C_SCAN_CLK_3  vir_I3C_SCAN_CLK_3        }
    {I3C_SCAN_CLK_4  vir_I3C_SCAN_CLK_4        }
    {I3C_SCAN_CLK_5  vir_I3C_SCAN_CLK_5        }
    {DROOPCLK      vir_DROOPCLK                }
    {REFCLK*       vir_REFCLK*    *DROOPAPBCLK*}
    {RFCLK*        vir_RFCLK*                  }
    {OBSCLK        vir_OBSCLK                  }
    {TELEMETRYCLK  vir_TELEMETRYCLK            }
  } {
    set func_clks [get_clocks -quiet $pat]
    if {[sizeof_collection $func_clks] > 0} {
      set_clock_groups -physically_exclusive -group $func_clks -group $singlechain_clocks
    }
  }
}


set isTT false

# we override Macro clock stampings manually with our own names so treat them as physically exclusive to all other clocks
# these cause errors in litmus, using {[isSynosys] || [info commands set_interactive_constraint_modes] ne {}} as ![isLitmus]
if {[isSynopsys] || [info commands set_interactive_constraint_modes] ne {}} {
  foreach ck [lsort -unique [get_object_name [get_clocks -quiet */*]]] {
    set_clock_groups -physically_exclusive -group $ck
    set_false_path -to [get_clocks $ck]
    set_false_path -from [get_clocks $ck]
  }
}

# each functional shift clock group is physically exclusive to all the other shift clock groups
#foreach_in_collection ck [get_clocks -quiet {shift_clock_*} -filter "full_name!~*_mem"] {
#  set ckName [get_object_name $ck]
#  set curCk [get_clocks -quiet "$ckName vir_$ckName ${ckName}_mem vir_${ckName}_mem"]
#  set nonCurCk [remove_from_collection $shift_clocks $curCk]
#  if {[sizeof_collection $curCk] > 0 && [sizeof_collection $nonCurCk] > 0} {
#    set_clock_groups -physically_exclusive -group $curCk -group $nonCurCk
#  }
#}

set cmd "set_clock_groups -physically_exclusive -name tessent_ssn_bus_clocks_phy_exclusivity_group "
set ssn_clocks [get_clocks -quiet tessent_ssn_bus_clock_network_* -filter defined(sources)]
if { [sizeof_collection $ssn_clocks] > 0 } {
  set names [lsort -unique [get_object_name $ssn_clocks]]
  if { [llength $names] > 1 } {
    foreach ck $names {
      lappend cmd -group $ck
    }
    eval $cmd
  }
}


set cmd "set_clock_groups -physically_exclusive -name tessent_primary_vs_secondary_tck"
set primary   [get_clocks -quiet *_tck_*primary*   -filter defined(sources)]
set secondary [get_clocks -quiet *_tck_*secondary* -filter defined(sources)]
if { [sizeof_collection $primary] > 0 && [sizeof_collection $secondary] > 0} {
  set p_names [lsort -unique [get_object_name $primary]]
  set s_names [lsort -unique [get_object_name $secondary]]
  lappend cmd -group $p_names -group $s_names
  eval $cmd
}


set cmd "set_clock_groups -physically_exclusive -name tessent_primary_vs_secondary_bisr"
set primary   [get_clocks -quiet *_bisr_*primary*   -filter defined(sources)]
set secondary [get_clocks -quiet *_bisr_*secondary* -filter defined(sources)]
if { [sizeof_collection $primary] > 0 && [sizeof_collection $secondary] > 0} {
  set p_names [lsort -unique [get_object_name $primary]]
  set s_names [lsort -unique [get_object_name $secondary]]
  lappend cmd -group $p_names -group $s_names
  eval $cmd
}




### Start - Jungyu Im 20250925
## clock uncertainties
#set ::NOCCLK_HOLD_UNCERTAINTY [expr {5 * $::TIME_SCALE_FROM_PS}]
#set ::NOCCLK_SETUP_UNCERTAINTY [expr {65.71 * $::TIME_SCALE_FROM_PS}]
#set ::NOCCLK_PHASE_UNCERTAINTY [expr {65.71 * $::TIME_SCALE_FROM_PS}]
#set ::OVLCLK_HOLD_UNCERTAINTY [expr {5 * $::TIME_SCALE_FROM_PS}]
#set ::OVLCLK_SETUP_UNCERTAINTY [expr {62.5 * $::TIME_SCALE_FROM_PS}]
#set ::OVLCLK_PHASE_UNCERTAINTY [expr {62.5 * $::TIME_SCALE_FROM_PS}]
#set ::OVL_UNCORE_CLK_HOLD_UNCERTAINTY [expr {5 * $::TIME_SCALE_FROM_PS}]
#set ::OVL_UNCORE_CLK_SETUP_UNCERTAINTY [expr {62.5 * $::TIME_SCALE_FROM_PS}]
#set ::OVL_UNCORE_CLK_PHASE_UNCERTAINTY [expr {62.5 * $::TIME_SCALE_FROM_PS}]
#set ::ck_feedthru_HOLD_UNCERTAINTY [expr {5 * $::TIME_SCALE_FROM_PS}]
#set ::ck_feedthru_SETUP_UNCERTAINTY [expr {25.0 * $::TIME_SCALE_FROM_PS}]
#set ::ck_feedthru_PHASE_UNCERTAINTY [expr {25.0 * $::TIME_SCALE_FROM_PS}]
#set ::vir_NOCCLK_HOLD_UNCERTAINTY [expr {5 * $::TIME_SCALE_FROM_PS}]
#set ::vir_NOCCLK_SETUP_UNCERTAINTY [expr {65.71 * $::TIME_SCALE_FROM_PS}]
#set ::vir_NOCCLK_PHASE_UNCERTAINTY [expr {65.71 * $::TIME_SCALE_FROM_PS}]
#set ::vir_OVLCLK_HOLD_UNCERTAINTY [expr {5 * $::TIME_SCALE_FROM_PS}]
#set ::vir_OVLCLK_SETUP_UNCERTAINTY [expr {62.5 * $::TIME_SCALE_FROM_PS}]
#set ::vir_OVLCLK_PHASE_UNCERTAINTY [expr {62.5 * $::TIME_SCALE_FROM_PS}]
#
#set_clock_uncertainty -setup $::NOCCLK_SETUP_UNCERTAINTY [get_clocks NOCCLK]
#set_clock_uncertainty -hold  $::NOCCLK_HOLD_UNCERTAINTY  [get_clocks NOCCLK]
#set_clock_uncertainty $::NOCCLK_PHASE_UNCERTAINTY -rise_from [get_clocks NOCCLK] -fall_to [get_clocks NOCCLK]
#set_clock_uncertainty $::NOCCLK_PHASE_UNCERTAINTY -fall_from [get_clocks NOCCLK] -rise_to [get_clocks NOCCLK]
#set_clock_uncertainty -setup $::OVLCLK_SETUP_UNCERTAINTY [get_clocks OVLCLK]
#set_clock_uncertainty -hold  $::OVLCLK_HOLD_UNCERTAINTY  [get_clocks OVLCLK]
#set_clock_uncertainty $::OVLCLK_PHASE_UNCERTAINTY -rise_from [get_clocks OVLCLK] -fall_to [get_clocks OVLCLK]
#set_clock_uncertainty $::OVLCLK_PHASE_UNCERTAINTY -fall_from [get_clocks OVLCLK] -rise_to [get_clocks OVLCLK]
#set_clock_uncertainty -setup $::OVL_UNCORE_CLK_SETUP_UNCERTAINTY [get_clocks OVL_UNCORE_CLK]
#set_clock_uncertainty -hold  $::OVL_UNCORE_CLK_HOLD_UNCERTAINTY  [get_clocks OVL_UNCORE_CLK]
#set_clock_uncertainty $::OVL_UNCORE_CLK_PHASE_UNCERTAINTY -rise_from [get_clocks OVL_UNCORE_CLK] -fall_to [get_clocks OVL_UNCORE_CLK]
#set_clock_uncertainty $::OVL_UNCORE_CLK_PHASE_UNCERTAINTY -fall_from [get_clocks OVL_UNCORE_CLK] -rise_to [get_clocks OVL_UNCORE_CLK]
#set_clock_uncertainty -setup $::ck_feedthru_SETUP_UNCERTAINTY [get_clocks ck_feedthru]
#set_clock_uncertainty -hold  $::ck_feedthru_HOLD_UNCERTAINTY  [get_clocks ck_feedthru]
#set_clock_uncertainty $::ck_feedthru_PHASE_UNCERTAINTY -rise_from [get_clocks ck_feedthru] -fall_to [get_clocks ck_feedthru]
#set_clock_uncertainty $::ck_feedthru_PHASE_UNCERTAINTY -fall_from [get_clocks ck_feedthru] -rise_to [get_clocks ck_feedthru]
#set_clock_uncertainty -setup $::vir_NOCCLK_SETUP_UNCERTAINTY [get_clocks vir_NOCCLK]
#set_clock_uncertainty -hold  $::vir_NOCCLK_HOLD_UNCERTAINTY  [get_clocks vir_NOCCLK]
#set_clock_uncertainty $::vir_NOCCLK_PHASE_UNCERTAINTY -rise_from [get_clocks vir_NOCCLK] -fall_to [get_clocks vir_NOCCLK]
#set_clock_uncertainty $::vir_NOCCLK_PHASE_UNCERTAINTY -fall_from [get_clocks vir_NOCCLK] -rise_to [get_clocks vir_NOCCLK]
#set_clock_uncertainty -setup $::vir_OVLCLK_SETUP_UNCERTAINTY [get_clocks vir_OVLCLK]
#set_clock_uncertainty -hold  $::vir_OVLCLK_HOLD_UNCERTAINTY  [get_clocks vir_OVLCLK]
#set_clock_uncertainty $::vir_OVLCLK_PHASE_UNCERTAINTY -rise_from [get_clocks vir_OVLCLK] -fall_to [get_clocks vir_OVLCLK]
#set_clock_uncertainty $::vir_OVLCLK_PHASE_UNCERTAINTY -fall_from [get_clocks vir_OVLCLK] -rise_to [get_clocks vir_OVLCLK]
##DONE
### End - Jungyu Im


### Start - Jungyu Im 20250925
# transition limits
set_max_transition -clock_path [expr { 0.1 * $::NOCCLK_PERIOD }] [get_clocks NOCCLK]
set_max_transition -data_path  [expr { 0.1 * $::NOCCLK_PERIOD }] [get_clocks NOCCLK]
set_max_transition -data_path  [expr { 0.1 * $::vir_NOCCLK_PERIOD }] [get_clocks vir_NOCCLK]
set_max_transition -clock_path [expr { 0.1 * $::OVLCLK_PERIOD }] [get_clocks OVLCLK]
set_max_transition -data_path  [expr { 0.1 * $::OVLCLK_PERIOD }] [get_clocks OVLCLK]
set_max_transition -data_path  [expr { 0.1 * $::vir_OVLCLK_PERIOD }] [get_clocks vir_OVLCLK]
set_max_transition -clock_path [expr { 0.1 * $::OVLCLK_PERIOD * 2 }] [get_clocks OVL_UNCORE_CLK]
set_max_transition -data_path  [expr { 0.1 * $::OVLCLK_PERIOD * 2 }] [get_clocks OVL_UNCORE_CLK]
set_max_transition -clock_path [expr { 0.1 * $::ck_feedthru_PERIOD }] [get_clocks ck_feedthru]
set_max_transition -data_path  [expr { 0.1 * $::ck_feedthru_PERIOD }] [get_clocks ck_feedthru]
set_max_transition -clock_path [expr { 0.1 * $::vir_NOCCLK_PERIOD }] [get_clocks vir_NOCCLK]
set_max_transition -data_path  [expr { 0.1 * $::vir_NOCCLK_PERIOD }] [get_clocks vir_NOCCLK]
set_max_transition -clock_path [expr { 0.1 * $::vir_OVLCLK_PERIOD }] [get_clocks vir_OVLCLK]
set_max_transition -data_path  [expr { 0.1 * $::vir_OVLCLK_PERIOD }] [get_clocks vir_OVLCLK]
### End - Jungyu Im

set my_shared_wrappers {}
set cur_instance {}


puts "Sourcing global exception file: [info script]"
set ::SVP1 0
set clock_out_ports [get_ports -quiet -of [get_nets -quiet -of [filter_collection [driverOf [get_ports -filter direction=~*out]] defined(clocks)]] -filter direction=~*out]

# FIXME
if {[sizeof_collection $clock_out_ports] > 0} {
  set_false_path -to $clock_out_ports
}



set_max_fanout 32 [current_design]



# the following are copied from the flows/synth.global_exceptions.tcl
  # REVIEWED 11/10/25
if {[isDC]} {

  if { [info exists tt_pocvm] && $tt_pocvm == 1 && [shell_is_in_topographical_mode]} {
     ### TODO: MW: should these timing derates be set per scenario for mcmm, in setup_mcmm_scenarios.tcl? 
     ### Add guardband to account for clock tree & wire OCV not being calculated in synthesis: 
     set_timing_derate -cell_delay -pocvm_guardband -early 0.97
     set_timing_derate -cell_delay -pocvm_guardband -late 1.03 
  }
}


# MCP between 'async' D2D clocks that are generated fron NOCCLK
# REVIEWED 11/10/25
set d2d_async_clocks [get_clocks -quiet {NOCCLK_QNP* NOCCLK_DIV2_APB* NOCCLK_DIV2_AXI4L* NOCCLK_DIV2_SBTX*}]
if { [sizeof_collection $d2d_async_clocks] > 0 } {
  foreach clk {NOCCLK_QNP* NOCCLK_DIV2_APB* NOCCLK_DIV2_AXI4L* NOCCLK_DIV2_SBTX*} {
    set toClock [get_clocks $clk]
    set fromClocks [remove_from_collection $d2d_async_clocks $toClock]
    set_multicycle_path -setup 2 -end -from $fromClocks -to $toClock
    set_multicycle_path -hold 2 -end -from $fromClocks -to $toClock
  }
}
set d2d_async_ref_clocks [get_clocks -quiet {REFCLK_APB* REFCLK_AXI4L* REFCLK_SBTX*}]
if { [sizeof_collection $d2d_async_ref_clocks] > 0 } {
  foreach clk {REFCLK_APB* REFCLK_AXI4L* REFCLK_SBTX*} {
    set toClock [get_clocks $clk]
    set fromClocks [remove_from_collection $d2d_async_ref_clocks $toClock]
    set_multicycle_path -setup 1 -end -from $fromClocks -to $toClock
    set_multicycle_path -hold 1 -end -from $fromClocks -to $toClock
  }
}
set synchronizers [filter_collection [all_registers] ref_name=~SDFFY*]
if { [sizeof_collection $d2d_async_clocks] > 0 && [sizeof_collection $synchronizers] > 0} {
  set sync_d [get_pins -quiet -of $synchronizers -filter lib_pin_name=~D]
  foreach clk {NOCCLK_QNP* NOCCLK_DIV2_APB* NOCCLK_DIV2_AXI4L* NOCCLK_DIV2_SBTX*} {
    set toClock [get_clocks $clk]
    set fromClocks [remove_from_collection $d2d_async_clocks $toClock]
    set_multicycle_path -setup 1 -end -from $fromClocks -through $sync_d -to $toClock
    set_multicycle_path -hold 0 -end -from $fromClocks -through $sync_d -to $toClock
  }
}
if { [sizeof_collection $d2d_async_ref_clocks] > 0 && [sizeof_collection $synchronizers] > 0} {
  foreach clk {REFCLK_APB* REFCLK_AXI4L* REFCLK_SBTX*} {
    set toClock [get_clocks $clk]
    set fromClocks [remove_from_collection $d2d_async_ref_clocks $toClock]
    set_multicycle_path -setup 1 -end -from $fromClocks  -through $sync_d -to $toClock
    set_multicycle_path -hold 0 -end -from $fromClocks  -through $sync_d -to $toClock
  }
}

###############################################################################
# Design Compiler TCL Script: False Path and Delay Constraints for 
# tt_edc1_state_machine and tt_edc1_bus_interface instances
#
# This script contains false path constraints for asynchronous clock domain
# signals in tt_edc1_state_machine and tt_edc1_bus_interface instances containing
# synchronizer flops
#
# 1. For all edc instances, apply set_false_path -through ingress.async_init port
#    If practical, check that all edc instances have EDC_CFG.ENABLE_INIT==1
#    
# 2. For edc instances that instantiate ack_tgl sync flops:  
#    Apply set_false_path -through ingress_intf.async_init port
#    Apply set_false_path -through these ports:  egress_intf.req_tgl*, egress_intf.data*, egress_intf.err
#
# 3. For edc instances that instantiate req_tgl sync flops:
#    a. Apply set_false_path -to ingress_req0_tgl_sync3.i_D and ingress_req1_tgl_sync3.i_D
#    b. Collect all the flops fed by ingress_intf.data* and ingress_intf.err
#       Apply set_data_check -from each of the collected flops data inputs -to each of the req_tgl_sync i_D inputs
#       This check ensures data arrives close to req_tgl transition for proper handshaking
#
###############################################################################

###############################################################################
# Configuration Parameters
###############################################################################

# Data check setup time value (in nanoseconds)
# This specifies how much time before req_tgl the data must arrive
# Set to 0.0 for data to arrive at the same time as req_tgl
# Set to positive value (e.g., 0.1) for data to arrive before req_tgl
# Set to negative value (e.g., -0.1) to allow data to arrive after req_tgl
set data_check_setup_value 0.0

# Synchronizer cell reference name
set sync_flop_ref_name "tt_libcell_sync3r"

###############################################################################
# Helper Procedures
###############################################################################

# Procedure to check if a cell has a specific child instance (sync flop)
proc has_sync_flop {instance sync_name} {
    set sync_cell [get_cells -quiet ${instance}/${sync_name}]
    return [expr {[sizeof_collection $sync_cell] > 0}]
}

# Procedure to get i_D pin of a sync flop instance
proc get_sync_flop_D_pin {instance sync_name} {
    return [get_pins -quiet ${instance}/${sync_name}/i_D]
}

# Procedure to get leaf-level D pins from a hierarchical pin
# set_data_check requires leaf-level pins, not hierarchical module pins
# This traces through hierarchy to find actual flop D inputs
proc get_leaf_D_pins_from_hier_pin {hier_pin} {
    set leaf_D_pins {}
    
    if {[sizeof_collection $hier_pin] == 0} {
        return $leaf_D_pins
    }
    
    # Trace fanout to find leaf-level sequential endpoints
    set fanout_pins [all_fanout -from $hier_pin -flat -endpoints_only]
    
    if {[sizeof_collection $fanout_pins] > 0} {
        set fanout_cells [get_cells -quiet -of_objects $fanout_pins]
        
        foreach_in_collection cell $fanout_cells {
            set is_seq [get_attribute -quiet $cell is_sequential]
            set is_hier [get_attribute -quiet $cell is_hierarchical]
            
            # Only process leaf-level sequential cells
            if {$is_seq == "true" && $is_hier != "true"} {
                # Get the D input pin of this leaf cell
                set d_pin [get_pins -quiet -of $cell -filter {direction == in && (name == D || name == d || name == data_in || name == i_D)}]
                
                if {[sizeof_collection $d_pin] > 0} {
                    foreach_in_collection dp $d_pin {
                        lappend leaf_D_pins [get_object_name $dp]
                    }
                }
            }
        }
    }
    
    return [lsort -unique $leaf_D_pins]
}

###############################################################################
# Main Script - Find all EDC instances
###############################################################################

puts "INFO: Starting EDC async constraint generation..."

# Get all tt_edc1_state_machine and tt_edc1_bus_interface instances
set edc_state_machine_instances [get_cells -quiet -hierarchical -filter {ref_name =~ "tt_edc1_state_machine*"}]
set edc_bus_interface_instances [get_cells -quiet -hierarchical -filter {ref_name =~ "tt_edc1_bus_interface*"}]
set all_edc_instances [add_to_collection $edc_state_machine_instances $edc_bus_interface_instances]

if {[sizeof_collection $all_edc_instances] == 0} {
    puts "WARNING: No tt_edc1_state_machine or tt_edc1_bus_interface instances found."
    puts "WARNING: EDC async constraints may not apply."
} else {
    puts "INFO: Found [sizeof_collection $edc_state_machine_instances] tt_edc1_state_machine instance(s)"
    puts "INFO: Found [sizeof_collection $edc_bus_interface_instances] tt_edc1_bus_interface instance(s)"
}

###############################################################################
# 1. False Path Constraints for async_init (all EDC instances)
#
# The async_init signal is a multi-cycle asynchronous reset that propagates
# through the EDC chain. It should be synchronized at each node.
###############################################################################

puts "INFO: Processing async_init false path constraints..."

set async_init_count 0
set enable_init_mismatch_count 0

foreach_in_collection instance_item $all_edc_instances {
    set instance [get_object_name $instance_item]
    
    # Check for ingress_intf.async_init pin
    #set async_init_pin [get_pins -quiet ${instance}/ingress_intf.async_init]
    set async_init_pin [get_pins -quiet ${instance}/ingress_intf?async_init]
    
    if {[sizeof_collection $async_init_pin] > 0} {
        # Check if init_sync3r exists (indicates ENABLE_INIT==1)
        #set has_init_sync [has_sync_flop $instance "gen_with_init_sync.init_sync3r"]
        set has_init_sync [has_sync_flop $instance "gen_with_init_sync?init_sync3r"]
        if {!$has_init_sync} {
            # Try alternate path for BIU
            #set has_init_sync [has_sync_flop $instance "gen_init_sync.init_sync3r"]
            set has_init_sync [has_sync_flop $instance "gen_init_sync?init_sync3r"]
        }
        
        if {$has_init_sync} {
            set_false_path -through $async_init_pin \
                -comment "EDC async_init through interface pin (ENABLE_INIT=1)"
            incr async_init_count
        } else {
            puts "WARNING: Instance $instance has async_init pin but no init_sync3r flop"
            puts "         (EDC_CFG.ENABLE_INIT may be 0)"
            incr enable_init_mismatch_count
        }
    }
}

puts "INFO: Applied false path constraints through $async_init_count async_init pin(s)"
if {$enable_init_mismatch_count > 0} {
    puts "WARNING: $enable_init_mismatch_count instance(s) missing init_sync3r (ENABLE_INIT!=1)"
}

###############################################################################
# 2. False Path Constraints for ack_tgl sync flop instances
#
# For EDC instances that instantiate egress ack_tgl synchronizer flops:
# - The egress_intf outputs (req_tgl, data, data_p, err) cross clock domains
# - These signals go to the next node's ingress and are synchronized there
# - Apply false paths through these egress output ports
###############################################################################

puts "INFO: Processing ack_tgl sync flop false path constraints..."

set ack_tgl_instance_count 0
set ack_tgl_fp_count 0

foreach_in_collection instance_item $edc_state_machine_instances {
    set instance [get_object_name $instance_item]
    
    # Check if this instance has egress ack_tgl sync flops
    #set has_ack_sync0 [has_sync_flop $instance "gen_with_sync_flops.egress_ack0_tgl_sync3"]
    #set has_ack_sync1 [has_sync_flop $instance "gen_with_sync_flops.egress_ack1_tgl_sync3"]
    set has_ack_sync0 [has_sync_flop $instance "gen_with_sync_flops?egress_ack0_tgl_sync3"]
    set has_ack_sync1 [has_sync_flop $instance "gen_with_sync_flops?egress_ack1_tgl_sync3"]
    
    if {$has_ack_sync0 && $has_ack_sync1} {
        incr ack_tgl_instance_count
        
        # Apply false path through egress_intf.req_tgl[*]
        #set egress_req_tgl_pins [get_pins -quiet ${instance}/egress_intf.req_tgl*]
        set egress_req_tgl_pins [get_pins -quiet ${instance}/egress_intf?req_tgl*]
        foreach_in_collection pin $egress_req_tgl_pins {
            set pin_name [get_object_name $pin]
            set_false_path -through $pin \
                -comment "EDC egress req_tgl CDC output (ack_tgl sync instance)"
            incr ack_tgl_fp_count
        }
        
        # Apply false path through egress_intf.data[*]
        #set egress_data_pins [get_pins -quiet ${instance}/egress_intf.data*]
        set egress_data_pins [get_pins -quiet ${instance}/egress_intf?data*]
        foreach_in_collection pin $egress_data_pins {
            set pin_name [get_object_name $pin]
            set_false_path -through $pin \
                -comment "EDC egress data CDC output (ack_tgl sync instance)"
            incr ack_tgl_fp_count
        }
        
        # Apply false path through egress_intf.err
        #set egress_err_pin [get_pins -quiet ${instance}/egress_intf.err]
        set egress_err_pin [get_pins -quiet ${instance}/egress_intf?err]
        if {[sizeof_collection $egress_err_pin] > 0} {
            set_false_path -through $egress_err_pin \
                -comment "EDC egress err CDC output (ack_tgl sync instance)"
            incr ack_tgl_fp_count
        }
    }
}

puts "INFO: Found $ack_tgl_instance_count instance(s) with ack_tgl sync flops"
puts "INFO: Applied $ack_tgl_fp_count false path constraints for ack_tgl sync instances"

###############################################################################
# 3. False Path and Data Check Constraints for req_tgl sync flop instances
#
# For EDC instances that instantiate ingress req_tgl synchronizer flops:
# a. Apply false path to ingress_req0_tgl_sync3.i_D and ingress_req1_tgl_sync3.i_D
# b. Collect flops fed by ingress_intf.data* and ingress_intf.err
# c. Apply set_data_check from data flop inputs to req_tgl sync flop inputs
#    This ensures data arrives close to req_tgl transition for proper handshaking
###############################################################################

puts "INFO: Processing req_tgl sync flop constraints..."

set req_tgl_instance_count 0
set req_tgl_fp_count 0
set data_check_count 0

foreach_in_collection instance_item $edc_state_machine_instances {
    set instance [get_object_name $instance_item]
    
    # Check if this instance has ingress req_tgl sync flops
    #set has_req_sync0 [has_sync_flop $instance "gen_with_sync_flops.ingress_req0_tgl_sync3"]
    #set has_req_sync1 [has_sync_flop $instance "gen_with_sync_flops.ingress_req1_tgl_sync3"]
    set has_req_sync0 [has_sync_flop $instance "gen_with_sync_flops?ingress_req0_tgl_sync3"]
    set has_req_sync1 [has_sync_flop $instance "gen_with_sync_flops?ingress_req1_tgl_sync3"]
    
    if {$has_req_sync0 && $has_req_sync1} {
        incr req_tgl_instance_count
        
        # Get req_tgl sync flop i_D pins (hierarchical module pins)
        #set req0_D_pin [get_sync_flop_D_pin $instance "gen_with_sync_flops.ingress_req0_tgl_sync3"]
        #set req1_D_pin [get_sync_flop_D_pin $instance "gen_with_sync_flops.ingress_req1_tgl_sync3"]
        set req0_D_pin [get_sync_flop_D_pin $instance "gen_with_sync_flops?ingress_req0_tgl_sync3"]
        set req1_D_pin [get_sync_flop_D_pin $instance "gen_with_sync_flops?ingress_req1_tgl_sync3"]
        
        # 3a. Apply false path TO the req_tgl sync flop i_D inputs
        # (set_false_path works with hierarchical pins)
        if {[sizeof_collection $req0_D_pin] > 0} {
            #set_false_path -to $req0_D_pin 
            set_false_path -through $req0_D_pin \
                -comment "EDC ingress req_tgl[0] CDC sync flop input"
            incr req_tgl_fp_count
        }
        if {[sizeof_collection $req1_D_pin] > 0} {
            #set_false_path -to $req1_D_pin 
            set_false_path -through $req1_D_pin \
                -comment "EDC ingress req_tgl[1] CDC sync flop input"
            incr req_tgl_fp_count
        }
        
        # For set_data_check, we need leaf-level pins (not hierarchical module pins)
        # Trace through hierarchy to find actual flop D inputs
        set req_tgl_leaf_D_pins {}
        set req0_leaf_pins [get_leaf_D_pins_from_hier_pin $req0_D_pin]
        set req1_leaf_pins [get_leaf_D_pins_from_hier_pin $req1_D_pin]
        set req_tgl_leaf_D_pins [concat $req0_leaf_pins $req1_leaf_pins]
        set req_tgl_leaf_D_pins [lsort -unique $req_tgl_leaf_D_pins]
        
        # 3b. Collect flops fed by ingress_intf.data* and ingress_intf.err
        set data_flop_D_pins {}
        
        # Get ingress_intf.data pins
        #set ingress_data_pins [get_pins -quiet ${instance}/ingress_intf.data*]
        set ingress_data_pins [get_pins -quiet ${instance}/ingress_intf?data*]
        
        # Get ingress_intf.err pin
        #set ingress_err_pin [get_pins -quiet ${instance}/ingress_intf.err]
        set ingress_err_pin [get_pins -quiet ${instance}/ingress_intf?err]
        
        # Combine data and err pins
        set ingress_cdc_pins [add_to_collection $ingress_data_pins $ingress_err_pin]
        
        # For each ingress CDC pin, find the fanout sequential elements
        foreach_in_collection ingress_pin $ingress_cdc_pins {
            set pin_name [get_object_name $ingress_pin]
            
            # Get all fanout endpoints from this pin
            set fanout_cells [get_cells -quiet -of_objects [all_fanout -from $ingress_pin -flat -endpoints_only]]
            
            # Filter for leaf-level sequential cells only
            foreach_in_collection cell $fanout_cells {
                set cell_name [get_object_name $cell]
                set is_seq [get_attribute -quiet $cell is_sequential]
                set is_hier [get_attribute -quiet $cell is_hierarchical]
                
                # Only process leaf-level sequential cells (not hierarchical modules)
                if {$is_seq == "true" && $is_hier != "true"} {
                    # Get the data input pin of this leaf sequential cell
                    # Try common data input pin names
                    set d_pin [get_pins -quiet -of $cell -filter {direction == in && (name == D || name == d || name == data_in || name == i_D)}]
                    
                    if {[sizeof_collection $d_pin] > 0} {
                        foreach_in_collection dp $d_pin {
                            lappend data_flop_D_pins [get_object_name $dp]
                        }
                    }
                }
            }
        }
        
        # Remove duplicates from data_flop_D_pins list
        set data_flop_D_pins [lsort -unique $data_flop_D_pins]
        
        # 3c. Apply set_data_check from data flop inputs to req_tgl sync flop inputs
        # Note: set_data_check requires leaf-level pins, hence using req_tgl_leaf_D_pins
        if {[llength $data_flop_D_pins] > 0 && [llength $req_tgl_leaf_D_pins] > 0} {
            puts "INFO: Instance $instance: Found [llength $data_flop_D_pins] data flop D pins"
            puts "INFO: Instance $instance: Found [llength $req_tgl_leaf_D_pins] req_tgl leaf D pins"
            
            foreach data_pin $data_flop_D_pins {
                foreach req_pin $req_tgl_leaf_D_pins {
                    # Apply data check constraint
                    # This ensures data arrives close to req_tgl transition
                    set_data_check -from $data_pin -to $req_pin -setup $data_check_setup_value
                    
                    incr data_check_count
                }
            }
        } else {
            if {[llength $data_flop_D_pins] == 0} {
                puts "WARNING: Instance $instance: No data flops found for data_check constraints"
            }
            if {[llength $req_tgl_leaf_D_pins] == 0} {
                puts "WARNING: Instance $instance: No leaf-level req_tgl D pins found for data_check constraints"
            }
        }
    }
}

puts "INFO: Found $req_tgl_instance_count instance(s) with req_tgl sync flops"
puts "INFO: Applied $req_tgl_fp_count false path constraints to ingress sync flop inputs"
puts "INFO: Applied $data_check_count data_check constraints"

###############################################################################
# Summary
###############################################################################

puts ""
puts "==========================================================================="
puts "EDC Async Constraint Summary"
puts "==========================================================================="
puts "Total EDC state machine instances:    [sizeof_collection $edc_state_machine_instances]"
puts "Total EDC bus interface instances:    [sizeof_collection $edc_bus_interface_instances]"
puts ""
puts "async_init false paths applied:       $async_init_count"
puts "egress sync false paths:              $ack_tgl_fp_count"
puts "ingress sync false paths:             $req_tgl_fp_count"
puts "data_check constraints:               $data_check_count"
puts "==========================================================================="
puts ""
puts "INFO: Completed EDC async constraint generation"

###############################################################################
# End of Script
###############################################################################

puts "Done sourcing global exception file: [info script]"


set cur_instance tt_dispatch_engine/disp_eng_overlay_noc_wrap/disp_eng_overlay_noc_niu_router/disp_eng_overlay_wrapper/overlay_wrapper/

if {$DESIGN_NAME eq "tt_overlay_wrapper"} {
  set cur_instance {}

  #Sync cells mcp for hold. This will cover RFCLK and SYnc crossing on async signals
  #TODO:  dkrings -- this should be removed this is not a valid MCP. and moved to global_exceptions.tcl
  #set sync_d_pins [filter_collection [all_registers -data_pins] "(full_name=~${cur_instance}*sync3*||full_name=~${cur_instance}*sync2*)&&(full_name!~*/SI&&full_name!~*/SE)"]
  #set_multicycle_path -end -hold 2 -to [get_pins $sync_d_pins]
}
#set reset_from [get_pins -quiet clock_reset_ctrl?gen_core_clk_reset_sync_*__core_clk_reset_sync?gen_rst_sync_stage_*__sync_dffr_d0nt_dffr/CK]
#if {[sizeof_collection $reset_from] > 0} {
#  set_multicycle_path -end -setup 6 -from $reset_from  -to [get_clocks {OVLCLK vir_OVLCLK}]
#  set_multicycle_path -end -setup 5 -from $reset_from  -to [get_clocks {OVLCLK vir_OVLCLK}]
#}

#set reset_from [get_pins -quiet  ${cur_instance}clock_reset_ctrl?uncore_clk_reset_sync?gen_rst_sync_stage_.*_?sync_dffr_d0nt_dffr/CK]
#if {[sizeof_collection $reset_from] > 0} {
#  set_multicycle_path -end -setup 3 -from $reset_from -to [get_clocks {OVL_UNCORE_CLK}]
#  set_multicycle_path -end -hold  2 -from $reset_from -to [get_clocks {OVL_UNCORE_CLK}]
#}

set reset_from [get_pins -quiet ${cur_instance}clock_reset_ctrl?noc_clk_reset_sync?gen_rst_sync_stage_*_?sync_dffr_d0nt_dffr/CK]
if {[sizeof_collection $reset_from] > 0} {
  set_multicycle_path -end -setup 4 -from $reset_from -to [get_clocks {NOCCLK*}]
  set_multicycle_path -end -hold  3 -from $reset_from -to [get_clocks {NOCCLK*}]
}

set reset_from [get_pins -quiet  ${cur_instance}clock_reset_ctrl?ai_clk_reset_sync?gen_rst_sync_stage_*_?sync_dffr_d0nt_dffr/CK]
if {[sizeof_collection $reset_from] > 0} {
  set_multicycle_path -end -setup 4 -from $reset_from -to [get_clocks {AICLK*}]
  set_multicycle_path -end -hold  3 -from $reset_from -to [get_clocks {AICLK*}]
}



set cur_instance {}
set cur_instance {}



##############################################################################################
####################################### BOS-constraint #######################################
##############################################################################################
if {$USE_ND} {
    source ${SDC_HOME}/common_imem_EMA_setting.tcl
} else {
    source ${SDC_HOME}/common_imem_EMA_setting_OD.tcl
}

source -echo -verbose ${NPU_HOME}/HPDF/constraint_by_TT.tcl

# reset MCP
set my_ports [get_ports  { i_*reset_n } -filter "direction=~in*"]
if { [sizeof_collection $my_ports]>0 } { set_multicycle_path -setup 4 -from $my_ports }
if { [sizeof_collection $my_ports]>0 } { set_multicycle_path -hold 3 -from $my_ports }

## remove input delay static ports
set input_opt "i_static_is_r180"
remove_input_delay [get_ports $input_opt]
unset input_opt

set input_opt "i_phys_x*"
remove_input_delay [get_ports $input_opt]
unset input_opt

set input_opt "i_phys_y*"
remove_input_delay [get_ports $input_opt]
unset input_opt

## TEMP MCP before applying TT SDC
set my_in_ports  [get_ports -quiet  { *t6_to_de* } -filter "direction=~in" ]
set my_out_ports [get_ports -quiet  { *t6_to_de* } -filter "direction=~out"]
if { [sizeof_collection $my_in_ports]>0 } { set_multicycle_path -setup 3 -from $my_in_ports  }
if { [sizeof_collection $my_in_ports]>0 } { set_multicycle_path -hold  2 -from $my_in_ports  }
if { [sizeof_collection $my_out_ports]>0 } { set_multicycle_path -setup 3 -to $my_out_ports  }
if { [sizeof_collection $my_out_ports]>0 } { set_multicycle_path -hold  2 -to $my_out_ports  }

set my_in_ports  [get_ports -quiet  { *de_to_t6* } -filter "direction=~in" ]
set my_out_ports [get_ports -quiet  { *de_to_t6* } -filter "direction=~out"]
if { [sizeof_collection $my_in_ports]>0 } { set_multicycle_path -setup 3  -from $my_in_ports  }
if { [sizeof_collection $my_in_ports]>0 } { set_multicycle_path -hold  2  -from $my_in_ports  }
if { [sizeof_collection $my_out_ports]>0 } { set_multicycle_path -setup 3  -to $my_out_ports  }
if { [sizeof_collection $my_out_ports]>0 } { set_multicycle_path -hold  2  -to $my_out_ports  }


