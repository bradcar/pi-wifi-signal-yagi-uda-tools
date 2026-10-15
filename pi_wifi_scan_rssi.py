#
"""
pi-wifi-scan_rssi.py

Runs on Raspberry Pi Zero 2 W in Linux. Repeatedly scans all available 2.4GHz Wi-Fi
networks (not 5GHz or 6GHz) and sorts them by strongest RSSI first. When paired with an
LIS3MDL magnetometer, 360° polar plots are constructed to map signal strength against
physical headings for spatial Wi-Fi signal tracking. Pi Zeros only probe 2.4 GHz.

Operational Modes:
    * Scan Mode (Default / Menu Selection):
      - Scans for Wi-Fi networks via Linux wpa_supplicant / system utilities.
        - Unfortunately, No Quality nor RX bitrates on unconnected networks.
        - For connected network use: pi_wifi_rssi_quality_rxrate.py
      - Tracks 360° RSSI history across all discovered BSSIDs.
      - Update RSSI values ONLY when stronger than previous values.
      - Displays interactive table on the WaveShare Triple LCD Display.
      - Polling Cadence: ~1 Hz (940 ms period) on Pi Zero 2 W.
    * Polar Radar Plot Mode (Lo-Rez Real-Time Visualizer):
      - Live rendering of 360° polar RSSI strength distribution for a targeted BSSID.
      - Automatically identifies peak(s) signal directions. Uses red arc to highlight multiple peaks with same value.
      - Display Updates: Real-time polar graph rendering on 240x240 center display.
    * High-Resolution Export Mode (Hi-Rez Matplotlib Plotter):
      - Generates auto-scaled, publication-quality 1° polar plots via Matplotlib.
      - Automatically exports raw 360° degree-by-dBm telemetry to structured CSV files.
      - Render Time: ~20 seconds per high-resolution file generation.
      - Creates .pdf

Display Layouts & Hardware Mapping:
    * WaveShare Triple LCD Display (ST7789 Drivers, rotated 180° / USB at bottom):
      - Left Display  (disp_0): 160px x  80px (12,800 px)
      - Center Display(disp_2): 240px x 240px (57,600 px)
      - Right Display (disp_1): 160px x  80px (12,800 px)
    * Button Mapping - Display buttons next to left display (gpiozero with active on Pi pull-ups):
      - On-screen metric extraction for peak RSSI, peak angle, and signal cluster counting.
      - Legacy SSD1305 OLED display support (monochrome fallback).

Sensors & Integration:
    * LIS3MDL 3-axis I2C magnetometer for compass headings for external direction antenna.
    * On-chip Temperature monitoring to protect Pi Zero 2 W against thermal limits.

NOTES:
  1) Python MUST be enabled in System Settings > Privacy & Security> Location Services.

Usage:
  in terminal, python3 mac_wifi_scan_rssi.py
  can also run in PyCharm

Power Draw:
    Scanning:    0.25a, 1.31w, 5.22v
    Radar Graph: 0.29a, 1.51w, 5.22v
    Idle:        0.15a, 0.77w, 5.22v

Legacy Displays:
    * OLED monochrome display are slow.
    * E-Ink B&W has 2-3 sec full refresh which is way too slow.

Other GPIO:
    pin 1 - GPIO 1 3v3 (Red)
    pin 3 - GPIO 2 SDA - I2C (Blue)
    pin 5 - GPIO 3 SCL - I2C (Yellow)
    pin 7 - GND	—	(Black)
    GPIO 6 - trigger
    GPIO 25, 26 Buttons

WaveShare Defintions
    Signal	Board Pin No.	Broadcom GPIO	Function / Assignment
    VCC pin 1   3.3V	—	3.3V Power
    GND	pin 7   GND	—	Ground
    MOSI1	Pin 38	GPIO 20	SPI1 MOSI (center display)
    MOSI0	Pin 19	GPIO 10	SPI0 MOSI (left/right displays)
    SCLK1	Pin 40	GPIO 21	SSPI1 SCLK (center display)
    SCLK0	Pin 23	GPIO 11	SPI0 SCLK (left/right displays)
    CS0	Pin 12	GPIO 18	SPI1 Chip Select 0 (1.3" Main Screen 0)
    CS1	Pin 24	GPIO 8	SPI0 Chip Select 1 (0.96" Screen 1)
    CS2	Pin 26	GPIO 7	SPI0 Chip Select 2 (0.96" Screen 2)
    DC0	Pin 15	GPIO 22	Data/Command Control (1.3" Main Screen 0)
    DC1	Pin 7	GPIO 4	Data/Command Control (0.96" Screen 1)
    DC2	Pin 29	GPIO 5	Data/Command Control (0.96" Screen 2)
    RST0	Pin 13	GPIO 27	HHardware Reset (1.3" Main Screen 0)
    RST1	Pin 18	GPIO 24	Hardware Reset (0.96" Screen 1)
    RST2	Pin 16	GPIO 23	Hardware Reset (0.96" Screen 2)
    BL0	Pin 35	GPIO 19	Backlight PWM/Control (1.3" Main Screen 0)
    BL1	Pin 33	GPIO 13	Backlight PWM/Control (0.96" Screen 1)
    BL2	Pin 32	GPIO 12	Backlight PWM/Control (0.96" Screen 2)
    KEY1	Pin 22	GPIO 25	Bottom User Button 1
    KEY2	Pin 37	GPIO 26	Top User Button 2

Free pins:
    GPIO 9 (Physical Pin 21 / SPI0 MISO) — Free (SPI0 is transmit-only for these LCDs, so MISO isn't used by the HAT).
    GPIO 14 (Physical Pin 8 / UART TX) — Free GPIO or Serial TX.
    GPIO 15 (Physical Pin 10 / UART RX) — Free GPIO or Serial RX.
    GPIO 16 (Physical Pin 36) — Free general-purpose GPIO.
    GPIO 17 (Physical Pin 11) — Free general-purpose GPIO.

TODOs:


"""
import subprocess
import time

