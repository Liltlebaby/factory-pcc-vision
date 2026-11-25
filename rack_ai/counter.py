"""Configurable line crossing, with bounded per-track history.

Duplicate suppression
---------------------
A single physical rack can be reported as two overlapping tracks (a split
box), and two physically distinct racks can cross the line within a second of
each other when they travel touching. A single global cooldown cannot tell
these apart: it suppresses both.

``dedupe='spatial'`` (default) keeps the cooldown as a *time window* but only
suppresses a crossing whose box overlaps a box that was already counted inside
that window. A split box of the same rack overlaps heavily and is suppressed;
a second rack travelling behind the first has its own box and is counted.

``dedupe='global'`` restores the previous behaviour exactly (any crossing
inside the cooldown is suppressed) so the change can be reverted from the
environment without editing code.
"""
from dataclasses import dataclass, field
from collections import deque

from .config import Settings


def box_iou(first, second):
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    intersection = max(0.0, min(ax2, bx2)-max(ax1, bx1))*max(0.0, min(ay2, by2)-max(ay1, by1))
    area_a = max(1e-9, (ax2-ax1)*(ay2-ay1))
    area_b = max(1e-9, (bx2-bx1)*(by2-by1))
    return intersection/max(1e-9, area_a+area_b-intersection)


def containment(first, second):
    """Largest fraction of either box covered by the other."""
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    intersection = max(0.0, min(ax2, bx2)-max(ax1, bx1))*max(0.0, min(ay2, by2)-max(ay1, by1))
    area_a = max(1e-9, (ax2-ax1)*(ay2-ay1))
    area_b = max(1e-9, (bx2-bx1)*(by2-by1))
    return max(intersection/area_a, intersection/area_b)


@dataclass
class TrackState:
    positions: deque = field(default_factory=lambda: deque(maxlen=15))
    seen: float = 0
    armed: bool = False
    counted: bool = False
    counted_at: float = -float('inf')
    bbox: list = field(default_factory=list)


class RackCounter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.tracks: dict[int, TrackState] = {}
        self.count = 0
        self.last_event = None
        self.last_at = -float('inf')
        # Crossings the duplicate guard rejected; exposed for tuning, never for counting.
        self.suppressed = 0

    def reset_tracks(self):
        # Preserve the total across reconnects; IDs belong to each tracking session.
        # Clearing the states also clears the duplicate memory, which is correct:
        # boxes from the previous session must not suppress the next one.
        self.tracks.clear()

    def _duplicate(self, track_id, bbox, timestamp) -> bool:
        """True when this crossing is the same physical rack as a recent count.

        Compares against the *current* box of every track counted inside the
        window rather than its box frozen at crossing time. A split box travels
        in lockstep with the rack it belongs to, so it keeps overlapping; a rack
        following behind separates as the one ahead moves on.
        """
        cfg = self.settings
        if timestamp-self.last_at >= cfg.cooldown:
            return False
        if cfg.dedupe == 'global':
            return True
        for key, state in self.tracks.items():
            if key == track_id or not state.counted or not state.bbox:
                continue
            if timestamp-state.counted_at >= cfg.cooldown:
                continue
            if (box_iou(bbox, state.bbox) >= cfg.duplicate_iou
                    or containment(bbox, state.bbox) >= cfg.duplicate_containment):
                return True
        return False

    def update(self, detections: list[dict], height: int, timestamp: float) -> list[dict]:
        cfg = self.settings
        line = height * cfg.line
        for d in detections:
            state = self.tracks.setdefault(d['track_id'], TrackState())
            x1, y1, x2, y2 = d['bbox']
            anchor = {'top': y1, 'center': (y1+y2)/2, 'bottom': y2}[cfg.anchor]
            state.seen = timestamp
            state.bbox = [x1, y1, x2, y2]
            state.positions.append(anchor)
            if anchor < line - 2:
                state.armed = True
            movement = anchor - state.positions[0]
            d['direction'] = 'down' if movement >= cfg.movement else 'up' if movement <= -cfg.movement else 'stationary'
            if (state.armed and not state.counted and anchor >= line + 2
                    and len(state.positions) >= 3 and movement >= cfg.movement):
                if self._duplicate(d['track_id'], state.bbox, timestamp):
                    # Not counted now; the track stays eligible so a genuine rack
                    # held back by the window is still counted on a later frame.
                    self.suppressed += 1
                else:
                    self.count += 1
                    state.counted = True
                    state.counted_at = timestamp
                    self.last_at = timestamp
                    self.last_event = {'rackNumber': self.count, 'trackId': d['track_id'],
                                       'timestamp': timestamp, 'confidence': d['confidence']}
            d['counted'] = state.counted
            d['center'] = [(x1+x2)/2, (y1+y2)/2]
        self.tracks = {k: v for k, v in self.tracks.items() if timestamp-v.seen < 60}
        return detections
