## # # # # # # # # # # # #
# openresty generated conf
## # # # # # # # # # # # #

worker_processes auto;
pid /run/nginx.pid;

events {
	worker_connections 768;
	# multi_accept on;
}

http {
	include       mime.types;
	default_type  application/octet-stream;
	{% if VTS_ENABLED %}
	vhost_traffic_status_zone shared:vhost_traffic_status:32m;
	vhost_traffic_status_dump /etc/nginx/db/vts.db;
	{% endif %}

	##
	# Basic Settings
	##

	sendfile on;
	tcp_nopush on;
	tcp_nodelay on;
	keepalive_timeout 65;
	types_hash_max_size 2048;
	server_names_hash_bucket_size 128;

	##
	# SSL Settings
	##

	ssl_protocols TLSv1 TLSv1.1 TLSv1.2; # Dropping SSLv3, ref: POODLE
	ssl_prefer_server_ciphers on;

	##
	# Logging Settings
	##

	access_log /var/log/nginx/access.log;
	error_log /var/log/nginx/error.log;

    ##
    # Log Formats
	##
{% include TPL_DIR + "/log_fmts.tpl" %}

	##
	# Gzip Settings
	##

	gzip on;
	gzip_disable "msie6";

	##
	# Virtual Host Configs
	##

	include /etc/nginx/conf.d/*.conf;
}
