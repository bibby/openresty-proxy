{% if service.render_confs %}
{% for conf in service.rendered_custom_confs %}
{{ conf | safe }}
{% endfor %}
{% else %}
{% for conf in service.custom_confs %}
{{ conf | safe }}
{% endfor %}
{% endif %}