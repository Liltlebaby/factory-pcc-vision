"""Presentation-only suppression. Never feed this output back to the counter."""


def _overlap(first: list[float], second: list[float]) -> tuple[float, float, float]:
    """Return IoU and the intersection ratio for each box."""
    x1 = max(first[0], second[0])
    y1 = max(first[1], second[1])
    x2 = min(first[2], second[2])
    y2 = min(first[3], second[3])
    intersection = max(0.0, x2-x1)*max(0.0, y2-y1)
    first_area = max(0.0, first[2]-first[0])*max(0.0, first[3]-first[1])
    second_area = max(0.0, second[2]-second[0])*max(0.0, second[3]-second[1])
    union = first_area+second_area-intersection
    return (intersection/union if union else 0.0,
            intersection/first_area if first_area else 0.0,
            intersection/second_area if second_area else 0.0)


def _same_physical_rack(first: dict, second: dict) -> bool:
    """Conservative visual-only duplicate test for two tracker boxes."""
    a, b = first['bbox'], second['bbox']
    aw, ah = a[2]-a[0], a[3]-a[1]
    bw, bh = b[2]-b[0], b[3]-b[1]
    if min(aw, ah, bw, bh) <= 0:
        return False
    iou, inside_a, inside_b = _overlap(a, b)
    center_dx = abs((a[0]+a[2])-(b[0]+b[2]))/2
    center_dy = abs((a[1]+a[3])-(b[1]+b[3]))/2
    # The tighter vertical condition is important for this camera: different
    # racks appear stacked in depth, while duplicate fragments share a centre.
    centers_aligned = (center_dx <= .40*max(aw, bw)
                       and center_dy <= .24*max(ah, bh))
    return centers_aligned and (iou >= .50 or max(inside_a, inside_b) >= .88)


def select_preview_tracks(tracks: list[dict], line_y: float) -> list[dict]:
    """Hide duplicate boxes in the preview without changing counting state.

    A counted track wins over an uncounted duplicate. Otherwise the most
    complete (largest) box wins. Two already-counted tracks remain visible so
    separately counted physical racks are never rewritten by presentation code.
    The line argument remains part of the public interface but suppression is
    now applied over the whole frame because duplicates also occur before it.
    """
    del line_y
    def priority(index):
        track = tracks[index]
        x1, y1, x2, y2 = track['bbox']
        area = max(0.0, x2-x1)*max(0.0, y2-y1)
        return (bool(track.get('counted')), area, float(track.get('confidence', 0)))

    kept = []
    for index in sorted(range(len(tracks)), key=priority, reverse=True):
        track = tracks[index]
        duplicate = False
        for other_index in kept:
            other = tracks[other_index]
            if track.get('counted') and other.get('counted'):
                continue
            if _same_physical_rack(track, other):
                duplicate = True
                break
        if not duplicate:
            kept.append(index)
    selected = set(kept)
    return [track for index, track in enumerate(tracks) if index in selected]
