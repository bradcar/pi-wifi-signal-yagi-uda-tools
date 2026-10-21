#
"""
wifi_directional_utils.py

Collection of utility functions for mapping Wi-Fi source locations with data from a directional antenna.

estimate_wifi_distance - Crude estimate of Wi-Fi distance using a log-distance path loss model and antenna gain.
plot_wifi_source_angle_rssi - Create a 2D polar plot mapping Wi-Fi by angle and RSSI signal strength.
plot_wifi_sources_angle_crude_distance - Create 2D polar plot of estimated Wi-Fi distance and angle from the antenna.
calculate_target_gps_crude - Calculate GPS coordinates given an origin, distance, and bearing using spherical earth.
calculate_target_gps_vincenty - Calculate GPS coordinates given an origin, distance, and bearing using Vincenty's Formula.
calculate_target_gps_WGGS84 - Calculate GPS coordinates given an origin, distance, and bearing using WGS84 ellipsoid.
export_summary_to_gpx - Reads a CSV file, estimates Wi-Fi's GPS coordinates, and exports a GPX file (Apple Maps).
export_summary_to_kml - Reads a CSV file, estimates Wi-Fi's GPS coordinates, and exports a GPX file (Google My Maps).

"""

import csv
import math
import xml.etree.ElementTree as ele_tree
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


# TODO FIX Internet sharing and INSTALL THIS PACKAGE
# from geographiclib.geodesic import Geodesic


def crude_estimate_wifi_distance(
        rssi_measured: float,
        angle_offset_deg: float = 0.0,  # assume peak
        p0_1m: float = -8.0,  # example p0 at 1 meter reference
        path_loss_n: float = 3.5,  # suburban heavy
        beamwidth_3db_deg: float = 28.0,  # degrees for sample Techtoo Yagi Uda 18.5 dBi Antenna
):
    """
    crude_estimate_wifi_meters is a VERY ROUGH GUESS.

    CAUTION: It is not suited for mixed free space and suburban environments as it is unlikely to give
    any reasonable accuracy.

    Estimates distance to a Wi-Fi source given a measured RSSI and off-axis angle.
    Typically best to use peaks and avoid off-axis angles.
    This code uses a standard Log-Distance Path Loss model and a Gaussian Antenna Gain Approximation.

    Log-Distance Path Loss model:
    The standard Log-Distance Path Loss model relates received signal power (RSSI) to distance d:
        d = 10 ^ ((P0 - RSSI) / 10 * n)
        Where:
            n = 2.0         free space and clear line of sight
            n = 2.7 to 3.5  suburban or light foliage environments
            n = 3.5 to 4.0  indoor or heavy obstruction

    Gaussian Antenna Gain Approximation:
    Near the main lobe center, off-axis gain attenuation is modeled as:
        Gain_off_axis(theta) = -3.0 * (theta / (beamwidth_full_3db_deg / 2)) ^ 2
    This ensures a precise -3dB attenuation at the half-power beam edge.

    Accuracy:
        * CAUTION: Distance estimation is VERY CRUDE and requires tuning to get parameters to match environment.
          Evironment must be uniform.
        * improving this would take multiple experiments and calibrations
        * likely poor due to plausibile but crude estimate of P0_1m of -30 dBm guess.
        * path_loss_n = 3.5, reasonble but high variability
        * beamwidth_horiz_deg = 28.0, example for Techtoo Yagi Uda 18.5 dBi
        * lobe_coefficient = -12.0, approximate

    # Example Usage:
        # Distance based on Peak hit (0° offset) at various RSSI
        for rssi in [-51.0, -60, -70.0, -80.0, -85.0, -90]:
            meters_to_source = crude_estimate_wifi_meters(rssi_measured=rssi, angle_offset_deg=0)
            print(f"Peak Boresight Distance for RSSI={rssi:.0f}: {meters_to_source:.1f} meters")

    :param rssi_measured: Raw RSSI value in dBm
    :param angle_offset_deg: Misalignment angle from peak bearing (degrees)
    :param p0_1m: RSSI measured at a distance of one meter (dBm)
    :param path_loss_n: Path loss exponent (2.0=LOS, 2.5–3.5=suburban)
    :param beamwidth_3db_deg: Horizontal 3dB beamwidth of the Yagi (degrees)
    :return: Estimated distance in meters
    """
    # Correct for off-axis antenna pattern attenuation
    lobe_coefficient = -12.0

    # Approximate antenna attenuation relative to boresight.
    # If beamwidth_3db_deg is the total span (ex: 28°), then half-angle is half of that:
    half_beamwidth = beamwidth_3db_deg / 2.0
    theta = abs(angle_offset_deg)

    # At theta == half_beamwidth, gain should equal -3 dB:
    gain_off_axis_db = -3.0 * (theta / half_beamwidth) ** 2

    # Subtract off-axis dBm lose
    rssi_boresight = rssi_measured - gain_off_axis_db

    # Log-distance path-loss model, using d0 @ 1 meter. Return distance in meters.
    exponent = (p0_1m - rssi_boresight) / (10.0 * path_loss_n)
    return 10.0 ** exponent


