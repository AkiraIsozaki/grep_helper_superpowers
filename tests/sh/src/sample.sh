#!/bin/bash
# sample.sh - Shell E2E test fixture
MY_CODE="TARGET"

if [ "$MY_CODE" = "check" ]; then
    echo "$MY_CODE"
fi
grep "$MY_CODE" data.txt
