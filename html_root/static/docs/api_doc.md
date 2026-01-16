# WisComPer API Reference

Base URL: `http://<your-domain>/api`

## 1. 认证 (Auth)

### 注册
`POST /register`
*   **Body**: `{ "username": "...", "password": "...", "captcha": "...", "captcha_id": "..." }`
*   **Response**: `{ "status": "success", "message": "注册成功" }`

### 登录
`POST /login`
*   **Body**: `{ "username": "...", "password": "...", "captcha": "...", "captcha_id": "..." }`
*   **Response**: `{ "status": "success", "username": "..." }`

### 获取验证码
`GET /captcha`
*   **Response**: PNG Image Stream
*   **Headers**: `X-Captcha-ID: <uuid>`

---

## 2. 核心功能 (Core)

### 图像识别 (OCR)
`POST /detect`
*   **Content-Type**: `multipart/form-data`
*   **File**: `file` (image/jpeg, image/png)
*   **Response**: `{ "status": "success", "latex": "E = mc^2" }`

### 动画生成流 (SSE)
`POST /animate/stream`
*   **Content-Type**: `application/json`
*   **Body**: 
    ```json
    {
      "matrixA": "...",
      "matrixB": "...",
      "operation": "add | mul | det | other"
    }
    ```
*   **Response**: Server-Sent Events (text/event-stream)
    *   `step: "generating_code"`
    *   `step: "code_generated", code: "..."`
    *   `step: "rendering"`
    *   `step: "complete", video_url: "..."`

---

## 3. 算式库 (Formulas)

### 保存算式
`POST /formulas/save`
*   **Body**: `{ "username": "...", "latex": "...", "note": "..." }`

### 获取列表
`GET /formulas/list?username=...`

### 更新算式
`PUT /formulas/update`
*   **Body**: `{ "id": 1, "username": "...", "latex": "...", "note": "..." }`

### 删除算式
`DELETE /formulas/delete?id=...&username=...`