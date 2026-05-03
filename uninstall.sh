#!/bin/bash
# mimicode uninstaller - Remove mimicode global installation

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
info "Uninstalling mimicode..."
echo ""

REPO_DIR="$HOME/.mimicode"
INSTALL_DIRS=("/usr/local/bin" "$HOME/.local/bin")

# Find and remove the global command
FOUND=false
for dir in "${INSTALL_DIRS[@]}"; do
    if [ -f "$dir/mimicode" ]; then
        info "Removing $dir/mimicode..."
        rm -f "$dir/mimicode"
        success "Removed global launcher"
        FOUND=true
    fi
done

if [ ! "$FOUND" = true ]; then
    warn "Global mimicode command not found in standard locations"
fi

# Remove repository
if [ -d "$REPO_DIR" ]; then
    warn "About to remove $REPO_DIR"
    echo ""
    echo "This will delete:"
    echo "  - mimicode source code"
    echo "  - Python virtual environment"
    echo "  - Session history (if stored there)"
    echo ""
    read -p "Continue? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        info "Removing $REPO_DIR..."
        rm -rf "$REPO_DIR"
        success "Removed mimicode installation"
    else
        info "Keeping $REPO_DIR"
    fi
else
    warn "mimicode installation directory not found at $REPO_DIR"
fi

echo ""
success "Uninstall complete!"
echo ""
info "Your API key and shell configuration were not modified."
info "To reinstall, run:"
echo "  curl -fsSL https://raw.githubusercontent.com/Nihalsaeed/mimicode/main/install.sh -o /tmp/mimicode-install.sh"
echo "  bash /tmp/mimicode-install.sh"
echo ""