def plot_wifi_source_angle_rssi(summary_csv_path: str):
    """
    Reads the summary CSV file and generates a 2-D polar radar plot
    where the center circle represents -45 dBm (strong)
    and the outer circle represents -99 dBm (weak).

    :param summary_csv_path: Path to the summary_{timestamp}.csv file.
    """
    path = Path(summary_csv_path)
    if not path.exists():
        print(f"Error: Summary file not found at {path}")
        return

    ssids = []
    rssi_values = []
    angles_rad = []

    # Read the CSV datafile
    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ssid = row["ssid"]
            max_rssi = float(row["max_rssi"])
            peak_angle_string = row["peak_angle"]

            # Clamp RSSI to -45 to -99 dBm
            clamped_rssi = max(-99.0, min(-45.0, max_rssi))

            # Convert compass heading (0° North, clockwise) to polar angle (0° East, counter-clockwise)
            if peak_angle_string.strip().lower() == "omni":
                peak_angle_degree = 0.0
            else:
                peak_angle_degree = float(peak_angle_string)
            angle_rad = np.radians(peak_angle_degree)

            ssids.append(ssid)
            rssi_values.append(clamped_rssi)
            angles_rad.append(angle_rad)

    if not rssi_values:
        print("No valid entries found in the CSV data file to plot.")
        return

    # Map RSSI to Polar Radius (r) based on -45 dBm center
    # -45 dBm maps to r = 0 (center)
    # -99 dBm maps to r = 54 (outer circle)
    radii = [-45.0 - rssi for rssi in rssi_values]

    # Set up Polar Plot
    fig, ax = plt.subplots(subplot_kw={'projection': 'polar'}, figsize=(8, 8))

    # Configure 0 degrees to point Up (North) and sweep clockwise
    ax.set_theta_zero_location('N')
    ax.set_theta_direction(-1)

    # Set radial limits from -45 center (0) to -99 outer (54 span)
    ax.set_ylim(0, 54)

    # Custom radial ticks corresponding to dBm levels anchored to -45 center
    tick_rssis = [-45, -50, -60, -70, -80, -90, -99]
    tick_radii = [-45.0 - r for r in tick_rssis]
    ax.set_yticks(tick_radii)
    ax.set_yticklabels([f"{r} dBm" for r in tick_rssis], color="gray", fontsize=8)
    ax.grid(True, color='lightgray', linestyle='--', linewidth=0.8, alpha=0.6)

    # Map each RSSI value to its pre-calculated radius
    rssi_radius_map = dict(zip(tick_rssis, tick_radii))

    # 1-bar dotted: -80 dB, 2-bar dashed: -70 dB, 3-bar dashed: -60 dB, 4-bar solid: -50 dB
    circle_theta = np.linspace(0, 2 * np.pi, 360)
    ax.plot(circle_theta, np.full_like(circle_theta, rssi_radius_map[-80]), color='orange', linestyle=':', linewidth=1,
            zorder=3, label='-80 dBm (1-Bar)')
    ax.plot(circle_theta, np.full_like(circle_theta, rssi_radius_map[-70]), color='orange', linestyle='--', linewidth=1,
            zorder=3, label='-70 dBm (2-Bars)')
    ax.plot(circle_theta, np.full_like(circle_theta, rssi_radius_map[-60]), color='orange', linestyle='--', linewidth=1,
            zorder=3, label='-60 dBm (3-Bars)')
    ax.plot(circle_theta, np.full_like(circle_theta, rssi_radius_map[-50]), color='orange', linestyle='-', linewidth=1,
            zorder=3, label='-50 dBm (4-Bars)')

    # Plot points for each Wi-Fi source
    for ssid, r, angle in zip(ssids, radii, angles_rad):
        # Marker for the Wi-Fi source location
        ax.scatter(angle, r, color='blue', s=20, zorder=4)

        # SSID text label near the point
        ax.text(angle, r + 1.5, f" {ssid[:12]}", fontsize=7, color='black', va='center', zorder=5)

    # Plot Antenna Center Marker
    ax.scatter(0, 0, color='red', marker='^', s=120, zorder=1, label='Yagi Uda Antenna')

    # Plot annotations
    ax.set_title("Wi-Fi RSSI Radar Map (-45 dBm to -99 dBm Edge)", va='bottom', fontsize=12, fontweight='bold')
    ax.legend(loc='upper right', bbox_to_anchor=(1.05, 0.01), fontsize=8)
    fig.text(0.02, 0.02, f"Data: {path}", fontsize=9, color='black', ha='left', va='bottom', wrap=True)

    # Save plot in the same directory as the CSV data file
    output_plot_path = path.parent / f"{path.stem}_angle-rssi.png"
    plt.tight_layout()
    plt.savefig(output_plot_path, dpi=1200)
    print(f"-> Saved RSSI radar map to '{output_plot_path}'")

    plt.show()


