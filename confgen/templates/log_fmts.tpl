    log_format vhost '$host $remote_addr - $remote_user [$time_local] '
                     '"$request" $status $body_bytes_sent '
                     '"$http_referer" "$http_user_agent"';

    log_format graylog2_json escape=json '{ "timestamp": "$time_iso8601", '
      '"remote_addr": "$remote_addr", '
      '"body_bytes_sent": $body_bytes_sent, '
      '"request_time": $request_time, '
      '"response_status": $status, '
      '"request": "$request", '
      '"request_verb": "$request_method", '
      '"host": "$host",'
      '"upstream_cache_status": "$upstream_cache_status",'
      '"upstream_addr": "$upstream_addr",'
      '"http_x_forwarded_for": "$http_x_forwarded_for",'
      '"http_referrer": "$http_referer", '
      '"http_user_agent": "$http_user_agent" }';