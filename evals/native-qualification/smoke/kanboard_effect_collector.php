<?php
// Host-owned endpoint on the app-only internal Docker network. SQLite is not
// mounted in the app or researcher container.

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST' ||
    ($_SERVER['REMOTE_ADDR'] ?? '') !== getenv('EXPECTED_APP_IP')) {
    http_response_code(403);
    return;
}

$raw = file_get_contents('php://input', false, null, 0, 8193);
if (!is_string($raw) || strlen($raw) > 8192) {
    http_response_code(413);
    return;
}

try {
    $record = json_decode($raw, true, 32, JSON_THROW_ON_ERROR);
    $allowed = ['kind', 'request_id', 'broker_request_id', 'broker_handle', 'broker_peer_ip', 'method',
        'remote_addr', 'php_pid', 'controller_sha256',
        'actor_id', 'app_role', 'effective_project_role', 'route_project_id',
        'body_project_id', 'body_user_id', 'task_id', 'status', 'marker_present',
        'response_sha256', 'before', 'after', 'probe_error'];
    if (!is_array($record) || array_keys($record) !== $allowed) {
        throw new RuntimeException('invalid_keys');
    }
    if (!in_array($record['kind'], ['web_add', 'web_task', 'jsonrpc', 'other'], true) ||
        !in_array($record['method'], ['GET', 'POST', 'other'], true)) {
        throw new RuntimeException('invalid_route');
    }
    if (!preg_match('/^[0-9a-f]{24}$/', $record['request_id']) ||
        ($record['broker_request_id'] !== '' &&
         !preg_match('/^[0-9a-f]{32}$/D', $record['broker_request_id'])) ||
        !in_array($record['broker_handle'], ['', 'A', 'B', 'C'], true) ||
        (($record['broker_request_id'] === '') !== ($record['broker_handle'] === '')) ||
        (($record['broker_request_id'] === '') !== ($record['broker_peer_ip'] === '')) ||
        ($record['broker_peer_ip'] !== '' &&
         filter_var($record['broker_peer_ip'], FILTER_VALIDATE_IP) === false) ||
        filter_var($record['remote_addr'], FILTER_VALIDATE_IP) === false ||
        !preg_match('/^[0-9a-f]{64}$/', $record['controller_sha256']) ||
        !preg_match('/^[0-9a-f]{64}$/', $record['response_sha256'])) {
        throw new RuntimeException('invalid_digest_or_address');
    }
    if (!is_bool($record['marker_present']) ||
        !is_int($record['actor_id']) || !is_int($record['status']) ||
        !is_int($record['route_project_id']) || !is_int($record['body_project_id']) ||
        !is_int($record['body_user_id']) || !is_int($record['task_id']) ||
        !is_int($record['php_pid'])) {
        throw new RuntimeException('invalid_number');
    }
    if (!is_string($record['app_role']) || !is_string($record['effective_project_role']) ||
        strlen($record['app_role']) > 80 || strlen($record['effective_project_role']) > 80 ||
        ($record['probe_error'] !== null && !in_array($record['probe_error'],
            ['prestate_unavailable', 'poststate_or_app_context_unavailable'], true))) {
        throw new RuntimeException('invalid_role_or_error');
    }
    $stateKeys = ['s_owner_id', 's_is_private', 'q_owner_id', 'q_is_private',
        'q_is_public', 'q_has_public_token', 't_project_id', 't_title_sha256',
        't_is_active', 'b_s_role', 'b_q_role', 'b_q_group_role_count'];
    foreach (['before', 'after'] as $phase) {
        $state = $record[$phase];
        if ($state !== null && (!is_array($state) || array_keys($state) !== $stateKeys ||
            !preg_match('/^[0-9a-f]{64}$/', $state['t_title_sha256']) ||
            !is_bool($state['q_has_public_token']) ||
            !in_array($state['b_s_role'], [null, 'project-manager', 'project-member', 'project-viewer'], true) ||
            !in_array($state['b_q_role'], [null, 'project-manager', 'project-member', 'project-viewer'], true))) {
            throw new RuntimeException('invalid_state');
        }
    }
    $db = new PDO('sqlite:/receipts/receipts.sqlite', null, null,
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    $db->exec('CREATE TABLE IF NOT EXISTS receipts ('
        .'id INTEGER PRIMARY KEY AUTOINCREMENT, peer TEXT NOT NULL, payload TEXT NOT NULL)');
    $insert = $db->prepare('INSERT INTO receipts (peer,payload) VALUES (?,?)');
    $insert->execute([$_SERVER['REMOTE_ADDR'], json_encode($record, JSON_UNESCAPED_SLASHES)]);
    http_response_code(204);
} catch (Throwable $error) {
    // Keep the rejected body out of HTTP and logs; the caller fails attribution
    // when no matching receipt is committed.
    $reason = $error instanceof PDOException ? 'storage' :
        ($error instanceof RuntimeException && in_array($error->getMessage(),
            ['invalid_keys', 'invalid_route', 'invalid_digest_or_address', 'invalid_number',
             'invalid_role_or_error', 'invalid_state'], true) ? $error->getMessage() : 'internal');
    error_log('NQ_CAPTURE_REJECT '.$reason);
    http_response_code(422);
}
