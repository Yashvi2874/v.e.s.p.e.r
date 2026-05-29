import threading
import time
import re
import requests
import difflib
import os
from datetime import datetime
import numpy as np
import json

try:
    from vosk import Model, KaldiRecognizer
    VOSK_AVAILABLE = True
except Exception:
    VOSK_AVAILABLE = False


# Import speech recognition library
try:
    import speech_recognition as sr
    SPEECH_RECOGNITION_AVAILABLE = True
except Exception:
    sr = None
    SPEECH_RECOGNITION_AVAILABLE = False

# Speech recognizer class
class SpeechRecognizer:
    """
    Buffered background recognizer that accumulates chunks into sentences,
    uses regex + fuzzy matching to detect offensive/unsafe phrases and
    posts a rate-limited webhook alert.
    Public attributes:
      - speech_text: last completed sentence (str)
      - partial_text: last partial chunk (str)
      - offensive_detected: bool
      - help_detected: bool
    """
    def __init__(self, stress_markers=None, help_words=None, webhook_url=None,
                 phrase_time_limit=3, silence_flush_sec=0.8,
                 fuzzy_threshold=0.75, alert_cooldown=60, controller_instance=None, sos_callback=None, offensive_words=None):
        self.controller = controller_instance
        self.controller_instance = controller_instance
        
        # Re-framed safety markers replacing legacy word filters
        default_markers = ["stop", "move", "watch out", "crazy", "get out", "hit"]
        self.stress_markers = [w.strip().lower() for w in (stress_markers or offensive_words or default_markers) if w.strip()]
        
        self.help_words = [w.strip().lower() for w in (help_words or []) if w.strip()]
        self.help_phrases = self.help_words
        self.sos_callback = sos_callback
        
        self._help_regexes = [re.compile(r"\b" + re.escape(p) + r"\b", re.IGNORECASE) for p in self.help_words]
        self.webhook_url = webhook_url
        self.phrase_time_limit = phrase_time_limit
        self.silence_flush_sec = silence_flush_sec
        self.fuzzy_threshold = fuzzy_threshold
        self.alert_cooldown = alert_cooldown

        # Offline acoustic amplitude spike tracker settings
        self.amplitude_threshold = 0.18  # Calibrated for in-cabin scream signatures
        self.vosk_initialized = False
        
        if VOSK_AVAILABLE:
            try:
                # Expecting a tiny local model folder like 'model' in workspace
                if os.path.exists("model"):
                    self.model = Model("model")
                    self.rec = KaldiRecognizer(self.model, 16000)
                    self.vosk_initialized = True
                    print("[Acoustic Config] Vosk offline language model loaded successfully.")
                else:
                    self.model = None
                    self.rec = None
                    print("[Acoustic Config] Vosk model directory ('model') not found. Using Google fallback.")
            except Exception as e:
                self.model = None
                self.rec = None
                print(f"[Acoustic Config Warning] Vosk setup failed: {e}. Using Google fallback.")
        else:
            self.model = None
            self.rec = None

        if SPEECH_RECOGNITION_AVAILABLE and sr is not None:
            self.r = sr.Recognizer()
            self.mic = sr.Microphone()
        else:
            self.r = None
            self.mic = None

        self.speech_text = ""
        self.partial_text = ""
        self.stress_detected = False
        self.help_detected = False

        self._buffer = []
        self._lock = threading.Lock()
        self._flush_timer = None
        self._stop_listening = None
        self._last_alert_time = 0.0
        self._last_help_alert_time = 0.0
        
        # Initialize safety audit log file
        self.log_file = "data/safety_audit_log.txt"
        self._initialize_log_file()
    
    # Initialize log file with header
    def _initialize_log_file(self):
        try:
            if os.path.dirname(self.log_file):
                os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
            if not os.path.exists(self.log_file):
                with open(self.log_file, 'w') as f:
                    f.write("Timestamp,Type,Context\n")
        except Exception as e:
            print(f"[Acoustic Config Warning] Could not initialize safety log: {e}")

    @property
    def offensive_detected(self):
        """Backward-compatible alias for the controller core loop."""
        return self.stress_detected

    @offensive_detected.setter
    def offensive_detected(self, value):
        self.stress_detected = value

    # Send alert via webhook
    def _alert_webhook(self, sentence, event_type="behavioral_stress"):
        now = time.time()
        if not self.webhook_url:
            return
        # Use different cooldowns for different alert types
        last_alert_time = self._last_alert_time if event_type == "behavioral_stress" else self._last_help_alert_time
        if now - last_alert_time < self.alert_cooldown:
            return
        try:
            payload = {"event": event_type, "text": sentence, "timestamp": now}
            requests.post(self.webhook_url, json=payload, timeout=3)
            if event_type == "behavioral_stress":
                self._last_alert_time = now
            else:
                self._last_help_alert_time = now
        except Exception:
            pass

    def process_transcribed_chunk(self, text):
        """Evaluates incoming cabin audio for cognitive load anomalies."""
        cleaned_text = text.lower()
        print(f"[Acoustic Input] Parsing: {cleaned_text}")
        
        # Look for behavioral stress indicators
        matched_markers = []
        for marker in self.stress_markers:
            if re.search(r'\b' + re.escape(marker) + r'\b', cleaned_text):
                matched_markers.append(marker)
            else:
                # Fuzzy matching fallback
                ratio = difflib.SequenceMatcher(None, marker, cleaned_text).ratio()
                if ratio >= self.fuzzy_threshold:
                    matched_markers.append(marker)
        
        if matched_markers:
            print(f"[Acoustic Anomaly] High cognitive load markers detected: {matched_markers}")
            self.stress_detected = True
            
            # Fire safety-first incident logger
            self.log_high_cognitive_stress_incident(text)
        else:
            self.stress_detected = False

    def write_to_safety_log(self, timestamp, log_type=None, context=None, type=None):
        """Saves data to a security ledger file instead of a baseline text log."""
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        file_exists = os.path.exists(self.log_file)
        
        final_log_type = log_type or type or "INFO"
        final_context = context or ""
        
        try:
            with open(self.log_file, "a") as f:
                if not file_exists:
                    f.write("Timestamp,Type,Context\n")
                clean_context = final_context.replace('"', '""').strip()
                f.write(f'"{timestamp}","{final_log_type}","{clean_context}"\n')
        except Exception as e:
            print(f"[Acoustic Logging Warning] Failed writing to safety audit log: {e}")

    # Flush buffer and check for stress or help content
    def _flush_buffer(self):
        with self._lock:
            if not self._buffer:
                return
            sentence = " ".join(self._buffer).strip()
            self._buffer = []
            self.partial_text = ""
            self.speech_text = sentence

            # Process cognitive stress markers
            self.process_transcribed_chunk(sentence)

            # Help request detection
            lower = sentence.lower()
            help_detected = False

            # 1) regex exact match
            for rx in self._help_regexes:
                if rx.search(sentence):
                    help_detected = True
                    break

            # 2) substring/token check
            if not help_detected and self.help_words:
                tokens = re.findall(r"\w+", lower)
                for phrase in self.help_words:
                    if " " in phrase:
                        if phrase in lower:
                            help_detected = True
                            break
                    else:
                        if phrase in tokens:
                            help_detected = True
                            break

            # 3) fuzzy fallback
            if not help_detected and self.help_words:
                for phrase in self.help_words:
                    ratio = difflib.SequenceMatcher(None, phrase, lower).ratio()
                    if ratio >= self.fuzzy_threshold:
                        help_detected = True
                        break

            if help_detected and not self.help_detected:
                self._alert_webhook(sentence, "help_requested")
                print("[Voice Hook Alert] Emergency phrase intercepted inside the vehicle cabin!")
                if self.sos_callback:
                    self.sos_callback()
                elif self.controller_instance:
                    if hasattr(self.controller_instance, 'check_and_execute_emergency_pipeline'):
                        self.controller_instance.check_and_execute_emergency_pipeline(routing_severity="critical")
                    elif hasattr(self.controller_instance, 'on_voice_sos_detected'):
                        self.controller_instance.on_voice_sos_detected()

            self.help_detected = help_detected
    
    def get_current_timestamp(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def log_high_cognitive_stress_incident(self, verbal_context):
        """
        Logs severe acoustic stress events within the passenger cabin.
        High verbal stress indicators are flags for impending distraction risks.
        """
        timestamp = self.get_current_timestamp()
        # Saves parameters directly to an objective safety audit trail log
        self.write_to_safety_log(timestamp, type="BEHAVIORAL_STRESS_ANOMALY", context=verbal_context)
        
        # Apply a reduction to the attention score because of behavioral distraction, not a "punishment"
        if self.controller and hasattr(self.controller, 'reduce_attention_score_from_distraction'):
            self.controller.reduce_attention_score_from_distraction(penalty=10)

    # Schedule buffer flush
    def _schedule_flush(self):
        if self._flush_timer and self._flush_timer.is_alive():
            try:
                self._flush_timer.cancel()
            except Exception:
                pass
        self._flush_timer = threading.Timer(self.silence_flush_sec, self._flush_buffer)
        self._flush_timer.daemon = True
        self._flush_timer.start()

    # Callback function for speech recognition
    def _callback(self, recognizer, audio):
        if not SPEECH_RECOGNITION_AVAILABLE or self.r is None:
            return

        # 1. Offline RMS Amplitude Spike Check (Panic/Scream Tracking)
        try:
            raw_bytes = audio.get_raw_data(convert_rate=16000, convert_width=2)
            audio_data = np.frombuffer(raw_bytes, dtype=np.int16)
            if len(audio_data) > 0:
                audio_float = audio_data.astype(np.float32) / 32768.0
                rms = np.sqrt(np.mean(audio_float**2))
                if rms > self.amplitude_threshold:
                    print(f"[Acoustic Alert] High-decibel vocal panic spike detected! RMS: {rms:.4f}")
                    if self.sos_callback:
                        self.sos_callback()
                    elif self.controller:
                        if hasattr(self.controller, 'on_voice_sos_detected'):
                            self.controller.on_voice_sos_detected()
        except Exception as e:
            print(f"[Acoustic Error] Offline RMS check error: {e}")

        # 2. Transcribe voice data (Offline Vosk with Online Google fallback)
        text = ""
        transcription_done = False
        
        if self.vosk_initialized and self.rec:
            try:
                # Convert raw data for Vosk
                raw_bytes_16k = audio.get_raw_data(convert_rate=16000, convert_width=2)
                if self.rec.AcceptWaveform(raw_bytes_16k):
                    res = json.loads(self.rec.Result())
                    text = res.get("text", "")
                    transcription_done = True
            except Exception as e:
                print(f"[Acoustic Config Warning] Vosk local decoding failed: {e}")

        if not transcription_done:
            try:
                text = recognizer.recognize_google(audio)
            except Exception:
                return

        if not text:
            return

        with self._lock:
            self._buffer.append(text)
            self.partial_text = text
            # For more immediate feedback, we'll also update speech_text immediately for single words
            if len(self._buffer) == 1:
                self.speech_text = text
            # schedule flush after silence
            self._schedule_flush()

    # Start speech recognition
    def start(self):
        if not SPEECH_RECOGNITION_AVAILABLE or self.r is None or self.mic is None:
            print("SpeechRecognition not available; speech disabled.")
            return
        # ambient calibration
        try:
            with self.mic as source:
                self.r.adjust_for_ambient_noise(source, duration=1)
        except Exception:
            pass

        self._stop_listening = self.r.listen_in_background(
            self.mic, self._callback, phrase_time_limit=self.phrase_time_limit
        )

    # Stop speech recognition
    def stop(self):
        if self._stop_listening:
            try:
                self._stop_listening(wait_for_stop=False)
            except Exception:
                pass
            self._stop_listening = None
        if self._flush_timer and self._flush_timer.is_alive():
            try:
                self._flush_timer.cancel()
            except Exception:
                pass
        # flush remaining
        self._flush_buffer()