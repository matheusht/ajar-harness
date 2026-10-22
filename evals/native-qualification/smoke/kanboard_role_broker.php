<?php
// Target-side synthetic actor route. This process retains backend cookies only
// in memory; the native researcher receives no backend credential or CSRF token.

function fail_response($peer, $status)
{
    $reason = [400 => 'Bad Request', 413 => 'Payload Too Large',
        502 => 'Bad Gateway', 503 => 'Service Unavailable'][$status] ?? 'Bad Request';
    $body = $reason."\n";
    @fwrite($peer, "HTTP/1.1 $status $reason\r\nContent-Type: text/plain; charset=utf-8\r\n"
        ."Cache-Control: no-store\r\nConnection: close\r\nContent-Length: ".strlen($body)."\r\n\r\n".$body);
}

function read_request($peer)
{
    stream_set_timeout($peer, 5);
    $line = fgets($peer, 8193);
    if ($line === false || strlen($line) > 8192 || !str_ends_with($line, "\r\n") ||
        !preg_match('~^(GET|POST) (/[^\x00-\x20]*) HTTP/1\.1\r\n$~D', $line, $match)) {
        throw new RuntimeException('request_line_invalid');
    }
    $path = $match[2];
    $method = $match[1];
    if (strlen($path) > 4096 || str_contains($path, '\\') ||
        preg_match('~(?:^|/)\.\.?(/|$)|%2[ef]~i', $path)) {
        throw new RuntimeException('path_invalid');
    }
    $pathname = rawurldecode(explode('?', $path, 2)[0]);
    $asset = str_starts_with($pathname, '/assets/') &&
        preg_match('~\.(?:css|js|png|jpg|jpeg|gif|svg|ico|woff2?|ttf)$~i', $pathname);
    if (!in_array($pathname, ['/', '/index.php', '/jsonrpc.php', '/favicon.ico'], true) && !$asset) {
        throw new RuntimeException('path_out_of_scope');
    }
    $headers = [];
    for ($i = 0; $i < 64; ++$i) {
        $line = fgets($peer, 8193);
        if ($line === false || strlen($line) > 8192 || !str_ends_with($line, "\r\n")) {
            throw new RuntimeException('header_invalid');
        }
        if ($line === "\r\n") {
            break;
        }
        if (!preg_match('/^([A-Za-z0-9-]+):[ \t]*([^\r\n]*)\r\n$/D', $line, $match)) {
            throw new RuntimeException('header_invalid');
        }
        $key = strtolower($match[1]);
        if (isset($headers[$key])) {
            throw new RuntimeException('duplicate_header');
        }
        $headers[$key] = trim($match[2]);
    }
    if ($i === 64 || !isset($headers['host']) || isset($headers['transfer-encoding']) ||
        !isset($headers['x-native-actor']) ||
        !in_array($headers['x-native-actor'], ['A', 'B', 'C'], true)) {
        throw new RuntimeException('headers_invalid');
    }
    $length = $headers['content-length'] ?? '0';
    if (!ctype_digit($length) || strlen($length) > 7 || (int) $length > 1024 * 1024 ||
        ($method === 'POST' && !isset($headers['content-length']))) {
        throw new RuntimeException('body_length_invalid');
    }
    $body = '';
    $remaining = (int) $length;
    while ($remaining > 0) {
        $chunk = fread($peer, min($remaining, 8192));
        if ($chunk === false || $chunk === '' || stream_get_meta_data($peer)['timed_out']) {
            throw new RuntimeException('body_truncated');
        }
        $body .= $chunk;
        $remaining -= strlen($chunk);
    }
    return [$method, $path, $headers, $body];
}

function backend_request($backend, $method, $path, $actor, $handle, $peerIp,
                         $body, $contentType, $cookie)
{
    $requestId = bin2hex(random_bytes(16));
    $headers = ["Host: localhost", "Connection: close", "X-LRH-Actor: $actor",
        "X-LRH-Handle: $handle",
        "X-LRH-Peer: $peerIp",
        'X-LRH-Request-Id: '.$requestId];
    if ($cookie !== null) {
        $headers[] = 'Cookie: KB_SID='.$cookie;
    }
    if ($method === 'POST') {
        $headers[] = 'Content-Type: '.$contentType;
    }
    $context = stream_context_create(['http' => ['method' => $method,
        'header' => implode("\r\n", $headers), 'content' => $body,
        'follow_location' => 0, 'ignore_errors' => true, 'timeout' => 10]]);
    $response = @file_get_contents('http://'.$backend.$path, false, $context);
    if ($response === false || !isset($http_response_header[0]) ||
        !preg_match('~^HTTP/\S+ (\d{3})~', $http_response_header[0], $match)) {
        throw new RuntimeException('backend_unavailable');
    }
    $status = (int) $match[1];
    if ($status < 100 || $status > 599) {
        throw new RuntimeException('backend_status_invalid');
    }
    $safe = [];
    $newCookie = $cookie;
    foreach ($http_response_header as $header) {
        if (preg_match('/^Set-Cookie:\s*KB_SID=([^;\s]*)/i', $header, $parts)) {
            $newCookie = $parts[1] === '' ? null : $parts[1];
        } elseif (preg_match('/^(Content-Type|Location):\s*([^\r\n]*)$/i', $header, $parts)) {
            $name = strtolower($parts[1]);
            if ($name === 'location' && !str_starts_with($parts[2], '/')) {
                continue;
            }
            $safe[$name] = $parts[2];
        }
    }
    return [$status, $safe, $response, $newCookie, $requestId];
}

