"""
Live Camera RTSP Stream Processing Service
Handles real-time video feeds from IP cameras via RTSP protocol
Detects anomalies in real-time using YOLO + classifier
"""
import cv2
import threading
import time
import logging
from datetime import datetime
from typing import Dict, Optional, List
from queue import Queue
import numpy as np
from anomaly_engine.detector import get_detector
from anomaly_engine.anomaly_classifier import Anomaly
from database.connection import get_db
from models.anomaly import log_anomaly

logger = logging.getLogger(__name__)


class StreamBuffer:
    """Thread-safe buffer for storing latest frames and detections"""
    def __init__(self, max_frames=30):
        self.frames = Queue(maxsize=max_frames)
        self.latest_frame = None
        self.latest_detections = None
        self.latest_anomalies = []
        self.lock = threading.Lock()
        self.fps = 0
        self.frame_count = 0
        self.dropped_frames = 0
        
    def add_frame(self, frame):
        try:
            if self.frames.full():
                self.frames.get_nowait()  # Drop oldest
                self.dropped_frames += 1
            self.frames.put_nowait(frame)
            with self.lock:
                self.latest_frame = frame.copy() if frame is not None else None
        except Exception as e:
            logger.error(f"Error adding frame to buffer: {e}")
    
    def get_latest_frame(self):
        with self.lock:
            return self.latest_frame.copy() if self.latest_frame is not None else None
    
    def update_detections(self, detections, anomalies):
        with self.lock:
            self.latest_detections = detections
            self.latest_anomalies = anomalies
    
    def get_status(self):
        with self.lock:
            return {
                "fps": self.fps,
                "frame_count": self.frame_count,
                "dropped_frames": self.dropped_frames,
                "buffer_size": self.frames.qsize(),
                "anomaly_count": len(self.latest_anomalies)
            }


class RTSPStreamReader:
    """
    Handles RTSP stream reading with automatic reconnection
    Supports various IP camera formats (Hikvision, Axis, Dahua, generic)
    """
    
    # Common RTSP URL patterns for different camera brands
    RTSP_PATTERNS = {
        "hikvision": "rtsp://{user}:{password}@{host}:{port}/Streaming/Channels/101/",
        "axis": "rtsp://{user}:{password}@{host}:{port}/axis-media/media.amp",
        "dahua": "rtsp://{user}:{password}@{host}:{port}/cam/realmonitor?channel=1&subtype=0",
        "generic": "rtsp://{user}:{password}@{host}:{port}/stream"
    }
    
    def __init__(self, camera_url: str, max_retries=5, retry_delay=5):
        """
        Args:
            camera_url: RTSP URL (e.g., rtsp://admin:pass@192.168.1.100:554/stream)
            max_retries: Max reconnection attempts
            retry_delay: Seconds between reconnection attempts
        """
        self.camera_url = camera_url
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.cap = None
        self.is_connected = False
        self.last_frame = None
        self.frame_width = None
        self.frame_height = None
        self.fps = 30  # default
        
    def connect(self) -> bool:
        """Attempt to connect to RTSP stream with retries.

        Also supports a plain webcam device index (e.g. "0") instead of a
        real RTSP URL, so this same pipeline can be tested on a laptop
        webcam without owning an actual IP camera.
        """
        # If the "url" is just a number, treat it as a local webcam index
        # (OpenCV needs an int here, not a string, for device indices).
        source = int(self.camera_url) if self.camera_url.strip().isdigit() else self.camera_url

        for attempt in range(self.max_retries):
            try:
                logger.info(f"Connecting to stream (attempt {attempt + 1}/{self.max_retries}): {self._mask_url()}")

                self.cap = cv2.VideoCapture(source)
                
                # Set optimizations for streaming
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimal buffering
                self.cap.set(cv2.CAP_PROP_FPS, 30)
                
                # Wait for first frame with timeout
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    self.frame_height, self.frame_width = frame.shape[:2]
                    self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
                    self.last_frame = frame
                    self.is_connected = True
                    logger.info(f"✓ Connected to RTSP stream: {self.frame_width}x{self.frame_height} @ {self.fps} FPS")
                    return True
                else:
                    logger.warning(f"Failed to read frame from stream")
                    self.cap.release()
                    self.cap = None
                    
            except Exception as e:
                logger.error(f"Connection attempt {attempt + 1} failed: {e}")
                if self.cap:
                    self.cap.release()
                    self.cap = None
            
            if attempt < self.max_retries - 1:
                time.sleep(self.retry_delay)
        
        logger.error(f"Failed to connect after {self.max_retries} attempts")
        self.is_connected = False
        return False
    
    def read_frame(self) -> Optional[np.ndarray]:
        """
        Read next frame from stream
        Returns None if stream is disconnected
        """
        if not self.is_connected or self.cap is None:
            return None
        
        try:
            ret, frame = self.cap.read()
            if ret and frame is not None:
                self.last_frame = frame
                return frame
            else:
                logger.warning("Stream ended or frame read failed")
                self.is_connected = False
                return None
        except Exception as e:
            logger.error(f"Error reading frame: {e}")
            self.is_connected = False
            return None
    
    def disconnect(self):
        """Clean disconnect from stream"""
        if self.cap:
            self.cap.release()
            self.cap = None
        self.is_connected = False
        logger.info("Disconnected from RTSP stream")
    
    def _mask_url(self) -> str:
        """Return URL with credentials masked for logging"""
        if "@" in self.camera_url:
            proto, rest = self.camera_url.split("://", 1)
            creds, host = rest.split("@", 1)
            return f"{proto}://***:***@{host}"
        return self.camera_url


