"""แปลงเฟรมภาพเป็นข้อมูลที่ ppe.py กับ presence.py ใช้ได้

ขอบเขตของไฟล์นี้
-----------------
รับเฟรม คืนรายการคนพร้อมผลว่าใส่หมวกหรือไม่ เท่านั้น ไม่รู้จักกฎของโรงงาน
ไม่รู้จักรอบตรวจ ไม่รู้จักการแจ้งเตือน กฎทั้งหมดอยู่ในไฟล์อื่นที่ทดสอบไปแล้ว

หลักที่ทำให้ผลแม่น: ไม่เดาเมื่อไม่รู้
--------------------------------------
โมเดลตรวจ PPE ให้กล่องมาหลายชนิด วิธีที่ผิดคือ "ถ้าไม่เจอกล่องหมวก แปลว่าไม่ใส่"
เพราะโมเดลมองไม่เห็นหมวกได้จากหลายสาเหตุที่ไม่เกี่ยวกับการไม่ใส่ — คนหันหลัง
ศีรษะโดนบัง ภาพเบลอ อยู่ไกล หรือโมเดลพลาดเอง การตีความแบบนั้นทำให้ระบบฟ้องผิด
ทั้งวันแล้วไม่มีใครเชื่ออีกเลย

ไฟล์นี้จึงบังคับให้ต้องมีหลักฐานทางบวกเสมอ

    เจอกล่อง 'helmet' ในบริเวณศีรษะ   →  PASS
    เจอกล่อง 'head' เปล่าในบริเวณนั้น  →  VIOLATION
    ไม่เจอทั้งสองอย่าง                 →  UNDECIDED (ไม่ใช่ VIOLATION)

UNDECIDED ไม่ถูกส่งต่อให้ ppe.py ตัดสิน จึงไม่มีทางกลายเป็นการฟ้อง และเวลาที่
สะสมไว้ก่อนหน้าก็ไม่ถูกล้างทิ้ง คนที่หันหลังชั่วครู่แล้วหันกลับมาจึงยังนับต่อได้

ทำไมต้องจับคู่กล่องกับบริเวณศีรษะ
---------------------------------
ถ้าเอากล่องหมวกที่อยู่ที่ไหนก็ได้ในเฟรมมาจับคู่กับคน หมวกของคนที่ยืนข้าง ๆ
จะถูกนับเป็นหมวกของคนที่ไม่ได้ใส่ ระบบจะบอกว่าทุกคนใส่หมวกตราบใดที่มีใคร
สักคนในเฟรมใส่อยู่ จึงต้องบังคับว่ากล่องต้องอยู่ในช่วงบนของกล่องคนคนนั้นจริง
"""
from dataclasses import dataclass

# ชื่อคลาสที่โมเดล PPE มักใช้ รองรับหลายแบบเพราะแต่ละชุดน้ำหนักตั้งชื่อไม่เหมือนกัน
HELMET_NAMES = frozenset({
    'helmet', 'hardhat', 'hard-hat', 'hard_hat', 'safety-helmet', 'safety_helmet',
    'with_helmet', 'with-helmet', 'helmet_on',
})
BARE_HEAD_NAMES = frozenset({
    'head', 'bare_head', 'bare-head', 'no-helmet', 'no_helmet', 'nohelmet', 'no-hardhat', 'no_hardhat',
    'nohardhat', 'without_helmet', 'without-helmet', 'person_no_helmet',
})
PERSON_NAMES = frozenset({'person', 'people', 'worker'})

PASS = 'PASS'
VIOLATION = 'VIOLATION'
UNDECIDED = 'UNDECIDED'

# ศีรษะอยู่ในช่วงบนของกล่องคนเท่านี้ ใช้จับคู่กล่องหมวกกับเจ้าของ
HEAD_REGION_RATIO = 0.40
# กล่องหมวกต้องอยู่ในบริเวณศีรษะไม่น้อยกว่าสัดส่วนนี้ของพื้นที่ตัวเอง
HEAD_CONTAINMENT = 0.50


