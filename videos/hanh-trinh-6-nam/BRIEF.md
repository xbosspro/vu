---
workflow: general-video
flow: automation
storyboard: no
format: 1080x1920 (9:16)
duration: ~51s (driven by voiceover)
language: vi
---

# Hành Trình 6 Năm — Talking head + minimalist edit

**Message:** Từ sinh viên thú y đến chuyên viên dựng phim & media — xuất phát điểm không định nghĩa bạn; sự lì lợm và lòng biết ơn mới đưa bạn tới đích.

## Inputs
- `assets/portrait.png` — ảnh nhân vật (A-roll tạm, ảnh tĩnh + chuyển động camera)
- `assets/voice.mp3` — thoại tiếng Việt (MiniMax TTS), 48.9s
- Kịch bản: `Kich_Ban_TikTok_60s_Hanh_Trinh_6_Nam_Media.docx`
- Video mẫu style: talking head + chữ trắng đậm xen serif nghiêng đỏ, thẻ đỏ/trắng toàn màn hình

## Decisions
- Màu theo video mẫu: đỏ #C8102E / trắng / nền tối; font Be Vietnam Pro + Playfair Display Italic (nhúng local).
- B-roll thay bằng đồ họa line-art tối giản (ống nghe, bàn phím, timeline, lens, gimbal, drone).
- SFX + nhạc nền tổng hợp bằng `tools/synth_audio.py` (catalog HeyGen bị chặn mạng).
- Timing từng từ: canh theo khoảng lặng của file thoại (`transcript.json`) — không có ASR trong môi trường.

## Pending
- A-roll khẩu hình thật (HeyGen/Hedra/LivePortrait) để thay ảnh tĩnh — cần mở mạng `api.heygen.com` hoặc người dùng gửi mp4.

## Rebuild
`python3 tools/synth_audio.py && python3 tools/gen.py && npx hyperframes check && npx hyperframes render`
