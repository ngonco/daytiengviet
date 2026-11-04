# Xóa phông tại máy — Vietnamese with Vinh

## Cài đặt trên Windows

1. Cài app theo README trước (Python 3.11+, FFmpeg và Node).
2. Chạy **CAI_DAT_XOA_PHONG.cmd**. Lần đầu tải PyTorch CUDA khoảng 3,5 GB và hai mô hình RVM khoảng 23 MB; cần mạng và khoảng 10 GB trống cho bộ xử lý. Video/mặt nạ cần thêm dung lượng riêng.
3. Trong app, mở **Xóa phông tự động → Kiểm tra lại**. Máy này dùng RTX 3060 Laptop 6 GB, driver 576.52, PyTorch 2.8.0+cu128.

Bộ xử lý nằm trong `data/runtime/matting`; mô hình trong `data/runtime/models`. App chính không cài/import Torch CUDA và không thay Torch CPU có sẵn. Nếu không có GPU, app báo rõ: bạn tự chọn **CPU · chạy chậm hơn** hoặc tắt tính năng. Không có chuyển CPU ngầm. Bộ cài hiện cài bản CUDA cho Windows x64; không tự sửa driver NVIDIA.

## Sử dụng

- Dự án mới tự bật xóa phông. Dự án cũ không thay đổi; bật riêng rồi bấm **Lưu & dựng lại** nếu muốn.
- Người nói được ghép lên nền kem và giữ trong ô của khung bài học. Cùng kết quả dùng cho dọc, ngang, đổi chữ/ảnh và cắt/khôi phục lời nói.
- **Xem trước / sau** có video gốc và clip đã xóa phông; nghe/tua bằng nút điều khiển video. Ảnh kiểm tra cho chọn nền kem, đen hoặc trắng.
- **Sửa vùng tại mốc video chính** lấy thời gian video nguồn từ trình xem chính. Chọn cọ giữ/bỏ, cỡ cọ, mốc kết thúc rồi kéo trên ảnh gốc. Lưu để áp dụng. Có thể dùng nút **Dùng mốc clip này để sửa vùng** ngay dưới clip so sánh. Nét sửa bắt đầu ở mốc đánh dấu và theo dõi tiến về trước; không sửa ngược những khung hình trước đó.
- Khi theo dõi mất độ tin cậy, nét sửa dừng áp dụng và app báo thời điểm cần đánh dấu lại. Có thể xóa từng nét. Tối đa 100 nét, mỗi nét 300 điểm.
- Làm mềm viền 0–4 px; co viền số dương, nới viền số âm. Đơn vị là pixel ở độ phân giải làm việc, không phải kích thước bản xem trước.
- Bấm **Dừng** để hủy. **Thử lại** hoặc dựng lại sẽ tiếp tục từ đoạn 20 giây hoàn tất gần nhất. Phần đang làm dở được tính lại; không tái dùng tệp chưa có dấu hoàn tất.

## Tăng tốc và phục hồi (v1.5)

Bộ xử lý v3 giữ nguyên RVM, kích thước và đủ 30 khung/giây. Với GPU và không có nét cọ, chỉ đưa alpha về CPU để tinh viền, giữ RGB trên GPU để ghép nền/đổi sang byte trước khi chuyển về bộ mã hoá. Khi có nét cọ, vẫn dùng đường xử lý giữ/bỏ đầy đủ. Đọc trước hai khung và hàng đợi ghi hai khung cho mỗi lớp có giới hạn bộ nhớ; không tải toàn bộ clip lên RAM. Tiến độ ghi tối đa hai lần/giây, checkpoint từng đoạn vẫn bắt buộc.

Bản ghép nền từng đoạn được dùng thẳng nếu đúng màu và phiên bản; chỉ ghép lại khi đổi màu. Cache v3 phân biệt với v2, không xóa hay ghi đè cache cũ. Lần chạy đầu sau nâng cấp có thể phải xử lý lại; các lần dừng/tiếp tục trong cùng phiên bản dùng đoạn đã hoàn tất và trạng thái mô hình/cọ đã lưu.

Thời lượng container/âm thanh không còn được coi là số khung giải mã chính xác. Bộ giải mã chuẩn hoá từ thời gian nguồn 0 rồi mới bỏ các khung đã xử lý khi tiếp tục, tránh lệch video FPS biến đổi. Khi hết hình sạch, chỉ bù khung cuối cho phần đuôi chênh đã xác minh từ thời gian luồng hình và sai số làm tròn; lỗi giải mã, khung thiếu dữ liệu hoặc hết sớm bất thường vẫn dừng với thông báo. Chi tiết lỗi kỹ thuật nằm trong `matting/<mã>/failure.json` tại máy.

