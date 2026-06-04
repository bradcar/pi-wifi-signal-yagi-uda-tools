# pi_wifi_rssi_quality_txrate.py
"""
On Raspberry Pi Zero 2 W, repeatedly measure and print RSSI, Link Quality,
and Tx Bit Rate of the currently connected network on interface wlan0.

Prototype for tracking signal vectors using a directional Yagi_Uda antenna.
Reads metrics continuously to signal strength changes.

Usage:
  python pi_wifi_rssi_quality_txrate.py
"""

import subprocess
import time
from datetime import datetime
import re


def get_ssid():
    """
    Queries the connected SSID name once at startup before the tracking loop begins.
    """
    try:
        # query iwconfig to get the ESSID string
        out = subprocess.check_output(["/sbin/iwconfig", "wlan0"], text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            if "ESSID" in line:
                return line.split('"')[1].strip()
    except Exception:
        pass

    # Final default so avoid empty 'None' type
    return "wlan0 essid unknown"


def query_wifi():
    """
    Queries RSSI, Link Quality, and current Tx Bit Rate dynamically.
    Execution time is kept low to ensure dense logging updates.

    :return: tuple (rssi, quality, tx_rate) or (None, None, None) on disconnect
    """
    rssi = None
    quality = None
    tx_rate = None

    # Get RSSI and Link Quality from the Linux Kernel network stats
    try:
        with open("/proc/net/wireless", "r") as f:
            lines = f.readlines()
            for line in lines:
                if "wlan0" in line:
                    parts = line.split()
                    quality = int(parts[2].replace('.', ''))
                    rssi = int(parts[3].replace('.', ''))

                    if rssi > 0:
                        rssi = rssi - 256
    except Exception:
        return None, None, None

    # Get Tx Rate as a raw float/int numerical value
    try:
        out = subprocess.check_output(["/sbin/iwconfig", "wlan0"], text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            if "Bit Rate" in line:
                parts = line.split("Bit Rate=")
                if len(parts) > 1:
                    raw_rate_str = parts[1].split("   ")[0].strip()
                    # regex match to isolate only numbers/decimals
                    match = re.findall(r"[+-]?\d*(?:\.\d+)?", raw_rate_str)
                    if match and match[0] != "":
                        tx_rate = float(match[0])
                    break
    except Exception:
        pass

    return rssi, quality, tx_rate


def scan_target_ssid(interface="wlan0", target_ssid="ABox-PDX"):
    """
    High-speed, non-blocking scan replacement using 'iw dump' instead of iwlist.
    Reads the kernel's active BSS cache to avoid blocking the main loop.
    """
    try:
        scan = subprocess.check_output(
            ["/usr/sbin/iw", "dev", interface, "scan", "dump"],
            text=True,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        return None

    # Split Access Point blocks
    cells = scan.split("BSS ")
    target_rssi = None

    for cell in cells[1:]:
        # Extract SSID
        ssid_match = re.search(r"SSID:\s*(.*)", cell)
        if ssid_match:
            # Strip quotes or trailing spaces
            ssid = ssid_match.group(1).strip().strip('"')

            if ssid == target_ssid:
                # Extract signal strength ("signal: -65.00 dBm")
                rssi_match = re.search(r"signal:\s*([+-]?\d+(?:\.\d+)?)", cell)
                if rssi_match:
                    target_rssi = int(float(rssi_match.group(1)))
                    # loop to catch the strongest signal if there are multiple APs with same SSID

    return target_rssi


def rssi_to_string(rssi):
    """Generates text strings for signal metrics."""
    if rssi is None:
        return "0 bar", "Unstable Link"

    if rssi > -50:
        rssi_string = "4 bars"
    elif rssi > -60:
        rssi_string = "3 bars"
    elif rssi > -70:
        rssi_string = "2 bars"
    elif rssi > -80:
        rssi_string = "1 bar"
    else:
        rssi_string = "0 bar"
    return rssi_string

def quality_to_string(quality):
    """Generates text strings for signal metrics."""
    if quality is not None:
        if quality >= 60:
            quality_string = "Hi Quality"
        elif quality >= 45:
            quality_string = "Stable Link"
        elif quality >= 30:
            quality_string = "Low Quality"
        else:
            quality_string = "Unstable Link"
    else:
        quality_string = "Disconnected"

    return quality_string


def print_metrics(quality, rssi, ssid, tx_rate):
    """Prints RSSI, Link Quality, and Tx Rate with text interpretation."""
    rssi_string = rssi_to_string(rssi)
    quality_string = quality_to_string(quality)

    print(f"WiFi Signal Monitor (Pi Zero): {ssid}")
    print(f"SSID:    {ssid}")

    if rssi is not None:
        print(f"RSSI:    {rssi:>3} dBm  {rssi_string}")
        print(f"Link Q:  {f'{quality:>2}/70' if quality is not None else 'n/a'}    {quality_string}")
        print(f"Tx Rate: {f'{tx_rate:.1f} Mb/s' if tx_rate is not None else 'n/a'}")
    else:
        print("RSSI:    n/a")
        print("Link Q:  n/a")
        print("Tx Rate: n/a")


def main():
    print("Starting Pi Zero 2 W Signal Tracking Loop...\n")

    # Get the network SSID text
    ssid = get_ssid()

    try:
        start_time = time.time()
        while True:
            # Get RSSI, Quality, and Mb/s
            rssi, quality, tx_rate = query_wifi()
            finish_time = time.time()
            duration = finish_time - start_time
            start_time = finish_time

            print_metrics(quality, rssi, ssid, tx_rate)
            print(f"Updates:  {duration * 1000:.1f} msec, {1.0 / duration:.0f} Hz")
            print(f"Clock: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nTracking Stopped. Exiting.")


if __name__ == "__main__":
    main()