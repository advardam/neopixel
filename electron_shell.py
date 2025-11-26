#!/usr/bin/env python3
"""
electron_shells_by_shell.py

Atomic shell model where each hardware ring = one atomic shell:
  ring0 -> K (1st), ring1 -> L (2nd), ring2 -> M (3rd), ring3 -> N (4th)

Two filling modes:
  - chemical: [2,8,8,18]  (typical chemistry for small atoms)
  - bohr:     [2,8,18,32]  (Bohr capacities)

Requires:
 - Arduino controller running (ARDUINO_NEOCTRL)
 - led_mapping.json in same folder (optional; fallback to numeric indices)
 - pyserial installed: sudo apt install python3-serial

Run:
  python3 electron_shells_by_shell.py
"""
import json, glob, serial, time, sys, os, math

# ---------- CONFIG ----------
DEFAULT_MAPPING = "led_mapping.json"
AUTO_PORT_GLOBS = ['/dev/ttyACM*','/dev/ttyUSB*']
SERIAL_BAUD = 115200
SAFE_BRIGHTNESS = 120

# Hardware ring sizes (must match Arduino config)
RING_LEDS = [7, 8, 12, 16]   # ring0 includes nucleus at index 0 (so outer_count = 6)

# Shell mapping: ring0 -> K, ring1 -> L, ring2 -> M, ring3 -> N
SHELL_NAMES = ['K', 'L', 'M', 'N']

# Two filling strategies
FILL_PRESETS = {
    'chemical': [2, 8, 8, 18],   # chemical-style (makes Carbon => 2,4)
    'bohr':     [2, 8, 18, 32],  # larger Bohr-capacities
}
# --------------------------------

ATOM_PRESETS = {
    "H": 1,  "He": 2, "Li": 3, "Be": 4, "B":5, "C":6, "N":7, "O":8, "F":9, "Ne":10,
    "Na":11,"Mg":12,"Al":13,"Si":14,"P":15,"S":16,"Cl":17,"Ar":18
}

# ---------- serial helpers ----------
def find_serial_port():
    cand = []
    for g in AUTO_PORT_GLOBS:
        cand += glob.glob(g)
    if not cand:
        raise RuntimeError("No serial device found. Plug in Arduino and try.")
    # prefer ACM
    cand = sorted(cand, key=lambda s: (0 if 'ACM' in s else 1, s))
    return cand[0]

def open_serial(port):
    s = serial.Serial(port, SERIAL_BAUD, timeout=1)
    time.sleep(2)
    return s

def send(ser, cmd, wait_resp=True):
    ser.write((cmd.strip() + '\n').encode('ascii'))
    if wait_resp:
        return ser.readline().decode('ascii').strip()
    return ""

# ---------- mapping loader ----------
def load_mapping(path=DEFAULT_MAPPING):
    if os.path.exists(path):
        with open(path,'r') as f:
            data = json.load(f)
        mapping = data.get('mapping', {})
        # convert keys to ints
        return {int(k): v for k,v in mapping.items()}
    else:
        # fallback numeric mapping
        return {i: [str(j) for j in range(RING_LEDS[i])] for i in range(len(RING_LEDS))}

# ---------- utility: distribute electrons into shells ----------
def distribute_by_shell(total_electrons, fill_caps):
    """Fill shells inner->outer according to fill_caps list.
       Returns list counts per shell and remainder (if electrons > sum caps)."""
    remaining = total_electrons
    dist = []
    for cap in fill_caps:
        take = min(cap, remaining)
        dist.append(take)
        remaining -= take
    return dist, remaining

def map_shell_to_hardware_positions(ring, count):
    """Return list of actual LED indices (hardware) for `count` electrons on `ring`.
       For ring0 we skip index 0 (nucleus) and use indices 1..outer_count.
       We evenly space electrons among available positions; if count > available positions,
       we cap to available positions and return those indices (user is warned upstream).
    """
    total_leds = RING_LEDS[ring]
    if ring == 0:
        available = total_leds - 1  # outer only
        indices = [1 + i for i in range(available)]
    else:
        available = total_leds
        indices = [i for i in range(total_leds)]
    if available == 0 or count <= 0:
        return []
    # cap
    use = min(count, available)
    step = available / float(use)
    chosen = []
    for k in range(use):
        pos = int(round(k * step)) % available
        chosen.append(indices[pos])
    # remove duplicates while preserving order
    seen = set()
    chosen_unique = []
    for x in chosen:
        if x not in seen:
            chosen_unique.append(x)
            seen.add(x)
    # if we need more (due to rounding) fill remaining sequentially
    i = 0
    while len(chosen_unique) < use:
        cand = indices[i % available]
        if cand not in seen:
            chosen_unique.append(cand)
            seen.add(cand)
        i += 1
    return chosen_unique[:use]

# ---------- LED control helpers ----------
def clear_all(ser):
    return send(ser, "CLEAR")

def set_brightness(ser, b):
    return send(ser, f"BRIGHT {int(max(0,min(255,b)))}")

def set_nucleus(ser, r,g,b):
    return send(ser, f"PIX 0 0 {r} {g} {b}")

def set_pixels_color(ser, ring, idx_list, color):
    for idx in idx_list:
        send(ser, f"PIX {ring} {idx} {color[0]} {color[1]} {color[2]}")

