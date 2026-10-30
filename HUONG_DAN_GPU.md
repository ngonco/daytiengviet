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

## Kỹ thuật và dữ liệu

RVM MobileNetV3 official release v1.0.0; FP16 CUDA, FP32 khi người dùng chọn CPU. Xử lý tuần tự CFR 30 fps; cạnh dài đầu vào tối đa 1920, mạng nội bộ tối đa 512. Khởi tạo bằng một hình 4D (yêu cầu của TorchScript upstream), sau đó nhóm 4 hình; khi GPU hết bộ nhớ giảm xuống từng hình. Bốn tensor ghi nhớ được lưu sau mỗi đoạn, không đặt lại tại ranh giới 20 giây.

Mỗi đoạn có lớp màu người H.264 yuv444p, mặt nạ xám FFV1 không mất dữ liệu, bản ghép kem, trạng thái mô hình NPZ không pickle và trạng thái theo dõi vùng. Màu người được nén QP16 bằng NVENC khi có, hoặc CRF16 bằng CPU; mặt nạ không bị nén mất dữ liệu. Bộ mã hóa GPU giảm tải CPU, nhưng phép đo toàn luồng vẫn gồm đọc/ghi, tinh viền và lưu lớp. Luồng Windows dùng bộ đệm 1 MB cố định thay cho 4 KB mặc định. Âm thanh luôn lấy từ bản nguồn, qua cùng bản đồ cắt như trước.

Bộ nhớ đệm phụ thuộc toàn bộ byte video nguồn, mã băm mô hình, phiên bản xử lý, kích thước, màu kem, tham số viền và nét sửa. Đổi tỷ lệ, bài học, ảnh hoặc điểm cắt dùng lại kết quả. Đổi viền/cọ hiện tính lại bước xóa phông cho cấu hình đó; chưa tách riêng bộ nhớ đệm thô và bước sửa viền.

ZIP chỉ mang cấu hình và nét sửa trong options, không mang mô hình, môi trường GPU, mặt nạ hay trạng thái xử lý. Khi nhập, app tạo lại kết quả tại máy. Tất cả dữ liệu này nằm ngoài Git.

## Chẩn đoán

- GPU chưa sẵn sàng: chạy lại bộ cài, kiểm tra driver và chọn lại trạng thái trong app. Bộ cài không đụng môi trường Python khác.
- Mã băm mô hình không khớp: chạy lại bộ cài để tải đúng tệp chính thức. Không bỏ qua kiểm tra này.
- Hết bộ nhớ GPU: app thử nhóm một hình; nếu vẫn thiếu, đóng app dùng GPU khác rồi thử lại hoặc chủ động chọn CPU.
- Viền kém: xem cả nền đen/trắng, thử co/nới/làm mềm ít một, dùng cọ và đánh dấu lại nếu cần. Thay đổi ánh sáng mạnh, người khác đi ngang hoặc camera di chuyển nằm ngoài cảnh tối ưu.
- Cần chẩn đoán tốc độ: xem `matting/<mã>/stats.json` trong dự án; tách thời gian nạp mô hình, xử lý khung hình, số hình tiếp tục và bộ nhớ GPU. Không so số đo trên máy khác như một cam kết cho máy này.

Mốc CapCut là yêu cầu chất lượng mong muốn. Người dùng duyệt clip trong app trước khi xác nhận đạt; không có bảo đảm tự động tương đương CapCut cho mọi video.

Nguồn chính thức: [RVM inference](https://github.com/PeterL1n/RobustVideoMatting/blob/master/documentation/inference.md), [PyTorch CUDA 12.8](https://pytorch.org/get-started/previous-versions/). Ghi công và GPL-3.0 của RVM nằm trong `assets/licenses/`.
