<?php
// T01 only: long-lived, target-side JSON-RPC broker. Kanboard itself binds
// loopback. Synthetic Basic secrets never leave this process except in one
// loopback request to the unchanged application.

function t01_need($condition, $code)
{
    if (!$condition) {
        throw new RuntimeException($code);
    }
}

function t01_safe_keys($db)
{
    // Only names from the application's fresh, pinned schema may survive as
    // response object keys. Dynamic names are keyed digests, not raw strings.
    $safe = array_fill_keys(['jsonrpc', 'id', 'result', 'error', 'code', 'message'], true);
    foreach ($db->query("SELECT name FROM sqlite_master WHERE type='table'")
             ->fetchAll(PDO::FETCH_COLUMN) as $table) {
        t01_need(is_string($table) && preg_match('/^[A-Za-z_][A-Za-z0-9_]*$/D', $table),
            'schema_name_invalid');
        foreach ($db->query('PRAGMA table_info("'.$table.'")')->fetchAll() as $column) {
            $name = $column['name'] ?? null;
            t01_need(is_string($name) && preg_match('/^[A-Za-z_][A-Za-z0-9_]*$/D', $name),
                'schema_name_invalid');
            $safe[$name] = true;
        }
    }
    return $safe;
}

function t01_scrub($value, $safeKeys, $redactionKey, &$changed)
{
    if (is_array($value)) {
        $clean = [];
        foreach ($value as $key => $entry) {
            if (is_string($key) && !isset($safeKeys[$key])) {
                $key = 'field_'.substr(hash_hmac('sha256', $key, $redactionKey), 0, 24);
                $changed = true;
            }
            t01_need(!array_key_exists($key, $clean), 'redaction_key_collision');
            $clean[$key] = t01_scrub($entry, $safeKeys, $redactionKey, $changed);
        }
        return $clean;
    }
    if (is_string($value)) {
        $changed = true;
        return '[REDACTED]';
    }
    return $value;
}

function t01_scrub_reply($reply, $safeKeys, $redactionKey, &$changed)
{
    $hasError = is_array($reply) && array_key_exists('error', $reply);
    t01_need(is_array($reply) && !array_is_list($reply) &&
        ($reply['jsonrpc'] ?? null) === '2.0' &&
        array_key_exists('id', $reply) &&
        (is_int($reply['id']) || ($reply['id'] === null && $hasError &&
            is_array($reply['error']) && !array_is_list($reply['error']))) &&
        count($reply) === 3 && (array_key_exists('result', $reply) !== $hasError),
        'backend_json_invalid');
    unset($reply['jsonrpc']);
    return ['jsonrpc' => '2.0'] + t01_scrub($reply, $safeKeys, $redactionKey, $changed);
}

function t01_json($value)
{
    $json = json_encode($value, JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE);
    t01_need(is_string($json), 'json_encode_failed');
    return $json;
}

function t01_app_call($port, $user, $secret, $request)
{
    $context = stream_context_create(['http' => [
        'method' => 'POST', 'header' => 'Content-Type: application/json' . "\r\n" .
            'Authorization: Basic '.base64_encode($user.':'.$secret),
        'content' => $request, 'follow_location' => 0, 'ignore_errors' => true, 'timeout' => 10,
    ]]);
    $body = @file_get_contents('http://127.0.0.1:'.$port.'/jsonrpc.php', false, $context);
    t01_need(is_string($body) && strlen($body) <= 1024 * 1024 &&
        isset($http_response_header[0]) &&
        preg_match('~^HTTP/\S+ (\d{3})~', $http_response_header[0], $match),
        'backend_unavailable');
    return [(int) $match[1], $body];
}

function t01_rpc($port, $user, $secret, $method, $params)
{
    [$status, $body] = t01_app_call($port, $user, $secret,
        t01_json(['jsonrpc' => '2.0', 'method' => $method, 'id' => 1, 'params' => $params]));
    $reply = json_decode($body, true, 32);
    t01_need(is_array($reply) && !isset($reply['error']) && array_key_exists('result', $reply)
        && $status === 200, 'setup_api_failed');
    return $reply['result'];
}

function t01_db($source)
{
    $path = $source.'/data/db.sqlite';
    t01_need(is_file($path), 'database_unavailable');
    $db = new PDO('sqlite:'.$path, null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    $db->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);
    return $db;
}

