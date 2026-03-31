# anomaly_engine/detector.py
import logging
import os
import time
from datetime import datetime
from typing import List, Optional
import cv2

from .yolo_model import YOLODetector
from .anomaly_classifier import AnomalyClassifier, Detection, Anomaly
from models.anomaly import log_anomaly
from services.notification_service import send_alert
from config import Config

logger = logging.getLogger(__name__)


# Map raw objects to behavior names
def get_behavior_name(anomaly_type: str) -> str:
    mapping = {
        "weapon": "Armed Aggression",
        "gun": "Armed Aggression",
        "knife": "Armed Aggression",
        "fire": "Fire Hazard",
        "smoke": "Fire Hazard",
        "fight": "Physical Violence",
        "crowd": "Crowd Anomaly",
        "person": "Suspicious Loitering"
    }
    return mapping.get(anomaly_type.lower(), anomaly_type.title())


yolo_detector: Optional[YOLODetector] = None
anomaly_classifier: Optional[AnomalyClassifier] = None


def get_detector():
    global yolo_detector, anomaly_classifier
    if yolo_detector is None:
        yolo_detector = YOLODetector()
    if anomaly_classifier is None:
        anomaly_classifier = AnomalyClassifier()
    return yolo_detector, anomaly_classifier


def process_video(db, video_path: str, video_id):
    """Process a stored video and record anomalies."""
    file_path = video_path.strip()

    # If already absolute and exists, use directly
    if os.path.isabs(file_path) and os.path.exists(file_path):
        pass
    else:
        # Strip leading slashes
        while file_path.startswith('/') or file_path.startswith('\\'):
            file_path = file_path[1:]

        file_path = os.path.normpath(file_path)

        if not os.path.exists(file_path):
            # Try relative to CWD
            abs_path = os.path.join(os.getcwd(), file_path)
            if os.path.exists(abs_path):
                file_path = abs_path
            else:
                # Search multiple folders
                basename = os.path.basename(file_path)
                search_dirs = [
                    os.path.join(os.getcwd(), 'uploads'),
                    os.path.join(os.getcwd(), 'static', 'videos'),
                    os.path.join(os.getcwd(), 'static', 'recordings'),
                ]
                found = False
                for search_dir in search_dirs:
                    candidate = os.path.join(search_dir, basename)
                    if os.path.exists(candidate):
                        file_path = candidate
                        found = True
                        break

                if not found:
                    raise ValueError(
                        f"Video not found. Searched:\n"
                        f"  {video_path}\n"
                        f"  {abs_path}\n"
                        + "\n".join(f"  {os.path.join(d, basename)}" for d in search_dirs)
                    )

    logger.info("Processing video: %s", file_path)

    detector, classifier = get_detector()

    cap = cv2.VideoCapture(file_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    os.makedirs(Config.IMAGE_FOLDER, exist_ok=True)

    skip_frames = max(1, int(fps / 5))
    anomalies_results = []
    prev_detections: Optional[List[Detection]] = None
    alert_cooldowns = {}
    frame_count = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % skip_frames == 0:
            current_time = frame_count / fps

            raw_detections: List[Detection] = detector.detect(frame)
            detections = [d for d in raw_detections if d.confidence > 0.40]

            anomalies: List[Anomaly] = classifier.classify(
                detections, current_time, prev_detections
            )

            for anomaly in anomalies:
                if anomaly.score < 0.60:
                    continue

                last_alert_time = alert_cooldowns.get(anomaly.type, -100)
                if (current_time - last_alert_time) < 5.0:
                    continue

                alert_cooldowns[anomaly.type] = current_time

                ts = int(time.time())
                img_name = f"anomaly_{video_id}_{ts}_{frame_count}.jpg"
                img_path = os.path.join(Config.IMAGE_FOLDER, img_name)

                visual = _annotate_frame(frame, detections, anomaly, detector)
                cv2.imwrite(img_path, visual)

                anomaly_data = _serialize_anomaly(
                    anomaly, video_id, current_time, img_name, len(detections), detections
                )

                _log_and_alert(db, anomaly_data)
                anomalies_results.append(anomaly_data)

            prev_detections = detections

        frame_count += 1

    cap.release()
    logger.info("Processing complete! Found %d total anomalies", len(anomalies_results))
    return anomalies_results


def _annotate_frame(frame, detections: List[Detection], anomaly: Anomaly, detector: YOLODetector):
    """Draw bounding boxes and alert text on the frame."""
    annotated = frame.copy()

    # Draw ALL detections that are relevant to this anomaly
    for d in detections:
        x, y, w, h = d.bbox

        # Check if this detection is part of the anomaly
        is_anomaly_object = d.label in anomaly.objects

        if is_anomaly_object:
            # Red for threat objects
            if d.label in ['knife', 'scissors', 'baseball bat', 'bottle']:
                color = (0, 0, 255)  # Red
            elif d.label == 'person':
                color = (0, 0, 255)  # Red for person in anomaly
            else:
                color = (0, 0, 255)  # Red
        else:
            # Green for normal objects
            color = (0, 255, 0)

        # Draw rectangle
        cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)

        # Draw label
        label = f"{d.label} {int(d.confidence * 100)}%"
        
        # Background for text
        text_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
        cv2.rectangle(annotated, (x, y - text_size[1] - 10), (x + text_size[0], y), color, -1)
        cv2.putText(annotated, label, (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

    # Draw alert banner at top
    behavior_label = get_behavior_name(anomaly.type)
    banner_text = f"ALERT: {behavior_label.upper()}"
    
    # Red banner background
    cv2.rectangle(annotated, (0, 0), (500, 40), (0, 0, 255), -1)
    cv2.putText(
        annotated,
        banner_text,
        (10, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2
    )

    # Score badge
    score_text = f"Score: {int(anomaly.score * 100)}%"
    cv2.putText(
        annotated,
        score_text,
        (510, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 0, 255),
        2
    )

    return annotated


def _serialize_anomaly(anomaly: Anomaly, video_id, current_time, img_name, detection_count, detections=None):
    data = {
        "video_id": video_id,
        "anomaly_type": anomaly.type,
        "anomaly_score": round(anomaly.score, 2),
        "frame_timestamp": round(current_time, 1),
        "image_path": f"/static/images/{img_name}",
        "description": anomaly.description,
        "objects_detected": anomaly.objects,
        "detection_count": detection_count,
        "is_live": False
    }

    bboxes = []
    if detections:
        try:
            for d in detections:
                if d.label in anomaly.objects:
                    x, y, w, h = d.bbox
                    bboxes.append([int(x), int(y), int(w), int(h)])
        except Exception:
            bboxes = []

    if bboxes:
        data["bboxes"] = bboxes

    data.update(anomaly.extra)
    return data


def _log_and_alert(db, anomaly_data):
    logger.warning("%s detected (Score: %s)",
                   anomaly_data["anomaly_type"].upper(),
                   anomaly_data["anomaly_score"])
    log_anomaly(db, anomaly_data)
    send_alert(anomaly_data)


def generate_live_feed(db, camera_index=0):
    """Yield multipart JPEGs from a server-side camera WITH behavior detection."""
    yolo_detector, anomaly_classifier = get_detector()

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        logger.error("Unable to open camera %s", camera_index)
        yield b''
        return

    alert_cooldowns = {}
    prev_detections = []
    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        current_time = time.time()

        raw_detections = yolo_detector.detect(frame)
        detections = [d for d in raw_detections if d.confidence > 0.40]

        anomalies = anomaly_classifier.classify(detections, current_time, prev_detections)

        for anomaly in anomalies:
            if anomaly.score < 0.60:
                continue

            last_alert = alert_cooldowns.get(anomaly.type, 0)
            if (current_time - last_alert) < 5.0:
                continue

            alert_cooldowns[anomaly.type] = current_time
            logger.warning("LIVE ALERT: %s detected!", anomaly.type.upper())

            anomaly_data = {
                "video_id": "live_feed_01",
                "anomaly_type": anomaly.type,
                "anomaly_score": round(anomaly.score, 2),
                "frame_timestamp": current_time,
                "image_path": None,
                "description": f"Live Camera: {anomaly.description}",
                "objects_detected": anomaly.objects,
                "detection_count": len(detections),
                "created_at": datetime.now(),
                "is_live": True
            }
            try:
                if db:
                    db.anomalies.insert_one(anomaly_data)
            except Exception as e:
                logger.error(f"DB Error: {e}")

        annotated = frame.copy()
        is_threat = len(anomalies) > 0

        for d in detections:
            x, y, w, h = d.bbox
            color = (0, 0, 255) if is_threat else (0, 255, 0)
            cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
            label_text = f"{d.label} {int(d.confidence * 100)}%"
            cv2.putText(annotated, label_text, (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        if is_threat:
            top_anomaly = max(anomalies, key=lambda a: a.score)
            cv2.putText(annotated, f"ALERT: {top_anomaly.type.upper()}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        prev_detections = detections

        ok, buffer = cv2.imencode('.jpg', annotated)
        if not ok:
            continue

        frame_bytes = buffer.tobytes()
        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n'
            b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n\r\n' +
            frame_bytes + b'\r\n'
        )

    cap.release()