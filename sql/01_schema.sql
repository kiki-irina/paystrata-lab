-- PayStrata daily statistics per merchant.
-- Typical pattern: surrogate auto-increment PK + a natural unique key.
CREATE TABLE IF NOT EXISTS merchant_daily_stats (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  merchant_id  INT UNSIGNED    NOT NULL,
  stat_date    DATE            NOT NULL,
  txn_count    INT UNSIGNED    NOT NULL DEFAULT 0,
  total_amount DECIMAL(18,2)   NOT NULL DEFAULT 0.00,
  PRIMARY KEY (id),
  UNIQUE KEY uq_merchant_day (merchant_id, stat_date)
) ENGINE=InnoDB;
