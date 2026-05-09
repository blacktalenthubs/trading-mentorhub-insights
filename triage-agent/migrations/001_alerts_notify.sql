-- ╔═══════════════════════════════════════════════════════════════════╗
-- ║  Migration: 001_alerts_notify                                      ║
-- ║  Adds a Postgres trigger that fires pg_notify('new_alert', id)     ║
-- ║  on every INSERT into the alerts table.                            ║
-- ║                                                                    ║
-- ║  This is PURELY ADDITIVE.                                          ║
-- ║  - tv_webhook.py, monitor.py, worker.py, alert_store.py keep       ║
-- ║    inserting into `alerts` exactly as they do today.               ║
-- ║  - The trigger emits a NOTIFY when a row lands.                    ║
-- ║  - Anything LISTENING gets the alert id sub-second; no listener,   ║
-- ║    the NOTIFY is a no-op. The insert is unaffected either way.     ║
-- ║                                                                    ║
-- ║  Apply once on Railway Postgres:                                   ║
-- ║    psql $DATABASE_URL -f migrations/001_alerts_notify.sql          ║
-- ║                                                                    ║
-- ║  Rollback (if ever needed):                                        ║
-- ║    DROP TRIGGER alerts_notify_new ON alerts;                       ║
-- ║    DROP FUNCTION notify_new_alert();                               ║
-- ╚═══════════════════════════════════════════════════════════════════╝

CREATE OR REPLACE FUNCTION notify_new_alert() RETURNS TRIGGER AS $$
BEGIN
    -- Payload is just the row id. Listeners SELECT the row themselves.
    -- pg_notify is fire-and-forget; no error path can fail the INSERT.
    PERFORM pg_notify('new_alert', NEW.id::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


DROP TRIGGER IF EXISTS alerts_notify_new ON alerts;

CREATE TRIGGER alerts_notify_new
AFTER INSERT ON alerts
FOR EACH ROW
EXECUTE FUNCTION notify_new_alert();


-- ── Sanity check ─────────────────────────────────────────────────────
-- After running, verify the trigger exists:
--
--   SELECT tgname, tgrelid::regclass, tgenabled
--   FROM pg_trigger WHERE tgname = 'alerts_notify_new';
--
-- Expected: one row, tgenabled = 'O' (origin = enabled).
