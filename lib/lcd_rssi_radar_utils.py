# lcd_rssi_radar_utils.py
"""
lcd Radar Utilities, to be used by pi_yagi_uda.py and pi_wifi_scan_radar.py

Primary Metrics Parsing
    extract_radar_metrics(): Get peaks info from  a 360-degree array of RSSI signals

Main Radar Display
    display_radar_lcd(): High-level rendering of 240px x 240px radar screen elements.

Radar Draw Engine
    draw_rssi_polygon(): Computes multi-vertex radar coordinates area map.
    draw_crosshairs(): Draw a North solid line and dotted line for other 3 coordinates.
    draw_peak_arc(): Draws arc connecting same peak values also mean indicator.
    draw_rssi_box(): Draws tracking box at compass angle at RSSI distance.
    draw_indicator(): Switches square indicating cadence of display updates.
    arrow_annotation(): Radar image display Left/Right direction guidance for peak rotation.
    draw_box(): Draw rectangle shape at a given screen coordinate.

Vector Navigation & Geometry
    rotation_to_peak(): Calculate shortest angular difference between two directions.

Functionality
    * Peak indicator, draws arc if multiple RSSI at same peak
    * Indicator update cadence if showing continuous updates, not shown for single render
    * RSSI current value shown as box at compass heading

NOTES:
    * Colors blue and green are muted and dim, Must use "x00ff00" for green and "x0000ff" for blue

TODOs:
    * TODO should RSSI=0
"""

import math

import numpy as np
from PIL.ImageDraw import ImageDraw

from lib.lcd_st7789_utils import draw_directional_arrow
from lib.matplot_rssi_radar_utils import rssi_peak
from lib.polar_math_utils import calculate_peak_bounds

# Radar lines Boundary
SCAN_RSSI_STRONG = -30
SCAN_RSSI_WEAK = -85
CONNECT_RSSI_STRONG = -25
CONNECT_RSSI_WEAK = -85


def extract_radar_metrics(signal_history):
    """
    Parses 360-degree signal history to locate peak clusters.
    Returns: (peak_rssi, peak_degree, peak_cluster_array, valid_history)
    """
    # Create a 2D NumPy array: column 0 is degrees, column 1 is rssi
    history_array = np.column_stack((np.arange(360), signal_history))

    # Filter rows directly based on the RSSI column condition
    valid_history = history_array[history_array[:, 1] > -98]

    if len(valid_history) == 0:
        return -99.0, 0.0, None, False

    # Pass the filtered NumPy matrix to your peak locator
    arc_radians, arc_radii, peak_cluster, peak_degree, peak_rssi = rssi_peak(valid_history)
    return peak_rssi, peak_degree, peak_cluster, True


def display_rssi_polar_plot_lcd(draw, cadence_fill, heading: float, signal_history, connected, peak_degree=None,
                                peak_rssi=None, peak_cluster=None, rssi=None, magnetometer=None, rssi_min_plot=-90.0,
                                rssi_max_plot=None):
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
    center_x = 120  # vertical height, 120 is centered, 111 drops 9 px, 1px margin
    center_y = 120
    max_radius = 110

    if peak_rssi is not None and peak_rssi > -99:
        # if rssi_max_plot is not set, calculate dynamic plot range
        if rssi_max_plot is None:
            max_radius_percent = 0.90
            if peak_rssi > -45:
                # Autoscaled range when peak RSSI is stronger than -45 dBm
                rssi_max_plot = rssi_min_plot + (peak_rssi - rssi_min_plot) * (1.0 / max_radius_percent)
            else:
                # Static range bounds (-99 dBm to -45 dBm) when peak RSSI is weaker than or equal to -45 dBm
                rssi_max_plot = -45.0
    else:
        # Fallback to defaults if no signal is detected
        rssi_max_plot = CONNECT_RSSI_STRONG if connected else SCAN_RSSI_STRONG

    # if no heading orientate to North 0°
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
    draw_rssi_green_polygon(draw, signal_history, heading, center_x, center_y, max_radius, rssi_max_plot, rssi_min_plot)

    # Small white triangle pointing down at the top of the circle, notice this is 270 degree so it get rotated correctly
    right_circle_x = center_x + max_radius  # 120 + 110 = 230
    draw.polygon([
        (right_circle_x - 8, center_y),  # Tip pointing left (toward center)
        (right_circle_x + 2, center_y - 3), (right_circle_x + 2, center_y + 3)  # Base edges
    ], fill="white")

    if magnetometer is not None:
        # Draw peak signal Line indicator graphic
        if peak_rssi is not None and peak_degree is not None:
            draw_peak_arc(draw, heading, center_x, center_y, max_radius,
                          rssi_max_plot, rssi_min_plot, peak_degree, peak_rssi, peak_cluster)

        # Draw box at current RSSI strength in antenna direction
        draw_rssi_box(draw=draw, rssi=rssi, target_degree=0.0, heading=0.0, center_x=center_x,
                      center_y=center_y, max_radius=max_radius, strong_bound=rssi_max_plot,
                      weak_bound=rssi_min_plot, box_size=12, color="cyan")

        # RSSI Bar circles (-50 solid, -60/-70/-80 dashed)
        rssi_targets = [
            {"rssi": -50, "dashed": False},
            {"rssi": -60, "dashed": True},
            {"rssi": -70, "dashed": True},
            {"rssi": -80, "dashed": True},
        ]

        for item in rssi_targets:
            val = item["rssi"]
            # Check if target RSSI falls within current plot bounds
            if rssi_min_plot <= val <= rssi_max_plot:
                # Map RSSI to radius, center is min_plot and outer edge is max_plot
                fraction = (val - rssi_min_plot) / (rssi_max_plot - rssi_min_plot)
                radius = int(max_radius * fraction)

                if radius > 0:
                    if item["dashed"]:
                        draw_dashed_circle(draw, center_x, center_y,radius, outline="white", dash_deg=10, gap_deg=5,)
                    else:
                        # Solid circle for -50 dBm
                        draw.ellipse([center_x - radius, center_y - radius, center_x + radius, center_y + radius,], outline="white")

    # Center axis core marker Blue give hex so it is bright blue
    draw.rectangle((center_x - 2, center_y - 2, center_x + 1, center_y + 1), fill="#00ff00")


