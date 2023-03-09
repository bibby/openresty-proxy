#!/bin/bash

: ${NGINX_CONF:="/usr/local/openresty/nginx/conf/nginx.conf"};
mkdir -p /var/log/nginx \
         /etc/nginx/certs \
         /etc/nginx/conf.d

[ -f /etc/nginx/conf.d/default.conf ] && {
  rm /etc/nginx/conf.d/default.conf
}


j2 -f env \
-o "${NGINX_CONF}" \
/usr/src/confgen/templates/nginx_conf.tpl || {
  echo "nginx.conf failed to render" >&2
  sleep 30;
}

vts_db="${VTS_DB_DIR}/vts.vts_db"
chown root:nogroup "${VTS_DB_DIR}"
chmod -v -R ug+rw "${VTS_DB_DIR}"

echo "VTS_RESET_DB? ${VTS_RESET_DB}" >&2
if [ "${VTS_RESET_DB}" != "0" ]
then
  if [ -f "${vts_db}" ]
  then
    rm "${vts_db}"
    echo "removed DB"
  fi
fi

echo 'daemon..'
supervisord 2>/dev/stderr >/dev/stdout &
sleep 2

echo 'openresty..'
supervisorctl start openresty
sleep 4

echo 'watcher..'
supervisorctl start watcher
sleep 2

echo 'listener..'
supervisorctl start listener

exec tail -f /var/log/nginx/access.log /var/log/nginx/error.log