# ---------- display modes ----------
def show_static(ser, fill_caps, total_electrons, nucleus_color=(255,150,60), electron_color=(255,255,255)):
    clear_all(ser)
    set_brightness(ser, SAFE_BRIGHTNESS)
    set_nucleus(ser, *nucleus_color)
    dist, rem = distribute_by_shell(total_electrons, fill_caps)
    if rem > 0:
        print(f"Warning: {rem} electrons couldn't be placed (exceed fill capacities).")
    for ring_idx, shell_count in enumerate(dist):
        if shell_count <= 0:
            continue
        positions = map_shell_to_hardware_positions(ring_idx, shell_count)
        if len(positions) < shell_count:
            print(f"Warning: ring{ring_idx} has {RING_LEDS[ring_idx]} LEDs but requested {shell_count} electrons; placing {len(positions)}.")
        set_pixels_color(ser, ring_idx, positions, electron_color)
    print("Static atom displayed.")

def orbit(ser, fill_caps, total_electrons, nucleus_color=(255,150,60), electron_color=(255,255,255), speed=0.12, duration=10.0):
    clear_all(ser)
    set_brightness(ser, SAFE_BRIGHTNESS)
    set_nucleus(ser, *nucleus_color)
    dist, rem = distribute_by_shell(total_electrons, fill_caps)
    if rem > 0:
        print(f"Warning: {rem} electrons couldn't be placed (exceed fill capacities).")
    # prepare per-ring positions arrays (local positions 0..len-1)
    per_ring_local_counts = []
    for ring_idx, shell_count in enumerate(dist):
        if shell_count <= 0:
            per_ring_local_counts.append([])
            continue
        total_positions = (RING_LEDS[ring_idx]-1) if ring_idx==0 else RING_LEDS[ring_idx]
        use = min(shell_count, total_positions)
        # initial evenly spaced local positions (0..total_positions-1)
        local = [int(round((k * total_positions) / float(use))) % total_positions for k in range(use)]
        per_ring_local_counts.append(local)
    # animate
    end = time.time() + duration
    prev_drawn = [[] for _ in range(len(RING_LEDS))]
    while time.time() < end:
        # clear previous
        for r_idx, drawn in enumerate(prev_drawn):
            for actual_idx in drawn:
                send(ser, f"PIX {r_idx} {actual_idx} 0 0 0")
        prev_drawn = [[] for _ in range(len(RING_LEDS))]
        # step & draw
        for ring_idx, local_positions in enumerate(per_ring_local_counts):
            if not local_positions:
                continue
            total_positions = (RING_LEDS[ring_idx]-1) if ring_idx==0 else RING_LEDS[ring_idx]
            for p_index in range(len(local_positions)):
                local_positions[p_index] = (local_positions[p_index] + 1) % total_positions
                if ring_idx == 0:
                    actual = 1 + (local_positions[p_index] % (RING_LEDS[0]-1))
                else:
                    actual = local_positions[p_index] % RING_LEDS[ring_idx]
                send(ser, f"PIX {ring_idx} {actual} {electron_color[0]} {electron_color[1]} {electron_color[2]}")
                prev_drawn[ring_idx].append(actual)
        time.sleep(speed)
    # cleanup
    for r in range(len(RING_LEDS)):
        if r == 0:
            outer = RING_LEDS[0]-1
            if outer>0:
                send(ser, f"RANGE 0 1 {outer} 0 0 0")
            send(ser, "PIX 0 0 0 0 0")
        else:
            send(ser, f"SET {r} 0 0 0")
    print("Orbit finished and cleared shells.")

# ---------- CLI ----------
def cli():
    mapping = load_mapping(DEFAULT_MAPPING)
    port = find_serial_port()
    print("Using serial port:", port)
    ser = open_serial(port)
    try:
        intro = ser.readline().decode().strip()
        if intro:
            print("Arduino:", intro)
        set_brightness(ser, SAFE_BRIGHTNESS)
        print("Hardware ring sizes:", RING_LEDS)
        print("Shell names (ring -> shell):", list(zip(range(len(SHELL_NAMES)), SHELL_NAMES)))
        print("Available fill modes:", list(FILL_PRESETS.keys()))
        mode = input("Choose fill mode [chemical/bohr] (default chemical): ").strip().lower() or "chemical"
        if mode not in FILL_PRESETS:
            print("Unknown mode, using 'chemical'.")
            mode = 'chemical'
        fill_caps = FILL_PRESETS[mode]
        print(f"Selected mode '{mode}' with shell caps {fill_caps}")

        while True:
            cmd = input("\nEnter command (preset <sym> | custom <N> | static <N> | orbit <N> [sec] | clear | quit): ").strip()
            if not cmd:
                continue
            parts = cmd.split()
            op = parts[0].lower()
            if op == 'quit':
                break
            if op == 'clear':
                clear_all(ser); continue
            if op == 'preset' and len(parts) >= 2:
                sym = parts[1]
                if sym in ATOM_PRESETS:
                    N = ATOM_PRESETS[sym]
                    print(f"Displaying {sym} with {N} electrons (fill mode {mode}) ...")
                    show_static(ser, fill_caps, N)
                else:
                    print("Unknown preset symbol.")
                continue
            if op == 'custom' and len(parts) >= 2:
                try:
                    N = int(parts[1])
                    show_static(ser, fill_caps, N)
                except:
                    print("Invalid number.")
                continue
            if op == 'static' and len(parts) >= 2:
                try:
                    N = int(parts[1])
                    show_static(ser, fill_caps, N)
                except:
                    print("Invalid number.")
                continue
            if op == 'orbit' and len(parts) >= 2:
                try:
                    N = int(parts[1])
                    sec = float(parts[2]) if len(parts) >= 3 else 10.0
                    orbit(ser, fill_caps, N, duration=sec)
                except Exception as e:
                    print("Error:", e)
                continue
            print("Unknown command.")
    finally:
        try:
            clear_all(ser)
        except:
            pass
        ser.close()

if __name__ == "__main__":
    cli()
