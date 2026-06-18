# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.triggers import ClockCycles
from cocotb.types import Logic
from cocotb.types import LogicArray

async def await_half_sclk(dut):
    """Wait for the SCLK signal to go high or low."""
    start_time = cocotb.utils.get_sim_time(units="ns")
    while True:
        await ClockCycles(dut.clk, 1)
        # Wait for half of the SCLK period (10 us)
        if (start_time + 100*100*0.5) < cocotb.utils.get_sim_time(units="ns"):
            break
    return

def ui_in_logicarray(ncs, bit, sclk):
    """Setup the ui_in value as a LogicArray."""
    return LogicArray(f"00000{ncs}{bit}{sclk}")

async def send_spi_transaction(dut, r_w, address, data):
    """
    Send an SPI transaction with format:
    - 1 bit for Read/Write
    - 7 bits for address
    - 8 bits for data
    
    Parameters:
    - r_w: boolean, True for write, False for read
    - address: int, 7-bit address (0-127)
    - data: LogicArray or int, 8-bit data
    """
    # Convert data to int if it's a LogicArray
    if isinstance(data, LogicArray):
        data_int = int(data)
    else:
        data_int = data
    # Validate inputs
    if address < 0 or address > 127:
        raise ValueError("Address must be 7-bit (0-127)")
    if data_int < 0 or data_int > 255:
        raise ValueError("Data must be 8-bit (0-255)")
    # Combine RW and address into first byte
    first_byte = (int(r_w) << 7) | address
    # Start transaction - pull CS low
    sclk = 0
    ncs = 0
    bit = 0
    # Set initial state with CS low
    dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
    await ClockCycles(dut.clk, 1)
    # Send first byte (RW + Address)
    for i in range(8):
        bit = (first_byte >> (7-i)) & 0x1
        # SCLK low, set COPI
        sclk = 0
        dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
        await await_half_sclk(dut)
        # SCLK high, keep COPI
        sclk = 1
        dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
        await await_half_sclk(dut)
    # Send second byte (Data)
    for i in range(8):
        bit = (data_int >> (7-i)) & 0x1
        # SCLK low, set COPI
        sclk = 0
        dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
        await await_half_sclk(dut)
        # SCLK high, keep COPI
        sclk = 1
        dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
        await await_half_sclk(dut)
    # End transaction - return CS high
    sclk = 0
    ncs = 1
    bit = 0
    dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
    await ClockCycles(dut.clk, 600)
    return ui_in_logicarray(ncs, bit, sclk)

@cocotb.test()
async def test_spi(dut):
    dut._log.info("Start SPI test")

    # Set the clock period to 100 ns (10 MHz)
    clock = Clock(dut.clk, 100, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut._log.info("Reset")
    dut.ena.value = 1
    ncs = 1
    bit = 0
    sclk = 0
    dut.ui_in.value = ui_in_logicarray(ncs, bit, sclk)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)

    dut._log.info("Test project behavior")
    dut._log.info("Write transaction, address 0x00, data 0xF0")
    ui_in_val = await send_spi_transaction(dut, 1, 0x00, 0xF0)  # Write transaction
    assert dut.uo_out.value == 0xF0, f"Expected 0xF0, got {dut.uo_out.value}"
    await ClockCycles(dut.clk, 1000) 

    dut._log.info("Write transaction, address 0x01, data 0xCC")
    ui_in_val = await send_spi_transaction(dut, 1, 0x01, 0xCC)  # Write transaction
    assert dut.uio_out.value == 0xCC, f"Expected 0xCC, got {dut.uio_out.value}"
    await ClockCycles(dut.clk, 100)

    dut._log.info("Write transaction, address 0x30 (invalid), data 0xAA")
    ui_in_val = await send_spi_transaction(dut, 1, 0x30, 0xAA)
    await ClockCycles(dut.clk, 100)

    dut._log.info("Read transaction (invalid), address 0x00, data 0xBE")
    ui_in_val = await send_spi_transaction(dut, 0, 0x30, 0xBE)
    assert dut.uo_out.value == 0xF0, f"Expected 0xF0, got {dut.uo_out.value}"
    await ClockCycles(dut.clk, 100)
    
    dut._log.info("Read transaction (invalid), address 0x41 (invalid), data 0xEF")
    ui_in_val = await send_spi_transaction(dut, 0, 0x41, 0xEF)
    await ClockCycles(dut.clk, 100)

    dut._log.info("Write transaction, address 0x02, data 0xFF")
    ui_in_val = await send_spi_transaction(dut, 1, 0x02, 0xFF)  # Write transaction
    await ClockCycles(dut.clk, 100)

    dut._log.info("Write transaction, address 0x04, data 0xCF")
    ui_in_val = await send_spi_transaction(dut, 1, 0x04, 0xCF)  # Write transaction
    await ClockCycles(dut.clk, 30000)

    dut._log.info("Write transaction, address 0x04, data 0xFF")
    ui_in_val = await send_spi_transaction(dut, 1, 0x04, 0xFF)  # Write transaction
    await ClockCycles(dut.clk, 30000)

    dut._log.info("Write transaction, address 0x04, data 0x00")
    ui_in_val = await send_spi_transaction(dut, 1, 0x04, 0x00)  # Write transaction
    await ClockCycles(dut.clk, 30000)

    dut._log.info("Write transaction, address 0x04, data 0x01")
    ui_in_val = await send_spi_transaction(dut, 1, 0x04, 0x01)  # Write transaction
    await ClockCycles(dut.clk, 30000)

    dut._log.info("SPI test completed successfully")

