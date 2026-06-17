// Author: Michelle Dominic

/*
This module recieves 16 bit spi command from ext controller.
stores decoded valye to 5 config register -> wiered to pwm peripheral
-> used to control output pins
*/2][]

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
// Everything between "module" and "endmodule" is the hardware inside this block.

    // below is a port list which signals what goes in and out of this module
    /*
    input wires are signals that go in which is conr=trolled by the instaitinter
    output reg is a signal that sstored in memory and output wire is the combo logic w/out the memory
    */

    input  wire       clk,
    // The 10 MHz system clock. Every clocked block in this module ticks on its rising edge.
    // clock is driveb extermaly

    input  wire       rst_n,
    // Active-low reset. rst_n = 0 means "reset right now". rst_n = 1 means "run normally".
    // The "n" suffix is a hardware convention for active-low signals (the bar over reset in schematics).

    input  wire       spi_cs_n,
    // Chip Select, active low. Controller pulls this to 0 to start talking to us.
    // While spi_cs_n = 0, a transaction is happening. When it goes back to 1, we're done.

    input  wire       spi_sclk,
    // The SPI clock driven by the controller (~100 kHz). NOT the same as our system clock.
    // It's asynchronous so it must be synchronized first.
    // In SPI Mode 0: clock idles LOW, and we sample COPI on the RISING edge.

    input  wire       spi_copi,
    // COPI = Controller Out, Peripheral In.
    // The controller drives this wire. We read one bit from it on each rising SCLK edge.
    // "Controller Out" from the controller's side, "Peripheral In" from our side → INPUT.

    output wire       spi_cipo,
    // CIPO = Controller In, Peripheral Out.
    // We would drive this if we supported reads. We don't, so we tie it to 0 below.
    // Still declared as a port so it isn't left "floating"

    // -- The 5 registers this module controls --
    // "output reg [7:0]"= 8-bit register that this module drives outward.
    // The PWM peripheral reads all 5 of these to decide what to do with the output pins.

    output reg  [7:0] en_reg_out_7_0,
    // Written by SPI address 0x00. Each bit enables one of uo_out[7:0].
    // Bit N = 1 → output pin N is active. Bit N = 0 → output pin N is forced low.

    output reg  [7:0] en_reg_out_15_8,
    // Written by SPI address 0x01. Same idea for uio_out[7:0] (the upper 8 output pins).

    output reg  [7:0] en_reg_pwm_7_0,
    // Written by SPI address 0x02. Each bit controls whether uo_out[N] gets PWM or static high.
    // Only has effect when the corresponding en_reg_out bit is also 1.

    output reg  [7:0] en_reg_pwm_15_8,
    // Written by SPI address 0x03. Same idea for uio_out[7:0].

    output reg  [7:0] pwm_duty_cycle
    // Written by SPI address 0x04. Controls PWM duty cycle for all outputs.
    // 0x00 = 0%, 0xFF = 100%. Formula: (value / 256) * 100%.
);

    // =========================================================================
    // Tie CIPO permanently to 0 cus  we never send data back to the controller.
    // =========================================================================
    assign spi_cipo = 1'b0;
    // "assign" makes a permanent combinational (not clocked) connection.
    // Like soldering this wire directly to ground.
    // 1'b0 means: a number that is 1 bit wide, in binary, with value 0.

    // =========================================================================
    // STAGE 1 — Clock Domain Crossing (CDC): 2-Stage Synchronizers
    //
    // WHY THIS EXISTS:
    //   spi_sclk, spi_cs_n, and spi_copi come from an external controller.
    //   They change at times that have nothing to do with our 10 MHz clock.
    //   If our flip-flop captures one of these signals exactly while it's
    //   mid-transition (0→1 or 1→0), the flip-flop can get "stuck" at a
    //   voltage between 0 and 1. This is called METASTABILITY. It can then
    //   propagate and corrupt your whole design unpredictably.
    //
    // THE FIX — run each signal through TWO flip-flops in series:
    //   raw signal → [Flip-Flop 1] → [Flip-Flop 2] → safe to use
    //
    //   FF1 might go metastable, but it resolves within one clock period.
    //   By the time FF2 samples it, the voltage is a clean 0 or 1.
    //   This reduces metastability probability to near-zero.
    // =========================================================================

    reg [1:0] sclk_sync;
    // A 2-bit register holding both stages of the SCLK synchronizer.
    // sclk_sync[0] = first flip-flop  (samples raw spi_sclk — might be metastable)
    // sclk_sync[1] = second flip-flop (samples [0] — overwhelmingly stable)
    // [1:0] means the register is 2 bits wide, indexed from bit 1 down to bit 0.

    reg [1:0] cs_n_sync;
    // Same 2-stage synchronizer structure, for chip select (spi_cs_n).

    reg [1:0] copi_sync;
    // Same 2-stage synchronizer structure, for the data line (spi_copi).

    always @(posedge clk or negedge rst_n) begin
    // This block runs when:
    //   posedge clk   = clock just rose (0→1) — normal operation tick
    //   negedge rst_n = reset just fell (1→0) — async reset, takes effect immediately

        if (!rst_n) begin
        // !rst_n means "if rst_n is 0" (the ! flips 0→1 and 1→0, so !0 = 1 = true).
        // This is the reset condition. Force everything to known safe idle values.

            sclk_sync <= 2'b00;
            // 2'b00 = 2-bit binary 00. Both sync stages → 0.
            // SCLK idles low in SPI Mode 0, so 0 is the correct reset state.

            cs_n_sync <= 2'b11;
            // 2'b11 = 2-bit binary 11. Both sync stages → 1.
            // CS is active-low, so idle (not selected) = HIGH = 1. Reset looks like "idle."

            copi_sync <= 2'b00;
            // Both stages → 0. No transaction is happening at reset, so data line = 0.

        end else begin
        // Reset is not active. On every clock rising edge, shift each signal one step forward.

            sclk_sync <= {sclk_sync[0], spi_sclk};
            // Right side builds a 2-bit value using curly-brace concatenation:
            //   bit[1] = sclk_sync[0]  (old stage-0 value moves up to stage-1)
            //   bit[0] = spi_sclk      (raw input enters at stage-0)
            // This is the shift: raw → stage0 → stage1, advancing one step per clock.

            cs_n_sync <= {cs_n_sync[0], spi_cs_n};
            // Same shift for chip select.

            copi_sync <= {copi_sync[0], spi_copi};
            // Same shift for the data line.
        end
    end

    wire sclk_s = sclk_sync[1];
    // Give the stable second-stage output a short, readable name.
    // "sclk_s" = SCLK synchronized. Use this everywhere — never use raw spi_sclk below this line.

    wire cs_n_s = cs_n_sync[1];
    // Stable synchronized chip select. Use this instead of raw spi_cs_n.

    wire copi_s = copi_sync[1];
    // Stable synchronized data line. Use this instead of raw spi_copi.

    // =========================================================================
    // STAGE 2 — Edge Detection
    //
    // WHY THIS EXISTS:
    //   Knowing the current value of a signal isn't enough — we need to know
    //   WHEN it changes. For example, we want to sample COPI only right when
    //   SCLK transitions from 0 to 1 (rising edge). To detect that transition,
    //   we compare the current value to what it was one clock cycle ago.
    //
    //   Rising edge  = it's 1 now AND was 0 last cycle → it just went 0→1
    //   Falling edge = it's 0 now AND was 1 last cycle → it just went 1→0
    //
    //   The resulting edge signals are only TRUE for ONE clock cycle each time.
    // =========================================================================

    reg sclk_prev;
    // Holds what sclk_s was on the PREVIOUS clock cycle.
    // By comparing sclk_s (current) to sclk_prev (previous), we detect transitions.

    reg cs_n_prev;
    // Holds what cs_n_s was on the PREVIOUS clock cycle.

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sclk_prev <= 1'b0;
            // 1'b0 = 1-bit binary 0. Reset: SCLK was low (correct Mode 0 idle state).

            cs_n_prev <= 1'b1;
            // 1'b1 = 1-bit binary 1. Reset: CS was high (correct idle = not selected).

        end else begin
            sclk_prev <= sclk_s;
            // Every clock cycle: copy the current synchronized SCLK into sclk_prev.
            // Next cycle, sclk_prev will hold "what sclk_s was this cycle."

            cs_n_prev <= cs_n_s;
            // Same — copy current CS so next cycle we can compare to detect a transition.
        end
    end

    wire sclk_rising  =  sclk_s && !sclk_prev;
    // TRUE when: sclk_s is currently 1 AND sclk_prev was 0 last cycle → SCLK just went 0→1.
    // This is the RISING EDGE of SCLK. In SPI Mode 0, this is when we sample COPI.
    // This wire is only HIGH for exactly one clock cycle each time SCLK rises.

    wire cs_n_falling = !cs_n_s &&  cs_n_prev;
    // TRUE when: cs_n_s is currently 0 AND cs_n_prev was 1 last cycle → CS just went 1→0.
    // CS falling = the controller just started a new transaction. Reset our shift register.
    // !cs_n_s = NOT cs_n_s. Since CS is active-low, "0" means "active," so !0 = 1 = true.

    wire cs_n_rising  =  cs_n_s && !cs_n_prev;
    // TRUE when: cs_n_s is currently 1 AND cs_n_prev was 0 last cycle → CS just went 0→1.
    // CS rising = the controller just finished the transaction. Time to write to the register.

    // =========================================================================
    // STAGE 3 — 16-bit Shift Register + Bit Counter
    //
    // WHY THIS EXISTS:
    //   SPI sends bits one at a time. We accumulate them in a shift register until
    //   we have all 16, then decode the complete frame.
    //
    // HOW SHIFTING WORKS:
    //   Bits arrive MSB (most significant bit) first.
    //   On each rising SCLK edge, we shift the register LEFT by 1 and insert
    //   the new bit at the rightmost position (bit 0).
    //
    //   After 16 edges, the register holds:
    //     [15]    = first bit received  = R/W flag (1=write, 0=read)
    //     [14:8]  = next 7 bits         = address (which register to write)
    //     [7:0]   = last 8 bits         = data (what value to write)
    //
    //   bit_count tracks how many bits we've received so we know when we're done.
    // =========================================================================

    localparam MAX_ADDRESS = 7'h04;
    // localparam defines a named constant (like #define in C, or const in Python).
    // 7'h04 = a number that is 7 bits wide, in hexadecimal, with value 4.
    // Valid register addresses are 0x00 through 0x04 (5 registers total).
    // Using a name instead of a raw "4" makes the code easier to read and update.

    reg [15:0] shift_reg;
    // A 16-bit register. Accumulates incoming SPI bits one at a time.
    // [15:0] means 16 bits wide, indexed from bit 15 (MSB) down to bit 0 (LSB).

    reg [4:0] bit_count;
    // A 5-bit counter that tracks how many bits we've received this transaction.
    // [4:0] = 5 bits wide, can hold values 0 through 31. We count up to 16.

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            shift_reg <= 16'h0;
            // 16'h0 = 16-bit hex value 0. Clear the shift register on reset.

            bit_count <=  5'h0;
            // 5'h0 = 5-bit hex value 0. Reset the counter on reset.

        end else if (cs_n_falling) begin
        // CS just went low → a new transaction is starting.
        // Reset everything so we don't mix old bits from a previous transaction with new ones.

            shift_reg <= 16'h0;
            // Clear the shift register — start fresh for the incoming frame.

            bit_count <=  5'h0;
            // Reset the counter — 0 bits received so far in this new transaction.

        end else if (sclk_rising && !cs_n_s) begin
        // SCLK just had a rising edge, AND CS is still low (transaction is in progress).
        // The controller just placed a new bit on COPI — sample it now.
        // "!cs_n_s" = "CS is currently active (low)" — ensures we only sample during a transaction.

            shift_reg <= {shift_reg[14:0], copi_s};
            // Shift the register left by 1 and insert the new bit at position [0].
            //
            // {shift_reg[14:0], copi_s} breaks down as:
            //   shift_reg[14:0] = bits 14 down to 0 (the lower 15 bits of the old value)
            //   copi_s          = the 1 new bit we just received
            //   Together: a 16-bit value with old bits shifted left, new bit on the right.
            //
            // The old bit[15] is lost (shifted off the left edge) — that's intentional.
            //
            // Trace example (showing last 4 bits received: A, B, C, D):
            //   Start:    0000_0000_0000_0000
            //   After A:  0000_0000_0000_000A
            //   After B:  0000_0000_0000_00AB
            //   After C:  0000_0000_0000_0ABC
            //   After D:  0000_0000_0000_ABCD
            //   (continues for all 16 bits)

            bit_count <= bit_count + 1'b1;
            // Increment the bit counter. 1'b1 = 1-bit value of 1 (avoids width warnings).
            // After 16 increments, bit_count == 16 and we know the frame is complete.
        end
        // If none of the above matched: shift_reg and bit_count keep their current values.
        // Verilog registers hold their last value until explicitly changed — no decay.
    end

    // =========================================================================
    // STAGE 4 — Register Write on Transaction End
    //
    // WHY THIS EXISTS:
    //   Once CS goes high (transaction over), we check if what we received was
    //   valid. If it passes all checks, we write the data byte to the correct
    //   one of our 5 output registers. We wait for the end of the transaction
    //   (not mid-way) to avoid writing partial/corrupted data.
    //
    // THREE CHECKS before writing:
    //   1. bit_count == 16  → Did we receive exactly 16 bits? (complete frame)
    //   2. rw_bit == 1      → Was it a write command? (not a read, which we ignore)
    //   3. addr <= 0x04     → Is the address one of our 5 valid registers?
    // =========================================================================

    wire rw_bit = shift_reg[15];
    // Extract just bit 15 from the completed shift register.
    // This is the FIRST bit that was clocked in, which is the R/W flag.
    // 1 = write (do something), 0 = read (ignore — we don't support reads).

    wire [6:0] addr = shift_reg[14:8];
    // Extract bits 14 down to 8 — a 7-bit slice — which is the address field.
    // [6:0] on the left declares this wire is 7 bits wide.
    // The address tells us which of our 5 registers to write to.

    wire [7:0] data = shift_reg[7:0];
    // Extract bits 7 down to 0 — the 8-bit data field.
    // This is the value the controller wants to store in the register.

    wire valid_tx = (bit_count == 5'd16) && rw_bit && (addr <= MAX_ADDRESS);
    // A single 1-bit wire that is 1 (true) only if ALL three conditions are met.
    // Uses "&&" (logical AND) — all must be true simultaneously.
    //
    // (bit_count == 5'd16)  → 5'd16 = 5-bit decimal 16. Were exactly 16 bits received?
    // rw_bit                → Was the R/W bit = 1 (write)?
    // (addr <= MAX_ADDRESS) → Is the address 0x00, 0x01, 0x02, 0x03, or 0x04?
    //
    // If any check fails, valid_tx = 0 and no register gets written.

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
        // Reset: put all registers into their default (safe/off) states.

            en_reg_out_7_0  <= 8'h00;
            // 8'h00 = 8-bit hex 0. All lower output-enables OFF (no outputs active after reset).

            en_reg_out_15_8 <= 8'h00;
            // All upper output-enables OFF.

            en_reg_pwm_7_0  <= 8'h00;
            // All lower PWM-enables OFF.

            en_reg_pwm_15_8 <= 8'h00;
            // All upper PWM-enables OFF.

            pwm_duty_cycle  <= 8'h00;
            // Duty cycle = 0% (outputs stay low even if enable bits are set).

        end else if (cs_n_rising && valid_tx) begin
        // CS just went high (transaction ended) AND valid_tx passed all 3 checks.
        // Decode the address and write data to the matching register.

            case (addr)
            // "case" works like a switch statement.
            // It checks "addr" against each listed value and runs the matching line.

                7'h00: en_reg_out_7_0  <= data;
                // addr == 0x00 → write data into the output-enable register for uo_out[7:0].

                7'h01: en_reg_out_15_8 <= data;
                // addr == 0x01 → write data into the output-enable register for uio_out[7:0].

                7'h02: en_reg_pwm_7_0  <= data;
                // addr == 0x02 → write data into the PWM-enable register for uo_out[7:0].

                7'h03: en_reg_pwm_15_8 <= data;
                // addr == 0x03 → write data into the PWM-enable register for uio_out[7:0].

                7'h04: pwm_duty_cycle  <= data;
                // addr == 0x04 → write data into the duty cycle register.

                default: ;
                // No matching address → do nothing. Semicolon = empty statement.
                // valid_tx already ensures addr <= 0x04, so this is purely defensive.
            endcase

        end
        // If cs_n_rising = 0 or valid_tx = 0: all registers hold their current values unchanged.
    end

endmodule
// Closes the module definition opened at the top with "module spi_peripheral(".
