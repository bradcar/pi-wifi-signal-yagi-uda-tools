# pi-wifi-scan_rssi.py
"""
Pi hardware only measures RSSI on 2.4GHz WiFi (not 5GHz or 6GHz). Runs on Raspberry Pi Zero 2 W in Linux
Scans repeatedly, sorted by strongest RSSI first.

Hardware:
    * Waveshare: Triple LCD HAT for Raspberry Pi Zero/Zero W/Zero WH/2B/3B/3B+/4B
    * Onboard 1.3inch IPS LCD Main Screen
    * Dual 0.96inch IPS LCD Secondary Screens
    * 2x User-Defined Keys
    * SPI Communication


Features
    * Scans all Wi-Fi's and collects strength at direction
    * Displays 360° polar plot of RSSI data for each Wi-FI, fast best every 5° plot
    * Can Create Hi-Resolution .png of selected Wi-Fis every 1° plot
    * Outputs csv of 360° data for each Wi-Fi
    * Displays channel used by each
    *

Unfortunately, No Quality nor Tx bitrates on unconnected networks.
For connected network use: pi_wifi_rssi_quality_txrate.py

NOTES:
  1) Python MUST be enabled in System Settings > Privacy & Security> Location Services.

Usage:
  in terminal, python3 mac_wifi_scan_rssi.py
  can also run in PyCharm

TODO:

"""
import random
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
from lib.e_ink_utils import init_e_ink_display, refresh_e_ink_display, blank_canvas_e_ink
from lib.lcd_rssi_polar_utils import display_radar_lcd, extract_radar_metrics
from lib.lcd_st7789_utils import create_lcd_display_canvases
from lib.lis3mdl_utils import init_lis3mdl, get_compass_heading
from lib.oled_1305_utils import init_oled_display, clear_display_oled
from lib.pi_zero_utils import pico_temperature, timeout
from lib.matplot_rssi_polar_utils import plot_rssi_polar
from lib.wifi_utils import init_wifi, scan_target_ssid, map_band_to_string, rssi_to_string, rssi_to_bars, \
    channel_to_frequency, trigger_background_scan

DEBUG = False
BLOCK_0_BAR = True
BLOCK_NON_2_4_G = True  # Pi Zero 2 W shows only 2.4 GHz

button1_pressed = False
button2_pressed = False
button1 = Button(25, pull_up=True, bounce_time=0.1)
button2 = Button(26, pull_up=True, bounce_time=0.1)  # TODO CHANGE THIS TO 26 with LCD


def button1_callback():
    global button1_pressed
    button1_pressed = True


