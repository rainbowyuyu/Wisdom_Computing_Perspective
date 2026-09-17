-- MySQL 8.0 additive migration. Existing user_wrongbook remains as an archive.
CREATE TABLE IF NOT EXISTS learning_wrongbook (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    owner_id INT NOT NULL,
    legacy_id INT NULL,
    source_type ENUM('manual','video','solution') NOT NULL DEFAULT 'manual',
    video_id VARCHAR(256) NOT NULL DEFAULT '',
    formula_id INT NULL,
    time_sec INT UNSIGNED NOT NULL DEFAULT 0,
    title VARCHAR(512) NOT NULL,
    problem TEXT NOT NULL,
    answer MEDIUMTEXT NOT NULL,
    note TEXT NOT NULL,
    solution_snapshot JSON NULL,
    fingerprint CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    status ENUM('new','reviewing','mastered') NOT NULL DEFAULT 'new',
    difficulty TINYINT UNSIGNED NOT NULL DEFAULT 3,
    review_count INT UNSIGNED NOT NULL DEFAULT 0,
    interval_days INT UNSIGNED NOT NULL DEFAULT 0,
    next_review_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
    last_reviewed_at DATETIME NULL,
    revision INT UNSIGNED NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_wrongbook_origin(owner_id,fingerprint),
    UNIQUE KEY uq_wrongbook_legacy(legacy_id),
    KEY ix_wrongbook_due(owner_id,status,next_review_at,id),
    KEY ix_wrongbook_recent(owner_id,updated_at,id),
    KEY ix_wrongbook_video(owner_id,video_id,time_sec),
    CONSTRAINT fk_wrongbook_owner FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_wrongbook_formula FOREIGN KEY(formula_id) REFERENCES formulas(id) ON DELETE SET NULL,
    CONSTRAINT ck_wrongbook_difficulty CHECK(difficulty BETWEEN 1 AND 5)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS learning_wrongbook_tags (
    entry_id BIGINT UNSIGNED NOT NULL,
    tag VARCHAR(64) NOT NULL,
    PRIMARY KEY(entry_id,tag),
    KEY ix_wrongbook_tag(tag,entry_id),
    CONSTRAINT fk_wrongbook_tag_entry FOREIGN KEY(entry_id) REFERENCES learning_wrongbook(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS learning_wrongbook_reviews (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    entry_id BIGINT UNSIGNED NOT NULL,
    grade ENUM('again','good','mastered') NOT NULL,
    note TEXT NOT NULL,
    interval_days INT UNSIGNED NOT NULL,
    next_review_at DATETIME NULL,
    reviewed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY ix_wrongbook_review(entry_id,reviewed_at,id),
    CONSTRAINT fk_wrongbook_review_entry FOREIGN KEY(entry_id) REFERENCES learning_wrongbook(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