@cocotb.test()
async def test_pwm_freq(dut):
    dut._log.info("Start PWM frequency test")

    # =========================================================================
    # SECTION 1 — Setup
    #
    # so before u can see any output toggling, 3 things need to be configured:
    #   1. output enable (addr 0x00) — tells the pin its allowed to turn on
    #   2. pwm mode enable (addr 0x02) — makes it actually toggle instead of
    #      sitting static high (i didnt know u needed both at first, tripped me up)
    #   3. duty cycle (addr 0x04) — has to be nonzero or theres nothing to toggle
    #
    # im using 50% duty cycle (0x80) cus we only care about the PERIOD here,
    # not how long its high vs low. 50% is also the easiest to read in gtkwave
    # if smth goes wrong
    # =========================================================================

    # 10 mhz clock — 100ns per cycle, same as the real chip
    clock = Clock(dut.clk, 100, units="ns")
    cocotb.start_soon(clock.start())

    # hold reset for a few cycles so all the registers start cleared to 0x00
    # if u skip reset the regs might have garbage values from previous tests
    dut.ena.value = 1
    dut.ui_in.value = ui_in_logicarray(1, 0, 0)  # CS high while resetting
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)

    # addr 0x00 — turn on uo_out[7:0] by writing 0xFF
    # we only actualy measure bit 0 but enabling all 8 doesnt hurt anything
    await send_spi_transaction(dut, 1, 0x00, 0xFF)

    # addr 0x02 — enable pwm mode on uo_out[7:0]
    # without this the output just stays HIGH forever, no toggling at all
    await send_spi_transaction(dut, 1, 0x02, 0xFF)

    # addr 0x04 — set duty cycle to 50% (0x80 = 128/256 = 50%)
    await send_spi_transaction(dut, 1, 0x04, 0x80)

    # =========================================================================
    # SECTION 2 — Measure
    #
    # the way to measure freqency is:
    #   wait for a rising edge on uo_out[0] → record the time
    #   wait for the NEXT rising edge        → record the time again
    #   the differnce betwen those two times = one full period
    #   then frequency = 1 / period
    #
    # to detect a rising edge in software i just poll the pin every clock cycle
    # and check if it was 0 last time and is 1 now (0→1 transition)
    #
    # expected period from the hardware (from pwm_peripheral.v):
    #   clk_div_trig = 12, so pwm_counter ticks every (12+1) = 13 system clocks
    #   pwm_counter is 8 bit so it wraps every 256 counts
    #   one full period = 13 * 256 = 3328 clocks = 332800 ns = ~3004.8 hz
    # =========================================================================

    # grab bit 0 of uo_out as the baseline to compare agianst
    # "& 0x1" masks off everything except bit 0
    prev = int(dut.uo_out.value) & 0x1

    # loop until we catch the first 0→1 transition on uo_out[0]
    while True:
        await ClockCycles(dut.clk, 1)
        curr = int(dut.uo_out.value) & 0x1
        if prev == 0 and curr == 1:   # was 0, now its 1 — thats a rising edge!
            break
        prev = curr

    t1 = cocotb.utils.get_sim_time(units="ns")
    dut._log.info(f"First rising edge at {t1} ns")

    # wait for the second rising edge
    # important: set prev = curr (which is 1 rn) so the loop doesnt
    # immediately trigger again — it has to wait for the pin to fall to 0 first
    prev = curr
    while True:
        await ClockCycles(dut.clk, 1)
        curr = int(dut.uo_out.value) & 0x1
        if prev == 0 and curr == 1:
            break
        prev = curr

    t2 = cocotb.utils.get_sim_time(units="ns")
    dut._log.info(f"Second rising edge at {t2} ns")

    # period = time betwen the two rising edges (in nanoseconds)
    # to get hz from ns: freq = 1 / (period_ns * 1e-9) = 1e9 / period_ns
    period_ns = t2 - t1
    freq_hz = 1e9 / period_ns
    dut._log.info(f"Measured period: {period_ns:.0f} ns  →  frequency: {freq_hz:.2f} Hz")

    # =========================================================================
    # SECTION 3 — Assert
    #
    # spec says pwm should run at 3khz with +-1% tolerence
    # 1% of 3000 = 30 so the acceptable range is 2970 to 3030 hz
    # our hardware gives ~3004.8 hz which is only 0.16% off so it should pass ez
    #
    # if this assert fires, first thing to do is open tb.vcd in gtkwave and
    # check if uo_out[0] is even toggling — if its stuck the enables are prob wrong
    # =========================================================================

    assert 2970 <= freq_hz <= 3030, (
        f"PWM frequency out of range: expected 2970–3030 Hz, got {freq_hz:.2f} Hz"
    )

    dut._log.info("PWM frequency test completed successfully")


