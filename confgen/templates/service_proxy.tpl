listen 443 ssl ;
client_max_body_size {{service.max_upload_size}};

{% include "service_log.tpl" %}

{% include "ssl_common.tpl" %}

{% include "service_loc.tpl" %}