from datetime import datetime
from pathlib import Path

import board
import busio
import numpy as np
from PIL import Image, ImageDraw
from busio import I2C
from gpiozero import Button

import lib.lcd_st7789_utils as lcd
from lib.lcd_rssi_radar_utils import display_rssi_polar_radar_lcd, extract_radar_metrics
from lib.lcd_st7789_utils import create_lcd_display_canvases
from lib.lis3mdl_utils import init_lis3mdl, get_compass_heading_hard_soft_corrections
from lib.oled_1305_utils import init_oled_display, clear_display_oled
from lib.pi_zero_utils import pico_temperature, timeout, celsius_to_fahrenheit
from lib.matplot_rssi_radar_utils import plot_rssi_polar_matplotlib
from lib.wifi_utils import init_wifi, scan_target_ssid, map_band_to_string, rssi_to_string, rssi_to_bars, \
    channel_to_frequency, trigger_background_scan

DEBUG = False
BLOCK_0_BAR = True
BLOCK_NON_2_4_G = True  # Pi Zero 2 W only works 2.4 GHz Wi-Fi

button1_pressed = False
button2_pressed = False
button1 = None
button2 = None


def button1_callback():
    global button1_pressed
    button1_pressed = True


def button2_callback():
    global button2_pressed
    button2_pressed = True


def init_buttons():
    global button1, button2
    button1 = Button(25, pull_up=True, bounce_time=0.1)
    button2 = Button(26, pull_up=True, bounce_time=0.1)
    button1.when_pressed = button1_callback
    button2.when_pressed = button2_callback
    print("Button 1 & 2 Listeners Active (GPIO 25 & 26) for Press")


def init_i2c() -> tuple[bool, I2C, bool]:
    # Initialize Display and Magnetometer
    i2c1 = busio.I2C(board.SCL, board.SDA)
    devices1 = i2c1.scan()

    oled_detected = 0x3C in devices1
    lis3mdl_detected = (0x1C in devices1) or (0x1E in devices1)
    print(f"{oled_detected=}, {lis3mdl_detected=}")
    return i2c1, lis3mdl_detected, oled_detected


def update_bssid_map(data, heading, bssid_map):
    """
    Updates the persistent bssid_map with current rssi data. If ssid is unknown it will be updated in later
    scans as soon as ssid is found.

    Use None when there is no signal.
    """
    heading = int(heading % 360) if heading is not None else None
    hidden_placeholders = {"<hidden>", "Unknown", "", None}

    # Track which BSSIDs were seen in THIS specific scan cycle
    seen_bssids_this_scan = set()

    for net in data:
        bssid = net.bssid() or "Unknown"
        ssid = net.ssid() or "<hidden>"
        rssi = net.rssi_value()

        seen_bssids_this_scan.add(bssid)

        if bssid not in bssid_map:
            bssid_map[bssid] = {"ssid": ssid, "rssi_history": [None] * 360}
        else:
            current_stored = bssid_map[bssid]["ssid"]
            if current_stored in hidden_placeholders and ssid not in hidden_placeholders:
                bssid_map[bssid]["ssid"] = ssid

        if heading is not None and rssi is not None:
            old_rssi = bssid_map[bssid]["rssi_history"][heading]
            if old_rssi is None or old_rssi < rssi:
                bssid_map[bssid]["rssi_history"][heading] = rssi
        elif rssi is not None:
            old_rssi = bssid_map[bssid]["rssi_history"][0]
            if old_rssi is None or old_rssi < rssi:
                bssid_map[bssid]["rssi_history"] = [float(rssi)] * 360


