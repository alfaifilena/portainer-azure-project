"""Run with sudo on the VM; credentials are entered locally and never printed."""
import getpass
import json
import os
import secrets
from pathlib import Path
from urllib.request import Request, urlopen


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run this script with sudo.')
    token = getpass.getpass('Telegram bot token (hidden): ').strip()
    if not token or ':' not in token or any(c.isspace() for c in token):
        raise SystemExit('Invalid token format; nothing saved.')

    def call(method, data):
        request = Request('https://api.telegram.org/bot' + token + '/' + method,
                          data=json.dumps(data).encode(),
                          headers={'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=40) as response:
                result = json.load(response)
            if not result.get('ok'):
                raise ValueError()
            return result['result']
        except Exception:
            raise SystemExit('Telegram request failed. Check the token and connection; nothing saved.') from None

    bot = call('getMe', {})
    if call('getWebhookInfo', {}).get('url'):
        raise SystemExit('This bot already has a webhook. Use a new dedicated bot.')
    nonce = secrets.token_hex(12)
    print('Open this link in Telegram and press Start:')
    print('https://t.me/' + bot['username'] + '?start=' + nonce)
    input('After pressing Start, press Enter here: ')
    updates = call('getUpdates', {'timeout': 20, 'allowed_updates': ['message']})
    matches = [u['message']['chat'] for u in updates if
               u.get('message', {}).get('text') == '/start ' + nonce
               and u['message']['chat'].get('type') == 'private']
    if not matches:
        raise SystemExit('The private Start message was not found. Run setup again; nothing saved.')
    chat_id = str(matches[-1]['id'])
    directory = Path('/srv/portainer-data/config/secrets')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, value in [('telegram_bot_token', token), ('telegram_chat_id', chat_id)]:
        fd = os.open(directory / name, os.O_WRONLY | os.O_CREAT, 0o600)
        with os.fdopen(fd, 'w') as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(value + '\n')
            output.truncate()
    print('Telegram private destination saved. The monitor reads these files automatically.')


if __name__ == '__main__':
    main()
