# Parameterized OpenROAD flow for the GRX930 structural proxy.
#
# Required environment:
#   TECH_LEF, SC_LEF, LIB_FILES (colon-separated), SITE,
#   NETLIST, SDC, OUT_DIR, DESIGN
# Optional:
#   MIN_ROUTING_LAYER, MAX_ROUTING_LAYER, CLOCK_LAYER,
#   IO_H_LAYER, IO_V_LAYER, CTS_BUFS, ROOT_BUF,
#   CORE_UTIL, PLACE_DENSITY

proc env_or {name default} {
    if { [info exists ::env($name)] && $::env($name) ne "" } {
        return $::env($name)
    }
    return $default
}

set tech_lef   $::env(TECH_LEF)
set sc_lef     $::env(SC_LEF)
set lib_files  [split $::env(LIB_FILES) ":"]
set site       $::env(SITE)
set netlist    $::env(NETLIST)
set sdc        $::env(SDC)
set out_dir    $::env(OUT_DIR)
set design     $::env(DESIGN)

set min_layer  [env_or MIN_ROUTING_LAYER metal2]
set max_layer  [env_or MAX_ROUTING_LAYER metal10]
set clk_layer  [env_or CLOCK_LAYER metal4]
set io_h       [env_or IO_H_LAYER metal3]
set io_v       [env_or IO_V_LAYER metal2]
set cts_bufs   [env_or CTS_BUFS "CLKBUF_X1 CLKBUF_X2 BUF_X4"]
set root_buf   [env_or ROOT_BUF "CLKBUF_X1"]
set core_util  [env_or CORE_UTIL 0.42]
set place_den  [env_or PLACE_DENSITY 0.55]
set core_space [env_or CORE_SPACE 10.0]
set time_unit  [env_or TIME_UNIT ns]

file mkdir $out_dir

read_lef $tech_lef
read_lef $sc_lef
foreach lib $lib_files {
    if { $lib ne "" } {
        read_liberty $lib
    }
}
# ASAP7 Liberty is characterized in ps.  Setting the STA unit explicitly keeps
# the SDC period (20.0) in ns instead of being read as 20 ps.  The default ns
# preserves the GF180MCU and NanGate45 runs.
set_units -time $time_unit
read_verilog $netlist
link_design $design
read_sdc $sdc
set_max_fanout [env_or MAX_FANOUT 16] [current_design]

# OpenDB creates an empty "zero_" net for the Verilog constant-0 domain.
# It has no ITerms, but TritonRoute refuses to route a net typed GROUND.
set block [ord::get_db_block]
foreach net [$block getNets] {
    if { [$net getName] eq "zero_" } {
        $net setSigType SIGNAL
    }
}

initialize_floorplan \
    -utilization [expr {$core_util * 100.0}] \
    -aspect_ratio 1.0 \
    -core_space $core_space \
    -site $site

if { [info exists ::env(MAKE_TRACKS_TCL)] && $::env(MAKE_TRACKS_TCL) ne "" } {
    source $::env(MAKE_TRACKS_TCL)
} else {
    make_tracks
}
set_global_routing_layer_adjustment $min_layer-$max_layer 0.30
set_routing_layers -signal $min_layer-$max_layer -clock $clk_layer-$max_layer

place_pins -hor_layers $io_h -ver_layers $io_v

global_placement -density $place_den
detailed_placement
repair_design -verbose
detailed_placement

clock_tree_synthesis -buf_list $cts_bufs -root_buf $root_buf
detailed_placement
set_propagated_clock [all_clocks]

global_route
set drt_args [split [env_or DETAILED_ROUTE_ARGS ""] " "]
detailed_route -output_drc $out_dir/route_drc.rpt -verbose 1 {*}$drt_args

report_design_area
report_wns
report_tns
report_power
report_wire_length -summary
report_checks -path_delay max -group_count 1
write_def $out_dir/final.def
write_verilog $out_dir/final.v
