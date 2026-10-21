<?php
// Owned inert effect; a missing client result must never be treated as no effect.
$path = $_SERVER['REQUEST_URI'];
if ($_SERVER['REQUEST_METHOD'] !== 'POST' ||
    !preg_match('~^/effect/(positive|pre-dispatch|post-effect|pre-ack)$~D', $path, $match) ||
    ($_SERVER['CONTENT_LENGTH'] ?? '0') !== '0') {
    http_response_code(400);
    exit;
}
$case = $match[1];
$ledger = fopen('/state/effects.jsonl', 'ab');
if (!$ledger || !flock($ledger, LOCK_EX)) {
    http_response_code(500);
    exit;
}
$row = json_encode(['case' => $case, 'effect' => 'inert_append']) . "\n";
if (fwrite($ledger, $row) !== strlen($row) || !fflush($ledger) || !fsync($ledger)) {
    fclose($ledger);
    http_response_code(500);
    exit;
}
flock($ledger, LOCK_UN);
fclose($ledger);
if ($case === 'post-effect') {
    $deadline = hrtime(true) + 15000000000;
    while (!file_exists('/state/release-post-effect') && hrtime(true) < $deadline) {
        usleep(50000);
    }
    if (!file_exists('/state/release-post-effect')) {
        http_response_code(504);
        exit;
    }
    file_put_contents('/state/response-attempted', 'after-release');
}
header('Content-Type: text/plain');
echo 'ACK:' . $case . "\n";
