
# Wi-Fi Directional finder and download for Pi Zero 2 W

Directional tracking of a targeted Wi-Fi network using a Yagi-Uda antenna and an LIS3MDL magnetometer.
This code was designed to determine the location of a Wi-Fi network and then download a telemetry dataset to the Raspberry Pi Zero 2 W's flash storage for later analysis.

pi_yagi_uda.py tracks the signal strength of a selected 2.4 GHz Wi-Fi network as a hand-held directional Yagi-Uda antenna is rotated.
The received signal strength (RSSI) is recorded at each compass heading (1° resolution), measured using the LIS3MDL magnetometer to build a 360° directional signal history.

The code runs on a Raspberry Pi Zero 2 W under Linux and uses the nmcli utility to measure RSSI. 
It supports a Waveshare Triple LCD HAT or a detected OLED display and provides live Wi-Fi telemetry. 
Hardware buttons control operating modes, initiate connections when the signal strength is sufficient, and trigger downloads from an access point to the Raspberry Pi's flash storage.
When the signal is strong enough, the user sees notification on screen and can press the button underneath the menu.
This initiates a download of a binary file from the  configured access point.

It scans for unconnected networks at 1.4 Hz and polls a user-initiated connection at a faster rate of 5 Hz for more accurate measurements. 
When in connected mode, multithreading keeps network measurements responsive while display rendering runs asynchronously, minimizing delays in signal measurements.

pi_yagi_uda.py Features:
* Targeted Single-network Tracking: Locks onto and monitors a specific Wi-Fi SSID.
* 1.4 Hz Unconnected Scan Rate: Scans unconnected Wi-Fis with "nmcli".
* 5 Hz Connected Scan Rate: Higher accuracy interface polling when actively connected with an access point.
* Dual Operational Modes: Can switch between background scanning and connected link polling.
* Hardware Buttons Control Modes: Features the display's hardware buttons for mode handling and file-download triggers.
* Modes: Scans unconnected Wi-Fi (nmcli) when signal strength sufficient can start connection mode.
* Access Point Download: Button can trigger data download from Access Point and store into Pi Zero W flash.
* Multi-Threading: Handles faster background network polling, while slower display rendering runs asynchronously to prevent signal measurement lag.


# pi_yagi_uda.py

The primary script runs on a Raspberry Pi Zero 2 W (Linux) to continuously scan a 2.4 GHz Wi-Fi networs.
When paired with a Yagi Uda directional antenna and a LIS3MDL 3-axis magnetometer, it correlates signal strength (RSSI) with physical antenna headings to build 360° polar signal distribution map.
It supports real-time visualization on a WaveShare Triple LCD HAT and creates a high-resolution print-quality plot exports with Matplotlib on program exit.
You will need to enter in the Pi Zero 2 W's password for Wi-Fi scans, since it uses system call to get network state (nmcli).

irectional Yagi Uda Antenaa with photograher handgrip and small tripod screwed into it.
Raspberry Pi Zero 2 W with WaveShare Triple display LCD (red open case), black 10000maH battery, and a LIS3MDL (white open box).


## Hardware & Display Layout

Data an images shown on the WaveShare Triple Display LCD HAT (ST7789 drivers).
It also uses the left most screen for menu selection using the physical buttons on the Triple Display LCD Hat. These buttons are directly under the left-most screen.

## Display layout

When using the three-display Waveshare LCD HAT, the code uses the displays as follows:

| Display           | Resolution | Purpose                                                        |
|-------------------|-----------:|----------------------------------------------------------------|
| Left (`disp_0`)   |   160 × 80 | Connection status, signal status, and download prompts         |
| Center (`disp_2`) |  240 × 240 | Polar RSSI plot and directional signal history                 |
| Right (`disp_1`)  |   160 × 80 | Compass heading and direction to the strongest recorded signal |

The code also contains a vestigial OLED display path. 
The display initialization logic selects the OLED path when an OLED is detected.
When not detected, the code initializes the three LCD displays.

## Hardware button controls

The LCD button assignments are:

| GPIO    | Button                      | Action                                                                               |
|---------|-----------------------------|--------------------------------------------------------------------------------------|
| GPIO 6  | Button 0 / external trigger | Short press: attempt connection in Scan Mode or trigger a download in Connected Mode |
| GPIO 6  | Button 0 / external trigger | Long press: disconnect and return to Scan Mode                                       |
| GPIO 25 | Button 1                    | Trigger a download in Connected Mode                                                 |
| GPIO 26 | Button 2                    | Request a connection in Scan Mode                                                    |

The connection and download requests are subject to the applicable RSSI thresholds.
A button press does not guarantee that a connection or download will succeed.


T## Operating modes

### 1. Scan Mode

Scan Mode is the initial operating mode. 
The code is not connected to the target network and scans for the configured SSID using the Wi-Fi scanning utilities.

