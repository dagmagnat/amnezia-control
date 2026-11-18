#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || exit 1
read -r -p 'Domain / Домен: ' DOMAIN
# Let the certificate client validate the domain. It is passed as one argument.
apt-get install -y certbot python3-certbot-nginx
# For nonstandard panel ports use a separate HTTPS server on 443 via Nginx plugin.
certbot --nginx -d "$DOMAIN"
echo 'HTTPS certificate installed. Check the exact listen ports in nginx -T.'
