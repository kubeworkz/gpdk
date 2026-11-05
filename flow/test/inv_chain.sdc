create_clock -name clk -period 10.0 [get_ports clk]
set_input_delay 2.0 -clock clk [get_ports d]
set_output_delay 2.0 -clock clk [get_ports q]
set_load 0.02 [get_ports q]
