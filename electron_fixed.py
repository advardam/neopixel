cat > electron_model_fixed.py <<'PY'
"""electron_model_fixed.py

Interactive Electron Model GUI (Tkinter)
- Tries multiple locations for mapping JSON (MAPPING_PATH, ./led_mapping.json, file chooser)
- Fixed fallback syntax bug
"""
import json
import math
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

MAPPING_PATH = "/mnt/data/led_mapping.json"   # original expected path

PRESETS = [
    ("Hydrogen", 1),
    ("Helium", 2),
    ("Lithium", 3),
    ("Carbon", 6),
    ("Oxygen", 8),
    ("Neon", 10),
    ("Sodium", 11),
    ("Chlorine", 17),
    ("Argon", 18),
    ("Calcium", 20),
]

SHELL_CAP = [2, 8, 18, 32]  # classical capacities for K, L, M, N

def load_mapping(path):
    with open(path, "r") as f:
        return json.load(f)

def try_load_mapping():
    # 1) Try MAPPING_PATH
    if os.path.exists(MAPPING_PATH):
        return load_mapping(MAPPING_PATH), MAPPING_PATH
    # 2) Try local file next to script
    local = os.path.join(os.getcwd(), "led_mapping.json")
    if os.path.exists(local):
        return load_mapping(local), local
    # 3) Ask the user to pick a file with a dialog (only if tkinter root exists)
    return None, None

def compute_shells(Z):
    shells = [0,0,0,0]
    remaining = max(0, int(math.floor(Z)))
    for i,cap in enumerate(SHELL_CAP):
        take = min(remaining, cap)
        shells[i] = take
        remaining -= take
    return shells

def map_shells_to_rings(shells, ring_leds):
    # Flatten electrons by shells
    electrons = []
    for s,count in enumerate(shells):
        electrons += [s]*count
    led_state = [ [False]*n for n in ring_leds ]
    eidx = 0
    for r_idx, r_count in enumerate(ring_leds):
        for i in range(r_count):
            if eidx < len(electrons):
                led_state[r_idx][i] = True
                eidx += 1
            else:
                break
    remaining = len(electrons) - eidx
    return led_state, remaining

