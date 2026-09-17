-- Existing installations use these FK names from the original visdom_db.sql.
-- Each ALTER is atomic and can be repeated after an interrupted migration.
ALTER TABLE formulas DROP FOREIGN KEY formulas_ibfk_1,
    ADD CONSTRAINT fk_formulas_username FOREIGN KEY(user_id) REFERENCES users(username) ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE animation_scripts DROP FOREIGN KEY animation_scripts_ibfk_1,
    ADD CONSTRAINT fk_animation_scripts_username FOREIGN KEY(user_id) REFERENCES users(username) ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE agent_templates DROP FOREIGN KEY agent_templates_ibfk_1,
    ADD CONSTRAINT fk_agent_templates_username FOREIGN KEY(user_id) REFERENCES users(username) ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE user_profiles DROP FOREIGN KEY user_profiles_ibfk_1,
    ADD CONSTRAINT fk_user_profiles_username FOREIGN KEY(user_id) REFERENCES users(username) ON DELETE CASCADE ON UPDATE CASCADE;