The default target is `shell-fi` on channel 11. 
The measured RSSI is used to determine whether a connection attempt is permitted.

Press GPIO 6 briefly or press GPIO 26 to request a connection.
The connection is attempted only when a usable RSSI measurement is available and meets the connection threshold.

If the signal is below the threshold, the code with return to unconnected scan mode.
After a successful connection, the recorded RSSI heading history is reset for connected scanning.

### 2. Connected Mode

In Connected Mode, the code polls the connected Wi-Fi interface for network metrics.
With asynchronous monitoring enabled, a background worker handles connected-mode updates while the main loop manages the displays and other output.

The code collects or displays the following metrics where available:

- **RSSI:** Received Wi-Fi signal strength in dBm.
- **BSSID:** The access point's basic service set identifier.
- **Compass heading:** The current direction reported by the LIS3MDL magnetometer.

The code monitors for connection loss and returns to scanning when it determines that the target connection has dropped. A temporary missing RSSI measurement does not automatically mean the connection has been lost.

## Downloading a file

The default configuration is intended to download a binary file from the `shell-fi` access point.

Current settings in `pi_yagi_uda.py`:

```python
TARGET_SSID = "shell-fi"
TARGET_CHANNEL = 11

URL_STRING = "http://192.168.4.1/download"
DESTINATION_STRING = os.path.expanduser("~/downloads")
```
When connected, briefly press GPIO 6 or press GPIO 25 to request a download. 
The code checks the current RSSI against `RSSI_DOWNLOAD_THRESHOLD` before starting the transfer.

The download utility is called with a five-second timeout.
A successful transfer increments the download counter and reports the destination and filename. 
A failed transfer returns to scanning.

The destination directory is configured as `~/downloads`. 
Ensure that it exists and is writable by the user running the program.

The download endpoint must be reachable from the Pi at the configured URL. 
If the access point, SSID, IP address, endpoint, or destination changes, update the corresponding settings in the source.

### Exit w/ Plot:

If the button under "Exit & Plot?" is selected the script will start preparing high-resolution print-ready Matplotlib polar plots for each of the Wi-Fi's detected (unknown and RSSI < -90db are skipped). 
These polar plots are scaled to show -99 dBm to -45 dBm range.
In addition, orange rings are show at the bar equivalents.
1. The innermost ring is solid orange at -80 dBm (1 bar), 
2. next ring is orange dashed at -70 dBm (2 bars), 
3. next ring is orange dashed at -60 dBm (3 bars),
4. final ring is solid orange at -50 dBm (4 bars).

On exit, the data used to generate the plot is also saved in a CSV file with data for the entire 360° (1° increments).
The file names are labeled with SSID Name, BSSID, Date/Time plot created, and strongest RSSI in this dataset. 
Plots use the ".png" extension and CSV Files use the ".csv" extension.
The CSV files and high-resolution PNG radar plots into the logs_polar_plots/ directory.

For locations with hundreds of networks, this may take 10 seconds or more.

Note: To quickly check the available Wi-Fi from the console use:

```$ sudo nmcli dev wifi list```

---

## Yagi Uda Directional Antenna
Yagi Uda directional antenna
* TECHTOO Wi-Fi Yagi-Uda Antenna 2.4GHz 18dBi High, RP-SMA Connector
  * Directional Antenna (we have observed similar Beamwidth)
    * 30° Horizontal Beamwidth
    * 28° Vertical Beamwidth
  * measured 10 to 19 dB gain over omnidirectional antenna
    * u.FL mod still lacks removal of some traces, so additional improvements are likely.
  * Return Loss: -30.7 dB  (VSWR 1:1.06)
  * Noise floor measure at unbelievably low -98.0 dBm.
* u.FL TO RP-SMA 4.1" Pigtail - Required to hook RP-SMA to Pi Zero 2 W
  * TE Connectivity, Part: 994-080-0001-ND
* Hardware modification required to add external u.FL connector to Pi Zero 2 W
  * Voids warranty because one must cut traces and remove capacitors to solder u.FL connector to provided pads.
  * Zero 2 W: https://www.youtube.com/watch?v=6R8xhSzpJTU&t=166s
    * 100°C board heater
    * 280°C hot air at low flow
  * Buy the best u.FL connectors, many cheap ones do not hold up to the soldering heat.
* Photographers hand grip
  * DSLR Camera Hand Grip Stabilizer https://www.amazon.com/dp/B01FUEXLGU
    * Also has 3/8" screw at bottom so can mount on tripod.
  * Hand grip attached to antenna bar with Hillman #10-24 x 5/8-in Rubber Well Nut


## Noise Floor - exceptional configuration
In an open neighborhood park we have seen -99 dBm on a verified, named SSID. This value is nearly at the absolute bottom edge of what silicon can physically resolve on a 2.4 GHz Wi-Fi channel.
With a theoretical thermal noise floor around -101 dBm for a 20 MHz wide channel and hardware sensitivity limits on the Broadcom/Cypress chipset likely bottoms out at -100 to -105 dBm.
Getting a clean beacon frame out at -99 dBm proves this directional Yagi-Uda setup is performing at near-peak efficiency. 


