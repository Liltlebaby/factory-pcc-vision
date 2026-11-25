import argparse
import csv
import time
from collections import defaultdict, deque
from pathlib import Path

import cv2
from ultralytics import YOLO


def parse_args():
    parser = argparse.ArgumentParser(description="ตรวจจับ ติดตาม และนับเก๊ะจากไฟล์วิดีโอ")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--duration", type=float, default=600.0)
    parser.add_argument("--sample-fps", type=float, default=5.0)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--line", type=float, default=0.60)
    return parser.parse_args()


def valid_rack(box, width, height):
    x1, y1, x2, y2 = box
    box_width = x2 - x1
    box_height = y2 - y1
    center_x = (x1 + x2) / 2
    return (
        x1 >= width * 0.03
        and center_x <= width * 0.72
        and box_width >= width * 0.14
        and box_width <= width * 0.68
        and box_height >= height * 0.055
        and box_height <= height * 0.38
        and 1.25 <= box_width / max(1.0, box_height) <= 4.5
    )


def box_iou(first, second):
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    intersection = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
    area_a = max(1.0, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1.0, (bx2 - bx1) * (by2 - by1))
    return intersection / max(1.0, area_a + area_b - intersection)


def filter_racks(boxes, ids, scores, width, height):
    items = [
        {"box": box, "track_id": track_id, "score": score}
        for box, track_id, score in zip(boxes, ids, scores)
        if valid_rack(box, width, height)
    ]
    without_unions = []
    for item in items:
        x1, y1, x2, y2 = item["box"]
        area = max(1.0, (x2 - x1) * (y2 - y1))
        children = []
        for other in items:
            if other is item:
                continue
            ox1, oy1, ox2, oy2 = other["box"]
            other_area = max(1.0, (ox2 - ox1) * (oy2 - oy1))
            center_x, center_y = (ox1 + ox2) / 2, (oy1 + oy2) / 2
            if other_area < area * 0.78 and x1 <= center_x <= x2 and y1 <= center_y <= y2:
                children.append(center_y)
        if len(children) >= 2 and max(children) - min(children) >= height * 0.07:
            continue
        without_unions.append(item)

    kept = []
    for item in sorted(without_unions, key=lambda value: value["score"], reverse=True):
        if all(box_iou(item["box"], previous["box"]) < 0.72 for previous in kept):
            kept.append(item)
    return kept


def format_time(seconds):
    seconds = int(round(seconds))
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def main():
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.csv.parent.mkdir(parents=True, exist_ok=True)

    model = YOLO(str(args.model))
    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise RuntimeError(f"เปิดวิดีโอไม่ได้: {args.video}")

    source_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    stride = max(1, round(source_fps / args.sample_fps))
    actual_fps = source_fps / stride
    start_frame = round(args.start * source_fps)
    end_frame = start_frame + round(args.duration * source_fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    writer = cv2.VideoWriter(
        str(args.output),
        cv2.VideoWriter_fourcc(*"mp4v"),
        actual_fps,
        (width, height),
    )
    line_y = int(height * args.line)
    histories = defaultdict(lambda: deque(maxlen=15))
    counted_ids = set()
    events = []
    last_event_second = -999.0
    processed = 0
    source_frame = start_frame
    started_at = time.time()

    while source_frame < end_frame:
        ok, frame = cap.read()
        if not ok:
            break
        if (source_frame - start_frame) % stride:
            source_frame += 1
            continue

        result = model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            classes=[0],
            conf=args.conf,
            iou=0.70,
            verbose=False,
        )[0]
        video_second = source_frame / source_fps

        if result.boxes.id is not None:
            boxes = result.boxes.xyxy.cpu().numpy()
            ids = result.boxes.id.int().cpu().tolist()
            scores = result.boxes.conf.cpu().tolist()
            for detection in filter_racks(boxes, ids, scores, width, height):
                box = detection["box"]
                track_id = detection["track_id"]
                score = detection["score"]
                x1, y1, x2, y2 = (int(v) for v in box)
                anchor_y = y1
                history = histories[track_id]
                previous_y = history[-1][1] if history else None
                history.append((video_second, anchor_y))

                moving_down = len(history) >= 3 and anchor_y - min(position for _, position in history) >= 10
                crossed = previous_y is not None and previous_y < line_y <= anchor_y
                outside_cooldown = video_second - last_event_second >= 1.5
                if crossed and moving_down and outside_cooldown and track_id not in counted_ids:
                    counted_ids.add(track_id)
                    last_event_second = video_second
                    events.append(
                        {
                            "rack_number": len(events) + 1,
                            "video_second": round(video_second, 2),
                            "video_time": format_time(video_second),
                            "track_id": track_id,
                            "confidence": round(float(score), 4),
                        }
                    )

                color = (0, 0, 255) if track_id in counted_ids else (0, 255, 0)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
                cv2.putText(
                    frame,
                    f"RACK ID:{track_id} {score:.2f}",
                    (x1, max(28, y1 - 9)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.72,
                    color,
                    2,
                )

        cv2.line(frame, (0, line_y), (width - 1, line_y), (255, 0, 255), 3)
        cv2.putText(frame, f"RACK OUT: {len(events)}", (25, 65), cv2.FONT_HERSHEY_SIMPLEX, 1.35, (0, 255, 255), 3)
        cv2.putText(frame, format_time(video_second), (25, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 255, 255), 2)
        writer.write(frame)

        processed += 1
        if processed % 250 == 0:
            elapsed = time.time() - started_at
            print(f"processed={processed} time={format_time(video_second)} count={len(events)} elapsed={elapsed:.0f}s", flush=True)
        source_frame += 1

    cap.release()
    writer.release()
    with args.csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer_csv = csv.DictWriter(handle, fieldnames=["rack_number", "video_second", "video_time", "track_id", "confidence"])
        writer_csv.writeheader()
        writer_csv.writerows(events)

    print(f"rack_count={len(events)}")
    print(f"video={args.output}")
    print(f"events={args.csv}")


if __name__ == "__main__":
    main()