def plot_wifi_sources_angle_crude_distance(summary_csv_path: str):
    """
    Reads the CSV data file and generates a 2-D polar/cartesian scatter plot
    showing the antenna at the center (0,0), with lines and points indicating
    the estimated distance and direction of each Wi-Fi source.

    CAUTION: Distance estimation is VERY CRUDE and requires tuning to get parameters to match environment.
    Evironment must be uniform.

    :param summary_csv_path: Path to the summary_{timestamp}.csv file.
    """
    path = Path(summary_csv_path)
    if not path.exists():
        print(f"Error: Summary file not found at {path}")
        return

    ssids = []
    distances = []
    angles_rad = []

    # Read the CSV data file
    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ssid = row["ssid"]
            bssid = row["bssid"]
            max_rssi = float(row["max_rssi"])
            peak_angle_string = row["peak_angle"]

            print(f"ssid: {ssid}, peak_angle: {peak_angle_string}, max_rssi: {max_rssi}")

            # Estimate distance using crude log-distance model using peak RSSI
            distance = crude_estimate_wifi_distance(rssi_measured=max_rssi, angle_offset_deg=0.0)

            # Convert compass heading (0° North, clockwise) to polar angle (0° East, counter-clockwise)
            if peak_angle_string.strip().lower() == "omni":
                peak_angle_degree = 0.0
            else:
                peak_angle_degree = float(peak_angle_string)
            angle_rad = np.radians(peak_angle_degree)

            ssids.append(ssid)
            distances.append(distance)
            angles_rad.append(angle_rad)

    if not distances:
        print("No valid entries found in the CSV data file to plot.")
        return

    # Set up Polar Plot
    fig, ax = plt.subplots(subplot_kw={'projection': 'polar'}, figsize=(8, 8))

    # Configure 0 degrees to point Up (North) and sweep clockwise
    ax.set_theta_zero_location('N')
    ax.set_theta_direction(-1)

    # Set the outer boundary ring to maximum distance
    max_dist = max(distances) if distances else 100.0
    grid_max = max_dist

    # Create 50m step ticks, and append the max distance at outer edge
    metric_ticks = np.arange(50.0, grid_max, 50.0)
    if len(metric_ticks) == 0 or metric_ticks[-1] < grid_max:
        metric_ticks = np.append(metric_ticks, grid_max)

    # Set plot limits to distance of furthest point
    ax.set_ylim(0, grid_max)
    ax.set_yticks(metric_ticks)
    ax.set_yticklabels([f"{int(m)}m" if m != grid_max else f"{m:.1f}m" for m in metric_ticks], color="gray", fontsize=8)
    ax.grid(True, color='lightgray', linestyle='--', linewidth=0.8, alpha=0.6)

    # Plot the RSSI distance rings (1-bar to 4-bar equivalents)
    circle_theta = np.linspace(0, 2 * np.pi, 360)
    ax.plot(circle_theta,
            np.full_like(circle_theta, crude_estimate_wifi_distance(rssi_measured=-80, angle_offset_deg=0.0)),
            color='orange', linestyle='-', linewidth=1, zorder=3, label='-80 dBm (1-Bar)')
    ax.plot(circle_theta,
            np.full_like(circle_theta, crude_estimate_wifi_distance(rssi_measured=-70, angle_offset_deg=0.0)),
            color='orange', linestyle='--', linewidth=1, zorder=3, label='-70 dBm (2-Bars)')
    ax.plot(circle_theta,
            np.full_like(circle_theta, crude_estimate_wifi_distance(rssi_measured=-60, angle_offset_deg=0.0)),
            color='orange', linestyle='--', linewidth=1, zorder=3, label='-60 dBm (3-Bars)')
    ax.plot(circle_theta,
            np.full_like(circle_theta, crude_estimate_wifi_distance(rssi_measured=-50, angle_offset_deg=0.0)),
            color='orange', linestyle='-', linewidth=1, zorder=3, label='-50 dBm (4-Bars)')

    # Plot estimated Wi-Fi source points
    for ssid, dist, angle in zip(ssids, distances, angles_rad):
        # Thin dashed gray line to the estimated Wi-Fi source
        # ax.plot([angle, angle], [0, dist], color='gray', linestyle='--', linewidth=1, alpha=0.7)

        # Marker for the Wi-Fi source location
        ax.scatter(angle, dist, color='blue', s=10, zorder=3)

        # SSID text label near the point
        # ax.text(angle, dist + 1.0, f" {ssid[:8]} ({dist:.0f}m)", fontsize=8, color='black', va='center')
        ax.text(angle, dist + 1.0, f" {ssid[:12]}", fontsize=7, color='black', va='center', zorder=5)

    # Plot Antenna Center Marker
    ax.scatter(0, 0, color='red', marker='^', s=100, zorder=1, label='Yagi Uda Antenna (0,0)')

    # Plot annotations
    ax.set_title("Wi-Fi Source Map (crude distance)", va='bottom', fontsize=12,
                 fontweight='bold')
    ax.legend(loc='upper right', bbox_to_anchor=(1.05, 0.01), fontsize=8)
    fig.text(0.02, 0.02, f"Data: {path}", fontsize=9, color='black', ha='left', va='bottom', wrap=True)

    # Save plot in the same directory as the CSV data file
    output_plot_path = path.parent / f"{path.stem}_angle-crude_dist.png"
    plt.tight_layout()
    plt.savefig(output_plot_path, dpi=1200)
    print(f"-> Saved 2D spatial radar map to '{output_plot_path}'")

    plt.show()


