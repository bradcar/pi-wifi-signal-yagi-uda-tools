# lcd_rssi_polar_utils.py
"""
lcd Radar Utilities, to be used by pi_yagi_uda.py an di_wifi_scan_radar.py



Functionality
    * Peak indicator, draws arc if multiple RSSI at same peak
    * Indicator update cadence if showing continuous updates, not shown for single render
"""

import time

import math
from PIL import Image, ImageDraw

from lib.radar_math_utils import calculate_peak_bounds

# Radar lines Boundary
SCAN_RSSI_STRONG = -30
SCAN_RSSI_WEAK = -80
CONNECT_RSSI_STRONG = -30
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


def draw_peak_arc(draw, heading: float, center_x: int, center_y: int, max_radius: int,
                  strong_bound: int, weak_bound: int, peak_degree: float, peak_rssi: float, peak_cluster):
    """
    Draws a heavy red vector pointer and an encompassing signal arc across matching peak boundaries.
    """
    max_signal_radius = max_radius - 10
    outer_marker_radius = max_radius + 10

    def rssi_to_radius(val):
        if val < weak_bound: val = weak_bound
        if val > strong_bound: val = strong_bound
        proportion = (val - weak_bound) / (strong_bound - weak_bound)
        return max_signal_radius * proportion

    # Align primary needle with the clean shared vector mean
    peak_angle_rad = math.radians(heading - peak_degree)
    r_peak = rssi_to_radius(peak_rssi)

    x_peak = int(center_x + r_peak * math.cos(peak_angle_rad))
    y_peak = int(center_y - r_peak * math.sin(peak_angle_rad))
    x_edge = int(center_x + outer_marker_radius * math.cos(peak_angle_rad))
    y_edge = int(center_y - outer_marker_radius * math.sin(peak_angle_rad))

    halfway_radius = (outer_marker_radius + r_peak) / 2
    x_halfway = int(center_x + halfway_radius * math.cos(peak_angle_rad))
    y_halfway = int(center_y - halfway_radius * math.sin(peak_angle_rad))

    # Draw pointer hardware indicators
    draw.line([(x_edge, y_edge), (x_halfway, y_halfway)], fill="red", width=7)
    draw.line([(x_halfway, y_halfway), (x_peak, y_peak)], fill="red", width=3)

    # Render the boundary tracking arc using the shared helper bounds
    if peak_cluster is not None and len(peak_cluster) > 1:
        degrees = peak_cluster['degree'].to_numpy()

        # Call the exact same shared logic used by the high-res engine
        _, first_deg, last_deg = calculate_peak_bounds(degrees)

        # Convert back to integers for the pixel step range
        first_deg, last_deg = int(first_deg), int(last_deg)

        if last_deg < first_deg:
            sweep_range = list(range(first_deg, 360)) + list(range(0, last_deg + 1))
        else:
            sweep_range = list(range(first_deg, last_deg + 1))

        arc_points = []
        for deg in sweep_range:
            rad = math.radians(heading - deg)
            ax = int(center_x + r_peak * math.cos(rad))
            ay = int(center_y - r_peak * math.sin(rad))
            arc_points.append((ax, ay))

        if len(arc_points) >= 2:
            draw.line(arc_points, fill="red", width=4)


def draw_indicator(draw, cadence_fill, x_box: int, y_box: int, dot_size: int):
    """ show indicator, then toggle to next state """
    if cadence_fill is not None:
        outer_color = "white" if int(cadence_fill) == 1 else "black"
        inner_color = "black" if int(cadence_fill) == 1 else "white"
        draw.rectangle((x_box, y_box, x_box + dot_size + 4, y_box + dot_size + 4), fill=outer_color)
        draw.rectangle((x_box + 2, y_box + 2, x_box + dot_size + 2, y_box + dot_size + 2), fill=inner_color)


def draw_crosshairs(draw, heading: float, center_x: int, center_y: int, max_radius: int):
    """ Draw Crosshairs in cardinal directions """
    # Solid North Crosshair
    north_rad = math.radians(heading)
    nx = int(center_x + max_radius * math.cos(north_rad))
    ny = int(center_y - max_radius * math.sin(north_rad))
    draw.line((center_x, center_y, nx, ny), fill="white", width=2)

    # Dashed Crosshairs (South, West, East)
    south_rad = math.radians(heading - 180)
    west_rad = math.radians(heading - 270)
    east_rad = math.radians(heading - 90)

    for r in range(0, max_radius + 1, 12):
        sx = int(center_x + r * math.cos(south_rad))
        sy = int(center_y - r * math.sin(south_rad))
        draw.ellipse((sx - 1, sy - 1, sx + 1, sy + 1), fill="white")

        wx = int(center_x + r * math.cos(west_rad))
        wy = int(center_y - r * math.sin(west_rad))
        draw.ellipse((wx - 1, wy - 1, wx + 1, wy + 1), fill="white")

        ex = int(center_x + r * math.cos(east_rad))
        ey = int(center_y - r * math.sin(east_rad))
        draw.ellipse((ex - 1, ey - 1, ex + 1, ey + 1), fill="white")


def display_radar_splash_lcd(disp_2):
    """ Splash art jpg on display 2"""
    try:
        radar_image = Image.open("assets/images/radiant-ether-098.jpg")
        rotated_radar = radar_image.rotate(270)
        disp_2.ShowImage(rotated_radar)
    except IOError:
        print("Wallpaper 'radiant-ether-098.jpg' not found at project root. Skipping center lcd")


def display_radar_lcd(draw, cadence_fill, heading: float, signal_history, connected,
                      peak_degree=None, peak_rssi=None, peak_cluster=None):
    """
    Draw a white box with a black radar circle in it.
    Add white directional orientation lines for North, East, South, and West.
    Calculates a solid white polygon tracking signal strength vs compass directions.
    Tailored for 240px x 240px RGB LCD panel configurations.

    Time:
    * indicator  6ms
    * polygon   17ms
    * arc        0.7ms

    """
    center_x = 120
    center_y = 120
    max_radius = 110

    strong_bound = CONNECT_RSSI_STRONG if connected else SCAN_RSSI_STRONG
    weak_bound = CONNECT_RSSI_WEAK if connected else SCAN_RSSI_WEAK

    if heading is None:
        heading = 0.0

    # Draw basic radar layout
    draw.rectangle((0, 0, 240, 240), fill="#111111")
    draw.ellipse((center_x - max_radius, center_y - max_radius,
                  center_x + max_radius, center_y + max_radius),
                 outline="black", fill="black")

    # draw indicator, crosshairs and RSSI polygon
    draw_indicator(draw, cadence_fill, x_box=210, y_box=10, dot_size=15)
    draw_crosshairs(draw, heading, center_x, center_y, max_radius)
    draw_polygon(draw, signal_history, heading, center_x, center_y, max_radius, strong_bound, weak_bound)

    # peak signal graphic
    if peak_rssi is not None and peak_degree is not None:
        draw_peak_arc(draw, heading, center_x, center_y, max_radius,
                      strong_bound, weak_bound, peak_degree, peak_rssi, peak_cluster)
    # Center axis core marker
    draw.rectangle((center_x - 2, center_y - 2, center_x + 1, center_y + 1), fill="black")
