"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line


def run(ds, cfg):
    limits = cfg["label_format"]
    issues = []
    for label_file in ds.label_files():
        stem = label_file.stem
        size = ds.image_size(stem)
        previous = []
        for line, text in ds.read_label_lines(stem) or []:
            try:
                class_id, x, y, w, h = parse_yolo_line(text)
            except (ValueError, OverflowError) as exc:
                issues.append(Issue("label_format", ERROR, "BAD_FORMAT", stem,
                                    f"dòng nhãn không hợp lệ: {exc}", line=line))
                continue

            if not 0 <= class_id < len(ds.classes):
                issues.append(Issue("label_format", ERROR, "BAD_CLASS_ID", stem,
                                    f"id lớp {class_id} ngoài 0..{len(ds.classes) - 1}", line=line))
                continue
            if w <= 0 or h <= 0:
                issues.append(Issue("label_format", ERROR, "BOX_ZERO", stem,
                                    f"box có rộng/cao không dương: {w}, {h}", line=line))
                continue

            box = (x, y, w, h)
            # Mức tràn lớn nhất trong bốn mép, theo tỉ lệ kích thước ảnh.
            overflow = max(0.0, w / 2 - x, h / 2 - y,
                           x + w / 2 - 1, y + h / 2 - 1)
            if overflow > limits["overflow_tol"]:
                issues.append(Issue("label_format", ERROR, "BOX_OUT_OF_IMAGE", stem,
                                    f"box tràn ảnh {overflow:.6f}", line=line,
                                    extra={"overflow": overflow}))

            # Chỉ báo dòng sau, tối đa một DUP_BOX dù trùng nhiều dòng trước.
            for prev_line, prev_class, prev_box in previous:
                overlap = iou_xywh(box, prev_box)
                if class_id == prev_class and overlap > limits["dup_box_iou"]:
                    issues.append(Issue("label_format", ERROR, "DUP_BOX", stem,
                                        f"box cùng lớp trùng dòng {prev_line}, IoU={overlap:.4f}",
                                        line=line, extra={"iou": overlap}))
                    break
            previous.append((line, class_id, box))

            if size is not None:
                width, height = size
                short_side = min(w * width, h * height)
                if short_side < limits["min_box_px"]:
                    issues.append(Issue("label_format", WARN, "BOX_TINY", stem,
                                        f"cạnh ngắn box {short_side:.2f}px < {limits['min_box_px']}px",
                                        line=line))
            if w * h > limits["max_box_frac"]:
                issues.append(Issue("label_format", WARN, "BOX_HUGE", stem,
                                    f"diện tích box {w * h:.4f} > {limits['max_box_frac']}",
                                    line=line))
    return issues
