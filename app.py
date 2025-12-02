import time
import math
import random
import threading
import json
import serial
from flask import Flask, render_template, jsonify, request
import board
import busio
import spidev
import RPi.GPIO as GPIO
from w1thermsensor import W1ThermSensor
import adafruit_tcs34725

# --- HARDWARE SETUP ---
try:
    ser = serial.Serial('/dev/ttyACM0', 115200, timeout=1)
    time.sleep(2)
except:
    ser = None
    print("WARNING: Arduino NOT connected")

# I2C (Color)
i2c = busio.I2C(board.SCL, board.SDA)
try:
    color_sensor = adafruit_tcs34725.TCS34725(i2c)
    color_sensor.led = True
    color_sensor.gain = 16
except:
    color_sensor = None

# SPI (Solar)
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 50000 

# Temp
try:
    temp_sensor = W1ThermSensor()
except:
    temp_sensor = None

# Buzzer
BUZZER_PIN = 18
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

def read_solar():
    adc = spi.xfer2([1, (8 + 0) << 4, 0])
    return ((adc[1] & 3) << 8) + adc[2]

def send_arduino(cmd):
    if ser: ser.write(f"{cmd}\n".encode())

# --- DATA: ELEMENTS 1-18 ---
ELEMENTS = {
    "Hydrogen": "1,0,0,0", "Helium": "2,0,0,0", "Lithium": "2,1,0,0",
    "Beryllium": "2,2,0,0", "Boron": "2,3,0,0", "Carbon": "2,4,0,0",
    "Nitrogen": "2,5,0,0", "Oxygen": "2,6,0,0", "Fluorine": "2,7,0,0",
    "Neon": "2,8,0,0", "Sodium": "2,8,1,0", "Magnesium": "2,8,2,0",
    "Aluminum": "2,8,3,0", "Silicon": "2,8,4,0", "Phosphorus": "2,8,5,0",
    "Sulfur": "2,8,6,0", "Chlorine": "2,8,7,0", "Argon": "2,8,8,0"
}

# --- COLOR CARD LOADING ---
known_colors = []
try:
    with open('color_card.json', 'r') as f:
        known_colors = json.load(f)
except:
    print("WARNING: color_card.json missing.")

def get_closest_color(r, g, b):
    best_name = "None"
    min_dist = 100000
    for c in known_colors:
        cr, cg, cb = c['rgb']
        dist = math.sqrt((r-cr)**2 + (g-cg)**2 + (b-cb)**2)
        if dist < min_dist:
            min_dist = dist
            best_name = c['name']
    if min_dist > 120: return "None"
    return best_name

# --- GLOBAL STATE ---
app = Flask(__name__)
state = {
    "mode": 1,
    "mode2_demo": True,
    "mode2_base": "Hydrogen", # Default base for transitions
    "temp": 0.0,
    "solar": 0,
    "color": "None",
    "photo_current": 0.0,
    "decay_count": 43,
    "decay_halflife": 10,
    "decay_running": False
}

# --- SENSOR THREAD ---
def sensor_logic():
    last_color_time = 0
    while True:
        # Temp
        try:
            t = temp_sensor.get_temperature() if temp_sensor else 25.0
            state["temp"] = round(t, 1)
        except: pass

        # Solar
        try:
            s = read_solar()
            state["solar"] = s
            state["photo_current"] = round((s / 235.0) * 50.0, 1)
        except: pass

        # Color (Mode 2 Real)
        if state["mode"] == 2 and not state["mode2_demo"] and color_sensor:
            if time.time() - last_color_time > 1.5:
                try:
                    r, g, b = color_sensor.color_rgb_bytes
                    det = get_closest_color(r,g,b)
                    if det != "None":
                        process_transition(det)
                        last_color_time = time.time()
                except: pass

        # Mode Logic
        if state["mode"] == 3: # Thermodynamics
            diff = max(0, state["temp"] - 25.0)
            speed = 1.0 + (diff * 0.8)
            send_arduino(f"SPEED:{speed}")
            if diff > 2.0: send_arduino("COLOR:255,0,0") 
            elif diff > 0.5: send_arduino("COLOR:255,255,0")
            else: send_arduino("COLOR:0,255,0") 
            send_arduino("CONF:2,4,0,0") 

        elif state["mode"] == 4: # Photoelectric
            s = state["solar"]
            # Tuned thresholds based on your calibration
            if s < 30: send_arduino("CONF:0,0,0,0")
            elif s < 100: send_arduino("CONF:1,0,0,0")
            elif s < 180: send_arduino("CONF:2,4,0,0")
            else: send_arduino("CONF:2,8,8,4")
            send_arduino("SPEED:2.0")

        elif state["mode"] == 5: # Band Theory
            s = state["solar"]
            if s > 180:
                send_arduino("CONF:2,8,0,4"); send_arduino("COLOR:255,200,0") 
            else:
                send_arduino("CONF:2,8,4,0"); send_arduino("COLOR:0,0,255") 

        time.sleep(0.1)

