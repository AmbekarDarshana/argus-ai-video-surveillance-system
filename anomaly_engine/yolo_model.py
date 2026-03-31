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
            
            # Standard COCO mappings to ensure names match your logic
            self.extended_classes = {
                0: 'person',
                # Vehicles
                1: 'bicycle', 2: 'car', 3: 'motorcycle', 5: 'bus', 7: 'truck',
                # Animals
                15: 'dog', 16: 'horse', 17: 'sheep', 18: 'cow',
                19: 'elephant', 20: 'bear', 21: 'zebra', 22: 'giraffe',
                23: 'cat', 24: 'bird',
                # Suspicious objects
                26: 'handbag', 27: 'suitcase', 28: 'backpack',
                # Potential weapons / dangerous items
                39: 'bottle', 43: 'knife', 44: 'spoon', 
                34: 'baseball bat', 46: 'banana' # sometimes banana is tested as false positive
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
        
        # IGNORE CONFIG. Force a safe threshold.
        # 0.40 means AI must be 40% sure before even mentioning it.
        self.confidence_threshold = 0.40
        
        self.animal_classes = ['dog', 'cat', 'bird', 'horse', 'cow', 'sheep', 
                              'elephant', 'bear', 'zebra', 'giraffe']
        
        # These items are static and often cause false alarms. We will filter them strictly.
        self.static_suspicious_items = ['handbag', 'suitcase', 'backpack', 'bottle']

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