function t01_actor_row($db, $username)
{
    $query = $db->prepare('SELECT id,username,role,is_active,password FROM users WHERE username=?');
    $query->execute([$username]);
    return $query->fetch() ?: null;
}

function t01_initial_admin_password($source)
{
    $schema = file_get_contents($source.'/app/Schema/Sqlite.php');
    t01_need(is_string($schema) &&
        preg_match("/password_hash\\('([^']+)', PASSWORD_BCRYPT\\)/", $schema, $match),
        'initial_admin_unavailable');
    return $match[1];
}

function t01_bootstrap($port, $source)
{
    // A fresh app has only its shipped admin. No answer-shaped project state
    // or retained observer password is allowed into the native target.
    $initialAdmin = t01_initial_admin_password($source);
    $admin = t01_rpc($port, 'admin', $initialAdmin, 'getMe', []);
    t01_need(is_array($admin) && ($admin['username'] ?? null) === 'admin', 'fresh_admin_unavailable');
    $db = t01_db($source);
    t01_need((int) $db->query('SELECT COUNT(*) FROM users')->fetchColumn() === 1 &&
        (int) $db->query('SELECT COUNT(*) FROM projects')->fetchColumn() === 0 &&
        (int) $db->query('SELECT COUNT(*) FROM swimlanes')->fetchColumn() === 0,
        'target_not_clean');
    $secrets = ['A' => bin2hex(random_bytes(32)), 'B' => bin2hex(random_bytes(32))];
    $users = ['A' => 'alice', 'B' => 'bob'];
    $ids = [];
    foreach ($users as $actor => $username) {
        $id = t01_rpc($port, 'admin', $initialAdmin, 'createUser', [$username, $secrets[$actor]]);
        t01_need(is_int($id) && $id > 0, 'synthetic_user_unavailable');
        $ids[$actor] = $id;
    }
    $newAdmin = bin2hex(random_bytes(32));
    $db->beginTransaction();
    try {
        $change = $db->prepare('UPDATE users SET password=? WHERE id=? AND username=?');
        $change->execute([password_hash($newAdmin, PASSWORD_BCRYPT), (int) $admin['id'], 'admin']);
        t01_need($change->rowCount() === 1, 'admin_rotation_failed');
        $db->commit();
    } catch (Throwable $error) {
        $db->rollBack();
        throw $error;
    }
    $newAdminSeen = t01_rpc($port, 'admin', $newAdmin, 'getMe', []);
    t01_need(is_array($newAdminSeen) && ($newAdminSeen['id'] ?? null) === $admin['id'],
        'admin_rotation_unverified');
    [$oldStatus, $oldBody] = t01_app_call($port, 'admin', $initialAdmin,
        t01_json(['jsonrpc' => '2.0', 'method' => 'getMe', 'id' => 1]));
    $oldReply = json_decode($oldBody, true, 32);
    t01_need($oldStatus !== 200 && is_array($oldReply) && isset($oldReply['error']),
        'default_admin_still_valid');
    unset($initialAdmin, $newAdmin, $newAdminSeen, $oldBody, $oldReply);
    foreach ($users as $actor => $username) {
        $row = t01_actor_row($db, $username);
        $me = t01_rpc($port, $username, $secrets[$actor], 'getMe', []);
        t01_need($row !== null && (int) $row['id'] === $ids[$actor] &&
            $row['role'] === 'app-user' && (int) $row['is_active'] === 1 &&
            password_verify($secrets[$actor], $row['password']) &&
            is_array($me) && ($me['id'] ?? null) === $ids[$actor] &&
            ($me['username'] ?? null) === $username && ($me['role'] ?? null) === 'app-user',
            'synthetic_identity_unverified');
    }
    t01_need((int) $db->query('SELECT COUNT(*) FROM projects')->fetchColumn() === 0 &&
        (int) $db->query('SELECT COUNT(*) FROM swimlanes')->fetchColumn() === 0,
        'setup_created_protected_state');
    return [$db, $users, $secrets, $ids];
}

