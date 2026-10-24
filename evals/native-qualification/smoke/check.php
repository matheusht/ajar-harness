<?php
require __DIR__ . '/message.php';
$passed = message() === 'after';
if (PHP_SAPI !== 'cli') {
    http_response_code($passed ? 200 : 500);
    header('Content-Type: text/plain');
    echo $passed ? "check passed\n" : "check failed\n";
    return;
}
if (!$passed) {
    fwrite(STDERR, "message() must return after\n");
    exit(1);
}
echo "check passed\n";
