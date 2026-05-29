import cv2
import threading
from gui import HybridAttentionSpeechGUI
from video import VideoCapture
from audio import SpeechRecognizer
from detection import detect_attention_and_drowsiness
from obd_telemetry import OBDTelemetryManager, SensorFusionValidator
from sos_router import SOSRouter
import tkinter as tk
import os
import time

# Main application class
class HybridAttentionSpeechApp:
    def __init__(self):
        self.video_stream = VideoCapture()
        
        # Help-related phrases that trigger alerts
        help_phrases = [
            "help", "police", "stop the car", "stop car", "emergency", 
            "danger", "call police", "get help", "need help", "help me",
            "pull over", "stop the vehicle", "emergency stop", "dangerous",
            "unsafe", "scared", "afraid", "threat", "assault", "harassment"
        ]
        
        # Initialize SOS Router & GPS Location tracking
        self.sos_router = SOSRouter()
        
        # Initialize OBD-II vehicle telemetry and Sensor Fusion confirmation
        self.obd_manager = OBDTelemetryManager(use_mock=True)
        self.sensor_fusion = SensorFusionValidator()
        
        # Initialize speech recognizer with voice SOS callback and stress monitoring
        self.speech_recognizer = SpeechRecognizer(
            stress_markers=[
                "stop", "move", "watch out", "crazy", "get out", "hit"
            ],
            help_words=help_phrases,
            webhook_url=os.environ.get("OFFENSIVE_ALERT_WEBHOOK"),
            phrase_time_limit=3,
            silence_flush_sec=0.8,
            fuzzy_threshold=0.75,
            alert_cooldown=60,
            controller_instance=self,
            sos_callback=self.on_voice_sos_detected
        )
        self.speech_recognizer.start()
        
        # Create GUI
        self.root = tk.Tk()
        self.gui = HybridAttentionSpeechGUI(self.root)
        
        # Inject dependencies into GUI
        self.gui.set_sos_router(self.sos_router)
        self.gui.set_obd_manager(self.obd_manager)
        
        # Control flag
        self.running = True
        
        # Track last displayed sentence to avoid duplicates
        self.last_displayed_sentence = ""
        
        # Driver scoring system
        self.attention_scores = [100]  # Rolling score timeline history
        self.ride_start_time = time.time()  # Track when the ride started
        self.ride_end_time = None  # Track when the ride ended
        self.behavioral_stress_count = 0  # Track stress marker detections
        self.current_attention_score = 95
        
        # Track if we've shown alerts to prevent continuous display
        self.stress_alert_shown = False
        self.help_alert_shown = False

    @property
    def offensive_language_count(self):
        """Fallback property tracking configuration to prevent core crashes."""
        return self.behavioral_stress_count

    def reduce_attention_score_from_distraction(self, penalty=10):
        """
        Applies an immediate, data-driven reduction to the live attention matrix.
        Triggered when vision or audio layers record a high cognitive strain marker.
        """
        print(f"[Safety Control Hook] Applying distraction penalty: -{penalty} points.")
        self.behavioral_stress_count += 1
        
        # Calculate real-time deduction bounds safely
        self.current_attention_score = max(0, self.current_attention_score - penalty)
        self.attention_scores.append(self.current_attention_score)
        
        # Push immediate structural updates onto the active UI elements
        if hasattr(self, 'gui') and self.gui:
            self.gui.show_stress_warning(f"Cognitive Strain Detected (Incident #{self.behavioral_stress_count})")

    # Process video stream
    def start_video_stream(self):
        while self.running:
            frame = self.video_stream.get_frame()
            if frame is not None:
                # Process frame and get attention score, drowsiness alert, and yawning status
                result = detect_attention_and_drowsiness(frame, self.speech_recognizer)
                
                # Handle both old and new return value formats
                if len(result) == 4:
                    processed_frame, attention_score, drowsiness_alert, yawning_detected = result
                else:
                    # Old format (3 values)
                    processed_frame, attention_score, drowsiness_alert = result
                    yawning_detected = False
                
                # Store attention score for final calculation
                self.attention_scores.append(attention_score)
                
                # Update GUI with attention and drowsiness data (thread-safely)
                self.root.after(0, self.gui.update_attention, attention_score)
                self.root.after(0, self.gui.update_drowsiness, drowsiness_alert)
                
                # Read live vehicle telemetry
                telemetry = self.obd_manager.fetch_live_metrics()
                
                # Sensor Fusion Check: Validate isolated G-force spikes against driver status indicators
                g_force = telemetry.get("g_force", 1.0)
                self.sensor_fusion.register_hardware_g_spike(g_force)
                
                airbag_triggered = telemetry.get("airbag_status") == "TRIGGERED"
                voice_panic_triggered = self.speech_recognizer.help_detected
                
                if airbag_triggered or self.sensor_fusion.validate_with_vision_and_audio(attention_score, voice_panic_triggered):
                    self.on_crash_detected()
                    
                # Update live vehicle telemetry (thread-safely)
                load_val = float(telemetry["rpm"] / 4000.0 * 100.0) if telemetry["rpm"] > 0 else 0.0
                status_str = "Simulating" if self.obd_manager.use_mock else "Connected (Hardware)"
                dtcs_val = ["Airbag deployed"] if telemetry["airbag_status"] == "TRIGGERED" else []
                self.root.after(0, self.gui.update_obd_ui, 
                    telemetry["speed"],
                    telemetry["rpm"],
                    load_val,
                    telemetry["g_force"],
                    status_str,
                    self.obd_manager.use_mock,
                    dtcs_val
                )
                
                # Update video display in GUI (thread-safely)
                self.root.after(0, self.gui.update_video, processed_frame)
                
                # Prevent CPU core starvation
                time.sleep(0.01)
            
            # Use a shorter wait time for more responsive UI
            # Check for ESC key press without displaying separate window
            key = cv2.waitKey(1) & 0xFF
            if key == 27:  # ESC to quit
                self.running = False
                break

    # Process audio transcription
    def start_audio_transcription(self):
        while self.running:
            # The speech recognizer updates its attributes automatically
            # We just need to read them and update the GUI
            speech_text = self.speech_recognizer.speech_text or self.speech_recognizer.partial_text or ""
            help_detected = self.speech_recognizer.help_detected
            
            # Only update GUI if we have a new sentence
            if speech_text and speech_text != self.last_displayed_sentence:
                # Update GUI with transcription data
                self.gui.update_transcription(speech_text)
                self.last_displayed_sentence = speech_text
                
            if help_detected:
                # Show help alert every time it's detected
                self.gui.show_help_warning("PASSENGER ASKING FOR HELP!")
            
            # Small delay to prevent excessive CPU usage
            cv2.waitKey(50)

    # Calculate final driver score
    def calculate_final_score(self):
        if not self.attention_scores:
            return 0.0
        
        # Calculate average attention score
        avg_score = sum(self.attention_scores) / len(self.attention_scores)
        
        # Apply penalty for cognitive stress markers
        # Each cognitive stress detection reduces the score by 5 points
        stress_penalty = min(self.behavioral_stress_count * 5, 30)  # Max penalty of 30 points
        adjusted_score = max(0, avg_score - stress_penalty)
        
        # Calculate ride duration in minutes
        if self.ride_end_time:
            ride_duration = (self.ride_end_time - self.ride_start_time) / 60
        else:
            ride_duration = (time.time() - self.ride_start_time) / 60
        
        return round(adjusted_score, 1)

    # Get driver rating description
    def get_driver_rating(self, score):
        if score >= 90:
            return "Excellent"
        elif score >= 80:
            return "Very Good"
        elif score >= 70:
            return "Good"
        elif score >= 60:
            return "Average"
        elif score >= 50:
            return "Below Average"
        else:
            return "Poor"

    def dispatch_gsm_sms(self, phone_number, message):
        """Dispatches SMS via connected GSM hardware AT commands over serial, or falls back to system emulation."""
        print(f"[GSM Dispatcher] Attempting automated SMS transmission to {phone_number}...")
        
        # Log message showing GSM send status to render on bottom status bar
        log_msg = f"[GSM Module] Sending dispatch SMS payload to {phone_number}...\n"
        
        gsm_connected = False
        try:
            import serial
            # Scan COM ports 1-9 and standard Linux dev files
            ports_to_check = [f"COM{i}" for i in range(1, 10)] + [f"/dev/ttyUSB{i}" for i in range(5)] + [f"/dev/ttyACM{i}" for i in range(5)]
            for port in ports_to_check:
                try:
                    ser = serial.Serial(port, baudrate=9600, timeout=1.0)
                    ser.write(b"AT\r\n")
                    time.sleep(0.5)
                    response = ser.read(ser.in_waiting or 100).decode('utf-8', errors='ignore')
                    if "OK" in response:
                        # Connected SIM800/SIM900 shield found
                        ser.write(b"AT+CMGF=1\r\n")  # Text mode
                        time.sleep(0.5)
                        ser.write(f'AT+CMGS="{phone_number}"\r\n'.encode('utf-8'))
                        time.sleep(0.5)
                        ser.write(f"{message}\x1a".encode('utf-8'))  # Send Ctrl+Z to submit SMS
                        time.sleep(1.0)
                        ser.close()
                        gsm_connected = True
                        log_msg += f"✅ GSM HARDWARE SUCCESS: Sent via modem on {port}!\n"
                        print(f"[GSM Hardware] SMS successfully sent via {port}")
                        break
                    ser.close()
                except Exception:
                    continue
        except Exception as e:
            print(f"[GSM Warning] Hardware serial port scan failed: {e}")
            
        if not gsm_connected:
            log_msg += f"🛰️ GSM HARDWARE EMULATOR: GSM Shield offline. Broadcast simulated via fallback routing.\n"
            log_msg += f"💬 Payload: \"{message}\"\n"
            print(f"[GSM Emulation] Offline fallback active. Payload: {message}")
            
        return log_msg

    # Crash event handler
    def on_crash_detected(self):
        print("[RoadSOS] Crash telemetry alert received!")
        self.gui.activate_sos()
        
        # Poll coordinates and latest diagnostics
        telemetry = self.obd_manager.fetch_live_metrics()
        lat = self.sos_router.current_lat
        lon = self.sos_router.current_lon
        
        # Build outbound SMS payload using shortlink compression
        msg_payload = self.sos_router.location_service.compile_compressed_sms_payload(
            lat, lon, telemetry, self.calculate_final_score()
        )
        
        # Trigger automated SMS via GSM hardware/simulation
        gsm_log = self.dispatch_gsm_sms("112", msg_payload)
        
        # Calculate optimal triage hospital using crash speed velocity
        speed = telemetry.get("speed", 0)
        hospitals = self.sos_router.run_triage_routing(lat, lon, crash_velocity=speed, severity="critical")
        if hospitals:
            optimal_hospital = hospitals[0]
            self.gui.display_triage_intercept_results(
                optimal_hospital, 
                lat, 
                lon,
                gsm_log=gsm_log
            )
        
    # Voice SOS event handler
    def on_voice_sos_detected(self):
        print("[RoadSOS] Passenger distress phrase recognized!")
        self.gui.activate_sos()
        
        # Poll coordinates and latest diagnostics
        telemetry = self.obd_manager.fetch_live_metrics()
        lat = self.sos_router.current_lat
        lon = self.sos_router.current_lon
        
        # Build outbound SMS payload using shortlink compression
        msg_payload = self.sos_router.location_service.compile_compressed_sms_payload(
            lat, lon, telemetry, self.calculate_final_score()
        )
        
        # Trigger automated SMS via GSM hardware/simulation
        gsm_log = self.dispatch_gsm_sms("112", msg_payload)
        
        # Calculate optimal triage hospital using crash speed velocity
        speed = telemetry.get("speed", 0)
        hospitals = self.sos_router.run_triage_routing(lat, lon, crash_velocity=speed, severity="critical")
        if hospitals:
            optimal_hospital = hospitals[0]
            self.gui.display_triage_intercept_results(
                optimal_hospital, 
                lat, 
                lon,
                gsm_log=gsm_log
            )



    # Run the application
    def run(self):
        try:
            # Start video processing in a separate thread
            video_thread = threading.Thread(target=self.start_video_stream)
            video_thread.daemon = True
            video_thread.start()
            
            # Start audio processing in a separate thread
            audio_thread = threading.Thread(target=self.start_audio_transcription)
            audio_thread.daemon = True
            audio_thread.start()
            
            # Run GUI in main thread
            self.root.mainloop()
        finally:
            # Clean up when GUI is closed
            self.running = False
            self.ride_end_time = time.time()  # Mark ride end time
            final_score = self.calculate_final_score()
            driver_rating = self.get_driver_rating(final_score)
            ride_duration = (self.ride_end_time - self.ride_start_time) / 60
            readings = len(self.attention_scores)
            
            try:
                self.gui.show_final_score(final_score, driver_rating, ride_duration, readings, self.behavioral_stress_count)
            except:
                # Fallback to console if GUI is already closed
                pass
            
            # Print final score to console
            print(f"\n--- Ride Summary ---")
            print(f"Final Driver Attention Score: {final_score}%")
            print(f"Driver Rating: {driver_rating}")
            print(f"Ride Duration: {ride_duration:.1f} minutes")
            print(f"Total Attention Readings: {readings}")
            
            self.speech_recognizer.stop()
            self.video_stream.release()

# Main entry point
if __name__ == "__main__":
    app = HybridAttentionSpeechApp()
    app.run()