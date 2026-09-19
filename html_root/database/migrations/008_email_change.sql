-- 支持已登录用户通过新邮箱验证码更换绑定邮箱。
ALTER TABLE account_email_codes
    MODIFY COLUMN purpose ENUM('register','verify','reset','change_email') NOT NULL;