def calculate_target_gps_crude(lat_antenna: float, lon_antenna: float, distance_m: float, heading_deg: float) -> tuple:
    """
    Computes target GPS coordinates given a starting point, distance (meters),
    and compass bearing (0-360 degrees from North).

    Uses crude estimated perfectly spherical earth.
    """
    radius_earth_meters = 6371000.0  # Earth radius in meters

    lat1 = math.radians(lat_antenna)
    lon1 = math.radians(lon_antenna)
    bearing = math.radians(heading_deg)

    # Angular distance in radians
    angular_dist = distance_m / radius_earth_meters

    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_dist) +
        math.cos(lat1) * math.sin(angular_dist) * math.cos(bearing)
    )

    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular_dist) * math.cos(lat1),
        math.cos(angular_dist) - math.sin(lat1) * math.sin(lat2)
    )

    return math.degrees(lat2), math.degrees(lon2)


# TODO FIX Internet sharing and INSTALL THE PACKAGE for this
'''
def calculate_target_gps_wgs84(lat_antenna: float, lon_antenna: float, distance_m: float, heading_deg: float) -> tuple:
    """
    Computes precise target GPS coordinates using the WGS84 ellipsoid model
    via GeographicLib. Accurate to sub-millimeter precision.

    The gold standard in Python for exact geodetic calculations is the geographiclib library
    (created by Charles Karney, which replaced Vincenty's formulas because it converges globally without failure).
    """
    # Solve the direct geodesic problem
    result = Geodesic.WGS84.Direct(lat_antenna, lon_antenna, heading_deg, distance_m)

    return result['lat2'], result['lon2']
'''


