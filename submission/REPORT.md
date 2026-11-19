# Day 09 Lab — Phạm Minh Quân, 2A202603307

# 1. Kết luận trước

Pipeline kết luận **Hold** . Từ **224 ảnh đầu vào** , bước intake loại **22 ảnh** , còn **202 ảnh** được xuất thành dataset nháp `clean_v1`.

Sau sửa tự động và người duyệt mô phỏng, dataset không còn lỗi bắt buộc. Tuy nhiên, **38/202 ảnh (18,81%)** vẫn còn cảnh báo chưa được duyệt, vượt ngưỡng Hold **10%** . Dataset chưa đủ điều kiện phát hành.

## 2. Lỗi và phân việc

`02_error_list_v1.csv` có **211 dòng lỗi/cảnh báo**, gồm kết quả intake trên 224 ảnh đầu vào và QC trên 202 ảnh được nhận. Bảng dưới đếm dòng báo cáo theo mã, không phải số ảnh độc lập; một ảnh có thể có nhiều lỗi. `CLASS_RARE` và `BAD_CLASS_NAME` là vấn đề cấp dataset.

| Mã lỗi             | Số dòng báo cáo (trên tổng 211) | Ai xử lý             | Vì sao / cách xử lý                                                         |
| -------------------- | ------------------------------------: | ---------------------- | ------------------------------------------------------------------------------- |
| CORRUPT_IMAGE        |                                     2 | Máy (intake)          | Loại ảnh không đọc được                                                 |
| BAD_SIZE             |                                     3 | Máy (intake)          | Loại ảnh không đủ kích thước quy định                                 |
| DUP_IMAGE_EXACT      |                                     8 | Máy (intake)          | Loại bản sao trùng byte                                                      |
| DUP_IMAGE_NEAR       |                                     4 | Máy (intake)          | Loại ảnh gần trùng theo ngưỡng pHash đã chọn                           |
| LEAK_TEST            |                                     5 | Máy (intake)          | Loại ảnh trùng kho test/val để tránh rò rỉ                              |
| MISSING_LABEL_FILE   |                                     6 | Người                | Máy ghi needs_label; người gán, không tạo file rỗng thay thế            |
| BAD_FORMAT           |                                     3 | Máy (autofix)         | Xóa dòng sai định dạng                                                     |
| BAD_CLASS_ID         |                                     6 | Máy (autofix)         | Xóa dòng có ID ngoài danh sách lớp                                        |
| BOX_ZERO             |                                     4 | Máy (autofix)         | Xóa box có chiều rộng/cao không dương                                    |
| BOX_OUT_OF_IMAGE     |                                     8 | Máy (autofix)         | Cắt box vào ảnh; xóa nếu không còn diện tích                           |
| DUP_BOX              |                                     7 | Máy (autofix)         | Xóa dòng box lặp phía sau                                                   |
| BAD_CLASS_NAME       |                                     2 | Máy (autofix)         | Chuẩn hóa names trong data.yaml đúng tên và thứ tự lớp                 |
| EMPTY_LABEL          |                                    12 | Người                | Phân biệt ảnh nền với ảnh bị thiếu nhãn                                |
| BOX_TINY             |                                     6 | Người                | Box nhỏ có thể hợp lệ, cần xem nội dung                                  |
| BOX_HUGE             |                                     3 | Người                | Kiểm tra box lớn có ôm đúng vật thể không                              |
| CLASS_RARE           |                                     4 | Người phụ trách QC | Xem xét phân bố lớp; đây là cảnh báo thống kê, không tự sửa nhãn |
| POSSIBLE_MISSING     |                                    53 | Người                | Xác minh vật thể bị bỏ sót và bổ sung nhãn nếu cần                   |
| POSSIBLE_WRONG_CLASS |                                    18 | Người                | Xác minh lớp đúng vì model đối chiếu cũng có thể sai                 |
| POSSIBLE_LOOSE_BOX   |                                    28 | Người                | Kiểm tra và chỉnh khung nếu lỏng/lệch                                     |
| POSSIBLE_FALSE_POS   |                                    29 | Người                | Kiểm tra box thừa; không xóa chỉ vì model không thấy                    |

