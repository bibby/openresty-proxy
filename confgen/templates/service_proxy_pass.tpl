listen 443 ;
client_max_body_size {{service.max_upload_size}};

{% include "ssl_common.tpl" %}
proxy_ssl_session_reuse off;

{% include "service_loc.tpl" %}