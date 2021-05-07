import board
import time
import displayio
import busio
import gc
import terminalio
from adafruit_bitmap_font import bitmap_font
from adafruit_display_text import label
import adafruit_requests as requests
import adafruit_imageload
from digitalio import DigitalInOut
import adafruit_esp32spi.adafruit_esp32spi_socket as socket
from adafruit_esp32spi import adafruit_esp32spi
import framebufferio
import rgbmatrix
import supervisor
from adafruit_ntp import NTP
import json

print('Starting up..')
DELAY_BETWEEN=3 # Time delay between datadog queries / how long to leave each metric displayed for. If set too low, you will hit the DD rate limit. There is logic to check and back off if that happens, but I've not tested it much
RATE_LIMIT_BACKOFF=300 # Backoff timer if we start approaching the DD API Rate limit
INTERVAL=600 # Time period to get metrics in

# Setup board / network stack
esp32_cs = DigitalInOut(board.ESP_CS)
esp32_ready = DigitalInOut(board.ESP_BUSY)
esp32_reset = DigitalInOut(board.ESP_RESET)
spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)
# esp._debug = True

displayio.release_displays()
matrix = rgbmatrix.RGBMatrix(
    width=64, bit_depth=4,
    rgb_pins=[
        board.MTX_R1,
        board.MTX_G1,
        board.MTX_B1,
        board.MTX_R2,
        board.MTX_G2,
        board.MTX_B2
    ],
    addr_pins=[
        board.MTX_ADDRA,
        board.MTX_ADDRB,
        board.MTX_ADDRC,
        board.MTX_ADDRD
    ],
    clock_pin=board.MTX_CLK,
    latch_pin=board.MTX_LAT,
    output_enable_pin=board.MTX_OE
)

# Get datadog keys from secrets.py file
try:
    from secrets import secrets
    DD_CLIENT_API_KEY=secrets['dd_api']
    DD_CLIENT_APP_KEY=secrets['dd_app']
except ImportError:
    print("WiFi/Datadog API secrets are kept in secrets.py, please add them there!")
    raise

# Display settings
SCALE = 1
display = framebufferio.FramebufferDisplay(matrix, auto_refresh=False)
display.auto_refresh = True
# Define some preset colours
white = 0xFFFFFF
blue = 0x0000FF
red = 0xFF0000

# Title text
group1 = displayio.Group(max_size=3, scale=SCALE)
initial_text = "______________________"
title_font = bitmap_font.load_font("/fonts/pixel-10.bdf")
title_text = label.Label(title_font, text=initial_text, color=white) # Create the text label
title_text.x = 24
title_text.y = 5
group1.append(title_text)

# Data display text
data_display_group = displayio.Group(max_size=3, scale=SCALE)
data_display_text = "               "
data_display_font = terminalio.FONT
data_display_label = label.Label(data_display_font, text=data_display_text, color=white)
data_display_label.x = 26
data_display_label.y = 16
group1.append(data_display_label)

# Load logo/background image
img_bitmap, palette = adafruit_imageload.load("/logo.bmp",
                                         bitmap=displayio.Bitmap,
                                         palette=displayio.Palette)
# Create a sprite (tilegrid)
img_logo_sprite = displayio.TileGrid(img_bitmap, pixel_shader=palette,
                            width = 1,
                            height = 1,
                            tile_width = 64,
                            tile_height = 32)
logoGroup = displayio.Group(scale=1)
logoGroup.append(img_logo_sprite)

# Draw big square for intro reveal animation
group2 = displayio.Group()
square2 = displayio.Bitmap(64, 32, 1)
palette = displayio.Palette(1)
palette[0] = 0x002FA7
tile_grid_square2 = displayio.TileGrid(square2, pixel_shader=palette) # Create a TileGrid using the Bitmap and Palette
tile_grid_square2.x = 0
tile_grid_square2.y = 0
group2.append(tile_grid_square2)

# Draw all layers
combinedGroup = displayio.Group()
combinedGroup.append(logoGroup) # Draw logo first so its the background
combinedGroup.append(group1)
combinedGroup.append(group2)
display.show(combinedGroup)