**Ưu tiên duyệt:** `05_review_queue.csv` có **125 ảnh**. Điểm là tổng trọng số cảnh báo theo cấu hình (cảnh báo có confidence được nhân thêm hệ số 1 + confidence), cộng điểm cho các thao tác drop_line, clip_box và needs_label. Ảnh img_0020 đứng đầu với **11,524 điểm** do kết hợp FIXED_DROP_LINE, POSSIBLE_MISSING và POSSIBLE_WRONG_CLASS. Sáu ảnh thiếu file nhãn có **10 điểm/ảnh**, được ưu tiên để người gán nhãn. Các ảnh đồng điểm được xếp theo tên để kết quả tái lập.

**Phạm vi người duyệt:** ngân sách cho phép duyệt **80/125 ảnh** trong hàng đợi (64%), còn 45 ảnh chưa duyệt. Đối chiếu `04_error_list_v2.csv` với `06_review_log.csv`, người đã xem **74/103 ảnh có cảnh báo ngữ nghĩa POSSIBLE\_\***, bao phủ **94/123 dòng cảnh báo ngữ nghĩa** trước duyệt. Đây là số nghi vấn được đưa ra xem xét, không phải số lỗi thật đã được xác nhận. Kết quả cuối còn **38/202 ảnh** có cảnh báo chưa duyệt theo gate; số này khác 45 ảnh còn trong hàng đợi vì hàng đợi còn bao gồm ảnh đã được máy sửa và có thể không còn cảnh báo.

## 3. Calibration (2 ngưỡng)

| Tham số                  | Khởi đầu | Đã chọn | Precision / Recall (trước → sau)                                                                           | Lý do (đánh đổi)                                                                                                                     |
| ------------------------- | ----------- | ---------- | ------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `duplicates.phash_dist` | 2           | 14         | `DUP_IMAGE_NEAR`: 100% / 50% → 100% / 67%                                                                  | Bắt thêm ảnh gần trùng so với ban đầu, đồng thời tránh hai trường hợp báo nhầm đã quan sát ở ngưỡng 16             |
| `second_opinion.conf`   | 0.25        | 0.6        | Nhầm lớp: 56% / 83% → 62% / 83%; thiếu nhãn: 50% / 100% → 57% / 100%; box lỏng: 29% / 40% → 20% / 20% | Cải thiện precision ở nhầm lớp và thiếu nhãn, giữ recall của hai nhóm này; chấp nhận khả năng phát hiện box lỏng giảm |

**Lý do không chọn ngưỡng 16:** Trên calib, ngưỡng pHash 16 đạt precision 100%, recall 83% cho ảnh gần trùng. Tuy nhiên, kiểm tra trực quan trên raw cho thấy hai cặp img_0011–img_0008 và img_0177–img_0113 bị báo trùng nhầm. Tôi chọn ngưỡng 14 để hạn chế loại nhầm ảnh tốt, chấp nhận recall trên calib giảm từ 5/6 xuống 4/6.

**Calibration có thể đánh lừa ở đâu:** Bộ calib chỉ có 39 ảnh, nên precision 100% trên calib không bảo đảm không báo nhầm trên raw. Ba cặp ảnh cùng có khoảng cách pHash 16 nhưng hai cặp khác nhau, còn img_0084–img_0074 trùng thật. Một ngưỡng pHash duy nhất không phân biệt được các trường hợp này; giảm ngưỡng có nguy cơ bỏ sót cặp trùng thật.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được

**Kiểm chứng gate:** chạy không có người duyệt:

```powershell
python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb
$LASTEXITCODE
```

Kết quả trong `work/rep_nb/08_summary.json`: còn **6/202 ảnh thiếu file nhãn**, kết luận **Rework**, tương ứng mã thoát **20**. `exported: null` và không có `work/exp_nb/clean_v1`, chứng minh gate chặn xuất khi còn lỗi bắt buộc.

**Hai điểm mù:**

1. **Ảnh gần trùng:** img_0084–img_0074 trùng thật nhưng pHash = 16 > ngưỡng 14 nên bị bỏ sót; tăng lên 16 lại báo nhầm hai cặp khác.
2. **Box lỏng:** tại confidence 0,6, calibration chỉ bắt **1/5 lỗi chèn** (recall 20%), bỏ sót 4/5. Không có cảnh báo chưa bảo đảm nhãn đúng.