@dataclass(frozen=True)
class Box:
    """กล่องในพิกัดพิกเซลของเฟรม"""
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def area(self) -> float:
        return self.width * self.height

    def head_region(self, ratio: float = HEAD_REGION_RATIO) -> 'Box':
        """ช่วงบนของกล่องคน ที่ศีรษะควรอยู่"""
        return Box(self.x1, self.y1, self.x2, self.y1 + self.height * ratio)

    def containment_in(self, other: 'Box') -> float:
        """พื้นที่ของกล่องนี้ที่อยู่ในอีกกล่องหนึ่ง คิดเป็นสัดส่วนของตัวเอง"""
        if self.area <= 0:
            return 0.0
        left = max(self.x1, other.x1)
        top = max(self.y1, other.y1)
        right = min(self.x2, other.x2)
        bottom = min(self.y2, other.y2)
        if right <= left or bottom <= top:
            return 0.0
        return (right - left) * (bottom - top) / self.area


@dataclass(frozen=True)
class Detection:
    """กล่องหนึ่งกล่องที่โมเดลตรวจพบ"""
    label: str
    box: Box
    confidence: float


@dataclass(frozen=True)
class PersonObservation:
    """ผลของคนหนึ่งคนในหนึ่งเฟรม พร้อมข้อมูลที่ ppe.py ต้องใช้ตัดสิน"""
    track_id: int
    box: Box
    confidence: float
    helmet_status: str
    helmet_confidence: float
    height_ratio: float

    @property
    def decided(self) -> bool:
        return self.helmet_status in (PASS, VIOLATION)

    @property
    def helmet(self) -> bool:
        return self.helmet_status == PASS


def classify_helmet(person: Box, detections, containment: float = HEAD_CONTAINMENT,
                    head_ratio: float = HEAD_REGION_RATIO) -> tuple[str, float]:
    """ตัดสินว่าคนในกล่องนี้ใส่หมวกหรือไม่ จากกล่องอื่นที่โมเดลตรวจพบ

    คืน UNDECIDED เมื่อไม่มีหลักฐานทางบวกทั้งสองฝั่ง ซึ่งเป็นกรณีที่พบบ่อยที่สุด
    ในภาพจริง และเป็นกรณีที่ต้องไม่ถูกตีความเป็นการไม่สวมหมวกเด็ดขาด
    """
    region = person.head_region(head_ratio)
    best_helmet = 0.0
    best_bare = 0.0
    for detection in detections:
        name = detection.label.strip().lower()
        if name not in HELMET_NAMES and name not in BARE_HEAD_NAMES:
            continue
        if detection.box.containment_in(region) < containment:
            continue
        if name in HELMET_NAMES:
            best_helmet = max(best_helmet, detection.confidence)
        else:
            best_bare = max(best_bare, detection.confidence)

    if best_helmet == 0.0 and best_bare == 0.0:
        return UNDECIDED, 0.0
    # เจอทั้งสองอย่างในบริเวณเดียวกัน เชื่อตัวที่มั่นใจกว่า และถ้าใกล้เคียงกันมาก
    # ให้ถือว่าตัดสินไม่ได้ ดีกว่าตัดสินด้วยส่วนต่างที่ไม่มีความหมาย
    if best_helmet and best_bare and abs(best_helmet - best_bare) < 0.10:
        return UNDECIDED, max(best_helmet, best_bare)
    return (PASS, best_helmet) if best_helmet > best_bare else (VIOLATION, best_bare)


def observe_frame(frame_height: int, people, detections,
                  containment: float = HEAD_CONTAINMENT,
                  head_ratio: float = HEAD_REGION_RATIO) -> list[PersonObservation]:
    """รวมผลของทั้งเฟรม

    `people`     รายการ (track_id, Box, confidence) จากตัวตรวจคนที่ติดตามแล้ว
    `detections` กล่องทั้งหมดที่โมเดลตรวจพบในเฟรมนี้ ใช้หาหมวก
    """
    if frame_height <= 0:
        raise ValueError('ความสูงของเฟรมต้องเป็นค่าบวก')
    observations = []
    for track_id, box, confidence in people:
        status, helmet_confidence = classify_helmet(box, detections, containment, head_ratio)
        observations.append(PersonObservation(
            track_id=int(track_id),
            box=box,
            confidence=float(confidence),
            helmet_status=status,
            helmet_confidence=helmet_confidence,
            height_ratio=box.height / frame_height,
        ))
    return observations


