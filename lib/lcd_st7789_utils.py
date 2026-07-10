"""
General Utils for Waveshare multi-display LCD setups (ST7789 Drivers)
Handles initialization, drawing parameters, and full RGB color rendering.

Left Display:   160px x  80px (12,800 px)
Center display: 240px x 240px (57,600 px)
Right display:  160px x  80px (12,800 px)

Add LCD st7789 to user code:
1) Imports
    import lib.lcd_st7789_utils as lcd
    from gpiozero import Button
    from PIL import ImageFont, Image, ImageDraw

2) Add Button handlers
    button1_pressed = False
    button2_pressed = False
    button1 = Button(25, pull_up=True, bounce_time=0.1)
    button2 = Button(26, pull_up=True, bounce_time=0.1) # TODO CHANGE THIS TO 26 with LCD

    def button1_callback():
        global button1_pressed
        button1_pressed = True
        print("\n[Hardware] Button 1 Activated (GPIO 25)")

    def button2_callback():
        global button2_pressed
        button2_pressed = True
        print("\n[Hardware] Button 2 Activated (GPIO 24)")

    button1.when_pressed = button1_callback
    button2.when_pressed = button2_callback
    print("Button1 & 2  Listeners Active (GPIO 25 26) for Press and Release Edges.")

    def main():
    global button1_pressed, button2_pressed

"""
import os
import spidev as SPI
import sys
from PIL import Image, ImageDraw, ImageFont

sys.path.append("..")
from vendor.waveshare_lcd import LCD_0inch96
from vendor.waveshare_lcd import LCD_1inch3

# Global hardware pin designations for displays
LCD_CONFIGS = {
    0: {"type": "0inch96", "bus": 0, "device": 0, "rst": 24, "dc": 4, "bl": 13},
    1: {"type": "0inch96", "bus": 0, "device": 1, "rst": 23, "dc": 5, "bl": 12},
    2: {"type": "1inch3", "bus": 1, "device": 0, "rst": 27, "dc": 22, "bl": 19}
}

base_font00 = ImageFont.truetype("assets/Font/Font00.ttf", 30)

font0_50pt = base_font00.font_variant(size=50)
font0_34pt = base_font00.font_variant(size=34)
font0_33pt = base_font00.font_variant(size=33)
font0_28pt = base_font00.font_variant(size=28)
font0_24pt = base_font00.font_variant(size=24)
font0_20pt = base_font00.font_variant(size=20)
font0_16pt = base_font00.font_variant(size=16)
font0_13pt = base_font00.font_variant(size=13)

# 17x17 Arrow (0 to 16 pixel boundaries)
ARROW_LEFT = ((8, 1), (1, 8), (5, 8), (5, 15), (11, 15), (11, 8), (15, 8))
ARROW_RIGHT = ((8, 15), (1, 8), (5, 8), (5, 1), (11, 1), (11, 8), (15, 8))  # Arrow right
ARROW_UP = ((15, 8), (8, 1), (8, 5), (1, 5), (1, 11), (8, 11), (8, 15))  # arrow up
ARROW_DOWN = ((1, 8), (8, 1), (8, 5), (15, 5), (15, 11), (8, 11), (8, 15))  # arrow down

SKINNY_ARROW_LEFT = ((8, 0), (2, 6), (7, 6), (7, 16), (9, 16), (9, 6), (14, 6))
SKINNY_ARROW_RIGHT = ((8, 16), (2, 10), (7, 10), (7, 0), (9, 0), (9, 10), (14, 10))
SKINNY_ARROW_UP = ((16, 8), (10, 2), (10, 7), (0, 7), (0, 9), (10, 9), (10, 14))
SKINNY_ARROW_DOWN = ((0, 8), (6, 2), (6, 7), (16, 7), (16, 9), (6, 9), (6, 14))

# Arrow direction mapping
DIRECTION_MAP = {
    "up": SKINNY_ARROW_UP,
    "down": SKINNY_ARROW_DOWN,
    "right": SKINNY_ARROW_RIGHT,
    "left": SKINNY_ARROW_LEFT
}


def init_lcd_display(index: int):
    """
    Initializes a specific hardware display panel by its configuration index.

    Returns:
        tuple: (display_driver, canvas_image)
    """
    if index not in LCD_CONFIGS:
        raise ValueError(f"Display index {index} is not defined in hardware configurations.")

    cfg = LCD_CONFIGS[index]
    spi_device = SPI.SpiDev(cfg["bus"], cfg["device"])

    # Initialize the correct display class
    if cfg["type"] == "0inch96":
        display = LCD_0inch96.LCD_0inch96(
            spi=spi_device, spi_freq=60000000,
            rst=cfg["rst"], dc=cfg["dc"], bl=cfg["bl"]
        )
    else:
        display = LCD_1inch3.LCD_1inch3(
            spi=spi_device, spi_freq=60000000,
            rst=cfg["rst"], dc=cfg["dc"], bl=cfg["bl"]
        )

    display.Init()
    display.clear()
    display.bl_DutyCycle(100)
    image = Image.new("RGB", (display.width, display.height), "BLACK")
    return display, image


