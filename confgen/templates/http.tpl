server {
    server_name {{ service.server_names() }}{% if service.default_server %} default_server{% endif %};
    listen 80 ;

    {% include "service_log.tpl" %}

    {% if service.serve_http %}

    {% include "service_loc.tpl" %}
    {% include "service_confs.tpl" %}
    {% include "vts.tpl" %}

    {% else %}
        return 301 https://$host$request_uri;
    {% endif %}
}