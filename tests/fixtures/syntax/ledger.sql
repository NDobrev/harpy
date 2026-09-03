CREATE TABLE fees.ledger (
    id uuid PRIMARY KEY,
    amount int NOT NULL
);
ALTER TABLE fees.ledger ADD COLUMN settled_at timestamptz;
ALTER TABLE users ADD COLUMN email text;
DROP TABLE fee_pending;
