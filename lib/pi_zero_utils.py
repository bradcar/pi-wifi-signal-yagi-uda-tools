# pi_zero_utils.py

def pico_temperature():
    """ Reads system temperature as substitute for Pico ADC(4) """
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            celsius = float(f.read()) / 1000.0
        return celsius
    except Exception:
        return None
