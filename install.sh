#!/bin/bash
# mimicode installer - Install mimicode globally
# Usage: 
#   curl -fsSL https://raw.githubusercontent.com/Nihalsaeed/mimicode/main/install.sh -o /tmp/mimicode-install.sh
#   bash /tmp/mimicode-install.sh

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

error() { echo -e "${RED}❌ $1${NC}" >&2; exit 1; }
info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
success() { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }

echo ""
info "Installing mimicode..."
echo ""

# Determine install location
if [ -n "$MIMICODE_INSTALL_DIR" ]; then
    INSTALL_DIR="$MIMICODE_INSTALL_DIR"
elif [ -w "/usr/local/bin" ]; then
    INSTALL_DIR="/usr/local/bin"
elif [ -w "$HOME/.local/bin" ]; then
    INSTALL_DIR="$HOME/.local/bin"
else
    INSTALL_DIR="$HOME/.local/bin"
    mkdir -p "$INSTALL_DIR"
fi

REPO_DIR="$HOME/.mimicode"

# Check prerequisites
info "Checking prerequisites..."

if ! command -v git &> /dev/null; then
    error "git is required but not found. Please install git first."
fi

if ! command -v python3 &> /dev/null; then
    error "Python 3 is required but not found. Please install Python 3.8 or later."
fi

if ! command -v rg &> /dev/null; then
    warn "ripgrep (rg) is not installed. It's required for mimicode to work."
    echo ""
    echo "Install ripgrep using one of these methods:"
    echo ""
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "  brew install ripgrep"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if command -v apt &> /dev/null; then
            echo "  sudo apt install ripgrep"
        elif command -v dnf &> /dev/null; then
            echo "  sudo dnf install ripgrep"
        elif command -v pacman &> /dev/null; then
            echo "  sudo pacman -S ripgrep"
        fi
    fi
    echo ""
    echo "Or download from: https://github.com/BurntSushi/ripgrep/releases"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Clone or update repository
if [ -d "$REPO_DIR" ]; then
    info "Updating existing installation at $REPO_DIR..."
    cd "$REPO_DIR"
    git pull --quiet
else
    info "Cloning mimicode to $REPO_DIR..."
    # Update this URL to your actual GitHub repository
    git clone --quiet https://github.com/Nihalsaeed/mimicode.git "$REPO_DIR" || \
        error "Failed to clone repository. Please check the repository URL."
fi

success "Repository installed at $REPO_DIR"

# Create wrapper script
info "Creating global launcher at $INSTALL_DIR/mimicode..."

cat > "$INSTALL_DIR/mimicode" << 'WRAPPER_EOF'
#!/bin/bash
# mimicode global wrapper
# Runs mimicode from the current directory

set -e

MIMICODE_HOME="$HOME/.mimicode"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

error() { echo -e "${RED}❌ $1${NC}" >&2; exit 1; }
info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
success() { echo -e "${GREEN}✅ $1${NC}"; }

# Check if mimicode is installed
if [ ! -d "$MIMICODE_HOME" ]; then
    error "mimicode is not installed at $MIMICODE_HOME
    
Run the installer:
  curl -fsSL https://raw.githubusercontent.com/Nihalsaeed/mimicode/main/install.sh -o /tmp/mimicode-install.sh
  bash /tmp/mimicode-install.sh"
fi

# Store the current working directory (where user wants to work)
WORK_DIR="$(pwd)"

# Change to mimicode installation directory
cd "$MIMICODE_HOME"

# Check for ripgrep
if ! command -v rg &> /dev/null; then
    error "ripgrep (rg) is required but not found. Please install it:
    
    macOS:         brew install ripgrep
    Ubuntu/Debian: sudo apt install ripgrep
    Fedora:        sudo dnf install ripgrep
    Arch:          sudo pacman -S ripgrep
    Windows:       choco install ripgrep  OR  scoop install ripgrep
    
    Or download from: https://github.com/BurntSushi/ripgrep/releases"
fi

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    error "Python 3 is required but not found. Please install Python 3.8 or later."
fi

# Check for API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo -e "${YELLOW}⚠️  ANTHROPIC_API_KEY environment variable is not set.${NC}"
    echo ""
    echo "To set your API key, run:"
    echo "  export ANTHROPIC_API_KEY='your-key-here'"
    echo ""
    echo "Or add it to your shell profile (~/.bashrc, ~/.zshrc, etc.):"
    echo "  echo 'export ANTHROPIC_API_KEY=\"your-key-here\"' >> ~/.bashrc"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    info "Creating Python virtual environment..."
    python3 -m venv .venv
    success "Virtual environment created"
fi

# Activate virtual environment
source .venv/bin/activate

# Check if dependencies are installed
NEEDS_INSTALL=false
if ! python3 -c "import anthropic" &> /dev/null 2>&1; then
    NEEDS_INSTALL=true
elif ! python3 -c "import textual" &> /dev/null 2>&1; then
    NEEDS_INSTALL=true
fi

# Install/update dependencies if needed
if [ "$NEEDS_INSTALL" = true ]; then
    info "Installing Python dependencies..."
    pip install -q --upgrade pip
    pip install -q -r requirements.txt
    success "Dependencies installed"
fi

# Change back to user's working directory
cd "$WORK_DIR"

# Run mimicode TUI with the working directory as context
info "Starting mimicode TUI in: $WORK_DIR"
echo ""
exec python3 "$MIMICODE_HOME/agent.py" --tui "$@"
WRAPPER_EOF

chmod +x "$INSTALL_DIR/mimicode"
success "Global launcher created"

# Check if install dir is in PATH
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    warn "$INSTALL_DIR is not in your PATH"
    echo ""
    echo "Add it to your shell profile to use 'mimicode' command:"
    echo ""
    
    # Detect shell and provide specific instructions
    if [ -n "$BASH_VERSION" ]; then
        echo "  echo 'export PATH=\"$INSTALL_DIR:\$PATH\"' >> ~/.bashrc"
        echo "  source ~/.bashrc"
    elif [ -n "$ZSH_VERSION" ]; then
        echo "  echo 'export PATH=\"$INSTALL_DIR:\$PATH\"' >> ~/.zshrc"
        echo "  source ~/.zshrc"
    else
        echo "  export PATH=\"$INSTALL_DIR:\$PATH\""
    fi
    echo ""
fi

# Check for API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
    warn "ANTHROPIC_API_KEY is not set"
    echo ""
    echo "Set your Anthropic API key:"
    if [ -n "$BASH_VERSION" ]; then
        echo "  echo 'export ANTHROPIC_API_KEY=\"your-key-here\"' >> ~/.bashrc"
        echo "  source ~/.bashrc"
    elif [ -n "$ZSH_VERSION" ]; then
        echo "  echo 'export ANTHROPIC_API_KEY=\"your-key-here\"' >> ~/.zshrc"
        echo "  source ~/.zshrc"
    else
        echo "  export ANTHROPIC_API_KEY='your-key-here'"
    fi
    echo ""
fi

echo ""
success "mimicode installed successfully!"
echo ""
info "Installation complete. You can now:"
echo "  1. Set your API key (if not already set)"
echo "  2. Run 'mimicode' from any directory"
echo ""
echo "The agent will work on files in your current directory."
echo ""
