{% if opts.VTS_ENABLED %}
vhost_traffic_status_filter_by_host on;
{% if opts.VTS_USER_AGENT%}
vhost_traffic_status_filter_by_set_key $http_user_agent agent::$server_name;{% endif %}
{% if opts.VTS_URIS%}
vhost_traffic_status_filter_by_set_key $uri uris::$server_name;{% endif %}
{% endif %}

location /{{opts.VTS_PATH}} {
    vhost_traffic_status_display;
    vhost_traffic_status_display_format html;
}