#!/bin/bash

# iMessage Style Imitator - AI Reply Generator
# Uses Text Style Transfer (TST) to analyze and imitate texting styles
#
# Prerequisites:
#   - Python 3.8+
#   - pip3 install rich openai
#   - OPENAI_API_KEY environment variable set
#   - Full Disk Access for terminal (to read Messages DB)
#   - Accessibility permissions (to send via Messages app)

echo "====================================="
echo "  iMessage Style Imitator (AI TST)"
echo "====================================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found. Install Python 3.8+."
    exit 1
fi

# Check dependencies
python3 -c "import rich, openai" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Installing dependencies..."
    pip3 install -r "$(dirname "$0")/requirements.txt"
    if [ $? -ne 0 ]; then
        echo "Error: Failed to install dependencies."
        exit 1
    fi
fi

# Check API key
if [ -z "$OPENAI_API_KEY" ]; then
    echo "Warning: OPENAI_API_KEY is not set."
    echo ""
    read -p "Enter your OpenAI API key: " API_KEY
    if [ -z "$API_KEY" ]; then
        echo "Error: API key is required."
        exit 1
    fi
    export OPENAI_API_KEY="$API_KEY"
fi

echo "Starting style imitator..."
echo ""

# Run the Python script
python3 "$(dirname "$0")/style_reply.py"
