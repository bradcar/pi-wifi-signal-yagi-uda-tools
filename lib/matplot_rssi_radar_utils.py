# mac_rssi_heading_polar_plot.py
"""
Polar plot of RSSI strength at 360° headings. Radar-style plot for analysis
of measured RSSI from directional antenna Yagi-Uda data.
Peak RSSI is detected and its value and heading are printed in the title.
Magnetic North is 0° degrees, East is 90° degrees.

Features:
- Runs on MacOS or Pi Zero 2 W
- lcd_png_generate flag - if True creates small 240px x 240px png for direct display on small color LCD
- Dark Mode created for testing and possible use for lcd png's.
- Detects peak RSSI, or mid of plateau of peaks
- Autoscales so the peak is 85% of the polar plot limit.
- Indicates peak with red line from plot boundary to peak, outside of boundary peaks RSSI printed.

Dependencies:
    matplotlib, numpy

Expected CSV Input Format:
    The input file must include headers matching 'degree' and 'rssi'.
    Example:
        degree,rssi
        0,-45
        10,-48.5
        ...

Note:
    Magnetic North 0° is at Top/Up. Clockwise rotation with East 90° at right.

Usage:
    python mac_rssi_heading_polar_plot.py <path_to_rssi_data.csv>

"""
from typing import Any
import io  # ADD THIS FOR IN-MEMORY BUFFERS

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image  # ADD THIS TO RETURN A PIL IMAGE

from lib.polar_math_utils import calculate_peak_bounds

# dBm bounds for clamping values and gridlines
RSSI_MAX_PLOT_CONSTANT = -20
RSSI_MIN_PLOT_CONSTANT = -99
Y_TICK_MAX = -10
Y_TICK_MIN = -90

LCD_PIXELS = 240
LCD_DPI = 100
LCD_INCHES = LCD_PIXELS / LCD_DPI


def rssi_peak(valid_data) -> tuple[float, float, Any, Any, Any]:
    """valid_data is a a 2D numpy array. Column 0: degree, Column 1: rssi"""
    max_rssi = valid_data[:, 1].max()

    # Filter rows where rssi matches the maximum value
    peak_cluster = valid_data[valid_data[:, 1] == max_rssi]
    peak_rssi = float(max_rssi)

    # Extract matching degrees straight from column 0
    degrees = peak_cluster[:, 0]

    arc_radians, arc_radii, peak_degree = peaks_arc_calc(degrees, peak_rssi)
    return arc_radians, arc_radii, peak_cluster, peak_degree, peak_rssi


def peaks_arc_calc(degrees, peak_rssi: float):
    """
    Determine the arc boundary of all peak cluster points with vector mean.
    Look for the largest angular gap between adjacent peaks.
    """
    # Call the shared math helper
    mean_peak_degree, first_deg, last_deg = calculate_peak_bounds(degrees)

    # Generate plotting coordinates along the true shortest arc
    if last_deg < first_deg:
        arc_degrees = np.linspace(first_deg, last_deg + 360, num=100) % 360
    else:
        arc_degrees = np.linspace(first_deg, last_deg, num=100)

    arc_radians = np.deg2rad(arc_degrees)
    arc_radii = np.full_like(arc_radians, peak_rssi)

    return arc_radians, arc_radii, mean_peak_degree



