-- Fill tables omitted from older bootstrap SQL before adding relational integrity.
CREATE TABLE IF NOT EXISTS course_packs (
    id INT AUTO_INCREMENT PRIMARY KEY,user_id VARCHAR(64) NOT NULL,
    name VARCHAR(128) NOT NULL,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS course_pack_documents (
    pack_id INT PRIMARY KEY,description TEXT NOT NULL,lesson_json LONGTEXT NOT NULL,
    revision INT NOT NULL DEFAULT 1,updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS course_pack_videos (
    pack_id INT NOT NULL,video_id VARCHAR(128) NOT NULL,sort_order INT DEFAULT 0,
    PRIMARY KEY(pack_id,video_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
ALTER TABLE course_pack_documents ADD CONSTRAINT fk_pack_document FOREIGN KEY(pack_id) REFERENCES course_packs(id) ON DELETE CASCADE;
ALTER TABLE course_pack_videos ADD CONSTRAINT fk_pack_video FOREIGN KEY(pack_id) REFERENCES course_packs(id) ON DELETE CASCADE;
ALTER TABLE formula_topics ADD CONSTRAINT fk_topic_formula FOREIGN KEY(formula_id) REFERENCES formulas(id) ON DELETE CASCADE;
