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
    # Before we can see any PWM output we need three things to be true:
    #   1. the output enable register (addr 0x00) has to say this pin is on
    #   2. the PWM enable register (addr 0x02) has to say use PWM (not static)
    #   3. the duty cycle register (addr 0x04) has to be non-zero so it toggles
    #
    # Without step 1 the pin is just stuck at 0.
    # Without step 2 the pin is stuck at 1 (static high — no toggling).
    # We use 50% duty cycle (0x80) because it gives equal high and low time
    # which makes both rising and falling edges easy to catch.
    # =========================================================================

    # 10 MHz system clock — 100 ns per cycle, same as the hardware target
    clock = Clock(dut.clk, 100, units="ns")
    cocotb.start_soon(clock.start())

    # hold reset low for a few cycles so all registers start at 0x00
    dut.ena.value = 1
    dut.ui_in.value = ui_in_logicarray(1, 0, 0)  # CS high while in reset
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)

    # addr 0x00 — output enable for uo_out[7:0]
    # 0xFF turns on all 8 lower output pins. we only actually look at pin 0
    # but enabling all of them doesn't hurt
    await send_spi_transaction(dut, 1, 0x00, 0xFF)

    # addr 0x02 — PWM mode enable for uo_out[7:0]
    # this is what makes the pin TOGGLE instead of staying statically high
    await send_spi_transaction(dut, 1, 0x02, 0xFF)

    # addr 0x04 — duty cycle = 0x80 = 128/256 = exactly 50%
    # 50% is a good choice here because we only care about PERIOD not duty
    # and a 50% wave is the clearest to look at in GTKWave if something breaks
    await send_spi_transaction(dut, 1, 0x04, 0x80)

    # =========================================================================
    # SECTION 2 — Measure
    #
    # The idea: the time between two consecutive rising edges of uo_out[0]
    # is exactly one PWM period. Frequency = 1 / period.
    #
    # How I detect a rising edge in software:
    #   - sample the pin value every clock cycle
    #   - a rising edge happened when: last sample was 0, current sample is 1
    #   - I do this twice and record the simulation time at each detection
    #
    # Expected period from the hardware:
    #   clk_div_trig = 12, so pwm_counter ticks every (12+1) = 13 system clocks
    #   pwm_counter is 8-bit, so it wraps every 256 ticks
    #   total period = 13 * 256 = 3328 system clocks = 332,800 ns = ~3004.8 Hz
    # =========================================================================

    # sample the current state of uo_out bit 0 as our baseline
    # "& 0x1" masks everything except bit 0
    prev = int(dut.uo_out.value) & 0x1

    # wait for the FIRST rising edge on uo_out[0]
    while True:
        await ClockCycles(dut.clk, 1)
        curr = int(dut.uo_out.value) & 0x1
        if prev == 0 and curr == 1:   # was 0 last cycle, is 1 now → rising edge
            break
        prev = curr

    t1 = cocotb.utils.get_sim_time(units="ns")
    dut._log.info(f"First rising edge at {t1} ns")

    # now carry on from here and wait for the SECOND rising edge
    # prev stays as curr (= 1) so we correctly wait for the signal to
    # go low first before detecting the next 0→1 transition
    prev = curr
    while True:
        await ClockCycles(dut.clk, 1)
        curr = int(dut.uo_out.value) & 0x1
        if prev == 0 and curr == 1:
            break
        prev = curr

    t2 = cocotb.utils.get_sim_time(units="ns")
    dut._log.info(f"Second rising edge at {t2} ns")

    # period = gap between the two edges
    # frequency = 1 / period — but period is in nanoseconds so:
    #   freq_hz = 1 / (period_ns * 1e-9) = 1e9 / period_ns
    period_ns = t2 - t1
    freq_hz = 1e9 / period_ns
    dut._log.info(f"Measured period: {period_ns:.0f} ns  →  frequency: {freq_hz:.2f} Hz")

    # =========================================================================
    # SECTION 3 — Assert
    #
    # The spec says 3 kHz ±1%. 1% of 3000 = 30 Hz, so:
    #   lower bound = 3000 - 30 = 2970 Hz
    #   upper bound = 3000 + 30 = 3030 Hz
    #
    # Our hardware computes ~3004.8 Hz so it should land comfortably inside.
    # If this assert fires, the first thing to check is the tb.vcd in GTKWave
    # to see whether the output pin is actually toggling at all.
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
    # Same boilerplate as test_pwm_freq: start the clock, reset the chip,
    # then write to the two enable registers so the output pin is in PWM mode.
    # We deliberately DON'T set the duty cycle here — that happens in Section 2
    # so we can try multiple values and check each one.
    # =========================================================================

    clock = Clock(dut.clk, 100, units="ns")
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = ui_in_logicarray(1, 0, 0)  # CS high during reset
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)

    # addr 0x00 — output enable for uo_out[7:0]
    # all 8 lower pins enabled; we only look at pin 0
    await send_spi_transaction(dut, 1, 0x00, 0xFF)

    # addr 0x02 — PWM mode enable for uo_out[7:0]
    # without this the pin is static high regardless of duty cycle register
    await send_spi_transaction(dut, 1, 0x02, 0xFF)

    # =========================================================================
    # SECTION 2 — Measure
    #
    # For each "normal" duty cycle (somewhere between 0% and 100%) we use a
    # three-step edge-detection pattern to measure what the hardware actually
    # outputs:
    #
    #   Step A: wait for a RISING  edge → this is the start of the high phase
    #   Step B: wait for a FALLING edge → this is the end of the high phase
    #   Step C: wait for the next RISING edge → this completes one full period
    #
    #   high_time = t_fall  - t_rise1       (how long the pin was HIGH)
    #   period    = t_rise2 - t_rise1       (length of one full PWM cycle)
    #   duty%     = (high_time / period) * 100
    #
    # For the two edge cases (0% and 100%) the pin never toggles so the
    # rising/falling pattern would loop forever. We handle those separately
    # by just waiting two full PWM periods and checking the pin is stuck.
    # =========================================================================

    results = []  # collect (measured_duty, expected_duty, label) for Section 3

    # test 25% (0x40 = 64/256) and 50% (0x80 = 128/256)
    for reg_val, expected_pct in [(0x40, 25.0), (0x80, 50.0)]:

        await send_spi_transaction(dut, 1, 0x04, reg_val)

        # STEP A — wait for a rising edge on uo_out[0]
        prev = int(dut.uo_out.value) & 0x1
        while True:
            await ClockCycles(dut.clk, 1)
            curr = int(dut.uo_out.value) & 0x1
            if prev == 0 and curr == 1:  # 0→1 = rising edge
                break
            prev = curr
        t_rise1 = cocotb.utils.get_sim_time(units="ns")

        # STEP B — wait for the falling edge (1→0) right after the rise
        # this tells us when the high phase ended
        prev = curr
        while True:
            await ClockCycles(dut.clk, 1)
            curr = int(dut.uo_out.value) & 0x1
            if prev == 1 and curr == 0:  # 1→0 = falling edge
                break
            prev = curr
        t_fall = cocotb.utils.get_sim_time(units="ns")

        # STEP C — wait for the next rising edge to complete one full period
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
    # pwm_signal = (pwm_counter < 0) which is always false for an unsigned counter
    # so the output should be stuck LOW the entire time
    await send_spi_transaction(dut, 1, 0x04, 0x00)
    await ClockCycles(dut.clk, 2 * 3328)   # wait 2 full PWM periods to be sure
    stuck_low = (int(dut.uo_out.value) & 0x1) == 0
    dut._log.info(f"0x00: pin is {'LOW — correct' if stuck_low else 'HIGH — WRONG'}")

    # --- edge case: 100% duty cycle (0xFF) ---
    # the RTL has a special case: if pwm_duty_cycle == 0xFF, force output = 1
    # (without this special case, 0xFF would actually give 255/256 not 100%
    # because pwm_counter only reaches 255 not 256)
    await send_spi_transaction(dut, 1, 0x04, 0xFF)
    await ClockCycles(dut.clk, 2 * 3328)   # wait 2 full PWM periods to be sure
    stuck_high = (int(dut.uo_out.value) & 0x1) == 1
    dut._log.info(f"0xFF: pin is {'HIGH — correct' if stuck_high else 'LOW — WRONG'}")

    # =========================================================================
    # SECTION 3 — Assert
    #
    # The spec says ±1% tolerance on duty cycle.
    # That means the measured value must be within 1 percentage point of expected.
    # e.g. for 25% expected: anything from 24.0% to 26.0% passes.
    #
    # The hardware computes duty as (reg_val / 256) * 100 which for our values
    # gives exactly 25.0% and 50.0%, so both should pass cleanly.
    # =========================================================================

    for measured, expected, label in results:
        assert abs(measured - expected) <= 1.0, (
            f"Duty cycle wrong for {label}: "
            f"expected {expected:.1f}% ±1%, got {measured:.2f}%"
        )

    assert stuck_low,  "0x00 duty cycle: expected pin LOW but it wasn't"
    assert stuck_high, "0xFF duty cycle: expected pin HIGH but it wasn't"

    dut._log.info("PWM duty cycle test completed successfully")
