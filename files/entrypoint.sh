#!/bin/sh

# turn on bash's job control
set -m

echo "Starting nginx.."
nginx &
echo "Starting our application.."
sleep infinity
