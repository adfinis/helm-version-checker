#!/bin/sh -l


python /app/scripts/version_checker.py \
  --token="${INPUT_TOKEN}" \
  --charts-path="${INPUT_CHARTS_PATH}" \
  --maintainers-file="${INPUT_MAINTAINERS_FILE}" \