function redact_tokens($body, &$token)
{
    $body = preg_replace_callback('~(<input\s+type="hidden"\s+name="csrf_token"\s+value=")([^"]+)(")~i',
        function ($match) use (&$token) {
            if ($token === null) {
                $token = $match[2];
            }
            return $match[1].'broker-managed'.$match[3];
        }, $body);
    if (!is_string($body)) {
        throw new RuntimeException('response_redaction_failed');
    }
    $body = preg_replace('/(csrf_token(?:=|%3D))[A-Za-z0-9%]+/i', '$1broker-managed', $body);
    if (!is_string($body)) {
        throw new RuntimeException('response_redaction_failed');
    }
    return $body;
}

if ($argc !== 4 || !preg_match('/^127\.0\.0\.1:[0-9]{2,5}$/', $argv[3]) ||
    !preg_match('/^(127\.0\.0\.1|0\.0\.0\.0):[0-9]{2,5}$/', $argv[1])) {
    exit(2);
}
$map = json_decode(@file_get_contents($argv[2]), true);
if (!is_array($map) || array_keys($map) !== ['A', 'B', 'C'] ||
    count(array_filter($map, fn ($user) => is_string($user) &&
        preg_match('/^[A-Za-z0-9_.-]{1,80}$/D', $user))) !== 3 ||
    count(array_unique($map)) !== 3) {
    exit(3);
}
$listener = @stream_socket_server('tcp://'.$argv[1], $errorNumber, $errorMessage);
if ($listener === false) {
    exit(4);
}
$cookies = ['A' => null, 'B' => null, 'C' => null];
$tokens = ['A' => null, 'B' => null, 'C' => null];
while (($peer = @stream_socket_accept($listener, -1)) !== false) {
    try {
        [$method, $path, $headers, $body] = read_request($peer);
        $peerName = stream_socket_get_name($peer, true);
        if (!is_string($peerName) || !preg_match('/^([0-9.]+):[0-9]+$/D', $peerName, $peerParts) ||
            filter_var($peerParts[1], FILTER_VALIDATE_IP, FILTER_FLAG_IPV4) === false) {
            throw new RuntimeException('peer_invalid');
        }
        $actor = $headers['x-native-actor'];
        $contentType = $headers['content-type'] ?? '';
        if ($method === 'POST' && $contentType !== 'application/x-www-form-urlencoded') {
            throw new RuntimeException('content_type_invalid');
        }
        if ($method === 'POST') {
            parse_str($body, $form);
            if (isset($form['csrf_token']) && $form['csrf_token'] === 'broker-managed') {
                if ($tokens[$actor] === null) {
                    throw new RuntimeException('token_unavailable');
                }
                $form['csrf_token'] = $tokens[$actor];
                $body = http_build_query($form);
            }
        }
        [$status, $safe, $response, $cookie, $requestId] = backend_request(
            $argv[3], $method, $path, $map[$actor], $actor, $peerParts[1],
            $body, $contentType, $cookies[$actor]);
        $cookies[$actor] = $cookie;
        $response = redact_tokens($response, $tokens[$actor]);
        if (isset($safe['location'])) {
            $safe['location'] = redact_tokens($safe['location'], $tokens[$actor]);
        }
        $reason = [200 => 'OK', 302 => 'Found', 303 => 'See Other', 403 => 'Forbidden',
            404 => 'Not Found'][$status] ?? 'Response';
        $wire = "HTTP/1.1 $status $reason\r\nCache-Control: no-store\r\nConnection: close\r\n"
            .'X-LRH-Request-ID: '.$requestId."\r\n";
        foreach ($safe as $name => $value) {
            $wire .= $name.': '.$value."\r\n";
        }
        $wire .= 'Content-Length: '.strlen($response)."\r\n\r\n".$response;
        @fwrite($peer, $wire);
    } catch (Throwable $error) {
        fail_response($peer, $error->getMessage() === 'backend_unavailable' ? 502 : 400);
    } finally {
        fclose($peer);
    }
}
