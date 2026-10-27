-- Optional baseline for a NEW MySQL database. Not executed by the application.
-- Existing legacy databases require schema inspection first; never replace users.
-- Roles are database-owned. This script creates no users, passwords or admins.
CREATE TABLE IF NOT EXISTS users (
 id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
 username VARCHAR(255) NOT NULL UNIQUE,
 hashed_password VARCHAR(255) NOT NULL,
 email VARCHAR(254) CHARACTER SET ascii COLLATE ascii_bin NULL,
 email_verified BOOLEAN NOT NULL DEFAULT FALSE,
 email_verified_at TIMESTAMP NULL DEFAULT NULL,
 created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE KEY uq_users_email(email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS account_access (
 user_id INT PRIMARY KEY,
 role ENUM('member','vip','admin') NOT NULL DEFAULT 'member',
 disabled BOOLEAN NOT NULL DEFAULT FALSE,
 daily_limit INT NULL,
 updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 CONSTRAINT fk_access_user FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS account_email_codes (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
 user_id INT NULL,
 email VARCHAR(254) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 purpose ENUM('register','verify','reset','change_email') NOT NULL,
 code_hash CHAR(64) NOT NULL,
 expires_at DATETIME NOT NULL, consumed_at DATETIME NULL,
 attempts TINYINT UNSIGNED NOT NULL DEFAULT 0,
 requester_ip_hash CHAR(64) NOT NULL DEFAULT '',
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 INDEX ix_email_code_lookup(email,purpose,created_at),
 INDEX ix_email_code_user(user_id,created_at),
 CONSTRAINT fk_email_code_user FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE IF NOT EXISTS account_email_limits (
 bucket CHAR(64) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
 window_start DATETIME NOT NULL, used INT UNSIGNED NOT NULL DEFAULT 0,
 INDEX ix_email_limit_window(window_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