# Reveal animation
while tile_grid_square2.y < 32:
    tile_grid_square2.y += 1
    time.sleep(0.065)
group2.pop()


def get_time():
    try:
        ntp = NTP(esp)
        # Wait for a valid time to be received
        while not ntp.valid_time:
            print("Setting time..", end='')
            ntp.set_time()
            time.sleep(1)
        current_time = time.time()
        print("Got time:", current_time)
        if current_time < 1619250585:
            print('Time sanity check failed, rebooting')
            data_display_label.text = "TimeERR"
            time.sleep(10)
            supervisor.reload()
        else:
            return(current_time)
    except Exception as e:
        print("Unable to get time, restarting!!!", e)
        #network_check()
        supervisor.reload() # Restart the program if unable to get time, hack to work around intermittent "repeated socket failures" errors 
    
def network_connect():
    '''
    Set up the wifi
    '''
    print("Connecting to WiFi..")
    while not esp.is_connected:
        title_text.color = blue
        title_text.text = "Connecting"
        data_display_label.text = "ToWiFi"
        try:
            esp.connect_AP(secrets["ssid"], secrets["password"])
        except RuntimeError as e:
            title_text.text = "WiFi Error"
            print("Could not connect to WiFi, retrying: ", e)
            continue
    title_text.text = "Starting"
    data_display_label.text = "WiFiOK"
    # title_text.color = white
    try:
        print("Connected to", str(esp.ssid, "utf-8"), "\nRSSI:", esp.rssi)
        print("My local IP address is", esp.pretty_ip(esp.ip_address))
        print(
            "IP lookup google.com: %s" % esp.pretty_ip(esp.get_host_by_name("google.com")) # Just to check network is working
        )
    except RuntimeError as e:
        print("Network error: ", e)
        raise

def network_check():
    '''
    Check if wifi has disconnected and reconnect if needed
    '''
    if esp.is_connected:
        # print('Still connected..')
        pass
    else:
        print('Wifi disconnected, attempting to reconnect..')
        network_connect()

def datadog_get_metrics(current_time, query, metric_name, trailing_string, prefix_string, rounding_places, high_threshold):
    '''
    Fetches last data point for a given datadog metric query
    '''
    FROM_TIME = int(current_time) - INTERVAL
    JSON_URL="https://api.datadoghq.com/api/v1/query?api_key=" + DD_CLIENT_API_KEY + "&application_key=" + DD_CLIENT_APP_KEY + "&from=" + str(FROM_TIME) + "&to=" + str(current_time) + "&query=" + query

    print('Using time range in DD request:', FROM_TIME, "to", current_time)
    print('Running query:', query)
    try:
        r = requests.get(JSON_URL)
        print("-" * 60)
        json_resp = r.json()
        # print(json_resp) # Raw JSON
        last_data_point = json_resp["series"][0]["pointlist"][-1] # Get latest value in time series
        print('Last data point:', last_data_point[1])

        # Format results
        # Hack for displaying percentages better
        if "percent_usage" in query:
            print('Formating as percentage')
            formatted_last_data_point = "{:.0%}".format(float(last_data_point[1]))
            print(last_data_point[1])
        else:
            if rounding_places < 1: # Adjust displayed value based on places to round to
                formatted_last_data_point = int(last_data_point[1])
            else:
                formatted_last_data_point = round(last_data_point[1],rounding_places)
        
        # Update display with result
        title_text.text = metric_name
        # Set colour to red if value over threshold
        if last_data_point[1] > high_threshold:
            print('Value over threshold!')
            data_display_label.color = red
        else:
            data_display_label.color = white

        data_display_label.text = prefix_string + str(formatted_last_data_point) + trailing_string

        # Process Response headers
        # Check we're not smashing the API rate limit
        if int(r.headers["x-ratelimit-remaining"]) < 500:
            print('Warning! Approaching rate limit. Backing off.')
            print('Rate limit remaining:', r.headers["x-ratelimit-remaining"], 'out of', r.headers["x-ratelimit-limit"], 'Period is', r.headers["x-ratelimit-period"])
            time.sleep(RATE_LIMIT_BACKOFF)

        print("-" * 60)
        r.close()
    except Exception as e:
        print(e)
        if "socket failures" in str(e): # TODO: Find out why these intermittent socket failures happen and handle them better. Not sure if its due to flakey wifi, a bug in the Adafruit libs or something else.
            print('Restarting due to socket failures..')
            supervisor.reload()
        else:
            return # Just return if we dont get a good value from DD
    time.sleep(DELAY_BETWEEN)
    return