def prepare_polar_plot_matplotlib(bssid, bssid_info, heading, lcd_png_generate,
                                  file_name="plot.png"):
    """ Set up data for plot_rssi_polar call"""
    rssi_array = np.array(bssid_info["rssi_history"])
    degrees = np.arange(360)

    theta = np.deg2rad(degrees)
    subtitle = f"{bssid_info['ssid']}"

    # 3.5 sec for lcd_png_generate=True,  #7.5 sec for lcd_png_generate=False
    return plot_rssi_polar_matplotlib(degrees, rssi_array, theta, heading, subtitle, lcd_png_generate,
                                      file_name=file_name)


def console_print(data, heading):
    """ Prints the scan results to the terminal """
    print(f"{'SSID':<23} {'Band':<7}  {'BSSID':<17}  {'Chan'}   {'RSSI':<8} {'Bars'}")
    print("-" * 74)

    if not data:
        print("       ...No networks found...")
        return

    for net in data:
        ssid = net.ssid() or "<hidden>"
        bssid = net.bssid() or "Unknown"
        rssi = net.rssi_value()
        band = map_band_to_string(net)
        rssi_string = rssi_to_string(rssi)
        channel = net.channel() if hasattr(net, 'channel') else "??"
        freq = channel_to_frequency(channel, band)

        truncated_ssid = ssid[:21] + "~" if len(ssid) > 22 else ssid

        if not (BLOCK_0_BAR and rssi <= -80) and not (BLOCK_NON_2_4_G and band != "2.4 GHz"):
            print(f"{truncated_ssid:<23} {band:<7}  {bssid}  ch={channel:<2} {rssi:>4} dBm  {rssi_string}")

    print(f"==> Heading direction: {heading:.0f}°" if heading is not None else " ** no compass **")


def oled_display_update(draw, font, image, oled_display, data, heading):
    """ Legacy OLED display - unfortunately refresh too slow."""
    if oled_display is None:
        return

    try:
        clear_display_oled(oled_display, draw, image)

        if heading is not None:
            draw.text((0, 0), f"dir: {heading:.0f}°", font=font, fill=1)
        else:
            draw.text((0, 0), f"no compass", font=font, fill=1)
        draw.text((86, 0), f"{datetime.now().strftime('%H:%M:%S')}", font=font, fill=1)

        y = 8
        for net in (data or [])[:3]:
            ssid = (net.ssid() or "<hidden>")[:10]
            rssi = net.rssi_value()
            num_bars = rssi_to_bars(rssi)
            bar_string = ("*" * num_bars).ljust(4)

            draw.text((0, y), f"{ssid:<10}", font=font, fill=1)
            draw.text((7 * 8 + 1, y), f"{rssi:>4} dbm", font=font, fill=1)
            draw.text((12 * 8 + 4, y), f"{bar_string}", font=font, fill=1)
            y += 8

        oled_display.image(image)
        oled_display.show()
    except Exception as e:
        print(f"OLED write error: {e}")


def update_metrics_lcd_display(disp_1, peak_rssi, peak_degree, peak_cluster):
    """
    Update the display metrics

    Relies on side effect of peak_count == 360 to denote no magnetometer
    """
    image1 = Image.new("RGB", (disp_1.width, disp_1.height), "black")
    lcd.print_270(text="Peak", pos=(132, 0), image=image1, font=lcd.font0_34pt, color="red")

    rssi_text = f"{peak_rssi:.0f}" if peak_rssi is not None else "no dBm"
    lcd.print_270(text=rssi_text, pos=(84, 2), image=image1, font=lcd.font0_50pt, color="red")

    peak_count = len(peak_cluster) if peak_cluster is not None else 0

    # If peak_count is 360 then it is omnidirectional so rename it to one peak
    if peak_count > 0 and peak_count != 360:
        degree_text = f"{peak_degree:.0f}°" if peak_degree is not None else "? °"
        lcd.print_270(text=degree_text, pos=(48, 8), image=image1, font=lcd.font0_34pt, color="red")
        peak_text = f"{peak_count:.0f} peak{'s' if peak_count != 1 else ''}"
        lcd.print_270(text=peak_text, pos=(18, 2), image=image1, font=lcd.font0_20pt, color="red")

    disp_1.ShowImage(image1)


def update_menu_lcd_display(disp_0, items):
    """
    update_menu_lcd_display to draw text items on Display 0.
    Items format: list of tuples -> (text, pos_tuple, font, color)
    """
    image0 = Image.new("RGB", (disp_0.width, disp_0.height), "black")
    for text, pos, font, color in items:
        lcd.print_270(text=text, pos=pos, image=image0, font=font, color=color)
    disp_0.ShowImage(image0)