def plot_rssi_polar(degrees, rssi, theta, heading, subtitle, lcd_png_generate, file_name="plot.png"):
    # Create a 2D array matrix: Column 0 = degree, Column 1 = rssi
    history_array = np.column_stack((degrees, rssi))

    # Fast mask filtering using native NumPy expressions
    valid_data = history_array[history_array[:, 1] > -98]

    if len(valid_data) == 0:
        peak_rssi = -99.0
        peak_degree = 0
        peak_cluster = np.array([])
    else:
        arc_radians, arc_radii, peak_cluster, peak_degree, peak_rssi = rssi_peak(valid_data)

    print(f"Peak detected: {peak_rssi:.0f} dBm @ {peak_degree:.0f}° degrees")

    dark_mode = False
    if not lcd_png_generate:
        fig, ax = plt.subplots(subplot_kw={'projection': 'polar'})
    else:
        dark_mode = True
        fig, ax = plt.subplots(figsize=(LCD_INCHES, LCD_INCHES), dpi=LCD_DPI, subplot_kw={'projection': 'polar'})

    if dark_mode:
        bg_color = '#000000'
        panel_color = '#121212'
        text_color = '#FFFFFF'
        y_label_color = 'cyan'
        grid_color = '#555555'
    else:
        bg_color = '#FFFFFF'
        panel_color = '#FFFFFF'
        text_color = '#000000'
        y_label_color = 'blue'
        grid_color = '#CCCCCC'

    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(panel_color)

    ax.set_theta_direction(-1)
    heading = heading % 360
    ax.set_theta_offset(np.deg2rad(heading))

    thetaticks = np.arange(0, 360, 15)
    ax.set_thetagrids(thetaticks, labels=[f"{x}°" for x in thetaticks])

    if not lcd_png_generate:
        font_adjust = 0
    else:
        font_adjust = 2
        ax.tick_params(axis='x', colors=text_color, pad=2)

    for tick, label in zip(thetaticks, ax.get_xticklabels()):
        if tick % 45 == 0:
            label.set_weight('bold')
            label.set_fontsize(11 - font_adjust)
        else:
            label.set_fontsize(9 - font_adjust)

    yticks = np.arange(Y_TICK_MIN, Y_TICK_MAX, 10)
    ax.set_yticks(yticks)
    ax.set_yticklabels([f"{y}" for y in yticks])
    if not lcd_png_generate:
        ax.tick_params(axis='y', labelsize=10, labelcolor='blue')
    else:
        ax.tick_params(axis='y', labelsize=9, labelcolor=y_label_color)

    rssi_max_plot = RSSI_MAX_PLOT_CONSTANT
    rssi_min_plot = RSSI_MIN_PLOT_CONSTANT

    if peak_rssi != -99:
        max_radius_percent = 0.90
        rssi_max_plot = rssi_min_plot + (peak_rssi - rssi_min_plot) * (1.0/max_radius_percent)
        print(f"Autoscaled Plot Range ({int(max_radius_percent*100)}%): {rssi_max_plot:.0f} to {rssi_min_plot:.0f} dBm")

    ax.set_ylim(rssi_min_plot, rssi_max_plot)

    if not lcd_png_generate:
        ax.plot(theta, rssi, color='green', linewidth=2.0)
    else:
        ax.plot(theta, rssi, color='green', linewidth=0.7)
    ax.fill(theta, rssi, color='green', alpha=0.7)

    red_peak_text = f"(Peak: {peak_rssi:.0f}dBm @ {peak_degree:.0f}°)"

    if not lcd_png_generate:
        fig.text(0.32, 0.95, "RSSI Strength", ha='center', fontsize=12, fontweight='bold')
        fig.text(0.45, 0.95, red_peak_text, ha='left', fontsize=12, fontweight='bold', color='red')
        fig.text(0.05, 0.03, f"{subtitle}", ha='left', fontsize=8)
    else:
        fig.text(0.10, 0.94, f"(Peak {peak_rssi:.0f} dBm @ {peak_degree:.0f}°)", ha='left', fontsize=11,
                 fontweight='bold', color='red')
        fig.text(0.01, 0.02, f"{subtitle}", ha='left', color=text_color, fontsize=9, fontweight='bold')
        fig.text(0.8, 0.02, f"RSSI", ha='left', color=text_color, fontsize=13, fontweight='bold')

    peak_rad = np.deg2rad(peak_degree)
    if peak_rssi < rssi_max_plot:
        halfway_peak = (peak_rssi - rssi_max_plot) / 2
        ax.plot([peak_rad, peak_rad], [peak_rssi, peak_rssi - halfway_peak], color='red', linestyle='--', linewidth=2)
        ax.plot([peak_rad, peak_rad], [peak_rssi - halfway_peak, rssi_max_plot], color='red', linestyle='-',
                linewidth=4)
    else:
        ax.plot([peak_rad, peak_rad], [rssi_min_plot, peak_rssi], color='red', linestyle='--', linewidth=1)

    if len(peak_cluster) > 1:
        ax.plot(arc_radians, arc_radii, color='red', linewidth=1, linestyle='-')

    if not lcd_png_generate:
        peak_string = f"{peak_rssi:.0f} dBm"
        peak_offset = 20
    else:
        peak_string = f"{peak_rssi:.0f}"
        peak_offset = 5

    ax.annotate(peak_string,
                xy=(peak_rad, rssi_max_plot),
                xytext=(np.sin(peak_rad) * peak_offset, np.cos(peak_rad) * peak_offset),
                textcoords="offset points",
                color='red',
                ha='center',
                va='center',
                fontweight='bold',
                fontsize=9,
                bbox=dict(boxstyle="round,pad=0.2", facecolor='white', edgecolor='red', alpha=0.8))

    plt.grid(True, linestyle='--', color=grid_color, alpha=0.6)

    if not lcd_png_generate:
        plt.savefig(file_name, format='png', dpi=300, bbox_inches='tight')
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
    else:
        ax.set_position([0.14, 0.1, 0.72, 0.75])
        plt.savefig(file_name, format='png', dpi=LCD_DPI)

        # Put image in memory
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=LCD_DPI)

    # reset image buffer, return PIL Image
    buf.seek(0)
    pil_img_out = Image.open(buf).copy()
    buf.close()
    plt.close(fig)

    return pil_img_out
