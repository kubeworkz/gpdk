module inv_chain (
    input  wire clk,
    input  wire d,
    output wire q
);
    reg [7:0] r;
    always @(posedge clk)
        r <= {r[6:0], d};
    assign q = ~r[7];
endmodule