def calculate_target_gps_vincenty(lat_antenna: float, lon_antenna: float, distance_m: float,
                                  heading_deg: float) -> tuple:
    """
    Computes precise target GPS coordinates using Vincenty's Direct Formula
    on the WGS84 ellipsoid model using only built-in math libraries.

    CAUTION: More accurate is the calculate_target_gps_wgs84 which uses external library.

    """
    if distance_m <= 0.0:
        return lat_antenna, lon_antenna

    # WGS84 Ellipsoid parameters
    a = 6378137.0  # Semi-major axis in meters
    f = 1.0 / 298.257223563  # Flattening
    b = a * (1.0 - f)  # Semi-minor axis

    lat1 = math.radians(lat_antenna)
    lon1 = math.radians(lon_antenna)
    alpha1 = math.radians(heading_deg)

    sin_alpha1 = math.sin(alpha1)
    cos_alpha1 = math.cos(alpha1)

    tan_u1 = (1.0 - f) * math.tan(lat1)

    cos_u1 = 1.0 / math.sqrt(1.0 + tan_u1 ** 2)
    sin_u1 = tan_u1 * cos_u1

    sigma1 = math.atan2(tan_u1, cos_alpha1)
    sin_alpha = cos_u1 * sin_alpha1
    cos2_alpha = 1.0 - sin_alpha ** 2

    u_sq = cos2_alpha * (a ** 2 - b ** 2) / (b ** 2)
    upper_a = 1.0 + (u_sq / 16384.0) * (4096.0 + u_sq * (-768.0 + u_sq * (320.0 - 175.0 * u_sq)))
    upper_b = (u_sq / 1024.0) * (256.0 + u_sq * (-128.0 + u_sq * (74.0 - 47.0 * u_sq)))

    sigma = distance_m / (b * upper_a)
    sigma_p = 2.0 * math.pi

    for _ in range(100):  # Safety limit for convergence
        cos_2_sigma_m = math.cos(2.0 * sigma1 + sigma)
        sin_sigma = math.sin(sigma)
        cos_sigma = math.cos(sigma)

        delta_sigma = upper_b * sin_sigma * (
                cos_2_sigma_m + (upper_b / 4.0) * (
                cos_sigma * (-1.0 + 2.0 * cos_2_sigma_m ** 2) -
                (upper_b / 6.0) * cos_2_sigma_m * (-3.0 + 4.0 * sin_sigma ** 2) * (-3.0 + 4.0 * cos_2_sigma_m ** 2)
        )
        )
        sigma_p = sigma
        sigma = (distance_m / (b * upper_a)) + delta_sigma
        if abs(sigma - sigma_p) <= 1e-12:
            break

    tmp = sin_u1 * sin_sigma - cos_u1 * cos_sigma * cos_alpha1
    lat2 = math.atan2(
        sin_u1 * cos_sigma + cos_u1 * sin_sigma * cos_alpha1,
        (1.0 - f) * math.sqrt(sin_alpha ** 2 + tmp ** 2)
    )

    lambda_val = math.atan2(
        sin_sigma * sin_alpha1,
        cos_u1 * cos_sigma - sin_u1 * sin_sigma * cos_alpha1
    )

    upper_c = (f / 16.0) * cos2_alpha * (4.0 + f * (4.0 - 3.0 * cos2_alpha))

    omega = lambda_val - (1.0 - upper_c) * f * sin_alpha * (
            sigma + upper_c * sin_sigma * (cos_2_sigma_m + upper_c * cos_sigma * (-1.0 + 2.0 * cos_2_sigma_m ** 2))
    )

    lon2 = lon1 + omega

    return math.degrees(lat2), math.degrees(lon2)


