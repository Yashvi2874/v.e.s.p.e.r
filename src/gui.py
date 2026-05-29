# src/gui.py

import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox
from PIL import Image, ImageTk
import cv2
import datetime

from emergency_db import fetch_offline_metadata
from location_service import ResilientLocationService

try:
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

class HybridAttentionSpeechGUI:
    # Obsidian Theme Parameters (Highly Professional, Human-Designed)
    BG_PRIMARY = "#08080A"       # Pure dark obsidian background
    BG_SECONDARY = "#121216"     # Deep warm charcoal card background
    BG_TERTIARY = "#1A1A22"      # Muted grey-black selection state
    BORDER_COLOR = "#22222B"     # Sleek modern border frame color
    TEXT_PRIMARY = "#F3F4F6"     # Crisp clean gray-white text
    TEXT_SECONDARY = "#9CA3AF"   # Cool gray subtext
    ACCENT_PRIMARY = "#8B5CF6"   # Soft Lavender/Purple accent (Tesla/native dashboard style)
    ACCENT_GREEN = "#10B981"     # Emerald Green
    ACCENT_AMBER = "#F59E0B"     # Warning Amber
    ACCENT_RED = "#EF4444"       # Alert Red
    FONT_FAMILY = "Segoe UI"     # Clean typography fallback

    def __init__(self, root, controller=None):
        self.root = root
        self.controller = controller
        self.loc_service = ResilientLocationService()
        self.router = None
        self.obd_manager = None
        
        # Window settings
        self.root.title("V.E.S.P.E.R. - Vehicle Edge Sensor Panic & Emergency Router")
        self.root.geometry("1200x750")
        self.root.minsize(800, 500)
        self.root.configure(bg=self.BG_PRIMARY)
        
        # Configure Tab Framework Design Elements
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        # Configure Notebook styling
        self.style.configure("TNotebook", background=self.BG_PRIMARY, borderwidth=0)
        self.style.configure(
            "TNotebook.Tab", 
            background=self.BG_SECONDARY, 
            foreground=self.TEXT_SECONDARY, 
            padding=(24, 8), 
            font=(self.FONT_FAMILY, 13, "bold"),
            borderwidth=0
        )
        self.style.map(
            "TNotebook.Tab", 
            background=[("selected", self.ACCENT_PRIMARY), ("!selected", self.BG_SECONDARY)], 
            foreground=[("selected", "white"), ("!selected", self.TEXT_SECONDARY)]
        )

        # Style Combobox
        self.style.configure(
            "TCombobox", 
            fieldbackground=self.BG_SECONDARY, 
            background=self.BG_TERTIARY, 
            foreground=self.TEXT_PRIMARY, 
            bordercolor=self.BORDER_COLOR, 
            arrowcolor=self.TEXT_PRIMARY,
            font=(self.FONT_FAMILY, 15)
        )
        self.style.map(
            "TCombobox",
            fieldbackground=[("readonly", self.BG_SECONDARY)],
            foreground=[("readonly", self.TEXT_PRIMARY)]
        )
        # Ensure dropdown popup list values are size 15
        self.root.option_add("*TCombobox*Listbox.font", (self.FONT_FAMILY, 15))

        # Create bottom persistent bar first to ensure correct layout allocation
        self.create_road_sos_widgets()

        # Create Notebook container above the persistent bar
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Build Presentation Layers
        self.init_safety_monitor_tab()
        self.init_roadsos_hub_tab()

        # Initialize display tracking variables
        self.photo_image = None
        self.last_frame = None
        self.last_attention = 0
        self.sos_active = False
        self.sos_flash_state = False

        # Bind window events
        self.root.bind("<Configure>", self.on_resize)

    def init_safety_monitor_tab(self):
        """Tab 1: Keeps the original live attention and camera tracking widgets."""
        self.tab_monitor = tk.Frame(self.notebook, bg=self.BG_PRIMARY)
        self.notebook.add(self.tab_monitor, text=" Live Monitor ")
        
        # Scrollable container inside Tab 1
        self.main_frame = tk.Frame(self.tab_monitor, bg=self.BG_PRIMARY)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        self.canvas = tk.Canvas(self.main_frame, bg=self.BG_PRIMARY, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self.main_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=self.BG_PRIMARY)
        
        self.scrollable_frame.bind(
            "<Configure>",
            self._on_frame_configure
        )
        self.canvas.bind(
            "<Configure>",
            self._on_canvas_configure
        )
        
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self._bind_scroll_events()
        
        # Header block
        self.header_frame = tk.Frame(self.scrollable_frame, bg=self.BG_PRIMARY, pady=10)
        self.header_frame.pack(fill=tk.X)
        
        self.title_label = tk.Label(
            self.header_frame, 
            text="V.E.S.P.E.R.", 
            font=(self.FONT_FAMILY, 34, "bold"), 
            fg=self.TEXT_PRIMARY, 
            bg=self.BG_PRIMARY
        )
        self.title_label.pack()
        
        self.subtitle_label = tk.Label(
            self.header_frame, 
            text="Vehicle Edge Sensor Panic & Emergency Router", 
            font=(self.FONT_FAMILY, 14), 
            fg=self.TEXT_SECONDARY, 
            bg=self.BG_PRIMARY
        )
        self.subtitle_label.pack()
        
        # Split Work Panel
        self.content_frame = tk.Frame(self.scrollable_frame, bg=self.BG_PRIMARY)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        self.content_frame.columnconfigure(0, weight=1)
        self.content_frame.columnconfigure(1, weight=1)
        
        # Left Visual Column (Webcam Stream)
        self.video_column = tk.Frame(self.content_frame, bg=self.BG_PRIMARY)
        self.video_column.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.video_column.columnconfigure(0, weight=1)
        
        self.video_frame = tk.Frame(self.video_column, bg=self.BG_SECONDARY, highlightbackground=self.BORDER_COLOR, highlightthickness=1)
        self.video_frame.grid(row=1, column=0, sticky="nsew", pady=10)
        self.video_frame.columnconfigure(0, weight=1)
        
        self.video_title = tk.Label(
            self.video_frame, 
            text="Live Driver Feed", 
            font=(self.FONT_FAMILY, 18, "bold"), 
            fg=self.TEXT_PRIMARY, 
            bg=self.BG_SECONDARY
        )
        self.video_title.grid(row=0, column=0, pady=(10, 5), sticky="ew")
        
        self.video_label = tk.Label(self.video_frame, bg="#000000", anchor="center")
        self.video_label.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        
        # Right Numerical/Alerts Column
        self.info_column = tk.Frame(self.content_frame, bg=self.BG_PRIMARY)
        self.info_column.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        self.info_column.columnconfigure(0, weight=1)
        
        # Attention Level Box
        self.attention_frame = tk.Frame(self.info_column, bg=self.BG_SECONDARY, highlightbackground=self.BORDER_COLOR, highlightthickness=1)
        self.attention_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.attention_frame.columnconfigure(0, weight=1)
        
        self.attention_title = tk.Label(
            self.attention_frame, 
            text="Driver Attention Index", 
            font=(self.FONT_FAMILY, 18, "bold"), 
            fg=self.TEXT_PRIMARY, 
            bg=self.BG_SECONDARY
        )
        self.attention_title.pack(pady=(10, 5))
        
        self.attention_label = tk.Label(
            self.attention_frame, 
            text="0%", 
            font=(self.FONT_FAMILY, 34, "bold"), 
            fg=self.ACCENT_GREEN, 
            bg=self.BG_SECONDARY
        )
        self.attention_label.pack(pady=5)
        
        # Attention Progress Bar
        self.progress_frame = tk.Frame(self.attention_frame, bg=self.BG_SECONDARY)
        self.progress_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        self.progress_frame.columnconfigure(0, weight=1)
        
        self.progress_canvas = tk.Canvas(self.progress_frame, height=22, bg=self.BG_TERTIARY, highlightthickness=0)
        self.progress_canvas.grid(row=0, column=0, sticky="ew", padx=5)
        
        # Rolling Attention Line Chart
        self.embed_rolling_attention_chart(self.attention_frame)
        
        # Driver Status Alert Box
        self.status_frame = tk.Frame(self.info_column, bg=self.BG_SECONDARY, highlightbackground=self.BORDER_COLOR, highlightthickness=1)
        self.status_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.status_frame.columnconfigure(0, weight=1)
        
        self.status_title = tk.Label(
            self.status_frame, 
            text="Driver Status Indicators", 
            font=(self.FONT_FAMILY, 18, "bold"), 
            fg=self.TEXT_PRIMARY, 
            bg=self.BG_SECONDARY
        )
        self.status_title.pack(pady=(10, 5))
        
        self.drowsiness_label = tk.Label(
            self.status_frame, 
            text="Normal", 
            font=(self.FONT_FAMILY, 18, "bold"), 
            fg=self.ACCENT_GREEN, 
            bg=self.BG_SECONDARY
        )
        self.drowsiness_label.pack(pady=5)
        
        self.status_label = tk.Label(
            self.status_frame, 
            text="Driver is alert and attentive", 
            font=(self.FONT_FAMILY, 14), 
            fg=self.TEXT_SECONDARY, 
            bg=self.BG_SECONDARY
        )
        self.status_label.pack(pady=(0, 10))
        
        # Audio Speech Transcription Panel
        self.transcription_frame = tk.Frame(self.info_column, bg=self.BG_SECONDARY, highlightbackground=self.BORDER_COLOR, highlightthickness=1)
        self.transcription_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        self.transcription_frame.columnconfigure(0, weight=1)
        
        self.transcription_title = tk.Label(
            self.transcription_frame, 
            text="Cabin Speech Logs", 
            font=(self.FONT_FAMILY, 18, "bold"), 
            fg=self.TEXT_PRIMARY, 
            bg=self.BG_SECONDARY
        )
        self.transcription_title.pack(pady=(10, 5))
        
        self.transcription_text_frame = tk.Frame(self.transcription_frame, bg=self.BG_SECONDARY)
        self.transcription_text_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=(0, 10))
        self.transcription_text_frame.columnconfigure(0, weight=1)
        
        self.transcription_text = scrolledtext.ScrolledText(
            self.transcription_text_frame, 
            wrap=tk.WORD, 
            font=(self.FONT_FAMILY, 13),
            bg=self.BG_PRIMARY,
            fg=self.TEXT_PRIMARY,
            insertbackground=self.TEXT_PRIMARY,
            relief=tk.FLAT,
            bd=0,
            height=8
        )
        self.transcription_text.grid(row=0, column=0, sticky="nsew")
        
        # Warnings Alert Labels
        self.alerts_frame = tk.Frame(self.info_column, bg=self.BG_PRIMARY)
        self.alerts_frame.grid(row=3, column=0, sticky="ew")
        self.alerts_frame.columnconfigure(0, weight=1)
        
        self.stress_warning_label = tk.Label(
            self.alerts_frame, 
            text="Biometric Core Active: Scanning for cognitive stress...", 
            font=(self.FONT_FAMILY, 18, "bold"), 
            fg=self.ACCENT_PRIMARY, 
            bg=self.BG_SECONDARY,
            highlightbackground=self.BORDER_COLOR,
            highlightthickness=1,
            bd=0,
            padx=20,
            pady=12
        )
        self.stress_warning_label.grid(row=0, column=0, sticky="ew", pady=5)
        
        self.help_warning_label = tk.Label(
            self.alerts_frame, 
            text="Acoustic Sensors Online: Listening for voice distress...", 
            font=(self.FONT_FAMILY, 18, "bold"), 
            fg=self.ACCENT_PRIMARY, 
            bg=self.BG_SECONDARY,
            highlightbackground=self.BORDER_COLOR,
            highlightthickness=1,
            bd=0,
            padx=20,
            pady=12
        )
        self.help_warning_label.grid(row=1, column=0, sticky="ew", pady=5)
        
        # Bottom Demo Trigger Box
        self.demo_frame = tk.Frame(self.scrollable_frame, bg=self.BG_PRIMARY, pady=10)
        self.demo_frame.pack(fill=tk.X)
        
        self.btn_crash = tk.Button(
            self.demo_frame, 
            text="Simulate Vehicle Collision Event", 
            bg=self.BG_SECONDARY, 
            fg=self.ACCENT_RED, 
            font=(self.FONT_FAMILY, 18, "bold"), 
            activebackground=self.BG_TERTIARY,
            activeforeground=self.ACCENT_RED,
            highlightbackground=self.BORDER_COLOR,
            highlightthickness=1,
            relief=tk.FLAT,
            bd=0,
            pady=10,
            command=self.activate_sos_emergency_mode
        )
        self.btn_crash.pack(pady=10)

    def init_roadsos_hub_tab(self):
        """Tab 2: The dedicated RoadSOS triage dashboard."""
        self.tab_sos = tk.Frame(self.notebook, bg=self.BG_PRIMARY)
        self.notebook.add(self.tab_sos, text=" RoadSOS Hub ")

        # Scrollable container inside Tab 2
        self.main_sos_frame = tk.Frame(self.tab_sos, bg=self.BG_PRIMARY)
        self.main_sos_frame.pack(fill=tk.BOTH, expand=True)
        
        self.sos_canvas = tk.Canvas(self.main_sos_frame, bg=self.BG_PRIMARY, highlightthickness=0)
        self.sos_scrollbar = tk.Scrollbar(self.main_sos_frame, orient="vertical", command=self.sos_canvas.yview)
        self.scrollable_sos_frame = tk.Frame(self.sos_canvas, bg=self.BG_PRIMARY)
        
        self.scrollable_sos_frame.bind(
            "<Configure>",
            self._on_sos_frame_configure
        )
        self.sos_canvas.bind(
            "<Configure>",
            self._on_sos_canvas_configure
        )
        
        self.sos_canvas_window = self.sos_canvas.create_window((0, 0), window=self.scrollable_sos_frame, anchor="nw")
        self.sos_canvas.configure(yscrollcommand=self.sos_scrollbar.set)
        
        self.sos_canvas.pack(side="left", fill="both", expand=True)
        self.sos_scrollbar.pack(side="right", fill="y")
        self._bind_sos_scroll_events()

        # Upper Layout Block - Live Metadata Details
        self.meta_frame = tk.Frame(
            self.scrollable_sos_frame, 
            bg=self.BG_SECONDARY, 
            highlightbackground=self.BORDER_COLOR, 
            highlightthickness=1
        )
        self.meta_frame.pack(fill=tk.X, padx=15, pady=10)

        self.meta_title = tk.Label(
            self.meta_frame, 
            text="Network Node & Location Parameters", 
            fg=self.ACCENT_PRIMARY, 
            bg=self.BG_SECONDARY, 
            font=(self.FONT_FAMILY, 16, "bold")
        )
        self.meta_title.pack(anchor="w", padx=15, pady=(8, 2))

        self.lbl_loc = tk.Label(
            self.meta_frame, 
            text="Resolving Telemetry...", 
            fg=self.TEXT_SECONDARY, 
            bg=self.BG_SECONDARY, 
            font=(self.FONT_FAMILY, 15)
        )
        self.lbl_loc.pack(anchor="w", padx=15, pady=(0, 8))
        
        # Alert Activation Announcement Banner
        self.alarm_banner = tk.Label(
            self.scrollable_sos_frame, 
            text="System Status: Nominal | Safe Operations Active", 
            fg=self.ACCENT_GREEN, 
            bg=self.BG_SECONDARY, 
            highlightbackground=self.BORDER_COLOR, 
            highlightthickness=1, 
            font=(self.FONT_FAMILY, 22, "bold"), 
            height=2
        )
        self.alarm_banner.pack(fill=tk.X, padx=15, pady=5)

        # Main Workspace Split Pane Layout (Three columns config)
        self.workspace_frame = tk.Frame(self.scrollable_sos_frame, bg=self.BG_PRIMARY)
        self.workspace_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        # ------------------ COLUMN 0: Local Settings & Coordinates ------------------
        self.loc_col = tk.Frame(self.workspace_frame, bg=self.BG_PRIMARY)
        
        # Location Control Frame
        self.loc_frame = tk.Frame(
            self.loc_col, 
            bg=self.BG_SECONDARY, 
            highlightbackground=self.BORDER_COLOR, 
            highlightthickness=1
        )
        self.loc_frame.pack(fill=tk.X, pady=(0, 10))
        self.loc_frame.columnconfigure(1, weight=1)
        
        tk.Label(
            self.loc_frame, 
            text="Regional Overrides", 
            font=(self.FONT_FAMILY, 20, "bold"), 
            fg=self.TEXT_PRIMARY, 
            bg=self.BG_SECONDARY
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=15, pady=(12, 8))
        
        tk.Label(
            self.loc_frame, 
            text="Country:", 
            font=(self.FONT_FAMILY, 15), 
            fg=self.TEXT_SECONDARY, 
            bg=self.BG_SECONDARY
        ).grid(row=1, column=0, sticky="w", padx=15, pady=5)
        
        self.country_combo = ttk.Combobox(self.loc_frame, state="readonly", values=["India"], font=(self.FONT_FAMILY, 15))
        self.country_combo.set("India")
        self.country_combo.grid(row=1, column=1, sticky="ew", padx=15, pady=5)
        self.country_combo.bind("<<ComboboxSelected>>", self.on_country_select)
        
        tk.Label(
            self.loc_frame, 
            text="City Selection:", 
            font=(self.FONT_FAMILY, 15), 
            fg=self.TEXT_SECONDARY, 
            bg=self.BG_SECONDARY
        ).grid(row=2, column=0, sticky="w", padx=15, pady=5)
        
        self.city_combo = ttk.Combobox(
            self.loc_frame, 
            state="readonly", 
            values=["Chennai", "Bengaluru", "Mumbai", "Delhi", "Kolkata", "Hyderabad", "Pune"], 
            font=(self.FONT_FAMILY, 15)
        )
        self.city_combo.set("Chennai")
        self.city_combo.grid(row=2, column=1, sticky="ew", padx=15, pady=5)
        self.city_combo.bind("<<ComboboxSelected>>", self.on_city_select)

        # Custom Search input for any location in India
        tk.Label(
            self.loc_frame, 
            text="Search Location:", 
            font=(self.FONT_FAMILY, 15), 
            fg=self.TEXT_SECONDARY, 
            bg=self.BG_SECONDARY
        ).grid(row=3, column=0, sticky="w", padx=15, pady=5)
        
        self.search_entry = tk.Entry(
            self.loc_frame, 
            font=(self.FONT_FAMILY, 15),
            bg=self.BG_PRIMARY,
            fg=self.TEXT_PRIMARY,
            insertbackground=self.TEXT_PRIMARY,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=self.BORDER_COLOR
        )
        self.search_entry.grid(row=3, column=1, sticky="ew", padx=15, pady=5)
        self.search_entry.insert(0, "Somaiya, Mumbai")
        
        self.search_btn = tk.Button(
            self.loc_frame, 
            text="Search & Dispatch", 
            bg=self.ACCENT_PRIMARY, 
            fg="white", 
            font=(self.FONT_FAMILY, 12, "bold"), 
            activebackground=self.BG_TERTIARY,
            activeforeground="white",
            relief=tk.FLAT, 
            bd=0,
            pady=4,
            command=self.on_location_search
        )
        self.search_btn.grid(row=4, column=0, columnspan=2, sticky="ew", padx=15, pady=(5, 15))
        self.city_combo.set("Chennai")
        self.city_combo.grid(row=2, column=1, sticky="ew", padx=15, pady=(5, 15))
        self.city_combo.bind("<<ComboboxSelected>>", self.on_city_select)
        
        # Telemetry Display Frame
        self.obd_frame = tk.Frame(
            self.loc_col, 
            bg=self.BG_SECONDARY, 
            highlightbackground=self.BORDER_COLOR, 
            highlightthickness=1
        )
        self.obd_frame.pack(fill=tk.X, pady=(0, 10))
        self.obd_frame.columnconfigure(1, weight=1)
        
        tk.Label(
            self.obd_frame, 
            text="Vehicle Telemetry Reads", 
            font=(self.FONT_FAMILY, 20, "bold"), 
            fg=self.TEXT_PRIMARY, 
            bg=self.BG_SECONDARY
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=15, pady=(12, 8))
        
        tk.Label(
            self.obd_frame, 
            text="Speed / Velocity:", 
            font=(self.FONT_FAMILY, 15), 
            fg=self.TEXT_SECONDARY, 
            bg=self.BG_SECONDARY
        ).grid(row=1, column=0, sticky="w", padx=15, pady=3)
        
        self.obd_speed_label = tk.Label(
            self.obd_frame, 
            text="0.0 km/h", 
            font=("Consolas", 15), 
            fg=self.TEXT_PRIMARY, 
            bg=self.BG_SECONDARY
        )
        self.obd_speed_label.grid(row=1, column=1, sticky="w", padx=5, pady=3)
        
        tk.Label(
            self.obd_frame, 
            text="Engine RPM:", 
            font=(self.FONT_FAMILY, 15), 
            fg=self.TEXT_SECONDARY, 
            bg=self.BG_SECONDARY
        ).grid(row=2, column=0, sticky="w", padx=15, pady=3)
        
        self.obd_rpm_label = tk.Label(
            self.obd_frame, 
            text="0 RPM", 
            font=("Consolas", 15), 
            fg=self.TEXT_PRIMARY, 
            bg=self.BG_SECONDARY
        )
        self.obd_rpm_label.grid(row=2, column=1, sticky="w", padx=5, pady=3)
        
        tk.Label(
            self.obd_frame, 
            text="Load Index:", 
            font=(self.FONT_FAMILY, 15), 
            fg=self.TEXT_SECONDARY, 
            bg=self.BG_SECONDARY
        ).grid(row=3, column=0, sticky="w", padx=15, pady=3)
        
        self.obd_load_label = tk.Label(
            self.obd_frame, 
            text="0.0 %", 
            font=("Consolas", 15), 
            fg=self.TEXT_PRIMARY, 
            bg=self.BG_SECONDARY
        )
        self.obd_load_label.grid(row=3, column=1, sticky="w", padx=5, pady=3)
        
        tk.Label(
            self.obd_frame, 
            text="G-Force (Accelerometer):", 
            font=(self.FONT_FAMILY, 15), 
            fg=self.TEXT_SECONDARY, 
            bg=self.BG_SECONDARY
        ).grid(row=4, column=0, sticky="w", padx=15, pady=3)
        
        self.obd_gforce_label = tk.Label(
            self.obd_frame, 
            text="1.00g (Normal)", 
            font=(self.FONT_FAMILY, 15, "bold"), 
            fg=self.ACCENT_GREEN, 
            bg=self.BG_SECONDARY
        )
        self.obd_gforce_label.grid(row=4, column=1, sticky="w", padx=5, pady=3)
        
        tk.Label(
            self.obd_frame, 
            text="Airbag Deployment DTC:", 
            font=(self.FONT_FAMILY, 15), 
            fg=self.TEXT_SECONDARY, 
            bg=self.BG_SECONDARY
        ).grid(row=5, column=0, sticky="w", padx=15, pady=(3, 12))
        
        self.obd_dtc_label = tk.Label(
            self.obd_frame, 
            text="OK", 
            font=(self.FONT_FAMILY, 15, "bold"), 
            fg=self.ACCENT_GREEN, 
            bg=self.BG_SECONDARY
        )
        self.obd_dtc_label.grid(row=5, column=1, sticky="w", padx=5, pady=(3, 12))

        # Scenario Simulator Frame
        self.scenario_frame = tk.Frame(
            self.loc_col, 
            bg=self.BG_SECONDARY, 
            highlightbackground=self.BORDER_COLOR, 
            highlightthickness=1
        )
        self.scenario_frame.pack(fill=tk.X, pady=(0, 10))
        self.scenario_frame.columnconfigure(1, weight=1)
        
        tk.Label(
            self.scenario_frame, 
            text="Scenario Simulator", 
            font=(self.FONT_FAMILY, 20, "bold"), 
            fg=self.TEXT_PRIMARY, 
            bg=self.BG_SECONDARY
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=15, pady=(12, 8))
        
        tk.Label(
            self.scenario_frame, 
            text="Active Preset:", 
            font=(self.FONT_FAMILY, 15), 
            fg=self.TEXT_SECONDARY, 
            bg=self.BG_SECONDARY
        ).grid(row=1, column=0, sticky="w", padx=15, pady=5)
        
        self.scenario_combo = ttk.Combobox(self.scenario_frame, state="readonly", values=["Normal Drive", "Normal Cruise", "Swerving Erratic", "Hard Braking", "Critical Side Impact"], font=(self.FONT_FAMILY, 15))
        self.scenario_combo.set("Normal Drive")
        self.scenario_combo.grid(row=1, column=1, sticky="ew", padx=15, pady=(5, 15))
        self.scenario_combo.bind("<<ComboboxSelected>>", self.on_scenario_select)

        # ------------------ COLUMN 1: Triage Ranked Directory ------------------
        self.middle_col = tk.Frame(self.workspace_frame, bg=self.BG_PRIMARY)

        self.lbl_dir = tk.Label(
            self.middle_col, 
            text="Emergency Directory (Nearest Facilities)", 
            fg=self.TEXT_PRIMARY, 
            bg=self.BG_PRIMARY, 
            font=(self.FONT_FAMILY, 20, "bold")
        )
        self.lbl_dir.pack(anchor="w", pady=(0, 5))

        self.directory_listbox = tk.Text(
            self.middle_col, 
            bg=self.BG_SECONDARY, 
            fg=self.TEXT_PRIMARY, 
            font=(self.FONT_FAMILY, 15), 
            wrap=tk.WORD, 
            bd=0, 
            height=22, 
            highlightthickness=1, 
            highlightbackground=self.BORDER_COLOR
        )
        self.directory_listbox.pack(fill=tk.BOTH, expand=True)

        # ------------------ COLUMN 2: Golden Hour Guide & SMS ------------------
        self.right_col = tk.Frame(self.workspace_frame, bg=self.BG_PRIMARY, width=350)

        # Distress Auto-Generator Section
        self.msg_frame = tk.Frame(
            self.right_col, 
            bg=self.BG_SECONDARY, 
            highlightbackground=self.BORDER_COLOR, 
            highlightthickness=1
        )
        self.msg_frame.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            self.msg_frame, 
            text="Outbound Emergency SMS Payload", 
            font=(self.FONT_FAMILY, 16, "bold"), 
            fg=self.TEXT_PRIMARY, 
            bg=self.BG_SECONDARY
        ).pack(anchor="w", padx=15, pady=(12, 8))

        self.txt_msg = tk.Text(
            self.msg_frame, 
            height=8, 
            width=38, 
            bg=self.BG_PRIMARY, 
            fg=self.TEXT_PRIMARY, 
            font=(self.FONT_FAMILY, 14), 
            bd=0,
            highlightthickness=1,
            highlightbackground=self.BORDER_COLOR
        )
        self.txt_msg.pack(padx=15, pady=(0, 10), fill=tk.X)
        
        self.copy_btn = tk.Button(
            self.msg_frame, 
            text="Copy Distress SMS", 
            bg=self.ACCENT_PRIMARY, 
            fg="white", 
            font=(self.FONT_FAMILY, 15, "bold"), 
            activebackground=self.BG_TERTIARY,
            activeforeground="white",
            relief=tk.FLAT, 
            bd=0,
            pady=6,
            command=self.copy_distress_msg
        )
        self.copy_btn.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        # Emergency Dials Panel
        self.quick_dials = tk.Frame(
            self.right_col, 
            bg=self.BG_SECONDARY, 
            highlightbackground=self.BORDER_COLOR, 
            highlightthickness=1
        )
        self.quick_dials.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(
            self.quick_dials, 
            text="Helplines Quick Dials", 
            font=(self.FONT_FAMILY, 16, "bold"), 
            fg=self.TEXT_PRIMARY, 
            bg=self.BG_SECONDARY
        ).pack(anchor="w", padx=15, pady=(12, 8))
        
        self.dial_med_btn = tk.Button(
            self.quick_dials, 
            text="Dial Medical", 
            bg=self.ACCENT_RED, 
            fg="white", 
            font=(self.FONT_FAMILY, 15, "bold"), 
            activebackground=self.BG_TERTIARY,
            activeforeground="white",
            relief=tk.FLAT, 
            bd=0,
            pady=6,
            command=self.dial_medical_call
        )
        self.dial_med_btn.pack(fill=tk.X, padx=15, pady=5)
        
        self.dial_pol_btn = tk.Button(
            self.quick_dials, 
            text="Dial Police", 
            bg=self.ACCENT_PRIMARY, 
            fg="white", 
            font=(self.FONT_FAMILY, 15, "bold"), 
            activebackground=self.BG_TERTIARY,
            activeforeground="white",
            relief=tk.FLAT, 
            bd=0,
            pady=6,
            command=self.dial_police_call
        )
        self.dial_pol_btn.pack(fill=tk.X, padx=15, pady=(0, 5))
        
        self.sos_reset_btn = tk.Button(
            self.quick_dials, 
            text="Reset Emergency State", 
            bg=self.BG_TERTIARY, 
            fg=self.TEXT_PRIMARY, 
            font=(self.FONT_FAMILY, 15, "bold"), 
            activebackground=self.BG_SECONDARY,
            activeforeground=self.TEXT_PRIMARY,
            relief=tk.FLAT, 
            bd=0,
            pady=6,
            command=self.cancel_sos_sim
        )
        self.sos_reset_btn.pack(fill=tk.X, padx=15, pady=(0, 15))
        
        # Golden Hour First-Aid Quick Reference Guide Pane
        self.guide_frame = tk.Frame(
            self.right_col, 
            bg=self.BG_SECONDARY, 
            highlightbackground=self.BORDER_COLOR, 
            highlightthickness=1
        )
        self.guide_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            self.guide_frame, 
            text="Golden Hour First-Aid Guide", 
            font=(self.FONT_FAMILY, 16, "bold"), 
            fg=self.TEXT_PRIMARY, 
            bg=self.BG_SECONDARY
        ).pack(anchor="w", padx=10, pady=(12, 8))

        guide_content = (
            "1. CONTROL BLEEDING: Apply direct, constant pressure to wounds using clean cloth.\n\n"
            "2. AIRWAY MANAGEMENT: Ensure air passage is unrestricted. Do not move head if neck trauma is suspected.\n\n"
            "3. SHOCK MITIGATION: Keep victim warm, comfortable, and stable. Do not administer oral fluids.\n\n"
            "4. BYSTANDER PROTECTION: Secure oncoming highway margins using hazard lights."
        )
        lbl_guide = tk.Label(
            self.guide_frame, 
            text=guide_content, 
            fg=self.TEXT_SECONDARY, 
            bg=self.BG_SECONDARY, 
            font=(self.FONT_FAMILY, 15), 
            justify=tk.LEFT, 
            anchor="w"
        )
        lbl_guide.pack(padx=10, pady=(0, 15), fill=tk.X)

        # Dynamic wrap width scaling helper to avoid empty margins on right (full-width text)
        def scale_guide_wrap(event):
            new_wrap = event.width - 20
            if new_wrap > 100:
                lbl_guide.config(wrap=new_wrap)
        lbl_guide.bind("<Configure>", scale_guide_wrap)

        # Load Initial Map parameters
        self.refresh_location_and_directory()

    def set_sos_router(self, router):
        self.router = router
        self._update_location_ui()
        self.refresh_location_and_directory()
        
    def set_obd_manager(self, obd_manager):
        self.obd_manager = obd_manager

    def _update_location_ui(self):
        if not self.router:
            return
        self.country_combo.set("India")
        # Dynamically append custom search city to selection options list
        current_cities = list(self.city_combo["values"])
        if self.router.current_city not in current_cities:
            current_cities.append(self.router.current_city)
            self.city_combo.config(values=current_cities)
        self.city_combo.set(self.router.current_city)

    def refresh_location_and_directory(self, selected_country="IN"):
        """Resolves local data parameters, updates the UI elements, and calculates proximity values."""
        loc = self.loc_service.capture_current_coordinates(self.obd_manager)
        db = fetch_offline_metadata(selected_country)
        
        # Overwrite coordinate readouts if router has modified them
        if self.router:
            loc["lat"] = self.router.current_lat
            loc["lon"] = self.router.current_lon
            loc["country"] = "IN" if self.router.current_country.upper() in ["IN", "INDIA"] else "US"
            loc["address"] = f"{self.router.current_city}, {self.router.current_country}"
        
        self.lbl_loc.config(
            text=f"Country Node: {db['country_name']} ({selected_country}) | Mode: {loc['status']} | Coordinates: {loc['lat']:.5f}, {loc['lon']:.5f}"
        )

        # Generate Automated Message payload data using shortlink compression
        mock_telemetry = {
            "speed": self.obd_manager.fetch_live_metrics()["speed"] if self.obd_manager else 70,
            "g_force": self.obd_manager.fetch_live_metrics()["g_force"] if self.obd_manager else 1.0
        }
        score = self.controller.calculate_final_score() if self.controller else 100
        sms_text = self.loc_service.compile_compressed_sms_payload(
            loc["lat"], loc["lon"], mock_telemetry, score
        )
        self.txt_msg.delete("1.0", tk.END)
        self.txt_msg.insert(tk.END, sms_text)

        # Build out the organized text matrix string structure
        self.directory_listbox.delete("1.0", tk.END)
        self.directory_listbox.insert(tk.END, f"Primary Emergency Services\nPolice: {db['services']['police']['phone']} | Medical: {db['services']['medical']['phone']}\n\n")
        
        self.directory_listbox.insert(tk.END, "Ranked Triage Facilities (Hospitals)\n")
        
        # Hospitals triage calculation
        hospitals_list = []
        if self.router:
            # Leverage our advanced triage ranking calculations
            hospitals_list = self.router.get_nearest_services("hospitals")
            for h in hospitals_list:
                self.directory_listbox.insert(tk.END, f"• [{h['distance']} KM] {h['name']} -> {h['address']} | Call: {h['phone']}\n")
        else:
            for h in db["hospitals"]:
                dist = self.loc_service.calculate_haversine_distance(loc["lat"], loc["lon"], h["lat"], h["lon"])
                self.directory_listbox.insert(tk.END, f"• [{round(dist, 1)} KM] {h['name']} -> Tier Level-{h['level']} | Core Line: {h['phone']}\n")

        self.directory_listbox.insert(tk.END, "\nHighway Towing Services\n")
        for t in db["towing"]:
            self.directory_listbox.insert(tk.END, f"• {t['name']} | Line: {t['phone']} [{t['distance_mock']}]\n")

        self.directory_listbox.insert(tk.END, "\nNearest Puncture Repair Hubs\n")
        for p in db["puncture_shops"]:
            self.directory_listbox.insert(tk.END, f"• {p['name']} | Line: {p['phone']} [{p['distance_mock']}]\n")

        self.directory_listbox.insert(tk.END, "\nOfficial Automotive Recovery Centers\n")
        for s in db["showrooms"]:
            self.directory_listbox.insert(tk.END, f"• {s['name']} | Line: {s['phone']} [{s['distance_mock']}]\n")

    def activate_sos(self):
        """Forcibly brings the RoadSOS tab to the foreground and starts emergency styling, called by controller."""
        self.notebook.select(self.tab_sos)
        self.sos_active = True
        self.alarm_banner.config(
            text="Collision signature or distress phrase detected. Proximity triage routing engaged.", 
            fg="#FFFFFF", bg=self.ACCENT_RED
        )
        self.flash_sos_loop()

    def activate_sos_emergency_mode(self):
        """Forcibly brings the RoadSOS tab to the foreground, signaling an emergency to vehicle occupants."""
        self.activate_sos()
        
        # Trigger orchestrator emergency pipeline
        if self.controller:
            self.controller.on_crash_detected()
            
        messagebox.showwarning("RoadSOS Emergency Intercept Active", "Vehicle safety logic has registered a critical incident. Proximity emergency routing pathways are now active.")

    def cancel_sos_sim(self):
        self.sos_active = False
        if self.obd_manager:
            self.obd_manager.simulated_crash = False
        self.alarm_banner.config(
            text="System Status: Nominal | Active safety monitoring in progress",
            fg=self.ACCENT_GREEN, bg="#0E2C1E"
        )
        if hasattr(self, 'triage_text'):
            self.triage_text.config(
                text="System Scanning Mode: Active monitoring via vision, speech, and OBD-II telemetry...",
                fg=self.ACCENT_GREEN
            )
        self.refresh_location_and_directory()
        messagebox.showinfo("SOS Reset", "Emergency SOS Alarm cleared. Telemetry monitoring resumed.")

    def flash_sos_loop(self):
        if not self.sos_active:
            return
            
        self.sos_flash_state = not self.sos_flash_state
        if self.sos_flash_state:
            self.alarm_banner.config(text="Critical Event: Emergency Routing Engaged", bg=self.ACCENT_RED, fg="#FFFFFF")
        else:
            self.alarm_banner.config(text="Active Emergency: Nearest Triage Centers Sorted Below", bg=self.ACCENT_AMBER, fg="#FFFFFF")
            
        self.root.after(800, self.flash_sos_loop)

    def on_country_select(self, event=None):
        # Locked strictly to India-wide routing targets
        self.country_combo.set("India")
        if self.router:
            self.router.current_country = "IN"
            cities = self.router.db["India"]["cities"]
            self.city_combo.config(values=cities)
            self.city_combo.set(cities[0])
            self.on_city_select(None)
        else:
            cities = ["Chennai", "Bengaluru", "Mumbai", "Delhi", "Kolkata", "Hyderabad", "Pune"]
            self.city_combo.config(values=cities)
            self.city_combo.set(cities[0])
            self.refresh_location_and_directory("IN")

    def on_city_select(self, event=None):
        city = self.city_combo.get()
        country_code = "IN"
        
        if self.router:
            self.router.current_city = city
            # Coordinate lookup for pre-cached override centers in India
            if "Chennai" in city:
                self.router.current_lat = 12.9910
                self.router.current_lon = 80.2420
            elif "Bengaluru" in city:
                self.router.current_lat = 12.9431
                self.router.current_lon = 77.5971
            elif "Mumbai" in city:
                self.router.current_lat = 19.0760
                self.router.current_lon = 72.8777
            elif "Delhi" in city:
                self.router.current_lat = 28.6139
                self.router.current_lon = 77.2090
            elif "Kolkata" in city:
                self.router.current_lat = 22.5726
                self.router.current_lon = 88.3639
            elif "Hyderabad" in city:
                self.router.current_lat = 17.3850
                self.router.current_lon = 78.4867
            elif "Pune" in city:
                self.router.current_lat = 18.5204
                self.router.current_lon = 73.8567
            
            self._update_location_ui()
            self.lbl_loc.config(text=f"Fetching real-time local infrastructure via OpenStreetMap...")
            self.root.update()
            
            # Retrieve Overpass nodes/ways within the surrounding area
            self.router.fetch_realtime_osm_data(self.router.current_lat, self.router.current_lon)
            
        self.refresh_location_and_directory(country_code)

    def on_location_search(self):
        query = self.search_entry.get().strip()
        if not query:
            return
            
        if self.router:
            self.lbl_loc.config(text=f"Searching coordinates for '{query}' via Nominatim...")
            self.root.update()
            
            lat, lon, city = self.router.geocode_location(query)
            if lat and lon:
                self.router.current_lat = lat
                self.router.current_lon = lon
                self.router.current_city = city or query
                
                self.lbl_loc.config(text=f"Fetching real-time local infrastructure via OpenStreetMap...")
                self.root.update()
                
                # Retrieve Overpass nodes/ways for custom queried points
                self.router.fetch_realtime_osm_data(lat, lon)
                
                self._update_location_ui()
                self.refresh_location_and_directory("IN")
                messagebox.showinfo("Location Dispatched", f"Successfully dispatched V.E.S.P.E.R. edge nodes to:\n{city or query}\nCoordinates: {lat:.4f}, {lon:.4f}")
            else:
                self.lbl_loc.config(text=f"Failed to geocode '{query}'. Fallback registry active.")
                messagebox.showerror("Geocode Error", f"Could not find coordinates for: '{query}'. Please check spelling or connectivity.")

    def on_scenario_select(self, event=None):
        scenario = self.scenario_combo.get()
        mapping = {
            "Normal Cruise": "NORMAL_CRUISE",
            "Swerving Erratic": "SWERVING_ERRATIC",
            "Hard Braking": "HARD_BRAKING",
            "Critical Side Impact": "CRITICAL_SIDE_IMPACT",
            "Normal Drive": "NONE"
        }
        preset_key = mapping.get(scenario, "NONE")
        if self.obd_manager:
            if preset_key == "NONE":
                self.obd_manager.set_scenario(None)
            else:
                self.obd_manager.set_scenario(preset_key)
                
            # If it's a critical impact scenario, trigger crash routing
            if preset_key == "CRITICAL_SIDE_IMPACT":
                self.activate_sos_emergency_mode()

    def copy_distress_msg(self):
        msg = self.txt_msg.get("1.0", tk.END).strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(msg)
        messagebox.showinfo("Clipboard", "Outbound distress message copied successfully!")

    def dial_medical_call(self):
        db = fetch_offline_metadata("IN" if self.country_combo.get() == "India" else "US")
        phone = db["services"]["medical"]["phone"]
        messagebox.showinfo("Voice Command Triage", f"Connecting vehicle occupant voice call to: {phone}")

    def dial_police_call(self):
        db = fetch_offline_metadata("IN" if self.country_combo.get() == "India" else "US")
        phone = db["services"]["police"]["phone"]
        messagebox.showinfo("Voice Command Triage", f"Connecting vehicle occupant voice call to: {phone}")

    # ------------------ Original System Integrations ------------------
    def update_attention(self, attention):
        self.last_attention = attention
        self.attention_label.config(text=f"{attention:.1f}%")
        
        if attention > 70:
            self.attention_label.config(fg=self.ACCENT_GREEN)
        elif attention > 40:
            self.attention_label.config(fg=self.ACCENT_AMBER)
        else:
            self.attention_label.config(fg=self.ACCENT_RED)
            
        self._update_attention_progress(attention)

        # Update real-time line chart (throttled to once every 15 updates to prevent lagging)
        if not hasattr(self, 'chart_update_counter'):
            self.chart_update_counter = 0
        self.chart_update_counter += 1
        
        if self.chart_update_counter % 15 == 0:
            if hasattr(self, 'controller') and self.controller and hasattr(self.controller, 'attention_scores'):
                scores = self.controller.attention_scores
            else:
                if not hasattr(self, 'temp_attention_scores'):
                    self.temp_attention_scores = []
                self.temp_attention_scores.append(attention)
                scores = self.temp_attention_scores
                
            self.update_gui_chart_frame(scores)

    def _update_attention_progress(self, attention):
        self.progress_canvas.delete("all")
        self.progress_canvas.update_idletasks()
        width = self.progress_canvas.winfo_width()
        height = self.progress_canvas.winfo_height()
        if width <= 1:
            width = 300
        if height <= 1:
            height = 25
            
        self.progress_canvas.create_rectangle(0, 0, width, height, fill=self.BG_TERTIARY, outline="")
        progress_width = int((attention / 100) * width)
        color = self.ACCENT_GREEN if attention > 70 else self.ACCENT_AMBER if attention > 40 else self.ACCENT_RED
        self.progress_canvas.create_rectangle(0, 0, progress_width, height, fill=color, outline="")
        self.progress_canvas.create_text(width//2, height//2, text=f"{attention:.1f}%", fill="#FFFFFF", font=(self.FONT_FAMILY, 12, "bold"))

    def update_drowsiness(self, alert):
        if alert == "DROWSY":
            self.drowsiness_label.config(text="Drowsiness Detected", fg=self.ACCENT_RED)
            self.status_label.config(text="Critical: Driver showing signs of drowsiness", fg=self.ACCENT_RED)
        elif alert == "WARNING":
            self.drowsiness_label.config(text="Eyes Closing", fg=self.ACCENT_AMBER)
            self.status_label.config(text="Warning: Driver's eyes are closing", fg=self.ACCENT_AMBER)
        elif alert == "SLEEPY":
            self.drowsiness_label.config(text="Sleepiness Detected", fg=self.ACCENT_AMBER)
            self.status_label.config(text="Driver is yawning", fg=self.ACCENT_AMBER)
        elif alert == "LOW_ATTENTION":
            self.drowsiness_label.config(text="Driver on Call (Low Attention)", fg=self.ACCENT_AMBER)
            self.status_label.config(text="Warning: Phone usage detected (Driver is on call!)", fg=self.ACCENT_AMBER)
        elif alert == "HANDS_OFF_WHEEL":
            self.drowsiness_label.config(text="Hands Off Wheel", fg=self.ACCENT_RED)
            self.status_label.config(text="Warning: Driver's hands are off the steering wheel", fg=self.ACCENT_RED)
        else:
            self.drowsiness_label.config(text="Attentive", fg=self.ACCENT_GREEN)
            self.status_label.config(text="Monitoring driver attention indicators...", fg=self.ACCENT_GREEN)

    def update_transcription(self, transcription):
        if transcription:
            timestamp = datetime.datetime.now().strftime("[%H:%M:%S] ")
            self.transcription_text.insert(tk.END, timestamp + transcription + "\n")
            self.transcription_text.see(tk.END)
            lines = self.transcription_text.get("1.0", tk.END).splitlines()
            if len(lines) > 30:
                self.transcription_text.delete("1.0", "2.0")

    @property
    def offensive_warning_label(self):
        """Backward-compatible alias for warning label."""
        return self.stress_warning_label

    def show_stress_warning(self, status_msg):
        """Rewrites display text configurations to reflect the active threat vector alert state."""
        self.stress_warning_label.config(
            text=f"Cognitive Stress Warning: {status_msg.upper()}",
            fg=self.TEXT_PRIMARY,
            bg=self.ACCENT_RED,
            font=(self.FONT_FAMILY, 18, "bold")
        )
        self._flash_alert(self.stress_warning_label, self.ACCENT_RED, self.BG_SECONDARY, 6)
        self.root.after(8000, self._clear_stress_warning)

    def show_offensive_warning(self, message):
        """Fallback method for backward compatibility."""
        self.show_stress_warning(message)

    def show_help_warning(self, message):
        self.help_warning_label.config(text="Voice Hook Intercept: Passenger requesting assistance", fg=self.TEXT_PRIMARY, bg=self.ACCENT_AMBER, font=(self.FONT_FAMILY, 18, "bold"))
        self._flash_alert(self.help_warning_label, self.ACCENT_AMBER, self.BG_SECONDARY, 6)
        self.root.after(8000, self._clear_help_warning)

    def _flash_alert(self, label, color1, color2, count):
        if count > 0:
            current_color = label.cget("bg")
            new_color = color1 if current_color == color2 else color2
            label.config(bg=new_color)
            self.root.after(300, self._flash_alert, label, color1, color2, count-1)

    def _clear_stress_warning(self):
        self.stress_warning_label.config(
            text="Biometric Core Active: Scanning for cognitive stress...",
            fg=self.ACCENT_PRIMARY,
            bg=self.BG_SECONDARY,
            font=(self.FONT_FAMILY, 18, "bold")
        )

    def _clear_offensive_warning(self):
        self._clear_stress_warning()

    def _clear_help_warning(self):
        self.help_warning_label.config(text="Acoustic Sensors Online: Listening for voice distress...", fg=self.ACCENT_PRIMARY, bg=self.BG_SECONDARY, font=(self.FONT_FAMILY, 18, "bold"))

    def show_final_score(self, score, rating, duration, readings, stress_count=0, offensive_count=None):
        # Handle backward compatibility parameter
        actual_stress_count = stress_count or offensive_count or 0
        
        score_window = tk.Toplevel(self.root)
        score_window.title("Driver Performance Report")
        score_window.geometry("400x350")
        score_window.configure(bg=self.BG_PRIMARY)
        score_window.resizable(False, False)
        
        score_window.transient(self.root)
        score_window.grab_set()
        
        tk.Label(score_window, text="Driver Performance Report", font=(self.FONT_FAMILY, 16, "bold"), fg=self.ACCENT_PRIMARY, bg=self.BG_PRIMARY).pack(pady=20)
        
        score_frame = tk.Frame(score_window, bg=self.BG_SECONDARY, highlightbackground=self.BORDER_COLOR, highlightthickness=1, bd=0)
        score_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Label(score_frame, text=f"Attention Score: {score}%", font=(self.FONT_FAMILY, 20, "bold"), fg=self.ACCENT_GREEN if score > 70 else self.ACCENT_RED, bg=self.BG_SECONDARY).pack(pady=10)
        tk.Label(score_frame, text=f"Rating: {rating}", font=(self.FONT_FAMILY, 12, "bold"), fg=self.TEXT_PRIMARY, bg=self.BG_SECONDARY).pack(pady=5)
        
        details_frame = tk.Frame(score_window, bg=self.BG_PRIMARY)
        details_frame.pack(fill=tk.X, padx=20, pady=10)
        tk.Label(details_frame, text=f"Ride Duration: {duration:.1f} minutes", fg=self.TEXT_SECONDARY, bg=self.BG_PRIMARY, font=(self.FONT_FAMILY, 13)).pack(pady=2)
        tk.Label(details_frame, text=f"Attention Readings: {readings}", fg=self.TEXT_SECONDARY, bg=self.BG_PRIMARY, font=(self.FONT_FAMILY, 13)).pack(pady=2)
        
        if actual_stress_count > 0:
            tk.Label(details_frame, text=f"Cognitive Stress Incidents: {actual_stress_count}", fg=self.ACCENT_RED, bg=self.BG_PRIMARY, font=(self.FONT_FAMILY, 13)).pack(pady=2)
            
        tk.Button(score_window, text="Close Report", font=(self.FONT_FAMILY, 18, "bold"), fg="white", bg=self.ACCENT_PRIMARY, relief=tk.FLAT, command=score_window.destroy).pack(pady=15)
        
        score_window.update_idletasks()
        x = (score_window.winfo_screenwidth() // 2) - (score_window.winfo_width() // 2)
        y = (score_window.winfo_screenheight() // 2) - (score_window.winfo_height() // 2)
        score_window.geometry(f"+{x}+{y}")

    def update_video(self, frame):
        self.last_frame = frame
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)
        
        window_width = self.root.winfo_width()
        window_height = self.root.winfo_height()
        
        target_width = max(320, window_width // 2 - 20)
        reserved_height = 250
        target_height = max(240, window_height - reserved_height)
        
        img_width, img_height = pil_image.size
        aspect_ratio = img_width / img_height
        
        if target_width / target_height > aspect_ratio:
            new_height = min(target_height, int(target_width / aspect_ratio))
            new_width = int(aspect_ratio * new_height)
        else:
            new_width = min(target_width, target_width)
            new_height = int(new_width / aspect_ratio)
            
        new_width = max(320, new_width)
        new_height = max(240, new_height)
        
        pil_image = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        self.photo_image = ImageTk.PhotoImage(pil_image)
        self.video_label.configure(image=self.photo_image, anchor="center")
        self.video_label.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

    def update_obd_ui(self, speed, rpm, load, g_force, status, is_simulated, dtcs):
        self.obd_speed_label.config(text=f"{speed:.1f} km/h")
        self.obd_rpm_label.config(text=f"{rpm} RPM")
        self.obd_load_label.config(text=f"{load:.1f} %")
        
        if abs(g_force) > 3.0:
            self.obd_gforce_label.config(text=f"{g_force:.2f}g (CRASH DETECTED!)", fg=self.ACCENT_RED)
        elif abs(g_force) > 1.5:
            self.obd_gforce_label.config(text=f"{g_force:.2f}g (Erratic pattern)", fg=self.ACCENT_AMBER)
        else:
            self.obd_gforce_label.config(text=f"{g_force:.2f}g (Normal)", fg=self.ACCENT_GREEN)
            
        dtcs_str = ", ".join(dtcs) if dtcs else "OK"
        dtc_color = self.ACCENT_RED if dtcs else self.ACCENT_GREEN
        self.obd_dtc_label.config(text=dtcs_str, fg=dtc_color)

    def create_road_sos_widgets(self):
        """Appends the specialized RoadSoS operational dashboard layout."""
        self.sos_display_frame = tk.LabelFrame(
            self.root, text="Incident Dispatch Core", 
            fg=self.ACCENT_PRIMARY, font=(self.FONT_FAMILY, 18, "bold"), bg=self.BG_PRIMARY,
            relief=tk.FLAT, highlightbackground=self.BORDER_COLOR, highlightthickness=1
        )
        self.sos_display_frame.pack(fill=tk.X, padx=10, pady=5, side=tk.BOTTOM)

        self.triage_text = tk.Label(
            self.sos_display_frame, 
            text="System Scanning Mode: Active monitoring via vision, speech, and OBD-II telemetry...",
            fg=self.ACCENT_GREEN, bg=self.BG_PRIMARY, font=(self.FONT_FAMILY, 15), justify=tk.LEFT, anchor="w",
            pady=5
        )
        self.triage_text.pack(fill=tk.X, padx=5, pady=5)

    def display_triage_intercept_results(self, optimal_facility, lat, lon, gsm_log=""):
        """Displays optimal triage hospital coordinates and outbound SMS transmission status."""
        trauma_desc_map = {
            1: "Level 1: PolyTrauma Hub",
            2: "Level 2: District Hospital",
            3: "Level 3: Primary Care Clinic"
        }
        level_desc = trauma_desc_map.get(optimal_facility['trauma_level'], f"Level {optimal_facility['trauma_level']}")
        
        triage_info = (
            f"Active Incident Routing Engaged\n"
            f"Nearest Capable Facility: {optimal_facility['name']} ({level_desc})\n"
            f"Distance: {optimal_facility['distance_km']} km | Beds Available: {optimal_facility['beds']}\n"
            f"Emergency Call: {optimal_facility['contact']} | Assets: {', '.join(optimal_facility['specialties'][:2])}\n"
        )
        if gsm_log:
            clean_log = gsm_log.replace("✅", "").replace("🚨", "").replace("💬", "").replace("🛰️", "").strip()
            triage_info += f"GSM Network Status: {clean_log}"
        else:
            triage_info += f"Outbound eCall Broadcast Dispatched to 112 [Coordinates: {lat:.5f}, {lon:.5f}]"
            
        self.triage_text.config(text=triage_info, fg=self.ACCENT_AMBER)

    # ------------------ Scrollbar viewport setups ------------------
    def _on_frame_configure(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        canvas_width = self.canvas.winfo_width()
        if canvas_width > 1:
            self.canvas.itemconfig(self.canvas_window, width=canvas_width)
            
        bbox = self.canvas.bbox("all")
        if bbox:
            canvas_height = self.canvas.winfo_height()
            content_height = bbox[3] - bbox[1]
            if content_height <= canvas_height:
                self.scrollbar.pack_forget()
            else:
                self.scrollbar.pack(side="right", fill="y")

    def _on_canvas_configure(self, event):
        # Stretch inner frame to match canvas width
        self.canvas.itemconfig(self.canvas_window, width=event.width)
        # Stretch height only if contents are shorter than canvas to prevent scroll collapse
        req_h = self.scrollable_frame.winfo_reqheight()
        self.canvas.itemconfig(self.canvas_window, height=event.height if req_h < event.height else "")
        # Recalculate column-wrap grids responsively
        self.adjust_responsive_layout(self.root.winfo_width())

    def _bind_scroll_events(self):
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)
        
        self.scrollable_frame.bind("<MouseWheel>", self._on_mousewheel)
        self.scrollable_frame.bind("<Button-4>", self._on_mousewheel)
        self.scrollable_frame.bind("<Button-5>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        bbox = self.canvas.bbox("all")
        if bbox and (bbox[3] - bbox[1]) > self.canvas.winfo_height():
            if event.num == 5 or event.delta < 0:
                self.canvas.yview_scroll(1, "units")
            else:
                self.canvas.yview_scroll(-1, "units")

    def embed_rolling_attention_chart(self, parent_frame):
        """Embeds an optimized, real-time matplot canvas stream inside the GUI layout."""
        if not MATPLOTLIB_AVAILABLE:
            self.chart_canvas = None
            fallback_lbl = tk.Label(
                parent_frame,
                text="Matplotlib not installed.\nReal-time chart disabled.",
                font=(self.FONT_FAMILY, 13),
                fg=self.TEXT_SECONDARY,
                bg=self.BG_SECONDARY
            )
            fallback_lbl.pack(pady=10)
            return

        self.chart_fig, self.chart_ax = plt.subplots(figsize=(4.5, 2.0), facecolor=self.BG_PRIMARY)
        self.chart_ax.set_facecolor(self.BG_SECONDARY)
        
        # Stylize matrix vectors to blend with the dark slate premium visual theme
        self.chart_ax.tick_params(colors=self.TEXT_SECONDARY, labelsize=8)
        self.chart_ax.grid(True, color=self.BORDER_COLOR, linestyle="--")
        self.chart_ax.set_ylim(0, 100)
        
        self.chart_line, = self.chart_ax.plot([], [], color=self.ACCENT_PRIMARY, linewidth=2)
        
        self.chart_canvas = FigureCanvasTkAgg(self.chart_fig, master=parent_frame)
        self.chart_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def update_gui_chart_frame(self, historical_scores):
        """Pushes rolling score coordinates onto the visual axis window frame."""
        if not MATPLOTLIB_AVAILABLE or not hasattr(self, 'chart_canvas') or self.chart_canvas is None:
            return
            
        timeline = list(range(len(historical_scores)))[-60:]  # Limit viewport to last 60 steps
        view_scores = historical_scores[-60:]
        
        self.chart_line.set_data(timeline, view_scores)
        self.chart_ax.set_xlim(max(0, len(historical_scores)-60), max(60, len(historical_scores)))
        
        try:
            self.chart_fig.canvas.draw_idle()
        except Exception:
            pass

    def _on_sos_frame_configure(self, event=None):
        self.sos_canvas.configure(scrollregion=self.sos_canvas.bbox("all"))
        canvas_width = self.sos_canvas.winfo_width()
        if canvas_width > 1:
            self.sos_canvas.itemconfig(self.sos_canvas_window, width=canvas_width)
            
        bbox = self.sos_canvas.bbox("all")
        if bbox:
            canvas_height = self.sos_canvas.winfo_height()
            content_height = bbox[3] - bbox[1]
            if content_height <= canvas_height:
                self.sos_scrollbar.pack_forget()
            else:
                self.sos_scrollbar.pack(side="right", fill="y")

    def _on_sos_canvas_configure(self, event):
        # Stretch inner frame to match canvas width
        self.sos_canvas.itemconfig(self.sos_canvas_window, width=event.width)
        # Stretch height only if contents are shorter than canvas to prevent scroll collapse
        req_h = self.scrollable_sos_frame.winfo_reqheight()
        self.sos_canvas.itemconfig(self.sos_canvas_window, height=event.height if req_h < event.height else "")
        # Recalculate column-wrap grids responsively
        self.adjust_responsive_layout(self.root.winfo_width())

    def _bind_sos_scroll_events(self):
        self.sos_canvas.bind("<MouseWheel>", self._on_sos_mousewheel)
        self.sos_canvas.bind("<Button-4>", self._on_sos_mousewheel)
        self.sos_canvas.bind("<Button-5>", self._on_sos_mousewheel)
        
        self.scrollable_sos_frame.bind("<MouseWheel>", self._on_sos_mousewheel)
        self.scrollable_sos_frame.bind("<Button-4>", self._on_sos_mousewheel)
        self.scrollable_sos_frame.bind("<Button-5>", self._on_sos_mousewheel)

    def _on_sos_mousewheel(self, event):
        bbox = self.sos_canvas.bbox("all")
        if bbox and (bbox[3] - bbox[1]) > self.sos_canvas.winfo_height():
            if event.num == 5 or event.delta < 0:
                self.sos_canvas.yview_scroll(1, "units")
            else:
                self.sos_canvas.yview_scroll(-1, "units")

    def adjust_responsive_layout(self, width):
        # --- TAB 1 Monitor Responsiveness ---
        if hasattr(self, 'video_column') and hasattr(self, 'info_column') and hasattr(self, 'content_frame'):
            self.video_column.grid_forget()
            self.info_column.grid_forget()
            if width < 900:
                # Stack vertically
                self.video_column.grid(row=0, column=0, sticky="nsew", padx=0, pady=(0, 10))
                self.info_column.grid(row=1, column=0, sticky="nsew", padx=0, pady=(10, 0))
                self.content_frame.columnconfigure(0, weight=1)
                self.content_frame.columnconfigure(1, weight=0)
            else:
                # Side-by-side
                self.video_column.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=0)
                self.info_column.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=0)
                self.content_frame.columnconfigure(0, weight=1)
                self.content_frame.columnconfigure(1, weight=1)

        # --- TAB 2 RoadSOS Responsiveness ---
        if hasattr(self, 'loc_col') and hasattr(self, 'middle_col') and hasattr(self, 'right_col') and hasattr(self, 'workspace_frame'):
            self.loc_col.grid_forget()
            self.middle_col.grid_forget()
            self.right_col.grid_forget()
            
            if width < 768:
                # 1-column layout: Stack all 3 columns vertically
                self.loc_col.grid(row=0, column=0, sticky="nsew", padx=0, pady=5)
                self.middle_col.grid(row=1, column=0, sticky="nsew", padx=0, pady=5)
                self.right_col.grid(row=2, column=0, sticky="nsew", padx=0, pady=5)
                
                self.workspace_frame.columnconfigure(0, weight=1)
                self.workspace_frame.columnconfigure(1, weight=0)
                self.workspace_frame.columnconfigure(2, weight=0)
            elif width < 1100:
                # 2-column layout: Left has loc_col and right_col, Right has middle_col
                self.loc_col.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=5)
                self.right_col.grid(row=1, column=0, sticky="nsew", padx=(0, 10), pady=5)
                self.middle_col.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(10, 0), pady=5)
                
                self.workspace_frame.columnconfigure(0, weight=1)
                self.workspace_frame.columnconfigure(1, weight=1)
                self.workspace_frame.columnconfigure(2, weight=0)
            else:
                # 3-column layout: Side-by-side
                self.loc_col.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=0)
                self.middle_col.grid(row=0, column=1, sticky="nsew", padx=10, pady=0)
                self.right_col.grid(row=0, column=2, sticky="nsew", padx=(10, 0), pady=0)
                
                self.workspace_frame.columnconfigure(0, weight=1)
                self.workspace_frame.columnconfigure(1, weight=1)
                self.workspace_frame.columnconfigure(2, weight=1)

            # Stretch row configs
            self.workspace_frame.rowconfigure(0, weight=1)
            self.workspace_frame.rowconfigure(1, weight=1)
            self.workspace_frame.rowconfigure(2, weight=1)

    def on_resize(self, event):
        if event.widget == self.root:
            if not hasattr(self, '_last_width') or self._last_width != event.width or self._last_height != event.height:
                self._last_width = event.width
                self._last_height = event.height
                self.adjust_responsive_layout(event.width)
                
            if hasattr(self, 'last_attention'):
                self.root.after_idle(self._update_attention_progress, self.last_attention)
            if hasattr(self, 'last_frame') and self.last_frame is not None:
                self.root.after_idle(self.update_video, self.last_frame)

    def show_gsm_terminal(self, log_text):
        """Displays a simulated serial monitor terminal showing AT commands sent to the GSM module."""
        term_window = tk.Toplevel(self.root)
        term_window.title("V.E.S.P.E.R. - GSM AT Serial Monitor (Simulated)")
        term_window.geometry("600x450")
        term_window.configure(bg=self.BG_PRIMARY)
        term_window.resizable(False, False)
        term_window.transient(self.root)
        
        # Heading
        tk.Label(
            term_window, 
            text="GSM AT Command Serial Console", 
            font=(self.FONT_FAMILY, 12, "bold"), 
            fg=self.ACCENT_PRIMARY, 
            bg=self.BG_PRIMARY
        ).pack(pady=10)
        
        # Scrolled Text for Console
        console = scrolledtext.ScrolledText(
            term_window, 
            wrap=tk.WORD, 
            font=("Consolas", 10),
            bg="#020204",
            fg="#00FF00",  # Classic matrix green
            insertbackground="#00FF00",
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=10
        )
        console.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 10))
        
        # Insert log text
        console.insert(tk.END, log_text)
        console.config(state=tk.DISABLED)
        
        # Close button
        tk.Button(
            term_window, 
            text="Close Console", 
            font=(self.FONT_FAMILY, 10, "bold"), 
            fg="white", 
            bg=self.ACCENT_PRIMARY, 
            relief=tk.FLAT, 
            command=term_window.destroy,
            pady=5
        ).pack(pady=10)
        
        # Center window
        term_window.update_idletasks()
        x = (term_window.winfo_screenwidth() // 2) - (term_window.winfo_width() // 2)
        y = (term_window.winfo_screenheight() // 2) - (term_window.winfo_height() // 2)
        term_window.geometry(f"+{x}+{y}")

def main():
    root = tk.Tk()
    gui = HybridAttentionSpeechGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()