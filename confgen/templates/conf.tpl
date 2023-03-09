map $http_upgrade $proxy_connection {
  default upgrade;
  '' close;
}

map $http_x_forwarded_proto $proxy_x_forwarded_proto {
  default $http_x_forwarded_proto;
  ''      $scheme;
}

lua_shared_dict cache 20m;

# HTTP 1.1 support
proxy_http_version 1.1;
proxy_buffering off;
proxy_set_header Host $http_host;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $proxy_connection;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $proxy_x_forwarded_proto;


server {
	server_name _; # This is just an invalid value which will never trigger on a real hostname.
	listen 80;
	access_log /var/log/nginx/access.log vhost;
	return 503;
}


{% for service in services %}
{% include "service.tpl" %}
{% endfor %}