class LiveCameraProcessor(threading.Thread):
    """
    Main live camera processing thread
    Reads frames, runs detection, stores results

    FIXED: __init__, run(), and stop() were previously sitting at module
    level (not indented inside this class), so LiveCameraProcessor had no
    working constructor or run loop of its own - it silently fell back to
    threading.Thread's defaults, meaning no RTSP camera ever actually
    processed a frame, and calling .stop() raised AttributeError.
    """

    def __init__(self, camera_id: str, stream_reader: RTSPStreamReader, owner_id: str = None):
        super().__init__(daemon=True)
        self.camera_id = camera_id
        self.stream_reader = stream_reader
        self.owner_id = owner_id
        self.yolo_detector = None
        self.classifier = None
        self.buffer = StreamBuffer()
        self.running = False
        self.frame_skip = 2
        self.frame_count = 0
        self.start_time = time.time()
        # track previous detections for fight detection
        self.prev_detections = []

    def _init_detectors(self):
        """Lazily initialize the shared YOLO detector + classifier."""
        self.yolo_detector, self.classifier = get_detector()

    def run(self):
        """Main processing loop"""
        logger.info(f"Starting live processor for camera {self.camera_id}")
        self.running = True

        self._init_detectors()

        if not self.stream_reader.connect():
            logger.error(f"Failed to start stream for camera {self.camera_id}")
            self.running = False
            return

        frame_times = []
        alert_cooldowns = {}

        while self.running:
            try:
                frame = self.stream_reader.read_frame()
                if frame is None:
                    logger.warning(f"Stream lost for camera {self.camera_id}, attempting reconnect...")
                    if self.stream_reader.connect():
                        continue
                    else:
                        break

                self.frame_count += 1
                self.buffer.add_frame(frame)

                if self.frame_count % self.frame_skip != 0:
                    continue

                current_time = time.time()

                raw_detections = self.yolo_detector.detect(frame)
                detections = [d for d in raw_detections if d.confidence > 0.40]

                anomalies = self.classifier.classify(
                    detections,            # List[Detection] objects
                    current_time,          # float timestamp
                    self.prev_detections   # previous frame's detections
                )

                # Filter and store with cooldown
                valid_anomalies = []
                for anomaly in anomalies:
                    if anomaly.score < 0.60:
                        continue

                    last_alert = alert_cooldowns.get(anomaly.type, 0)
                    if (current_time - last_alert) < 5.0:
                        continue
                    alert_cooldowns[anomaly.type] = current_time

                    self._store_anomaly(frame, anomaly, detections)
                    valid_anomalies.append(anomaly)

                self.buffer.update_detections(detections, valid_anomalies)

                # UPDATE previous detections for next frame
                self.prev_detections = detections

                # Calculate FPS
                frame_times.append(current_time)
                if len(frame_times) > 30:
                    frame_times.pop(0)
                if len(frame_times) > 1:
                    self.buffer.fps = len(frame_times) / (frame_times[-1] - frame_times[0])

            except Exception as e:
                logger.error(f"Error in processing loop: {e}", exc_info=True)
                time.sleep(1)

        self.stream_reader.disconnect()
        logger.info(f"Stopped live processor for camera {self.camera_id}")

    def _store_anomaly(self, frame, anomaly, detections):
        """Persist a detected anomaly for this live camera.

        FIXED: now goes through models.anomaly.log_anomaly() instead of a
        raw insert (consistent detection_time/status stamping like every
        other anomaly path), and includes owner_id so the in-app
        notification-polling endpoint (routes/cameras.py) can find it.
        """
        try:
            db = get_db()
            anomaly_data = {
                "video_id": self.camera_id,
                "owner_id": self.owner_id,
                "anomaly_type": anomaly.type,
                "anomaly_score": round(anomaly.score, 2),
                "description": f"Live Camera: {anomaly.description}",
                "objects_detected": anomaly.objects,
                "detection_count": len(detections),
                "created_at": datetime.now(),
                "is_live": True
            }
            if db:
                log_anomaly(db, anomaly_data)
            logger.warning(f"LIVE ALERT [{self.camera_id}]: {anomaly.type.upper()}")
        except Exception as e:
            logger.error(f"Failed to store live anomaly: {e}")

    def stop(self):
        """Signal the processing loop to stop and wait for the thread to exit."""
        self.running = False
        if self.is_alive():
            self.join(timeout=5)