def lcd_display_update(disp_0, disp_1, disp_2, data, heading):
    """Print scan results across the triple LCD HAT displays."""
    if not (disp_0 and disp_1 and disp_2):
        return

    try:
        time_str = datetime.now().strftime("%H:%M:%S")
        heading_str = f"{heading:.0f}°" if heading is not None else "? °"
        dir_str = f"dir: {heading:.0f}°" if heading is not None else "no compass"

        # Screen 0: Interactive Menu Option, to tp
        update_menu_lcd_display(disp_0, [
            ("Plot", (137, 0), lcd.font0_28pt, "yellow"),
            ("RSSI?", (113, 0), lcd.font0_28pt, "yellow"),
            ("Exit w/", (72, 0), lcd.font0_24pt, "yellow"),
            ("Plots ?", (47, 0), lcd.font0_24pt, "yellow")
        ])

        # Screen 1: Heading & Clock
        image1 = Image.new("RGB", (disp_1.width, disp_1.height), "black")
        lcd.print_270(f"heading=", pos=(132, 0), image=image1, font=lcd.font0_16pt, color="yellow")
        lcd.print_270(heading_str, pos=(104, 10), image=image1, font=lcd.font0_28pt, color="yellow")
        lcd.print_270(time_str, pos=(2, 0), image=image1, font=lcd.font0_20pt, color="yellow")
        disp_1.ShowImage(image1)

        # Screen 2: Center Display: Table of current Wi-Fi RSSI signal strenghs
        image2 = Image.new("RGB", (disp_2.width, disp_2.height), "black")
        lcd.print_270(dir_str, pos=(240, 0), image=image2, font=lcd.font0_20pt, color="yellow")
        lcd.print_270(time_str, pos=(240, 200), image=image2, font=lcd.font0_20pt, color="yellow")

        y = 210
        headers = [("SSID", 2, lcd.font0_24pt), ("dBm", 129, lcd.font0_20pt),
                   ("bar", 177, lcd.font0_20pt), ("ch", 213, lcd.font0_20pt)]
        for label, x, font in headers:
            lcd.print_270(label, pos=(y, x), image=image2, font=font, color="yellow")

        y -= 24

        for net in (data or []):
            rssi = net.rssi_value()
            band = map_band_to_string(net)

            if (BLOCK_0_BAR and rssi <= -80) or (BLOCK_NON_2_4_G and band != "2.4 GHz"):
                continue

            ssid = net.ssid() or "<hidden>"
            truncated_ssid = ssid[:9] + "." if len(ssid) > 9 else ssid
            channel = net.channel() if hasattr(net, 'channel') else "??"
            bar_string = ("*" * rssi_to_bars(rssi)).ljust(4)

            lcd.print_270(f"{truncated_ssid:<10}", pos=(y, 2), image=image2, font=lcd.font0_24pt, color="white")
            lcd.print_270(f"{rssi:>4}", pos=(y, 132), image=image2, font=lcd.font0_24pt, color="yellow")
            lcd.print_270(bar_string, pos=(y, 176), image=image2, font=lcd.font0_20pt, color="white")
            lcd.print_270(f"{channel:>2}", pos=(y, 213), image=image2, font=lcd.font0_24pt, color="white")

            y -= 24

        disp_2.ShowImage(image2)
    except Exception as e:
        print(f"Display write error (LCD ignored): {e}")


