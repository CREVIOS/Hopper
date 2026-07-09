CREATE TABLE IF NOT EXISTS email_codes (
  id varchar NOT NULL,
  email varchar NOT NULL,
  purpose varchar NOT NULL,
  code_hash varchar NOT NULL,
  attempts integer NOT NULL DEFAULT 0,
  expires_at timestamp without time zone NOT NULL,
  consumed_at timestamp without time zone,
  created_at timestamp without time zone DEFAULT now(),
  CONSTRAINT email_codes_pkey PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_email_codes_email ON email_codes (email);
UPDATE alembic_version SET version_num='012';
