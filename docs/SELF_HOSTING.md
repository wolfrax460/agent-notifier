# Self-hosting guide (Ubuntu + nginx + Let's Encrypt)

This guide runs the hosted service as ONE systemd service (port 8787, localhost only) behind nginx with HTTPS.
Tested on Ubuntu 24.04 with about 1 GB of RAM. It does not touch any other site you already serve with nginx.

Replace `YOUR_DOMAIN` everywhere with the domain you point at your server (a free DuckDNS name works).

## 0. Before touching the server (5 min)

1. **Domain**: point a DNS A record (or a free DuckDNS subdomain) at your server's public IP. Ports 80 and 443 must be reachable.
2. **Existing sites**: if nginx already serves other sites, this adds one new site file and does not edit theirs.
3. **Telegram bot**: in Telegram open @BotFather -> `/newbot` -> pick a name and a username ending in `bot`. Save the token and username. Make it a NEW bot, not one used by anything else.

## 1. Swap (RAM is tight)

```bash
free -h; swapon --show          # if swap is already >= 1G, skip
sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 2. Install the app

Get the `cloud` folder onto the server (git clone this repo, then use its `cloud` folder), then:

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip sqlite3
sudo useradd --system --home /opt/agent-notifier --shell /usr/sbin/nologin notify
sudo mkdir -p /opt/agent-notifier && sudo cp -r cloud/. /opt/agent-notifier/
sudo python3 -m venv /opt/agent-notifier/venv
sudo /opt/agent-notifier/venv/bin/pip install /opt/agent-notifier
sudo chown -R root:notify /opt/agent-notifier && sudo chmod -R g+rX,o-rwx /opt/agent-notifier
```

## 3. Configure

```bash
sudo cp /opt/agent-notifier/deploy/env.example /etc/agent-notifier.env
sudo chown root:notify /etc/agent-notifier.env && sudo chmod 640 /etc/agent-notifier.env
python3 -c "import secrets;print('TG_WEBHOOK_SECRET='+secrets.token_hex(24));print('SESSION_SECRET='+secrets.token_urlsafe(48))"
sudo nano /etc/agent-notifier.env     # paste the two generated lines, the bot token + username, PUBLIC_URL, ADMIN_TG_IDS (optional), LANDING_URL (optional)
```

Check it: `sudo -u notify bash -c 'set -a; . /etc/agent-notifier.env; /opt/agent-notifier/venv/bin/python -m agent_notifier_cloud check'`
(prints "config OK" or exactly what is missing).

## 4. Run as a service

```bash
sudo cp /opt/agent-notifier/deploy/agent-notifier.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now agent-notifier
sleep 2; curl -s http://127.0.0.1:8787/health     # -> {"ok":true}
sudo journalctl -u agent-notifier -n 30 --no-pager
```

## 5. nginx + HTTPS

```bash
sudo cp /opt/agent-notifier/deploy/nginx-limits.conf /etc/nginx/conf.d/agent-notifier-limits.conf
sudo cp /opt/agent-notifier/deploy/nginx-site.conf /etc/nginx/sites-available/YOUR_DOMAIN
sudo nano /etc/nginx/sites-available/YOUR_DOMAIN          # set server_name to your name
sudo ln -s /etc/nginx/sites-available/YOUR_DOMAIN /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx                        # only reload if the test passes
sudo certbot --nginx -d YOUR_DOMAIN --redirect           # install certbot first if missing:
                                                                     # sudo apt install -y certbot python3-certbot-nginx
```

If `nginx -t` fails, do NOT reload; fix or remove the new site file. Your other sites keep running either way.

## 6. Connect Telegram

```bash
sudo -u notify bash -c 'set -a; . /etc/agent-notifier.env; /opt/agent-notifier/venv/bin/python -m agent_notifier_cloud set-webhook'
```
Expect `{'ok': True, ...}`. Then open `https://YOUR_DOMAIN/login`, press Start in Telegram, tap Confirm.

## 6b. Make yourself admin (optional)

Put your numeric Telegram ID in `ADMIN_TG_IDS` in `/etc/agent-notifier.env` and restart. You then get an Admin console at `/admin` (users, usage, suspend, broadcast, audit log). It never shows message contents.

## 7. Verify

```bash
curl -s https://YOUR_DOMAIN/health
curl -s https://YOUR_DOMAIN/.well-known/oauth-authorization-server | head -c 300
curl -si -X POST https://YOUR_DOMAIN/mcp | head -5      # expect 401 mentioning resource_metadata
```
Then in the dashboard click "Send a test notification". Then add the connector in your AI tool.

## 8. Backups + updates

```bash
# nightly DB backup, keeps 14 days (as root: sudo crontab -e)
15 3 * * * sqlite3 /var/lib/agent-notifier/notify.db ".backup '/var/backups/notify-$(date +\%F).db'" && find /var/backups -name 'notify-*.db' -mtime +14 -delete

# update
sudo /opt/agent-notifier/venv/bin/pip install --upgrade /opt/agent-notifier && sudo systemctl restart agent-notifier
```

## Troubleshooting

| Symptom | Check |
|---|---|
| 421 Misdirected Request | nginx must pass `Host $host`; `PUBLIC_URL` must match the hostname exactly |
| Telegram buttons do nothing | `getWebhookInfo` for the bot (last_error_message); rerun `set-webhook`; check `journalctl -u agent-notifier` |
| claude.ai says it cannot connect | `/.well-known/oauth-authorization-server` and `/mcp` must answer over HTTPS on 443 with a valid cert |
| Service killed / restarts | `journalctl -u agent-notifier`; memory cap is 300M; check `free -h` and swap |
| Login page loops | cookies blocked, or `PUBLIC_URL` is `http://` while you browse via `https://` |

## Remove completely

```bash
sudo systemctl disable --now agent-notifier && sudo rm /etc/systemd/system/agent-notifier.service
sudo rm /etc/nginx/sites-enabled/YOUR_DOMAIN /etc/nginx/conf.d/agent-notifier-limits.conf && sudo nginx -t && sudo systemctl reload nginx
sudo rm -rf /opt/agent-notifier /var/lib/agent-notifier /etc/agent-notifier.env && sudo userdel notify
```

## Running a public service: your responsibilities

- Users trust you with a Telegram link and the content of their notifications. Keep the server patched, back up the DB, and never log message text (the app does not).
- Publish a short privacy note and a contact address.
- Abuse limits are on by default (10/min, 300/day per user, per-IP login throttling). Tune `RATE_PER_MIN` / `RATE_PER_DAY`.
