<?php
$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
if ($path === '/health') {
    echo "ready\n";
    return;
}
$input = json_decode(file_get_contents('php://input'), true);
file_put_contents('/log/shape.jsonl', json_encode([
    'path' => $path,
    'keys' => is_array($input) ? array_keys($input) : [],
    'stream' => is_array($input) ? ($input['stream'] ?? null) : null,
]) . "\n", FILE_APPEND);

if (!str_ends_with($path, '/chat/completions')) {
    http_response_code(501);
    echo "unsupported route\n";
    return;
}

header('Content-Type: text/event-stream');
$base = ['id' => 'chatcmpl-owned', 'object' => 'chat.completion.chunk',
    'created' => 1, 'model' => 'deepseek-v4.1-flash-free'];
$response = 'data: ' . json_encode($base + ['choices' => [[
    'index' => 0, 'delta' => ['role' => 'assistant', 'content' => 'OK'],
    'finish_reason' => null,
]]]) . "\n\n";
$response .= 'data: ' . json_encode($base + ['choices' => [[
    'index' => 0, 'delta' => new stdClass(), 'finish_reason' => 'stop',
]], 'usage' => ['prompt_tokens' => 5, 'completion_tokens' => 1, 'total_tokens' => 6]]) . "\n\n";
$response .= "data: [DONE]\n\n";
file_put_contents('/log/response.bin', $response);
echo $response;