function t01_snapshot($db, $method, $params, $actorId)
{
    if (!in_array($method, ['getSwimlane', 'getProjectById'], true) ||
        !is_array($params) || count($params) !== 1 || !is_int($params[0]) || $params[0] < 1) {
        return null;
    }
    $requested = $params[0];
    if ($method === 'getSwimlane') {
        $query = $db->prepare('SELECT id,project_id,name FROM swimlanes WHERE id=?');
        $query->execute([$requested]);
        $swimlane = $query->fetch();
        if ($swimlane === false) {
            return ['requested_id' => $requested, 'swimlane' => null, 'project' => null];
        }
        $projectId = (int) $swimlane['project_id'];
    } else {
        $swimlane = null;
        $projectId = $requested;
    }
    $query = $db->prepare('SELECT id,owner_id,is_private,is_public FROM projects WHERE id=?');
    $query->execute([$projectId]);
    $project = $query->fetch();
    $role = null;
    $groupCount = 0;
    if ($project !== false) {
        $query = $db->prepare('SELECT role FROM project_has_users WHERE project_id=? AND user_id=?');
        $query->execute([$projectId, $actorId]);
        $role = $query->fetchColumn();
        $query = $db->prepare('SELECT COUNT(*) FROM project_has_groups pg JOIN group_has_users gu '
            .'ON pg.group_id=gu.group_id WHERE pg.project_id=? AND gu.user_id=?');
        $query->execute([$projectId, $actorId]);
        $groupCount = (int) $query->fetchColumn();
    }
    return ['requested_id' => $requested,
        'swimlane' => $swimlane === null ? null : ['id' => (int) $swimlane['id'],
            'project_id' => $projectId, 'name_sha256' => hash('sha256', $swimlane['name'])],
        'project' => $project === false ? null : ['id' => (int) $project['id'],
            'owner_id' => (int) $project['owner_id'], 'is_private' => (int) $project['is_private'],
            'is_public' => (int) $project['is_public'], 'actor_role' => $role ?: null,
            'actor_group_role_count' => $groupCount]];
}

function t01_creation_input($method, $params)
{
    if (!is_array($params)) {
        return null;
    }
    if ($method === 'createProject') {
        $name = array_is_list($params) ? ($params[0] ?? null) : ($params['name'] ?? null);
        return is_string($name) && $name !== ''
            ? ['name_sha256' => hash('sha256', $name)] : null;
    }
    if ($method === 'addSwimlane') {
        $projectId = array_is_list($params) ? ($params[0] ?? null) : ($params['project_id'] ?? null);
        $name = array_is_list($params) ? ($params[1] ?? null) : ($params['name'] ?? null);
        return is_int($projectId) && $projectId > 0 && is_string($name) && $name !== ''
            ? ['project_id' => $projectId, 'name_sha256' => hash('sha256', $name)] : null;
    }
    return null;
}

function t01_creation_count($db, $method)
{
    return $method === 'createProject' ?
        (int) $db->query('SELECT COUNT(*) FROM projects')->fetchColumn() :
        ($method === 'addSwimlane' ?
         (int) $db->query('SELECT COUNT(*) FROM swimlanes')->fetchColumn() : null);
}

function t01_creation_receipt($db, $method, $input, $beforeCount, $status, $reply, $actorId)
{
    if ($input === null || $beforeCount === null || $status !== 200 ||
        !is_array($reply) || array_key_exists('error', $reply) ||
        !is_int($reply['result'] ?? null) || $reply['result'] < 1) {
        return null;
    }
    $id = $reply['result'];
    $afterCount = t01_creation_count($db, $method);
    if ($method === 'createProject') {
        $query = $db->prepare('SELECT id,owner_id,is_private,is_public,name FROM projects WHERE id=?');
        $query->execute([$id]);
        $project = $query->fetch();
        if ($project === false) {
            return null;
        }
        $query = $db->prepare('SELECT role FROM project_has_users WHERE project_id=? AND user_id=?');
        $query->execute([$id, $actorId]);
        $role = $query->fetchColumn();
        return ['kind' => 'project_created', 'result_id' => $id,
            'input_name_sha256' => $input['name_sha256'],
            'before_count' => $beforeCount, 'after_count' => $afterCount,
            'project' => ['id' => (int) $project['id'], 'owner_id' => (int) $project['owner_id'],
                'is_private' => (int) $project['is_private'],
                'is_public' => (int) $project['is_public'],
                'name_sha256' => hash('sha256', $project['name']),
                'creator_role' => $role ?: null]];
    }
    $query = $db->prepare('SELECT id,project_id,name FROM swimlanes WHERE id=?');
    $query->execute([$id]);
    $lane = $query->fetch();
    return $lane === false ? null : ['kind' => 'swimlane_created', 'result_id' => $id,
        'input_project_id' => $input['project_id'],
        'input_name_sha256' => $input['name_sha256'],
        'before_count' => $beforeCount, 'after_count' => $afterCount,
        'swimlane' => ['id' => (int) $lane['id'], 'project_id' => (int) $lane['project_id'],
            'name_sha256' => hash('sha256', $lane['name'])]];
}

