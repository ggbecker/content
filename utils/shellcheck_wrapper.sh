#!/bin/bash

shellcheck_executable="$1"
shift
scripts_directory="$1"
shift
shellcheck_options=("$@")

"$shellcheck_executable" "${shellcheck_options[@]}" "$scripts_directory"/*
