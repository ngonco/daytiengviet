# VietCut Studio

Ứng dụng web chạy trên máy Windows, tự dựng video dạy tiếng Việt bằng Groq, Vilao và ảnh Pexels.

Mã nguồn: [ngonco/daytiengviet](https://github.com/ngonco/daytiengviet).

## Khung pastel, xem trực tiếp và Thùng rác (v1.4)

Video dọc đặt **ảnh trên → từ/câu ở giữa → người nói dưới khoảng 30%**. Phụ đề song ngữ nằm ở đáy ảnh trên. Video ngang giữ bố cục người nói trái, bài học phải. Cả hai dùng be/trắng/xanh pastel, chữ navy, viền mảnh và tên kênh nhỏ.

Trong **Bản dựng**, chữ, ảnh, cách cắt và vị trí người nói cập nhật trực tiếp, không cần đợi dựng MP4. Bấm **Lưu** để giữ thay đổi và lịch sử; **Xuất video** dùng bản đã lưu. Nhạc/hiệu ứng âm thanh và cân âm lượng được áp dụng khi xuất. Nội dung quá dài có thông báo; khung giữ trạng thái hợp lệ gần nhất. Tác vụ AI/xóa phông vẫn cần thời gian xử lý và có tiến độ; app báo rõ khi lớp người nói chưa cập nhật. Đổi màu nền tận dụng lớp người/mặt nạ đã có.

App giữ **tối đa 30 dự án hoạt động**, chuyển dự án có **ngày tạo cũ nhất** vào **Thùng rác 7 ngày**. Dự án đang xử lý được giữ tới khi tác vụ kết thúc. Mở **Thùng rác → Khôi phục** để lấy lại; nếu đang đủ 30, một dự án khác cũ nhất sẽ chuyển vào thùng rác. Sau 7 ngày, app xóa hẳn dữ liệu trong thư mục dự án khi đang chạy hoặc lần mở tiếp theo. Video nguồn gốc và bản xuất nằm ngoài thư mục dự án được giữ nguyên. Dữ liệu trong thùng rác vẫn chiếm dung lượng cho tới khi được dọn.

## Khung không blur và 10 ảnh mỗi mục (v1.3)

Ô người nói giữ nguyên kích thước, nền kem phẳng và viền bo góc mảnh; không còn hình mờ mở rộng hai bên. Ảnh minh họa phủ kín ô ở cả 9:16 và 16:9, giữ tỷ lệ và cắt mép dư. Trong tab **Bài học**, kéo ảnh hoặc dùng thanh vị trí/phóng 1–3×; **Đặt lại** đưa về giữa. Mỗi tỷ lệ lưu cách cắt riêng. Đổi sang ảnh khác đặt lại cách cắt; bấm **Lưu & dựng lại** để áp dụng.

Dự án mới chuẩn bị **10 ảnh tải sẵn cho mỗi mục**, AI chọn mặc định. Bấm ảnh trong lưới để đổi, không cần mạng. Dự án đã có dùng nút **Chuẩn bị 10 ảnh**; không tự tìm ảnh khi mở dự án. Có **Bổ sung đủ 10 ảnh**, **Tìm bộ 10 ảnh khác**, từ khóa và tải ảnh riêng. Lưu chỉnh sửa trước khi chuẩn bị bộ ảnh. Tải thiếu sẽ báo số thực có, không lặp ảnh để đủ mười. Hủy/thử lại giữ ảnh đã tải. ZIP giữ bộ ảnh và cách cắt; ảnh và video riêng không đưa lên GitHub.

Bản sửa được dùng khi dựng lại dự án có khung bài học; bản đã xuất được giữ nguyên. Dự án legacy không tự đổi cách dựng. Thay chữ/ảnh/cắt/tỷ lệ tiếp tục dùng lại xóa phông đã có.

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

**Mở ẩn từ Start:** chạy **TAO_BIEU_TUONG_START.cmd** một lần để tạo biểu tượng **Vietnamese with Vinh** trong danh sách ứng dụng Start và tệp **Vietnamese with Vinh.lnk** ngay trong thư mục app. Bản cài hiện tại đã tạo sẵn cả hai.

Bấm Start, tìm **Vietnamese with Vinh**, nhấp phải → **Pin to Start / Ghim vào Bắt đầu**. Hoặc nhấp phải tệp shortcut trong thư mục app rồi ghim. Đây là [cách ghim của Windows](https://support.microsoft.com/en-us/windows/experience/personalization/customize-the-windows-start-menu).

Biểu tượng mở trình duyệt và tự chạy app ẩn, không hiện cửa sổ lệnh. Nếu app đã chạy, chỉ mở lại trang đang phục vụ; bấm liên tiếp không tạo nhiều máy chủ. Đóng tab trình duyệt vẫn để tác vụ đang xử lý tiếp tục. Lỗi khởi động được ghi vào `data/logs/launcher.log`, có thông báo nếu không mở được. Sau khi chuyển thư mục app hoặc đổi môi trường Python, chạy lại tệp tạo biểu tượng và ghim lại nếu cần. Shortcut không tự mở app khi đăng nhập Windows.


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
