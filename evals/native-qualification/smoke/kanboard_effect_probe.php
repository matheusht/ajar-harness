<?php
// Kanboard v1.2.36 local capture candidate, loaded only with PHP auto_prepend_file.
// It never modifies Kanboard source or returns observer data to the HTTP client.

if (PHP_SAPI !== 'cli-server' || getenv('NATIVE_EFFECT_COLLECTOR') === false) {
    return;
}

function nq_effect_id($value)
{
    return is_scalar($value) && ctype_digit((string) $value) ? (int) $value : 0;
}

function nq_effect_snapshot($dbPath, $s, $q, $t, $b)
{
    if (!is_file($dbPath)) {
        throw new RuntimeException('database_unavailable');
    }
    $db = new PDO('sqlite:'.$dbPath, null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    $db->exec('PRAGMA query_only=ON');
    $project = $db->prepare('SELECT owner_id,is_private,is_public,token FROM projects WHERE id=?');
    $project->execute([$s]);
    $sRow = $project->fetch(PDO::FETCH_NUM);
    $project->execute([$q]);
    $qRow = $project->fetch(PDO::FETCH_NUM);
    $task = $db->prepare('SELECT project_id,title,is_active FROM tasks WHERE id=?');
    $task->execute([$t]);
    $tRow = $task->fetch(PDO::FETCH_NUM);
    if (!$sRow || !$qRow || !$tRow) {
        throw new RuntimeException('protected_row_unavailable');
    }
    $role = $db->prepare('SELECT role FROM project_has_users WHERE project_id=? AND user_id=?');
    $role->execute([$s, $b]);
    $sRole = $role->fetchColumn();
    $role->execute([$q, $b]);
    $qRole = $role->fetchColumn();
    $groups = $db->prepare('SELECT COUNT(*) FROM project_has_groups pg '
        .'JOIN group_has_users gu ON pg.group_id=gu.group_id WHERE pg.project_id=? AND gu.user_id=?');
    $groups->execute([$q, $b]);
    return [
        's_owner_id' => (int) $sRow[0], 's_is_private' => (int) $sRow[1],
        'q_owner_id' => (int) $qRow[0], 'q_is_private' => (int) $qRow[1],
        'q_is_public' => (int) $qRow[2], 'q_has_public_token' => !empty($qRow[3]),
        't_project_id' => (int) $tRow[0], 't_title_sha256' => hash('sha256', $tRow[1]),
        't_is_active' => (int) $tRow[2],
        'b_s_role' => $sRole === false ? null : $sRole,
        'b_q_role' => $qRole === false ? null : $qRole,
        'b_q_group_role_count' => (int) $groups->fetchColumn(),
    ];
}

$s = nq_effect_id(getenv('NATIVE_EFFECT_S'));
$q = nq_effect_id(getenv('NATIVE_EFFECT_Q'));
$t = nq_effect_id(getenv('NATIVE_EFFECT_T'));
$b = nq_effect_id(getenv('NATIVE_EFFECT_B'));
$dbPath = getenv('DB_FILENAME') ?: '';
$method = $_SERVER['REQUEST_METHOD'] ?? '';
$controller = $_GET['controller'] ?? '';
$action = $_GET['action'] ?? '';
$script = basename($_SERVER['SCRIPT_NAME'] ?? '');
$kind = $script === 'jsonrpc.php' ? 'jsonrpc' : 'other';
if ($script !== 'jsonrpc.php' && $method === 'POST' &&
    $controller === 'ProjectPermissionController' && $action === 'addUser') {
    $kind = 'web_add';
} elseif ($script !== 'jsonrpc.php' && $method === 'GET' &&
          $controller === 'TaskViewController' && $action === 'show') {
    $kind = 'web_task';
}
$before = null;
$preError = null;
try {
    if (!$s || !$q || !$t || !$b || !$dbPath) {
        throw new RuntimeException('probe_configuration_unavailable');
    }
    $before = nq_effect_snapshot($dbPath, $s, $q, $t, $b);
} catch (Throwable $error) {
    $preError = 'prestate_unavailable';
}

register_shutdown_function(function () use ($s, $q, $t, $b, $dbPath, $method, $kind, $before, $preError) {
    $receipt = [
        'kind' => $kind,
        'request_id' => bin2hex(random_bytes(12)),
        'method' => in_array($method, ['GET', 'POST'], true) ? $method : 'other',
        'remote_addr' => filter_var($_SERVER['REMOTE_ADDR'] ?? '', FILTER_VALIDATE_IP) ?: '',
        'php_pid' => getmypid(),
        'controller_sha256' => hash_file('sha256',
            (getenv('NATIVE_EFFECT_SOURCE_DIR') ?: __DIR__.'/../app').'/app/Controller/ProjectPermissionController.php') ?: '',
        'actor_id' => 0, 'app_role' => '', 'effective_project_role' => '',
        'route_project_id' => nq_effect_id($_GET['project_id'] ?? null),
        'body_project_id' => nq_effect_id($_POST['project_id'] ?? null),
        'body_user_id' => nq_effect_id($_POST['user_id'] ?? null),
        'task_id' => nq_effect_id($_GET['task_id'] ?? null),
        'status' => 0, 'marker_present' => false, 'response_sha256' => '',
        'before' => $before, 'after' => null, 'probe_error' => $preError,
    ];
    try {
        $receipt['after'] = nq_effect_snapshot($dbPath, $s, $q, $t, $b);
        $container = $GLOBALS['container'] ?? null;
        if ($container === null) {
            throw new RuntimeException('app_context_unavailable');
        }
        $session = $container['userSession'];
        $receipt['actor_id'] = (int) $session->getId();
        $receipt['app_role'] = (string) $session->getRole();
        if ($receipt['actor_id'] > 0) {
            $projectId = $kind === 'web_add' ? $s : ($kind === 'web_task' ? $q : 0);
            if ($projectId > 0) {
                $receipt['effective_project_role'] = (string)
                    $container['projectUserRoleModel']->getUserRole($projectId, $receipt['actor_id']);
            }
        }
        $response = $container['response'];
        $reflection = new ReflectionClass($response);
        $body = (string) $reflection->getProperty('httpBody')->getValue($response);
        $responseStatus = (int) $reflection->getProperty('httpStatusCode')->getValue($response);
        $wireStatus = http_response_code();
        $receipt['status'] = $responseStatus !== 200 ? $responseStatus :
            ($wireStatus >= 300 && $wireStatus < 400 ? $wireStatus : 200);
        $receipt['response_sha256'] = hash('sha256', $body);
        if ($kind === 'web_task') {
            $db = new PDO('sqlite:'.$dbPath, null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
            $db->exec('PRAGMA query_only=ON');
            $title = $db->prepare('SELECT title FROM tasks WHERE id=?');
            $title->execute([$t]);
            $marker = $title->fetchColumn();
            $receipt['marker_present'] = is_string($marker) && $marker !== '' && str_contains($body, $marker);
        }
    } catch (Throwable $error) {
        $receipt['probe_error'] = $receipt['probe_error'] ?: 'poststate_or_app_context_unavailable';
    }
    // Never retain URL, headers, credentials, cookies, raw form data or body.
    $json = json_encode($receipt, JSON_UNESCAPED_SLASHES);
    if ($json !== false) {
        $context = stream_context_create(['http' => ['method' => 'POST',
            'header' => 'Content-Type: application/json', 'content' => $json,
            'timeout' => 1, 'ignore_errors' => true]]);
        @file_get_contents(getenv('NATIVE_EFFECT_COLLECTOR'), false, $context);
    }
});
