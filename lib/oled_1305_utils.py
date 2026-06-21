"""
General Utils for OLED SSD1305
"""
from PIL import Image, ImageDraw, ImageFont
from adafruit_ssd1305 import SSD1305_I2C

OLED_WIDTH = 128
OLED_HEIGHT = 32


def init_oled_display(i2c, use_mono_type=False):
    display = SSD1305_I2C(OLED_WIDTH, OLED_HEIGHT, i2c)
    display.fill(0)
    display.show()

    image = Image.new("1", (OLED_WIDTH, OLED_HEIGHT))
    draw = ImageDraw.Draw(image)

    try:
        if use_mono_type:
            print("Using mono type")
            font = ImageFont.truetype("DejaVuSansMono.ttf", 10)
        else:
            font = ImageFont.load_default()
            print("Using default font")
    except IOError:
        font = ImageFont.load_default()
        print("fall back to default font")

    return display, draw, font, image


def clear_display_oled(oled_display, draw=None, image=None):
    if draw:
        draw.rectangle((0, 0, OLED_WIDTH, OLED_HEIGHT), fill=0)
    if image:
        oled_display.image(image)
    oled_display.show()