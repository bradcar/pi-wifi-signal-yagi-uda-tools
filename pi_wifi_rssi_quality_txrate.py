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
        # Startup fallback: query iwconfig once to extract the true ESSID string
        out = subprocess.check_output(["/sbin/iwconfig", "wlan0"], text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            if "ESSID" in line:
                # Splits out the string between the quotation marks
                return line.split('"')[1].strip()
    except Exception:
        pass

    # Final default so the variable never becomes an empty 'None' type
    return "wlan0 essid unknown"


def probe_target_ssid(interface="wlan0", target_ssid="ABox-PDX"):
    """
    targeted probe for a specific SSID on an unjoined interface,
    returning its RSSI value if found in the local radio environment.
    """
    try:
        # Trigger an active network scan filtered for the target SSID
        cmd = f"sudo iwlist {interface} scan essid '{target_ssid}'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=2.0)

        if result.returncode != 0:
            return None

        # Parse the output blocks for the specific signal levels found
        output = result.stdout
        cells = output.split("Cell ")

        for cell in cells:
            if f'ESSID:"{target_ssid}"' in cell:
                # Use a regular expression to extract the signal level integer
                match = re.search(r"Signal level=(-\d+)\s+dBm", cell)
                if match:
                    return int(match.group(1))
    except Exception:
        return None
    return None


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

    # Get Tx speed as a raw float/int numerical value
    try:
        out = subprocess.check_output(["/sbin/iwconfig", "wlan0"], text=True, stderr=subprocess.DEVNULL)
        for line in out.splitlines():
            if "Bit Rate" in line:
                parts = line.split("Bit Rate=")
                if len(parts) > 1:
                    raw_rate_str = parts[1].split("   ")[0].strip()
                    # Use a strict regex match to isolate only numbers/decimals
                    match = re.findall(r"[+-]?\d*(?:\.\d+)?", raw_rate_str)
                    if match and match[0] != "":
                        tx_rate = float(match[0])
                    break
    except Exception:
        pass

    # If we parsed a valid RSSI but tx_rate parsing completely failed,
    # handle it as a partial connection drop state
    if rssi is None or quality is None or tx_rate is None:
        return None, None, None

    return rssi, quality, tx_rate


def rssi_quality_to_string(rssi, quality):
    """Generates qualitative text interpretations for signal metrics."""
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

    if quality >= 60:
        quality_string = "Hi Quality"
    elif quality >= 45:
        quality_string = "Stable Link"
    elif quality >= 30:
        quality_string = "Low Quality"
    else:
        quality_string = "Unstable Link"

    return rssi_string, quality_string


def print_with_string(quality, rssi, ssid, tx_rate):
    """Prints RSSI, Link Quality, and Tx Rate with text interpretation."""
    rssi_string, quality_string = rssi_quality_to_string(rssi, quality)

    print(f"WiFi Signal Monitor (Pi Zero): {ssid}")
    print(f"SSID:    {ssid}")

    if rssi is not None:
        print(f"RSSI:    {rssi:>3} dBm  {rssi_string}")
        print(f"Link Q:  {quality:>2}/70    {quality_string}")
        print(f"Tx Rate: {tx_rate:.1f} Mb/s")
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
            # Get RSSI, Quality, and Mb/s (numerical)
            rssi, quality, tx_rate = query_wifi()
            finish_time = time.time()
            duration = finish_time - start_time
            start_time = finish_time

            print_with_string(quality, rssi, ssid, tx_rate)
            print(f"\nUpdates:  {duration * 1000:.1f} msec, {1.0 / duration:.0f} Hz")
            print(f"Clock: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nTracking Stopped. Exiting.")


if __name__ == "__main__":
    main()
