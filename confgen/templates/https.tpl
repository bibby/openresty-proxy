server {
    server_name {{ service.server_names() }}{% if service.default_server %} default_server{% endif %};
    {% if service.proxy_pass %}
    {% include "service_proxy_pass.tpl" %}
    {% else %}
    {% include "service_proxy.tpl" %}
    {% endif %}

    {% include "service_confs.tpl" %}
    {% include "vts.tpl" %}
}
