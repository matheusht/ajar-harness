#!/usr/bin/env bash
# P4 — SQL unary-plus predicate test: +<col>.sequence='good' across DB engines
# Verdict: REFUTED (predicate behaves identically+correctly on sqlite, MariaDB, MySQL 5.7, MySQL 8.0)
set -euo pipefail

echo "=== 1. sqlite ==="
sqlite3 :memory: "
CREATE TABLE units(unit TEXT, sequence TEXT, is_stable INTEGER);
INSERT INTO units VALUES ('a','good',1),('b','final-bad',1),('c','temp-bad',1),('d','good',0);
SELECT unit, (+sequence='good') AS matches FROM units;
"

echo ""
echo "=== 2. MariaDB (brew, 11.x) ==="
mariadb -e "
DROP DATABASE IF EXISTS p4test; CREATE DATABASE p4test; USE p4test;
CREATE TABLE units(unit VARCHAR(64), sequence TEXT, is_stable INT);
INSERT INTO units VALUES ('a','good',1),('b','final-bad',1),('c','temp-bad',1),('d','good',0);
SELECT unit, +sequence AS plus_seq, (+sequence='good') AS matches FROM units;
SELECT +'good' AS unary_plus_literal, 0='good' AS zero_eq_literal;
"

echo ""
echo "=== 3. Oracle MySQL 8.0 (docker mysql:8.0.46) ==="
docker exec p4mysql mysql -uroot -e "
DROP DATABASE IF EXISTS p4test; CREATE DATABASE p4test; USE p4test;
CREATE TABLE units(unit VARCHAR(64), sequence TEXT, is_stable INT);
INSERT INTO units VALUES ('a','good',1),('b','final-bad',1),('c','temp-bad',1),('d','good',0);
SELECT unit, +sequence AS plus_seq, (+sequence='good') AS matches FROM units;
SELECT +'good' AS unary_plus_literal, +'123' AS numeric_literal, 0='good' AS zero_eq_literal;
" 2>/dev/null

echo ""
echo "=== 4. Percona/MySQL 5.7 (docker percona:5.7.44) ==="
docker exec p4mysql57 mysql -uroot -e "
DROP DATABASE IF EXISTS p4test57; CREATE DATABASE p4test57; USE p4test57;
CREATE TABLE units(unit VARCHAR(64), sequence TEXT, is_stable INT);
INSERT INTO units VALUES ('a','good',1),('b','final-bad',1),('c','temp-bad',1),('d','good',0);
SELECT unit, +sequence AS plus_seq, (+sequence='good') AS matches FROM units;
SELECT +'good' AS unary_plus_literal, +'123' AS numeric_literal;
" 2>/dev/null

echo ""
echo "EXPECTED (all engines): a|good|1, b|final-bad|0, c|temp-bad|0, d|good|1  => predicate matches ONLY 'good'"
