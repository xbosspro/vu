# AutoEdit cho DaVinci Resolve

Tự động dựng video **trực tiếp thành timeline trong DaVinci Resolve**, dành cho quay sự kiện, phỏng vấn, podcast nhiều máy:

1. **Đồng bộ nhiều camera**: mỗi camera là một thư mục gồm nhiều clip quay rải rác. Clip được xếp sơ bộ theo giờ quay (tên file DJI/điện thoại, metadata, timecode), rồi khớp chính xác theo sóng âm với Cam 1. App tự phát hiện đồng hồ các máy lệch nhau.
2. **Cắt phần thừa**: bỏ khoảng lặng (khi mọi camera đều im) và các đoạn không máy nào quay.
3. **Tự đảo góc máy**: theo nhịp, hoặc theo người đang nói.
4. **Tự chèn B-roll**: rải đều, hoặc chèn đúng lúc người nói nhắc tới nội dung của clip.

Timeline tạo ra:

| Track | Nội dung |
|---|---|
| V1 + A1 | Cam 1 |
| V2 + A2 | Cam 2 |
| V3 + A3 … | Cam 3 … |
| Track video trên cùng | B-roll |

Mỗi camera nằm đủ trên track của mình. Ở mỗi thời điểm, góc máy được chọn là lớp trên cùng đang bật; các đoạn của camera ở track cao hơn bị **tắt (disable)** chứ không bị xoá. Muốn đổi góc, chọn đoạn đó và bấm **D** để bật lại. Nếu chọn chế độ đảo góc "Tắt", mọi track đều bật để bạn tự dựng.

> Âm thanh của tất cả camera đều nằm trên timeline (A1, A2…). Thường bạn chỉ cần giữ track mic tốt nhất và tắt tiếng các track còn lại.

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

1. **Nguồn**: bấm **Chọn thư mục...** cho Cam 1, Cam 2. Bấm **+ Thêm camera** nếu có thêm máy. Mỗi thư mục chứa toàn bộ clip của một máy (tìm cả trong thư mục con; bỏ qua thư mục Proxy). **Cam 1 là máy chuẩn**: nên chọn máy quay liên tục nhất và thu tiếng tốt nhất.
2. **Cắt phần thừa**: bật/tắt cắt khoảng lặng, ngưỡng dB (mặc định -35; sự kiện ồn thì tăng lên -30 hoặc -25), độ dài lặng tối thiểu, khoảng đệm.
3. **Đảo góc máy**:
   - *Theo nhịp*: đổi góc ở mỗi chỗ cắt và khi một shot quá dài. Hợp với sự kiện, 1 người nói nhiều góc.
   - *Theo người nói*: podcast/phỏng vấn, mỗi người một camera có mic riêng. Nhập số camera toàn cảnh nếu có.
   - *Tắt*: chỉ xếp chồng các camera đã đồng bộ để bạn tự dựng.
4. **B-roll**: bật/tắt, khoảng cách và độ dài mỗi đoạn.
5. Bấm **Phân tích & tạo timeline**. Log hiển thị từng bước: độ lệch đồng hồ giữa các máy, số clip khớp được, thời lượng trước/sau khi cắt.

Nếu log báo `! ... không khớp được âm thanh`, clip đó được đặt theo giờ quay. Nguyên nhân thường là Cam 1 không quay đoạn đó, hoặc âm thanh quá khác nhau (máy ở xa, tắt mic).

**Tăng tốc:** cài `pip install numpy` để đồng bộ nhanh hơn với sự kiện dài nhiều giờ. Không cài cũng chạy được.

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
python -m autoedit -c "E:/Su kien/Cam 1" -c "E:/Su kien/Cam 2" --broll-dir broll --dry-run

# Tạo timeline trong Resolve Studio đang mở
python -m autoedit -c "Cam 1" -c "Cam 2" -c "Cam 3" --mode speaker --wide-cam 3 \
    --broll-dir broll --name "Podcast tập 1"
```

`python -m autoedit --help` để xem tất cả tuỳ chọn. Có thể lưu/đọc cài đặt bằng `--save-config` / `--config`.

## Cấu trúc mã

| File | Việc |
|---|---|
| `autoedit/ffmpeg_tools.py` | Đọc thông tin media, giờ quay, đo âm lượng bằng ffmpeg |
| `autoedit/sources.py` | Tìm clip trong thư mục camera, ước lượng giờ quay |
| `autoedit/silence.py` | Tìm khoảng lặng, tính các đoạn giữ lại |
| `autoedit/sync.py` | Đồng bộ mọi clip lên trục thời gian của Cam 1 (0,25 s → 50 ms → 10 ms) |
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

Bộ test dựng một "sự kiện" mẫu bằng ffmpeg: 2 máy, mỗi máy 2 clip, đồng hồ Cam 2 lệch 37 giây. Sau đó test chạy toàn bộ quy trình với một Resolve giả lập.

## Giới hạn hiện tại

- B-roll chỉ hỗ trợ file video (chưa hỗ trợ ảnh tĩnh).
- Chế độ *theo người nói* cần mỗi camera thu được tiếng của người mình quay rõ hơn người kia.
- Các camera nên cùng frame rate với timeline.
- Clip chỉ có ở camera khác mà Cam 1 không quay cùng lúc sẽ được đặt theo giờ quay, không khớp được bằng âm thanh.
- Tắt các đoạn góc máy không chọn cần Resolve 18.5 trở lên.