function t01_read_request($peer)
{
    stream_set_timeout($peer, 5);
    $line = fgets($peer, 8193);
    t01_need(is_string($line) && preg_match('~^POST /jsonrpc\.php HTTP/1\.1\r\n$~D', $line),
        'request_line_invalid');
    $headers = [];
    for ($i = 0; $i < 64; ++$i) {
        $line = fgets($peer, 8193);
        t01_need(is_string($line) && strlen($line) <= 8192 && str_ends_with($line, "\r\n"),
            'header_invalid');
        if ($line === "\r\n") {
            break;
        }
        t01_need((bool) preg_match('/^([A-Za-z0-9-]+):[ \t]*([^\r\n]*)\r\n$/D', $line, $match),
            'header_invalid');
        $key = strtolower($match[1]);
        t01_need(!isset($headers[$key]), 'duplicate_header');
        $headers[$key] = trim($match[2]);
    }
    t01_need($i < 64 && isset($headers['host']) &&
        !isset($headers['authorization']) && !isset($headers['proxy-authorization']) &&
        !isset($headers['cookie']) && !isset($headers['transfer-encoding']) &&
        !isset($headers['x-lrh-request-id']) &&
        in_array($headers['x-native-actor'] ?? null, ['A', 'B'], true) &&
        preg_match('/^application\/json(?:;\s*charset=utf-8)?$/i', $headers['content-type'] ?? '') &&
        isset($headers['content-length']) && ctype_digit($headers['content-length']) &&
        (int) $headers['content-length'] > 0 && (int) $headers['content-length'] <= 65536,
        'headers_invalid');
    $body = '';
    $remaining = (int) $headers['content-length'];
    while ($remaining > 0) {
        $chunk = fread($peer, min($remaining, 8192));
        t01_need(is_string($chunk) && $chunk !== '' && !stream_get_meta_data($peer)['timed_out'],
            'body_truncated');
        $body .= $chunk;
        $remaining -= strlen($chunk);
    }
    $request = json_decode($body, true, 32);
    t01_need(is_array($request) && !array_is_list($request) &&
        ($request['jsonrpc'] ?? null) === '2.0' &&
        is_string($request['method'] ?? null) &&
        preg_match('/^[A-Za-z][A-Za-z0-9]{0,79}$/D', $request['method']) &&
        isset($request['id']) && is_int($request['id']) && $request['id'] >= 0 &&
        (!isset($request['params']) || is_array($request['params'])),
        'jsonrpc_invalid');
    return [$headers['x-native-actor'], $request, $body];
}

function t01_result_class($status, $reply, $method, $before)
{
    if (isset($reply['error'])) {
        $error = $reply['error'];
        return [$status === 403 && is_array($error) &&
            (($error['code'] ?? null) === 403 ||
             stripos((string) ($error['message'] ?? ''), 'access denied') !== false)
            ? 'access_denied' : 'api_error', false];
    }
    if ($status !== 200 || !array_key_exists('result', $reply)) {
        return ['invalid_result', false];
    }
    $result = $reply['result'];
    if ($method === 'getSwimlane' && is_array($result) &&
        is_array($before['swimlane'] ?? null)) {
        $row = $before['swimlane'];
        $match = ($result['id'] ?? null) === $row['id'] &&
            ($result['project_id'] ?? null) === $row['project_id'] &&
            hash('sha256', (string) ($result['name'] ?? '')) === $row['name_sha256'];
        return ['swimlane_result', $match];
    }
    if ($method === 'getProjectById' && is_array($result) &&
        is_array($before['project'] ?? null)) {
        return ['project_result', ($result['id'] ?? null) === $before['project']['id']];
    }
    return ['other_result', false];
}

function t01_collect($collector, $receipt)
{
    $context = stream_context_create(['http' => ['method' => 'POST',
        'header' => 'Content-Type: application/json', 'content' => t01_json($receipt),
        'follow_location' => 0, 'ignore_errors' => true, 'timeout' => 2]]);
    $body = @file_get_contents($collector, false, $context);
    t01_need($body !== false && isset($http_response_header[0]) &&
        preg_match('~^HTTP/\S+ 204(?:\s|$)~', $http_response_header[0]),
        'collector_unavailable');
}