def export_summary_to_gpx(
        summary_csv_path: str,
        antenna_lat: float,
        antenna_lon: float,
):
    """
    TODO - TEST THIS METHOD
    Reads summary CSV, calculates GPS coordinates for each Wi-Fi source,
    exports a GPX file for Apple Maps / GPS apps.
    """
    path = Path(summary_csv_path)
    if not path.exists():
        print(f"Error: Summary file not found at {path}")
        return

    sources = []

    with open(path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ssid_raw = row["ssid"]
            try:
                # Fix double-encoded UTF-8 mojibake
                ssid_fixed = ssid_raw.encode('latin1').decode('utf-8')
            except (UnicodeEncodeError, UnicodeDecodeError):
                ssid_fixed = ssid_raw

            # Clean raw strings and strip out invalid control characters/null bytes
            ssid_clean = ssid_fixed.encode('utf-8', 'ignore').decode('utf-8', 'ignore')
            ssid = "".join(ch for ch in ssid_clean if ord(ch) >= 32 or ch == "\n")

            # Fallback for hidden or empty SSIDs
            if not ssid.strip():
                ssid = "[Hidden SSID]"

            bssid = row["bssid"]
            max_rssi = float(row["max_rssi"])
            peak_angle_string = row["peak_angle"]

            distance = crude_estimate_wifi_distance(rssi_measured=max_rssi, angle_offset_deg=0.0)

            if peak_angle_string.strip().lower() == "omni":
                angle_deg = 0.0
            else:
                angle_deg = float(peak_angle_string)

            target_lat, target_lon = ccalculate_target_gps_wgs84(antenna_lat, antenna_lon, distance, angle_deg)

            sources.append({
                "ssid": ssid,
                "bssid": bssid,
                "max_rssi": max_rssi,
                "distance": distance,
                "heading": angle_deg,
                "lat": target_lat,
                "lon": target_lon
            })

    if not sources:
        print("No valid entries found to process.")
        return

    # Generate GPX File for Apple Maps / GIS
    gpx_path = path.with_suffix('.gpx')
    gpx_content = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="Pi Yagi-Uda Scanner" xmlns="http://www.topografix.com/GPX/1/1">',
        f'  <wpt lat="{antenna_lat}" lon="{antenna_lon}">',
        '    <name>Yagi Antenna Station</name>',
        '    <desc>Scan Origin Point</desc>',
        '  </wpt>'
    ]

    for src in sources:
        gpx_content.extend([
            f'  <wpt lat="{src["lat"]}" lon="{src["lon"]}">',
            f'    <name>{src["ssid"]}</name>',
            f'    <desc>Max RSSI: {src["max_rssi"]} dBm | Dist: {src["distance"]:.1f}m | BSSID: {src["bssid"]}</desc>',
            '  </wpt>'
        ])

    gpx_content.append('</gpx>')

    with open(gpx_path, "w", encoding="utf-8") as gpx_file:
        gpx_file.write("\n".join(gpx_content))
    print(f"-> Exported Apple-compatible GPX file to '{gpx_path}'")


