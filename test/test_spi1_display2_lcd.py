#!/usr/bin/env python3
"""
spi1_test_utils.py

Diagnostics and testing utilities for Waveshare Triple LCD HAT SPI1 bus (Center Display).
- test_spi1_burst(): Runs a controlled burst test with CS pin monitoring.
- flood_spi1_bus(): Floods SPI1 with continuous byte transfers for pinctrl/logic analyzer capture.
"""

import subprocess
import time
import spidev


def check_cs_state(pin: int = 18) -> str:
    """Queries pinctrl to get the live state of the designated CS pin."""
    res = subprocess.run(["pinctrl", "get", str(pin)], capture_output=True, text=True)
    return res.stdout.strip()


def test_spi1_test_burst_xmit():
    """
    Transmits a controlled 256-byte burst payload over SPI1 at 30 MHz.
    Verifies that device open/close and writebytes execute cleanly without OS exceptions.
    """
    print("--- Running SPI1 Burst Test (30 MHz) ---")
    print("Opening /dev/spidev1.0...")
    spi = spidev.SpiDev()
    spi.open(1, 0)
    spi.max_speed_hz = 30000000
    spi.mode = 0b00

    print(f"CS Pin (GPIO 18) initial state: {check_cs_state(18)}")

    # Send 256-byte dummy test burst
    test_data = [0xAA if i % 2 == 0 else 0x55 for i in range(256)]

    print("Transmitting test payload across SPI1 (MOSI: GPIO 20, SCLK: GPIO 21)...")
    for _ in range(10):
        spi.writebytes(test_data)
        time.sleep(0.05)

    print("SUCCESS (if no errors shown): SPI1 write completed with no OS or hardware driver exceptions.\n")
    spi.close()


def flood_spi1_bus():
    """
    Floods SPI1 with continuous 2KB payload transfers at 1 MHz.
    Holds CS (GPIO 18) LOW long enough for pinctrl or oscilloscope sampling loops.

    run in separate term window:
        $ for i in {1..2000}; do pinctrl get 18,20,21; sleep 0.1; done

    """
    print("--- Running SPI1 Continuous Bus Flood (1 MHz) ---")
    print("Flooding SPI1 bus... Press Ctrl+C to stop.")

    spi = spidev.SpiDev()
    spi.open(1, 0)
    spi.max_speed_hz = 1000000  # 1 MHz expands transfer window to ~2ms per payload
    spi.mode = 0b00

    dummy = [0xFF] * 2048  # Large 2KB buffer

    try:
        while True:
            spi.writebytes(dummy)
    except KeyboardInterrupt:
        print("\nInterrupt received. Closing SPI1 bus cleanly.")
    finally:
        spi.close()


if __name__ == "__main__":
    # Method 1: Controlled 30 MHz burst test
    test_spi1_test_burst_xmit()

    # Method 2: Continuous 1 MHz bus flooding test
    # flood_spi1_bus()