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

        # Track how many consecutive frames a person has been seen
        self.person_presence_count = 0
        # FIXED: was 15 frames (~3 seconds at 5fps) - way too short, any
        # brief pause (checking phone, tying a shoe) read as "loitering".
        # ~5 classify() calls/sec of real video, so 100 frames = ~20 real
        # seconds, a much more reasonable bar for actual loitering.
        self.LOITERING_THRESHOLD = 100

        # ADD: Track consecutive frames of "grappling" overlap, same
        # persistence pattern as loitering - a single frame of two people
        # standing close (hug, walking past each other, doorway) should
        # NOT immediately fire "Physical Violence".
        self.fight_presence_count = 0
        self.FIGHT_THRESHOLD = 6  # ~1.2 real seconds of sustained overlap

        self.suspicious_objects = {
            # FIXED: removed "bottle" - an ordinary water/soda bottle is
            # extremely common in any room and was flagging as
            # "Armed Aggression", almost certainly the #1 source of false
            # alarms. Rule-based detection can't tell a held bottle from
            # one sitting on a table, so it's excluded entirely.
            "weapon": ["knife", "scissors", "baseball bat", "gun"],
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

    # ------------------------------------------------------------------
    # RULES
    # ------------------------------------------------------------------

    def _detect_intrusion(self, counts: Counter, detections: List[Detection]) -> List[Anomaly]:
        """
        FIXED (was previously defined twice - the second, no-threshold
        version was silently overriding this one, so every single-frame
        person sighting fired a "loitering" alert with no time requirement).
        Only trigger after a person has been present for multiple
        consecutive frames, so someone just walking past the camera
        doesn't count as loitering.
        """
        n = counts.get(self.PERSON, 0)
        if n == 0:
            return []

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
        2. High overlap (grappling) OR rapid movement, SUSTAINED across
           multiple consecutive frames (FIXED - previously fired on a
           single frame, so a hug or two people briefly passing close to
           each other immediately read as "Physical Violence").
        """
        if counts.get(self.PERSON, 0) < 2:
            self.fight_presence_count = 0
            return []

        # Get all people detections
        people = [d for d in current if d.label == self.PERSON]
        
        # CHECK 1: GRAPPLING (High Overlap)
        # FIXED: raised from 0.30 - a normal hug or two people standing
        # near a doorway easily hits 30% box overlap. 0.5+ means the two
        # bounding boxes are substantially on top of each other.
        is_grappling = False
        for i in range(len(people)):
            for j in range(i + 1, len(people)):
                overlap = self._bbox_overlap(people[i].bbox, people[j].bbox)
                if overlap > 0.50:
                    is_grappling = True
                    break
        
        # CHECK 2: RAPID MOVEMENT
        moved_fast = False
        if previous:
             moved_fast = self._detect_rapid_movement(current, previous)

        # FIXED: require this condition to hold for several consecutive
        # frames (not just one) before actually raising an alert - mirrors
        # the loitering persistence fix.
        if is_grappling or moved_fast:
            self.fight_presence_count += 1
        else:
            self.fight_presence_count = 0

        if self.fight_presence_count < self.FIGHT_THRESHOLD:
            return []

        return [Anomaly(
                type="Physical Violence", # Behavior Name
                score=0.85, 
                description="Aggressive behavior / Fighting detected",
                objects=[self.PERSON] * 2,
            )]

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
            
            # FIXED: raised from 40px - normal walking speed between
            # sampled frames could easily exceed 40px on a 640px-wide
            # frame, causing false "rapid movement" hits.
            if min_dist > 90 and min_dist != float('inf'):
                return True
        return False

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