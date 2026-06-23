-- V3.13.5.2 existing-product-db upgrade.
-- Chat message snapshots may contain HTML plus chart image dataURL. MySQL TEXT
-- only stores about 64KB, which is too small for restored analysis cards.

USE datawhisperer_product;

ALTER TABLE chat_messages
  MODIFY COLUMN content LONGTEXT NOT NULL;
