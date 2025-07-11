#!/bin/bash

# Start Hummingbot with proper environment activation
cd /home/hummingbot

# Check if conda environment exists
if conda env list | grep -q "hummingbot"; then
    echo "Activating hummingbot environment..."
    source /opt/conda/etc/profile.d/conda.sh
    conda activate hummingbot
else
    echo "Error: hummingbot conda environment not found!"
    exit 1
fi

# Ensure logs directory exists with proper permissions
mkdir -p ./logs

# Start Hummingbot
exec python bin/hummingbot_quickstart.py "$@" 2>> ./logs/errors.log
