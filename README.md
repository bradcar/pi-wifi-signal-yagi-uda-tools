
# WiFi Signal Tools for Pi Zero 2 W

Rour tools for measuring WiFi signals. Very preliminary work in progress!

1) pi_wifi_scan_rssi.py - scans all 2.4 GHz networks getting rssi signal strength
2) pi_wifi_rssi_quality_txrate.py - get quality of the connected network
   1) Note: macOS measures SNR & Noise and not quality and TxRate
3) pi_wifi_rssi_quality_txrate_curses.py - Curses version of above
4) pi_yagi_uda.py - measurs signal strength of connected network using directional Yagi-Uda Antenna and IMU.

## pi_wifi_scan_rssi.py 

Scans and only measures RSSI on available 2.4GHz WiFis (not 5GHz or 6GHz). Runs on Raspberry Pi Zero 2 W in Linux
Scans repeatedly, sorted by strongest RSSI first.

Quality or Tx bitrates on unconnected networks. For connected network use: pi_wifi_rssi_quality_txrate.py

### Power draw
0.16a @ 5.22v (0.82w)

### Usage:
  in terminal, python3 mac_wifi_scan_rssi.py
  can also run in pycharm

### Sample output pi_wifi_scan_rssi.py

    SSID                    Band    BSSID             RSSI      Bars
    ------------------------------------------------------------------
    ABox-PDX                2.4 GHz B6:39:56:91:1D:0F  -20 dBm  4 bars
    CenturyLink7697         2.4 GHz 08:26:97:62:38:DC  -22 dBm  4 bars
    <hidden>                2.4 GHz BA:39:56:91:1D:0F  -23 dBm  4 bars
    ABox-PDX                2.4 GHz 0E:02:8E:9E:7D:C3  -55 dBm  3 bars
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

Also a Curses version:
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
and Tx Bit Rate of the currently connected network on interface wlan0. 
When connected to a Yagi-Uda Antenna and an IMU we can use this to locate the WiFi source.

It prints the results to std out and an OLED display.
It graphically shows the signal strength at a compass direction.
This is also shown graphically in a small radar screen graphic.
It gracefully handles total connection drops and resumes automatically on reconnect.

### Power draw
TODO update
~~0.21a @ 5.22v (1.2w)~~

### Usage:
in terminal, python3 pi_yagi-uda.py
can also run in pycharm

### Sample output pi_wifi_rssi_quality_txrate.py
    WiFi Signal Monitor (Pi Zero): ABox-PDX
    SSID:    ABox-PDX
    RSSI:    -24 dBm  4 bars
    Link Q:  70/70    Hi Quality
    Tx Rate: 65.0 Mb/s
    Sweep Vector Angle: 170.0° --> Mock RSSI: -23.3 dBm
    Compass Heading: n/a
    Updates:  245.2 msec, 4 Hz
    Clock: 2026-05-25 17:27:47

### NOTES

1. Python MUST be enabled in System Settings > Privacy & Security> Location Services.

2. iwlist sudo
   1. Give the iwlist program setuid root permissions
   sudo chmod u+s /usr/sbin/iwlist
   2. Verify the permissions changed successfully
   ls -l /usr/sbin/iwlist


### PyCharm Remote Deployment Reset Guide

On renaming my project and pushing to GitHub, PyCharm's internal tracking broke, making remote development on the Raspberry Pi incredibly difficult.
The PyCharm SSH remote interpreter insisted on running code out of a randomized path like `/tmp/<randomstring>/` instead of the project's actual remote directory.
It also occasionally threw ghost credential errors.

To completely reset PyCharm's global and project-level memory, follow these steps:


Step 1: Remove Old Remote Configurations:
Before wiping the caches, strip out all active links to the remote target within the PyCharm UI:

* **Python Interpreters:** Go to `Settings/Preferences` ➔ `Project` ➔ `Python Interpreter`. Click **Show All...**, highlight any remote interpreters, and click the **- (Minus icon)** until the list is blank. Click **Apply**.
* **Deployment Servers:** Go to `Tools` ➔ `Deployment` ➔ `Configuration`. Highlight any server profiles in the left column and click the **- (Minus icon)** until it's completely empty. Click **Apply**.
* **SSH Configurations:** Go to `Tools` ➔ `SSH Configurations`. Delete every single entry here using the **- (Minus icon)**. Click **Apply** and **OK**.

Step 2: Purge Cache & Configuration Files:
Quit PyCharm completely. Open the laptop Terminal, navigate to local project directory, and run the following to destroy the local project database and global JetBrains application caches:

```bash
rm -rf .idea

rm -rf ~/Library/Caches/JetBrains/PyCharm*/remote_sources/
rm -rf ~/Library/Caches/JetBrains/PyCharm*/project_caches/
```
Step 3: Pristine Re-Configuration (After Restarting navigate to your project):
1. Go to Tools ➔ Deployment ➔ Configuration.
   1. Click the + icon, select SFTP, and authenticate your SSH connection to the Pi.
   2. Switch to the Mappings tab. Set the Local path to your Mac project folder, and explicitly hardcode the Deployment path on your Pi (/home/pi-admin/pi-wifi-signal-yagi-uda-tools).
   3. Click the Checkmark icon (Set as Default) above the server list, then click Apply.
2. Add the Remote Interpreter:
   1. Go to Project ➔ Python Interpreter ➔ Add Interpreter ➔ On SSH...
   2. Select Existing configuration and choose the SFTP deployment server you just created.
   3. On the final configuration screen, ensure the Python interpreter path is correct (/usr/bin/python3) and double-check that the folder synchronization path matches your permanent home directory on the Pi, rather than a /tmp/ directory. Click Finish.
3. Trigger Initial Manual Sync:
   1. Right-click your top-level project folder in the PyCharm project sidebar.
   2. Select Deployment ➔ Upload to... and choose your Pi. Wait for the file transfer to complete.
4. Create a Dedicated Run Configuration:
   1. Click the run dropdown in the top-right corner of PyCharm and select Edit Configurations...
   2. Click + ➔ Python.
   3. Set the Script path to your primary local execution script.
   4. Ensure the Python interpreter is set to your newly created Remote SSH instance.
   5. Set the Working directory explicitly to your permanent project folder on the Pi.
   6. Click Apply and OK.

Click the green Play arrow. The execution pipeline will now bypass the broken automated tracking layer, running your code natively out of its true remote directory.