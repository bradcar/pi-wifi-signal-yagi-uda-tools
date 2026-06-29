# mock_rssi_heading_history.py
"""
mock rssi_heading_history creation
"""
import os
import pandas as pd
import numpy as np

def read_theta_rssi_from_csv(csv_file):
    df = pd.read_csv(csv_file)
    theta = np.deg2rad(df['degree'])
    rssi = df['rssi']
    return df, rssi, theta


def mock_rssi_heading_history(rssi: float, csv_file="yagi.csv"):
    """
    Reads a historical CSV file containing 'degree' and 'rssi' columns
    and reconstructs a 360-element array compatible with the radar display pipeline.
    """

    rssi_history = [-99.0] * 360

    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        absolute_path = os.path.join(script_dir, csv_file)
        df = pd.read_csv(absolute_path)
    except FileNotFoundError:
        print(f"Warning: Mock target '{csv_file}' not found.")
        return rssi_history

    if rssi:
        # Find the peak RSSI value present in the CSV file
        csv_peak = df['rssi'].max()

        # Proportionally scale the telemetry results down from the new peak target
        for _, row in df.iterrows():
            degree = int(row['degree']) % 360
            csv_rssi = float(row['rssi'])

            attenuation = csv_peak - csv_rssi
            scaled_rssi = rssi - attenuation
            if scaled_rssi < -99.0:
                scaled_rssi = -99.0

            rssi_history[degree] = scaled_rssi
    else:
        for _, row in df.iterrows():
            degree = int(row['degree']) % 360
            csv_rssi = float(row['rssi'])

            if csv_rssi < -99.0:
                csv_rssi = -99.0

            rssi_history[degree] = csv_rssi

    return rssi_history