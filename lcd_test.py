#!/usr/bin/python
"""
lcd_test.py
"""

import os
import sys
import time
import logging
from PIL import ImageFont, Image, JpegImagePlugin
from gpiozero import Button

import lib.lcd_st7789_utils as lcd

logging.basicConfig(level=logging.DEBUG)

logging.info("--- Initializing displays ---")
disp_0, _ = lcd.init_lcd_display(0)
logging.info("disp_0 (Left 0.96\", SPI0) initialized.")

disp_1, _ = lcd.init_lcd_display(1)
logging.info("disp_1 (Right 0.96\", SPI0) initialized.")

disp_2, _ = lcd.init_lcd_display(2)
logging.info("disp_2 (Center 1.3\", SPI1) initialized.\n")

# Use native gpiozero Button instances to keep SPI handles clean
KEY1_PIN = 25
KEY2_PIN = 26

curr_state_key1 = 0
curr_state_key2 = 0

def key1_callback():
    global curr_state_key1, curr_state_key2
    curr_state_key1 = 1
    curr_state_key2 = 0

def key2_callback():
    global curr_state_key1, curr_state_key2
    curr_state_key1 = 0
    curr_state_key2 = 1

key1 = Button(KEY1_PIN, pull_up=True, bounce_time=0.1)
key2 = Button(KEY2_PIN, pull_up=True, bounce_time=0.1)
key1.when_pressed = key1_callback
key2.when_pressed = key2_callback

# Network Signal Lock Thresholds
RSSI_CONNECT_THRESHOLD = -77
RSSI_DOWNLOAD_THRESHOLD = -74

def display_radar_splash_lcd(disp_2):
    logging.info("--- Testing disp_2 (Center) with Red frame ---")
    fallback_frame = Image.new("RGB", (240, 240), "red")
    disp_2.ShowImage(fallback_frame)
    time.sleep(2)

    logging.info("Displaying JPG wallpaper on center LCD...")
    image_path = "assets/images/yagi-uda-dark.jpg"
    try:
        with Image.open(image_path) as img:
            radar_image = img.convert("RGB").rotate(270)
        disp_2.ShowImage(radar_image)
        logging.info("Successfully pushed frame to disp_2.")
    except IOError:
        logging.warning(f"Image '{image_path}' not found. Leaving red fallback frame active.")

def display_metrics_lcd(lcd, disp_0, disp_1, rssi, ssid: str, tx_rate, heading: float, download_count, connected: bool = True):
    try:
        Font1 = ImageFont.truetype("assets/Font/Font00.ttf", 50)
        Font2 = ImageFont.truetype("assets/Font/Font00.ttf", 34)
        Font5 = ImageFont.truetype("assets/Font/Font00.ttf", 33)
        Font3 = ImageFont.truetype("assets/Font/Font00.ttf", 28)
        Font4 = ImageFont.truetype("assets/Font/Font00.ttf", 13)
    except IOError:
        Font1 = Font2 = Font3 = Font4 = Font5 = ImageFont.load_default()

    # SCREEN 0: Connection & Downloads
    disp0_image = Image.new("RGB", (disp_0.width, disp_0.height), "BLACK")
    if rssi >= RSSI_CONNECT_THRESHOLD:
        lcd.print_rotated(text="Con-", pos=(132, 0), ang=270, image=disp0_image, font=Font3, color="green")
        lcd.print_rotated(text="nect?", pos=(108, 0), ang=270, image=disp0_image, font=Font3, color="green")
    if connected and rssi >= RSSI_DOWNLOAD_THRESHOLD:
        lcd.print_rotated(text="down", pos=(70, 0), ang=270, image=disp0_image, font=Font3, color="blue")
        lcd.print_rotated(text="load?", pos=(44, 0), ang=270, image=disp0_image, font=Font3, color="blue")
    if download_count > 0:
        lcd.print_rotated(text=f"#{download_count}", pos=(2, 4), ang=270, image=disp0_image, font=Font2, color="blue")
    disp_0.ShowImage(disp0_image)

    # SCREEN 1: Signal Metrics & Mode Status
    disp1_image = Image.new("RGB", (disp_1.width, disp_1.height), "BLACK")
    lcd.print_rotated(text="RSSI:", pos=(132, 0), ang=270, image=disp1_image, font=Font2, color="red")
    lcd.print_rotated(text=f"{rssi}", pos=(84, 2), ang=270, image=disp1_image, font=Font1, color="red")
    lcd.print_rotated(text=f"{heading}°", pos=(48, 8), ang=270, image=disp1_image, font=Font2, color="red")

    if connected:
        lcd.print_rotated(text="Wi-Fi", pos=(11, 1), ang=270, image=disp1_image, font=Font5, color="green")
        lcd.print_rotated(text="connected", pos=(0, 3), ang=270, image=disp1_image, font=Font4, color="green")
    else:
        lcd.print_rotated(text="Scan", pos=(5, 0), ang=270, image=disp1_image, font=Font5, color="yellow")

    disp_1.ShowImage(disp1_image)

# ====== MAIN =======
heading = 225
rssi = -54
connected = False
download_count = 20
tx_rate = 24.7
ssid = "shell-fi"

# Render center display test frame
display_radar_splash_lcd(disp_2)

logging.info("Entering main display update loop...")

try:
    while True:
        display_metrics_lcd(lcd, disp_0, disp_1, rssi, ssid, tx_rate, heading, download_count, connected)
        connected = not connected
        time.sleep(1.0)

except IOError as e:
    logging.error(f"Hardware communication crash on SPI channels: {e}")
except KeyboardInterrupt:
    logging.info("Interrupt sequence caught. Releasing resources.")
finally:
    disp_0.module_exit()
    disp_1.module_exit()
    disp_2.module_exit()
    logging.info("GPIO and SPI resources released safely.")