def summarise(observations) -> dict:
    """นับผลรวมของเฟรมสำหรับ heartbeat

    นับเฉพาะคนที่ตัดสินได้ ใน helmet_pass และ no_helmet ส่วน people_count นับทุกคน
    ผลคือ helmet_pass + no_helmet อาจน้อยกว่า people_count ซึ่งถูกต้องแล้ว
    เพราะส่วนต่างคือจำนวนคนที่ระบบยังตัดสินไม่ได้ ไม่ใช่คนที่หายไป
    """
    decided = [item for item in observations if item.decided]
    return {
        'people': len(observations),
        'helmet_pass': sum(1 for item in decided if item.helmet),
        'no_helmet': sum(1 for item in decided if not item.helmet),
        'undecided': len(observations) - len(decided),
    }


class YoloVision:
    """ห่อ Ultralytics YOLO ให้คืนผลในรูปแบบข้างบน

    นำเข้าไลบรารีตอนสร้างวัตถุ ไม่ใช่ตอน import โมดูล เพื่อให้ตรรกะข้างบน
    ทดสอบได้โดยไม่ต้องลง ultralytics และไม่ต้องมีไฟล์น้ำหนักโมเดล
    """

    def __init__(self, person_model: str, ppe_model: str | None = None,
                 imgsz: int = 640, confidence: float = 0.35, iou: float = 0.5,
                 device: str | None = None, tracker: str = 'bytetrack.yaml'):
        from ultralytics import YOLO

        self.person = YOLO(person_model)
        # ไม่มีโมเดล PPE ก็ยังทำงานได้ แค่ทุกคนจะเป็น UNDECIDED
        # จงใจให้เดินได้ก่อนโมเดลหมวกพร้อม เพราะกฎห้ามคนหายใช้แค่การตรวจคน
        self.ppe = YOLO(ppe_model) if ppe_model else None
        self.imgsz = imgsz
        self.confidence = confidence
        self.iou = iou
        self.device = device
        self.tracker = tracker

    @staticmethod
    def _boxes(result) -> list[Detection]:
        names = result.names
        found = []
        for row in result.boxes:
            x1, y1, x2, y2 = (float(value) for value in row.xyxy[0])
            found.append(Detection(
                label=str(names[int(row.cls[0])]),
                box=Box(x1, y1, x2, y2),
                confidence=float(row.conf[0]),
            ))
        return found

    def people(self, frame) -> list[tuple[int, Box, float]]:
        """ตรวจคนพร้อมติดตาม คืนเฉพาะคนที่มี track id แล้ว

        `persist=True` ทำให้ตัวติดตามจำสถานะข้ามเฟรม ซึ่งจำเป็นเพราะ ppe.py
        ตัดสินเป็นรายคนตลอดเวลาที่คนนั้นอยู่ในเฟรม ไม่ใช่รายเฟรม
        """
        results = self.person.track(
            frame, persist=True, verbose=False, imgsz=self.imgsz,
            conf=self.confidence, iou=self.iou, device=self.device, tracker=self.tracker,
        )
        found = []
        for result in results:
            names = result.names
            if result.boxes is None or result.boxes.id is None:
                continue
            for row in result.boxes:
                if str(names[int(row.cls[0])]).lower() not in PERSON_NAMES:
                    continue
                if row.id is None:
                    continue
                x1, y1, x2, y2 = (float(value) for value in row.xyxy[0])
                found.append((int(row.id[0]), Box(x1, y1, x2, y2), float(row.conf[0])))
        return found

    def ppe_boxes(self, frame) -> list[Detection]:
        if self.ppe is None:
            return []
        results = self.ppe.predict(
            frame, verbose=False, imgsz=self.imgsz,
            conf=self.confidence, iou=self.iou, device=self.device,
        )
        found = []
        for result in results:
            found.extend(self._boxes(result))
        return found

    def observe(self, frame) -> list[PersonObservation]:
        height = int(frame.shape[0])
        return observe_frame(height, self.people(frame), self.ppe_boxes(frame))
