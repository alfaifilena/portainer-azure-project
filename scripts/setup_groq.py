"""Enter the Groq key privately on the VM; no inference request is sent."""
import getpass, os
from pathlib import Path

if os.geteuid() != 0:
    raise SystemExit('Run with sudo.')
key = getpass.getpass('Groq API key (hidden): ').strip()
if not key.startswith('gsk_') or any(c.isspace() for c in key):
    raise SystemExit('Invalid key format; nothing saved.')
path = Path('/srv/portainer-data/config/secrets/groq_api_key')
fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
with os.fdopen(fd, 'w') as output:
    os.fchmod(output.fileno(), 0o600)
    output.write(key + '\n')
    output.truncate()
print('Groq key saved. No AI request was sent. Use Analyze with AI in the dashboard.')
