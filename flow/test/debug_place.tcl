set platform "flow/vendor/orfs/flow/platforms/nangate45"

read_lef $platform/lef/NangateOpenCellLibrary.tech.lef
read_lef $platform/lef/NangateOpenCellLibrary.macro.mod.lef
read_liberty $platform/lib/NangateOpenCellLibrary_typical.lib
read_verilog flow/test/build/inv_chain_netlist.v
link_design inv_chain
read_sdc flow/test/inv_chain.sdc

initialize_floorplan \
    -die_area {0 0 40 40} \
    -core_area {4 4 36 36} \
    -site FreePDK45_38x28_10R_NP_162NW_34O

make_tracks
set_global_routing_layer_adjustment metal2-metal10 0.3
set_routing_layers -signal metal2-metal10 -clock metal4-metal10
place_pins -hor_layers metal3 -ver_layers metal2
global_placement -density 0.45
detailed_placement
clock_tree_synthesis -buf_list {CLKBUF_X1 BUF_X2} -root_buf CLKBUF_X1
set_propagated_clock [all_clocks]
write_def flow/test/build/inv_chain_placed.def
report_design_area
