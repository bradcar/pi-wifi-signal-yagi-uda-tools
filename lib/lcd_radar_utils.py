# lcd_radar_utils.py
"""
lcd Radar Utilities, to be used by pi_yagi_uda.py an di_wifi_scan_radar.py

Functionality
    * Peak indicator, draws arc if multiple RSSI at same peak
    *
"""

import math

from PIL import Image

# from pi_yagi_uda import CONNECT_RSSI_STRONG, SCAN_RSSI_STRONG, CONNECT_RSSI_WEAK, SCAN_RSSI_WEAK

# Radar lines Boundary
SCAN_RSSI_STRONG = -20  # -65
SCAN_RSSI_WEAK = -80
CONNECT_RSSI_STRONG = -20
CONNECT_RSSI_WEAK = -75


def draw_polygon(draw, signal_history, heading: float, center_x: int, center_y: int, max_radius: int, strong_bound: int,
                 weak_bound: int):
    # Antenna strength polygon vertex points at 5 degrees intervals, 72 vertices
    polygon_points = []
    for angle in range(0, 360, 5):
        window_values = []
        for offset in range(-2, 3):
            neighbor_index = (angle + offset) % 360
            window_values.append(signal_history[neighbor_index])

        saved_rssi = max(window_values)

        # Apply the dynamic bounds
        if saved_rssi < weak_bound:
            saved_rssi = weak_bound
        elif saved_rssi > strong_bound:
            saved_rssi = strong_bound

        # Calculate proportion using dynamic bounds
        proportion = (saved_rssi - weak_bound) / (strong_bound - weak_bound)
        # Keep a 5px offset inward so outer boundary lines remain clean
        line_length = (max_radius - 5) * proportion

        # Apply identical screen space angle mapping
        angle_rad = math.radians(heading - angle)

        target_x = int(center_x + line_length * math.cos(angle_rad))
        target_y = int(center_y - line_length * math.sin(angle_rad))  # Subtracted for screen-space Y

        polygon_points.append((target_x, target_y))

    # Draw the Antenna strength/direction polygon in pure green
    if len(polygon_points) >= 3:
        draw.polygon(polygon_points, fill="#00ff00", outline="#00ff00")


def draw_indicator(draw, cadence_fill, x_box: int, y_box: int, dot_size: int):
    # Toggle color rendering based on cadence fill state
    if cadence_fill is not None:
        outer_color = "white" if int(cadence_fill) == 1 else "black"
        inner_color = "black" if int(cadence_fill) == 1 else "white"
        draw.rectangle((x_box, y_box, x_box + dot_size + 4, y_box + dot_size + 4), fill=outer_color)  # Outer Box
        draw.rectangle((x_box + 2, y_box + 2, x_box + dot_size + 2, y_box + dot_size + 2),
                       fill=inner_color)  # Inner dot


def draw_crosshairs(draw, heading: float, center_x: int, center_y: int, max_radius: int):
    # Solid North Crosshair
    north_rad = math.radians(heading)
    nx = int(center_x + max_radius * math.cos(north_rad))
    ny = int(center_y - max_radius * math.sin(north_rad))  # Subtracted for screen-space Y
    draw.line((center_x, center_y, nx, ny), fill="white", width=2)

    # Dashed Crosshairs (South, West, East)
    south_rad = math.radians(heading - 180)
    west_rad = math.radians(heading - 270)
    east_rad = math.radians(heading - 90)

    # Dashes scaled up to every 12px for high-density rendering clarity
    for r in range(0, max_radius + 1, 12):
        # South
        sx = int(center_x + r * math.cos(south_rad))
        sy = int(center_y - r * math.sin(south_rad))
        draw.ellipse((sx - 1, sy - 1, sx + 1, sy + 1), fill="white")

        # West
        wx = int(center_x + r * math.cos(west_rad))
        wy = int(center_y - r * math.sin(west_rad))
        draw.ellipse((wx - 1, wy - 1, wx + 1, wy + 1), fill="white")

        # East
        ex = int(center_x + r * math.cos(east_rad))
        ey = int(center_y - r * math.sin(east_rad))
        draw.ellipse((ex - 1, ey - 1, ex + 1, ey + 1), fill="white")


def display_radar_splash_lcd(disp_2):
    try:
        radar_image = Image.open("assets/images/radiant-ether-098.jpg")
        rotated_radar = radar_image.rotate(270)
        disp_2.ShowImage(rotated_radar)
    except IOError:
        print("Wallpaper 'yagi-uda-dark.jpg' not found at project root. Skipping center lcd")


def display_radar_lcd(draw, cadence_fill, heading: float, signal_history, connected):
    """
    Draw a white box with a black radar circle in it.
    Add white directional orientation lines for North, East, South, and West.
    Calculates a solid white polygon tracking signal strength vs compass directions.
    Tailored for 240px x 240px RGB LCD panel configurations.
    """
    # Optimized center and layout bounding coordinates for 240x240 geometry
    center_x = 120
    center_y = 120
    max_radius = 110

    # Select radar line length bounds based on mode
    strong_bound = CONNECT_RSSI_STRONG if connected else SCAN_RSSI_STRONG
    weak_bound = CONNECT_RSSI_WEAK if connected else SCAN_RSSI_WEAK

    if heading is None:
        heading = 0.0

    # Radar graphics: white background block covering full canvas, black circle mask
    draw.rectangle((0, 0, 240, 240), fill="#111111")
    draw.ellipse((center_x - max_radius, center_y - max_radius,
                  center_x + max_radius, center_y + max_radius),
                 outline="black", fill="black")

    # Cadence indicator box in upper right text region
    draw_indicator(draw, cadence_fill, x_box=210, y_box=10, dot_size=15)

    draw_crosshairs(draw, heading, center_x, center_y, max_radius)

    draw_polygon(draw, signal_history, heading, center_x, center_y, max_radius, strong_bound, weak_bound)

    # Center axis markers & black center dot on top of everything (Scaled to 4x4 box)
    draw.rectangle((center_x - 2, center_y - 2, center_x + 1, center_y + 1), fill="black")