def lcd_choose_ssid(lcd, disp_0, disp_1, disp_2, bssid_map):
    """choose SSID with scrolling window and automatic wrap-around using persistent map data"""
    global button1_pressed, button2_pressed

    # Screen 0: Menu options "Next" and "Select"
    update_menu_lcd_display(disp_0, [
        ("Next", (127, 0), lcd.font0_28pt, "green"),
        ("Select", (62, 0), lcd.font0_24pt, "yellow")
    ])

    # Screen 1: Time
    image1 = Image.new("RGB", (disp_1.width, disp_1.height), "black")
    lcd.print_270(text=f"{datetime.now().strftime('%H:%M:%S')}", pos=(2, 0), image=image1, font=lcd.font0_20pt,
                  color="yellow")
    disp_1.ShowImage(image1)

    # filter out networks with no RSSI data
    filtered_networks = []
    for bssid, info in (bssid_map or {}).items():
        valid_signals = [v for v in info["rssi_history"] if v is not None and v > -99.0]
        if not valid_signals:
            continue
        rssi = max(valid_signals)

        if BLOCK_0_BAR and rssi <= -80:
            continue

        filtered_networks.append({"bssid": bssid, "ssid": info["ssid"] or "<hidden>", "rssi": rssi})

    # Sort BSSIDs by RSSI strength, strongest first
    filtered_networks.sort(key=lambda x: x["rssi"], reverse=True)
    total_entries = len(filtered_networks)

    if total_entries == 0:
        # No Wi-Fi signal warning
        image2 = Image.new("RGB", (disp_2.width, disp_2.height), "black")
        lcd.print_270(text="No Wi-Fi Signals", pos=(120, 20), image=image2, font=lcd.font0_20pt, color="red")
        disp_2.ShowImage(image2)
        time.sleep(2)
        return None, None

    select = False
    idx_pick = 1
    max_visible_rows = 8

    while not select:
        image2 = Image.new("RGB", (disp_2.width, disp_2.height), "black")

        # sliding window start, and show title
        if idx_pick > max_visible_rows:
            start_idx = idx_pick - max_visible_rows
        else:
            start_idx = 0

        y = 210
        lcd.print_270(text="#  SSID           (RSSI)", pos=(y, 2), image=image2, font=lcd.font0_24pt, color="blue")
        y -= 24

        # show visible rows
        visible_chunk = filtered_networks[start_idx:start_idx + max_visible_rows]
        for local_i, net_dict in enumerate(visible_chunk):
            current_abs_idx = start_idx + local_i + 1
            ssid = net_dict["ssid"]
            rssi = net_dict["rssi"]

            # Selected row shown in yellow highlight
            pick_color = "yellow" if idx_pick == current_abs_idx else "white"
            lcd.print_270(text=f"{current_abs_idx:>2}", pos=(y, 2), image=image2, font=lcd.font0_24pt, color=pick_color)
            lcd.print_270(text=f"{ssid} ({rssi})", pos=(y, 2 * 14), image=image2, font=lcd.font0_24pt, color=pick_color)
            y -= 24

        disp_2.ShowImage(image2)

        # "Next" with button2
        if button2_pressed:
            button2_pressed = False
            idx_pick += 1
            if idx_pick > total_entries:
                idx_pick = 1

        # "Select" with button1
        if button1_pressed:
            button1_pressed = False
            chosen_net = filtered_networks[idx_pick - 1]
            target_bssid = chosen_net["bssid"]
            chosen_ssid = chosen_net["ssid"]
            print(f"\n Selected SSID: {chosen_ssid} ({target_bssid})")
            return target_bssid, chosen_ssid

        time.sleep(0.1)
    return None


def create_radar_png_csv_save(bssid, info, heading, plot_dir, timestamp, lcd_png_generate):
    """ create polar plot for BSSID, then saves png and CSV """
    # Create safe SSID and BSSID strings for file names
    processed_ssid = info["ssid"].replace(" ", "_")
    safe_ssid = "".join([c for c in processed_ssid if c.isalnum() or c in ("-", "_")]).strip()
    if not safe_ssid:
        safe_ssid = "Hidden_or_Unknown"

    bssid_str = str(bssid) if bssid is not None else "UnknownBSSID"
    safe_bssid = bssid_str.replace(":", "")

    # Normalize history data array: map None to your minimum plot floor (-99.0), clips to the center of the polar plot
    cleaned_history = [v if v is not None else -99.0 for v in info["rssi_history"]]
    info["rssi_history"] = cleaned_history
    valid_signals = [v for v in info["rssi_history"] if v is not None and v > -99.0]

    # Find strongest rssi dB and append to file name
    max_rssi = int(max(valid_signals)) if valid_signals else -99

    db_string = f"{max_rssi}_db"
    csv_file = plot_dir / f"{safe_ssid}_{safe_bssid}_{timestamp}_{db_string}.csv"
    png_file = plot_dir / f"{safe_ssid}_{safe_bssid}_{timestamp}_{db_string}.png"

    # Save CSV & plot
    print(f"\n *** Saving plot for: {safe_ssid}, with BSSID: {safe_bssid}, Max RSSI: {max_rssi}, dB-String: {db_string}")
    csv_data = np.column_stack((np.arange(360), cleaned_history))
    np.savetxt(csv_file, csv_data, fmt='%d,%.1f', header='degree,rssi', comments='')
    print(f"Saved csv: {csv_file}")

    # Create png plot
    start_time = time.time()
    polar_plot_image = prepare_polar_plot_matplotlib(bssid, info, heading, lcd_png_generate,
                                                     file_name=str(png_file))
    print(f"plot time = {(time.time() - start_time):.2f} secs")
    print(f"Plot file written: {png_file}")
    return polar_plot_image