def datadog_get_metrics_totaled(current_time, query, metric_name, trailing_string, time_range, high_threshold):
    '''
    Fetches a given datadog metric query, and totals all the datapoints in the given time range
    '''
    FROM_TIME = int(current_time) - time_range
    JSON_URL="https://api.datadoghq.com/api/v1/query?api_key=" + DD_CLIENT_API_KEY + "&application_key=" + DD_CLIENT_APP_KEY + "&from=" + str(FROM_TIME) + "&to=" + str(current_time) + "&query=" + query

    print('Using time range in DD request:', FROM_TIME, "to", current_time)
    print('Running query:', query)
    try:
        r = requests.get(JSON_URL)
        print("-" * 60)
        json_resp = r.json()
        # print(json_resp) # Raw JSON
        totalled_data_points = 0
        for i in json_resp["series"][0]["pointlist"]:
            # print(i[1])
            totalled_data_points = totalled_data_points + i[1]
        # print(json_resp["series"][0]["pointlist"])
        # last_data_point = json_resp["series"][0]["pointlist"][-1] # Get latest value in time series
        # print(last_data_point[1]) 
        print(totalled_data_points)

        # Update display with result
        title_text.text = metric_name
        # Set colour to red if value over threshold
        if totalled_data_points > high_threshold:
            print('Value over threshold!')
            data_display_label.color = red
        else:
            data_display_label.color = white

        data_display_label.text = "" + str(totalled_data_points).split(".")[0] + trailing_string

        # Check we're not smashing the API rate limit
        if int(r.headers["x-ratelimit-remaining"]) < 500:
            print('Warning! Approaching rate limit. Backing off.')
            print('Rate limit remaining:', r.headers["x-ratelimit-remaining"], 'out of', r.headers["x-ratelimit-limit"], 'Period is', r.headers["x-ratelimit-period"])
            time.sleep(RATE_LIMIT_BACKOFF)

        print("-" * 60)
        r.close()
    except Exception as e:
        print(e)
        return # Just return if we dont get a good value from DD

    time.sleep(DELAY_BETWEEN)
    return

network_connect() # Initialize network / connect to WiFi
data_display_label.text = "ReqSock"
requests.set_socket(socket, esp) # only do this once / keep outside of main loop
data_display_label.text = "GetTime"

t = None
while not t:
    t = get_time() # Set the initial time

# Load metrics to display from metrics.json file
with open('metrics.json') as f:
    try:
        jsondata = json.load(f)
        for i in jsondata['metrics']:
            print("Loaded metric: " + i['metric_name'])
        for i in jsondata['totalled_metrics']:
            print("Loaded totalled metric: " + i['metric_name'])   
    except Exception as e:
        print('Unable to load metrics from metrics.json -- Please add/fix this file and retry. (%s)' % str(e))
        time.sleep(1800)
        supervisor.reload()


while True: # Main loop
    for i in jsondata['metrics']:
        datadog_get_metrics(current_time=time.time(), query=i['query'], metric_name=i['metric_name'], trailing_string=i['trailing_string'], prefix_string=i['prefix_string'], rounding_places=i['rounding_places'], high_threshold=i['high_threshold'])

    for i in jsondata['totalled_metrics']:
        datadog_get_metrics_totaled(current_time=time.time(), query=i['query'], metric_name=i['metric_name'], trailing_string=i['trailing_string'], time_range=i['time_range'], high_threshold=i['high_threshold'])

    print(gc.mem_free(), "bytes free")
    network_check() # Checks wifi is still connected OK / reconnects if needed
