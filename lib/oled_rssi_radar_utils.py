import math

from lib.lcd_rssi_radar_utils import CONNECT_RSSI_STRONG, SCAN_RSSI_STRONG, CONNECT_RSSI_WEAK, SCAN_RSSI_WEAK


def display_radar_oled(draw, cadence_fill, heading: float, signal_history, connected):
    """
    Draw a white box with a black radar circle in it.
    Add white directional orientation lines for North, East, South, and West.
    Calculates a solid white polygon tracking signal strength vs compass directions.
    """
    center_x = 112
    center_y = 15
    max_radius = 16

    strong_bound = CONNECT_RSSI_STRONG if connected else SCAN_RSSI_STRONG
    weak_bound = CONNECT_RSSI_WEAK if connected else SCAN_RSSI_WEAK

    if heading is None:
        heading = 0.0

    # Radar graphics layout
    draw.rectangle((96, 0, 127, 31), fill=1)
    draw.ellipse((center_x - max_radius, center_y - max_radius + 1,
                  center_x + max_radius - 1, center_y + max_radius),
                 outline=0, fill=0)

    # Cadence indicator block
    x_box, y_box, dot_size = 90, 0, 3
    draw.rectangle((x_box, y_box, x_box + dot_size + 1, y_box + dot_size + 1), fill=1 - int(cadence_fill))
    draw.rectangle((x_box + 1, y_box + 1, x_box + dot_size, y_box + dot_size), fill=int(cadence_fill))

    # Solid North Crosshair
    north_rad = math.radians(heading - 0.0)
    nx = int(center_x + max_radius * math.cos(north_rad))
    ny = int(center_y - max_radius * math.sin(north_rad))
    draw.line((center_x, center_y, nx, ny), fill=1)

    # Dashed Crosshairs (South, West, East)
    south_rad = math.radians(heading - 180.0)
    west_rad = math.radians(heading - 270.0)
    east_rad = math.radians(heading - 90.0)
    for r in range(0, max_radius + 1, 4):
        draw.point((int(center_x + r * math.cos(south_rad)), int(center_y - r * math.sin(south_rad))), fill=1)
        draw.point((int(center_x + r * math.cos(west_rad)), int(center_y - r * math.sin(west_rad))), fill=1)
        draw.point((int(center_x + r * math.cos(east_rad)), int(center_y - r * math.sin(east_rad))), fill=1)

    # Antenna strength polygon vertices (72 vertices)
    polygon_points = []
    for angle in range(0, 360, 5):
        window_values = []
        for offset in range(-2, 3):
            neighbor_index = (angle + offset) % 360
            window_values.append(signal_history[neighbor_index])

        saved_rssi = max(window_values)

        if saved_rssi < weak_bound:
            saved_rssi = weak_bound
        elif saved_rssi > strong_bound:
            saved_rssi = strong_bound

        proportion = (saved_rssi - weak_bound) / (strong_bound - weak_bound)
        line_length = (max_radius - 2) * proportion

        angle_rad = math.radians(heading - angle)
        target_x = int(center_x + line_length * math.cos(angle_rad))
        target_y = int(center_y - line_length * math.sin(angle_rad))
        polygon_points.append((target_x, target_y))

    if len(polygon_points) >= 3:
        draw.polygon(polygon_points, fill=1, outline=1)

    # Center axis marker dots
    draw.point((center_x - 1, center_y - 1), fill=0)
    draw.point((center_x, center_y - 1), fill=0)
    draw.point((center_x - 1, center_y), fill=0)
    draw.point((center_x, center_y), fill=0)