def display_lcd_radar_ui(lcd, disp_0, disp_1, disp_2, ssid, heading, signal_history, peak_rssi, peak_degree,
                         peak_cluster,
                         has_valid_history):
    """
    Pure rendering function: Draws the UI layers onto screens 0, 1, and 2.
    """
    # Screen 2: Radar graph & annotations
    image2 = Image.new("RGB", (disp_2.width, disp_2.height), "black")
    disp2_draw = ImageDraw.Draw(image2)

    # Unpack calculations directly through the consolidated utility pipeline
    peak_rssi = peak_rssi if has_valid_history else None
    peak_deg = peak_degree if has_valid_history else None
    peak_clust = peak_cluster if has_valid_history else None

    # Screen 2: Draw graph of data
    display_rssi_polar_radar_lcd(
        disp2_draw,
        cadence_fill=None,
        heading=heading,
        signal_history=signal_history,
        connected=True,
        peak_degree=peak_deg,
        peak_rssi=peak_rssi,
        peak_cluster=peak_clust
    )

    # Annotate Polar Plot Text
    # Screen 2: Black-out patch on Radar for Peak RSSI and Peak degree, SSID
    disp2_draw.rectangle([209, 0, 240, 55], fill="black")
    lcd.print_270(text=f"{peak_rssi:.0f}", pos=(210, 0), image=image2, font=lcd.font0_34pt, color="black")
    disp2_draw.rectangle([212, 180, 240, 240], fill="black")
    lcd.print_270(text=f"{peak_degree:.0f}°", pos=(213, 178), image=image2, font=lcd.font0_28pt, color="black")
    lcd.print_270(text=f"{ssid}", pos=(0, 0), image=image2, font=lcd.font0_20pt, color="yellow")
    disp_2.ShowImage(image2)

    # Screen 0 Left Display: Menu option for LCD plot
    update_menu_lcd_display(disp_0, [
        ("Scan?", (127, 0), lcd.font0_24pt, "yellow"),
        ("Hi-Rez", (70, 0), lcd.font0_24pt, "yellow"),
        (" is 20s", (45, 0), lcd.font0_24pt, "yellow"),
        (" wait !", (20, 0), lcd.font0_24pt, "yellow")
    ])

    # Screen 1 Right Display: Metrics - Compass, Peak RSSI metrics, and clock
    update_metrics_lcd_display(disp_1, peak_rssi, peak_deg, peak_clust)


