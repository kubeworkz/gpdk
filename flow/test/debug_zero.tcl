set platform "flow/vendor/orfs/flow/platforms/nangate45"
read_lef $platform/lef/NangateOpenCellLibrary.tech.lef
read_lef $platform/lef/NangateOpenCellLibrary.macro.mod.lef
read_liberty $platform/lib/NangateOpenCellLibrary_typical.lib
read_verilog flow/build/nangate45/grx930_proxy_netlist.v
link_design grx930_proxy

set block [ord::get_db_block]
puts "nets: [llength [$block getNets]]"
foreach net [$block getNets] {
    set name [$net getName]
    if {[string match "*zero*" $name] || [string match "*gnd*" $name] || [string match "*vss*" $name]} {
        puts "NET $name type=[$net getSigType]"
        foreach iterm [$net getITerms] {
            puts "  iterm [$iterm getInst] [$iterm getMTerm]"
        }
    }
}
