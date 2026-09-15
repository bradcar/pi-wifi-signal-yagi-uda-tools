from lib.lis3mdl_utils import get_compass_8pt_string
from pi_yagi_uda import TARGET_SSID, RSSI_DOWNLOAD_THRESHOLD, RSSI_CONNECT_THRESHOLD


def display_metrics_oled(draw, font, rssi, ssid: str, rx_rate, heading: float, download_count, connected: bool = True):
    left_indent = 0
    direction_str = get_compass_8pt_string(heading) if heading is not None else ""
    heading_str = f"{heading:>3.0f}°" if heading is not None else "???°"

    # if rssi is not set, display out of range messages
    if rssi is None:
        line1 = f"target: {TARGET_SSID}"
        line2 = "out of range scan"
        line3 = f"{heading_str} {direction_str:<2}"

    # Update metrics for Connect Mode or Scan Mode
    else:
        if connected:
            line1 = f"SSID = {ssid}"
            # If connected, show Mb/s, else print "linked"
            rate_str = f"{rx_rate:.0f} mb/s" if rx_rate is not None else "linked"
            line2 = f"{rssi} dbm  {rate_str}"

            # Notify if download is possible based on -70 dBm rule
            if rssi >= RSSI_DOWNLOAD_THRESHOLD:
                line3 = f"{heading_str} {direction_str:<2} ..dload {download_count}?"
            else:
                line3 = f"{heading_str} {direction_str:<2}"
        else:
            line1 = f"ssid   {ssid}"
            line2 = f"{rssi} dbm ...Scan"

            # test if connection available
            if rssi >= RSSI_CONNECT_THRESHOLD:
                line3 = f"{heading_str} {direction_str:<2} .connect?"
            else:
                line3 = f"{heading_str} {direction_str:<2}"

    # Write text to OLED
    draw.text((left_indent, 0), line1, font=font, fill=1)
    draw.text((left_indent, 10), line2, font=font, fill=1)
    draw.text((left_indent, 20), line3, font=font, fill=1)
