# Bàn giao v1.1 — khung Vietnamese with Vinh

Ngày **30/10/2026**, múi giờ Việt Nam.

- **28 kiểm thử tự động đều qua**; `npm run build` thành công. Các kiểm thử mới gồm phủ kín mục bài học, giữ nội dung qua mốc 20/120 giây và khi cắt lời nói, khóa chính xác nội dung/ranh giới, tái sử dụng ảnh, từ chối chữ quá dài, tương thích cũ và thử lại chuyển khung không gọi AI thêm.
- Đã chạy thật Groq, Vilao và Pexels trên một dự án mẫu mới riêng. AI xác định một mục **Xin chào — Hello** giữ từ đầu đến cuối video, thay vì tạo mục từ các câu chỉ dẫn như “Repeat after me”.
- Đã kiểm tra trực quan và xuất hai bản cuối: **1080×1920** và **1920×1080**, H.264, AAC stereo, **59,933 giây**. FFmpeg đọc hết cả hai tệp hình/tiếng không có lỗi. Khoảng trống quanh đầu được chỉnh, phụ đề nằm trong ô người nói; ảnh và nội dung chính đứng yên cả mục.
- Đã thao tác giao diện thật: chọn mục, thêm/chia, gộp, xóa, sửa “Xin chào!” / “Hello!”, kiểm tra tự khóa và lưu/dựng lại. Dòng thời gian nối liền trở lại sau khi xóa/gộp.
- Đã sửa và kiểm thử việc dùng lại bộ nhớ đệm: bản xem trước có nội dung giống phiên bản cũ được ghi nhận đúng phiên bản hiện tại, không báo nhầm “chưa cập nhật”.
- ZIP v2 đã nhập lại và dựng thành công, giữ mục bài học và lựa chọn khung. Một bản sao ZIP cũ đã chuyển sang khung mới, giữ nguyên phụ đề/điểm cắt và lưu cách dựng cũ trong lịch sử.
- Hai dự án gốc được so sánh trước/sau và không bị chuyển khung hoặc thay đổi dữ liệu. Bản kiểm tra chuyển đổi chỉ thực hiện trên bản sao riêng.
- Đã quét Git index, không có key đã cấu hình, `.env`, video nguồn, dữ liệu dự án, bản xuất hoặc bộ nhớ đệm trong các tệp chuẩn bị công bố.

