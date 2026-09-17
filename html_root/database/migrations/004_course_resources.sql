-- Ordered learning materials with durable snapshots and nullable source links.
CREATE TABLE IF NOT EXISTS course_pack_resources (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    pack_id INT NOT NULL,
    kind ENUM('solution','wrongbook') NOT NULL,
    formula_id INT NULL,
    wrongbook_id BIGINT UNSIGNED NULL,
    snapshot JSON NOT NULL,
    sort_order INT UNSIGNED NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY ix_pack_resource_order(pack_id,sort_order,id),
    UNIQUE KEY uq_pack_formula(pack_id,formula_id),
    UNIQUE KEY uq_pack_wrongbook(pack_id,wrongbook_id),
    CONSTRAINT fk_resource_pack FOREIGN KEY(pack_id) REFERENCES course_packs(id) ON DELETE CASCADE,
    CONSTRAINT fk_resource_formula FOREIGN KEY(formula_id) REFERENCES formulas(id) ON DELETE SET NULL,
    CONSTRAINT fk_resource_wrongbook FOREIGN KEY(wrongbook_id) REFERENCES learning_wrongbook(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