def export_summary_to_kml(
        summary_csv_path: str,
        antenna_latitude: float,
        antenna_longitude: float
):
    """
    Reads summary CSV, calculates GPS coordinates, and exports a KML file
    compatible with Google My Maps and Google Earth.

    How to View Your KML File in Google Maps:
    * Go to: Google My Maps.
    * Click Create a new map.
    * Under the untitled layer, click Import.
    * Drag and drop your generated .kml file.
    * Google Maps will map out your antenna location and all detected Wi-Fi sources.
      This map will immediately synchronize to your Google account, allowing you to view and navigate to them directly
      inside the Google Maps app on your phone.

    """


def export_summary_to_kml(
        summary_csv_path: str,
        antenna_latitude: float,
        antenna_longitude: float,
):
    """
    Reads a Wi-Fi CSV data file, estimates source coordinates, and exports
    a KML file compatible with Google My Maps and Google Earth.

    CAUTION: Distance estimation is VERY CRUDE and requires tuning to get parameters to match environment.
    Evironment must be uniform.

    SSIDs are cleaned for display, while XML escaping is handled by
    ElementTree. Original SSID characters such as &, <, and > are preserved
    in the resulting map labels.

    Note:
        Source coordinates are estimates based on RSSI-derived distance
        and the recorded peak bearing, not verified access-point locations.
    """
    path = Path(summary_csv_path)
    if not path.is_file():
        print(f"Error: Summary file not found at {path}")
        return

    # Validate the antenna origin.
    if not (math.isfinite(antenna_latitude) and -90.0 <= antenna_latitude <= 90.0):
        raise ValueError("antenna_latitude must be between -90 and 90.")

    if not (math.isfinite(antenna_longitude) and -180.0 <= antenna_longitude <= 180.0):
        raise ValueError("antenna_longitude must be between -180 and 180.")

    def clean_ssid(value: str | None) -> str:
        """Clean SSID display text; leave XML escaping to ElementTree."""
        if value is None:
            return "[Hidden SSID]"

        ssid = str(value)

        # Remove XML 1.0-invalid control characters.
        # Preserve tab, newline, and carriage return.
        ssid = "".join(
            ch for ch in ssid
            if ch in "\t\n\r"
            or ord(ch) >= 32
        ).strip()

        return ssid if ssid else "[Hidden SSID]"

    def required_field(row: dict, name: str, line_number: int) -> str:
        """Read a required CSV field and report malformed rows clearly."""
        value = row.get(name)
        if value is None or not value.strip():
            raise ValueError(
                f"Missing required field '{name}' on CSV line {line_number}."
            )
        return value.strip()

    sources = []

    with path.open(mode="r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)

        required_columns = {
            "ssid", "bssid", "max_rssi", "peak_angle"
        }
        available_columns = set(reader.fieldnames or [])
        missing_columns = required_columns - available_columns

        if missing_columns:
            raise ValueError(
                "CSV is missing required columns: "
                + ", ".join(sorted(missing_columns))
            )

        for line_number, row in enumerate(reader, start=2):
            try:
                ssid = clean_ssid(row.get("ssid"))
                bssid = required_field(row, "bssid", line_number)
                max_rssi = float(
                    required_field(row, "max_rssi", line_number)
                )
                peak_angle_string = required_field(
                    row, "peak_angle", line_number
                )

                if not math.isfinite(max_rssi):
                    raise ValueError("max_rssi must be finite.")

                # Estimate distance using peak/on-axis RSSI.
                distance = crude_estimate_wifi_distance(
                    rssi_measured=max_rssi,
                    angle_offset_deg=0.0,
                )

                if not math.isfinite(distance) or distance < 0:
                    raise ValueError("Calculated distance is invalid.")

                # 'omni' does not provide a directional bearing.
                # Zero is used as a placeholder, meaning north here.
                if peak_angle_string.lower() == "omni":
                    angle_deg = 0.0
                else:
                    angle_deg = float(peak_angle_string)

                if not math.isfinite(angle_deg):
                    raise ValueError("peak_angle must be finite.")

                angle_deg %= 360.0

                target_latitude, target_longitude = (
                    calculate_target_gps_wgs84(
                        antenna_latitude,
                        antenna_longitude,
                        distance,
                        angle_deg,
                    )
                )

                if not (
                        math.isfinite(target_latitude)
                        and math.isfinite(target_longitude)
                        and -90.0 <= target_latitude <= 90.0
                        and -180.0 <= target_longitude <= 180.0
                ):
                    raise ValueError("Calculated GPS coordinates are invalid.")

                sources.append({
                    "ssid": ssid,
                    "bssid": bssid,
                    "max_rssi": max_rssi,
                    "distance": distance,
                    "heading": angle_deg,
                    "lat": target_latitude,
                    "lon": target_longitude,
                })

            except (ValueError, TypeError, KeyError) as exc:
                print(
                    f"Warning: Skipping CSV line {line_number}: {exc}"
                )

    if not sources:
        print("No valid Wi-Fi source entries found; no KML file created.")
        return

    # Build KML using ElementTree so SSIDs and descriptions are XML-escaped.
    kml_namespace = "http://www.opengis.net/kml/2.2"
    ele_tree.register_namespace("", kml_namespace)

    def kml_tag(name: str) -> str:
        return f"{{{kml_namespace}}}{name}"

    root = ele_tree.Element(kml_tag("kml"))
    document = ele_tree.SubElement(root, kml_tag("Document"))

    ele_tree.SubElement(document, kml_tag("name")).text = "Yagi-Uda Wi-Fi Scan Results"

    def add_placemark(
            name: str,
            description: str,
            latitude: float,
            longitude: float,
    ) -> None:
        placemark = ele_tree.SubElement(document, kml_tag("Placemark"))
        ele_tree.SubElement(placemark, kml_tag("name")).text = name
        ele_tree.SubElement(placemark, kml_tag("description")).text = description

        point = ele_tree.SubElement(placemark, kml_tag("Point"))
        ele_tree.SubElement(point, kml_tag("coordinates")).text = (
            f"{longitude:.8f},{latitude:.8f},0"
        )

    # Add the antenna's known position.
    add_placemark(
        name="Yagi Uda Station",
        description="Scan origin point",
        latitude=antenna_latitude,
        longitude=antenna_longitude,
    )

    # Add estimated Wi-Fi source locations.
    for src in sources:
        description = (
            f"Estimated distance: {src['distance']:.1f} m | "
            f"Max RSSI: {src['max_rssi']:.1f} dBm | "
            f"Bearing: {src['heading']:.1f} degrees | "
            f"BSSID: {src['bssid']}"
        )

        add_placemark(
            name=src["ssid"],
            description=description,
            latitude=src["lat"],
            longitude=src["lon"],
        )

    # Write the KML file as UTF-8 XML.
    kml_path = path.with_suffix(".kml")
    tree = ele_tree.ElementTree(root)
    ele_tree.indent(tree, space="  ")

    tree.write(
        kml_path,
        encoding="utf-8",
        xml_declaration=True,
    )

    print(f"-> Exported Google-compatible KML file to '{kml_path}'")
    print(f"-> Included {len(sources)} Wi-Fi source(s)")
