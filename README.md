
# Wi-Fi Signal Tools for Pi Zero 2 W

Four tools for measuring Wi-Fi signals. Preliminary work in progress!

our Python telemetry and scanning tools for measuring 2.4GHz Wi-Fi signals on a Raspberry Pi Zero 2 W. 

### LCD Display Tools:
1. **`pi_wifi_scan_rssi.py`** – Scans all surrounding 2.4GHz Wi-Fi networks, ranks them by RSSI strength, builds 360° directional signal profiles, and generates polar radar plots.
2. **`pi_yagi_uda.py`** – Live directional tracking of a targeted Wi-Fi network using a Yagi-Uda antenna and LIS3MDL magnetometer. Maps signal vectors (RSSI, Link Quality, RX Bitrate) to compass headings.

### Console-Only Tools:
3. **`pi_wifi_rssi_quality_rxrate.py`** – High-frequency terminal monitor tracking RSSI, Link Quality, and RX Bitrate (download rate from AP) for the connected network.
4. **`pi_wifi_rssi_quality_rxrate_curses.py`** – Full-screen `curses` terminal dashboard providing flicker-free, in-place metric updates.

---

## Hardware Setup & Pin Mapping

* **Board:** Raspberry Pi Zero 2 W (Linux)
* **Display:** [WaveShare Triple LCD Display HAT](https://www.waveshare.com/zero-lcd-hat-a.htm) (ST7789 Drivers, rotated 180° / USB at bottom)
  * Left Display (`disp_0`): 160px × 80px (Menu Controls)
  * Center Display (`disp_1`): 240px × 240px (Radar Plotter & Network Table)
  * Right Display (`disp_2`): 160px × 80px (Telemetry & Clock)
* **Sensors & Antenna:**
  * **LIS3MDL** 3-Axis I2C Magnetometer (for 360° compass headings)
  * 2.4GHz Directional Yagi-Uda Antenna
* **Button Controls (gpiozero with Pi internal pull-ups):**
  * `GPIO 26` (Top Button 2) : Scroll / Next in Menu | Toggle Scan/Connected Modes
  * `GPIO 25` (Bottom Button 1) : Select BSSID | Toggle Hi-Rez Plot Generation
  * `GPIO 6` (External Trigger Button 0) : Short press (Connect/Download) | Long press (Disconnect)

---

## pi_yagi_uda.py

Targeted directional tracking integrating the Yagi-Uda antenna and LIS3MDL magnetometer.
Automatically manages network state (nmcli) to toggle between unauthenticated scanning and high-speed multi-threaded connected polling.
Includes payload download capability when link budget is sufficient.

The code automatically handles connection drops and resumes polling upon reconnect.
When there is sufficient signal strength when connected, an option to download file on a specifiec webpage can be downloaded.

Operational Modes:
* Scan Mode (is_connected == False): Low-frequency pings via nmcli/iw (~5 Hz update rate).
* Connected Mode (is_connected == True): Multi-threaded direct network interface polling (~31 Hz metric updates, ~9 Hz UI updates).

### Power draw
* Scanning:  0.29a, 1.49w, 5.22v
* Connected: 0.31a, 1.62w, 5.22v
* Idle:      0.15a, 0.77w, 5.22v

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

Configuration & Notes

Permissions: Ensure system utilities have setuid permissions for non-root execution:

```sudo chmod u+s /usr/sbin/iwlist```



## pi_wifi_scan_rssi.py 

Scans and only measures RSSI on available 2.4GHz Wi-Fi (not 5GHz or 6GHz). Runs on Raspberry Pi Zero 2 W in Linux
Scans repeatedly, sorted by strongest RSSI first.

Quality or RX bitrates (download from AP) on unconnected networks. For connected network use: pi_wifi_rssi_quality_rxrate.py

### Power draw
* Scanning Mode   : 0.25A, 1.31W @ 5.22V
* Radar Graph UI  : 0.29A, 1.51W @ 5.22V
* Idle            : 0.15A, 0.77W @ 5.22V

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

## pi_wifi_rssi_quality_rxrate.py

On Raspberry Pi Zero 2 W, repeatedly measure and print RSSI, Link Quality,
and RX Bit Rate of the currently connected network on interface wlan0.

Prototype for tracking signal vectors using a directional Yagi_Uda antenna.
Reads metrics continuously to signal strength changes.

### Power draw
0.21a @ 5.22v (1.2w)

### Usage:
in terminal, python3 pi_wifi_rssi_quality_rxrate.py
can also run in pycharm

There is also a Curses version:
pi_wifi_rssi_quality_rxrate_curses.py

### Sample output pi_wifi_rssi_quality_rxrate.py
    WiFi Signal Monitor (Pi Zero): ABox-PDX
    SSID:    ABox-PDX
    RSSI:    -19 dBm  4 bars
    Link Q:  70/70, Perfect Link
    RX Rate: 72.2 Mb/s
    Updates:  15.8 msec, 63 Hz
    Clock: 2026-05-23 09:36:26



### NOTES

1. Python MUST be enabled in System Settings > Privacy & Security> Location Services.

2. iwlist sudo
   1. Give the iwlist program setuid root permissions
   sudo chmod u+s /usr/sbin/iwlist
   2. Verify the permissions changed successfully
   ls -l /usr/sbin/iwlist

      


### PyCharm Remote Deployment Reset (running out of /tmp issue)

You may run into issues with PyCharm executing your code in a randomized `/tmp/` directory instead of running natively out of your home directory on the Pi.
This can occur after renaming the repository.

* Follow the steps in the [PyCharm Remote Run Fix Guide](PyCharm-run-remote-temp-fix.md).