access_log /var/log/nginx/access.log vhost;
error_log /var/log/nginx/error.log {{ opts.OPENRESTY_LOG_LEVEL }};

{% if graylog.enabled %}
access_log syslog:server={{graylog.domain}}:{{graylog.ports.access}} graylog2_json;
error_log  syslog:server={{graylog.domain}}:{{graylog.ports.error}};
{% endif %}