Đo ngày 04/11/2026 trên RTX 3060 Laptop 6 GB, cùng bản sao clip 20,011 giây, CUDA FP16/NVENC, cache mới: **127,969 giây trước → 61,668 giây sau**, giảm **51,81%** toàn luồng. Cache có sẵn của clip thử trả kết quả trong khoảng 0,022 giây, gồm kiểm tra hash. Alpha ở 0,2 / 5 / 19,9 giây giống từng byte; đã xem trên nền đen/trắng/kem. Bản sao nguồn lỗi 63,301 giây hoàn tất sau huỷ/tiếp tục tại checkpoint 600 khung, giữ nguyên các file checkpoint và giải mã toàn bộ thành công. Không suy rộng số đo này thành cam kết CapCut hoặc mọi clip.

`stats.json` có `timings`: chờ đọc/giải mã, đưa lên GPU, đưa về CPU, sửa viền/cọ, ghép/đóng gói, ghi bộ mã hoá và chờ kết thúc mã hoá. Các giai đoạn chạy chồng lấp; không cộng các mục này để suy ra thời gian toàn luồng. Dùng `python -m scripts.benchmark_matting_speed --source <bản-sao-clip> --baseline <runner-trước-sửa>` để đo có kiểm soát; không chạy đồng thời hai việc GPU. `python -m scripts.acceptance_matting_recovery --source <bản-sao-clip>` kiểm tra huỷ/tiếp tục và EOF. Hai công cụ chỉ tạo dữ liệu riêng trong OUTPUT, không gọi dịch vụ AI hoặc sửa dự án có sẵn.

## Kỹ thuật và dữ liệu

RVM MobileNetV3 official release v1.0.0; FP16 CUDA, FP32 khi người dùng chọn CPU. Xử lý tuần tự CFR 30 fps; cạnh dài đầu vào tối đa 1920, mạng nội bộ tối đa 512. Khởi tạo bằng một hình 4D (yêu cầu của TorchScript upstream), sau đó nhóm 4 hình; khi GPU hết bộ nhớ giảm xuống từng hình. Bốn tensor ghi nhớ được lưu sau mỗi đoạn, không đặt lại tại ranh giới 20 giây.

Mỗi đoạn có lớp màu người H.264 yuv444p, mặt nạ xám FFV1 không mất dữ liệu, bản ghép kem, trạng thái mô hình NPZ không pickle và trạng thái theo dõi vùng. Màu người được nén QP16 bằng NVENC khi có, hoặc CRF16 bằng CPU; mặt nạ không bị nén mất dữ liệu. Bộ mã hóa GPU giảm tải CPU, nhưng phép đo toàn luồng vẫn gồm đọc/ghi, tinh viền và lưu lớp. Luồng Windows dùng bộ đệm 1 MB cố định thay cho 4 KB mặc định. Âm thanh luôn lấy từ bản nguồn, qua cùng bản đồ cắt như trước.

Bộ nhớ đệm phụ thuộc toàn bộ byte video nguồn, mã băm mô hình, phiên bản xử lý, kích thước, tham số viền và nét sửa; bản ghép màu có mã riêng. Đổi tỷ lệ, bài học, ảnh hoặc điểm cắt dùng lại kết quả. Đổi viền/cọ hiện tính lại bước xóa phông cho cấu hình đó; chưa tách riêng bộ nhớ đệm thô và bước sửa viền.

ZIP chỉ mang cấu hình và nét sửa trong options, không mang mô hình, môi trường GPU, mặt nạ hay trạng thái xử lý. Khi nhập, app tạo lại kết quả tại máy. Tất cả dữ liệu này nằm ngoài Git.

## Chẩn đoán

- GPU chưa sẵn sàng: chạy lại bộ cài, kiểm tra driver và chọn lại trạng thái trong app. Bộ cài không đụng môi trường Python khác.
- Mã băm mô hình không khớp: chạy lại bộ cài để tải đúng tệp chính thức. Không bỏ qua kiểm tra này.
- Hết bộ nhớ GPU: app thử nhóm một hình; nếu vẫn thiếu, đóng app dùng GPU khác rồi thử lại hoặc chủ động chọn CPU.
- Viền kém: xem cả nền đen/trắng, thử co/nới/làm mềm ít một, dùng cọ và đánh dấu lại nếu cần. Thay đổi ánh sáng mạnh, người khác đi ngang hoặc camera di chuyển nằm ngoài cảnh tối ưu.
- Cần chẩn đoán tốc độ: xem `matting/<mã>/stats.json` trong dự án; tách thời gian nạp mô hình, xử lý khung hình, số hình tiếp tục và bộ nhớ GPU. Không so số đo trên máy khác như một cam kết cho máy này.

Mốc CapCut là yêu cầu chất lượng mong muốn. Người dùng duyệt clip trong app trước khi xác nhận đạt; không có bảo đảm tự động tương đương CapCut cho mọi video.

Nguồn chính thức: [RVM inference](https://github.com/PeterL1n/RobustVideoMatting/blob/master/documentation/inference.md), [PyTorch CUDA 12.8](https://pytorch.org/get-started/previous-versions/). Ghi công và GPL-3.0 của RVM nằm trong `assets/licenses/`.