class LiveCameraManager:
    """
    Manages multiple live camera streams
    Handles start/stop, reconnection, status monitoring
    """
    
    def __init__(self):
        self.processors: Dict[str, LiveCameraProcessor] = {}
        self.lock = threading.Lock()
        
    def start_camera(self, camera_id: str, rtsp_url: str, owner_id: str = None) -> bool:
        """Start live processing for a camera"""
        with self.lock:
            if camera_id in self.processors and self.processors[camera_id].running:
                logger.warning(f"Camera {camera_id} is already running")
                return False
            
            try:
                # Create stream reader
                stream_reader = RTSPStreamReader(rtsp_url)
                
                # Create and start processor (detectors initialized on first frame)
                processor = LiveCameraProcessor(camera_id, stream_reader, owner_id=owner_id)
                processor.start()
                
                self.processors[camera_id] = processor
                
                logger.info(f"Started live processing for camera {camera_id}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to start camera {camera_id}: {e}")
                return False
    
    def stop_camera(self, camera_id: str) -> bool:
        """Stop live processing for a camera"""
        with self.lock:
            if camera_id not in self.processors:
                logger.warning(f"Camera {camera_id} not found")
                return False
            
            processor = self.processors[camera_id]
            processor.stop()
            del self.processors[camera_id]
            logger.info(f"Stopped live processing for camera {camera_id}")
            return True
    
    def get_camera_status(self, camera_id: str) -> Optional[dict]:
        """Get status of a specific camera"""
        with self.lock:
            if camera_id not in self.processors:
                return None
            return self.processors[camera_id].get_status()
    
    def get_all_status(self) -> dict:
        """Get status of all active cameras"""
        with self.lock:
            return {
                cid: proc.get_status() 
                for cid, proc in self.processors.items()
            }
    
    def get_latest_frame(self, camera_id: str) -> Optional[np.ndarray]:
        """Get latest frame for a camera"""
        with self.lock:
            if camera_id not in self.processors:
                return None
            return self.processors[camera_id].buffer.get_latest_frame()
    
    def get_live_detections(self, camera_id: str) -> tuple:
        """Get latest detections and anomalies for a camera"""
        with self.lock:
            if camera_id not in self.processors:
                return None, None
            buffer = self.processors[camera_id].buffer
            return buffer.latest_detections, buffer.latest_anomalies
    
    def is_running(self, camera_id: str) -> bool:
        """Check if camera is currently streaming"""
        with self.lock:
            if camera_id not in self.processors:
                return False
            return self.processors[camera_id].running
    
    def stop_all(self):
        """Stop all active cameras"""
        with self.lock:
            camera_ids = list(self.processors.keys())
            for camera_id in camera_ids:
                self.processors[camera_id].stop()
                del self.processors[camera_id]
        logger.info("Stopped all live cameras")


# Global manager instance
live_camera_manager = LiveCameraManager()
