import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO


# --- 辅助函数：生成验证码 (Linux 字体修复版) ---
def generate_captcha_image_bytes():
    # 去除易混淆字符 (0, O, I, 1, L)
    chars = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
    text = ''.join(random.choices(chars, k=4))

    width, height = 120, 50  # 保持原尺寸
    image = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)

    # -------------------------------------------------------------
    # [核心修改]：解决 Linux 上字体加载失败导致字体极小的问题
    # -------------------------------------------------------------
    font = None
    # 优先尝试的字体列表（包含 Windows 的 Arial 和 Linux 常见字体）
    font_list = [
        "arial.ttf",  # Windows
        "DejaVuSans.ttf",  # Linux (CentOS/Ubuntu 常见)
        "LiberationSans-Regular.ttf",  # Linux
        "FreeSans.ttf",  # Linux
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",  # 绝对路径尝试
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ]

    for font_name in font_list:
        try:
            font = ImageFont.truetype(font_name, 28)  # 保持原字号 28
            break
        except:
            continue

    # 如果所有字体都找不到，尝试使用 Pillow 新版的默认字体大小调整功能
    if font is None:
        try:
            # Pillow 10.0.0+ 支持设置 load_default 的大小
            font = ImageFont.load_default(size=28)
        except:
            # 旧版 Pillow 只能回退到小字体 (这是之前看不清的根源，但已经尽力了)
            font = ImageFont.load_default()
    # -------------------------------------------------------------

    # 绘制干扰线 (保持原样)
    for _ in range(5):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        draw.line(((x1, y1), (x2, y2)), fill=(200, 200, 200), width=2)

    # 绘制干扰点 (保持原样)
    for _ in range(30):
        x = random.randint(0, width)
        y = random.randint(0, height)
        draw.point((x, y), fill=(100, 100, 100))

    # 绘制字符 (保持原样)
    for i, char in enumerate(text):
        # 创建单个字符的图像用于旋转
        char_img = Image.new('RGBA', (30, 30), (255, 255, 255, 0))
        char_draw = ImageDraw.Draw(char_img)
        char_draw.text((5, 0), char, font=font,
                       fill=(random.randint(0, 100), random.randint(0, 100), random.randint(0, 100)))

        # 随机旋转
        angle = random.randint(-15, 15)
        char_img = char_img.rotate(angle, expand=1)

        # 粘贴到主图
        x = 10 + i * 25 + random.randint(-2, 2)
        y = 5 + random.randint(-2, 2)
        image.paste(char_img, (x, y), char_img)

    # 模糊滤镜 (保持原样，字体正常后这个滤镜就不会导致看不清了)
    image = image.filter(ImageFilter.SMOOTH)

    buf = BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    return text, buf

if __name__ == '__main__':
    # 本地测试代码
    code, data = generate_captcha_image_bytes()
    with open("test_captcha.png", "wb") as f:
        f.write(data.getvalue())
    print(f"Generated captcha: {code}")