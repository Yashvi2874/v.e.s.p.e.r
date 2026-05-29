import cv2
import threading
import time

class HighPerformanceStreamReader:
    def __init__(self, source=0, resolution=(640, 480)):
        self.stream = cv2.VideoCapture(source)
        self.stream.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
        self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
        
        # Clear frame buffer lag by grabbing the latest frame asynchronously
        self.grabbed, self.frame = self.stream.read()
        self.stopped = False
        self.lock = threading.Lock()

    def start(self):
        """Spawns an independent background thread dedicated entirely to reading hardware frames."""
        t = threading.Thread(target=self.update_frame_loop, args=(), daemon=True)
        t.start()
        return self

    def update_frame_loop(self):
        while not self.stopped:
            grabbed, frame = self.stream.read()
            if not grabbed:
                self.stop()
                break
            with self.lock:
                self.grabbed = grabbed
                self.frame = frame
            # Micro-sleep to prevent CPU core starvation
            time.sleep(0.01)

    def read_latest_frame(self):
        """Returns the single freshest frame currently in memory with zero buffer queue delay."""
        with self.lock:
            return self.frame.copy() if self.grabbed else None

    def stop(self):
        self.stopped = True
        self.stream.release()

class VideoCapture(HighPerformanceStreamReader):
    def __init__(self, source=0, resolution=(640, 480)):
        super().__init__(source, resolution)
        self.start()

    def get_frame(self):
        return self.read_latest_frame()

    def release(self):
        self.stop()

# Test function
def main():
    video_capture = VideoCapture()
    while True:
        frame = video_capture.get_frame()
        if frame is None:
            break
        cv2.imshow("Webcam Feed", frame)  # Display the frame
        if cv2.waitKey(1) & 0xFF == 27:  # ESC to quit
            break
    video_capture.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()