# --- TRANSITION LOGIC (Updated for Red/Blue/Violet/White) ---
def process_transition(color):
    # Logic based on relative jumps
    # White = De-excitation (Reset to Base)
    if color == "White":
        send_arduino("FLASH:255,255,255")
        time.sleep(0.5)
        # Reset to base element
        base_conf = ELEMENTS.get(state["mode2_base"], "1,0,0,0")
        send_arduino(f"CONF:{base_conf}")
        return

    # For transitions, we map colors to specific target Shells
    # Red = Low Energy (L Shell)
    # Blue = Med Energy (M Shell)
    # Violet = High Energy (N Shell)
    
    if color == "Red": send_arduino("CONF:0,1,0,0")   # Jump to L
    elif color == "Blue": send_arduino("CONF:0,0,1,0") # Jump to M
    elif color == "Violet": send_arduino("CONF:0,0,0,1") # Jump to N

# --- DECAY THREAD ---
def decay_logic():
    while True:
        if state["mode"] == 6 and state["decay_running"]:
            N0 = 43
            t_half = state["decay_halflife"]
            elapsed = 0
            state["decay_count"] = N0
            
            while state["decay_count"] > 0 and state["mode"] == 6 and state["decay_running"]:
                time.sleep(0.5) # Smoother updates (2Hz)
                elapsed += 0.5
                rem = int(N0 * pow(0.5, elapsed / t_half))
                lost = state["decay_count"] - rem
                state["decay_count"] = rem
                
                if lost > 0:
                    events = min(lost, 2)
                    for _ in range(events):
                        if random.randint(0, 10) > 7:
                            send_arduino("DECAY:ALPHA")
                            GPIO.output(BUZZER_PIN, 1); time.sleep(0.05); GPIO.output(BUZZER_PIN, 0)
                        else:
                            send_arduino("DECAY:BETA")
                            GPIO.output(BUZZER_PIN, 1); time.sleep(0.01); GPIO.output(BUZZER_PIN, 0)
                
                # Update Visuals
                k = min(rem, 2); rem -= k
                l = min(rem, 8); rem -= l
                m = min(rem, 12); rem -= m
                n = min(rem, 16)
                send_arduino(f"CONF:{k},{l},{m},{n}")
        else:
            time.sleep(0.5)

# --- WEB ROUTES ---
@app.route('/')
def index(): 
    # Pass elements list to template for Mode 1
    return render_template('index.html', elem_list=list(ELEMENTS.keys()))

@app.route('/set_mode/<int:m>')
def set_mode(m):
    state["mode"] = m
    state["decay_running"] = False # Stop decay on mode switch
    send_arduino("MODE:NORMAL"); send_arduino("SPEED:1.0"); send_arduino("COLOR:0,255,255")
    
    if m == 6: 
        send_arduino("MODE:RADIO_ON")
        send_arduino("CONF:2,8,8,16") # Show full atom ready to decay
    if m == 5: send_arduino("MODE:BAND_ON")
    if m == 2: 
        # Load the selected base element
        base_conf = ELEMENTS.get(state["mode2_base"], "1,0,0,0")
        send_arduino(f"CONF:{base_conf}")
        
    return "OK"

@app.route('/mode2/set_type/<type>')
def set_mode2_type(type):
    state["mode2_demo"] = (type == "demo")
    return "OK"

@app.route('/mode2/set_base/<elem>')
def set_mode2_base(elem):
    state["mode2_base"] = elem
    # Apply immediately
    if state["mode"] == 2:
        base_conf = ELEMENTS.get(elem, "1,0,0,0")
        send_arduino(f"CONF:{base_conf}")
    return "OK"

@app.route('/mode2/sim/<color>')
def mode2_sim(color):
    if state["mode"] == 2:
        process_transition(color)
    return "OK"

@app.route('/mode1/load/<element>')
def load_element(element):
    if element in ELEMENTS: send_arduino(f"CONF:{ELEMENTS[element]}")
    return "OK"

@app.route('/mode6/set_halflife/<int:val>')
def set_halflife(val): state["decay_halflife"] = val; return "OK"

@app.route('/mode6/start')
def start_decay():
    state["decay_running"] = True
    return "OK"

@app.route('/get_data')
def get_data(): return jsonify(state)

# --- START ---
t1 = threading.Thread(target=sensor_logic); t1.daemon = True; t1.start()
t2 = threading.Thread(target=decay_logic); t2.daemon = True; t2.start()

if __name__ == '__main__': app.run(host='0.0.0.0', port=5000)