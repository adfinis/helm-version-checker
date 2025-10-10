#!/bin/sh -l

printenv

python /app/version_checker.py \
  --token="${INPUT_TOKEN}" \
  --charts-path="${INPUT_CHARTSPATH}" \
  --maintainers-file="${INPUT_MAINTAINERSFILE}"
