# Mean Well DRS-series DC-UPS ModBus to MQTT

Mean Well is well known as a producer of better quality power supplies in various form factors. The DRS-series (240/480) is a DIN-rail type all-in-one intelligent power supply, complete with charger and configuration and monitoring via ModbBus RTU RS-485.

To communicate with the unit you need some kind of USB-to-RS485 dongle. This exists in various forms from cheap AliExpress $5 ones to more official-band names for $99. You will need to connect GND, D+ and D-.

This script is very basic but cover my needs, you could see it as example code for your own projects.

### Background

I run the most important parts of my home network gear on 24VDC with a SLA-battery backup. Historically this has been float-charged with regular 24VDC PSU tuned up to about 27.2V. This worked well but had no critical-level cut-off or any kind of charge management. It relied only on the DC-voltage measurement in the network equipment that isn't that great (varies 100-600mV between devices).

Lately I've also added my NAS (with the help of a 12V DC/DC) and upgraded the batteries, but I needed some better monitoring and too-low-battery cut-off functions.

### The script

The script is designed to run as a service, for example with systemd (I have included a sample configuration). It continuously (POLL_INTERVAL) polls the DRS and fetches the latest values. If there is too much of a difference (REPORT_HYSTERESIS) to the last value, it gets published via MQTT.

If two separate thresholds is reached (VOLTAGE_VOUT_LOW, VOLTAGE_VOUT_CRITICAL), then different actions can be performed (for example a system graceful shutdown)

There is also a regular static interval (REPORT_INTERVAL) where all values are published via MQTT. I send my values to an InfluxDB and can view them with Grafana.

### Why not just a regular AC-line UPS?

Well, what's the fun in that? And, nothing really needs AC anyways. All electronics run on low voltage DC.

Smaller commercial UPS:es are known to run the batteries harder (as in a higher float charge) to squeeze the most instantaneous power out of them. Vendor-specific batteries is somtimes required and costs quite a bit.

The Mean Well DRS-series support a wide range of type of batteries and can be sourced anywhere.

### References

  - Mean Well DRS-series product page
    <https://www.meanwell.com/newsInfo.aspx?c=1&i=1069>
  - Mean Well DRS-series more extensive manual
    <https://www.meanwell.com/Upload/PDF/DRS-240,480.pdf>

