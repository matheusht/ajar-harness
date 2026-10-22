<?php
// Observer-only receipt sink. The native producer cannot mount or address this
// file; only the target broker can reach this endpoint on its private network.

function t01_valid_snapshot($value)
{
    if ($value === null) {
        return true;
    }
    if (!is_array($value) || array_keys($value) !== ['requested_id', 'swimlane', 'project'] ||
        !is_int($value['requested_id']) || $value['requested_id'] < 1) {
        return false;
    }
    $lane = $value['swimlane'];
    if ($lane !== null && (!is_array($lane) ||
        array_keys($lane) !== ['id', 'project_id', 'name_sha256'] ||
        !is_int($lane['id']) || !is_int($lane['project_id']) ||
        !preg_match('/^[0-9a-f]{64}$/D', $lane['name_sha256']))) {
        return false;
    }
    $project = $value['project'];
    return $project === null || (is_array($project) &&
        array_keys($project) === ['id', 'owner_id', 'is_private', 'is_public',
            'actor_role', 'actor_group_role_count'] &&
        is_int($project['id']) && is_int($project['owner_id']) &&
        in_array($project['is_private'], [0, 1], true) &&
        in_array($project['is_public'], [0, 1], true) &&
        in_array($project['actor_role'], [null, 'project-manager',
            'project-member', 'project-viewer'], true) &&
        is_int($project['actor_group_role_count']) &&
        $project['actor_group_role_count'] >= 0);
}

function t01_valid_receipt($row)
{
    if (!is_array($row) ||
        array_keys($row) !== ['kind', 'request_id', 'peer_ip', 'actor',
            'actor_user_id', 'actor_app_role', 'identity_control', 'method',
            'requested_id', 'backend_status', 'result_class', 'result_matches_db',
            'before', 'after', 'backend_response_sha256',
            'delivered_response_sha256', 'redacted']) {
        return false;
    }
    return $row['kind'] === 't01-kanboard-jsonrpc-v1' &&
        is_string($row['request_id']) &&
        preg_match('/^[0-9a-f]{32}$/D', $row['request_id']) &&
        is_string($row['peer_ip']) &&
        filter_var($row['peer_ip'], FILTER_VALIDATE_IP, FILTER_FLAG_IPV4) &&
        in_array($row['actor'], ['A', 'B'], true) &&
        is_int($row['actor_user_id']) && $row['actor_user_id'] > 0 &&
        $row['actor_app_role'] === 'app-user' && $row['identity_control'] === true &&
        is_string($row['method']) && preg_match('/^[A-Za-z][A-Za-z0-9]{0,79}$/D', $row['method']) &&
        ($row['requested_id'] === null || (is_int($row['requested_id']) && $row['requested_id'] > 0)) &&
        is_int($row['backend_status']) && $row['backend_status'] >= 100 &&
        $row['backend_status'] <= 599 &&
        in_array($row['result_class'], ['access_denied', 'api_error', 'invalid_result',
            'swimlane_result', 'project_result', 'other_result'], true) &&
        is_bool($row['result_matches_db']) &&
        t01_valid_snapshot($row['before']) && t01_valid_snapshot($row['after']) &&
        is_string($row['backend_response_sha256']) &&
        preg_match('/^[0-9a-f]{64}$/D', $row['backend_response_sha256']) &&
        is_string($row['delivered_response_sha256']) &&
        preg_match('/^[0-9a-f]{64}$/D', $row['delivered_response_sha256']) &&
        is_bool($row['redacted']);
}

function t01_valid_setup($row)
{
    return is_array($row) &&
        array_keys($row) === ['kind', 'request_id', 'source_manifest_sha256',
            'actor_ids', 'admin_default_revoked', 'project_count',
            'swimlane_count', 'db_sha256'] &&
        $row['kind'] === 't01-kanboard-setup-v1' &&
        is_string($row['request_id']) &&
        preg_match('/^[0-9a-f]{32}$/D', $row['request_id']) &&
        $row['source_manifest_sha256'] ===
            '5d49c3f485f555f3118b0afb983997e29a5ddaad4b0ed6f9cf19d855c2e4f884' &&
        is_array($row['actor_ids']) && array_keys($row['actor_ids']) === ['A', 'B'] &&
        is_int($row['actor_ids']['A']) && $row['actor_ids']['A'] > 0 &&
        is_int($row['actor_ids']['B']) && $row['actor_ids']['B'] > 0 &&
        $row['actor_ids']['A'] !== $row['actor_ids']['B'] &&
        $row['admin_default_revoked'] === true &&
        $row['project_count'] === 0 && $row['swimlane_count'] === 0 &&
        is_string($row['db_sha256']) &&
        preg_match('/^[0-9a-f]{64}$/D', $row['db_sha256']);
}

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
    $row = json_decode($raw, true, 32, JSON_THROW_ON_ERROR);
    if (!t01_valid_receipt($row) && !t01_valid_setup($row)) {
        throw new RuntimeException('invalid_receipt');
    }
    $db = new PDO('sqlite:/receipts/receipts.sqlite', null, null,
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    $db->exec('CREATE TABLE IF NOT EXISTS receipts ('
        .'id INTEGER PRIMARY KEY AUTOINCREMENT, peer TEXT NOT NULL, payload TEXT NOT NULL)');
    $insert = $db->prepare('INSERT INTO receipts (peer,payload) VALUES (?,?)');
    $insert->execute([$_SERVER['REMOTE_ADDR'], json_encode($row, JSON_UNESCAPED_SLASHES)]);
    http_response_code(204);
} catch (Throwable $error) {
    error_log('T01_CAPTURE_REJECT '.($error instanceof PDOException ? 'storage' : 'invalid'));
    http_response_code(422);
}
