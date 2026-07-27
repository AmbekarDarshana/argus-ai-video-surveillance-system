from ultralytics import YOLO
import numpy as np
from config import Config
import torch
import cv2

# avoid circular import by type hinting
from typing import List
from .anomaly_classifier import Detection

class YOLODetector:
    def __init__(self, model_path=None):
        """Initialize YOLOv8 model with extended classes"""
        self.model_path = model_path or Config.YOLO_MODEL
        print(f"🤖 Loading YOLOv8 model: {self.model_path}")
        
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"   Using device: {self.device}")
        
        try:
            self.model = YOLO(self.model_path)
            
            # --- FIXED: correct standard COCO class-index -> name mapping ---
            # Previous version had indices 15-24 shifted by one and
            # suitcase/backpack swapped, which silently mislabeled every
            # animal detection (e.g. real cats were logged as "dog").
            # Reference order (0-indexed), matches ultralytics coco.yaml:
            # 14 bird, 15 cat, 16 dog, 17 horse, 18 sheep, 19 cow,
            # 20 elephant, 21 bear, 22 zebra, 23 giraffe, 24 backpack,
            # 26 handbag, 28 suitcase, 34 baseball bat, 39 bottle,
            # 43 knife, 44 spoon, 46 banana
            self.extended_classes = {
                0: 'person',
                # Vehicles
                1: 'bicycle', 2: 'car', 3: 'motorcycle', 5: 'bus', 7: 'truck',
                # Animals
                14: 'bird', 15: 'cat', 16: 'dog', 17: 'horse', 18: 'sheep',
                19: 'cow', 20: 'elephant', 21: 'bear', 22: 'zebra', 23: 'giraffe',
                # Suspicious/carryable objects
                24: 'backpack', 26: 'handbag', 28: 'suitcase',
                # Potential weapons / dangerous items
                39: 'bottle', 43: 'knife', 44: 'spoon',
                34: 'baseball bat', 46: 'banana'  # banana kept as a known false-positive check
            }
            
            # Force update names in model to match our expected strings
            for idx, name in self.extended_classes.items():
                if idx < len(self.model.names):
                    self.model.names[idx] = name
            
            print(f"✅ YOLOv8 model loaded. Device: {self.device}")
            
        except Exception as e:
            print(f"❌ Error loading YOLO model: {e}")
            self.model = YOLO('yolov8n.pt') 
            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        
        # FIXED: was hardcoded to ignore Config entirely, so tuning the
        # threshold required a code change instead of just editing
        # config.py. Now honors Config.CONFIDENCE_THRESHOLD, defaulting
        # higher (0.5) than before - lower thresholds let through weak,
        # noisy detections that were feeding false alarms downstream in
        # the anomaly rules.
        self.confidence_threshold = getattr(Config, 'CONFIDENCE_THRESHOLD', 0.50)
        
        self.animal_classes = ['dog', 'cat', 'bird', 'horse', 'cow', 'sheep', 
                              'elephant', 'bear', 'zebra', 'giraffe']
        
        # These items are static and often cause false alarms. We will filter them strictly.
        self.static_suspicious_items = ['handbag', 'suitcase', 'backpack']

    def detect(self, frame) -> List[Detection]:
        """
        Detect objects in a frame with strict filtering.
        """
        height, width = frame.shape[:2]
        max_dimension = 640
        scale = min(max_dimension / width, max_dimension / height)
        
        # Resize logic to speed up processing
        if scale < 1:
            new_width = int(width * scale)
            new_height = int(height * scale)
            frame_resized = cv2.resize(frame, (new_width, new_height))
        else:
            frame_resized = frame
            scale = 1.0
        
        # --- FIX 1: FORCE MINIMUM CONFIDENCE IN MODEL CALL ---
        results = self.model(frame_resized, 
                            conf=self.confidence_threshold, # Using our hardcoded 0.40
                            device=self.device,
                            verbose=False)
        
        detections: List[Detection] = []
        
        # Define what we actually care about
        relevant_classes = {
            'person', 'dog', 'cat', 'bird', 'horse', 'cow', 'sheep',
            'car', 'truck', 'bus', 'motorcycle', 'bicycle',
            'knife', 'scissors', 'bottle', 'baseball bat',
            'handbag', 'suitcase', 'backpack'
        }

        for result in results:
            boxes = result.boxes
            for box in boxes:
                confidence = float(box.conf[0])
                class_id = int(box.cls[0])

                # Get the class name
                if class_id in self.extended_classes:
                    class_name = self.extended_classes[class_id]
                elif class_id < len(self.model.names):
                    class_name = self.model.names[class_id]
                else:
                    continue # Skip unknown classes

                # Filter out irrelevant stuff (like 'chair', 'tv', 'sandwich')
                if class_name not in relevant_classes:
                    continue

                # --- FIX 2: STRICT FILTER FOR STATIC OBJECTS ---
                # Bags/Suitcases often look like random blobs. 
                # Only accept them if AI is VERY sure (60%+)
                if class_name in self.static_suspicious_items and confidence < 0.60:
                    continue

                # Coordinate mapping (Resize back to original)
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                if scale < 1:
                    x1, x2 = x1 / scale, x2 / scale
                    y1, y2 = y1 / scale, y2 / scale

                bbox = (int(x1), int(y1), int(x2 - x1), int(y2 - y1))

                detections.append(Detection(bbox=bbox, confidence=confidence, label=class_name))

        return detections

    def get_object_counts(self, detections: List[Detection]) -> dict:
        counts = {}
        for det in detections:
            counts[det.label] = counts.get(det.label, 0) + 1
        return counts
    
    def is_animal(self, class_name):
        return class_name in self.animal_classes