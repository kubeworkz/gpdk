set period 20.0
if { [info exists ::env(CLK_PERIOD)] && $::env(CLK_PERIOD) ne "" } {
    set period $::env(CLK_PERIOD)
}
set io_delay 2.0
if { [info exists ::env(IO_DELAY)] && $::env(IO_DELAY) ne "" } {
    set io_delay $::env(IO_DELAY)
}
create_clock -name clk -period $period [get_ports clk]
set_input_delay $io_delay -clock clk [get_ports rst_n]
set_output_delay $io_delay -clock clk [get_ports {signature[*] heartbeat}]