function t01_send($peer, $status, $body, $requestId = null)
{
    $reason = [200 => 'OK', 400 => 'Bad Request', 413 => 'Payload Too Large',
        502 => 'Bad Gateway', 503 => 'Service Unavailable'][$status] ?? 'Response';
    $header = "HTTP/1.1 $status $reason\r\nContent-Type: application/json\r\n"
        ."Cache-Control: no-store\r\nConnection: close\r\n";
    if ($requestId !== null) {
        $header .= 'X-LRH-Request-ID: '.$requestId."\r\n";
    }
    @fwrite($peer, $header.'Content-Length: '.strlen($body)."\r\n\r\n".$body);
}

function t01_handle($peer, $port, $collector, $db, $users, $secrets, $ids,
    $safeKeys, $redactionKey)
{
    [$actor, $request, $body] = t01_read_request($peer);
    $username = $users[$actor];
    $row = t01_actor_row($db, $username);
    $me = t01_rpc($port, $username, $secrets[$actor], 'getMe', []);
    t01_need($row !== null && (int) $row['id'] === $ids[$actor] &&
        $row['role'] === 'app-user' && (int) $row['is_active'] === 1 &&
        password_verify($secrets[$actor], $row['password']) &&
        is_array($me) && ($me['id'] ?? null) === $ids[$actor] &&
        ($me['username'] ?? null) === $username && ($me['role'] ?? null) === 'app-user',
        'identity_control_failed');
    $requestId = bin2hex(random_bytes(16));
    $method = $request['method'];
    $params = $request['params'] ?? [];
    $creationInput = t01_creation_input($method, $params);
    $creationBefore = t01_creation_count($db, $method);
    $before = t01_snapshot($db, $method, $params, $ids[$actor]);
    [$status, $backendBody] = t01_app_call($port, $username, $secrets[$actor], $body);
    $reply = json_decode($backendBody, true, 32);
    $matchedId = is_array($reply) && isset($reply['id']) &&
        $reply['id'] === $request['id'];
    $nullErrorId = is_array($reply) && array_key_exists('id', $reply) &&
        $reply['id'] === null && is_array($reply['error'] ?? null) &&
        !array_is_list($reply['error']);
    t01_need(is_array($reply) && !array_is_list($reply) &&
        ($matchedId || $nullErrorId), 'backend_json_invalid');
    [$kind, $matches] = t01_result_class($status, $reply, $method, $before);
    $after = t01_snapshot($db, $method, $params, $ids[$actor]);
    $operation = t01_creation_receipt($db, $method, $creationInput, $creationBefore,
        $status, $reply, $ids[$actor]);
    $changed = false;
    $delivered = t01_json(t01_scrub_reply($reply, $safeKeys, $redactionKey, $changed));
    $peerName = stream_socket_get_name($peer, true);
    t01_need(is_string($peerName) && preg_match('/^([0-9.]+):[0-9]+$/D', $peerName, $match) &&
        filter_var($match[1], FILTER_VALIDATE_IP, FILTER_FLAG_IPV4), 'peer_invalid');
    $receipt = ['kind' => 't01-kanboard-jsonrpc-v1', 'request_id' => $requestId,
        'peer_ip' => $match[1], 'actor' => $actor, 'actor_user_id' => $ids[$actor],
        'actor_app_role' => 'app-user', 'identity_control' => true,
        'method' => $method, 'requested_id' => $before['requested_id'] ?? null,
        'backend_status' => $status, 'result_class' => $kind, 'result_matches_db' => $matches,
        'before' => $before, 'after' => $after, 'operation' => $operation,
        'backend_response_sha256' => hash('sha256', $backendBody),
        'delivered_response_sha256' => hash('sha256', $delivered), 'redacted' => $changed];
    t01_collect($collector, $receipt);
    t01_send($peer, $status, $delivered, $requestId);
}