def draw_rssi_green_polygon(draw, signal_history, heading: float, center_x: int, center_y: int, max_radius: int,
                            strong_bound: int,
                            weak_bound: int):
    """
    draw_rssi_polygon draws polygon whose vertices are clamped from lower bound at center (0 length) to
    upper bound (farthest out).

    """
    # Antenna strength polygon vertex points at 5 degrees intervals, will create polygon with 72 vertices (360/5)
    polygon_points = []
    for angle in range(0, 360, 5):
        window_values = []

        # Get maximum rssi value over a local 5-degree window (±2°) of RSSI values, wrapping around the 360° compass
        for offset in range(-2, 3):
            neighbor_index = (angle + offset) % 360
            window_values.append(signal_history[neighbor_index])
        vertex_rssi = max(window_values)

        # Ensure no zero division error
        bound_range = strong_bound - weak_bound if strong_bound != weak_bound else 1

        # Clamp peak value within our newly calculated limits
        vertex_rssi = max(weak_bound, min(vertex_rssi, strong_bound))

        # Scale across the entire functional pixel radius length
        proportion = (vertex_rssi - weak_bound) / bound_range
        line_length = max_radius * proportion

        # Apply identical screen space angle mapping
        angle_rad = math.radians(heading - angle)

        target_x = int(center_x + line_length * math.cos(angle_rad))
        target_y = int(center_y - line_length * math.sin(angle_rad))  # Subtracted for screen-space Y

        polygon_points.append((target_x, target_y))

    # Draw the Antenna strength/direction polygon in pure green
    if len(polygon_points) >= 3:
        draw.polygon(polygon_points, fill="#00ff00", outline="#00ff00")


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


def draw_peak_arc(draw, heading: float, center_x: int, center_y: int, max_radius: int,
                  strong_bound: int, weak_bound: int, peak_degree: float, peak_rssi: float, peak_cluster):
    """ Draws a heavy red vector pointer and an arc across matching peaks."""
    if peak_rssi <= -99:
        return

    outer_marker_radius = max_radius + 10
    bound_range = strong_bound - weak_bound if strong_bound != weak_bound else 1

    # Dynamic calculation mapping val straight to the main radius metrics
    val_clamped = max(weak_bound, min(peak_rssi, strong_bound))
    r_peak = max_radius * ((val_clamped - weak_bound) / bound_range)

    # Align peak indicator line with vector mean
    peak_angle_rad = math.radians(heading - peak_degree)

    x_peak = int(center_x + r_peak * math.cos(peak_angle_rad))
    y_peak = int(center_y - r_peak * math.sin(peak_angle_rad))
    x_edge = int(center_x + outer_marker_radius * math.cos(peak_angle_rad))
    y_edge = int(center_y - outer_marker_radius * math.sin(peak_angle_rad))

    halfway_radius = (outer_marker_radius + r_peak) / 2
    x_halfway = int(center_x + halfway_radius * math.cos(peak_angle_rad))
    y_halfway = int(center_y - halfway_radius * math.sin(peak_angle_rad))

    # Draw thin line from peak point to halfway to circle, Thick line from halfway to 10px past outer edge
    # draw.line([(x_halfway, y_halfway), (x_peak, y_peak)], fill="yellow", width=3)
    draw.line([(center_x, center_y), (x_peak, y_peak)], fill="red", width=5)  #
    draw.line([(x_edge, y_edge), (x_halfway, y_halfway)], fill="red", width=9)

    # Render the boundary tracking arc using the shared helper bounds
    if peak_cluster is not None and isinstance(peak_cluster, np.ndarray) and len(peak_cluster) > 1:
        # Access Column 0 directly for degrees since peak_cluster is a 2D NumPy array
        degrees = peak_cluster[:, 0]

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