def plot_bssid_lcd(disp_0, disp_1, disp_2, bssid_map, menu_ssid, target_bssid, lis3mdl):
    global button1_pressed, button2_pressed

    button1_pressed = False
    button2_pressed = False

    if target_bssid not in bssid_map:
        print(f"ERROR: Selected BSSID {target_bssid} ({menu_ssid}) dropped out of map before plotting!")
        return

    raw_history = bssid_map[target_bssid]["rssi_history"]
    ssid = bssid_map[target_bssid]["ssid"]

    if ssid in {"", None}:
        print(f"ERROR: '{ssid}' for Selected BSSID {target_bssid}!")
        return

    # Normalize None values to -99.0 so NumPy can process
    signal_history = [v if v is not None else -99.0 for v in raw_history]

    peak_rssi, peak_degree, peak_cluster, has_valid_history = extract_radar_metrics(signal_history)
    hi_rez_active = False
    i = 1

    # Screen 0 - Menu options - Left-most screen
    update_menu_lcd_display(disp_0, [
        ("Scan?", (127, 0), lcd.font0_24pt, "yellow"),
        ("Hi-Rez", (70, 0), lcd.font0_24pt, "yellow"),
        (" ~20s !", (45, 0), lcd.font0_24pt, "yellow")
    ])

    # Screen 1 - Metrics: Peak RSSI & Peak degree right-most screen
    update_metrics_lcd_display(disp_1, peak_rssi, peak_degree, peak_cluster)

    while True:
        start_time = time.time()

        # Hi-Rez is static, so slow polling
        if hi_rez_active:
            time.sleep(0.1)

        # Lo-Rez RADAR plot
        if not hi_rez_active:
            raw_heading = get_compass_heading_hard_soft_corrections(lis3mdl) if lis3mdl else None
            heading = raw_heading if raw_heading is not None else 0.0

            # Screen 2: plot radar - large center screen
            image2 = Image.new("RGB", (disp_2.width, disp_2.height), "black")
            disp2_draw = ImageDraw.Draw(image2)

            display_rssi_polar_radar_lcd(
                disp2_draw,
                cadence_fill=None,
                heading=heading,
                signal_history=signal_history,
                connected=True,
                peak_degree=peak_degree,
                peak_rssi=peak_rssi,
                peak_cluster=peak_cluster,
                magnetometer=lis3mdl
            )
            # Annotate text overlay for screen 2
            disp2_draw.rectangle([209, 0, 240, 55], fill="black")
            lcd.print_270(text=f"{peak_rssi:.0f}dB" if peak_rssi is not None else "---", pos=(210, 0), image=image2,
                          font=lcd.font0_34pt, color="red")
            disp2_draw.rectangle([212, 180, 240, 240], fill="black")
            lcd.print_270(text=f"{ssid}", pos=(0, 0), image=image2, font=lcd.font0_20pt, color="yellow")

            # If no Magnetometer show "No Compass"
            if lis3mdl is not None:
                lcd.print_270(text=f"{peak_degree:.0f}°" if peak_degree is not None else "---°", pos=(213, 178),
                              image=image2, font=lcd.font0_28pt, color="red")
            else:
                lcd.print_270(text="No", pos=(124, 101), image=image2, font=lcd.font0_24pt, color="red")
                lcd.print_270(text="Compass", pos=(93, 62), image=image2, font=lcd.font0_24pt, color="red")

            disp_2.ShowImage(image2)

        # Button 1: Hi-Rez Toggle
        if button1_pressed:
            button1_pressed = False

            if hi_rez_active:
                print("Resume low-resolution plotting...")
                hi_rez_active = False

                # Re-paint the default Screen 0 options when dropping back to lo-rez
                update_menu_lcd_display(disp_0, [
                    ("Scan?", (127, 0), lcd.font0_24pt, "yellow"),
                    ("Hi-Rez", (70, 0), lcd.font0_24pt, "yellow"),
                    (" ~20s !", (45, 0), lcd.font0_24pt, "yellow")
                ])
            else:
                print("Creating Hi Resolution auto-scaled plot with matplotlib...")
                hi_rez_active = True

                # Screen 0: Display waiting for Hi-Rez plot
                update_menu_lcd_display(disp_0, [
                    ("Hi-Rez", (70, 0), lcd.font0_24pt, "yellow"),
                    ("...wait-", (45, 0), lcd.font0_24pt, "yellow"),
                    ("ing", (20, 22), lcd.font0_24pt, "yellow")
                ])

                plot_dir = Path("logs_polar_plots")
                plot_dir.mkdir(exist_ok=True)
                timestamp = datetime.now().strftime('%Y-%m%d_%H-%M')

                bssid_info = bssid_map.get(target_bssid, {"ssid": ssid, "rssi_history": signal_history})
                lcd_png_generate = True
                hi_rez_image = create_radar_png_csv_save(target_bssid, bssid_info, heading, plot_dir, timestamp,
                                                         lcd_png_generate)

                if hi_rez_image:
                    print("LCD Display 2 shows auto-scaled high-resolution plot...")
                    lcd_image = hi_rez_image.convert("RGB").resize((disp_2.width, disp_2.height))
                    lcd_image = lcd_image.rotate(270)
                    disp_2.ShowImage(lcd_image)

                    # Screen 0: Menu for return to scan or return to Lo-Rez plots - left-nost screen
                    update_menu_lcd_display(disp_0, [
                        ("Scan?", (127, 0), lcd.font0_24pt, "yellow"),
                        ("Back", (60, 0), lcd.font0_24pt, "yellow"),
                        ("to Lo-", (35, 0), lcd.font0_24pt, "yellow"),
                        ("Rez?", (10, 0), lcd.font0_24pt, "yellow")
                    ])
                else:
                    print("Error: Plot generation invalid image buffer reference.")
                    hi_rez_active = False

        # Button 2: return to scanning
        if button2_pressed:
            button2_pressed = False
            print("Returning to Wi-Fi scanning...")
            break


