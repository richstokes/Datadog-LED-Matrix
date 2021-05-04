Display metrics from Datadog in realtime on an [LED RGB Matrix](https://learn.adafruit.com/adafruit-matrixportal-m4).  

It lets you keep a pulse on your infrastructure by displaying your most important metrics on an LED wall board. It will light up anomalies in red. It looks great in any home or office. Voted must-have accessory Spring 2021 by Country Living. 

![demo video](https://raw.githubusercontent.com/richstokes/Datadog-LED-Matrix/main/demo.gif)

&nbsp;
> It's easy to make! You just have to screw a couple of things together. You can then display any datadog metric you like.

&nbsp;


# Shopping List

- 1x https://www.adafruit.com/product/4745  
- 1x https://www.adafruit.com/product/2278  
- Wall mounts (optional): https://www.prusaprinters.org/prints/44541-adafruit-rgb-matrix-portal-wall-mount/files - Make sure the pitch matches the pitch of your LED Matrix (4mm is the one I linked to above). Download .stl file and 3D print @ shapeways.com

&nbsp;

# Setup

1. Prep the MatrixPortal by following the [instructions here](https://learn.adafruit.com/adafruit-matrixportal-m4/prep-the-matrixportal)
2. Install [CircuitPython](https://learn.adafruit.com/adafruit-matrixportal-m4/install-circuitpython) on the device
3. Copy [these base libraries](https://learn.adafruit.com/adafruit-matrixportal-m4/circuitpython-setup) to the device (`/lib`), plus `adafruit_ntp.mpy`
4. Copy the `/fonts` directory to the device
5. Copy the `logo.bmp` file to the device 
6. Create a `secrets.py` file based on `secrets.py.example` - you will need a [datadog API and App key](https://app.datadoghq.com/account/settings#api), as well as your WiFi details
7. Create a `metrics.json` file based on `metrics.json.example` listing the metrics you would like to display on the LED matrix
8. Copy above files to the device (you can use the `helper.sh` script to do this automatically)

The device will reboot whenever you change any files, so after copying these it should start up!

&nbsp;

## metrics.json

This file lists out the metrics you would like to display. Just add any query you can make in datadog (their [metrics explorer](https://app.datadoghq.com/metric/explorer) is a good place to play around).  
Setting the `metric_name` controls the "title" text above the metric. You can also set prefix/trailing strings and the amount of decimal places to round to. 

Setting `high_threshold` is the value at which the metric will be displayed in <span style="color:red">red</span> if the value is greater than.  

`totalled_metrics` aggregates all values over the specified time period. I had to use this in lieu of `sum` -- TBC why. You can just comment these out if not useful to your setup. 

&nbsp;

## logo.bmp

This is the background/logo image. You may want to replace it with your company logo, etc.

Bitmaps should be 64x32, 24-bit. This command seems to work if you have a .bmp that wont load (it's kinda fussy about the format):  
`convert logo.bmp -compress none -type palette logo.bmp`

&nbsp;

# Debugging

The M4 has a built in serial output you can read with something like `screen /dev/tty.usbmodem2201 115200` -- [see here for more info](https://learn.adafruit.com/welcome-to-circuitpython/advanced-serial-console-on-mac-and-linux).



