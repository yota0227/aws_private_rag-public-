// BOS-AI RTL Parser 테스트용 Verilog 모듈
module BLK_UCIE #(
    parameter DATA_WIDTH = 32,
    parameter ADDR_WIDTH = 8
)(
    input  wire                  clk,
    input  wire                  rst_n,
    input  wire [DATA_WIDTH-1:0] tx_data,
    input  wire                  tx_valid,
    output wire                  tx_ready,
    output wire [DATA_WIDTH-1:0] rx_data,
    output wire                  rx_valid,
    input  wire                  rx_ready
);

    UCIE_PHY u_phy (
        .clk     (clk),
        .rst_n   (rst_n),
        .tx_data (tx_data),
        .tx_valid(tx_valid),
        .tx_ready(tx_ready)
    );

    RX_BUFFER u_rx_buf (
        .clk     (clk),
        .rst_n   (rst_n),
        .rx_data (rx_data),
        .rx_valid(rx_valid),
        .rx_ready(rx_ready)
    );

endmodule
