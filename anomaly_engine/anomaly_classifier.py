import logging
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
from collections import Counter
import numpy as np
from config import Config

logger = logging.getLogger(__name__)

@dataclass
class Detection:
    bbox: Tuple[int, int, int, int]
    confidence: float
    label: str

@dataclass
class Anomaly:
    type: str
    score: float
    description: str
    objects: List[str]
    extra: Dict = field(default_factory=dict)

# In anomaly_classifier.py

class AnomalyClassifier:
    PERSON = "person"

    def __init__(self) -> None:
        self.frame_counter = 0

        # ADD: Track how many consecutive frames a person has been seen
        self.person_presence_count = 0
        self.LOITERING_THRESHOLD = 15  # Must see person for 15+ frames (~3 seconds at 5fps)

        self.suspicious_objects = {
            "weapon": ["knife", "scissors", "baseball bat", "bottle", "gun"],
            "abandoned_items": ["suitcase", "backpack", "handbag"],
            "vehicles": ["car", "truck", "motorcycle", "bicycle", "bus"],
            "animals": ["dog", "cat", "bird", "horse", "cow", "sheep", "bear"],
        }
        logger.debug("AnomalyClassifier initialized")

    def classify(self, detections, frame_time, prev_detections=None):
        self.frame_counter += 1

        counts = Counter(d.label for d in detections)
        anomalies = []

        # UPDATE person tracking
        if counts.get(self.PERSON, 0) > 0:
            self.person_presence_count += 1
        else:
            self.person_presence_count = 0

        # Run Rules
        anomalies.extend(self._detect_intrusion(counts, detections))
        anomalies.extend(self._detect_crowding(counts))
        anomalies.extend(self._detect_suspicious_items(counts, detections))
        anomalies.extend(self._detect_fight(detections, prev_detections, counts))
        anomalies.extend(self._detect_animals(counts, detections))

        return anomalies

    def _detect_intrusion(self, counts, detections):
        n = counts.get(self.PERSON, 0)
        if n == 0:
            return []

        # FIXED: Only trigger after person has been present for multiple frames
        # This prevents "person walked past camera" from being an alert
        if self.person_presence_count < self.LOITERING_THRESHOLD:
            return []

        max_conf = self._get_max_confidence(detections, self.PERSON)
        score = max_conf
        if n > 1:
            score += 0.1

        return [Anomaly(
            type="Suspicious Loitering",
            score=min(0.99, score),
            description=f"{n} person(s) loitering for extended period",
            objects=[self.PERSON] * n,
        )]

    # ------------------------------------------------------------------
    # RULES
    # ------------------------------------------------------------------

    def _detect_intrusion(self, counts: Counter, detections: List[Detection]) -> List[Anomaly]:
        n = counts.get(self.PERSON, 0)
        if n == 0: return []
        
        max_conf = self._get_max_confidence(detections, self.PERSON)
        score = max_conf 
        if n > 1: score += 0.1
        
        return [Anomaly(
            type="Suspicious Loitering", # Behavior Name,
            score=min(0.99, score),
            description=f"{n} person(s) detected in area",
            objects=[self.PERSON] * n,
        )]

    def _detect_suspicious_items(self, counts: Counter, detections: List[Detection]) -> List[Anomaly]:
        anomalies: List[Anomaly] = []
        for category, items in self.suspicious_objects.items():
            if category == "animals" or category == "vehicles": continue
            found_items = [i for i in items if counts.get(i, 0) > 0]
            for item in found_items:
                conf = self._get_max_confidence(detections, item)
                if category == "weapon": score = conf * 1.1 
                else: score = conf * 0.95 

                               # Map category to Behavior Name
                behavior_type = "Armed Aggression" if category == "weapon" else f"Suspicious {category.title()}"
                
                anomalies.append(Anomaly(
                    type=behavior_type,
                    score=min(0.99, score),
                    description=f"Detected {item} ({int(conf*100)}% confidence)",
                    objects=[item]
                ))
        return anomalies

    def _detect_crowding(self, counts: Counter) -> List[Anomaly]:
        n = counts.get(self.PERSON, 0)
        if n < 3: return []
        score = 0.6 + (n * 0.05) 
        return [Anomaly(
            type="Crowd Anomaly",
            score=min(0.99, score),
            description=f"Crowd detected: {n} people",
            objects=[self.PERSON] * n,
        )]

    def _detect_fight(self, current: List[Detection], previous: Optional[List[Detection]], counts: Counter) -> List[Anomaly]:
        """
        Detects fights based on:
        1. Two or more people.
        2. High overlap (grappling/hugging).
        3. Or Rapid movement (running/punching).
        """
        if counts.get(self.PERSON, 0) < 2:
            return []

        # Get all people detections
        people = [d for d in current if d.label == self.PERSON]
        
        # CHECK 1: GRAPPLING (High Overlap)
        is_grappling = False
        for i in range(len(people)):
            for j in range(i + 1, len(people)):
                # THIS IS THE FUNCTION THAT WAS MISSING BEFORE
                overlap = self._bbox_overlap(people[i].bbox, people[j].bbox)
                if overlap > 0.30: # 30% overlap means they are very close
                    is_grappling = True
                    break
        
        # CHECK 2: RAPID MOVEMENT
        moved_fast = False
        if previous:
             moved_fast = self._detect_rapid_movement(current, previous)

        if is_grappling or moved_fast:
            return [Anomaly(
                type="Physical Violence", # Behavior Name
                score=0.85, 
                description="Aggressive behavior / Fighting detected",
                objects=[self.PERSON] * 2,
            )]
            
        return []

    def _detect_animals(self, counts: Counter, detections: List[Detection]) -> List[Anomaly]:
        anomalies: List[Anomaly] = []
        for animal in self.suspicious_objects["animals"]:
            if counts.get(animal, 0) > 0:
                conf = self._get_max_confidence(detections, animal)
                anomalies.append(Anomaly(
                    type="animal_intrusion",
                    score=conf,
                    description=f"{animal.capitalize()} detected",
                    objects=[animal]
                ))
        return anomalies

    # ------------------------------------------------------------------
    # HELPERS (MATH)
    # ------------------------------------------------------------------
    
    def _get_max_confidence(self, detections: List[Detection], label: str) -> float:
        scores = [d.confidence for d in detections if d.label == label]
        return max(scores) if scores else 0.0

    def _detect_rapid_movement(self, current: List[Detection], previous: List[Detection]) -> bool:
        curr_people = [d for d in current if d.label == self.PERSON]
        prev_people = [d for d in previous if d.label == self.PERSON]
        
        if not curr_people or not prev_people: return False
        
        def get_center(bbox):
            return (bbox[0] + bbox[2]/2, bbox[1] + bbox[3]/2)
            
        for c in curr_people:
            c_center = get_center(c.bbox)
            min_dist = float('inf')
            for p in prev_people:
                p_center = get_center(p.bbox)
                dist = np.hypot(c_center[0]-p_center[0], c_center[1]-p_center[1])
                if dist < min_dist: min_dist = dist
            
            if min_dist > 40 and min_dist != float('inf'):
                return True
        return False

    # THIS IS THE MISSING FUNCTION THAT CAUSED THE ERROR
    def _bbox_overlap(self, bbox1: Tuple[int, int, int, int], bbox2: Tuple[int, int, int, int]) -> float:
        """Calculates Intersection over Union (IoU) ratio between two boxes."""
        x1, y1, w1, h1 = bbox1
        x2, y2, w2, h2 = bbox2
        
        x_left = max(x1, x2)
        y_top = max(y1, y2)
        x_right = min(x1 + w1, x2 + w2)
        y_bottom = min(y1 + h1, y2 + h2)

        if x_right < x_left or y_bottom < y_top:
            return 0.0

        intersection_area = (x_right - x_left) * (y_bottom - y_top)
        area1 = w1 * h1
        area2 = w2 * h2
        union_area = area1 + area2 - intersection_area
        
        if union_area == 0: return 0.0
        return intersection_area / union_area