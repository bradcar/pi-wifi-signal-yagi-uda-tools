# pi_yagi_uda.py
"""
On Raspberry Pi Zero 2 W, the code repeatedly measures the RSSI, Link Quality,
and Tx Bit Rate of the currently connected network on interface wlan0.
It prints the results to std out and an OLED SSD 1305 display.
It reads metrics continuously to update signal strength changes.

This code displays data on a SSD1305 128x32 display (left 96px for text,
right 32px for circle graphic) and also prints data to std out.
https://learn.adafruit.com/adafruit-2-23-monochrome-oled-bonnet/usage

The Zero 2 W will be connected to a directional Yagi Uda antenna.

($35 with antenna specs) https://www.amazon.com/gp/product/B008Z4I7WQ
 * about 25 degree spread
 ($30 no antenna specs) https://www.amazon.com/dp/B00OCJYPCY
 * This is a passive antenna, It can not work alone. It must work together with other active network device
   like signal booster/repeater/router/access point

Usage:
  sudo python3 pi_yagi_uda.py

OLED Output (16 chars x 4 lines):
             123456789 123456
    line1 = "ssid  = shell-fi"
    line2 = "rssi  = -99 dBm"
    line3 = "TxRate= 72 Mb/s"
    line4 = "Download viable"
    or
    line4 = "Heading: 184.2°"
    line4 = "Downloaded 100%"
    line4 = "Downloaded 295KB"
    line4 = "Downloaded FAIL!"

Exmaple output to std out:
    WiFi Signal Monitor (Pi Zero): ABox-PDX
    SSID:    ABox-PDX
    RSSI:    -28 dBm  4 bars
    Link Q:  70/70    Perfect Link
    Tx Rate: 43.3 Mb/s

    Updates:  16.0 msec, 62 Hz
    Clock: 2026-05-24 14:20:27

Yagi-Uda with access point $150: https://www.youtube.com/watch?v=R1C4e-YRcOY
 * 24 deg to 25 degree spread
 * 600' omni AP -70 dBm 1-2 bars
 * 600' yagi-uda -59 dBm 3 bars
 * 1000' yagi-uda -78 dBm 2 bars
   - speedtest 40.6 download, 15.1 upload

 TP-Link Long Range Outdoor Access Point: https://www.amazon.com/gp/product/B07953S2FD
 Yagi-Uda: https://www.amazon.com/gp/product/B008Z4I7WQ

"""
import time
from datetime import datetime

import adafruit_ssd1305
import board
import busio
from PIL import Image, ImageDraw, ImageFont

# network signal code
from pi_wifi_rssi_quality_txrate import get_ssid, query_wifi, print_with_string

DOWNLOAD_LIMIT_RATE = 2.5  # Mb/s, 4Mb/s was measured on Pico AP for Mac download (quality 70/70)
SSD1305_WIDTH = 128
SSD1305_HEIGHT = 32
TEXT_WIDTH_LIMIT = 96  # text on left 96px
CIRCLE_AREA_START_X = TEXT_WIDTH_LIMIT  # Graphic starts at 96px
BNO086_AVAILABLE = False


def init_ssd1305_display(i2c):
    display = adafruit_ssd1305.SSD1305_I2C(SSD1305_WIDTH, SSD1305_HEIGHT, i2c)

    # clear display
    display.fill(0)
    display.show()

    # create image canvas (1-bit monochrome) and load font
    image = Image.new("1", (SSD1305_WIDTH, SSD1305_HEIGHT))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    return display, draw, font, image


def scan_i2c_bus(i2c):
    print("Scan for I2C devices...")

    # lock i2C bus before scan
    while not i2c.try_lock():
        pass

    try:
        devices = i2c.scan()
        if not devices:
            print("Error: No I2C devices detected. Check your wiring")
        else:
            print(f"\nFound {len(devices)} device(s):")
            for address in devices:
                # Print both decimal and standard hexadecimal notation
                print(f" Device detected at Address: Hex: {hex(address)} ({address})")

                if address == 0x3C:
                    print(" -> likely SSD1306 OLED display")
                if address == 0x4B:
                    print(" -> likely BNO086 IMU")

    finally:
        i2c.unlock()
    print("\n")


