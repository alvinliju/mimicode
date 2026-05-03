#!/bin/bash
# Test script for mimicode installation
# Tests the install.sh script in a simulated environment

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

success() { echo -e "${GREEN}✅ $1${NC}"; }
error() { echo -e "${RED}❌ $1${NC}"; }
info() { echo -e "${BLUE}ℹ️  $1${NC}"; }

echo ""
info "Testing mimicode installation script..."
echo ""

# Test 1: Check install.sh exists and is executable
if [ -x "install.sh" ]; then
    success "install.sh exists and is executable"
else
    error "install.sh not found or not executable"
    exit 1
fi

# Test 2: Check uninstall.sh exists and is executable
if [ -x "uninstall.sh" ]; then
    success "uninstall.sh exists and is executable"
else
    error "uninstall.sh not found or not executable"
    exit 1
fi

# Test 3: Check mimicode launcher exists and is executable
if [ -x "mimicode" ]; then
    success "mimicode launcher exists and is executable"
else
    error "mimicode launcher not found or not executable"
    exit 1
fi

# Test 4: Check for placeholder URLs that need to be updated
PLACEHOLDERS=$(rg -l "YOUR_USERNAME" install.sh uninstall.sh README.md 2>/dev/null || true)
if [ -n "$PLACEHOLDERS" ]; then
    info "Found placeholder URLs that need to be updated:"
    echo "$PLACEHOLDERS" | while read -r file; do
        echo "  - $file"
    done
    echo ""
    info "Replace YOUR_USERNAME with your actual GitHub username before publishing"
else
    success "No placeholder URLs found"
fi

# Test 5: Validate bash syntax
if bash -n install.sh; then
    success "install.sh has valid bash syntax"
else
    error "install.sh has syntax errors"
    exit 1
fi

if bash -n uninstall.sh; then
    success "uninstall.sh has valid bash syntax"
else
    error "uninstall.sh has syntax errors"
    exit 1
fi

if bash -n mimicode; then
    success "mimicode has valid bash syntax"
else
    error "mimicode has syntax errors"
    exit 1
fi

# Test 6: Check for required files
REQUIRED_FILES=(
    "agent.py"
    "tools.py"
    "providers.py"
    "logger.py"
    "tui.py"
    "requirements.txt"
    "README.md"
)

ALL_FOUND=true
for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        success "Found $file"
    else
        error "Missing required file: $file"
        ALL_FOUND=false
    fi
done

if [ "$ALL_FOUND" = false ]; then
    exit 1
fi

echo ""
success "All installation script tests passed!"
echo ""
info "Before publishing:"
echo "  1. Update YOUR_USERNAME in install.sh, uninstall.sh, and README.md"
echo "  2. Push to GitHub"
echo "  3. Test the installation with:"
echo "     curl -fsSL https://raw.githubusercontent.com/YOUR_USERNAME/mimicode/main/install.sh | bash"
echo ""
