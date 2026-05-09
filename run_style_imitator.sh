#!/bin/bash

# iMessage Style Imitator - AI Reply Generator (Ollama)
# Uses Text Style Transfer (TST) to analyze and imitate texting styles
#
# Prerequisites:
#   - Python 3.8+
#   - Ollama installed and running (https://ollama.com)
#   - At least one model pulled (e.g. ollama pull llama3.1)
#   - Full Disk Access for terminal (to read Messages DB)
#   - Accessibility permissions (to send via Messages app)

echo "====================================="
echo "  iMessage Style Imitator (Ollama)"
echo "====================================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found. Install Python 3.8+."
    exit 1
fi

# Check dependencies
python3 -c "import rich, requests" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Installing Python dependencies..."
    pip3 install -r "$(dirname "$0")/requirements.txt"
    if [ $? -ne 0 ]; then
        echo "Error: Failed to install dependencies."
        exit 1
    fi
fi

# Check if Ollama is running
OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
if ! curl -s "$OLLAMA_HOST/api/tags" > /dev/null 2>&1; then
    echo "Error: Ollama is not running at $OLLAMA_HOST"
    echo ""
    echo "Start Ollama with:"
    echo "  ollama serve"
    echo ""
    echo "Install from: https://ollama.com"
    echo ""
    echo "Then pull a model:"
    echo "  ollama pull llama3.1"
    echo "  ollama pull mistral"
    echo "  ollama pull gemma2"
    exit 1
fi

echo "Ollama detected. Starting style imitator..."
echo ""

# Run the Python script
python3 "$(dirname "$0")/style_reply.py"
