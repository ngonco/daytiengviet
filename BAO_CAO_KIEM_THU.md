# Báo cáo kiểm thử — Vietnamese with Vinh

## Khung không blur, chỉnh cắt ảnh và bộ 10 ảnh — v1.3

**51 kiểm thử tự động đều qua; `npm run build` thành công.** Các kiểm thử có sẵn về STT/AI, khóa bài, cắt/khôi phục, phụ đề, xóa phông và legacy tiếp tục qua.

- Ô người nói dùng một video trên nền kem phẳng, giữ phép tính kích thước/vị trí mặt và viền bo góc. Đã kiểm thử bằng video màu xanh rằng khoảng hai bên là kem, không phải hình mở rộng hoặc blur.
- Ảnh minh họa phủ kín vùng ảnh ở 9:16 và 16:9, không dùng blur, giữ tỷ lệ. Kiểm tra ảnh dọc/ngang/vuông, zoom 1–3×, các biên vị trí và ảnh hai màu để xác minh phần được cắt trong khung. Bản dựng dùng cùng phép tính với API hình học của giao diện.
- Lưu hai cấu hình cắt độc lập; chọn ảnh khác đặt lại cấu hình. Cấu hình và bộ ảnh được kiểm tra qua lưu, ZIP, nhập lại, lịch sử và khôi phục. Chọn ảnh tải sẵn được kiểm thử với Pexels/Vilao cố tình không khả dụng: vẫn lưu được, không gọi nhà cung cấp.
- Bộ ảnh tải đủ mười ID khác nhau; kiểm thử loại trùng, tải thiếu, lỗi mạng, hủy sau ba ảnh rồi tiếp tục chỉ tải bảy ảnh còn lại. AI xếp hạng chỉ được chọn ID trong danh sách. Mục lặp dùng lại bộ ảnh; ảnh đang chọn/khóa và vị trí cắt không bị AI dựng lại ghi đè.
- API chuẩn bị ảnh kiểm tra phiên bản, khóa khi dự án đang bận; thử lại tác vụ giữ cùng mã thế hệ bộ ảnh. Bộ mới loại bộ đang hiển thị, không thay ảnh đang chọn. Nếu không đủ ảnh, báo số thật; không nhân bản ảnh để đủ mười.

### Thử nghiệm thật trên máy

Dự án thử riêng **Khung sạch · 10 ảnh mỗi bài** (`88308cdfcbfe4f5d`), video nguồn 59,933 giây. Dùng Pexels và Vilao thật: chuẩn bị đủ 10 ảnh, sau đó tìm đủ bộ 10 ảnh mới không trùng bộ đầu, xác minh ảnh đang chọn được giữ. Không gọi lại Groq. Chọn ảnh từ bộ đã tải và lưu cấu hình cắt dọc/ngang qua API.

Đã xuất **1080×1920** và **1920×1080**, âm thanh stereo, đọc toàn bộ cả hai MP4 bằng FFmpeg. Ảnh trích kiểm tra tại 2 / 12 / 30 / 59 giây; kiểm tra trực quan không còn nền blur hai bên người nói, ảnh phủ kín vùng minh họa. Khung/tóc/miệng và phụ đề tiếp tục dùng vị trí cũ. Viền mảnh được giữ theo lựa chọn người dùng.

Cả hai tỷ lệ dùng lại mã xóa phông `8eeb6d7a5b6c0ce6285645ba`; thời gian sửa tệp manifest không thay đổi, không chạy lại GPU matting. Bốn dự án có sẵn giữ nguyên dữ liệu và phiên bản. ZIP được đọc kiểm tra và đối chiếu mã băm ảnh: giữ ảnh dự phòng, ảnh đang dùng, cách cắt và lịch sử; không chứa cache xóa phông hoặc key.

**Giới hạn kiểm tra giao diện:** trình duyệt tự động đang tắt trong Work settings. Bản này được kiểm tra qua build TypeScript, API thật, kiểm thử và ảnh/video xuất; chưa thao tác kéo ảnh trực tiếp trên trình duyệt ở lượt bàn giao này. Không ghi nhận là đã hoàn tất kiểm thử thao tác chuột.

Chứng cứ riêng tại `OUTPUT/photo_frames/`: `acceptance.json`, hai MP4, ZIP, ảnh trích, `bo_10_anh.jpg` và `hai_khung_khong_blur.jpg`. Toàn bộ nằm ngoài Git.

---


## Xóa phông RVM — bản v1.2, 30/10/2026

Đã cài môi trường CUDA riêng tại `data/runtime/matting`, PyTorch 2.8.0+cu128, RTX 3060 Laptop 6 GB / driver 576.52. Torch 2.8.0+cpu của môi trường cũ giữ nguyên. Mô hình RVM MobileNetV3 official v1.0.0 FP16/FP32 được kiểm tra SHA-256 trước dùng; GPL-3.0 và ghi công đã lưu trong assets/licenses.

