// GRX930 structural proxy.
//
// This is NOT the GRX930 RTL and it does not implement RV64IMAC. It is a
// synthesizable placeholder with the same broad composition as the measured
// chip: four 32-bit core slices with register files, ALUs, multipliers and
// control, plus two NPU slices built from 8x8 MAC arrays. It exists so the
// 45 nm and 180 nm library experiments exercise realistic cell mixes and
// routing, not a toy inverter chain.
//
// Scale: roughly 1/40 of the measured 1.35M NAND2-equivalent GRX930, so the
// absolute area is not the chip area. The 10T/9T/7T comparisons are relative.

module grx_mac4 (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [31:0] seed,
    output wire [23:0] sum
);
    reg [7:0]  x0, x1, x2, x3;
    reg [7:0]  y0, y1, y2, y3;
    reg [23:0] acc0, acc1, acc2, acc3;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            x0 <= 8'd0; x1 <= 8'd0; x2 <= 8'd0; x3 <= 8'd0;
            y0 <= 8'd0; y1 <= 8'd0; y2 <= 8'd0; y3 <= 8'd0;
            acc0 <= 24'd0; acc1 <= 24'd0; acc2 <= 24'd0; acc3 <= 24'd0;
        end else begin
            x0 <= seed[7:0];
            x1 <= seed[15:8];
            x2 <= seed[23:16];
            x3 <= seed[31:24];
            y0 <= seed[7:0] ^ 8'h5a;
            y1 <= seed[15:8] ^ 8'h3c;
            y2 <= seed[23:16] ^ 8'h96;
            y3 <= seed[31:24] ^ 8'hc3;
            acc0 <= acc0 + (x0 * y0);
            acc1 <= acc1 + (x1 * y1);
            acc2 <= acc2 + (x2 * y2);
            acc3 <= acc3 + (x3 * y3);
        end
    end

    assign sum = acc0 + acc1 + acc2 + acc3;
endmodule

module grx_npu (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [31:0] seed,
    output wire [23:0] result
);
    wire [23:0] s0, s1, s2, s3;

    grx_mac4 m0 (.clk(clk), .rst_n(rst_n), .seed(seed ^ 32'h0000_0001), .sum(s0));
    grx_mac4 m1 (.clk(clk), .rst_n(rst_n), .seed(seed ^ 32'h0000_0010), .sum(s1));
    grx_mac4 m2 (.clk(clk), .rst_n(rst_n), .seed(seed ^ 32'h0000_0100), .sum(s2));
    grx_mac4 m3 (.clk(clk), .rst_n(rst_n), .seed(seed ^ 32'h0000_1000), .sum(s3));

    assign result = s0 + s1 + s2 + s3;
endmodule

module grx_core (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [31:0] seed,
    output wire [31:0] result,
    output wire        zero
);
    reg [31:0] rf0, rf1, rf2, rf3, rf4, rf5, rf6, rf7;
    reg [31:0] pc;
    reg [31:0] ir;
    reg [31:0] a;
    reg [31:0] b;
    reg [31:0] alu;
    reg [2:0]  ra;
    reg [2:0]  rb;
    reg [2:0]  wa;

    wire [31:0] alu_add = a + b;
    wire [31:0] alu_sub = a - b;
    wire [31:0] alu_and = a & b;
    wire [31:0] alu_or  = a | b;
    wire [31:0] alu_xor = a ^ b;
    wire [31:0] alu_shl = a << b[3:0];
    wire [31:0] alu_shr = a >> b[3:0];
    wire [31:0] alu_mul = a[15:0] * b[15:0];

    always @* begin
        case (ra)
            3'd0: a = rf0; 3'd1: a = rf1;
            3'd2: a = rf2; 3'd3: a = rf3;
            3'd4: a = rf4; 3'd5: a = rf5;
            3'd6: a = rf6; default: a = rf7;
        endcase
    end

    always @* begin
        case (rb)
            3'd0: b = rf0; 3'd1: b = rf1;
            3'd2: b = rf2; 3'd3: b = rf3;
            3'd4: b = rf4; 3'd5: b = rf5;
            3'd6: b = rf6; default: b = rf7;
        endcase
    end

    always @* begin
        case (ir[2:0])
            3'd0: alu = alu_add;
            3'd1: alu = alu_sub;
            3'd2: alu = alu_and;
            3'd3: alu = alu_or;
            3'd4: alu = alu_xor;
            3'd5: alu = alu_shl;
            3'd6: alu = alu_shr;
            default: alu = alu_mul;
        endcase
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rf0 <= 32'd0; rf1 <= 32'd0; rf2 <= 32'd0; rf3 <= 32'd0;
            rf4 <= 32'd0; rf5 <= 32'd0; rf6 <= 32'd0; rf7 <= 32'd0;
            pc  <= 32'd0;
            ir  <= 32'd0;
            ra  <= 3'd0;
            rb  <= 3'd0;
            wa  <= 3'd0;
        end else begin
            pc <= pc + 32'd4;
            ir <= seed ^ {pc[15:0], 16'h9e37};
            ra <= ir[4:2];
            rb <= ir[7:5];
            wa <= ir[10:8];
            case (wa)
                3'd0: rf0 <= alu; 3'd1: rf1 <= alu;
                3'd2: rf2 <= alu; 3'd3: rf3 <= alu;
                3'd4: rf4 <= alu; 3'd5: rf5 <= alu;
                3'd6: rf6 <= alu; default: rf7 <= alu;
            endcase
        end
    end

    assign result = alu;
    assign zero   = (alu == 32'd0);
endmodule

module grx930_proxy (
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

    wire [31:0] c0, c1, c2, c3;
    wire        z0, z1, z2, z3;
    wire [23:0] n0, n1;

    grx_core core0 (.clk(clk), .rst_n(rst_n), .seed(lfsr ^ 32'h0000_0001), .result(c0), .zero(z0));
    grx_core core1 (.clk(clk), .rst_n(rst_n), .seed(lfsr ^ 32'h0000_0010), .result(c1), .zero(z1));
    grx_core core2 (.clk(clk), .rst_n(rst_n), .seed(lfsr ^ 32'h0000_0100), .result(c2), .zero(z2));
    grx_core core3 (.clk(clk), .rst_n(rst_n), .seed(lfsr ^ 32'h0000_1000), .result(c3), .zero(z3));

    grx_npu npu0 (.clk(clk), .rst_n(rst_n), .seed(lfsr ^ 32'h0001_0000), .result(n0));
    grx_npu npu1 (.clk(clk), .rst_n(rst_n), .seed(lfsr ^ 32'h0010_0000), .result(n1));

    assign signature = c0 ^ c1 ^ c2 ^ c3 ^ {8'd0, n0} ^ {8'd0, n1} ^
                       {28'd0, z0, z1, z2, z3};
    assign heartbeat = lfsr[0];
endmodule
