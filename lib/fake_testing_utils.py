import random


def fake_heading_sweep(sweep_degree: int) -> int:
    sweep_degree += 1  # sweep_degree += random.randint(0, 10)
    sweep_degree = int(sweep_degree) % 360
    if sweep_degree > 75 and sweep_degree < 90:
        sweep_degree = 270
    heading = sweep_degree  # fake heading that sweeps
    return heading, sweep_degree


def fake_rssi_history_fill(rssi, rssi_heading_history: list[float]) -> int:
    random_degree = random.randint(0, 359)
    fake_rssi = rssi
    # signals out of 20° (10-30°), reduce signal by -15 dBm
    if not (random_degree > 19 and random_degree < 45):
        fake_rssi -= 20
        if fake_rssi < -99:
            fake_rssi = -99
    if (random_degree < 300 and random_degree > 100):
        fake_rssi -= 15
        if fake_rssi < -99:
            fake_rssi = -99
    if (random_degree > 175 and random_degree < 225):
        fake_rssi = -99

    rssi_heading_history[random_degree] = fake_rssi
    return rssi_heading_history