@cocotb.test()
async def test_pwm_duty(dut):
    dut._log.info("Start PWM duty cycle test")

    # =========================================================================
    # SECTION 1 — Setup
    #
    # same setup as test_pwm_freq: clock, reset, then configure the two enable
    # registers so the output pin is in pwm mode.
    # we dont write the duty cycle reg here on purpose — we'll try a few
    # diffrent values in section 2 to test each one seperately
    # =========================================================================

    clock = Clock(dut.clk, 100, units="ns")
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = ui_in_logicarray(1, 0, 0)  # CS high while reseting
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)

    # addr 0x00 — enable uo_out[7:0] outputs
    # if this isnt set the pin just stays 0 no matter what u write to the other regs
    await send_spi_transaction(dut, 1, 0x00, 0xFF)

    # addr 0x02 — enable pwm mode on uo_out[7:0]
    # without this the output ignores the duty cycle reg and stays static high
    await send_spi_transaction(dut, 1, 0x02, 0xFF)

    # =========================================================================
    # SECTION 2 — Measure
    #
    # for "normal" duty cycles (not 0% or 100%) i use 3 edge detections:
    #
    #   step A: find rising edge  (0→1) → t_rise1, start of the high phase
    #   step B: find falling edge (1→0) → t_fall,  end of the high phase
    #   step C: find next rising  (0→1) → t_rise2, one full period done
    #
    #   high_time = t_fall  - t_rise1    (how long the pin was HIGH)
    #   period    = t_rise2 - t_rise1    (total length of one pwm cycle)
    #   duty %    = (high_time / period) * 100
    #
    # for 0% and 100% edge cases the pin doesnt ever toggle so the loop above
    # would run forever. instead we just wait 2 full pwm periods and check
    # that the pin is stuck at the right constant value
    # =========================================================================

    results = []  # store (measured, expected, label) — assert all at the end

    # testing 25% (0x40 = 64/256 = 25%) and 50% (0x80 = 128/256 = 50%)
    for reg_val, expected_pct in [(0x40, 25.0), (0x80, 50.0)]:

        await send_spi_transaction(dut, 1, 0x04, reg_val)

        # STEP A — scan for a rising edge (0→1) on uo_out[0]
        prev = int(dut.uo_out.value) & 0x1
        while True:
            await ClockCycles(dut.clk, 1)
            curr = int(dut.uo_out.value) & 0x1
            if prev == 0 and curr == 1:  # 0→1 transition = rising edge
                break
            prev = curr
        t_rise1 = cocotb.utils.get_sim_time(units="ns")

        # STEP B — scan for the falling edge (1→0)
        # prev = curr here which is 1, so we wait for it to drop back to 0
        prev = curr
        while True:
            await ClockCycles(dut.clk, 1)
            curr = int(dut.uo_out.value) & 0x1
            if prev == 1 and curr == 0:  # 1→0 transition = falling edge
                break
            prev = curr
        t_fall = cocotb.utils.get_sim_time(units="ns")

        # STEP C — scan for the next rising edge to close out one full period
        prev = curr
        while True:
            await ClockCycles(dut.clk, 1)
            curr = int(dut.uo_out.value) & 0x1
            if prev == 0 and curr == 1:
                break
            prev = curr
        t_rise2 = cocotb.utils.get_sim_time(units="ns")

        high_time = t_fall  - t_rise1
        period    = t_rise2 - t_rise1
        measured  = (high_time / period) * 100
        dut._log.info(
            f"{hex(reg_val)}: high={high_time:.0f} ns, "
            f"period={period:.0f} ns, duty={measured:.2f}%"
        )
        results.append((measured, expected_pct, hex(reg_val)))

    # --- edge case: 0% duty cycle (0x00) ---
    # in the rtl: pwm_signal = (pwm_counter < 0)
    # pwm_counter is unsigned so it can never be less than 0, always false
    # so the output should be stuck LOW the whole time
    await send_spi_transaction(dut, 1, 0x04, 0x00)
    await ClockCycles(dut.clk, 2 * 3328)   # wait 2 full pwm periods just to be safe
    stuck_low = (int(dut.uo_out.value) & 0x1) == 0
    dut._log.info(f"0x00: pin is {'LOW — correct' if stuck_low else 'HIGH — WRONG'}")

    # --- edge case: 100% duty cycle (0xFF) ---
    # the rtl has a hardcoded special case: if pwm_duty_cycle == 0xFF force output = 1
    # this is needed becasue without it 0xFF would give 255/256 = 99.6% not 100%
    # (pwm_counter counts 0 to 255, so "counter < 255" is only true 255 out of 256 times)
    await send_spi_transaction(dut, 1, 0x04, 0xFF)
    await ClockCycles(dut.clk, 2 * 3328)   # wait 2 full pwm periods just to be safe
    stuck_high = (int(dut.uo_out.value) & 0x1) == 1
    dut._log.info(f"0xFF: pin is {'HIGH — correct' if stuck_high else 'LOW — WRONG'}")

    # =========================================================================
    # SECTION 3 — Assert
    #
    # spec says duty cycle must be within +-1% of the expected value
    # so for 25% expected: anythign from 24.0% to 26.0% passes
    # for 50% expected: 49.0% to 51.0% passes
    #
    # the hardware computes exactly 25.0% and 50.0% for our test values
    # so both should pass no problem
    # =========================================================================

    for measured, expected, label in results:
        assert abs(measured - expected) <= 1.0, (
            f"Duty cycle wrong for {label}: "
            f"expected {expected:.1f}% ±1%, got {measured:.2f}%"
        )

    assert stuck_low,  "0x00 duty cycle: expected pin LOW but it wasnt"
    assert stuck_high, "0xFF duty cycle: expected pin HIGH but it wasnt"

    dut._log.info("PWM duty cycle test completed successfully")