def draw_rssi_box(draw, rssi: int, target_degree: float, heading: float, center_x: int, center_y: int,
                  max_radius: int, strong_bound: int, weak_bound: int, box_size: int = 10, color: str = "cyan"):
    """
    Draws a box at a specific degree orientation, positioned at a distance
    proportional to the provided RSSI signal strength from a center coordinate.
    Only odd numbered box sizes are symmetric about the position.
    """
    # Prevent handling empty out-of-range scans
    if rssi is None or rssi <= -99:
        return

    box_size = max(box_size, 3)

    # Enforce an odd number so there a single-pixel center point
    if box_size % 2 == 0:
        box_size += 1

    # Scale the RSSI to fit usable range
    bound_range = strong_bound - weak_bound if strong_bound != weak_bound else 1
    clamped_rssi = max(weak_bound, min(rssi, strong_bound))
    proportion = (clamped_rssi - weak_bound) / bound_range
    distance = max_radius * proportion
    half_size = box_size // 2

    # half-size*sqrt(2) makes sure box corners not outside radius, avoid negative distances
    max_center_distance = max_radius - (half_size * 1.41421356)
    max_center_distance = max(0.0, max_center_distance)
    distance = min(distance, max_center_distance)

    # Translate coordinates to respect the current radar display orientation
    angle_rad = math.radians(heading - target_degree)

    # Project the box from center point
    box_center_x = int(center_x + distance * math.cos(angle_rad))
    box_center_y = int(center_y - distance * math.sin(angle_rad))  # Subtracted for screen-space Y

    # draw color outer box
    x0 = box_center_x - half_size
    y0 = box_center_y - half_size
    x1 = x0 + box_size - 1
    y1 = y0 + box_size - 1
    draw.rectangle((x0, y0, x1, y1), outline=color)

    # draw black inner box
    x0_inner = x0 + 1
    y0_inner = y0 + 1
    x1_inner = x1 - 1
    y1_inner = y1 - 1
    draw.rectangle((x0_inner, y0_inner, x1_inner, y1_inner), outline="black")


def draw_dashed_circle(
    draw, center_x, center_y, radius, outline, dash_deg=6, gap_deg=4
):
  """Draws a dashed circle using arc segments."""
  if radius <= 0:
    return
  current_angle = 0
  while current_angle < 360:
    start_angle = current_angle
    end_angle = min(current_angle + dash_deg, 360)
    bbox = [
        center_x - radius,
        center_y - radius,
        center_x + radius,
        center_y + radius,
    ]
    draw.arc(bbox, start=start_angle, end=end_angle, fill=outline)
    current_angle += dash_deg + gap_deg


def draw_indicator(draw, cadence_fill, x_box: int, y_box: int, dot_size: int):
    """ Draw indicator, then toggle to next state """
    if cadence_fill is not None:
        outer_color = "white" if int(cadence_fill) == 1 else "black"
        inner_color = "black" if int(cadence_fill) == 1 else "white"
        draw.rectangle((x_box, y_box, x_box + dot_size + 4, y_box + dot_size + 4), fill=outer_color)
        draw.rectangle((x_box + 2, y_box + 2, x_box + dot_size + 2, y_box + dot_size + 2), fill=inner_color)


def arrow_annotation(disp1_draw: ImageDraw, shortest_angle,
                     left_arrow_position, right_arrow_position):
    """Draw arrows to show the shortest rotation to peak"""
    if shortest_angle is None or shortest_angle == 0:
        return
    if shortest_angle < 0:
        draw_directional_arrow(disp1_draw, "left", left_arrow_position, fill_color="red")
    if shortest_angle > 0:
        draw_directional_arrow(disp1_draw, "right", right_arrow_position, fill_color="red")
    return


def draw_box(draw, x_box: int, y_box: int, dot_size: int, color: str):
    """ Draw box at location, with dot size, and selected color """
    draw.rectangle((x_box, y_box, x_box + dot_size + 4, y_box + dot_size + 4), fill=color)


def rotation_to_peak(compass, peak_rssi_angle):
    """ degree rotation to peak
        clockwise: shortest_angle > 0
        counter-clockwise: shortest_angle < 0:
    """
    if compass is not None and peak_rssi_angle is not None:
        diff = peak_rssi_angle - compass
        shortest_angle = (diff + 180) % 360 - 180
        return shortest_angle
    else:
        return None
