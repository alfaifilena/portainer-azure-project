"""Rule-only Telegram notifications. No AI calls and no credentials in logs."""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from rules import redact
from storage import fingerprint


class TelegramAlerts:
    INTERVAL = 900

    def __init__(self, store, config, send_fn=None):
        self.store = store
        self.send_fn = send_fn or self.send

    def credentials(self):
        try:
            token = Path(os.environ.get('TELEGRAM_TOKEN_FILE', '/run/secrets/telegram_bot_token')).read_text().strip()
            chat = Path(os.environ.get('TELEGRAM_CHAT_FILE', '/run/secrets/telegram_chat_id')).read_text().strip()
            return (token, chat) if token and chat else None
        except OSError:
            return None

    def observe(self, eid, environment_name, container, finding, now):
        if finding.get('source') != 'rules' or not self.credentials():
            return
        identity = fingerprint([eid, container['id'], finding['rule'], finding.get('facts', {})])
        evidence = redact((finding.get('evidence') or ['No evidence supplied'])[0])[:400]
        message = '\n'.join([
            'Container Hub — Rule alert',
            'Environment: ' + redact(environment_name)[:100],
            'Container: ' + redact(container['name'])[:100],
            'Observed: ' + redact(finding['category'])[:150],
            'Time: ' + datetime.fromtimestamp(now, timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
            'Evidence: ' + evidence,
        ])
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM telegram_alerts WHERE id=?', (identity,)).fetchone()
            if row and (row['status'] == 'pending' or now - max(row['last_sent'], row['created']) < self.INTERVAL):
                return
            db.execute('INSERT OR REPLACE INTO telegram_alerts VALUES(?,?,?,?,?,?,?)',
                       (identity, message, now, row['last_sent'] if row else 0, 0, now, 'pending'))

    @staticmethod
    def send(token, chat, message):
        request = Request('https://api.telegram.org/bot' + token + '/sendMessage',
                          data=json.dumps({'chat_id': chat, 'text': message,
                              'link_preview_options': {'is_disabled': True}}).encode(),
                          headers={'Content-Type': 'application/json'})
        with urlopen(request, timeout=10) as response:
            result = json.load(response)
        if result.get('ok') is not True:
            raise ValueError('Telegram did not confirm delivery.')

    def send_once(self):
        credentials = self.credentials()
        if not credentials:
            self.store.put('telegram_status', {'status': 'not_configured'})
            return False
        now = time.time()
        status = self.store.get('telegram_status', {})
        credential_id = fingerprint(credentials)
        # Invalid credentials or a rejected destination require setup, not endless retries.
        if status.get('status') == 'configuration_error' and status.get('_credential_id') == credential_id:
            return False
        with self.store.connect() as db:
            db.execute("UPDATE telegram_alerts SET status='expired' WHERE status='pending' AND created<=?", (now - self.INTERVAL,))
            row = db.execute("SELECT * FROM telegram_alerts WHERE status='pending' AND due<=? ORDER BY created LIMIT 1", (now,)).fetchone()
        if not row:
            if status.get('status') != 'unavailable':
                self.store.put('telegram_status', {'status': 'ready'})
            return False
        try:
            self.send_fn(*credentials, row['message'])
        except Exception as error:
            attempts = row['attempts'] + 1
            delay = 30 * (2 ** (attempts - 1))
            code = getattr(error, 'code', None)
            if isinstance(error, HTTPError) and code == 429:
                try:
                    data = json.loads(error.read(16384))
                    delay = max(delay, int(data.get('parameters', {}).get('retry_after', 0)))
                except (ValueError, TypeError, OSError):
                    pass
            permanent = code in (400, 401, 403, 404)
            with self.store.connect() as db:
                db.execute('UPDATE telegram_alerts SET status=?,attempts=?,due=? WHERE id=?',
                           ('failed' if permanent or attempts >= 3 else 'pending', attempts, now + delay, row['id']))
            self.store.put('telegram_status', {
                'status': 'configuration_error' if permanent else 'unavailable',
                'message': 'Check Telegram bot setup.' if permanent else 'Telegram delivery failed; monitoring continues.',
                '_credential_id': credential_id,
            })
            return True
        with self.store.connect() as db:
            db.execute("UPDATE telegram_alerts SET status='sent',last_sent=? WHERE id=?", (now, row['id']))
        self.store.put('telegram_status', {'status': 'ready', 'last_sent': now})
        return True
