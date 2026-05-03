#!/bin/bash
# Setup script for mimicode - checks dependencies and helps install them

set -e

echo "🔍 Checking mimicode dependencies..."
echo ""

# Check for ripgrep
if command -v rg &> /dev/null; then
    RG_VERSION=$(rg --version | head -n1)
    echo "✅ ripgrep found: $RG_VERSION"
else
    echo "❌ ripgrep (rg) not found"
    echo ""
    echo "ripgrep is required for file searching in mimicode."
    echo "Install it using one of these methods:"
    echo ""
    
    # Detect OS and provide specific instructions
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "  macOS (Homebrew):"
        echo "    brew install ripgrep"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if command -v apt &> /dev/null; then
            echo "  Ubuntu/Debian:"
            echo "    sudo apt install ripgrep"
        elif command -v dnf &> /dev/null; then
            echo "  Fedora/RHEL:"
            echo "    sudo dnf install ripgrep"
        elif command -v pacman &> /dev/null; then
            echo "  Arch Linux:"
            echo "    sudo pacman -S ripgrep"
        else
            echo "  Linux:"
            echo "    Download from: https://github.com/BurntSushi/ripgrep/releases"
        fi
    elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
        echo "  Windows (Chocolatey):"
        echo "    choco install ripgrep"
        echo "  Windows (Scoop):"
        echo "    scoop install ripgrep"
    fi
    echo ""
    echo "  Or download from: https://github.com/BurntSushi/ripgrep/releases"
    echo ""
    exit 1
fi

# Check for Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo "✅ Python found: $PYTHON_VERSION"
else
    echo "❌ Python 3 not found. Please install Python 3.8 or later."
    exit 1
fi

# Check for pip
if command -v pip3 &> /dev/null || command -v pip &> /dev/null; then
    echo "✅ pip found"
else
    echo "❌ pip not found. Please install pip."
    exit 1
fi

echo ""
echo "📦 Installing Python dependencies..."

# Create venv if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate venv
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    source .venv/Scripts/activate
else
    source .venv/bin/activate
fi

# Install requirements
pip install -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Set your API key: export ANTHROPIC_API_KEY='your-key-here'"
echo "  2. Activate the virtual environment: source .venv/bin/activate"
echo "  3. Run mimicode: python agent.py --tui"
echo ""
