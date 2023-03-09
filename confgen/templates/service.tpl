#########
## {{service.fqdn}}
########
upstream {{service.fqdn}} {
    {% for container in service.containers %}
    server {{container.ip_address}}:{{container.exposed_port}}{% if container.options %} {{container.options}}{% endif %};{% endfor %}
}

{% include "http.tpl" %}
{% include "https.tpl" %}