def define_circle_bounding_box():
    # Bounding box for the circle centered in the 32x32 area
    circle_margin = 2  # Padding around the circle
    x0 = CIRCLE_AREA_START_X + circle_margin
    y0 = 0 + circle_margin
    x1 = SSD1305_WIDTH - 1 - circle_margin
    y1 = SSD1305_HEIGHT - 1 - circle_margin
    circle_bbox = [x0, y0, x1, y1]
    return circle_bbox


def display_text_ssd1305(draw, font, rssi: int, ssid: str, tx_rate: str):
    # slightly indent on X-axis for readability
    left_indent = 2

    # limit to 16 chars
    line1 = f"SSID: {ssid}"
    line2 = f"RSSI: {rssi} dBm"
    line3 = f"TxRate: {tx_rate:.0f} Mb/s"

    if tx_rate > DOWNLOAD_LIMIT_RATE:
        line4 = "Download viable"
    else:
        line4 = ""  # Leaves bottom line empty

    # Draw text using the 8px vertical grid (0, 8, 16, 24)
    draw.text((left_indent, 0), line1, font=font, fill=1)
    draw.text((left_indent, 8), line2, font=font, fill=1)
    draw.text((left_indent, 16), line3, font=font, fill=1)
    draw.text((left_indent, 24), line4, font=font, fill=1)


def display_radar_ssd1305(circle_bbox, draw, rssi: int):
    # Use PIL.Draw.chord to draw an outlined circle (like an arc with a closing line)
    # If filled=0, it will only draw the closing line, so we use full outline (outline=1, fill=0)
    draw.chord(circle_bbox, start=0, end=360, outline=1, fill=0)

    # Dynamic inner fill based on RSSI strength.
    # We map RSSI -100dBm to 0% fill, and RSSI -30dBm to 100% fill.
    try:
        numeric_rssi = float(rssi)
        # Map RSSI range (-100 to -30) to percentage (0 to 1.0)
        # Ensure the percentage stays within bounds
        percentage = max(0.0, min(1.0, (numeric_rssi - (-100)) / (-30 - (-100))))

        # Fill the circle like a pie chart using 'pieslice'
        # Starting at top (-90 degrees) and filling clockwise
        if percentage > 0.01:
            draw.pieslice(circle_bbox, start=-90, end=(-90 + (360 * percentage)), outline=0, fill=1)

    except (ValueError, TypeError):
        pass  # just keep the empty outline if parsing fails


def main():
    print("Starting Pi Zero 2 W Signal Tracking Loop...\n")
    ssid = get_ssid()

    i2c = busio.I2C(board.SCL, board.SDA)
    scan_i2c_bus(i2c)

    display, draw, font, image = init_ssd1305_display(i2c)
    circle_bbox = define_circle_bounding_box()

    try:
        start_time = time.time()
        while True:
            # Get RSSI, Quality, and Bit Rate
            rssi, quality, tx_rate = query_wifi()
            finish_time = time.time()
            duration = finish_time - start_time
            start_time = finish_time

            # Print metrics to standard out
            print_with_string(quality, rssi, ssid, tx_rate)
            print(f"\nUpdates:  {duration * 1000:.1f} msec, {1.0 / duration:.0f} Hz")
            print(f"Clock: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

            # OLED: display text on left 96px, radar graphic on right 32px
            draw.rectangle((0, 0, SSD1305_WIDTH, SSD1305_HEIGHT), fill=0)
            display_text_ssd1305(draw, font, rssi, ssid, tx_rate)
            display_radar_ssd1305(circle_bbox, draw, rssi)
            display.image(image)
            display.show()

            # Brief sleep before loop
            time.sleep(0.1)

    except KeyboardInterrupt:
        # Clear screen on exit
        draw.rectangle((0, 0, SSD1305_WIDTH, SSD1305_HEIGHT), fill=0)
        display.image(image)
        display.show()
        print("\nTracking Stopped. Exiting.")


if __name__ == "__main__":
    main()
