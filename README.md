
# Wi-Fi Signal Tools for Pi Zero 2 W

Four tools for measuring Wi-Fi signals. Preliminary work in progress!

1) pi_wifi_scan_rssi.py - scans all 2.4 GHz networks getting rssi signal strength
2) pi_yagi_uda.py - measurs signal strength of connected network using directional Yagi-Uda Antenna and IMU.

3) pi_wifi_rssi_quality_txrate.py - get quality of the connected network
   1) Note: macOS measures SNR & Noise and not quality and TxRate
4) pi_wifi_rssi_quality_txrate_curses.py - Curses version of above

## pi_wifi_scan_rssi.py 

Scans and only measures RSSI on available 2.4GHz Wi-Fi (not 5GHz or 6GHz). Runs on Raspberry Pi Zero 2 W in Linux
Scans repeatedly, sorted by strongest RSSI first.

Quality or Tx bitrates on unconnected networks. For connected network use: pi_wifi_rssi_quality_txrate.py

### Power draw
0.16a @ 5.22v (0.82w)

### Usage:
  in terminal, python3 mac_wifi_scan_rssi.py
  can also run from PyCharm

### Sample console output pi_wifi_scan_rssi.py

    SSID                    Band    BSSID             RSSI      Bars
    ------------------------------------------------------------------
    your-network               2.4 GHz B6:39:56:91:1D:0F  -20 dBm  4 bars
    CenturyLink7697         2.4 GHz 08:26:97:62:38:DC  -22 dBm  4 bars
    <hidden>                2.4 GHz BA:39:56:91:1D:0F  -23 dBm  4 bars
    your-network               2.4 GHz 0E:02:8E:9E:7D:C3  -55 dBm  3 bars
    <hidden>                2.4 GHz 12:02:8E:9E:7D:C3  -59 dBm  3 bars
    <hidden>                2.4 GHz 28:80:88:49:59:BF  -75 dBm  1 bar
    ORBI24                  2.4 GHz 28:80:88:46:FA:83  -79 dBm  1 bar
      Clock: 2026-05-22 23:08:38, Update every 0.84 secs
      Blocked <1-bar and only shows 2.4GHz on Zero 2 W

## pi_wifi_rssi_quality_txrate.py

On Raspberry Pi Zero 2 W, repeatedly measure and print RSSI, Link Quality,
and Tx Bit Rate of the currently connected network on interface wlan0.

Prototype for tracking signal vectors using a directional Yagi_Uda antenna.
Reads metrics continuously to signal strength changes.

### Power draw
0.21a @ 5.22v (1.2w)

### Usage:
in terminal, python3 pi_wifi_rssi_quality_txrate.py
can also run in pycharm

There is also a Curses version:
pi_wifi_rssi_quality_txrate_curses.py

### Sample output pi_wifi_rssi_quality_txrate.py
    WiFi Signal Monitor (Pi Zero): ABox-PDX
    SSID:    ABox-PDX
    RSSI:    -19 dBm  4 bars
    Link Q:  70/70, Perfect Link
    Tx Rate: 72.2 Mb/s
    Updates:  15.8 msec, 63 Hz
    Clock: 2026-05-23 09:36:26

## pi_yagi_uda.py

On Raspberry Pi Zero 2 W, the code repeatedly measures the RSSI, Link Quality,
and RX Bitrate of a targeted network on interface wlan0. Only measures RSSI on available 2.4GHz Wi-Fi's (not 5GHz or 6GHz)
When paired with a Yagi-Uda directional antenna and an LIS3MDL magnetometer,
signal strength is mapped with physical headings to locate the Wi-Fi signal source.

The code automatically handles connection drops and resumes polling upon reconnect.
When there is sufficient signal strength when connected, an option to download file on a specifiec webpage can be downloaded.

### Power draw
Scanniing mode: 0.3a, 1.5w

Connected Mode: 0.35a, 1.6w

Idle: 0.2a 0.76w

### Usage:
in terminal, python3 pi_yagi-uda.py
can also run in PyCharm

### Sample console output pi_yagi_uda.py
There are two modes with different information possible:
```
** Scanning your-network (channel=11) RSSI: -56 dBm
Bars:      3 bars
Compass Heading: 291° W
Pi Zero 2W temp: 42.9°C
Display Updates:   208.4 msec, 5 Hz
Radar Updates:     208.4 msec, 5 Hz
Clock: 2026-09-14 10:14:12
```

```
** Connected your-network (channel = 11) RSSI: -23 dBm
Bars:    4 bars
Quality: 100%  Excellent
RX Rate: 72.2 Mb/s
-> download possible, trigger with button1
Compass Heading: 332° NW
Pi Zero 2W temp: 42.9°C
Display Updates:   112.6 msec, 9 Hz
Radar Updates:      36.2 msec, 28 Hz
Clock: 2026-09-14 10:14:20
```

### NOTES

1. Python MUST be enabled in System Settings > Privacy & Security> Location Services.

2. iwlist sudo
   1. Give the iwlist program setuid root permissions
   sudo chmod u+s /usr/sbin/iwlist
   2. Verify the permissions changed successfully
   ls -l /usr/sbin/iwlist


### Turning on gadget-mode on existing Raspberry Pi headless

1. Verify that you are running Raspberry Pi OS Trixie:
cat /etc/os-release
→ Confirm that VERSION_CODENAME=trixie.

2. Install and enable gadget mode:
   1. sudo apt update
   2. sudo apt install rpi-usb-gadget
   3. sudo rpi-usb-gadget on
   4. sudo reboot


### PyCharm Remote Deployment Reset (running out of /tmp issue)

You may run into issues with PyCharm executing your code in a randomized `/tmp/` directory instead of running natively out of your home directory on the Pi.
This can occur after renaming the repository.

* Follow the steps in the [PyCharm Remote Run Fix Guide](PyCharm-run-remote-temp-fix.md).