// One-core/one-NPU slice of the GRX930 structural proxy. The full proxy has
// four cores and two NPUs; this slice keeps the same cell mix and clock/reset
// structure at roughly one quarter of the logic, so detailed routing is
// tractable on a single workstation. Absolute area is not GRX930 area.

module grx930_slice (
    input  wire        clk,
    input  wire        rst_n,
    output wire [31:0] signature,
    output wire        heartbeat
);
    reg [31:0] lfsr;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            lfsr <= 32'h1;
        else
            lfsr <= {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
    end

    wire [31:0] c0;
    wire        z0;
    wire [23:0] n0;

    grx_core core0 (.clk(clk), .rst_n(rst_n), .seed(lfsr ^ 32'h0000_0001), .result(c0), .zero(z0));
    grx_npu  npu0  (.clk(clk), .rst_n(rst_n), .seed(lfsr ^ 32'h0001_0000), .result(n0));

    assign signature = c0 ^ {8'd0, n0} ^ {31'd0, z0};
    assign heartbeat = lfsr[0];
endmodule