Tệp bàn giao mới trong **OUTPUT/frame_v2/**:

| Tệp | Nội dung |
| --- | --- |
| `Vietnamese_with_Vinh_9x16.mp4` | Khung dọc hoàn chỉnh |
| `Vietnamese_with_Vinh_16x9.mp4` | Khung ngang hoàn chỉnh |
| `Vietnamese_with_Vinh_project.zip` | Dự án mẫu khung mới |
| `khung_mau_so_sanh.jpg` | Ảnh kiểm tra hai bố cục |
| `acceptance.json` | Kết quả tích hợp API, ZIP và chuyển đổi |
| `final-verification.json` | Kết quả hai bản xuất cuối và kiểm tra giao diện |

Giới hạn: video thật được kiểm tra là mẫu khoảng một phút. Điều phối 60 phút có kiểm thử giả lập, chưa đo thời gian dựng một giờ Full HD. Phụ đề/dịch và ranh giới AI vẫn có thể cần duyệt; người dùng có thể sửa và khóa từng mục. Cấu hình tự động theo khuôn mặt có thêm điều chỉnh thủ công x/y/kích thước.

Mã nguồn dùng nhánh `main` tại repo người dùng chỉ định; quy trình bàn giao kiểm tra commit từ xa sau push. Chi tiết kiến trúc và hướng dẫn sửa tiếp nằm trong **system_map_daytiengviet.md** và **AGENTS.md**.

---

# Kết quả bàn giao v1.0 trước đó

Ngày: **29/10/2026**, múi giờ Việt Nam.

## Kết quả

App đã triển khai tại thư mục này. Mở **MO_VIETCUT.cmd** để sử dụng. Địa chỉ trên máy hiện tại: **http://127.0.0.1:8876**.

Luồng thực tế đã chạy thành công với key người dùng điền trong `.env`: **Groq → Vilao → Pexels → bản nháp → sửa phụ đề → xuất MP4 → lưu và mở lại dự án**.

- Groq: nhận diện lời nói có mốc thời gian từ và đoạn bằng `whisper-large-v3`.
- Vilao: `jpt/gpt-6-luna`, endpoint đã cấu hình; model đã nhận được ảnh lấy mẫu và trả phương án dựng, bản dịch, thẻ từ vựng, vị trí minh họa.
- Pexels: tìm, lựa chọn và tải ảnh thật qua API. Ghi công tác giả và đường dẫn ảnh được lưu cùng bản xuất.
- App không gửi API key về giao diện. Kiểm tra gói giao diện đã biên dịch không tìm thấy giá trị của ba key.

## Video và dự án bàn giao

| Tệp trong OUTPUT | Kết quả |
| --- | --- |
| `Bai_01_Xin_chao_9x16.mp4` | 1080 × 1920, H.264, 30 fps, AAC stereo, 59,933 giây |
| `Bai_01_Xin_chao_16x9.mp4` | 1920 × 1080, H.264, 30 fps, AAC stereo, 59,933 giây |
| `Bai_01_Xin_chao_Du_an.zip` | Dự án có video nguồn, lời thoại, ảnh, hình thu nhỏ và lịch sử; không chứa `.env` |
| `*.vi.srt`, `*.en.srt` | Phụ đề tiếng Việt và tiếng Anh, theo thời gian bản dựng |
| `*.credits.json` | Tác giả và đường dẫn ảnh đã dùng |

Đã đọc toàn bộ hai tệp MP4 bằng FFmpeg, không gặp lỗi giải mã hình hoặc tiếng. Đã kiểm tra trực quan các thời điểm mở đầu, giải nghĩa, luyện phát âm, ảnh B-roll và kết thúc. Ảnh khác tỷ lệ được đặt trên nền mờ khi cần để giữ đủ nhân vật. Thời lượng luồng hình và tiếng khớp nhau.

## Kiểm thử tự động và giao diện

**15 kiểm thử tự động đều qua.** `npm run build` thành công với TypeScript và Vite.

Các nhóm kiểm thử gồm:

- Ghép điểm cắt chồng nhau, khôi phục đoạn và ánh xạ thời gian phụ đề sau khi cắt.
- Từ lặp phục vụ luyện phát âm được giữ trong bản nhận diện.
- Từ chối thời gian sai, phương án AI vượt độ dài video và giá trị không hợp lệ.
- Phụ đề dấu tiếng Việt, thẻ chữ, ảnh, nhạc nền và hiệu ứng trong bản dựng thực.
- Hình và tiếng vẫn tồn tại sau cắt; âm thanh xuất stereo; bộ nhớ đệm dựng có thể sử dụng lại.
- Model từ chối ảnh hoặc trả JSON lỗi: có thông báo, thử sửa và giữ nguyên đoạn đã khóa.
- Lưu phiên bản và ngăn ghi đè bằng dữ liệu phiên bản cũ.
- Hủy tác vụ đang chạy vẫn khóa chỉnh sửa cho tới khi tác vụ dừng.
- Chặn đường dẫn thoát thư mục dự án, nguồn truy cập khác và phản hồi chứa key.
- Giả lập bài dài 60 phút gồm 12 phần nhận diện: nối đúng thời gian, tránh trùng phần chồng lấn và không gọi lại API với phần đã lưu.

Đã thao tác trên giao diện trình duyệt: mở dự án, xem bản gốc/bản dựng, sửa phụ đề tiếng Việt, kiểm tra khóa tự động, lưu và dựng lại, bấm xuất video, kiểm tra màn hình cấu hình không hiển thị key.

Đã tải ZIP và nhập lại thực tế, xác minh mã SHA-256 của video nguồn trùng bản gốc dự án; phụ đề, khóa đoạn, ảnh và hình thu nhỏ được khôi phục. Kiểm tra tải video theo khoảng byte trả về HTTP 206 để hỗ trợ tua.

## Phạm vi đã xác minh và lưu ý chất lượng

- Kiểm thử API và xuất video thật dùng mẫu khoảng **60 giây** do người dùng cung cấp. Luồng 60 phút đã được kiểm tra bằng dữ liệu nhận diện giả lập; **chưa đo tốc độ dựng một bài 60 phút ở Full HD**.
- Video mẫu chủ yếu nói tiếng Anh xen câu tiếng Việt. Chế độ ép tiếng Việt đã cho bản chép lời không phù hợp; bản bàn giao dùng lựa chọn **chủ yếu tiếng Anh**. Giao diện có đủ tự nhận diện, tiếng Việt và tiếng Anh.
- Nhận diện và bản dịch AI vẫn có thể sai, đặc biệt ở tiếng Anh có giọng địa phương, câu trộn ngôn ngữ và cách đọc mẫu. Có thể nghe lại bản gốc và sửa từng cue; bản dựng là bản nháp biên tập để người dùng duyệt.
- Video mẫu không có đoạn nói vấp rõ cần bỏ, nên AI giữ các lượt nói mẫu và khoảng luyện tập. Chức năng cắt/khôi phục được kiểm tra bằng bài kiểm thử riêng.
- Gọi Groq, Vilao hoặc yêu cầu AI dựng lại cần mạng và sử dụng hạn mức của key đã điền. Dựng lại chỉ từ những thay đổi thủ công sử dụng dữ liệu đã lưu tại máy.

Chứng cứ kiểm thử máy đọc được nằm tại **OUTPUT/final-verification.json**. Mã nguồn, bản đã biên dịch và dữ liệu dự án đều được lưu trước khi thực hiện yêu cầu tắt máy.