def main():
    global button1_pressed, button2_pressed
    last_update = time.time()

    print("Start Pi Wi-Fi scan:")
    wifi_interface = init_wifi()
    subprocess.run(["sudo", "ip", "link", "set", wifi_interface, "up"])

    # bssid_map Stores {bssid: {"ssid": "Name", "rssi_history": [-99]*360}}
    bssid_map = {}

    i2c1, lis3mdl_detected, oled_detected = init_i2c()

    oled_display, draw, font, image = None, None, None, None
    if oled_detected:
        try:
            oled_display, draw, font, image = init_oled_display(i2c1, use_mono_type=False)
        except Exception as e:
            print(f"Warning: Failed to initialize OLED display: {e}")
            oled_detected = False

    lcd_detected = False
    disp_0, disp_1, disp_2 = None, None, None

    try:
        disp_0, disp_1, disp_2 = create_lcd_display_canvases("radiant-ether-913.jpg")
        lcd_detected = True
        print("Triple LCD Display initialized.")
    except Exception as e:
        print(f"Warning: LCD hardware not connected or failed to initialize: {e}")
        lcd_detected = False

    # Initialize GPIO Buttons SECOND (after LCD claims SPI/GPIO pins)
    init_buttons()

    if not oled_detected and not lcd_detected:
        print("\n -- Running in Console-Only Mode --")

    lis3mdl = None
    if lis3mdl_detected:
        lis3mdl = init_lis3mdl(i2c1)

    # Fill Wi-Fi cache once before starting
    print("Pre-warming Wi-Fi cache...")
    trigger_background_scan(wifi_interface)
    if oled_detected and oled_display and draw:
        try:
            draw.text((0, 0), "Warming Wi-Fi cache", font=font, fill=1)
            oled_display.image(image)
            oled_display.show()
        except (OSError, IOError):
            # Skip if OLED not present, this is typical path
            pass

    try:
        duration = 0.0
        temp_duration = 0.0
        start_time = time.time()
        pi_celsius = pico_temperature() or 0.0

        while True:
            temp_duration += duration
            if temp_duration > 60.0:
                print(f"Updated Temperature (sys call) after): {temp_duration:.1f} sec")
                pi_celsius = pico_temperature()
                temp_duration = 0.0
                if pi_celsius and pi_celsius > 60.0:
                    print(f"Warning: ** High Temp: {pi_celsius:.1f}°C")

            wifi_data = None
            try:
                with timeout(3, "Wi-Fi scan timed out!"):
                    wifi_data = scan_target_ssid(wifi_interface)
            except TimeoutError:
                print("Wi-Fi hang detected. Reset interface...")
                subprocess.run(["sudo", "nmcli", "device", "reconnect", "wlan0"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(0.5)
                continue

            success = bool(wifi_data)
            if success:
                heading = get_compass_heading_hard_soft_corrections(lis3mdl)
                update_bssid_map(wifi_data, heading, bssid_map)

                console_print(wifi_data, heading)
                if oled_detected:
                    oled_display_update(draw, font, image, oled_display, wifi_data, heading)
                if lcd_detected:
                    lcd_display_update(disp_0, disp_1, disp_2, wifi_data, heading)

                duration = time.time() - last_update
                last_update = time.time()

                above_80_rssi = sum(
                    1 for info in bssid_map.values()
                    if any(v is not None and v > -80.0 for v in info["rssi_history"])
                )

                print(
                    f"\n{'Only showing networks with >1-bar & 2.4GHz' if BLOCK_0_BAR else 'Only showing 2.4GHz networks'}")
                print(
                    f"  Tracking {above_80_rssi} of {len(bssid_map)} Networks, only {above_80_rssi} above -80 dBm (>1-bar)")
                print(f"  Clock: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"  Updates: {duration * 1000:.1f} msec, {1.0 / duration:.1f} Hz")
                print(f"  Pi Zero 2W temp: {pi_celsius:.1f}°C ({celsius_to_fahrenheit(pi_celsius):.0f}°F)\n")

            if button2_pressed:
                button2_pressed = False
                if lcd_detected:
                    target_bssid, menu_ssid = lcd_choose_ssid(lcd, disp_0, disp_1, disp_2, bssid_map)
                    if target_bssid:
                        print(f"Starting Radar Plot Mode for: {target_bssid}")
                        plot_bssid_lcd(disp_0, disp_1, disp_2, bssid_map, menu_ssid, target_bssid, lis3mdl)
                else:
                    print("Button pressed, but no LCD display is active.")

            if button1_pressed:
                button1_pressed = False
                if lcd_detected:
                    plot_directory_name = "logs_polar_plots"
                    plot_dir = Path(plot_directory_name)
                    plot_dir.mkdir(exist_ok=True)

                    timestamp = datetime.now().strftime('%Y-%m%d_%H:%M')
                    saved_count = 0
                    exit_heading = 0   # Set Heading for plots to  0° North

                    lcd_png_generate = False
                    hidden_placeholders = {"<hidden>", "Unknown", "", None}

                    for bssid, info in bssid_map.items():
                        # Extract valid signal history
                        valid_signals = [v for v in info["rssi_history"] if v is not None and v > -99.0]
                        if not valid_signals:
                            continue

                        max_rssi = max(valid_signals)
                        ssid = info.get("ssid")
                        bssid = info.get("bssid")

                        # Skip if SSID is hidden/unknown or peak RSSI is <= -85 dBm
                        if ssid in hidden_placeholders or max_rssi <= -85:
                            print(f"\n *** Not Saving plot for: {ssid}, with BSSID: {bssid}, Max RSSI: {max_rssi}")
                            continue

                        create_radar_png_csv_save(bssid, info, exit_heading, plot_dir, timestamp, lcd_png_generate)
                        saved_count += 1

                    print(f"Successfully saved {saved_count} plot(s) in '{plot_dir}'.")
                    print("Clean Exit.")

                    # --- Break out of Wi-Fi Signal Scanningloop, after saving plots, which exits progrm ---
                    break
                else:
                    print("Button pressed, but no LCD display is active.")


    except KeyboardInterrupt:
        print("\nKeyboardInterrupt detected.")


if __name__ == "__main__":
    main()
    print("\nExiting.")
