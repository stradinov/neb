#!/usr/bin/env bash
# Convierte stdin a slug: lowercase, solo a-z0-9 y guiones, sin guiones repetidos ni en bordes.
sed 's/^[[:space:]#]*//' \
  | tr '[:upper:]' '[:lower:]' \
  | iconv -t ASCII//TRANSLIT 2>/dev/null \
  | tr -c 'a-z0-9' '-' \
  | sed 's/--*/-/g; s/^-//; s/-$//'
