# Yagi Uda Analysis with nanoVNA and Field Fest

## Vector network analyzer results

A vector network analyzer (VNA) is used to measuring how much of an applied signal is reflected back from the antenna. 
Typical nano-VNAs have two ports, but only one port is needed for basic antenna characterization. 
The nano-VNA can sweep through a range of frequencies, measuring the amplitude and phase of the signal reflected back to the same port (s11). 
The amplitude of the returned signal tells us the amount of power reflected back as a result of any mismatch of antenna and feed line. 
The return loss is measured in the logarithmic scale of decibels (dB), with a more negative values indicating less reflected power and better matching. 
Ideally, it should show below -20 dB (1% reflected and 99% accepted by the antenna). 
A return loss of -10 dB (10% reflected, 90% accepted) is considered acceptable for most applications.

## Adding external Yagi Uda Antenna
In order to add an external antenna (like a the Techtoo Yagi-Uda antenna) to a Raspberry Pi Zero 2W, one has to add a u.FL connector.
In addition, on the on the Pi Zero 2 W one must cut traces to the on-board PCB antenna.
We tested 6 different u.FL to RP-SMA pigtails to connect the antenna directly to the nano-VNA and swept all of the 11 Wi-Fi channels. 
The best pigtail-antenna combination shows that Chan1 has -23.96 dB, Chan6 has -18.38 dB, and Chan11 has an amazing -30.25 dB! Channel 11 showed near-perfect lab-quality -30.25 dB and a VSWR 1:1.063 which meant that 99.9% of the power was accepted and only 0.10% was reflected.
The Techtoo Yagi-Uda antenna is a directional antenna with specified gain of 18 dBi and a Half-Power Beam Width (HPBW) of 30° horizontally and 28° vertically.

Unlike omnidirectional antennas that radiate uniformly, a Yagi-Uda antenna focuses gain along its boresight axis, trading off-axis coverage for extended distance in the target direction. 
Lacking an anechoic chamber to precisely measure gain and radiation pattern, our field testing was consistent the specified gain and beamwidth.

## Field measurements – Will a Yagi-Uda really work?
Our use case is being able to locate a remote  Raspberry Pi Pico 2 W and remotely download telemetry data. 
We tested our devices on a field with three regulation soccer pitches we were able to get -78 dBm signal with our Yagi-Uda Antenna and Pi Zero 2 W combination and get stable telemetry downloads at an amazing 147.5 meters (484’). 
We estimate that at 174 meters (572’) we could still measure -80 dBm and successfully download data. Given the likely sensor distance is 76 meters (250’) we consider this to be well without our design needs.
Answer: Yes!


![delta-park-antenna-measurements-1-Nov-2026.png](../assets/images/delta-park-antenna-measurements-1-Nov-2026.png)

## References:

Adding u.FL connector to Raspberry Pi Zero 2 W:
https://www.youtube.com/watch?v=6R8xhSzpJTU&t=166s

TechToo 2.4 GHz  ($29.99)
* https://www.amazon.com/dp/B00OCJYPCY
* 18dBi Gain
* Half-power Beam width: 30° horizontal, and 28° vertical
* 58cm (23")
* 18 element
