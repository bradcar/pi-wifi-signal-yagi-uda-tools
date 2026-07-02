#!/usr/bin/python
# -*- coding: UTF-8 -*-
import os
import sys
import time
import logging
from PIL import ImageFont, Image

import lib.lcd_st7789_utils as lcd

# Define button
KEY1_PIN = 25
KEY2_PIN = 26

# Set the button pin to input mode and use a pull-up resistor
# GPIO.setup(KEY1_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
# GPIO.setup(KEY2_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
key1 = disp_0.gpio_mode(KEY1_PIN, disp_0.INPUT, None)
key2 = disp_0.gpio_mode(KEY2_PIN, disp_0.INPUT, None)

# Initialize button state
curr_state_key1 = 0
curr_state_key2 = 0


def key1_callback():  # Key 1 interrupt callback function
    global curr_state_key1
    global curr_state_key2
    curr_state_key1 = 1
    curr_state_key2 = 0


def key2_callback():  # Key 2 interrupt callback function
    global curr_state_key1
    global curr_state_key2
    curr_state_key1 = 0
    curr_state_key2 = 1


# Enable key interrupt
key1.when_activated = key1_callback
key2.when_activated = key2_callback


# Network Signal Lock Thresholds
RSSI_CONNECT_THRESHOLD = -77  # Minimum signal to allow a hardware connection
RSSI_DOWNLOAD_THRESHOLD = -74  # Minimum signal to execute data payload transfer


def display_radar_splash_lcd(disp_2):
    logging.info("Display jpg on center lcd")
    try:
        radar_image = Image.open("assets/images/yagi-uda-dark.jpg")
        rotated_radar = radar_image.rotate(270)
        disp_2.ShowImage(rotated_radar)
    except IOError:
        logging.warning("Wallpaper 'yagi-uda-dark.jpg' not found at project root. Skipping center lcd")


def display_metrics_lcd(lcd, disp_0, disp_1, rssi, ssid: str, tx_rate, heading: float, download_count,
                        connected: bool = True):
    # Setup fonts
    Font1 = ImageFont.truetype("assets/Font/Font00.ttf", 50)
    Font2 = ImageFont.truetype("assets/Font/Font00.ttf", 34)
    Font5 = ImageFont.truetype("assets/Font/Font00.ttf", 33)
    Font3 = ImageFont.truetype("assets/Font/Font00.ttf", 28)
    Font4 = ImageFont.truetype("assets/Font/Font00.ttf", 13)

    # SCREEN 0: Connection & Downloads
    disp0_image = Image.new("RGB", (disp_0.width, disp_0.height), "BLACK")

    if rssi >= RSSI_CONNECT_THRESHOLD:
        lcd.print_rotated(text="Con-", pos=(132, 0), ang=270, image=disp0_image, font=Font3, color="green")
        lcd.print_rotated(text="nect?", pos=(108, 0), ang=270, image=disp0_image, font=Font3, color="green")
    if connected and rssi >= RSSI_DOWNLOAD_THRESHOLD:
        lcd.print_rotated(text="down", pos=(70, 0), ang=270, image=disp0_image, font=Font3, color="blue")
        lcd.print_rotated(text="load?", pos=(44, 0), ang=270, image=disp0_image, font=Font3, color="blue")
    if download_count > 0:
        lcd.print_rotated(text=f"#{download_count}", pos=(2, 4), ang=270, image=disp0_image, font=Font2,
                          color="blue")

    disp_0.ShowImage(disp0_image)

    # SCREEN 1 Signal Metrics & Mode Status
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


logging.basicConfig(level=logging.DEBUG)

# Initialize 3 physical displays
disp_0, _ = lcd.init_lcd_display(0)
disp_1, _ = lcd.init_lcd_display(1)
disp_2, _ = lcd.init_lcd_display(2)

# Dummy system state
heading = 225
rssi = -54
connected = False
download_count = 20
tx_rate = 24.7
ssid = "shell-fi"

logging.info("Entering main display update loop")
# splash screen for lcd
display_radar_splash_lcd(disp_2)

try:
    while True:
        display_metrics_lcd(lcd, disp_0, disp_1, rssi, ssid, tx_rate, heading, download_count,
        connected)

        # State flip for debug
        connected = not connected

except IOError as e:
    logging.error(f"Hardware communication crash on SPI channels: {e}")
except KeyboardInterrupt:
    logging.info("Interrupt sequence caught. Executing clean peripheral power-down profiles.")
finally:
    # Ensure hardware resources are released safely during teardown
    disp_0.module_exit()
    disp_1.module_exit()
    disp_2.module_exit()
    logging.info("GPIO and SPI resources released safely.")