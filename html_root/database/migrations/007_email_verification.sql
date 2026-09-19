-- 邮箱验证与密码找回。users 的字段在新库建表时已包含；旧库由迁移器按字段存在性补齐。
ALTER TABLE users ADD COLUMN email VARCHAR(254) CHARACTER SET ascii COLLATE ascii_bin NULL;
ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN email_verified_at TIMESTAMP NULL DEFAULT NULL;
ALTER TABLE users ADD UNIQUE KEY uq_users_email (email);

CREATE TABLE IF NOT EXISTS account_email_codes (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL,
    email VARCHAR(254) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    purpose ENUM('register','verify','reset') NOT NULL,
    code_hash CHAR(64) NOT NULL,
    expires_at DATETIME NOT NULL,
    consumed_at DATETIME NULL,
    attempts TINYINT UNSIGNED NOT NULL DEFAULT 0,
    requester_ip_hash CHAR(64) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_email_code_lookup(email,purpose,created_at),
    INDEX ix_email_code_user(user_id,created_at),
    INDEX ix_email_code_created(created_at),
    CONSTRAINT fk_email_code_user FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS account_email_limits (
    bucket CHAR(64) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
    window_start DATETIME NOT NULL,
    used INT UNSIGNED NOT NULL DEFAULT 0,
    INDEX ix_email_limit_window(window_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
