# rainbow_yu animate_cal.captcha 🐋✨
# Date : 2026/1/20 20:31

import  random
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO


# --- 辅助函数：生成验证码 (优化版) ---
def generate_captcha_image_bytes():
    # 去除易混淆字符 (0, O, I, 1, L)
    chars = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
    text = ''.join(random.choices(chars, k=4))

    width, height = 120, 50  # 稍微加高
    image = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)

    try:
        # 尝试加载字体，调整大小
        font = ImageFont.truetype("arial.ttf", 28)
    except:
        font = ImageFont.load_default()

    # 绘制干扰线
    for _ in range(5):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        draw.line(((x1, y1), (x2, y2)), fill=(200, 200, 200), width=2)

    # 绘制干扰点
    for _ in range(30):
        x = random.randint(0, width)
        y = random.randint(0, height)
        draw.point((x, y), fill=(100, 100, 100))

    # 绘制字符 (增加旋转和位移)
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

    # 模糊滤镜 (轻微)
    image = image.filter(ImageFilter.SMOOTH)

    buf = BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    return text, buf