class ElectronModelApp:
    def __init__(self, root, mapping, mapping_path=None):
        self.root = root
        self.mapping = mapping
        self.mapping_path = mapping_path
        self.ring_leds = mapping.get("ring_leds", [7,8,12,16])
        self.led_state = [ [False]*n for n in self.ring_leds ]
        self.shells = [0,0,0,0]

        root.title("Electron Model — LED Mapping")
        self.build_ui()

    def build_ui(self):
        frm = ttk.Frame(self.root, padding=10)
        frm.grid(sticky="nsew")

        # Presets and atomic number
        top = ttk.Frame(frm)
        top.grid(row=0, column=0, sticky="w", pady=(0,8))

        ttk.Label(top, text="Preset:").grid(row=0, column=0, padx=(0,6))
        preset_menu = ttk.Combobox(top, values=[f"{n} (Z={z})" for n,z in PRESETS], state="readonly", width=20)
        preset_menu.current(3)
        preset_menu.grid(row=0, column=1)
        def on_preset_change(event):
            sel = preset_menu.get()
            z = int(sel.split("(Z=")[-1].rstrip(')'))
            self.atomic_var.set(str(z))
            self.load_atom(int(z))
        preset_menu.bind("<<ComboboxSelected>>", on_preset_change)

        ttk.Label(top, text="  Atomic Z:").grid(row=0, column=2, padx=(10,6))
        self.atomic_var = tk.StringVar(value=str(PRESETS[3][1]))
        atomic_entry = ttk.Entry(top, textvariable=self.atomic_var, width=6)
        atomic_entry.grid(row=0, column=3)

        load_btn = ttk.Button(top, text="Load configuration", command=self.on_load_click)
        load_btn.grid(row=0, column=4, padx=(8,0))

        # Shell display
        self.shell_label = ttk.Label(frm, text="Shells (K,L,M,N): 0 , 0 , 0 , 0")
        self.shell_label.grid(row=1, column=0, sticky="w", pady=(0,8))

        # Rings frame
        rings_frame = ttk.Frame(frm)
        rings_frame.grid(row=2, column=0, sticky="nsew")
        self.ring_frames = []
        for r_idx, count in enumerate(self.ring_leds):
            rf = ttk.LabelFrame(rings_frame, text=f"Ring {r_idx} — {count} LEDs", padding=8)
            rf.grid(row=r_idx//2, column=r_idx%2, padx=6, pady=6, sticky="nw")
            self.ring_frames.append(rf)
            self.build_ring_buttons(r_idx, rf, count)

        # Reference photo path
        ref = self.mapping.get("reference_photo", "")
        ttk.Label(frm, text=f"Reference photo: {ref}", foreground="gray").grid(row=4, column=0, sticky="w", pady=(10,0))

        # Bottom buttons
        bottom = ttk.Frame(frm)
        bottom.grid(row=5, column=0, sticky="w", pady=(12,0))
        ttk.Button(bottom, text="Choose mapping file", command=self.choose_mapping_file).grid(row=0, column=0)
        ttk.Button(bottom, text="Export LED state to JSON", command=self.export_state).grid(row=0, column=1, padx=(6,0))
        ttk.Button(bottom, text="Clear LEDs", command=self.clear_leds).grid(row=0, column=2, padx=(8,0))
        ttk.Button(bottom, text="Exit", command=self.root.quit).grid(row=0, column=3, padx=(8,0))

    def build_ring_buttons(self, ring_idx, frame, count):
        btns = []
        for i in range(count):
            b = tk.Button(frame, text=str(i), width=3, relief="raised",
                          command=lambda r=ring_idx, idx=i: self.toggle_led(r, idx))
            b.grid(row=i//8, column=i%8, padx=2, pady=2)
            btns.append(b)
        if not hasattr(self, "ring_buttons"):
            self.ring_buttons = {}
        self.ring_buttons[ring_idx] = btns

    def toggle_led(self, ring, idx):
        self.led_state[ring][idx] = not self.led_state[ring][idx]
        self.update_button_visual(ring, idx)

    def update_button_visual(self, ring, idx):
        btn = self.ring_buttons[ring][idx]
        if self.led_state[ring][idx]:
            btn.config(relief="sunken", background="#ffd54f")
        else:
            btn.config(relief="raised", background="#f0f0f0")

    def on_load_click(self):
        try:
            z = int(self.atomic_var.get())
            if z < 1 or z > 118:
                messagebox.showwarning("Atomic number", "Please enter an atomic number between 1 and 118.")
                return
            self.load_atom(z)
        except ValueError:
            messagebox.showerror("Input error", "Invalid atomic number.")

    def load_atom(self, Z):
        shells = compute_shells(Z)
        self.shells = shells
        self.shell_label.config(text=f"Shells (K,L,M,N): {shells[0]} , {shells[1]} , {shells[2]} , {shells[3]}")
        new_state, remaining = map_shells_to_rings(shells, self.ring_leds)
        self.led_state = new_state
        for r_idx, btns in self.ring_buttons.items():
            for i, btn in enumerate(btns):
                self.update_button_visual(r_idx, i)
        if remaining > 0:
            messagebox.showinfo("Note", f"{remaining} electrons could not be displayed (not enough physical LEDs).")

    def clear_leds(self):
        self.led_state = [ [False]*n for n in self.ring_leds ]
        for r_idx, btns in self.ring_buttons.items():
            for i,btn in enumerate(btns):
                self.update_button_visual(r_idx, i)
        self.shell_label.config(text="Shells (K,L,M,N): 0 , 0 , 0 , 0")

    def export_state(self):
        out = { "ring_leds": self.ring_leds, "led_state": self.led_state, "shells": self.shells }
        default_path = os.path.join(os.getcwd(), "led_state_output.json")
        try:
            with open(default_path, "w") as f:
                json.dump(out, f, indent=2)
            messagebox.showinfo("Exported", f"LED state written to: {default_path}")
        except Exception as e:
            messagebox.showerror("Export error", str(e))

    def choose_mapping_file(self):
        path = filedialog.askopenfilename(title="Select mapping JSON", filetypes=[("JSON files","*.json"),("All files","*.*")])
        if not path:
            return
        try:
            mapping = load_mapping(path)
            self.mapping = mapping
            self.mapping_path = path
            self.ring_leds = mapping.get("ring_leds", self.ring_leds)
            # rebuild ring buttons to match new counts
            for widget in self.root.winfo_children():
                widget.destroy()
            self.build_ui()
            messagebox.showinfo("Mapping loaded", f"Loaded mapping from: {path}")
        except Exception as e:
            messagebox.showerror("Load error", str(e))

if __name__ == '__main__':
    mapping, mapping_path = None, None
    try:
        loaded = try_load_mapping()
        if loaded[0] is not None:
            mapping, mapping_path = loaded
    except Exception:
        mapping = None

    # If not found, fall back to a safe default mapping (valid dict)
    if mapping is None:
        # Try local file in cwd
        local = os.path.join(os.getcwd(), "led_mapping.json")
        if os.path.exists(local):
            try:
                mapping = load_mapping(local)
                mapping_path = local
            except Exception:
                mapping = { "ring_leds": [7,8,12,16] }
        else:
            mapping = { "ring_leds": [7,8,12,16] }

    root = tk.Tk()
    app = ElectronModelApp(root, mapping, mapping_path)
    root.mainloop()
PY
