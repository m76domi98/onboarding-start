// Author: Michelle Dominic

/*
This module recieves 16 bit spi command from ext controller.
stores decoded valye to 5 config register -> wiered to pwm peripheral
-> used to control output pins
*/

/*
 for my understanding -> how spi works
 1)  controller pulls cs low to say that imma send you sm
 2) controller sneds 16 buts one at a time on the rising sclock edge. one bit eacch time
 3) conroller pulls cs  high to say that im done sending stuff
 4)  decode the 16 bits [read.write but][7 bit address][8 bit data]
 5) if we write to a valid address we store the data byte
*/


`default_nettype none // compiler safety to turn type into error message instead of new wire

module spi_peripheral(
// a module is like a class
// everything between module and endmodule is the hardware inside this block

    // port list — what goes in and out of this module
    // input wire = driven from outside, output reg = we store and drive it outward

    input  wire       clk,
    // 10 mhz system clock, every clocked block ticks on the rising edge
    // clock is driveb extermaly

    input  wire       rst_n,
    // active-low reset — rst_n = 0 means reset NOW, rst_n = 1 means run normally
    // the "n" at the end just means active low (convention in hardware)

    input  wire       spi_cs_n,
    // chip select, active low. controller pulls to 0 to start a transaction
    // when it goes back to 1 the transaction is over

    input  wire       spi_sclk,
    // spi clock from the controller (~100 khz), NOT our system clock
    // asynchronous to our clock so we have to synchronize it first (see stage 1)
    // mode 0: idles low, we sample copi on the rising edge

    input  wire       spi_copi,
    // controller out peripheral in — the controller drives this, we read it
    // one bit comes in per rising sclk edge

    // output wire    spi_cipo,
    // not used — this design is write-only, no data is sent back to the controller

    // the 5 registers we output to the pwm peripheral
    // output reg means we store the value and drive it out

    output reg  [7:0] en_reg_out_7_0,
    // addr 0x00 — enables uo_out[7:0], bit N=1 means pin N is allowed to turn on

    output reg  [7:0] en_reg_out_15_8,
    // addr 0x01 — same thing but for uio_out[7:0] (the upper 8 pins)

    output reg  [7:0] en_reg_pwm_7_0,
    // addr 0x02 — controls whether uo_out[N] gets pwm or just stays static high
    // only matters if the corresponding en_reg_out bit is also 1

    output reg  [7:0] en_reg_pwm_15_8,
    // addr 0x03 — same but for uio_out[7:0]

    output reg  [7:0] pwm_duty_cycle
    // addr 0x04 — duty cycle for all outputs, 0x00=0% 0xFF=100%
);

    // assign spi_cipo = 1'b0;
    // not used — no readback supported, port removed to avoid Verilator PINCONNECTEMPTY warning

    // =========================================================================
    // stage 1 — synchronizers (handling the clock domain crossing)
    //
    // spi signals come from outside and change at random times relative to our
    // 10mhz clock. if we sample them directly our flip flop might capture them
    // mid-transition (between 0 and 1) — this is called metastability and can
    // corrupt the whole design in unpredictable ways
    //
    // fix: run each signal thru 2 flip flops before using it
    //   raw signal → [ff1] → [ff2] → safe to use
    // ff1 might glitch but it has a full clock cycle to settle. by the time ff2
    // samples it its overwhelmingly likely to be a clean 0 or 1
    // =========================================================================

    reg [1:0] sclk_sync;
    // 2 bit reg, one bit per sync stage
    // [0] = first ff (samples raw spi_sclk, might be metastable)
    // [1] = second ff (samples [0], basically guaranteed stable)

    reg [1:0] cs_n_sync;
    // same 2 stage synchronizer for chip select

    reg [1:0] copi_sync;
    // same for the data line

    always @(posedge clk or negedge rst_n) begin
    // runs on every rising clock edge, or immediately if reset goes low

        if (!rst_n) begin
        // reset condition — force everything to known idle values

            sclk_sync <= 2'b00;
            // sclk idles low in mode 0, so reset to 0

            cs_n_sync <= 2'b11;
            // cs is active-low so idle = HIGH = 1, reset looks like "no transaction"

            copi_sync <= 2'b00;
            // no data coming in at reset

        end else begin
        // normal operation — shift each signal one stage forward every clock

            sclk_sync <= {sclk_sync[0], spi_sclk};
            // curly braces = concatenation: build a 2bit value where
            // bit[1] = old stage 0 (moves up), bit[0] = raw input (enters)
            // this is the shift: raw → stage0 → stage1, one step per clock

            cs_n_sync <= {cs_n_sync[0], spi_cs_n};
            // same shift for chip select

            copi_sync <= {copi_sync[0], spi_copi};
            // same for data line
        end
    end

    wire sclk_s = sclk_sync[1];
    // the safe syncd version of sclk — use this everywhere below, never use raw spi_sclk

    wire cs_n_s = cs_n_sync[1];
    // safe syncd chip select

    wire copi_s = copi_sync[1];
    // safe syncd data line

    // =========================================================================
    // stage 2 — edge detection
    //
    // knowing the current value of sclk isnt enough — i need to know the exact
    // moment it changes. for spi mode 0 i sample copi on the RISING edge of sclk.
    //
    // to detect a rising edge i compare current value to what it was last cycle:
    //   rising edge  = its 1 now AND was 0 last cycle (just went 0→1)
    //   falling edge = its 0 now AND was 1 last cycle (just went 1→0)
    //
    // each edge signal is only true for ONE clock cycle per transition
    // =========================================================================

    reg sclk_prev;
    // holds what sclk_s was last clock cycle so i can compare to current

    reg cs_n_prev;
    // same for chip select

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sclk_prev <= 1'b0;
            // sclk idles low so reset to 0

            cs_n_prev <= 1'b1;
            // cs idles high so reset to 1

        end else begin
            sclk_prev <= sclk_s;
            // every cycle: copy current sclk into prev, so next cycle we can compare

            cs_n_prev <= cs_n_s;
            // same for cs
        end
    end

    wire sclk_rising  =  sclk_s && !sclk_prev;
    // true when sclk is 1 now and was 0 last cycle → just went 0→1 (rising edge)
    // this is when we sample copi in mode 0
    // only true for exactly one clock cycle each time sclk rises

    wire cs_n_falling = !cs_n_s &&  cs_n_prev;
    // true when cs is 0 now and was 1 last cycle → controller just started a transaction
    // we use this to reset the shift register at the start of each new frame

    wire cs_n_rising  =  cs_n_s && !cs_n_prev;
    // true when cs is 1 now and was 0 last cycle → transaction just ended
    // this is when we write the decoded data to the register

    // =========================================================================
    // stage 3 — 16 bit shift register + bit counter
    //
    // spi sends bits one at a time msb first. i collect them in a shift register
    // until i have all 16, then decode the complete frame at the end.
    //
    // how the shift works:
    //   on each rising sclk edge, shift left and insert the new bit at position 0
    //   after 16 edges:
    //     [15]   = first bit recieved = r/w flag
    //     [14:8] = next 7 bits        = address
    //     [7:0]  = last 8 bits        = data
    //
    // i had to think abt this a lot — bit 15 ends up being the FIRST bit becuase
    // we shift left each time, pushing older bits toward the msb
    // =========================================================================

    localparam MAX_ADDRESS = 7'h04;
    // named constant for the highest valid register address (like #define in c)
    // 7'h04 = 7 bits wide, hex value 4. valid addrs are 0x00 thru 0x04

    reg [15:0] shift_reg;
    // 16 bit register that collects incoming spi bits one at a time
    // [15:0] = 16 bits, indexed from msb (15) down to lsb (0)

    reg [4:0] bit_count;
    // 5 bit counter tracking how many bits weve received this transaction
    // 5 bits = can hold 0 to 31, we count up to 16

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            shift_reg <= 16'h0;
            // clear shift reg on reset

            bit_count <=  5'h0;
            // reset counter

        end else if (cs_n_falling) begin
        // cs just went low, new transaction starting
        // clear everything so we dont mix old bits with new ones

            shift_reg <= 16'h0;
            bit_count <=  5'h0;

        end else if (sclk_rising && !cs_n_s) begin
        // rising sclk edge AND cs is still low (transaction in progress)
        // controller just put a new bit on copi — sample it

            shift_reg <= {shift_reg[14:0], copi_s};
            // shift left and insert new bit at position [0]
            // {shift_reg[14:0], copi_s} = lower 15 bits shifted up + new bit at bottom
            // the old bit[15] falls off the left edge (intentional)
            //
            // example with 4 bits arriving (A B C D):
            //   start:   0000
            //   after A: 000A
            //   after B: 00AB
            //   after C: 0ABC
            //   after D: ABCD  ← first bit received ends up at the top

            bit_count <= bit_count + 1'b1;
            // 1'b1 = 1 bit value of 1 (avoids width mismatch warnings)
        end
        // if none of the above matched: registers keep their current values
        // verilog regs hold their value until u explicitly change them
    end

    // =========================================================================
    // stage 4 — write to the correct register when the transaction ends
    //
    // when cs goes high (end of transaction) check if the frame was valid.
    // if it passes all 3 checks, write the data byte to the right register.
    //
    // why wait until the end? if i wrote mid-frame id be storing partial data
    //
    // 3 checks:
    //   1. bit_count == 16  → did we get a full 16 bit frame?
    //   2. rw_bit == 1      → was it a write? (reads are ignored)
    //   3. addr <= 0x04     → is it a valid register address?
    // =========================================================================

    wire rw_bit = shift_reg[15];
    // bit 15 = first bit that came in = the r/w flag
    // 1 = write (do smth), 0 = read (ignore)

    wire [6:0] addr = shift_reg[14:8];
    // bits 14 down to 8 = 7 bit address field
    // tells us which register to write to

    wire [7:0] data = shift_reg[7:0];
    // bits 7 down to 0 = 8 bit data field
    // the value the controller wants to store

    wire valid_tx = (bit_count == 5'd16) && rw_bit && (addr <= MAX_ADDRESS);
    // true only if ALL 3 conditions pass (all must be true at the same time)
    // 5'd16 = 5 bit decimal 16
    // if any check fails valid_tx = 0 and nothing gets written

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
        // reset: all registers to safe off state

            en_reg_out_7_0  <= 8'h00;
            // all lower output enables off after reset

            en_reg_out_15_8 <= 8'h00;
            // all upper output enables off

            en_reg_pwm_7_0  <= 8'h00;
            // all lower pwm enables off

            en_reg_pwm_15_8 <= 8'h00;
            // all upper pwm enables off

            pwm_duty_cycle  <= 8'h00;
            // duty cycle = 0% on reset

        end else if (cs_n_rising && valid_tx) begin
        // cs just went high AND the frame was valid — decode addr and write

            case (addr)
            // case = switch statement, checks addr against each value

                7'h00: en_reg_out_7_0  <= data;
                // addr 0x00 → output enable for uo_out[7:0]

                7'h01: en_reg_out_15_8 <= data;
                // addr 0x01 → output enable for uio_out[7:0]

                7'h02: en_reg_pwm_7_0  <= data;
                // addr 0x02 → pwm enable for uo_out[7:0]

                7'h03: en_reg_pwm_15_8 <= data;
                // addr 0x03 → pwm enable for uio_out[7:0]

                7'h04: pwm_duty_cycle  <= data;
                // addr 0x04 → duty cycle register

                default: ;
                // invalid addr → do nothing (shouldnt happen since valid_tx checks this)
            endcase

        end
        // if cs_n_rising=0 or valid_tx=0: all registers stay unchanged
    end

endmodule
// end of spi_peripheral module
