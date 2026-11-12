# VietCut Studio

Ứng dụng web chạy trên máy Windows, tự dựng video dạy tiếng Việt bằng Groq, Vilao và ảnh Pexels.

Mã nguồn: [ngonco/daytiengviet](https://github.com/ngonco/daytiengviet).

## Khởi động lại để nạp bản sửa 1.5.3

Chạy **KHOI_DONG_LAI_VIETCUT.cmd** khi không còn tác vụ đang chạy. Tệp kiểm tra đúng tiến trình VietCut của thư mục này, từ chối dừng app khác hoặc tác vụ còn hoạt động, rồi mở lại máy chủ và xác nhận bản mới. Hàng đợi, nguồn, bản đã xuất và cache vẫn giữ nguyên. Nếu dùng lệnh khởi chạy tương đối hoặc không xác minh được tiến trình, tệp sẽ từ chối thay vì tắt nhầm chương trình.

Bộ dựng video mới tự dừng và thử lại theo cơ chế hàng đợi khi FFmpeg không tăng tiến độ trong 3 phút; các đoạn đã xong được dùng lại.

## Khôi phục khi dịch vụ ngắt kết nối

Lỗi ngắt kết nối trong lúc nhận diện lời nói hoặc gọi AI được thử lại tối đa 3 lần, có hiển thị tên dịch vụ và lượt thử. Khi vẫn lỗi tạm thời, chế độ tự động chờ 30/120 giây để thử tiếp. Dữ liệu nhận diện và phân tích đã lưu được dùng lại. Lỗi key/quyền truy cập cần sửa cấu hình trước khi thử lại.

Sau khi cập nhật mã, cần khởi động lại **máy chủ Python VietCut**; đóng tab trình duyệt riêng không nạp lại mã máy chủ.

## Giữ nền, zoom video và cắt thủ công (v1.5.2)

Dự án mới mặc định tick **Không xoá nền video**, gồm cả tạo thủ công và tự động theo thư mục. Bỏ tick khi cần xoá nền bằng GPU. Dự án cũ giữ nguyên lựa chọn đã lưu.

Trong **Bản dựng**, kéo video để chỉnh vị trí, dùng **Zoom video trong khung** (25–400%) và **Đặt lại video** để trở về toàn hình ở giữa. Cài đặt áp dụng toàn video và lưu riêng cho khung dọc/ngang.

Video đã chạy tự động vẫn mở lại để chỉnh sửa: phóng to **Zoom timeline**, cuộn ngang đến đoạn cần bỏ → tua và **Đánh dấu đầu** → **Đánh dấu cuối** → **Cắt bỏ đoạn**. Có thể nhập giây, tiến/lùi từng khung hình, hoặc dùng phím mũi tên trên timeline. Bỏ tick một đoạn cắt để khôi phục đoạn đó. Chọn **Bản dựng** để xem kết quả, rồi **Lưu → Xuất video**. Phụ đề và nội dung bài học dùng cùng mốc cắt, không chạy lại AI.

Với dự án tự động theo thư mục, bản xuất chỉnh sửa được lưu cạnh video nguồn và hiện đường dẫn trên giao diện. Tên trùng được thêm số; video gốc và các bản đã xuất trước vẫn được giữ. Nếu lỗi lưu file, bấm thử lại tác vụ xuất.

Sau cập nhật, khởi động lại máy chủ VietCut và tải lại trang bằng Ctrl + F5 để dùng cả API/giao diện mới.

## Tự cân âm lượng giọng nói (v1.5.1)

**CÁCH DỰNG → Tự cân âm lượng giọng nói** mặc định bật. Bản dựng trực tiếp tự đo nguồn và tăng âm khi nhỏ, giới hạn theo đỉnh âm để tránh vỡ tiếng; có trạng thái đang đo/đã cân. Tắt công tắc để so sánh với mức gốc. Bản gốc vẫn phát âm thanh nguyên bản.

Khi xuất thủ công hoặc tự động theo thư mục, app đo lại âm thanh sau các điểm cắt và cân hai lượt về mức nghe rõ, rồi mới trộn nhạc/hiệu ứng. Nhạc vẫn tự hạ khi có giọng nói. Phần hình và kết quả xoá phông được dùng lại khi chỉ thay đổi cân âm. Nguồn im lặng không bị kéo âm lên vô hạn. Đây là cân âm lượng, không phải lọc tạp âm.

Trên bản sao nguồn thử, âm lượng tăng từ -25,86 lên -16,07 LUFS (khoảng 9,79 LU), giữ nguyên nguồn và thời lượng. File đã xuất trước cập nhật cần **Xuất video** lại để có âm lượng mới; app giữ nguyên các file cũ và lịch sử nguồn đã hoàn tất.

## Tự động dựng và xuất cạnh source (v1.5)

Mở **Tự động dựng → Chọn thư mục → Bật tự động dựng**. App nhận video đang có và video mới trong cả thư mục con, chờ file ổn định ít nhất 10 giây rồi xử lý lần lượt. Video gốc **đến hết 90 giây xuất dọc 1080×1920**, trên 90 giây xuất ngang 1920×1080; phụ đề Việt–Anh, khung bài học và giữ nền gốc mặc định; có thể chọn xoá phông GPU. Bản MP4 cuối được kiểm tra rồi lưu ngay cạnh từng source, không dựng thêm MP4 xem trước.

App nhớ nội dung file dù đổi tên/chuyển thư mục, tận dụng dự án phù hợp và bỏ qua nguồn đã xuất thành công. Lịch sử này vẫn còn khi dự án vào Thùng rác hoặc hết hạn lưu. File xuất không được nhận lại làm nguồn. Lỗi tạm thời thử lại hai lần; nguồn vẫn lỗi được ghi riêng để tiếp tục nguồn khác. Lỗi lưu chỉ thử lại việc lưu, không gọi lại AI. Thiếu GPU hoặc cấu hình cần sửa rồi bấm **Thử lại**. **Tạm dừng nhận nguồn** dừng nhận/xếp việc mới, để tác vụ hiện tại hoàn tất. **Quét ngay** vẫn chờ file ổn định. Giữ VietCut chạy để theo dõi; mở lại app sẽ tiếp tục hàng đợi, không cần giữ tab trình duyệt mở.

Dự án mới để trống tên sẽ tự lấy từ/câu hoặc chủ đề đang dạy. Có nút **Đổi tên**; tên tự đặt được giữ khi thử lại. Tên dự án cũ không tự đổi. Video xuất mới dùng **`<tên bài học> - learn vietnamese.mp4`**, giữ dấu tiếng Việt; nếu file đã tồn tại sẽ thêm số thứ tự. File xuất cũ không bị ghi đè.

Xoá phông v3 sửa lỗi hết hình ở đuôi clip khi thời lượng hình/tiếng lệch nhau, giữ checkpoint và trạng thái theo dõi qua mỗi đoạn. Phần ghép màu/chuyển dữ liệu chuyển sang GPU khi không có nét cọ, giảm ghi tiến độ và không ghép nền hai lần. Đo cùng clip 20 giây trên RTX 3060 Laptop: **127,97 → 61,67 giây**, giảm **51,8%** toàn luồng; mặt nạ tại ba mốc so sánh không đổi. Đây là số đo của clip/máy thử, không phải cam kết tốc độ mọi video hay bằng CapCut. Không dùng SDK thương mại, không đổi Torch CPU và không tự chuyển AI sang CPU.

Sau cập nhật cần khởi động lại máy chủ VietCut rồi tải lại trang; đóng/mở tab riêng không nạp lại mã Python.

## Khung pastel, xem trực tiếp và Thùng rác (v1.4)

Video dọc đặt **ảnh trên → từ/câu ở giữa → người nói dưới khoảng 30%**. Phụ đề song ngữ nằm ở đáy ảnh trên. Video ngang giữ bố cục người nói trái, bài học phải. Cả hai dùng be/trắng/xanh pastel, chữ navy, viền mảnh và tên kênh nhỏ.

Trong **Bản dựng**, chữ, ảnh, cách cắt và vị trí người nói cập nhật trực tiếp, không cần đợi dựng MP4. Bấm **Lưu** để giữ thay đổi và lịch sử; **Xuất video** dùng bản đã lưu. Nhạc/hiệu ứng âm thanh và cân âm lượng được áp dụng khi xuất. Nội dung quá dài có thông báo; khung giữ trạng thái hợp lệ gần nhất. Tác vụ AI/xóa phông vẫn cần thời gian xử lý và có tiến độ; app báo rõ khi lớp người nói chưa cập nhật. Đổi màu nền tận dụng lớp người/mặt nạ đã có.

App giữ **tối đa 30 dự án hoạt động**, chuyển dự án có **ngày tạo cũ nhất** vào **Thùng rác 7 ngày**. Dự án đang xử lý được giữ tới khi tác vụ kết thúc. Mở **Thùng rác → Khôi phục** để lấy lại; nếu đang đủ 30, một dự án khác cũ nhất sẽ chuyển vào thùng rác. Sau 7 ngày, app xóa hẳn dữ liệu trong thư mục dự án khi đang chạy hoặc lần mở tiếp theo. Video nguồn gốc và bản xuất nằm ngoài thư mục dự án được giữ nguyên. Dữ liệu trong thùng rác vẫn chiếm dung lượng cho tới khi được dọn.

## Khung không blur và 10 ảnh mỗi mục (v1.3)

Ô người nói giữ nguyên kích thước, nền kem phẳng và viền bo góc mảnh; không còn hình mờ mở rộng hai bên. Ảnh minh họa phủ kín ô ở cả 9:16 và 16:9, giữ tỷ lệ và cắt mép dư. Trong tab **Bài học**, kéo ảnh hoặc dùng thanh vị trí/phóng 1–3×; **Đặt lại** đưa về giữa. Mỗi tỷ lệ lưu cách cắt riêng. Đổi sang ảnh khác đặt lại cách cắt; bấm **Lưu & dựng lại** để áp dụng.

Dự án mới chuẩn bị **10 ảnh tải sẵn cho mỗi mục**, AI chọn mặc định. Bấm ảnh trong lưới để đổi, không cần mạng. Dự án đã có dùng nút **Chuẩn bị 10 ảnh**; không tự tìm ảnh khi mở dự án. Có **Bổ sung đủ 10 ảnh**, **Tìm bộ 10 ảnh khác**, từ khóa và tải ảnh riêng. Lưu chỉnh sửa trước khi chuẩn bị bộ ảnh. Tải thiếu sẽ báo số thực có, không lặp ảnh để đủ mười. Hủy/thử lại giữ ảnh đã tải. ZIP giữ bộ ảnh và cách cắt; ảnh và video riêng không đưa lên GitHub.

Bản sửa được dùng khi dựng lại dự án có khung bài học; bản đã xuất được giữ nguyên. Dự án legacy không tự đổi cách dựng. Thay chữ/ảnh/cắt/tỷ lệ tiếp tục dùng lại xóa phông đã có.

## Xóa phông tự động (v1.2)

Từ v1.5.2, dự án mới mặc định giữ nền gốc; dự án cũ giữ nguyên và có công tắc bật riêng. Người nói giữ trong ô hiện tại, nền đổi sang kem. Tối ưu một người đứng nói, camera cố định, chuyển động nhẹ.

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

### Chỉnh sửa bản dựng sau khi chạy tự động

- Timeline hiển thị thời gian bản dựng đã nối. Dùng **Tách tại đầu phát**, chọn đoạn rồi **Cắt bỏ đoạn**, hoặc đánh dấu đầu/cuối và kéo mép vùng chọn. Các đoạn còn lại nối theo thứ tự nguồn; không chạy lại AI.
- Có thumbnail, sóng âm, zoom timeline, tiến/lùi từng khung hình, hoàn tác/làm lại thao tác cắt và khôi phục đoạn đã bỏ. Danh sách khôi phục ghi thời gian nguồn. Lưu rồi xuất video để áp dụng thay đổi vào MP4.
- Khung ngang mới: ảnh bên trái, chữ Việt/Anh bên phải, người nói crop trong vòng tròn góc dưới phải. Kích thước vòng tròn mặc định 25% chiều cao, điều chỉnh 15–40%; zoom/kéo video để căn mặt. Mặc định không xoá phông. Khung dọc giữ bố cục hiện tại.
- Giao diện chia danh sách, khung xem và bảng thuộc tính riêng; timeline bên dưới có thể tăng chiều cao. Nếu máy chủ chưa nạp trình chỉnh sửa mới, giao diện sẽ báo cần mở lại VietCut.

### Cắt mạnh và chỉnh sau khi tự động

Sau khi tạo tự động, bản dựng được mở để xem và cắt tiếp trong cùng vùng màn hình. Mở danh sách bài học/phụ đề hoặc thuộc tính khi cần; đóng lại để có khung xem rộng. Kéo hoặc zoom timeline, tách tại đầu phát, chọn đoạn rồi bỏ; preview chuyển ngay đến phần còn lại. Lưu và Xuất nằm ngay trên khung xem.

Cường độ cắt có Nhẹ / Vừa / Mạnh, mặc định Mạnh. Lưu trước rồi bấm Chạy lại cắt tự động để tính lại từ âm thanh và transcript đã có. Bước này chỉ đổi các điểm cắt, giữ nội dung bài học/ảnh/phụ đề; có thể khôi phục từng đoạn hoặc phục hồi phiên bản trước. Giữ các khoảng chờ đọc theo và lượt luyện nói được nhận diện; những lượt lặp không rõ nghĩa vẫn cần người dùng rà soát.

### Space và Chèn im lặng

- Bấm **Space** để phát/tạm dừng. Khi nhập chữ, số hoặc sửa nội dung, Space vẫn dùng để gõ bình thường.
- Đặt đầu phát, chọn **Chèn im lặng +2s**. Bấm lại tại cùng vị trí để cộng dồn 2 → 4 → 6 giây. Sửa ô số giây nếu muốn thời lượng khác.
- Khoảng chèn giữ khung hình trước đó, không phát âm thanh/nhạc nền và không hiển thị phụ đề. Phần phía sau lùi lại đúng thời lượng.
- Mở **Khoảng im lặng đã chèn** để đến vị trí, sửa số giây hoặc xoá. Hoàn tác/Làm lại áp dụng cả điểm cắt và khoảng chèn. Lưu rồi xuất để đưa các khoảng chèn vào MP4. Chức năng dùng trong khung bài học.


### Tự động đẩy GitHub khi khởi động lại

Chạy `KHOI_DONG_LAI_VIETCUT.cmd` sẽ tự kiểm tra thay đổi mã nguồn/tài liệu, quét dữ liệu riêng và khóa API, commit rồi push lên nhánh `main` của `ngonco/daytiengviet`. Không có thay đổi thì không tạo commit mới. Nếu lần trước đã commit nhưng chưa push được, lần sau sẽ thử đẩy lại.

- Chỉ đồng bộ các vị trí mã nguồn, tài liệu, cấu hình và tài nguyên đóng gói của app. Không tự đưa video, dữ liệu dự án, cache, bản xuất hay `.env` lên GitHub.
- Không tự đổi nhánh, pull/merge hoặc force-push. Nếu có xung đột, sai kho, file staged ngoài phạm vi hoặc quét khóa API không đạt, phần đồng bộ sẽ dừng và báo rõ.
- Mất mạng, hết phiên đăng nhập GitHub hoặc thiếu quyền Git: commit đã tạo vẫn được giữ. VietCut vẫn thử khởi động lại; cửa sổ CMD giữ thông báo lỗi để xem. Không tự mở hộp thoại đăng nhập.
- Cần Git đã cài, thông tin tác giả Git đã thiết lập và quyền push hiện có. Lưu chỉnh sửa đang mở trong app trước khi khởi động lại.


### Delete và tự động lưu

- Chọn đoạn trên timeline rồi bấm **Delete** để bỏ đoạn và tự nối phần còn lại. Phím vẫn hoạt động khi chuyển con trỏ sang khu preview; không can thiệp khi đang nhập chữ/số hoặc mở hộp thoại. Có thể Hoàn tác sau khi xóa.
- **Tự động lưu** nằm cạnh nút Lưu/Xuất: mặc định **10 giây**, chọn từ **5 đến 20 giây**. Lựa chọn được nhớ trên trình duyệt này.
- Chỉ gửi lưu khi có thay đổi và dự án không bận. Bản dựng bài học vẫn phát trong lúc lưu nền; có thể cắt/chỉnh tiếp. Trạng thái hiển thị đang lưu, giờ lưu gần nhất hoặc lỗi; lỗi không làm mất bản nháp. Khi có xung đột với cửa sổ khác, tự lưu tạm dừng để tránh ghi đè.
- Tự lưu lưu chỉnh sửa dự án; vẫn bấm **Xuất video** khi cần MP4 mới.

- Phím **I** chèn im lặng tại đầu phát, dùng số giây đang chọn trên timeline (mặc định 2 giây). Bấm nhiều lần riêng biệt để cộng dồn; giữ phím không chèn liên tục. Không kích hoạt khi nhập chữ/số, gõ IME, mở hộp thoại hoặc dự án đang bận.
