# VietCut Studio

Ứng dụng web chạy trên máy Windows, tự dựng video dạy tiếng Việt bằng Groq, Vilao và ảnh Pexels.

Mã nguồn: [ngonco/daytiengviet](https://github.com/ngonco/daytiengviet).

## Xóa phông tự động (v1.2)

Dự án mới tự bật xóa phông; dự án cũ giữ nguyên và có công tắc bật riêng. Người nói giữ trong ô hiện tại, nền đổi sang kem. Tối ưu một người đứng nói, camera cố định, chuyển động nhẹ.

Chạy **CAI_DAT_XOA_PHONG.cmd** để cài bộ GPU riêng. Có xem clip trước/sau, kiểm tra nền kem/đen/trắng, co/nới/làm mềm viền và cọ giữ/bỏ theo thời gian nguồn. Đổi khung dọc/ngang hoặc sửa chữ/ảnh dùng lại kết quả. Hủy và thử lại tiếp tục từ đoạn 20 giây đã hoàn tất.

Xem **HUONG_DAN_GPU.md** để cài, sửa vùng và chẩn đoán. Chất lượng mong muốn lấy CapCut làm mốc; cần người dùng duyệt clip thực tế trước khi xác nhận đạt.

## Khung bài học — Vietnamese with Vinh (v1.1)

Dự án mới dùng khung kem/xanh đậm với tên kênh nhỏ **Vietnamese with Vinh**. Video dọc có người nói phía trên khoảng 30% chiều cao; video ngang có người nói bên trái khoảng 1/3 chiều rộng. Từ/câu, nghĩa và một ảnh Pexels giữ nguyên suốt từng mục bài học, kể cả lúc đọc mẫu và chờ người học nhắc lại. Phụ đề Việt–Anh thay đổi trong ô người nói.

Tab **Bài học** cho sửa nội dung, nghĩa, tối đa ba cụm giải thích, ảnh và ranh giới; có chia mục, gộp mục sau và xóa mục. Gộp giữ nội dung/ảnh của mục đang chọn. Xóa mở rộng mục liền kề để không tạo khoảng trống. Chỉnh tay mặc định khóa mục khi AI sửa lại.

Dự án cũ vẫn dùng cách dựng ban đầu. Bấm **Chuyển sang khung bài học** nếu muốn; app dùng lời thoại đã lưu, giữ phụ đề và điểm cắt, lưu phiên bản cũ để khôi phục. Có điều chỉnh tâm và kích thước người nói nếu vị trí tự động chưa phù hợp.

Phông Noto Sans/Noto Serif được đóng gói trong app, có giấy phép OFL kèm theo. Các phần chữ quá dài sẽ được báo để rút gọn hoặc chia mục, thay vì cắt mất nội dung.

Agent phát triển tiếp cần đọc **system_map_daytiengviet.md** và **AGENTS.md**. Sau khi kiểm thử qua, cập nhật tài liệu, kiểm tra `python scripts/verify_staged.py`, rồi commit/push lên nhánh main của repo người dùng chỉ định.

## Mở app

Nhấp đúp **MO_VIETCUT.cmd**, giữ cửa sổ chạy app mở. Trình duyệt tự mở tại địa chỉ ghi trong `.env` (máy hiện tại: **http://127.0.0.1:8876**).

Nếu cần cài lại thư viện hoặc chuyển sang máy mới, cài Python 3.11+, Node.js 20.19+/22.12+ và FFmpeg có bộ lọc subtitles, sau đó chạy **CAI_DAT.cmd**. Bản đã biên dịch nằm trong `dist/`.

## Cách dùng

1. Tạo dự án, chọn video hoặc dùng video mẫu trong thư mục. Hỗ trợ tới 60 phút, chọn dọc 9:16, ngang 16:9 hoặc giữ tỷ lệ gốc.
2. Chọn ngôn ngữ **chủ yếu tiếng Anh** nếu bạn giảng bằng tiếng Anh xen ví dụ tiếng Việt, như video mẫu. Chọn **chủ yếu tiếng Việt** cho bài giảng bằng tiếng Việt, hoặc để tự nhận diện.
3. Chờ app nhận diện, phân tích, tìm ảnh và dựng bản nháp. Theo dõi tiến độ trên màn hình. Kết quả mỗi bước được lưu tại máy.
4. Nhấp lời thoại, minh họa hoặc điểm cắt để sửa. Thời gian ở bảng chỉnh sửa và dòng thời gian luôn là thời gian **video gốc**. Tệp phụ đề xuất ra dùng thời gian **bản dựng**.
5. Bấm **Lưu & dựng lại**. Đoạn chỉnh tay mặc định được khóa để AI giữ lại. Có thể mở khóa theo từng đoạn.
6. Có thể yêu cầu AI sửa bằng lời, ví dụ: “giảm ảnh toàn khung, giữ mọi khoảng nghỉ luyện phát âm”. Lưu chỉnh sửa trước khi gửi yêu cầu.
7. Bấm **Xuất video**, chờ hoàn tất, rồi tải MP4, SRT Việt, SRT Anh hoặc dự án ZIP.

Trong tab Minh họa, có thể tìm ảnh Pexels khác hoặc tải ảnh riêng. Thêm nhạc tại phần Cách dựng; app tự hạ nhạc khi có giọng nói. Nhạc và ảnh riêng do bạn lựa chọn quyền sử dụng.

## Phong cách

- **9:16:** mặc định sôi động, zoom nhẹ, thẻ chữ và ảnh chuyển động, hiệu ứng âm thanh ngắn.
- **16:9:** mặc định giáo dục hiện đại, hình minh họa gọn và ít chuyển động hơn.
- Có thể đổi phong cách, phụ đề, mật độ minh họa, bật/tắt hiệu ứng và điều chỉnh khung hình.
- Giữ toàn bộ hình gốc với nền mờ là mặc định khi đổi tỷ lệ. Chế độ cắt lấp đầy có thanh chỉnh tâm cắt ngang.

## API key

Điền `GROQ_API_KEY`, `VILAO_API_KEY`, `PEXELS_API_KEY` trong `.env`; không gửi key vào chat hoặc chia sẻ tệp này. App đọc lại cấu hình khi chạy tác vụ hoặc kiểm tra kết nối, không cần gửi key qua giao diện.

Vilao mặc định dùng `jpt/gpt-6-luna` và `https://api.vilao.ai/v1`. Có thể thay trong `.env`. Khi model không nhận ảnh, app báo và phân tích bằng lời thoại. Ảnh minh họa có đường dẫn ghi công Pexels và tác giả trong dự án.

Âm thanh được gửi tới Groq; lời thoại và khung hình lấy mẫu được gửi tới Vilao; từ khóa được gửi tới Pexels. Ghép video thực hiện bằng FFmpeg trên máy. Phụ đề, bản dịch và quyết định dựng là đề xuất AI, có thể cần nghe lại, nhất là câu trộn nhiều ngôn ngữ hoặc phát âm mẫu.

## Dữ liệu và khôi phục

- Video gốc ban đầu không bị sửa. Dự án có bản sao nguồn, dữ liệu nhận diện, phương án, ảnh, phiên bản và bản dựng trong `data/projects/`.
- Đóng/mở lại app giữ nguyên dự án. Tác vụ đang chạy sẽ được tiếp tục từ các bước đã lưu khi app khởi động lại.
- **Dừng** hủy tác vụ và giữ kết quả từng bước. Khi yêu cầu mạng đang chờ phản hồi, việc dừng có thể cần chờ yêu cầu đó kết thúc.
- **Phiên bản** cho phép khôi phục phương án cũ. **Mở dự án đã lưu** nhập lại ZIP vào một dự án mới.
- ZIP chứa video, ảnh, nhạc, lời thoại và phương án, không chứa API key. Nhập lại dự án sẽ dựng bản xem trước mới bằng key hiện tại.
- Chỉ xóa bộ nhớ đệm khi app đã dừng; dữ liệu cần giữ là `studio.sqlite`, video nguồn và toàn bộ thư mục dự án.

## Kiểm thử

Chạy `python -m unittest discover -s tests -v` và `npm run build`.

Các kiểm thử tự động dùng dữ liệu giả lập, không gửi yêu cầu API trả phí. Kết quả kiểm thử thật và các giới hạn đã kiểm tra được ghi trong `BAO_CAO_KIEM_THU.md`.

## Phát triển

Backend: `python -m uvicorn backend.app:app --host 127.0.0.1 --port 8876`.

Frontend: `npm run dev` (kết nối backend theo APP_PORT trong `.env`).

Giao diện React/TypeScript; backend FastAPI; SQLite lưu tiến độ; FFmpeg dựng từng đoạn và tái sử dụng các đoạn không thay đổi. Âm thanh trung gian PCM tránh tích lũy độ trễ AAC khi ghép bài dài.