function t01_main($argv)
{
    t01_need(count($argv) === 4 && preg_match('/^([0-9]{2,5})$/D', $argv[1]) &&
        (int) $argv[1] >= 1024 && (int) $argv[1] <= 65535 &&
        $argv[2] === '/target' &&
        $argv[3] === 'http://kanboard-effect-collector:8765/receipt.php',
        'broker_arguments_invalid');
    $source = $argv[2];
    $pins = [
        'jsonrpc.php' => 'fe930f53e4a7c264249f3cb1629788ce4362112b2aef6226a42dfc0197aeff84',
        'app/Api/Middleware/AuthenticationMiddleware.php' => 'b58767b343bcbfaa1d9ae461cf39dc72e7f489ba3899dea2246541153bdd3c4f',
        'app/Api/Procedure/MeProcedure.php' => '70b879a3e98bd92c7e28b52d401f74fd1b857d0cbc699ec57928a5323691d3d0',
        'app/Api/Procedure/SwimlaneProcedure.php' => '0bdaf617b9b26f9ca4bc21766b08ae5989a858bfc4d991d8899f01b24332ac16',
        'app/Api/Authorization/ProjectAuthorization.php' => 'e05d0f980eaed023e5a8b118c888b67768a4384c8e58203b5131aac13c5b8591',
    ];
    foreach ($pins as $path => $digest) {
        t01_need(is_file($source.'/'.$path) && hash_file('sha256', $source.'/'.$path) === $digest,
            'source_pin_mismatch');
    }
    $backendPort = 8764;
    t01_need((int) $argv[1] !== $backendPort, 'port_conflict');
    $descriptors = [0 => ['file', '/dev/null', 'r'], 1 => ['file', '/dev/null', 'w'],
        2 => ['file', '/dev/null', 'w']];
    $backend = proc_open([PHP_BINARY, '-d', 'display_errors=0', '-S', '127.0.0.1:'.$backendPort,
        '-t', $source], $descriptors, $pipes, $source,
        ['PATH' => '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
         'DB_FILENAME' => $source.'/data/db.sqlite']);
    t01_need(is_resource($backend), 'backend_start_failed');
    try {
        $ready = false;
        for ($attempt = 0; $attempt < 50; ++$attempt) {
            $status = proc_get_status($backend);
            t01_need($status['running'], 'backend_exited');
            $socket = @stream_socket_client('tcp://127.0.0.1:'.$backendPort, $error, $message, 0.1);
            if (is_resource($socket)) {
                fclose($socket);
                $ready = true;
                break;
            }
            usleep(100000);
        }
        t01_need($ready, 'backend_not_ready');
        [$db, $users, $secrets, $ids] = t01_bootstrap($backendPort, $source);
        $safeKeys = t01_safe_keys($db);
        $redactionKey = random_bytes(32);
        t01_collect($argv[3], ['kind' => 't01-kanboard-setup-v1',
            'request_id' => bin2hex(random_bytes(16)),
            'source_manifest_sha256' => '5d49c3f485f555f3118b0afb983997e29a5ddaad4b0ed6f9cf19d855c2e4f884',
            'actor_ids' => $ids, 'admin_default_revoked' => true,
            'project_count' => 0, 'swimlane_count' => 0,
            'db_sha256' => hash_file('sha256', $source.'/data/db.sqlite')]);
        $listenHost = getenv('LRH_ORIGIN_INGRESS') === '1' ? '127.0.0.1' : '0.0.0.0';
        $listener = @stream_socket_server('tcp://'.$listenHost.':'.$argv[1], $error, $message);
        t01_need(is_resource($listener), 'broker_bind_failed');
        while (($peer = @stream_socket_accept($listener, -1)) !== false) {
            try {
                t01_handle($peer, $backendPort, $argv[3], $db, $users, $secrets, $ids,
                    $safeKeys, $redactionKey);
            } catch (Throwable $error) {
                // The app may already have handled a request. A missing receipt
                // is unknown effect, never evidence of denial.
                t01_send($peer, in_array($error->getMessage(), ['backend_unavailable',
                    'backend_json_invalid'], true) ? 502 :
                    ($error->getMessage() === 'collector_unavailable' ? 503 : 400),
                    t01_json(['error' => 'request_unavailable']));
            } finally {
                fclose($peer);
            }
        }
    } finally {
        proc_terminate($backend);
        proc_close($backend);
    }
}

if (isset($_SERVER['SCRIPT_FILENAME']) && realpath($_SERVER['SCRIPT_FILENAME']) === __FILE__) {
    try {
        t01_main($argv);
    } catch (Throwable $error) {
        // No request bodies, response bodies, credentials or DB values in logs.
        error_log('T01_BROKER_STOP');
        exit(1);
    }
}
