# AutoEdit cho DaVinci Resolve

Tự động dựng video **trực tiếp thành timeline trong DaVinci Resolve**:

1. **Cắt khoảng lặng** – bỏ các đoạn im lặng, tạo jump cut gọn gàng.
2. **Tự đảo góc máy** khi quay nhiều camera – tự đồng bộ các camera theo sóng âm rồi cắt qua lại giữa các góc.
3. **Tự chèn B-roll** – rải B-roll đều theo nhịp, hoặc chèn đúng lúc người nói nhắc tới nội dung của clip (khớp từ khoá qua phụ đề `.srt`).

Kết quả là một timeline mới trong project đang mở: camera ở V1, B-roll ở V2, âm thanh chính liền mạch ở A1. Mọi thứ vẫn chỉnh sửa được bình thường trong Resolve.

## Cài đặt

Yêu cầu:
- DaVinci Resolve 18 trở lên (bản **Free** hoặc **Studio**).
- Python 3.8+ (Resolve dùng Python cài trên máy để chạy script).
- **ffmpeg** (miễn phí). Trên Windows chọn 1 trong 2 cách:
  - Tải bản *ffmpeg-release-essentials.zip* tại https://www.gyan.dev/ffmpeg/builds/, giải nén, đổi tên thư mục thành `ffmpeg` và đặt vào thư mục AutoEdit, sao cho có file `ffmpeg\bin\ffprobe.exe`. Không cần sửa PATH.
  - Hoặc mở Command Prompt chạy `winget install Gyan.FFmpeg`, rồi **tắt hẳn và mở lại DaVinci Resolve**.

  AutoEdit tự tìm ffmpeg ở các chỗ trên, trong `PATH`, hoặc ở thư mục ghi trong biến môi trường `AUTOEDIT_FFMPEG_DIR`.

Không cần cài thêm thư viện Python nào.

```bash
git clone https://github.com/xbosspro/vu.git
cd vu
python install_resolve_script.py
```

Lệnh trên thêm mục **AutoEdit** vào menu của Resolve. Khởi động lại Resolve, mở project, vào trang **Edit → Workspace → Scripts → AutoEdit**.

## Cách dùng (giao diện)

1. **Nguồn**: thêm các file camera (camera 1 là góc chính, dùng làm âm thanh chính nếu không có âm thanh rời). Tuỳ chọn: file âm thanh mic rời, thư mục B-roll, file phụ đề `.srt`.
2. **Cắt khoảng lặng**: ngưỡng dB (mặc định -35; phòng ồn thì tăng lên -30), độ dài lặng tối thiểu, khoảng đệm giữ lại trước/sau lời nói.
3. **Đảo góc máy**:
   - *Theo nhịp* – 1 người nói, nhiều góc (toàn + cận): đổi góc ở mỗi chỗ cắt lặng (che jump cut) và khi một shot quá dài.
   - *Theo người nói* – podcast/phỏng vấn, mỗi người một camera có mic riêng: tự chuyển sang camera của người đang nói to nhất. Nếu có camera toàn cảnh, nhập số thứ tự để chuyển về toàn khi cả hai cùng nói hoặc shot quá dài.
4. **B-roll**: bật/tắt, khoảng cách và độ dài mỗi đoạn.
5. Bấm **Phân tích & tạo timeline**.

### Đặt tên B-roll để tự khớp nội dung

Đặt tên file theo nội dung, có thể có dấu: `cà-phê.mp4`, `sai-gon+ban-dem.mp4` (dấu `+` hoặc `,` ngăn các cụm từ). Khi phụ đề có câu "…uống **cà phê**…", clip `cà-phê.mp4` được chèn đúng lúc đó. Phụ đề `.srt` có thể tạo bằng Resolve Studio (Timeline → Create Subtitles from Audio), CapCut, Whisper…, miễn là khớp với file âm thanh gốc chưa cắt.

## Resolve Free và Studio

| | Free | Studio |
|---|---|---|
| Chạy từ menu Workspace → Scripts | ✅ | ✅ |
| Chạy từ terminal/ứng dụng bên ngoài | ❌ | ✅ (bật *Preferences → System → General → External scripting using: Local*) |

## Dòng lệnh

```bash
# Xem trước kế hoạch dựng, không cần mở Resolve
python -m autoedit -c cam1.mp4 -c cam2.mp4 --broll-dir broll --dry-run

# Tạo timeline trong Resolve Studio đang mở
python -m autoedit -c cam1.mp4 -c cam2.mp4 -c wide.mp4 --mode speaker --wide-cam 3 \
    --audio mic.wav --broll-dir broll --srt goc.srt --name "Podcast tập 1"
```

`python -m autoedit --help` để xem tất cả tuỳ chọn. Có thể lưu/đọc cài đặt bằng `--save-config` / `--config`.

## Cấu trúc mã

| File | Việc |
|---|---|
| `autoedit/ffmpeg_tools.py` | Đọc thông tin media, dò khoảng lặng, đo âm lượng bằng ffmpeg |
| `autoedit/silence.py` | Tính các đoạn giữ lại, ánh xạ thời gian gốc → timeline |
| `autoedit/sync.py` | Đồng bộ camera theo sóng âm (thô 100 ms rồi tinh 10 ms) |
| `autoedit/multicam.py` | Chọn góc máy theo nhịp hoặc theo người nói |
| `autoedit/broll.py` | Khớp từ khoá (bỏ dấu tiếng Việt) và rải B-roll |
| `autoedit/planner.py` | Kế hoạch dựng chính xác tới từng frame |
| `autoedit/resolve_bridge.py` | Kết nối Resolve, import media, dựng timeline |
| `autoedit/gui.py`, `autoedit/cli.py` | Giao diện và dòng lệnh |

## Kiểm thử

```bash
pip install pytest
python -m pytest
```

Bộ test tạo video mẫu bằng ffmpeg rồi chạy toàn bộ quy trình với một Resolve giả lập.

## Giới hạn hiện tại

- B-roll chỉ hỗ trợ file video (chưa hỗ trợ ảnh tĩnh).
- Chế độ *theo người nói* cần mỗi camera thu được tiếng của người mình quay rõ hơn người kia.
- Các camera nên cùng frame rate với timeline.