## Configuration

The principal settings are defined near the beginning of `pi_yagi_uda.py`:

```python
TARGET_SSID = "shell-fi"
TARGET_CHANNEL = 11
URL_STRING = "http://192.168.4.1/download"
DESTINATION_STRING = os.path.expanduser("~/downloads")
LOG_DIRECTORY = "logs_yagi_uda_rssi"

USE_ASYNC_METRICS = True
LOG_PRELIM_CSV_TO_FLASH = False
DEBUG = False

RSSI_CONNECT_THRESHOLD = -91.0
RSSI_DOWNLOAD_THRESHOLD = -80.0

USE_MONO_TYPE = False
```

- `TARGET_SSID` selects the network to track.
- `TARGET_CHANNEL` selects the channel used by the scan routine. The source comments indicate that `None` can be used when no particular channel is targeted.
- `URL_STRING` specifies the download endpoint.
- `DESTINATION_STRING` specifies where downloaded files are saved.
- `LOG_DIRECTORY` specifies the directory used for plot and summary exports.
- `USE_ASYNC_METRICS` enables the background connected-mode worker.
- `LOG_PRELIM_CSV_TO_FLASH` controls optional periodic CSV output of the RSSI heading history. It is disabled by default.

The compass is configured in the current source with a 180° mounting orientation and a 14.5° east-positive magnetic declination. These values should match the actual mounting orientation and the intended operating location.



## Hardware Setup & Pin Mapping
* **Board:** Raspberry Pi Zero 2 W (Linux)
* **Sensors & Antenna:**
  * 2.4GHz Directional Yagi-Uda Antenna
  * **LIS3MDL** 3-Axis I2C Magnetometer (for 360° compass headings)
* **Display:** [WaveShare Triple LCD Display HAT](https://www.waveshare.com/zero-lcd-hat-a.htm) (ST7789 Drivers, rotated 180° / USB at bottom)
  * Left Display (disp_0): 160px × 80px (Menu Controls)
  * Center Display (disp_2): 240px × 240px (Radar Plotter & Network Table)
  * Right Display (disp_1): 160px × 80px (Telemetry & Clock)
* **Button Controls (gpiozero with Pi internal pull-ups):**
  * `GPIO 26` (Top Button 2) : Scroll / Next in Menu | Toggle Scan/Connected Modes
  * `GPIO 25` (Bottom Button 1) : Select BSSID | Toggle Hi-Rez Plot Generation
  * `GPIO 6` (External Trigger Button 0) : Short press (Connect/Download) | Long press (Disconnect)



### Sample console output for pi_yagi_uda.py


### Power draw TODO UPDATE
* Scanning Mode   : 0.25A, 1.31W @ 5.22V
* Radar Graph UI  : 0.29A, 1.51W @ 5.22V
* Idle            : 0.15A, 0.77W @ 5.22V

### Usage:
  in terminal, python3 pi_yagi_uda.py
  can also run from PyCharm

---

Three other Python telemetry and scanning tools for measuring 2.4GHz Wi-Fi signals on a Raspberry Pi Zero 2 W. 

### LCD Display Tools with directional antenna:
1. **`pi_wifi_scan_rssi.py`** – The primary script runs on a Raspberry Pi Zero 2 W (Linux) to continuously scan all available 2.4 GHz Wi-Fi networks.

### Console-Only Tools:
2. **`pi_wifi_rssi_quality_rxrate.py`** – High-frequency terminal monitor tracking RSSI, Link Quality, and RX Bitrate (download rate from AP) for the connected network.
3. **`pi_wifi_rssi_quality_rxrate_curses.py`** – Full-screen `curses` terminal dashboard providing flicker-free, in-place metric updates.

---

todo: update

### Power draw. TODO UPDATE
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



## pi_wifi_rssi_quality_rxrate.py

On Raspberry Pi Zero 2 W, repeatedly measure and print RSSI, Link Quality,
and RX Bit Rate of the currently connected network on interface wlan0.

Prototype for tracking signal vectors using a directional Yagi_Uda antenna.
Reads metrics continuously to signal strength changes.

### Power draw
0.21a @ 5.22v (1.2w)

### Usage:
in terminal, python3 pi_wifi_rssi_quality_rxrate.py
can also run in PyCharm

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

      


### Analysis TECHTOO Wi-Fi Yagi Uda Antenna

Analysis of TECHTOO 2.4 GHz Wi-Fi Yagi-Uda Antenna 2.4GHz with u.FL TO RP-SMA 4.1"

![image](../assets/images/techtoo_yagi-uda_4in1_pigtail_nanoVNA-100926.png "Yagi Uda Analysis")