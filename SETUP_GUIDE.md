# mimicode Global Installation Setup Guide

This guide explains how to set up mimicode for global installation via curl.

## For Repository Maintainers

### Step 1: Update Repository URLs

Before publishing, replace all instances of `YOUR_USERNAME` with your actual GitHub username:

```bash
# In install.sh (line ~64)
git clone --quiet https://github.com/YOUR_GITHUB_USERNAME/mimicode.git "$REPO_DIR"

# In install.sh wrapper (line ~89)
curl -fsSL https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/mimicode/main/install.sh | bash

# In uninstall.sh (line ~59)
curl -fsSL https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/mimicode/main/install.sh | bash

# In README.md (multiple locations)
# Replace all YOUR_USERNAME occurrences
```

Or use this command to do it automatically:

```bash
# Replace YOUR_USERNAME with your actual GitHub username
GITHUB_USER="your-username-here"

# macOS
sed -i '' "s/YOUR_USERNAME/$GITHUB_USER/g" install.sh uninstall.sh README.md

# Linux
sed -i "s/YOUR_USERNAME/$GITHUB_USER/g" install.sh uninstall.sh README.md
```

### Step 2: Test Installation Locally

Before publishing, test the install script locally:

```bash
# Run the test script
./test-install.sh

# Try a local installation (without curl)
bash install.sh

# Verify it works
mimicode --help

# Uninstall
bash uninstall.sh
```

### Step 3: Push to GitHub

```bash
git add install.sh uninstall.sh mimicode mimicode.bat README.md SETUP_GUIDE.md
git commit -m "Add global installation support"
git push origin main
```

### Step 4: Test Remote Installation

After pushing to GitHub, test the remote installation:

```bash
# Test the curl installation
curl -fsSL https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/mimicode/main/install.sh | bash

# Verify it works
cd /tmp
mimicode --help

# Clean up
curl -fsSL https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/mimicode/main/uninstall.sh | bash
```

## For Users

### Prerequisites

Install these once:

1. **Python 3.8+**
   ```bash
   # Check if installed
   python3 --version
   
   # Install if needed
   # macOS: brew install python3
   # Ubuntu: sudo apt install python3
   # Download: https://www.python.org/downloads/
   ```

2. **ripgrep**
   ```bash
   # macOS
   brew install ripgrep
   
   # Ubuntu/Debian
   sudo apt install ripgrep
   
   # Fedora
   sudo dnf install ripgrep
   
   # Windows (Chocolatey)
   choco install ripgrep
   ```

3. **Git**
   ```bash
   # Check if installed
   git --version
   
   # Install if needed
   # macOS: brew install git
   # Ubuntu: sudo apt install git
   # Windows: https://git-scm.com/download/win
   ```

### Installation

```bash
# Install mimicode globally
curl -fsSL https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/mimicode/main/install.sh | bash

# Set your API key (add to ~/.bashrc or ~/.zshrc for persistence)
export ANTHROPIC_API_KEY="your-key-here"

# Run from anywhere!
cd ~/my-project
mimicode
```

### How It Works

The installer:
1. Clones mimicode to `~/.mimicode`
2. Creates a global wrapper script in `/usr/local/bin/mimicode` (or `~/.local/bin/mimicode`)
3. When you run `mimicode` from any directory:
   - Activates the Python virtual environment in `~/.mimicode/.venv`
   - Installs dependencies if needed
   - Launches the TUI
   - Works on files in your current directory

### Usage

```bash
# Navigate to any project
cd ~/my-website

# Run mimicode
mimicode

# Inside the TUI:
# - Type your prompt and press Enter
# - Use /cwd to change working directory
# - Use /help for more commands
```

### Updating

```bash
# Re-run the installer to update
curl -fsSL https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/mimicode/main/install.sh | bash
```

### Uninstalling

```bash
# Remove mimicode
curl -fsSL https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/mimicode/main/uninstall.sh | bash
```

## Troubleshooting

### "mimicode: command not found"

The installation directory may not be in your PATH. Add it manually:

```bash
# Check where mimicode was installed
which mimicode

# If it's in ~/.local/bin, add to PATH:
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### "ripgrep (rg) is required"

Install ripgrep:
```bash
# See prerequisites section above
```

### "ANTHROPIC_API_KEY is not set"

Set your API key:
```bash
# Temporary (current session only)
export ANTHROPIC_API_KEY="your-key"

# Permanent (add to shell profile)
echo 'export ANTHROPIC_API_KEY="your-key"' >> ~/.bashrc
source ~/.bashrc
```

### Permission Denied

If you can't write to `/usr/local/bin`:

```bash
# Install to user directory instead
MIMICODE_INSTALL_DIR="$HOME/.local/bin" bash install.sh
```

## Architecture

```
Installation Structure:
~/.mimicode/              # mimicode repository
  ├── .venv/             # Python virtual environment
  ├── agent.py           # Main agent code
  ├── tools.py           # Tool implementations
  ├── tui.py             # TUI interface
  └── ...                # Other mimicode files

/usr/local/bin/mimicode   # Global wrapper script
  or
~/.local/bin/mimicode     # User-local wrapper script

Working Directory:        # Where you run 'mimicode'
  └── your-project-files  # Files the agent works on
```

The wrapper script:
1. Stores where you ran `mimicode` (your working directory)
2. Changes to `~/.mimicode` to activate venv and run agent
3. Changes back to your working directory before launching
4. Agent works on files in your working directory

## Files Created

### install.sh
- Main installation script
- Clones repository to `~/.mimicode`
- Creates global wrapper command
- Checks prerequisites

### uninstall.sh
- Removes global wrapper command
- Optionally removes `~/.mimicode`
- Preserves API key and shell config

### mimicode (wrapper script)
- Installed to `/usr/local/bin` or `~/.local/bin`
- Activates venv in `~/.mimicode`
- Installs dependencies if needed
- Runs agent in your current directory

### mimicode (local launcher)
- Used when running from cloned repository
- Does not require global installation
- Works in the repository directory

### mimicode.bat (Windows)
- Windows version of local launcher
- Same functionality as bash version
