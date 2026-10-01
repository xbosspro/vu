---
name: flow-video
description: Tạo video bằng Google Flow (labs.google/flow) qua giao diện web, dùng Claude in Chrome để điều khiển Chrome đã đăng nhập sẵn của người dùng. Dùng khi người dùng nói "tạo video", "làm clip", "dùng Flow", "Omni Flash"/"Ommi Flash", hoặc gõ /flow-video. Gồm viết lại prompt, chọn model, tạo, chờ, tải về và báo kết quả.
---

# Tạo video bằng Google Flow (điều khiển trình duyệt)

Bạn là người điều phối chính. Người dùng ra lệnh bằng tiếng Việt, bạn tự lo toàn bộ quy trình
trên Google Flow rồi báo lại kết quả ngắn gọn bằng tiếng Việt.

Google Flow không có API công khai, nên mọi thao tác đi qua trình duyệt của người dùng
(Claude in Chrome). Skill này chỉ chạy được trong Claude Desktop / Claude Code trên máy người dùng
khi extension Claude in Chrome đang kết nối. Trước bước trình duyệt đầu tiên, đọc skill
`chrome-browser` (hoặc `anthropic-skills:chrome-browser`) và làm theo nó.

## Cấu hình mặc định

| Mục | Mặc định | Ghi chú |
|---|---|---|
| Trang | https://labs.google/fx/tools/flow | Nếu chuyển hướng sang URL khác thì đi theo |
| Model | Tên model người dùng gọi là "Ommi Flash" / "Omni Flash" | Chọn mục trong danh sách model có tên khớp gần nhất; nếu không có, hỏi người dùng, không tự chọn model khác |
| Tỉ lệ khung hình | 16:9 | Người dùng nói "dọc", "TikTok", "Reels", "Shorts" → 9:16 |
| Số video mỗi prompt | 1 | Tăng chỉ khi người dùng yêu cầu |
| Nơi lưu | Thư mục Downloads của Chrome; nếu có quyền truy cập file, chuyển vào `flow-output/` trong repo | Đặt tên `YYYYMMDD-HHMM-<mo-ta-ngan>.mp4` |

## Quy trình

### 1. Hiểu lệnh
Từ câu lệnh, rút ra: nội dung cảnh, số cảnh, thời lượng, tỉ lệ, phong cách, có ảnh tham chiếu không.
Chỉ hỏi lại khi thiếu thứ không thể đoán hợp lý (ví dụ sản phẩm cụ thể cần xuất hiện).

### 2. Viết prompt
Flow cho kết quả tốt nhất với prompt **tiếng Anh**, cụ thể và có cấu trúc. Viết lại lệnh của
người dùng theo `prompt-guide.md` trong thư mục skill này. Mỗi cảnh một prompt.
Cho người dùng xem prompt trước khi tạo **khi** lệnh lớn (từ 3 cảnh trở lên); lệnh 1–2 cảnh thì tạo luôn.

### 3. Xác nhận chi phí
Mỗi lần tạo tốn credit Flow của người dùng. Nếu tổng số video sẽ tạo lớn hơn 4, nêu con số và
hỏi xác nhận trước. Không bao giờ mua thêm credit, nâng cấp gói hay bấm vào trang thanh toán.

### 4. Mở Flow
1. Gọi `tabs_context_mcp`, rồi mở tab mới bằng `tabs_create_mcp` và `navigate` tới trang Flow.
2. Dùng `read_page` (và chụp màn hình bằng `computer` khi cần) để xem trạng thái.
3. Nếu thấy màn hình đăng nhập Google: dừng, nhờ người dùng tự đăng nhập trong tab đó. Không bao giờ
   tự nhập mật khẩu hay mã xác minh.
4. Mở project mà người dùng chỉ định, nếu không thì tạo project mới (nút kiểu "New project" / "+").

### 5. Thiết lập
Giao diện Flow thay đổi thường xuyên: tìm phần tử theo **chữ và vai trò** đọc được từ `read_page`,
không dựa vào vị trí cố định.
- Chế độ: "Text to Video" mặc định; "Frames to Video" khi có ảnh khung đầu/cuối;
  "Ingredients to Video" khi có ảnh nhân vật/vật thể tham chiếu.
- Mở phần cài đặt (biểu tượng bánh răng/tune gần ô prompt) để chọn model, tỉ lệ khung hình, số kết quả.
- Đọc lại cài đặt sau khi chọn để chắc chắn đã đúng model.

### 6. Tạo video
1. Bấm vào ô prompt, dán prompt (dùng `form_input` hoặc `computer` type), bấm nút tạo (mũi tên/Generate).
2. Với nhiều cảnh: gửi lần lượt từng prompt, không cần chờ cảnh trước xong nếu Flow cho phép xếp hàng.
3. Chờ: mỗi video thường 1–5 phút. Kiểm tra lại khoảng 30–60 giây một lần bằng `read_page`/ảnh chụp,
   tối đa khoảng 10 phút cho mỗi video.
4. Nếu Flow báo lỗi (vi phạm chính sách, hết credit, quá tải): báo nguyên văn lỗi cho người dùng.
   Lỗi chính sách thì đề xuất sửa prompt; không thử lại quá 2 lần cho cùng một prompt.

### 7. Tải về
1. Di chuột/bấm vào video đã xong, chọn nút tải xuống, chọn bản gốc (hoặc bản upscale nếu người dùng yêu cầu).
2. Tránh mọi nút có thể bật hộp thoại xác nhận (ví dụ xoá) — chúng làm treo extension.
3. Nếu có quyền đọc/ghi file trên máy, chuyển file vừa tải vào `flow-output/` và đổi tên như bảng trên.

### 8. Báo cáo
Trả lời ngắn gọn:
- Đã tạo bao nhiêu video, bằng model nào, tỉ lệ nào.
- Đường dẫn file (hoặc "trong thư mục Downloads").
- Prompt đã dùng cho từng cảnh (để người dùng tái sử dụng).
- Cảnh nào lỗi và vì sao.
Đóng các tab bạn đã mở, trừ khi người dùng muốn giữ.

## Lệnh lớn (nhiều cảnh)

Ví dụ "làm video quảng cáo 30 giây cho sự kiện X":
1. Chia kịch bản thành các cảnh ~8 giây (30 giây → 4 cảnh), giữ nhân vật/màu sắc/ánh sáng nhất quán
   bằng cách lặp lại cùng một đoạn mô tả nhân vật và phong cách ở mọi prompt.
2. Cho người dùng duyệt danh sách cảnh + prompt (bước 2–3).
3. Tạo và tải từng cảnh (bước 4–7).
4. Nếu có ffmpeg và quyền chạy lệnh trên máy, ghép theo thứ tự:
   `ffmpeg -f concat -safe 0 -i list.txt -c copy flow-output/<ten>-final.mp4`
   (list.txt gồm các dòng `file 'canh-01.mp4'`). Hoặc gợi ý đưa vào DaVinci Resolve làm B-roll với AutoEdit.

## Khi nào dừng và hỏi
- Extension Claude in Chrome không phản hồi hoặc chưa kết nối.
- Cần đăng nhập, xác minh, hoặc trang yêu cầu thanh toán/nâng cấp.
- Không tìm thấy model người dùng muốn.
- Cùng một thao tác thất bại 2–3 lần.
