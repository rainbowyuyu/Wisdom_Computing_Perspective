"""Email-client friendly account messages, with a plain-text alternative."""
from html import escape


def verification_content(code, purpose, minutes, *, preview=False):
    action, title, description = {
        'register': ('注册账户', '欢迎来到智算视界', '验证你的邮箱，开启更直观的数学探索。'),
        'verify': ('验证邮箱', '验证邮箱，继续探索', '完成邮箱验证，继续使用你的学习空间。'),
        'reset': ('重置密码', '重新设置你的密码', '在密码重置页面输入下方验证码，即可设置新密码。'),
        'change_email': ('更换邮箱', '确认你的新邮箱', '在更换邮箱页面输入下方验证码，完成新邮箱绑定。'),
    }[purpose]
    subject = f'智算视界 · {action}' + (' · 样式测试' if preview else '')
    notice = '这是一封样式测试邮件，示例验证码无法用于账户操作。' if preview else ''
    plain = (f'您好，\n\n{description}\n\n{action}验证码：{code}\n'
             f'请在 {minutes} 分钟内使用，并返回刚才的页面填写。\n\n'
             '请勿将验证码告诉他人。如非本人操作，请忽略此邮件。\n'
             '此邮箱用于发送通知，请勿直接回复。\n'
             + (notice + '\n' if notice else '') + '\n智算视界\nhttps://www.wiscomper.com/')
    code, action, title, description = map(escape, (str(code), action, title, description))
    preview_row = (f'<tr><td style="padding:14px 24px;background-color:#fff8e8;color:#866225;'
                   f'font-size:12px;line-height:1.8;">{notice}</td></tr>' if notice else '')
    # Tables, inline styles and solid-color fallbacks work without images, scripts or web fonts.
    html = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><title>{subject}</title></head>
<body style="margin:0;padding:0;background-color:#f4f6fb;color:#202740;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Microsoft YaHei',Arial,sans-serif;-webkit-text-size-adjust:100%;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;mso-hide:all;">{action}，验证码 {minutes} 分钟内有效。请勿向他人提供验证码。</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f4f6fb"><tr><td align="center" style="padding:28px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:560px;">
<tr><td style="padding:0 8px 20px;">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
  <td width="36" height="36" align="center" bgcolor="#6554e8" style="border-radius:11px;color:#ffffff;font-size:22px;font-weight:700;">W</td>
  <td style="padding-left:11px;color:#303957;font-size:17px;font-weight:700;letter-spacing:1px;">智算视界</td>
  </tr></table>
</td></tr>
<tr><td bgcolor="#ffffff" style="border:1px solid #e7eaf3;border-radius:18px;overflow:hidden;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr><td height="4" bgcolor="#6554e8" style="height:4px;font-size:0;line-height:4px;background-image:linear-gradient(90deg,#487bf4,#8a55e9);">&nbsp;</td></tr>
{preview_row}
<tr><td style="padding:30px 24px 0;">
  <p style="margin:0 0 12px;color:#7064ba;font-size:12px;font-weight:600;letter-spacing:2px;">账户安全 · {action}</p>
  <h1 style="margin:0 0 12px;color:#202740;font-size:24px;line-height:1.45;font-weight:700;">{title}</h1>
  <p style="margin:0;color:#6d7488;font-size:14px;line-height:1.9;">{description}</p>
</td></tr>
<tr><td style="padding:24px 24px 0;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f3f2ff" style="border:1px solid #e6e2ff;border-radius:12px;">
  <tr><td align="center" style="padding:20px 8px 8px;color:#77718f;font-size:12px;">你的邮箱验证码</td></tr>
  <tr><td align="center" style="padding:0 4px 10px;color:#5143bc;font-family:Consolas,'Courier New',monospace;font-size:34px;font-weight:700;line-height:1.35;letter-spacing:6px;white-space:nowrap;">{code}</td></tr>
  <tr><td align="center" style="padding:0 8px 20px;color:#77718f;font-size:12px;line-height:1.6;">请在 <strong style="color:#5143bc;">{minutes} 分钟</strong>内使用</td></tr>
  </table>
</td></tr>
<tr><td style="padding:18px 24px 26px;">
  <p style="margin:0;color:#6d7488;font-size:13px;line-height:1.9;">返回刚才的页面，输入上方验证码即可继续。</p>
</td></tr>
<tr><td style="padding:20px 24px 24px;border-top:1px solid #edf0f6;">
  <p style="margin:0 0 6px;color:#434b63;font-size:13px;font-weight:600;">保护好你的验证码</p>
  <p style="margin:0;color:#858b9b;font-size:12px;line-height:1.9;">请勿向任何人提供此验证码。如非本人操作，忽略本邮件即可，无需回复。</p>
</td></tr>
</table></td></tr>
<tr><td align="center" style="padding:22px 12px 0;color:#969cad;font-size:11px;line-height:1.9;">
  <a href="https://www.wiscomper.com/" style="color:#737b91;text-decoration:none;font-size:12px;">智算视界 · 让数学看得见</a><br>
  这是一封系统邮件，请勿直接回复。
</td></tr>
</table></td></tr></table>
</body></html>'''
    return subject, plain, html