def create_lcd_display_canvases(splash_file_name):
    disp_0, _ = init_lcd_display(0)
    disp_1, _ = init_lcd_display(1)
    disp_2, _ = init_lcd_display(2)
    startup_0 = Image.new("RGB", (disp_0.width, disp_0.height), "black")
    startup_1 = Image.new("RGB", (disp_1.width, disp_1.height), "black")
    disp_0.ShowImage(startup_0)
    disp_1.ShowImage(startup_1)
    display_2_splash_lcd(disp_2, splash_image_file=splash_file_name)
    return disp_0, disp_1, disp_2


def clear_canvas(image):
    """Resets memory layout image context matrix cleanly to true black."""
    draw = ImageDraw.Draw(image)
    # FIX: Fills the RGB background back to absolute black
    draw.rectangle((0, 0, image.width, image.height), fill="BLACK")


def display_2_splash_lcd(disp_2, splash_image_file=None):
    """ Splash art jpg on display 2

     radiant-ether-098.jpg
     radiant-ether-368.jpg
     radiant-ether-913.jpg

    Args:
        splash_image_file:
    """
    lib_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(lib_dir)
    image_directory = os.path.join(project_root, "assets", "images")

    if splash_image_file is None:
        splash_image_file = "radiant-ether-098.jpg"
    print(f"Splash Image directory: {image_directory}/{splash_image_file}")
    try:
        radar_image = Image.open(f"{image_directory}/{splash_image_file}")
        rotated_radar = radar_image.rotate(270)
        disp_2.ShowImage(rotated_radar)
    except IOError:
        print(f"Wallpaper '{splash_image_file}' not found at project root. Skipping splash on Display 2 LCD")


def print_270(text: str, pos: tuple, image, font, color):
    """
    270° rotated text onto a temporary canvas, transposes it at raw hardware speeds
    if rotate horizontal display to vertical by CCW rotation.
    """
    try:
        left, top, right, bottom = font.getbbox(str(text))
    except AttributeError:
        w, h = font.getsize(str(text))
        left, top, right, bottom = 0, 0, w, h

    txt_w = (right - left)
    txt_h = (bottom - top)
    pad = 4

    # Build local transparent layer
    txt_img = Image.new("RGBA", (txt_w + pad, txt_h + pad), (0, 0, 0, 0))
    txt_draw = ImageDraw.Draw(txt_img)

    draw_x = -left + (pad // 2)
    draw_y = -top + (pad // 2)
    txt_draw.text((draw_x, draw_y), str(text), font=font, fill=color)
    rotated_txt_img = txt_img.transpose(Image.Transpose.ROTATE_270)

    # Paste onto the base image
    image.paste(rotated_txt_img, pos, rotated_txt_img)


def print_rotated(text: str, pos: tuple, ang: int, image, font, color):
    """
    Draws text onto a temporary canvas, transposes it at raw hardware speeds
    if it matches a 90-degree step, and composites it cleanly.
    """
    try:
        left, top, right, bottom = font.getbbox(str(text))
    except AttributeError:
        w, h = font.getsize(str(text))
        left, top, right, bottom = 0, 0, w, h

    txt_w = (right - left)
    txt_h = (bottom - top)
    pad = 4

    # Build local transparency layer
    txt_img = Image.new("RGBA", (txt_w + pad, txt_h + pad), (0, 0, 0, 0))
    txt_draw = ImageDraw.Draw(txt_img)

    draw_x = -left + (pad // 2)
    draw_y = -top + (pad // 2)
    txt_draw.text((draw_x, draw_y), str(text), font=font, fill=color)

    # Fast hardware-aligned transpose path
    # Normalize angle to positive 0-359
    norm_ang = ang % 360

    if norm_ang == 90:
        rotated_txt_img = txt_img.transpose(Image.Transpose.ROTATE_90)
    elif norm_ang == 180:
        rotated_txt_img = txt_img.transpose(Image.Transpose.ROTATE_180)
    elif norm_ang == 270:
        rotated_txt_img = txt_img.transpose(Image.Transpose.ROTATE_270)
    elif norm_ang == 0:
        rotated_txt_img = txt_img
    else:
        # Fallback for arbitrary angles if ever needed
        rotated_txt_img = txt_img.rotate(ang, expand=True)

    # Paste onto the base image
    image.paste(rotated_txt_img, pos, rotated_txt_img)


def refresh_lcd_display(display, image):
    """
    Flushes the RGB image array out across the SPI hardware bus directly.
    """
    display.ShowImage(image)


def draw_directional_arrow(draw, direction: str, pos: tuple, fill_color="white"):
    """
    Draws a 17x17 pixel arrow with 1px boundary

    :param draw: PIL ImageDraw object.
    :param direction: "up", "down", "left", or "right"
    :param x_pos: Leftmost X-coordinate for arrow
    :param y_pos: Topmost Y-coordinate for arrow
    :param fill_color: Arrow Color string or pixel value.
    """
    direction_select = direction.lower()
    if direction_select not in DIRECTION_MAP:
        raise ValueError("Direction must be 'up', 'down', 'left', or 'right'")

    arrow_points = DIRECTION_MAP[direction_select]

    x_pos, y_pos = pos
    # Translate the local coordinates to the global screen target coordinates
    global_points = [(x + x_pos, y + y_pos) for (x, y) in arrow_points]

    # Draw the arrow
    draw.polygon(global_points, fill=fill_color)
