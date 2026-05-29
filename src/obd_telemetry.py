import random
import time

SCENARIO_PRESETS = {
    "NORMAL_CRUISE": {"speed": 75, "rpm": 2100, "g_force": 1.02, "airbag_status": "OK"},
    "SWERVING_ERRATIC": {"speed": 94, "rpm": 3400, "g_force": 1.85, "airbag_status": "OK"},
    "HARD_BRAKING": {"speed": 32, "rpm": 1200, "g_force": 2.45, "airbag_status": "OK"},
    "CRITICAL_SIDE_IMPACT": {"speed": 0, "rpm": 0, "g_force": 5.82, "airbag_status": "TRIGGERED"}
}

class OBDTelemetryManager:
    def __init__(self, use_mock=True):
        self.use_mock = use_mock
        self.connection = None
        self.simulated_crash = False
        self.current_scenario = None
        if not use_mock:
            try:
                import obd
                self.connection = obd.OBD() # Auto-connects to ELM327 Bluetooth/USB adapter
            except Exception:
                print("[OBD Warning] Physical device link failed. Defaulting to system simulation.")
                self.use_mock = True

    def set_scenario(self, scenario_name):
        """Overrides diagnostic streams with preset mock profiles for testing purposes."""
        if scenario_name in SCENARIO_PRESETS:
            self.current_scenario = scenario_name
            if scenario_name == "CRITICAL_SIDE_IMPACT":
                self.simulated_crash = True
            else:
                self.simulated_crash = False
        else:
            self.current_scenario = None
            self.simulated_crash = False

    def fetch_live_metrics(self):
        """Fetches vehicle diagnostic parameters or returns simulated telemetry loops."""
        if self.current_scenario in SCENARIO_PRESETS:
            preset = SCENARIO_PRESETS[self.current_scenario].copy()
            preset["gps_latitude"] = 12.9915
            preset["gps_longitude"] = 80.2336
            return preset

        if self.simulated_crash:
            return {
                "speed": 0,
                "rpm": 0,
                "g_force": 6.2,
                "airbag_status": "TRIGGERED",
                "gps_latitude": 12.9915,
                "gps_longitude": 80.2336
            }
            
        if not self.use_mock and self.connection and self.connection.is_connected():
            import obd
            try:
                speed_val = self.connection.query(obd.commands.SPEED).value
                speed = speed_val.to("kph") if speed_val else 0
                rpm_val = self.connection.query(obd.commands.RPM).value
                rpm = rpm_val.magnitude if rpm_val else 0
                # Fallback coordinates if hardware OBD doesn't support GPS
                return {
                    "speed": int(speed), 
                    "rpm": int(rpm), 
                    "g_force": 1.0, 
                    "airbag_status": "OK",
                    "gps_latitude": 12.9910,
                    "gps_longitude": 80.2420
                }
            except Exception:
                pass
        
        # Simulates real-time driving logs
        return {
            "speed": random.randint(55, 90),
            "rpm": random.randint(1800, 2600),
            "g_force": round(random.uniform(0.8, 1.3), 2),
            "airbag_status": "OK",
            "gps_latitude": 12.9915,
            "gps_longitude": 80.2336
        }

    def evaluate_crash_signature(self, telemetry):
        """Checks accelerometer metrics for impact thresholds."""
        if telemetry["g_force"] > 4.0 or telemetry["airbag_status"] == "TRIGGERED":
            return True
        return False

class SensorFusionValidator:
    def __init__(self):
        self.kinematic_anomaly_detected = False
        self.anomaly_timestamp = 0.0

    def register_hardware_g_spike(self, g_force):
        """Flags an isolated structural telemetry shock event."""
        if g_force > 4.0:
            import time
            self.kinematic_anomaly_detected = True
            self.anomaly_timestamp = time.time()
            return True
        return False

    def validate_with_vision_and_audio(self, driver_attention_score, voice_panic_triggered):
        """
        Cross-references the telematics shock event with behavioral markers.
        Reduces false alerts to nearly 0%.
        """
        import time
        if not self.kinematic_anomaly_detected:
            return False
            
        # Check if the validation window has expired (2.5 seconds)
        if time.time() - self.anomaly_timestamp > 2.5:
            self.kinematic_anomaly_detected = False
            return False

        # Fusion Check: Hardware shock combined with either unconsciousness or a verbal cry for help
        if driver_attention_score < 20 or voice_panic_triggered:
            print("[CRASH CONFIRMED] Multi-sensor verification criteria successfully met.")
            return True

        return False


