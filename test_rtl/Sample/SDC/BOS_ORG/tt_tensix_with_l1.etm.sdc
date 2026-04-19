if {![info exists ::SDC_DIR]} { set ::SDC_DIR {./}}
global SDC_DIR
set ::DESIGN_NAME tt_tensix_with_l1
if {![info exists ::tt_global_is_mapped]} { set ::tt_global_is_mapped 1 }
if {![info exists ::DESIGN_NAME]} { set ::DESIGN_NAME {tt_tensix_with_l1} }
global DESIGN_NAME
global tt_global_is_mapped

# This file contains procs that might be end up being usd in the redo file

################################################################################
# general procs for determining what tool is being run
################################################################################

#-------------------------------------------------------------------------------
proc myExecutable {} {
  if {[info vars ::synopsys_program_name] ne {}} {
    return $::synopsys_program_name
  } elseif {[info vars ::argv0] ne {}} {
    return [file tail $::argv0]
  } else {
    return "tclsh"
  }
}

#-------------------------------------------------------------------------------
proc isInnovus {} {
  if {[myExecutable] eq "innovus"} { return true }
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
  if {[string match {dc*} [myExecutable]]} { return true }
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
      set clkgates [filter_collection [all_registers] "is_clock_gating_check==true"]
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
      set clkgates [filter_collection [all_registers] "is_clock_gating_check==true"]
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
      set clkgates [filter_collection [all_registers] "is_clock_gating_check==true"]
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
proc getPinOrPort {thing} {
  set pins [get_pins -quiet $thing]
  append_to_collection pins [get_ports -quiet $thing]
  return $pins
}

proc cat_file {args} {return}
if {[info commands get_flow_config] eq {}} {
  proc get_flow_config {args} {return {}}
}


### Start Jungyu Im 20250304
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
set ::AICLK_PERIOD [expr (1 / $FREQ_AI) * (1 - $CLK_MARGIN)]
set ::NOCCLK_PERIOD [expr (1 / $FREQ_NOC) * (1 - $CLK_MARGIN)]
set ::OVLCLK_PERIOD [expr (1 / $FREQ_OVL) * (1 - $CLK_MARGIN)]
set ::RFCLK_NOC_PERIOD [expr (1 / 0.1) * (1 - $CLK_MARGIN)]
set ::ck_feedthru_PERIOD [expr (1 / 1) * (1 - $CLK_MARGIN)]
set ::ck_untimed_PERIOD [expr (1 / 0.1) * (1 - $CLK_MARGIN)]
set ::vir_NOCCLK_PERIOD [expr (1 / $FREQ_NOC) * (1 - $CLK_MARGIN)]
set ::vir_SMNCLK_PERIOD [expr (0.5 / $FREQ_NOC) * (1 - $CLK_MARGIN)]
set ::vir_scan_clock_PERIOD [expr 0.3333 * (1 - $CLK_MARGIN)]
set ::vir_tessent_ssn_bus_clock_network_PERIOD [expr 0.3333 * (1 - $CLK_MARGIN)]
#set ::AICLK_PERIOD 666.0
#set ::NOCCLK_PERIOD 714.0
#set ::OVLCLK_PERIOD 500.0
#set ::RFCLK_NOC_PERIOD 10000.0
#set ::ck_feedthru_PERIOD 1000.0
#set ::ck_untimed_PERIOD 10000.0
#set ::vir_NOCCLK_PERIOD 714.0
#set ::vir_SMNCLK_PERIOD 1428.0
#set ::vir_scan_clock_PERIOD 3333.0
#set ::vir_tessent_ssn_bus_clock_network_PERIOD 3333.0
### End - Jungyu Im

### Start Jungyu Im 20250716
set ::PERIOD_PRTNUN_CLK     [expr (1 / 0.1) * (1 - $CLK_MARGIN)]

create_clock -add -name "PRTNUN_CLK"     -period $::PERIOD_PRTNUN_CLK      [get_ports PRTNUN_FC2UN_CLK_IN]
### End - Jungyu Im

# create_clocks
create_clock -add -name AICLK -period $::AICLK_PERIOD [get_ports {i_ai_clk}]
create_clock -add -name NOCCLK -period $::NOCCLK_PERIOD [get_ports {i_noc_clk}]

create_clock -add -name OVLCLK -period $::OVLCLK_PERIOD [get_ports {i_dm_clk}]
#create_clock -add -name RFCLK_NOC -period $::RFCLK_NOC_PERIOD [get_ports {i_noc_clk}]
create_clock -add -name ck_feedthru -period $::ck_feedthru_PERIOD
create_clock -add -name ck_untimed -period $::ck_untimed_PERIOD
create_clock -add -name vir_NOCCLK -period $::vir_NOCCLK_PERIOD
create_clock -add -name vir_scan_clock -period $::vir_scan_clock_PERIOD
create_clock -add -name vir_tessent_ssn_bus_clock_network -period $::vir_tessent_ssn_bus_clock_network_PERIOD
create_clock -add -name vir_SMNCLK -period $::vir_SMNCLK_PERIOD
#DONE


### Start - Jungyu Im 20250416 : add ideal network for clocks
set_ideal_network -no_propagate [get_port {i_ai_clk}]
set_ideal_network -no_propagate [get_port {i_noc_clk}]
set_ideal_network -no_propagate [get_port {i_dm_clk}]
set_ideal_network -no_propagate [get_pins -hierarchical */ECK]
### End - Jungyu Im


### Start - Jungyu Im 20250715 : modify SDC constraint (set_in/output_delay for DFT ports)
#set my_ports [get_ports -quiet { * } -filter "direction=~in* && !defined(clocks)"]
#set my_clock [get_clocks -quiet { ck_feedthru }]
#if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_input_delay -max -clock $my_clock  [expr { 0 * $::ck_feedthru_PERIOD / 100.0 }] $my_ports }
#
#set my_ports [get_ports -quiet { * } -filter "direction=~*out && !defined(clocks)"]
#set my_clock [get_clocks -quiet { ck_feedthru }]
#if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_output_delay -max -clock $my_clock  [expr { 90 * $::ck_feedthru_PERIOD / 100.0 }] $my_ports }
#
#set my_ports [get_ports -quiet { * } -filter "direction=~in* && !defined(clocks)"]
#set my_clock [get_clocks -quiet { vir_NOCCLK }]
#if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_input_delay -add_delay -max -clock $my_clock  [expr { 60 * $::vir_NOCCLK_PERIOD / 100.0 }] $my_ports }
#
#set my_ports [get_ports -quiet { * } -filter "direction=~*out && !defined(clocks) "]
#set my_clock [get_clocks -quiet { vir_NOCCLK }]
#if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_output_delay -add_delay -max -clock $my_clock  [expr { 60 * $::vir_NOCCLK_PERIOD / 100.0 }] $my_ports }
source -e -v $NPU_HOME/HPDF/port.tcl > ./logs/port_test.log

set my_ports [get_ports $filtered_in_ports]
set my_clock [get_clocks -quiet { ck_feedthru }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_input_delay -max -clock $my_clock  [expr { 0 * $::ck_feedthru_PERIOD / 100.0 }] $my_ports }

set my_ports [get_ports $filtered_out_ports]
set my_clock [get_clocks -quiet { ck_feedthru }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_output_delay -max -clock $my_clock  [expr { 70 * $::ck_feedthru_PERIOD / 100.0 }] $my_ports }

set my_ports [get_ports $filtered_in_ports]
set my_clock [get_clocks -quiet { vir_NOCCLK }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_input_delay -add_delay -max -clock $my_clock  [expr { 60 * $::vir_NOCCLK_PERIOD / 100.0 }] $my_ports }

set my_ports [get_ports $filtered_out_ports]
set my_clock [get_clocks -quiet { vir_NOCCLK }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_output_delay -add_delay -max -clock $my_clock  [expr { 60 * $::vir_NOCCLK_PERIOD / 100.0 }] $my_ports }
### End - Jungyu Im


set my_out_ports [get_ports -quiet { * } -filter "direction=~*out"]
if {  [sizeof_collection $my_out_ports]>0 } { set_load 0.04 $my_out_ports }

set my_in_ports [get_ports -quiet { * } -filter "direction=~in*"]

set my_in_ports [get_ports -quiet { * } -filter "direction=~in* && defined(clocks)"]

set my_in_ports [get_ports -quiet { * } -filter "direction=~in*"]
set my_out_ports [get_ports -quiet { * } -filter "direction=~*out"]
set my_from_clock [get_clocks -quiet { vir_NOCCLK }]
set my_to_clock [get_clocks -quiet { vir_NOCCLK }]
if { [sizeof_collection $my_from_clock]>0 && [sizeof_collection $my_to_clock]>0 && [sizeof_collection $my_in_ports]>0 && [sizeof_collection $my_out_ports]>0 } { set_false_path -setup -from $my_from_clock -through $my_in_ports -through $my_out_ports -to $my_to_clock }

set my_ports [get_ports -quiet { test_si* } -filter "direction=~in* && !defined(clocks)"]
set my_clock [get_clocks -quiet { vir_tessent_ssn_bus_clock_network }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_input_delay -max -clock $my_clock  [expr { 50 * $::vir_tessent_ssn_bus_clock_network_PERIOD / 100.0 }] $my_ports }

set my_ports [get_ports -quiet { test_so* } -filter "direction=~*out && !defined(clocks)"]
set my_clock [get_clocks -quiet { vir_tessent_ssn_bus_clock_network }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_output_delay -max -clock $my_clock  [expr { 50 * $::vir_tessent_ssn_bus_clock_network_PERIOD / 100.0 }] $my_ports }

set my_ports [get_ports -quiet { i_noc_clk_* } -filter "direction=~in* && !defined(clocks)"]
set my_clock [get_clocks -quiet { ck_untimed }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_input_delay -max -clock $my_clock  [expr { 0 * $::ck_untimed_PERIOD / 100.0 }] $my_ports }

set my_ports [get_ports -quiet { o_noc_clk_* } -filter "direction=~*out && !defined(clocks)"]
set my_clock [get_clocks -quiet { ck_untimed }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_output_delay -max -clock $my_clock  [expr { 0 * $::ck_untimed_PERIOD / 100.0 }] $my_ports }

set my_ports [get_ports -quiet { i_ref_clk_* } -filter "direction=~in* && !defined(clocks)"]
set my_clock [get_clocks -quiet { ck_untimed }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_input_delay -max -clock $my_clock  [expr { 0 * $::ck_untimed_PERIOD / 100.0 }] $my_ports }

set my_ports [get_ports -quiet { o_ref_clk_* } -filter "direction=~*out && !defined(clocks)"]
set my_clock [get_clocks -quiet { ck_untimed }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_output_delay -max -clock $my_clock  [expr { 0 * $::ck_untimed_PERIOD / 100.0 }] $my_ports }

set my_ports [get_ports -quiet { i_reset_n } -filter "direction=~in*"]
set my_clock [get_clocks -quiet { NOCCLK* }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_multicycle_path -setup 4 -from $my_ports -to $my_clock }

set my_ports [get_ports -quiet { i_nocclk_reset_n } -filter "direction=~in*"]
set my_clock [get_clocks -quiet { NOCCLK* }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_multicycle_path -setup 4 -from $my_ports -to $my_clock }

set my_ports [get_ports -quiet { i_aiclk_reset_n } -filter "direction=~in*"]
set my_clock [get_clocks -quiet { AICLK }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_multicycle_path -setup 4 -from $my_ports -to $my_clock }

set my_ports [get_ports -quiet { i_noc_reset_n } -filter "direction=~in* && !defined(clocks)"]
set my_clock [get_clocks -quiet { vir_NOCCLK }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_input_delay -max -clock $my_clock  [expr { 30 * $::vir_NOCCLK_PERIOD / 100.0 }] $my_ports }

set my_ports [get_ports -quiet { i_axi_reset_n } -filter "direction=~in* && !defined(clocks)"]
set my_clock [get_clocks -quiet { vir_NOCCLK }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_input_delay -max -clock $my_clock  [expr { 0 * $::vir_NOCCLK_PERIOD / 100.0 }] $my_ports }

set my_ports [get_ports -quiet { i_test_clk_en* } -filter "direction=~in* && !defined(clocks)"]
set my_clock [get_clocks -quiet { vir_scan_clock }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_input_delay -max -clock $my_clock  [expr { 50 * $::vir_scan_clock_PERIOD / 100.0 }] $my_ports }

set my_ports [get_ports -quiet { i_test_mode* } -filter "direction=~in* && !defined(clocks)"]
set my_clock [get_clocks -quiet { vir_scan_clock }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_input_delay -max -clock $my_clock  [expr { 50 * $::vir_scan_clock_PERIOD / 100.0 }] $my_ports }

set my_ports [get_ports -quiet { i_smn*flit* } -filter "direction=~in* && !defined(clocks)"]
set my_clock [get_clocks -quiet { vir_SMNCLK }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_input_delay -max -clock $my_clock  [expr { 30 * $::vir_SMNCLK_PERIOD / 100.0 }] $my_ports }

set my_ports [get_ports -quiet { o_smn*flit* } -filter "direction=~*out && !defined(clocks)"]
set my_clock [get_clocks -quiet { vir_SMNCLK }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_output_delay -max -clock $my_clock  [expr { 30 * $::vir_SMNCLK_PERIOD / 100.0 }] $my_ports }

set my_ports [get_ports -quiet { i_dateline_node_* }]
set my_from_clock [get_clocks -quiet { * }]
set my_to_clock [get_clocks -quiet { * }]
if { [sizeof_collection $my_from_clock]>0 && [sizeof_collection $my_to_clock]>0 && [sizeof_collection $my_ports]>0 } { set_false_path -setup -from $my_from_clock -through $my_ports -to $my_to_clock }

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

set my_ports [get_ports -quiet { i_security_* }]
set my_from_clock [get_clocks -quiet { * }]
set my_to_clock [get_clocks -quiet { * }]
if { [sizeof_collection $my_from_clock]>0 && [sizeof_collection $my_to_clock]>0 && [sizeof_collection $my_ports]>0 } { set_false_path -setup -from $my_from_clock -through $my_ports -to $my_to_clock }

set my_ports [get_ports -quiet { i_routing_dim_order_* }]
set my_from_clock [get_clocks -quiet { * }]
set my_to_clock [get_clocks -quiet { * }]
if { [sizeof_collection $my_from_clock]>0 && [sizeof_collection $my_to_clock]>0 && [sizeof_collection $my_ports]>0 } { set_false_path -setup -from $my_from_clock -through $my_ports -to $my_to_clock }

set my_ports [get_ports -quiet { i_mem_*cfg* }]
set my_from_clock [get_clocks -quiet { * }]
set my_to_clock [get_clocks -quiet { * }]
if { [sizeof_collection $my_from_clock]>0 && [sizeof_collection $my_to_clock]>0 && [sizeof_collection $my_ports]>0 } { set_false_path -setup -from $my_from_clock -through $my_ports -to $my_to_clock }

set my_ports [get_ports -quiet { i_mem_*settings* }]
set my_from_clock [get_clocks -quiet { * }]
set my_to_clock [get_clocks -quiet { * }]
if { [sizeof_collection $my_from_clock]>0 && [sizeof_collection $my_to_clock]>0 && [sizeof_collection $my_ports]>0 } { set_false_path -setup -from $my_from_clock -through $my_ports -to $my_to_clock }

set my_ports [get_ports -quiet { i_phys_*_coord* }]
set my_from_clock [get_clocks -quiet { * }]
set my_to_clock [get_clocks -quiet { * }]
if { [sizeof_collection $my_from_clock]>0 && [sizeof_collection $my_to_clock]>0 && [sizeof_collection $my_ports]>0 } { set_false_path -setup -from $my_from_clock -through $my_ports -to $my_to_clock }

set my_ports [get_ports -quiet { o_nxt_phys_*_coord* }]
set my_from_clock [get_clocks -quiet { * }]
set my_to_clock [get_clocks -quiet { * }]
if { [sizeof_collection $my_from_clock]>0 && [sizeof_collection $my_to_clock]>0 && [sizeof_collection $my_ports]>0 } { set_false_path -setup -from $my_from_clock -through $my_ports -to $my_to_clock }

set my_ports [get_ports -quiet { o_local_node* }]
set my_from_clock [get_clocks -quiet { * }]
set my_to_clock [get_clocks -quiet { * }]
if { [sizeof_collection $my_from_clock]>0 && [sizeof_collection $my_to_clock]>0 && [sizeof_collection $my_ports]>0 } { set_false_path -setup -from $my_from_clock -through $my_ports -to $my_to_clock }

set my_ports [get_ports -quiet { o_mem_shutdown* }]
set my_from_clock [get_clocks -quiet { * }]
set my_to_clock [get_clocks -quiet { * }]
if { [sizeof_collection $my_from_clock]>0 && [sizeof_collection $my_to_clock]>0 && [sizeof_collection $my_ports]>0 } { set_false_path -setup -from $my_from_clock -through $my_ports -to $my_to_clock }

set my_ports [get_ports -quiet { o_tile_* }]
set my_from_clock [get_clocks -quiet { * }]
set my_to_clock [get_clocks -quiet { * }]
if { [sizeof_collection $my_from_clock]>0 && [sizeof_collection $my_to_clock]>0 && [sizeof_collection $my_ports]>0 } { set_false_path -setup -from $my_from_clock -through $my_ports -to $my_to_clock }

set my_ports [get_ports -quiet { o_intp* }]
set my_from_clock [get_clocks -quiet { * }]
set my_to_clock [get_clocks -quiet { * }]
if { [sizeof_collection $my_from_clock]>0 && [sizeof_collection $my_to_clock]>0 && [sizeof_collection $my_ports]>0 } { set_false_path -setup -from $my_from_clock -through $my_ports -to $my_to_clock }

set my_ports [get_ports -quiet { o_ecc_err* }]
set my_from_clock [get_clocks -quiet { * }]
set my_to_clock [get_clocks -quiet { * }]
if { [sizeof_collection $my_from_clock]>0 && [sizeof_collection $my_to_clock]>0 && [sizeof_collection $my_ports]>0 } { set_false_path -setup -from $my_from_clock -through $my_ports -to $my_to_clock }

set my_ports [get_ports -quiet { i_sys_bap_test_* } -filter "direction=~in*"]
set my_clock [get_clocks -quiet { ck_feedthru }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_multicycle_path -setup 6 -from $my_ports -to $my_clock }

set my_ports [get_ports -quiet { i_sys_bap_test_* } -filter "direction=~in*"]
set my_clock [get_clocks -quiet { ck_feedthru }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_multicycle_path -setup 6 -from $my_ports -to $my_clock }

set my_ports [get_ports -quiet { o_sys_bap_test_* } -filter "direction=~*out"]
set my_clock [get_clocks -quiet { * }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_multicycle_path -setup 6 -to $my_ports -from $my_clock }

set my_ports [get_ports -quiet { o_sys_bap_test_* } -filter "direction=~*out"]
set my_clock [get_clocks -quiet { vir_* }]
if { [sizeof_collection $my_clock]>0 && [sizeof_collection $my_ports]>0 } { set_multicycle_path -setup 6 -to $my_ports -from $my_clock }





set bbox_scan_clocks [get_clocks -quiet {*/*shift_clock* */*scan_* */*tessent*}]
set shift_clocks [get_clocks -quiet {*shift_clock*}]
set shift_clocks [remove_from_collection $shift_clocks $bbox_scan_clocks]
set scan_clocks [get_clocks [lsort -unique [get_object_name [get_clocks -quiet {*shift_clock_* *scan_* *tessent*}]]]]
set scan_clocks [remove_from_collection $scan_clocks [get_clocks -quiet  *tessent*_tck]]
set scan_clocks [remove_from_collection $scan_clocks $bbox_scan_clocks]
set scan_pat [lsort -unique [get_object_name $scan_clocks]]

if {[isCadence] && [info commands set_interactive_constraint_modes] ne {}} {
  set curmode [get_interactive_constraint_modes]
  set_interactive_constraint_modes ${::CORNER}
}

set cmd "set_clock_groups -asynchronous"
foreach pat [list \
  {TCK                      vir_TCK                    *_tck*}\
  {AICLK*                   vir_AICLK*                       }\
  {NOCCLK*                  vir_NOCCLK*                *ck_async*}\
  {SMN_CLK*                 vir_SMN_CLK*                     }\
  {OVL*CLK*                 vir_OVL*CLK*                     }\
  {SYSCLK*                  vir_SYSCLK*             *CLK_WR0*}\
  {PERIPHCLK*               vir_PERIPHCLK*                   }\
  {SPI_*                    vir_SPI_*                   *DQS*}\
  {I3C_CLK                  vir_I3C_CLK                      }\
  {I3C_SCAN_CLK             vir_I3C_SCAN_CLK                 }\
  {RFCLK*                   vir_RFCLK*                       }\
  {ck_feedthru              vir_ck_feedthru                  }\
  {ck_dummy                 vir_ck_dummy                     }\
  {ck_untimed               vir_ck_untimed                   }\
  {DROOPCLK                 vir_DROOPCLK                     }\
  {PRTNUN_CLK                                                }\
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
    {TCK           vir_TCK               *_tck*}
    {AICLK*        vir_AICLK*                  }
    {NOCCLK*       vir_NOCCLK*          *ck_async*}
    {SMN_CLK*      vir_SMN_CLK*                }
    {OVL*CLK*      vir_OVL*CLK*                }
    {SYSCLK*       vir_SYSCLK*        *CLK_WR0*}
    {PERIPHCLK*    vir_PERIPHCLK*              }
    {SPI_*         vir_SPI_*              *DQS*}
    {I3C_CLK*      vir_I3C_CLK*                }
    {I3C_SCAN_CLK* vir_I3C_SCAN_CLK*           }
    {DROOPCLK      vir_DROOPCLK                }
    {RFCLK_*       vir_RFCLK_*                 }
  } {
    set func_clks [get_clocks -quiet $pat]
    if {[sizeof_collection $func_clks] > 0} {
      set_clock_groups -physically_exclusive -group $func_clks -group $scan_clocks
    }
  }
}

set isTT false
# we override Macro clock stampings manually with our own names so treat them as physically exclusive to all other clocks
foreach_in_collection clock [get_clocks -quiet */*] {
  set_clock_groups -physically_exclusive -group [get_object_name $clock]
  set_false_path -to $clock
  set_false_path -from $clock
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




### Start - Jungyu Im 20250418
## clock uncertainties
#set ::AICLK_HOLD_UNCERTAINTY 5
#set ::AICLK_SETUP_UNCERTAINTY 44.99
#set ::AICLK_PHASE_UNCERTAINTY 44.99
#set ::NOCCLK_HOLD_UNCERTAINTY 5
#set ::NOCCLK_SETUP_UNCERTAINTY 65.71
#set ::NOCCLK_PHASE_UNCERTAINTY 65.71
#set ::OVLCLK_HOLD_UNCERTAINTY 5
#set ::OVLCLK_SETUP_UNCERTAINTY 62.5
#set ::OVLCLK_PHASE_UNCERTAINTY 62.5
#set ::RFCLK_NOC_HOLD_UNCERTAINTY 5
#set ::RFCLK_NOC_SETUP_UNCERTAINTY 201.65
#set ::RFCLK_NOC_PHASE_UNCERTAINTY 201.65
#set ::ck_feedthru_HOLD_UNCERTAINTY 5
#set ::ck_feedthru_SETUP_UNCERTAINTY 25.0
#set ::ck_feedthru_PHASE_UNCERTAINTY 25.0
#set ::ck_untimed_HOLD_UNCERTAINTY 5
#set ::ck_untimed_SETUP_UNCERTAINTY 25.0
#set ::ck_untimed_PHASE_UNCERTAINTY 25.0
#set ::vir_NOCCLK_HOLD_UNCERTAINTY 5
#set ::vir_NOCCLK_SETUP_UNCERTAINTY 65.71
#set ::vir_NOCCLK_PHASE_UNCERTAINTY 65.71
#set ::vir_SMNCLK_HOLD_UNCERTAINTY 5
#set ::vir_SMNCLK_SETUP_UNCERTAINTY 76.42
#set ::vir_SMNCLK_PHASE_UNCERTAINTY 76.42
#set ::vir_scan_clock_HOLD_UNCERTAINTY 5
#set ::vir_scan_clock_SETUP_UNCERTAINTY 391.65
#set ::vir_scan_clock_PHASE_UNCERTAINTY 391.65
#set ::vir_tessent_ssn_bus_clock_network_HOLD_UNCERTAINTY 5
#set ::vir_tessent_ssn_bus_clock_network_SETUP_UNCERTAINTY 391.65
#set ::vir_tessent_ssn_bus_clock_network_PHASE_UNCERTAINTY 391.65

#
#set_clock_uncertainty -setup $::AICLK_SETUP_UNCERTAINTY [get_clocks AICLK]
#set_clock_uncertainty -hold  $::AICLK_HOLD_UNCERTAINTY  [get_clocks AICLK]
#set_clock_uncertainty $::AICLK_PHASE_UNCERTAINTY -rise_from [get_clocks] -fall_to [get_clocks AICLK]
#set_clock_uncertainty $::AICLK_PHASE_UNCERTAINTY -fall_from [get_clocks] -rise_to [get_clocks AICLK]
#set_clock_uncertainty -setup $::NOCCLK_SETUP_UNCERTAINTY [get_clocks NOCCLK]
#set_clock_uncertainty -hold  $::NOCCLK_HOLD_UNCERTAINTY  [get_clocks NOCCLK]
#set_clock_uncertainty $::NOCCLK_PHASE_UNCERTAINTY -rise_from [get_clocks] -fall_to [get_clocks NOCCLK]
#set_clock_uncertainty $::NOCCLK_PHASE_UNCERTAINTY -fall_from [get_clocks] -rise_to [get_clocks NOCCLK]
#set_clock_uncertainty -setup $::OVLCLK_SETUP_UNCERTAINTY [get_clocks OVLCLK]
#set_clock_uncertainty -hold  $::OVLCLK_HOLD_UNCERTAINTY  [get_clocks OVLCLK]
#set_clock_uncertainty $::OVLCLK_PHASE_UNCERTAINTY -rise_from [get_clocks] -fall_to [get_clocks OVLCLK]
#set_clock_uncertainty $::OVLCLK_PHASE_UNCERTAINTY -fall_from [get_clocks] -rise_to [get_clocks OVLCLK]
#set_clock_uncertainty -setup $::RFCLK_NOC_SETUP_UNCERTAINTY [get_clocks RFCLK_NOC]
#set_clock_uncertainty -hold  $::RFCLK_NOC_HOLD_UNCERTAINTY  [get_clocks RFCLK_NOC]
#set_clock_uncertainty $::RFCLK_NOC_PHASE_UNCERTAINTY -rise_from [get_clocks] -fall_to [get_clocks RFCLK_NOC]
#set_clock_uncertainty $::RFCLK_NOC_PHASE_UNCERTAINTY -fall_from [get_clocks] -rise_to [get_clocks RFCLK_NOC]
#set_clock_uncertainty -setup $::ck_feedthru_SETUP_UNCERTAINTY [get_clocks ck_feedthru]
#set_clock_uncertainty -hold  $::ck_feedthru_HOLD_UNCERTAINTY  [get_clocks ck_feedthru]
#set_clock_uncertainty $::ck_feedthru_PHASE_UNCERTAINTY -rise_from [get_clocks] -fall_to [get_clocks ck_feedthru]
#set_clock_uncertainty $::ck_feedthru_PHASE_UNCERTAINTY -fall_from [get_clocks] -rise_to [get_clocks ck_feedthru]
#set_clock_uncertainty -setup $::ck_untimed_SETUP_UNCERTAINTY [get_clocks ck_untimed]
#set_clock_uncertainty -hold  $::ck_untimed_HOLD_UNCERTAINTY  [get_clocks ck_untimed]
#set_clock_uncertainty $::ck_untimed_PHASE_UNCERTAINTY -rise_from [get_clocks] -fall_to [get_clocks ck_untimed]
#set_clock_uncertainty $::ck_untimed_PHASE_UNCERTAINTY -fall_from [get_clocks] -rise_to [get_clocks ck_untimed]
#set_clock_uncertainty -setup $::vir_NOCCLK_SETUP_UNCERTAINTY [get_clocks vir_NOCCLK]
#set_clock_uncertainty -hold  $::vir_NOCCLK_HOLD_UNCERTAINTY  [get_clocks vir_NOCCLK]
#set_clock_uncertainty $::vir_NOCCLK_PHASE_UNCERTAINTY -rise_from [get_clocks] -fall_to [get_clocks vir_NOCCLK]
#set_clock_uncertainty $::vir_NOCCLK_PHASE_UNCERTAINTY -fall_from [get_clocks] -rise_to [get_clocks vir_NOCCLK]
#set_clock_uncertainty -setup $::vir_SMNCLK_SETUP_UNCERTAINTY [get_clocks vir_SMNCLK]
#set_clock_uncertainty -hold  $::vir_SMNCLK_HOLD_UNCERTAINTY  [get_clocks vir_SMNCLK]
#set_clock_uncertainty $::vir_SMNCLK_PHASE_UNCERTAINTY -rise_from [get_clocks] -fall_to [get_clocks vir_SMNCLK]
#set_clock_uncertainty $::vir_SMNCLK_PHASE_UNCERTAINTY -fall_from [get_clocks] -rise_to [get_clocks vir_SMNCLK]
#set_clock_uncertainty -setup $::vir_scan_clock_SETUP_UNCERTAINTY [get_clocks vir_scan_clock]
#set_clock_uncertainty -hold  $::vir_scan_clock_HOLD_UNCERTAINTY  [get_clocks vir_scan_clock]
#set_clock_uncertainty $::vir_scan_clock_PHASE_UNCERTAINTY -rise_from [get_clocks] -fall_to [get_clocks vir_scan_clock]
#set_clock_uncertainty $::vir_scan_clock_PHASE_UNCERTAINTY -fall_from [get_clocks] -rise_to [get_clocks vir_scan_clock]
#set_clock_uncertainty -setup $::vir_tessent_ssn_bus_clock_network_SETUP_UNCERTAINTY [get_clocks vir_tessent_ssn_bus_clock_network]
#set_clock_uncertainty -hold  $::vir_tessent_ssn_bus_clock_network_HOLD_UNCERTAINTY  [get_clocks vir_tessent_ssn_bus_clock_network]
#set_clock_uncertainty $::vir_tessent_ssn_bus_clock_network_PHASE_UNCERTAINTY -rise_from [get_clocks] -fall_to [get_clocks vir_tessent_ssn_bus_clock_network]
#set_clock_uncertainty $::vir_tessent_ssn_bus_clock_network_PHASE_UNCERTAINTY -fall_from [get_clocks] -rise_to [get_clocks vir_tessent_ssn_bus_clock_network]
##DONE
### End - Jungyu Im 20250418


# transition limits
set_max_transition -clock_path [expr 66.6*0.001]  [get_clocks AICLK]
set_max_transition -data_path [expr 200*0.001]  [get_clocks AICLK]
set_max_transition -clock_path [expr 71.4*0.001]  [get_clocks NOCCLK*]
set_max_transition -data_path [expr 200*0.001]  [get_clocks NOCCLK*]
set_max_transition -data_path [expr 200*0.001]  [get_clocks vir_NOCCLK]
set_max_transition -clock_path [expr 50.0*0.001]  [get_clocks OVLCLK]
set_max_transition -data_path [expr 166.5*0.001]  [get_clocks OVLCLK]
#set_max_transition -clock_path [expr 100*0.001]  [get_clocks RFCLK_NOC]
#set_max_transition -data_path [expr 200*0.001]  [get_clocks RFCLK_NOC]
set_max_transition -data_path [expr 200*0.001]  [get_clocks vir_SMNCLK]
set_max_transition -clock_path [expr 100.0*0.001]  [get_clocks ck_feedthru]
set_max_transition -data_path [expr 200*0.001]  [get_clocks ck_feedthru]
set_max_transition -clock_path [expr 100*0.001]  [get_clocks ck_untimed]
set_max_transition -data_path [expr 200*0.001]  [get_clocks ck_untimed]
set_max_transition -data_path [expr 200*0.001]  [get_clocks vir_scan_clock]
set_max_transition -data_path [expr 200*0.001]  [get_clocks vir_tessent_ssn_bus_clock_network]
set_max_transition -clock_path [expr 71.4*0.001]  [get_clocks vir_NOCCLK]
set_max_transition -data_path [expr 200*0.001]  [get_clocks vir_NOCCLK]
set_max_transition -clock_path [expr 100*0.001]  [get_clocks vir_SMNCLK]
set_max_transition -data_path [expr 200*0.001]  [get_clocks vir_SMNCLK]
set_max_transition -clock_path [expr 100*0.001]  [get_clocks vir_scan_clock]
set_max_transition -data_path [expr 200*0.001]  [get_clocks vir_scan_clock]
set_max_transition -clock_path [expr 100*0.001]  [get_clocks vir_tessent_ssn_bus_clock_network]
set_max_transition -data_path [expr 200*0.001]  [get_clocks vir_tessent_ssn_bus_clock_network]



puts "Sourcing global exception file: [info script]"



# flops are characterized up to 300ps clcok slopes and 150ps is the low voltage hard limit so no need to constrain tighter
if {0} {
  set_max_transition [expr 100*0.001]  [all_registers -clock_pins]
}
set_max_fanout 32 [current_design]




# the following are copied from the flows/synth.global_exceptions.tcl
if {[isDC]} {

  if { [info exists tt_pocvm] && $tt_pocvm == 1 && [shell_is_in_topographical_mode]} {
     ### TODO: MW: should these timing derates be set per scenario for mcmm, in setup_mcmm_scenarios.tcl? 
     ### Add guardband to account for clock tree & wire OCV not being calculated in synthesis: 
     set_timing_derate -cell_delay -pocvm_guardband -early 0.97
     set_timing_derate -cell_delay -pocvm_guardband -late 1.03 
  }
}

puts "Done sourcing global exception file: [info script]"


### Start Jungyu Im 20250304
#set cur_instance u_l1part/
#
#if {$DESIGN_NAME eq "tt_t6_l1_partition"} {
#  set cur_instance {}
#  set_max_time_borrow 50 [get_clocks *AICLK*]
#
#  set_max_fanout 1 [all_inputs ]
#
##  if {[isDC]} {
##    user_remove_pathgroups
##    user_create_base_pathgroups true true
##    user_create_hier_depth_pathgroups 1 1000 true
##  }
#
## Set a tighter max-trans in DC, In Innovus use setup.yaml to override it instead
#  if {[isDC]} {
#    set_max_transition [expr 100*0.001]  [current_design]
#  }
#
## pathgroups moved to tt-t6_l1_partition.pathgroups.tcl
#
#}
#
#
#set reset_from [get_pins -quiet ${cur_instance}t6_misc/sync_reset_n/gen_rst_sync_stage_*__sync_dffr/d0nt_dffr/CK]
#if {[sizeof_collection $reset_from] > 0} {
#  set_multicycle_path -end -setup 4 -from $reset_from -to [get_clocks {AICLK vir_AICLK}]
#  set_multicycle_path -end -hold  3 -from $reset_from -to [get_clocks {AICLK vir_AICLK}]
#}
#
#set reset_from [get_pins -quiet ${cur_instance}t6_misc/sync_risc_reset_n/gen_rst_sync_stage_*__sync_dffr/d0nt_dffr/CK]
#if {[sizeof_collection $reset_from] > 0} {
#  set_multicycle_path -end -setup 4 -from $reset_from -to [get_clocks {AICLK vir_AICLK}]
#  set_multicycle_path -end -hold  3 -from $reset_from -to [get_clocks {AICLK vir_AICLK}]
#}
#
#
#set cur_instance {}
#set cur_instance overlay_noc_wrap/overlay_noc_niu_router/overlay_wrapper/
#
#if {$DESIGN_NAME eq "tt_overlay_wrapper"} {
#  set cur_instance {}
#}
##set reset_from [get_pins -quiet clock_reset_ctrl?gen_core_clk_reset_sync_*__core_clk_reset_sync?gen_rst_sync_stage_*__sync_dffr_d0nt_dffr/CK]
##if {[sizeof_collection $reset_from] > 0} {
##  set_multicycle_path -end -setup 6 -from $reset_from  -to [get_clocks {OVLCLK vir_OVLCLK}]
##  set_multicycle_path -end -setup 5 -from $reset_from  -to [get_clocks {OVLCLK vir_OVLCLK}]
##}
#
##set reset_from [get_pins -quiet  ${cur_instance}clock_reset_ctrl?uncore_clk_reset_sync?gen_rst_sync_stage_.*_?sync_dffr_d0nt_dffr/CK]
##if {[sizeof_collection $reset_from] > 0} {
##  set_multicycle_path -end -setup 3 -from $reset_from -to [get_clocks {OVL_UNCORE_CLK}]
##  set_multicycle_path -end -hold  2 -from $reset_from -to [get_clocks {OVL_UNCORE_CLK}]
##}
#
#set reset_from [get_pins -quiet ${cur_instance}clock_reset_ctrl?noc_clk_reset_sync?gen_rst_sync_stage_*_?sync_dffr_d0nt_dffr/CK]
#if {[sizeof_collection $reset_from] > 0} {
#  set_multicycle_path -end -setup 4 -from $reset_from -to [get_clocks {NOCCLK}]
#  set_multicycle_path -end -hold  3 -from $reset_from -to [get_clocks {NOCCLK}]
#}
#
#set reset_from [get_pins -quiet  ${cur_instance}clock_reset_ctrl?ai_clk_reset_sync?gen_rst_sync_stage_*_?sync_dffr_d0nt_dffr/CK]
#if {[sizeof_collection $reset_from] > 0} {
#  set_multicycle_path -end -setup 4 -from $reset_from -to [get_clocks {AICLK}]
#  set_multicycle_path -end -hold  3 -from $reset_from -to [get_clocks {AICLK}]
#}
#
#set smnclk_selects {
#  smn_wrapper?gen_smn_inst_smn_inst?smn_clk_rst_ctrl?i?u?tt_smn_clkdiv?smn_clkmux_stage1?clk0_sel/o_Q
#  smn_wrapper?gen_smn_inst_smn_inst?smn_clk_rst_ctrl?i?u?tt_smn_clkdiv?smn_clkmux_stage1?clk1_sel/o_Q
#  smn_wrapper?gen_smn_inst_smn_inst?smn_clk_rst_ctrl?i?u?tt_smn_clkdiv?smn_clkmux_stage2?clk0_sel/o_Q
#  smn_wrapper?gen_smn_inst_smn_inst?smn_clk_rst_ctrl?i?u?tt_smn_clkdiv?smn_clkmux_stage2?clk1_sel/o_Q
#}
#set smnclk_select_pins [get_pins -quiet -hier *Q -filter full_name=~${cur_instance}[join $smnclk_selects "|| full_name=~${cur_instance}"]]
#if {[sizeof_collection $smnclk_select_pins] > 0} {
#  set_sense -type clock -clocks * -stop_propagation $smnclk_select_pins
#  set select [get_pins -quiet -hier *Q -filter full_name=~${cur_instance}smn_wrapper?gen_smn_inst?smn_inst?smn_clk_rst_ctrl?i?u?tt_smn_clkdiv?smn_clkmux_stage2?clk1_sel/o_Q]
#  if {[sizeof_collection $select] > 0 } {
#    set_multicycle_path -end -hold 1 -from [get_clocks SMNCLK2_ROOT] -through $select -to [get_clocks SMNCLK_ROOT]
#  }
#  set gater [get_pins -quiet -hier *A -filter full_name=~${cur_instance}smn_wrapper?gen_smn_inst?smn_inst?smn_clk_rst_ctrl?i?u?tt_smn_clkdiv?smn_clkmux_stage2?clk_out_nd/i_A]
#  if {[sizeof_collection $gater] > 0 } {
#    set_multicycle_path -end -hold 1 -from [get_clocks NOCCLK] -through $gater -to [get_clocks SMNCLK_ROOT]
#  }
#}
#
#
#
#set cur_instance {}
#set cur_instance overlay_noc_wrap/overlay_noc_niu_router/noc_niu_router_inst/
#
#if {$::DESIGN_NAME eq "tt_noc_niu_router"} {
#  set cur_instance {}
#  set_max_fanout 32 [current_design]
#  set_max_fanout 1 [all_inputs ]
#
#  set top_from_reg [all_registers -clock_pins]
#  set top_to_reg [all_registers -data_pins]
#  set top_mem [filter_collection [get_cells -hierarchical ]  "is_memory_cell==true" ]
#  set clkgates [filter_collection [all_registers] "is_clock_gating_check==true"]
#  set to_reg [remove_from_collection  $top_to_reg [get_pins -of $clkgates -filter "pin_direction=~in"]]
#
#  if {[isDC]} {
#    set_max_transition [expr 100*0.001]  [current_design]
#    set_auto_disable_drc_nets -all
#
##    Disable autogenerated hierarchy-based pathgroups
#    set tt_synth_auto_hier_path_group 0
#
##    Generate collapsed synth reports
#    set tt_synth_common_pnr_reports 1
#
#    #pathgroups moved to tt_noc_niu_router.pathgroups.tcl
#
#  }
#}
### End 20250417



set cur_instance {}
set cur_instance {}

if {$DESIGN_NAME eq "tt_tensix_with_l1"} {
  set cur_instance {}

  set_max_fanout 1 [all_inputs ]

  if {[isDC]} {
    set_max_transition [expr 100*0.001]  [current_design]
  }
  
} 

  


## stop all clocks on the outputs od SMN clk select muxes
#set stop_pin_names {
#  overlay_noc_wrap/overlay_noc_niu_router/overlay_wrapper/smn_wrapper?gen_smn_inst?smn_inst?smn_clk_rst_ctrl?i?u?tt_smn_clkdiv?smn_clkmux_stage2?clk0_sel/o_Q
#  overlay_noc_wrap/overlay_noc_niu_router/overlay_wrapper/smn_wrapper?gen_smn_inst?smn_inst?smn_clk_rst_ctrl?i?u?tt_smn_clkdiv?smn_clkmux_stage2?clk1_sel/o_Q
#  overlay_noc_wrap/overlay_noc_niu_router/overlay_wrapper/smn_wrapper?gen_smn_inst?smn_inst?smn_clk_rst_ctrl?i?u?tt_smn_clkdiv?smn_clkmux_stage1?clk0_sel/o_Q
#  overlay_noc_wrap/overlay_noc_niu_router/overlay_wrapper/smn_wrapper?gen_smn_inst?smn_inst?smn_clk_rst_ctrl?i?u?tt_smn_clkdiv?smn_clkmux_stage1?clk1_sel/o_Q
#}
#set stop_pins_filter [join $stop_pin_names " || full_name=~${cur_instance}"]
#set stop_pins [get_pins -quiet -hier *Q -filter full_name=~${cur_instance}${stop_pins_filter}]
#if {[sizeof_collection $stop_pins] > 0} {
#  set_sense -type clock -clocks * -stop_propagation $stop_pins
#}

#TODO: TEMPORARY, determine a better SMNCLK stamping strategy, need to be able to time SMNCLK ,SMNCLK2 and SMNCLK_NOC from this point
# only allow SMNCLK out of the final SMNCLK mus stage

#set stop_pin_names {
#  overlay_noc_wrap/overlay_noc_niu_router/overlay_wrapper/smn_wrapper?gen_smn_inst?smn_inst?smn_clk_rst_ctrl?i?u?tt_smn_clkdiv?smn_clkmux_stage2?clk_out_nd/o_Y
#}
#set stop_pins_filter [join $stop_pin_names " || full_name=~${cur_instance}"]
#set stop_pins [get_pins -quiet -hier *Y -filter full_name=~${cur_instance}${stop_pins_filter}]
#if {[sizeof_collection $stop_pins] > 0} {
#  set_sense -type clock -clocks {NOCCLK SMNCLK2 SMNCLK_NOC} -stop_propagation $stop_pins
#}

#set reset_from [get_pins -quiet -hier *Q  -filter full_name=~${cur_instance}overlay_noc_wrap/overlay_noc_niu_router/neo_overlay_wrapper/overlay_wrapper/clock_reset_ctrl?gen_core_clk_reset_sync*core_clk_reset_sync?gen_rst_sync_stage*sync_dffr?d0nt_dffr/Q]
#set noc_ovl_reset [get_pins -quiet -hier *noc_niu_router_inst/i_ovl_core_reset_n -filter full_name=~${cur_instance}overlay_noc_wrap/overlay_noc_niu_router/noc_niu_router_inst/i_ovl_core_reset_n]
#if { [sizeof_collection $reset_from] > 0
#  && [sizeof_collection $noc_ovl_reset] > 0
#   } {
#  set_multicycle_path -end -setup 2 -through $reset_from  -through $noc_ovl_reset -to [get_clocks {OVLCLK}]
#  set_multicycle_path -end -hold 1 -through $reset_from  -through $noc_ovl_reset -to [get_clocks {OVLCLK}]
#}

set fp_patterns {
  overlay_noc_wrap/overlay_noc_niu_router/noc_niu_router_inst/i_local_nodeid_x*
  overlay_noc_wrap/overlay_noc_niu_router/noc_niu_router_inst/i_local_nodeid_y*
  overlay_noc_wrap/overlay_noc_niu_router/noc_niu_router_inst/i_local_node_orientation*
  overlay_noc_wrap/overlay_noc_niu_router/noc_niu_router_inst/i_noc_endpoint_*
  overlay_noc_wrap/overlay_noc_niu_router/noc_niu_router_inst/i_mem_sp_cfg_*
  overlay_noc_wrap/overlay_noc_niu_router/noc_niu_router_inst/i_mem_2p_cfg_*
  overlay_noc_wrap/overlay_noc_niu_router/noc_niu_router_inst/i_mesh_start_x*
  overlay_noc_wrap/overlay_noc_niu_router/noc_niu_router_inst/i_mesh_start_y*
  overlay_noc_wrap/overlay_noc_niu_router/noc_niu_router_inst/i_mesh_end_x*
  overlay_noc_wrap/overlay_noc_niu_router/noc_niu_router_inst/i_mesh_end_y*
  overlay_noc_wrap/overlay_noc_niu_router/noc_niu_router_inst/i_noc_*_size*
  overlay_noc_wrap/overlay_noc_niu_router/noc_niu_router_inst/o_mem_shutdown*
}
foreach pat $fp_patterns {
  set fp_pins [get_pins -quiet ${cur_instance}$pat]
  if {[sizeof_collection $fp_pins] > 0} {
    set_false_path -through [get_pins $fp_pins] -to [get_clocks {SMNCLK* NOCCLK*}]
    set_false_path -from [get_clocks {SMNCLK* NOCCLK*}] -through [get_pins $fp_pins]
  }
}



  user_remove_pathgroups *

  user_create_base_pathgroups false true
  foreach {b1 i1 b2 i2} {
    tt_t6_l1_partition       u_l1part                                                    tt_neo_overlay_wrapper   overlay_noc_wrap/overlay_noc_niu_router/neo_overlay_wrapper
    tt_t6_l1_partition       u_l1part                                                    tt_noc_niu_router        overlay_noc_wrap/overlay_noc_niu_router/noc_niu_router_inst
    tt_t6_l1_partition       u_l1part                                                    tt_tensix                t6*neo?u_t6
    tt_neo_overlay_wrapper   overlay_noc_wrap/overlay_noc_niu_router/neo_overlay_wrapper tt_t6_l1_partition       u_l1part
    tt_noc_niu_router        overlay_noc_wrap/overlay_noc_niu_router/noc_niu_router_inst tt_t6_l1_partition       u_l1part
    tt_tensix                t6*neo?u_t6                                                 tt_t6_l1_partition       u_l1part
    tt_neo_overlay_wrapper   overlay_noc_wrap/overlay_noc_niu_router/neo_overlay_wrapper tt_noc_niu_router        overlay_noc_wrap/overlay_noc_niu_router/noc_niu_router_inst
    tt_noc_niu_router        overlay_noc_wrap/overlay_noc_niu_router/noc_niu_router_inst tt_neo_overlay_wrapper   overlay_noc_wrap/overlay_noc_niu_router/neo_overlay_wrapper
    tt_fpu_gtile             t6*neo?u_t6/gen_gtile*u_fpu_gtile                           tt_instrn_engine_wrapper t6*neo?u_t6/instrn_engine_wrapper
    tt_instrn_engine_wrapper t6*neo?u_t6/instrn_engine_wrapper                           tt_fpu_gtile             t6*neo?u_t6/gen_gtile*u_fpu_gtile
  } {
    group_path -name ${b1}.${b2}_intf -from [all_registers -clock_pins] -through [get_pins ${i1}/* -filter direction=~out] -through [get_pins ${i2}/* -filter direction=~in] -to [all_registers -data_pins]
  }


  # CPNR/Innovus: Increase the weight and effort level for user created path-groups, by default tool assigns lower weight/effort level
  if {[isInnovus]} {

    set all_user_cust_pg [get_object_name [remove_from_collection [get_path_groups *] [get_path_groups "*in2reg* *reg2out* *in2out*"]]]
    foreach sin_pg $all_user_cust_pg {
      set_path_group_options [get_object_name [get_path_groups $sin_pg]]  -weight 1 -effort_level high
    }
  }


### Start - Jungyu Im 20250630 : add in/output delay for PRTN feedthrough path
set_case_analysis 0 [get_ports TIEL_DFT_MODESCAN]

set_input_delay   -max -clock [get_clocks "PRTNUN_CLK"]    [expr $::PERIOD_PRTNUN_CLK * 0.40] [get_ports *PRTNUN* -f "direction ==in  && !defined(clocks)"]
set_output_delay  -max -clock [get_clocks "PRTNUN_CLK"]    [expr $::PERIOD_PRTNUN_CLK * 0.40] [get_ports *PRTNUN* -f "direction ==out && !defined(clocks)"]
### End - Jungyu Im
