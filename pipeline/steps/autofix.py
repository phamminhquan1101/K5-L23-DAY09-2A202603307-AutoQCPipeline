"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict

import yaml

from ..common import ERROR, ROOT, parse_yolo_line


def fix(ds, issues, cfg):
    # Chỉ sửa bản làm việc; dữ liệu raw phải được giữ nguyên.
    if ds.root.resolve() == (ROOT / "data" / "raw").resolve():
        raise ValueError("Không được autofix trực tiếp data/raw; hãy dùng bản sao làm việc.")

    errors = [issue for issue in issues if issue.severity == ERROR]
    fixes = []

    def record(image, line, action, before, after):
        fixes.append(dict(image=image, line=line, action=action,
                          before=before, after=after))

    # Loại ảnh trước để không tiếp tục sửa các dòng nhãn của ảnh đã loại.
    remove_codes = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}
    removed = {
        issue.image for issue in errors
        if issue.code in remove_codes or issue.code.startswith("DUP_IMAGE_")
    }
    for stem in sorted(removed):
        image_path = ds.image_path(stem)
        label_path = ds.label_path(stem)
        paths = [p for p in (image_path, label_path) if p is not None and p.exists()]
        if paths:
            before = "; ".join(p.name for p in paths)
            for path in paths:
                path.unlink()
            record(stem, None, "remove_image", before, "đã loại ảnh và nhãn")

    if any(issue.code == "BAD_CLASS_NAME" for issue in errors):
        before = ds.yaml_path.read_text(encoding="utf-8") if ds.yaml_path.exists() else ""
        data = yaml.safe_load(before) or {}
        expected_names = {i: name for i, name in enumerate(cfg["classes"])}
        if data.get("names") not in (expected_names, list(cfg["classes"])):
            data["names"] = expected_names
            after = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
            ds.yaml_path.write_text(after, encoding="utf-8")
            record("data.yaml", None, "rename_classes", before, after)

    missing = {issue.image for issue in errors if issue.code == "MISSING_LABEL_FILE"}
    for stem in sorted(missing - removed):
        if ds.image_path(stem) is not None and not ds.label_path(stem).exists():
            record(stem, None, "needs_label", "(không có file)", "chuyển người gán")

    drop_codes = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
    line_codes = defaultdict(lambda: defaultdict(set))
    for issue in errors:
        if (issue.image not in removed and issue.line is not None
                and (issue.code in drop_codes or issue.code == "BOX_OUT_OF_IMAGE")):
            line_codes[issue.image][issue.line].add(issue.code)

    for stem, by_line in sorted(line_codes.items()):
        path = ds.label_path(stem)
        if not path.exists():
            continue
        # Đọc cả dòng trống để số dòng khớp với báo cáo ban đầu.
        original = path.read_text(encoding="utf-8").splitlines(keepends=True)
        updated = []
        changed = False
        for line, raw_line in enumerate(original, 1):
            codes = by_line.get(line, set())
            before = raw_line.rstrip("\r\n")
            if codes & drop_codes:
                record(stem, line, "drop_line", before, "")
                changed = True
                continue
            if "BOX_OUT_OF_IMAGE" in codes:
                try:
                    class_id, x, y, w, h = parse_yolo_line(before)
                except (ValueError, OverflowError):
                    record(stem, line, "drop_line", before, "")
                    changed = True
                    continue
                left, top = max(0.0, x - w / 2), max(0.0, y - h / 2)
                right, bottom = min(1.0, x + w / 2), min(1.0, y + h / 2)
                if right <= left or bottom <= top:
                    record(stem, line, "drop_line", before, "")
                    changed = True
                    continue
                if (left, top, right, bottom) != (x - w / 2, y - h / 2, x + w / 2, y + h / 2):
                    box = ((left + right) / 2, (top + bottom) / 2,
                           right - left, bottom - top)
                    after = str(class_id) + " " + " ".join(format(v, ".15g") for v in box)
                    updated.append(after + "\n")
                    record(stem, line, "clip_box", before, after)
                    changed = True
                    continue
            updated.append(raw_line)
        if changed:
            path.write_text("".join(updated), encoding="utf-8")

    return fixes
