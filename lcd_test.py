import time
import logging
from PIL import ImageFont, Image

from lib.lcd_st7789_utils

logging.basicConfig(level=logging.DEBUG)

# 1. Initialize all 3 physical displays and their local 1-bit canvas buffers
disp_0, img0 = lcd.init_lcd_display(0)
disp_1, img1 = lcd.init_lcd_display(1)
disp_2, img2 = lcd.init_lcd_display(2)

# 2. Setup the exact Font profile configurations from your test suite
Font1 = ImageFont.truetype("../Font/Font00.ttf", 50)
Font2 = ImageFont.truetype("../Font/Font00.ttf", 34)
Font5 = ImageFont.truetype("../Font/Font00.ttf", 33)
Font3 = ImageFont.truetype("../Font/Font00.ttf", 28)
Font4 = ImageFont.truetype("../Font/Font00.ttf", 13)

# 3. Static Assets: Paint and push the persistent dark radar wallpaper to display 2
logging.info("Initializing persistent display 2 wallpaper asset")
try:
    radar_image = Image.open('../pic/yagi-uda-dark.jpg')
    # Match your exact test program rotation deployment
    rotated_radar = radar_image.rotate(270)
    disp_2.ShowImage(rotated_radar)
except IOError:
    logging.warning("Wallpaper asset '../pic/yagi-uda-dark.jpg' not found. Skipping Panel 2.")

# 4. Live runtime tracking state variables
heading = 225
rssi = -54
connected = False
download_count = 20

logging.info("Entering main data visualization framework telemetry loop")

try:
    while True:
        # ----------------------------------------------------
        # SCREEN 0 PROCESSING: Connection & Download Status
        # ----------------------------------------------------
        lcd.clear_canvas(img0)

        # Connect status string tokens
        lcd.draw_rotated_text(base_image=img0, text="Con-", position=(132, 0), angle=270, font=Font3, fill_color=1)
        lcd.draw_rotated_text(base_image=img0, text="nect?", position=(108, 0), angle=270, font=Font3, fill_color=1)

        # Download tracker status strings
        lcd.draw_rotated_text(base_image=img0, text="down", position=(70, 0), angle=270, font=Font3, fill_color=1)
        lcd.draw_rotated_text(base_image=img0, text="load?", position=(44, 0), angle=270, font=Font3, fill_color=1)

        # Dynamic variable mapping string replacement formatting for telemetry tracking
        download_text = f"#{download_count}"
        lcd.draw_rotated_text(base_image=img0, text=download_text, position=(2, 4), angle=270, font=Font2, fill_color=1)

        # Push completed buffer array to screen 0 hardware
        lcd.refresh_lcd_display(disp_0, img0)

        # ----------------------------------------------------
        # SCREEN 1 PROCESSING: Signal Metrics & Mode Status
        # ----------------------------------------------------
        lcd.clear_canvas(img1)

        # Telemetry Labels and numerical values
        lcd.draw_rotated_text(base_image=img1, text="RSSI:", position=(132, 0), angle=270, font=Font2, fill_color=1)
        lcd.draw_rotated_text(base_image=img1, text=f"{rssi}", position=(84, 2), angle=270, font=Font1, fill_color=1)
        lcd.draw_rotated_text(base_image=img1, text=f"{heading}°", position=(48, 8), angle=270, font=Font2,
                              fill_color=1)

        # Contextual logic switch based on hardware connection flag states
        if connected:
            lcd.draw_rotated_text(base_image=img1, text="Wi-Fi", position=(11, 1), angle=270, font=Font5, fill_color=1)
            lcd.draw_rotated_text(base_image=img1, text="connected", position=(0, 3), angle=270, font=Font4,
                                  fill_color=1)
        else:
            lcd.draw_rotated_text(base_image=img1, text="Scan", position=(5, 0), angle=270, font=Font5, fill_color=1)

        # Push completed buffer array to screen 1 hardware
        lcd.refresh_lcd_display(disp_1, img1)

        # State flip matches the original loop timing behavior for the interface test
        connected = not connected

        # Small sleep interval prevents CPU pinning while retaining high rendering response
        time.sleep(1.0)

except IOError as e:
    logging.error(f"Hardware communication crash on SPI channels: {e}")
except KeyboardInterrupt:
    logging.info("Interrupt sequence caught. Executing clean peripheral power-down profiles.")
finally:
    # Ensure display module exit cycles run no matter what caused the program to stop
    disp_0.module_exit()
    disp_1.module_exit()
    disp_2.module_exit()
    logging.info("GPIO and SPI resources released safely.")