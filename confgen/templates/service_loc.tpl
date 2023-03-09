{% if service.auth_cert_bundle %}
ssl_client_certificate {{ service.auth_cert_bundle }};
ssl_verify_depth 2;
ssl_verify_client optional;
{% endif %}

{% if not service.skip_root_location %}
location / {
    {% if service.auth_basic_file %}
    auth_basic           "{{ service.fqdn }}";
    auth_basic_user_file {{ service.auth_basic_file }};
    {% endif %}

    {% if service.auth_cert_bundle %}
    if ($ssl_client_verify != SUCCESS) {
      return 403;
    }
    {% endif %}
    proxy_pass http://{{service.upstream}};
}
{% endif %}