def button2_callback():
    global button2_pressed
    button2_pressed = True


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
    Updates the persistent bssid_map with current rssi data. If ssid is unknown it will updated in later
    scans if an ssid is found.
    """
    heading = int(heading % 360) if heading is not None else None

    # Wi-Fi partial state placeholder strings
    hidden_placeholders = {"<hidden>", "Unknown", "", None}

    for net in data:
        bssid = net.bssid() or "Unknown"
        ssid = net.ssid() or "<hidden>"
        rssi = net.rssi_value()

        if bssid not in bssid_map:
            bssid_map[bssid] = {
                "ssid": ssid,
                "rssi_history": [-99.0] * 360
            }
        else:
            # Overwrite placeholder when get SSID name
            current_stored = bssid_map[bssid]["ssid"]
            if current_stored in hidden_placeholders and ssid not in hidden_placeholders:
                bssid_map[bssid]["ssid"] = ssid

        # TODO REMOVE WHEN MAGNETOMETER IS INSTALLED
        heading = None

        if heading is not None:
            bssid_map[bssid]["rssi_history"][heading] = rssi
        else:
            # TODO REMOVE For testing: Make Random index of no magnetometer
            random_degree = random.randint(0, 300)
            fake_rssi = rssi
            # signals out of 20° (150-170°), reduce signal by -15 dBm
            if not (random_degree > 150 and random_degree < 170):
                fake_rssi -= 15
            if fake_rssi < -99:
                fake_rssi = -99
            bssid_map[bssid]["rssi_history"][random_degree] = fake_rssi


def prepare_and_plot(bssid, bssid_info, heading, rssi_min_plot=-80, rssi_max_plot=-40, file_name="plot.png"):
    rssi_array = np.array(bssid_info["rssi_history"])
    degrees = np.arange(360)

    theta = np.deg2rad(degrees)
    subtitle = f"{bssid_info['ssid']}"
    lcd_png_generate = True
    return plot_rssi_polar(degrees, rssi_array, theta, heading, subtitle, lcd_png_generate, file_name=file_name)


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

    print(f"  dir: {heading:.0f}°" if heading is not None else "  ** no compass **")


def oled_print(draw, font, image, oled_display, data, heading):
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


def e_ink_print(draw, font, image, epd_display, data, heading):
    """ Print for E-ink display """
    blank_canvas_e_ink(draw)

    if heading is not None:
        draw.text((1, 2), f"dir: {heading:.0f}°", font=font, fill=255)
    else:
        draw.text((1, 2), f"no compass", font=font, fill=255)

    draw.text((195, 2), f"{datetime.now().strftime('%H:%M:%S')}", font=font, fill=255)

    y = 22
    for net in (data or [])[:3]:
        ssid = (net.ssid() or "<hidden>")[:11]
        rssi = net.rssi_value()
        num_bars = rssi_to_bars(rssi)
        bar_string = ("*" * num_bars).ljust(4)
        bssid = net.bssid() or "Unknown"

        draw.text((2, y), f"{ssid:<14}", font=font, fill=255)
        draw.text((10 * 8, y), f"{rssi:>4} dbm", font=font, fill=255)
        draw.text((17 * 8 + 4, y), f"{bar_string}", font=font, fill=255)
        draw.text((23 * 8, y), f"{bssid}", font=font, fill=255)
        y += 16

    refresh_e_ink_display(epd_display, draw, image, partial=True)


def lcd_print(lcd, disp_0, disp_1, disp_2, data, heading):
    """ Print for LCD display """

    # Screen 0: Interactive menu option to Plot RSSI?
    image0 = Image.new("RGB", (disp_0.width, disp_0.height), "black")
    lcd.print_270(text="Plot", pos=(132, 0), image=image0, font=lcd.font0_28pt, color="green")
    lcd.print_270(text="RSSI?", pos=(108, 0), image=image0, font=lcd.font0_28pt, color="green")
    disp_0.ShowImage(image0)

    # Screen 1: Current Heading & time
    image1 = Image.new("RGB", (disp_1.width, disp_1.height), "black")
    if heading is not None:
        lcd.print_270(text=f"{heading:.0f}°", pos=(132, 0), image=image1, font=lcd.font0_28pt, color="yellow")
    else:
        lcd.print_270(text=f"? °", pos=(132, 0), image=image1, font=lcd.font0_28pt, color="yellow")
    lcd.print_270(text=f"{datetime.now().strftime('%H:%M:%S')}", pos=(2, 0), image=image1, font=lcd.font0_20pt,
                  color="yellow")
    disp_1.ShowImage(image1)

    image2 = Image.new("RGB", (disp_2.width, disp_2.height), "black")
    if heading is not None:
        lcd.print_270(text=f"dir: {heading:.0f}°", pos=(240, 0), image=image2, font=lcd.font0_20pt, color="yellow")
    else:
        lcd.print_270(text=f"no compass", pos=(240, 0), image=image2, font=lcd.font0_20pt, color="yellow")
    lcd.print_270(text=f"{datetime.now().strftime('%H:%M:%S')}", pos=(240, 200), image=image2, font=lcd.font0_20pt,
                  color="yellow")

    ssid_trim_length = 9
    y = 210
    lcd.print_270(text="SSID", pos=(y, 2), image=image2, font=lcd.font0_24pt, color="blue")
    lcd.print_270(text="dBm", pos=(y, 8 * 14 + 17), image=image2, font=lcd.font0_20pt, color="blue")
    lcd.print_270(text="bar", pos=(y, 12 * 14 + 9), image=image2, font=lcd.font0_20pt, color="blue")
    lcd.print_270(text="ch", pos=(y, 15 * 14 + 3), image=image2, font=lcd.font0_20pt, color="blue")
    y -= 24

    for net in (data or []):
        ssid = (net.ssid() or "<hidden>")
        rssi = net.rssi_value()
        band = map_band_to_string(net)
        channel = net.channel() if hasattr(net, 'channel') else "??"
        num_bars = rssi_to_bars(rssi)
        bar_string = ("*" * num_bars).ljust(4)
        bssid = net.bssid() or "Unknown"
        truncated_ssid = ssid[:ssid_trim_length] + "." if len(ssid) > ssid_trim_length else ssid

        if not (BLOCK_0_BAR and rssi <= -80) and not (BLOCK_NON_2_4_G and band != "2.4 GHz"):
            lcd.print_270(text=f"{truncated_ssid:<10}", pos=(y, 2), image=image2, font=lcd.font0_24pt, color="white")
            lcd.print_270(text=f"{rssi:>4}", pos=(y, 10 * 14 - 8), image=image2, font=lcd.font0_24pt, color="yellow")
            lcd.print_270(text=f"{bar_string}", pos=(y, 13 * 14 - 6), image=image2, font=lcd.font0_20pt, color="white")
            lcd.print_270(text=f"{channel:>2}", pos=(y, 15 * 14 + 3), image=image2, font=lcd.font0_24pt, color="white")

        y -= 24

    disp_2.ShowImage(image2)


def lcd_choose_ssid(lcd, disp_0, disp_1, disp_2, bssid_map):
    """choose SSID with scrolling window and automatic wrap-around using persistent map data"""
    global button1_pressed, button2_pressed

    # Screen 0: Menu options "Next" and "Select"
    image0 = Image.new("RGB", (disp_0.width, disp_0.height), "black")
    lcd.print_270(text="Next", pos=(127, 0), image=image0, font=lcd.font0_28pt, color="green")
    lcd.print_270(text="Select", pos=(60, 0), image=image0, font=lcd.font0_24pt, color="yellow")
    disp_0.ShowImage(image0)

    # Screen 1: Time
    image1 = Image.new("RGB", (disp_1.width, disp_1.height), "black")
    lcd.print_270(text=f"{datetime.now().strftime('%H:%M:%S')}", pos=(2, 0), image=image1, font=lcd.font0_20pt,
                  color="yellow")
    disp_1.ShowImage(image1)

    # filter out networks with no RSSI data
    filtered_networks = []
    for bssid, info in (bssid_map or {}).items():
        valid_signals = [v for v in info["rssi_history"] if v > -99.0]
        rssi = max(valid_signals) if valid_signals else -99.0

        # Note: Pi Zero 2 W only has a 2.4GHz, we bypass band blocking checks here
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
    MAX_VISIBLE_ROWS = 8

    while not select:
        image2 = Image.new("RGB", (disp_2.width, disp_2.height), "black")

        # sliding window start, and show title
        if idx_pick > MAX_VISIBLE_ROWS:
            start_idx = idx_pick - MAX_VISIBLE_ROWS
        else:
            start_idx = 0

        y = 210
        lcd.print_270(text="#  SSID           (RSSI)", pos=(y, 2), image=image2, font=lcd.font0_24pt, color="blue")
        y -= 24

        # show visible rows
        visible_chunk = filtered_networks[start_idx:start_idx + MAX_VISIBLE_ROWS]
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


def create_radar_png_csv_save(bssid, info, heading, plot_dir, timestamp):
    """ create polar plot for BSSID, then saves png and CSV """
    # safe SSID and BSSID strings for files
    processed_ssid = info["ssid"].replace(" ", "_")
    safe_ssid = "".join([c for c in processed_ssid if c.isalnum() or c in ("-", "_")]).strip()
    if not safe_ssid:
        safe_ssid = "Hidden_or_Unknown"

    safe_bssid = bssid.replace(":", "")
    print(f"\n *** Saving plot for: {safe_ssid}, with BSSID: {safe_bssid}")

    csv_file = plot_dir / f"{safe_ssid}_{safe_bssid}-{timestamp}.csv"
    png_file = plot_dir / f"{safe_ssid}_{safe_bssid}-{timestamp}.png"

    # Normalize history data array (convert None values to -99.0)
    cleaned_history = [v if v is not None else -99.0 for v in info["rssi_history"]]
    info["rssi_history"] = cleaned_history

    # Save CSV
    csv_data = np.column_stack((np.arange(360), cleaned_history))
    np.savetxt(csv_file, csv_data, fmt='%d,%.1f', header='degree,rssi', comments='')
    print(f"Saved csv: {csv_file}")

    # Create pngs
    start_time = time.time()
    polar_plot_image = prepare_and_plot(bssid, info, heading, file_name=str(png_file))
    print(f"plot time = {(time.time() - start_time):.2f} secs")
    print(f"Plot file written: {png_file}")

    return polar_plot_image


def render_lcd_radar_ui(lcd, disp_0, disp_1, disp_2, ssid, heading, signal_history, peak_rssi, peak_degree, peak_cluster,
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
    display_radar_lcd(
        disp2_draw,
        cadence_fill=None,
        heading=heading,
        signal_history=signal_history,
        connected=True,
        peak_degree=peak_deg,
        peak_rssi=peak_rssi,
        peak_cluster=peak_clust
    )

    # Annotate Graph Text
    # Screen 2: Black-out patch on Radar for Peak RSSI and Peak degree, SSID
    disp2_draw.rectangle([209, 0, 240, 55], fill="black")
    lcd.print_270(text=f"{peak_rssi:.0f}", pos=(210, 0), image=image2, font=lcd.font0_34pt, color="red")
    disp2_draw.rectangle([212, 180, 240, 240], fill="black")
    lcd.print_270(text=f"{peak_degree:.0f}°", pos=(213, 178), image=image2, font=lcd.font0_28pt, color="red")
    lcd.print_270(text=f"{ssid}", pos=(0, 0), image=image2, font=lcd.font0_20pt, color="yellow")
    disp_2.ShowImage(image2)

    # Screen 0: Menu option for LCD plot
    image0 = Image.new("RGB", (disp_0.width, disp_0.height), "black")
    lcd.print_270(text="Scan?", pos=(127, 0), image=image0, font=lcd.font0_24pt, color="yellow")
    lcd.print_270(text="Hi-Rez", pos=(60, 0), image=image0, font=lcd.font0_24pt, color="yellow")
    lcd.print_270(text=" is 20s", pos=(35, 0), image=image0, font=lcd.font0_24pt, color="yellow")
    lcd.print_270(text=" wait !", pos=(10, 0), image=image0, font=lcd.font0_24pt, color="yellow")
    disp_0.ShowImage(image0)

    # Screen 1: Metrics: Compass, Peak RSSI metrics, and clock
    image1 = Image.new("RGB", (disp_1.width, disp_1.height), "black")
    lcd.print_270(text="Peak:", pos=(132, 0), image=image1, font=lcd.font0_34pt, color="red")
    rssi_text = f"{peak_rssi:.0f}" if peak_rssi is not None else "no dBm"
    lcd.print_270(text=rssi_text, pos=(84, 2), image=image1, font=lcd.font0_50pt, color="red")
    degree_text = f"{peak_degree:.0f}°" if peak_degree is not None else "? °"
    lcd.print_270(text=degree_text, pos=(48, 8), image=image1, font=lcd.font0_34pt, color="red")
    peak_count = len(peak_cluster) if peak_cluster is not None else 0
    peak_text = f"{peak_count:.0f} peak{'s' if peak_count != 1 else ''}"
    lcd.print_270(text=peak_text, pos=(18, 2), image=image1, font=lcd.font0_20pt, color="red")
    lcd.print_270(text=f"{datetime.now().strftime('%H:%M:%S')}", pos=(2, 0), image=image1, font=lcd.font0_20pt,
                  color="yellow")
    disp_1.ShowImage(image1)


def plot_bssid_lcd(disp_0, disp_1, disp_2, bssid_map, menu_ssid, target_bssid, lis3mdl):
    global button1_pressed, button2_pressed

    button1_pressed = False
    button2_pressed = False

    if target_bssid not in bssid_map:
        print(f"ERROR: Selected BSSID {target_bssid} ({menu_ssid}) dropped out of map before plotting!")
        return

    signal_history = bssid_map[target_bssid]["rssi_history"]
    ssid = bssid_map[target_bssid]["ssid"]

    if ssid in {"", None}:
        print(f"ERROR: '{ssid}' for Selected BSSID {target_bssid}!")
        return

    peak_rssi, peak_degree, peak_cluster, has_valid_history = extract_radar_metrics(signal_history)
    hi_rez_active = False
    i = 1

    # Screen 0 - Menu options
    image0 = Image.new("RGB", (disp_0.width, disp_0.height), "black")
    lcd.print_270(text="Scan?", pos=(127, 0), image=image0, font=lcd.font0_24pt, color="yellow")
    lcd.print_270(text="Hi-Rez", pos=(60, 0), image=image0, font=lcd.font0_24pt, color="yellow")
    lcd.print_270(text=" ~20s !", pos=(35, 0), image=image0, font=lcd.font0_24pt, color="yellow")
    disp_0.ShowImage(image0)

    # Screen 1 - Metrics: Peak RSSI & Peak degree
    image1 = Image.new("RGB", (disp_1.width, disp_1.height), "black")
    lcd.print_270(text="Peak", pos=(132, 0), image=image1, font=lcd.font0_34pt, color="red")
    rssi_text = f"{peak_rssi:.0f}" if peak_rssi is not None else "no dBm"
    lcd.print_270(text=rssi_text, pos=(84, 2), image=image1, font=lcd.font0_50pt, color="red")
    degree_text = f"{peak_degree:.0f}°" if peak_degree is not None else "? °"
    lcd.print_270(text=degree_text, pos=(48, 8), image=image1, font=lcd.font0_34pt, color="red")
    peak_count = len(peak_cluster) if peak_cluster is not None else 0
    peak_text = f"{peak_count:.0f} peak{'s' if peak_count != 1 else ''}"
    lcd.print_270(text=peak_text, pos=(18, 2), image=image1, font=lcd.font0_20pt, color="red")
    disp_1.ShowImage(image1)

    while True:
        start_time = time.time()

        # Hi-Rez is static, so slow polling
        if hi_rez_active:
            time.sleep(0.1)

        # Lo-Rez RADAR plot
        if not hi_rez_active:
            # TODO implement compass, remove i
            i += 1
            # heading = get_compass_heading(lis3mdl)
            heading = 37 + i

            # Screen 2: plot radar
            image2 = Image.new("RGB", (disp_2.width, disp_2.height), "black")
            disp2_draw = ImageDraw.Draw(image2)

            display_radar_lcd(
                disp2_draw,
                cadence_fill=None,
                heading=heading,
                signal_history=signal_history,
                connected=True,
                peak_degree=peak_degree,
                peak_rssi=peak_rssi,
                peak_cluster=peak_cluster
            )

            # Annotate text overlay for screen 2
            disp2_draw.rectangle([209, 0, 240, 55], fill="black")
            lcd.print_270(text=f"{peak_rssi:.0f}" if peak_rssi is not None else "---", pos=(210, 0), image=image2,
                          font=lcd.font0_34pt, color="red")
            disp2_draw.rectangle([212, 180, 240, 240], fill="black")
            lcd.print_270(text=f"{peak_degree:.0f}°" if peak_degree is not None else "---°", pos=(213, 178),
                          image=image2, font=lcd.font0_28pt, color="red")
            lcd.print_270(text=f"{ssid}", pos=(0, 0), image=image2, font=lcd.font0_20pt, color="yellow")
            disp_2.ShowImage(image2)

        # Button 1: Hi-Rez Toggle
        if button1_pressed:
            button1_pressed = False

            if hi_rez_active:
                print("Resume low-resolution plotting...")
                hi_rez_active = False

                # Re-paint the default Screen 0 options when dropping back to lo-rez
                image0 = Image.new("RGB", (disp_0.width, disp_0.height), "black")
                lcd.print_270(text="Scan?", pos=(127, 0), image=image0, font=lcd.font0_24pt, color="yellow")
                lcd.print_270(text="Hi-Rez", pos=(60, 0), image=image0, font=lcd.font0_24pt, color="yellow")
                lcd.print_270(text=" ~20s !", pos=(35, 0), image=image0, font=lcd.font0_24pt, color="yellow")
                disp_0.ShowImage(image0)
            else:
                print("Creating Hi Resolution auto-scaled plot with matplotlib...")
                hi_rez_active = True

                # Screen 0: Display waiting for Hi-Rez plot
                image0 = Image.new("RGB", (disp_0.width, disp_0.height), "black")
                lcd.print_270(text="Hi-Rez", pos=(60, 0), image=image0, font=lcd.font0_24pt, color="yellow")
                lcd.print_270(text="...wait-", pos=(35, 0), image=image0, font=lcd.font0_24pt, color="yellow")
                lcd.print_270(text="ing", pos=(10, 22), image=image0, font=lcd.font0_24pt, color="yellow")
                disp_0.ShowImage(image0)

                plot_dir = Path("logs_polar_plots")
                plot_dir.mkdir(exist_ok=True)
                timestamp = datetime.now().strftime('%Y-%m%d_%H:%M')

                bssid_info = bssid_map.get(target_bssid, {"ssid": ssid, "rssi_history": signal_history})
                hi_rez_image = create_radar_png_csv_save(target_bssid, bssid_info, heading + 90, plot_dir, timestamp)

                if hi_rez_image:
                    print("LCD Display 2 shows auto-scaled high-resolution plot...")
                    lcd_image = hi_rez_image.convert("RGB").resize((disp_2.width, disp_2.height))
                    lcd_image = lcd_image.rotate(270)
                    disp_2.ShowImage(lcd_image)

                    # Screen 0: Menu for return to scan or return to Lo-Rez plots
                    image0 = Image.new("RGB", (disp_0.width, disp_0.height), "black")
                    lcd.print_270(text="Scan?", pos=(127, 0), image=image0, font=lcd.font0_24pt, color="yellow")
                    lcd.print_270(text="Back", pos=(60, 0), image=image0, font=lcd.font0_24pt, color="yellow")
                    lcd.print_270(text="to Lo-", pos=(35, 0), image=image0, font=lcd.font0_24pt, color="yellow")
                    lcd.print_270(text="Rez?", pos=(10, 0), image=image0, font=lcd.font0_24pt, color="yellow")
                    disp_0.ShowImage(image0)
                else:
                    print("Error: Plot generation invalid image buffer reference.")
                    hi_rez_active = False

        # Button 2: return to scanning
        if button2_pressed:
            button2_pressed = False
            print("Returning to Wi-Fi scanning...")
            break

        print(f"Loop time = {time.time() - start_time:.3f} sec")


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
        oled_display, draw, font, image = init_oled_display(i2c1, use_mono_type=False)

    # TODO DO NOT HARDCODE e_ink_detected
    e_ink_detected = False

    epd_display, epd_draw, epd_font, epd_image = None, None, None, None
    if e_ink_detected:
        epd_display, epd_draw, epd_font, epd_image = init_e_ink_display()

    lcd_detected = False
    if not (oled_detected or e_ink_detected):
        lcd_detected = True
        disp_0, disp_1, disp_2 = create_lcd_display_canvases("radiant-ether-913.jpg")

    lis3mdl = None
    if lis3mdl_detected:
        lis3mdl = init_lis3mdl(i2c1)

    # Fill Wi-Fi cache once before starting
    print("Pre-warming Wi-Fi cache...")
    trigger_background_scan(wifi_interface)
    if oled_detected:
        draw.text((0, 0), "Warming Wi-Fi cache", font=font, fill=1)
        oled_display.image(image)
        oled_display.show()

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
                heading = get_compass_heading(lis3mdl)

                # TODO ****** Fix when add Magnetometer !!!!
                heading = 37

                update_bssid_map(wifi_data, heading, bssid_map)

                console_print(wifi_data, heading)
                if oled_detected:
                    oled_print(draw, font, image, oled_display, wifi_data, heading)
                if e_ink_detected:
                    e_ink_print(epd_draw, epd_font, epd_image, epd_display, wifi_data, heading)
                if lcd_detected:
                    lcd_print(lcd, disp_0, disp_1, disp_2, wifi_data, heading)

                duration = time.time() - last_update
                last_update = time.time()

                above_80_rssi = sum(
                    1 for info in bssid_map.values()
                    if any(v > -80.0 for v in info["rssi_history"])
                )

                print(f"  Tracking {above_80_rssi} of {len(bssid_map)} Wi-Fis above -80 dBm (>1-bar)")
                print(f"  Clock: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"  Updates: {duration * 1000:.1f} msec, {1.0 / duration:.0f} Hz")
                print(f"  Pi Zero 2W temp: {pi_celsius:.1f}°C")
                print(f"{'Blocked <1-bar & Pi Zero (only 2.4GHz)' if BLOCK_0_BAR else 'Pi Zero (only 2.4GHz)'}\n")

            if button2_pressed:
                button2_pressed = False
                if lcd_detected:
                    # Select which SSID to plot
                    target_bssid, menu_ssid = lcd_choose_ssid(lcd, disp_0, disp_1, disp_2, bssid_map)
                    if target_bssid:
                        print(f"Starting Radar Plot Mode for: {target_bssid}")
                        plot_bssid_lcd(disp_0, disp_1, disp_2, bssid_map, menu_ssid, target_bssid, lis3mdl)


    except KeyboardInterrupt:
        print("\nSaving plots...")

        # directory for polar plots
        dir = "logs_polar_plots"
        plot_dir = Path(dir)
        plot_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime('%Y-%m%d_%H:%M')

        for bssid, info in bssid_map.items():
            # BSSID plotted on if RSSI > -99
            exit_heading = 0
            if any(val > -99.0 for val in info["rssi_history"]):
                _ = create_radar_png_csv_save(bssid, info, exit_heading, plot_dir, timestamp)
        print("Clean Exit.")


if __name__ == "__main__":
    main()
    print("\nExiting.")
