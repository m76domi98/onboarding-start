/*
 * Copyright (c) 2024 Your Name
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tt_um_uwasic_onboarding_michelle_dominic (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

  assign uio_oe = 8'hFF;  // All bidirectional pins used as outputs

  wire _unused = &{ena, ui_in[7:3], uio_in, 1'b0};

  // Registers written by SPI peripheral, read by PWM peripheral
  wire [7:0] en_reg_out_7_0;
  wire [7:0] en_reg_out_15_8;
  wire [7:0] en_reg_pwm_7_0;
  wire [7:0] en_reg_pwm_15_8;
  wire [7:0] pwm_duty_cycle;

  // SPI peripheral: receives commands and updates the 5 control registers
  spi_peripheral spi_peripheral_inst (
    .clk            (clk),
    .rst_n          (rst_n),
    .spi_sclk       (ui_in[0]),
    .spi_copi       (ui_in[1]),
    .spi_cs_n       (ui_in[2]),
    .spi_cipo       (),           // No readback
    .en_reg_out_7_0 (en_reg_out_7_0),
    .en_reg_out_15_8(en_reg_out_15_8),
    .en_reg_pwm_7_0 (en_reg_pwm_7_0),
    .en_reg_pwm_15_8(en_reg_pwm_15_8),
    .pwm_duty_cycle (pwm_duty_cycle)
  );

  // PWM peripheral: drives 16 output pins based on register values from SPI
  pwm_peripheral pwm_peripheral_inst (
    .clk            (clk),
    .rst_n          (rst_n),
    .en_reg_out_7_0 (en_reg_out_7_0),
    .en_reg_out_15_8(en_reg_out_15_8),
    .en_reg_pwm_7_0 (en_reg_pwm_7_0),
    .en_reg_pwm_15_8(en_reg_pwm_15_8),
    .pwm_duty_cycle (pwm_duty_cycle),
    .out            ({uio_out, uo_out})
  );

endmodule
