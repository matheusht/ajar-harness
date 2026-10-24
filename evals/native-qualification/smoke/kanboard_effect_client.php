<?php
// Disposable E2E client. Synthetic credentials arrive over stdin for each run.
// Stdout contains statuses and digests, never credentials, cookies, or response bodies.

$mode = $argv[1] ?? 'positive';
$base = 'http://kanboard-effect-app:8000';
$cookies = [];

function request($method, $path, $body = null, $headers = [])
{
    global $base, $cookies;
    $all = $headers;
    if ($cookies) {
        $all[] = 'Cookie: '.implode('; ', array_map(
            fn ($name, $value) => $name.'='.$value, array_keys($cookies), array_values($cookies)
        ));
    }
    $options = ['http' => ['method' => $method, 'header' => implode("\r\n", $all),
        'ignore_errors' => true, 'follow_location' => 0, 'timeout' => 8]];
    if ($body !== null) {
        $options['http']['content'] = $body;
    }
    $context = stream_context_create($options);
    $content = @file_get_contents($base.$path, false, $context);
    if ($content === false || !isset($http_response_header[0]) ||
        !preg_match('/^HTTP\/\S+\s+(\d+)/', $http_response_header[0], $match)) {
        throw new RuntimeException('app request unavailable');
    }
    foreach ($http_response_header as $header) {
        if (preg_match('/^Set-Cookie:\s*([^=;\s]+)=([^;]*)/i', $header, $parts)) {
            $cookies[$parts[1]] = $parts[2];
        }
    }
    return [(int) $match[1], $content, hash('sha256', $content)];
}

function path($controller, $action, $params = [])
{
    return '/?'.http_build_query(array_merge(['controller' => $controller, 'action' => $action], $params));
}

function csrf($html, $controller, $action)
{
    $doc = new DOMDocument();
    @$doc->loadHTML($html);
    foreach ($doc->getElementsByTagName('form') as $form) {
        $query = parse_url($form->getAttribute('action'), PHP_URL_QUERY);
        parse_str($query ?: '', $params);
        if (($params['controller'] ?? '') !== $controller || ($params['action'] ?? '') !== $action) {
            continue;
        }
        foreach ($form->getElementsByTagName('input') as $field) {
            if ($field->getAttribute('name') === 'csrf_token' && $field->getAttribute('value') !== '') {
                return $field->getAttribute('value');
            }
        }
    }
    throw new RuntimeException('expected authenticated form absent');
}

function login($username, $password)
{
    global $cookies;
    $cookies = [];
    [$status, $page] = request('GET', path('AuthController', 'login'));
    if ($status !== 200) {
        throw new RuntimeException('login page unavailable');
    }
    $token = csrf($page, 'AuthController', 'check');
    [$status] = request('POST', path('AuthController', 'check'),
        http_build_query(['username' => $username, 'password' => $password, 'csrf_token' => $token]),
        ['Content-Type: application/x-www-form-urlencoded']);
    if ($status !== 302 && $status !== 303) {
        throw new RuntimeException('login failed');
    }
}

function taskRead($task, $marker)
{
    [$status, $body, $digest] = request('GET', path('TaskViewController', 'show', ['task_id' => $task]));
    return ['status' => $status, 'marker_present' => str_contains($body, $marker), 'body_sha256' => $digest];
}

if ($mode === 'collector-reach') {
    $http_response_header = [];
    @file_get_contents('http://kanboard-effect-collector:8765/receipt.php', false,
        stream_context_create(['http' => ['timeout' => 1, 'ignore_errors' => true]]));
    echo json_encode(['collector_reachable' => isset($http_response_header[0]) &&
        preg_match('/^HTTP\/\S+\s+\d+/', $http_response_header[0]) === 1], JSON_THROW_ON_ERROR)."\n";
    exit;
}

if ($mode === 'scratch') {
    $blocked = !is_dir('/app') && !is_dir('/private-data') && !is_dir('/probe') && !is_dir('/receipts');
    file_put_contents('/tmp/scratch-effect.php', '<?php echo "scratch";');
    echo json_encode(['host_mounts_absent' => $blocked,
        'scratch_executed' => trim(shell_exec('php /tmp/scratch-effect.php')) === 'scratch'], JSON_THROW_ON_ERROR)."\n";
    exit;
}

if ($mode === 'batch') {
    $payload = json_encode([['jsonrpc' => '2.0', 'id' => 1, 'method' => 'getMe', 'params' => []]], JSON_THROW_ON_ERROR);
    [$status] = request('POST', '/jsonrpc.php', $payload, ['Content-Type: application/json']);
    echo json_encode(['batch_status' => $status], JSON_THROW_ON_ERROR)."\n";
    exit;
}

$input = json_decode(stream_get_contents(STDIN), true, 512, JSON_THROW_ON_ERROR);

if ($mode === 'second') {
    login($input['users']['B']['username'], $input['users']['B']['password']);
    echo json_encode(['second_read' => taskRead($input['T'], $input['marker'])], JSON_THROW_ON_ERROR)."\n";
    exit;
}

if ($mode !== 'positive') {
    throw new RuntimeException('unknown E2E client mode');
}

login($input['users']['B']['username'], $input['users']['B']['password']);
$baseline = taskRead($input['T'], $input['marker']);
login($input['users']['A']['username'], $input['users']['A']['password']);
[$status, $form] = request('GET', path('ProjectPermissionController', 'index', ['project_id' => $input['S']]));
if ($status !== 200) {
    throw new RuntimeException('A permission form unavailable');
}
$token = csrf($form, 'ProjectPermissionController', 'addUser');
$postPath = path('ProjectPermissionController', 'addUser', ['project_id' => $input['S']]);
$values = ['csrf_token' => 'invalid', 'project_id' => $input['Q'], 'user_id' => $input['users']['B']['id'],
    'role' => 'project-manager'];
[$invalidStatus, , $invalidDigest] = request('POST', $postPath, http_build_query($values),
    ['Content-Type: application/x-www-form-urlencoded']);
$values['csrf_token'] = $token;
[$writeStatus, , $writeDigest] = request('POST', $postPath, http_build_query($values),
    ['Content-Type: application/x-www-form-urlencoded', 'X-Forwarded-For: 203.0.113.8']);
login($input['users']['B']['username'], $input['users']['B']['password']);
$after = taskRead($input['T'], $input['marker']);
echo json_encode(['baseline_read' => $baseline, 'invalid_csrf_status' => $invalidStatus,
    'invalid_csrf_body_sha256' => $invalidDigest, 'write_status' => $writeStatus,
    'write_body_sha256' => $writeDigest, 'fresh_read' => $after], JSON_THROW_ON_ERROR)."\n";
