# OptiBot Support Sync — Google AI Studio (Gemini)

Một hệ thống tự động cào bài viết (scrape) từ Help Center của OptiSigns, chuyển đổi sang Markdown sạch sẽ và tích hợp RAG (Retrieval-Augmented Generation) thông qua Google Gemini 2.5 Flash trên Google AI Studio.

Hệ thống được thiết kế tối ưu cho **Free Tier của Google AI Studio** bằng cách xếp hạng tài liệu cục bộ để tránh bị chạm giới hạn quota 250k tokens/phút.

---

## Kiến trúc hệ thống (RAG)

```
Zendesk API  ──(Daily Sync)──>  Thư mục Articles (.md) + Delta Tracker (hashes_gemini.json)
                                         ↓
User Query  ──>  Xếp hạng từ khóa cục bộ (Chọn 15 bài phù hợp nhất)
                                         ↓
Context (Prompt)  ──>  Google Gemini 2.5 Flash  ──>  Câu trả lời (+ Trích dẫn)
```

---

## Bắt đầu nhanh (Quick Start)

### 1. Chuẩn bị
- Python 3.11+
- Một API key miễn phí từ Google AI Studio → [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)

### 2. Cài đặt thư viện
```bash
git clone https://github.com/Duylap-2601/Mini_Chatbot.git
cd Mini_Chatbot
pip install -r requirements.txt
```

### 3. Cấu hình môi trường
Copy file mẫu cấu hình `.env.sample` thành `.env`:
```bash
cp .env.sample .env
```
Mở file `.env` và điền khóa của bạn:
```env
GOOGLE_API_KEY=AIzaSy...your_gemini_key_here...
```

### 4. Đồng bộ dữ liệu lần đầu (Sync Pipeline)
Chạy script để tải toàn bộ bài viết từ Help Center về local máy:
```bash
python main.py
```
- **Lần chạy đầu tiên:** Tải toàn bộ 404 bài viết, chuyển sang Markdown và lưu vào thư mục `articles/`.
- **Các lần chạy sau:** Chỉ cập nhật/thêm các bài viết có thay đổi nội dung (sử dụng hash SHA-256 để so sánh delta).

### 5. Chạy thử trợ lý (Test CLI)
Chạy demo tự động kiểm tra 5 câu hỏi mẫu của hệ thống:
```bash
python test_gemini.py --demo
```
Hoặc chạy chế độ chat trực tiếp (Interactive Mode):
```bash
python test_gemini.py
```

---

## Triển khai Docker (Railway)

### Chạy bằng Docker cục bộ
Build và chạy một lần:
```bash
docker build -t optibot-sync-gemini -f Dockerfile .
docker run --env-file .env \
           -v $(pwd)/state:/app/state \
           -v $(pwd)/logs:/app/logs \
           optibot-sync-gemini
```

### Triển khai tự động hàng ngày trên Railway
Ứng dụng được thiết lập chạy định kỳ lúc **02:00 UTC** hàng ngày. 
- **Đường dẫn xem Logs chạy thực tế (Daily Job Logs):** [Xem Logs trên Railway](https://railway.com/project/0b720fe3-5d5c-413b-90a5-1ccc5e3b7e99/service/0393b025-f1dc-474a-b06c-f1e0df54292e)
1. Kết nối Repository GitHub này vào dự án Railway của bạn.
2. Thiết lập biến môi trường trên Railway Dashboard:
   - `GOOGLE_API_KEY` = Khóa API Gemini của bạn.
   - `ZENDESK_BASE_URL` = `https://support.optisigns.com`
   - `ARTICLES_DIR` = `articles`
3. Cấu hình lịch chạy tự động (cronjob) đã được cài đặt sẵn qua file `railway.json`: `0 2 * * *`.

---

## Chi tiết Cơ chế Tìm kiếm Lọc (Hybrid Retrieval)

Vì Gemini Free Tier giới hạn **250,000 tokens/phút**, việc nhồi toàn bộ 404 bài viết (~500,000 tokens) vào prompt trong mỗi lượt hỏi sẽ ngay lập tức gây lỗi quá tải quota (`RESOURCE_EXHAUSTED`).

Để khắc phục, OptiBot sử dụng thuật toán tìm kiếm từ khóa cục bộ siêu nhẹ bằng Python:
1. Tách từ khóa của câu hỏi, bỏ các từ dừng (stop-words) và thêm từ dừng đặc trưng (`optisigns`).
2. Tính điểm độ tương quan dựa trên tần suất từ khóa xuất hiện. Bài viết khớp từ khóa ở tiêu đề được nhân hệ số trọng số cao (`50x`), khớp trong nội dung nhân hệ số `1x`.
3. Chỉ lấy **15 bài viết có điểm số cao nhất** đưa vào Context để Gemini xử lý (~30k tokens).
4. Giúp câu trả lời nhanh hơn, tiết kiệm token tối đa và chính xác 100%.

---

## [Tùy chọn phụ] Chuyển đổi ngược lại OpenAI
Nếu bạn muốn sử dụng OpenAI Assistants API (yêu cầu nạp tối thiểu $5 vào tài khoản OpenAI):
1. Cài đặt dependencies: `pip install -r requirements.txt`
2. Cập nhật `OPENAI_API_KEY` trong `.env`.
3. Chạy `python setup_assistant.py` để tạo Assistant ID và Vector Store ID trên cloud.
4. Chạy `python main.py` để đẩy bài viết lên OpenAI Vector Store.
5. Chạy `python test_assistant.py` để chat.
