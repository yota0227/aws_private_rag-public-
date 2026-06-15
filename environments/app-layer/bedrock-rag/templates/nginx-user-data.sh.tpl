#!/bin/bash
# nginx is pre-installed in AMI — configure only
exec 1>/var/log/user-data.log
exec 2>&1
echo "[START] $(date)"

# Create SSL directory and self-signed cert
mkdir -p /etc/nginx/ssl
openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/server.key \
  -out /etc/nginx/ssl/server.crt \
  -subj "/CN=corp.bos-semi.com"
echo "[INFO] SSL cert created"

# Write nginx config
APIGW="${apigw_host}"
cat > /etc/nginx/conf.d/llm-gateway.conf <<EOF
server {
    listen 443 ssl;
    server_name llm.corp.bos-semi.com;
    ssl_certificate     /etc/nginx/ssl/server.crt;
    ssl_certificate_key /etc/nginx/ssl/server.key;
    location / {
        proxy_pass         https://$APIGW/prod/llm/;
        proxy_ssl_server_name on;
        proxy_set_header   Host $APIGW;
    }
}
server {
    listen 443 ssl;
    server_name mcp.corp.bos-semi.com;
    ssl_certificate     /etc/nginx/ssl/server.crt;
    ssl_certificate_key /etc/nginx/ssl/server.key;
    location / {
        proxy_pass         https://$APIGW/prod/mcp/;
        proxy_ssl_server_name on;
        proxy_set_header   Host $APIGW;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade \$http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_read_timeout 3600s;
    }
}
server {
    listen 443 ssl default_server;
    ssl_certificate     /etc/nginx/ssl/server.crt;
    ssl_certificate_key /etc/nginx/ssl/server.key;
    return 444;
}
EOF
echo "[INFO] nginx config written"

# Start nginx
nginx -t && systemctl enable nginx && systemctl restart nginx
echo "[DONE] $(date) nginx=$(systemctl is-active nginx)"