Đã tạo dự án thử riêng **Xóa phông · Duyệt chất lượng** (`e623b7fcd42c4415`) từ dữ liệu bài học đã lưu, không gọi thêm Groq/Vilao/Pexels. Hai dự án cũ và dự án khung bài học trước đó giữ nguyên dữ liệu/phiên bản. Dự án mới mặc định bật; dự án cũ thiếu cấu hình luôn tắt cho tới khi người dùng bật.

### Số đo thật trên toàn mẫu 59,933 giây

- 720×1290, đủ **1.798 khung hình ở 30 fps**, mạng nội bộ tối đa cạnh 512, FP16, nhóm 4 sau khung khởi tạo. Không bỏ khung để tăng tốc.
- Lượt tối ưu cuối: **263,55 giây xử lý**, khoảng **6,82 hình/giây** toàn luồng; thời gian tính mô hình trong đó **56,37 giây**. Nạp mô hình từ đĩa riêng **3,04 giây**; lần đầu trước đó có số đo 8,16 giây do khởi tạo lạnh. Thời gian xử lý không bao gồm xuất khung bài học. Chưa đo tốc độ bài dài một giờ.
- Bộ nhớ Torch cấp phát đỉnh **174,96 MiB**, pool giữ tối đa **284 MiB**. Lấy mẫu nvidia-smi mỗi giây trong phần còn lại của toàn lượt xử lý: tổng GPU đỉnh **3.426 MiB**, gồm desktop và app khác, không phải toàn bộ của RVM. Mẫu bắt đầu ở 3.307 MiB; không suy diễn chênh lệch này thành phép đo bộ nhớ từng tiến trình.
- Tải môi trường CUDA khoảng 3,46 GB và mô hình khoảng 23 MB là bước cài riêng. Không ghi được thời gian tải mạng ban đầu, nên không gộp hoặc bịa số đó thành thời gian xử lý video. Báo cáo nạp mô hình bên trên là nạp từ đĩa vào bộ xử lý.
- NVENC lưu màu người 4:4:4 QP16 và bản ghép QP18; alpha xám FFV1 không mất dữ liệu. Luồng Windows dùng bộ đệm 1 MB cố định, giới hạn luồng lọc. CPU encoding có thể dùng nếu NVENC không sẵn sàng; không chuyển suy luận GPU sang CPU ngầm.

**38 kiểm thử tự động đều qua; npm run build thành công.** Có kiểm thử truyền đủ byte qua luồng video, tương thích cũ, nét sửa, OOM, mặt nạ, ranh giới đoạn và ZIP.

### Hành vi đã kiểm tra

- Hủy tác vụ thật sau đoạn 20 giây hoàn tất; SHA-256 mặt nạ đoạn đầu không đổi. Chạy tiếp khôi phục 600 hình và trạng thái mô hình, không bắt đầu lại từ đầu. Lượt tối ưu cuối chạy đủ nguồn từ đầu để đo lại. Kiểm thử mô phỏng OOM xác minh giảm nhóm 4 xuống từng hình mà không đặt lại trạng thái.
- Đổi 9:16 / 16:9 dùng lại cùng mã mặt nạ; xuất 1080×1920 và 1920×1080 với tiếng stereo. Đã đọc hết hai tệp bằng FFmpeg.
- Cắt 19,8–20,2 giây rồi khôi phục không đổi bộ nhớ đệm xóa phông. PCM của bản ghép trước dựng giống hệt nguồn. Đối chiếu tiếng bản dựng sau cắt: tương quan **0,9914**, sai lệch **5 ms**, nằm trong một khung hình.
- Clip riêng 1,3 giây chạy CUDA thật với cọ bỏ: alpha vùng đánh dấu bằng 0, không có cảnh báo mất theo dõi trong clip. Bản mẫu sạch để duyệt không chứa nét thử này.
- Cọ giữ/bỏ, theo dõi tiến về trước, ngừng khi mất độ tin cậy; lưu/khôi phục trạng thái theo dõi qua ranh giới 20 giây. Kiểm thử cấu hình/nét sửa/khóa phiên bản và ZIP xác minh chỉ mang cấu hình, không mang cache/mô hình.
- Đã phát hiện và sửa trường hợp ảnh so sánh nền trống tại cuối đoạn do H.264/FFV1 khác đơn vị thời gian. API hiện lấy chính xác số khung hình; có kiểm thử hồi quy tại 19,9667 / 20,0333 giây và cuối đoạn.
- Kiểm tra tóc, tai, cổ áo, vai, bàn tay và khoảng trống cánh tay trên nền kem/đen/trắng; clip trước/sau nằm ngay trong app. Không xác nhận tương đương CapCut trước khi người dùng xem và duyệt.

**Trạng thái chất lượng: chờ người dùng duyệt clip thực tế.** Viền/cọ thay đổi hiện tạo bộ nhớ đệm mới và chạy lại xóa phông; đổi chữ/ảnh/tỷ lệ/cắt dùng lại kết quả. Nét sửa theo dõi từ mốc đánh dấu tiến về trước, không tự sửa ngược thời gian.

Chứng cứ tại `OUTPUT/matting/`: acceptance.json, gpu-memory.json, cuts-verification.json, kiem_tra_vien.jpg, hai MP4 và ZIP dự án. Đây là dữ liệu riêng đã loại khỏi Git.

---


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