### Quan sát thủ công ban đầu

| Ảnh         | Vị trí/vật thể | Lỗi hoặc nghi vấn quan sát được |
| ------------ | ------------------ | -------------------------------------- |
| img_0001.png | Person             | Đánh thiếu người                  |
| img_0004.png | Car                | Không đánh lớp car                 |
| img_0007.png | Car                | Đánh thiếu car                      |

## 5. Train: raw vs clean (tùy chọn, chấm riêng)

Đã chạy trên Kaggle GPU với cùng model `yolo26n.pt`, **20 epoch**, seed **0 và 1**, batch **16**, kích thước ảnh **640**. Hai biến thể dùng chung gold_val (40 ảnh) và test (100 ảnh). Số ảnh train trong bảng là số file được dựng trước khi Ultralytics kiểm tra và có thể bỏ ảnh/nhãn hỏng.

Bảng từ `submission/results/comparison.md` (trung bình ± độ lệch chuẩn giữa hai seed):

| biến thể | #ảnh train | số seed | map50 (TB ± độ lệch) | map50_95 (TB ± độ lệch) | precision (TB ± độ lệch) | recall (TB ± độ lệch) |
|---|---|---|---|---|---|---|
| raw | 224 | 2 | 0.726 ± 0.000 | 0.512 ± 0.004 | 0.764 ± 0.061 | 0.649 ± 0.028 |
| clean | 202 | 2 | 0.701 ± 0.025 | 0.487 ± 0.008 | 0.759 ± 0.003 | 0.625 ± 0.019 |

**Kết luận:** mAP50 clean − raw = **−0,0252** (giảm 2,52 điểm phần trăm), tương đương độ lệch chuẩn của clean **0,0246**; raw có độ lệch chuẩn **0,0002** (bảng làm tròn thành 0,000). Clean thấp hơn raw ở cả hai seed nhưng chỉ có hai lần chạy và 100 ảnh test, nên chưa đủ để kết luận tổng quát. Thí nghiệm hiện tại **không chứng minh clean tốt hơn raw**. AP50 trung bình lớp truck giảm rõ nhất: **0,6485 → 0,5377**.

**Giả thuyết và cách kiểm:** (1) Raw còn ảnh trùng test/val (intake phát hiện 5 trường hợp LEAK_TEST), có thể làm điểm đánh giá lạc quan; cần thí nghiệm đối chứng loại ảnh rò rỉ, giữ nguyên các yếu tố khác. (2) Clean ít hơn 22 ảnh và vẫn Hold với **38/202 ảnh** còn cảnh báo chưa duyệt; có thể mất dữ liệu hữu ích hoặc còn nhãn sai, cần kiểm tra phân bố lớp và nhãn truck, đặc biệt ở ảnh chưa duyệt. Tiếp theo nên chạy thêm seed và thí nghiệm đối chứng; các giả thuyết trên chưa được xác nhận là nguyên nhân.

## 6. Quyết định và ghi chú AI

Quyết định cuối là **Hold** . Dataset `clean_v1` chỉ dùng như bản nháp để thử nghiệm.

Để đủ điều kiện Release, cần xử lý các cảnh báo chưa duyệt theo quy trình dự án, chạy QC lại và xác nhận không còn lỗi bắt buộc, tỷ lệ ảnh cảnh báo chưa duyệt dưới 10%. Không thay đổi ngưỡng gate hoặc ngân sách duyệt để đạt Release.

Ghi chú AI:

- **Prompt chính:** “Dựa trên docstring, cấu hình và test của repo, hỗ trợ triển khai các hàm còn thiếu; giữ đúng định dạng đầu ra, xử lý các trường hợp biên và giải thích logic để tôi kiểm tra.”
- Cách kiểm: đã chạy test riêng từng module và toàn bộ repo, kết quả 79/79 test pass. Tôi cần đọc hiểu và giải thích được code trước khi nộp.
- Một đề xuất AI chưa phù hợp: AI đề xuất thử pHash 16 dựa trên calib. Kiểm tra trực quan trên raw phát hiện hai cặp bị báo trùng nhầm, nên tôi điều chỉnh xuống 14 và ghi nhận đánh đổi bỏ sót ảnh trùng.
