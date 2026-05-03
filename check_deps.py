#!/usr/bin/env python3
"""Check if all required dependencies are installed for mimicode."""
import shutil
import subprocess
import sys
from pathlib import Path


def check_ripgrep():
    """Check if ripgrep is installed."""
    rg_path = shutil.which("rg")
    if rg_path:
        try:
            result = subprocess.run(
                ["rg", "--version"],
                capture_output=True,
                text=True,
                check=True
            )
            version = result.stdout.split("\n")[0]
            print(f"✅ ripgrep found: {version}")
            return True
        except subprocess.CalledProcessError:
            print("⚠️  ripgrep found but unable to get version")
            return True
    else:
        print("❌ ripgrep (rg) not found")
        print("\nripgrep is REQUIRED for mimicode to function properly.")
        print("The agent uses it for file searching and pattern matching.")
        print("\nInstall instructions:")
        
        # Platform-specific instructions
        if sys.platform == "darwin":
            print("  macOS (Homebrew):")
            print("    brew install ripgrep")
        elif sys.platform.startswith("linux"):
            print("  Ubuntu/Debian:  sudo apt install ripgrep")
            print("  Fedora/RHEL:    sudo dnf install ripgrep")
            print("  Arch Linux:     sudo pacman -S ripgrep")
        elif sys.platform == "win32":
            print("  Windows (Chocolatey): choco install ripgrep")
            print("  Windows (Scoop):      scoop install ripgrep")
        
        print("\n  Or download from: https://github.com/BurntSushi/ripgrep/releases")
        return False


def check_python_packages():
    """Check if required Python packages are installed."""
    requirements_file = Path("requirements.txt")
    
    if not requirements_file.exists():
        print("⚠️  requirements.txt not found")
        return True
    
    missing = []
    with open(requirements_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            # Parse package name (before >= or ==)
            package = line.split(">=")[0].split("==")[0].strip()
            
            try:
                __import__(package.replace("-", "_"))
            except ImportError:
                missing.append(package)
    
    if missing:
        print(f"❌ Missing Python packages: {', '.join(missing)}")
        print("\nInstall them with:")
        print("  pip install -r requirements.txt")
        return False
    else:
        print("✅ All Python packages installed")
        return True


def check_api_key():
    """Check if ANTHROPIC_API_KEY is set."""
    import os
    
    # Try .env file first
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.strip().startswith("ANTHROPIC_API_KEY"):
                    print("✅ API key found in .env file")
                    return True
    
    # Check environment variable
    if os.getenv("ANTHROPIC_API_KEY"):
        print("✅ ANTHROPIC_API_KEY environment variable set")
        return True
    
    print("⚠️  ANTHROPIC_API_KEY not found")
    print("\nSet your API key:")
    print("  export ANTHROPIC_API_KEY='your-key-here'")
    print("\nOr create a .env file with:")
    print("  ANTHROPIC_API_KEY=your-key-here")
    return False


def main():
    """Run all dependency checks."""
    print("🔍 Checking mimicode dependencies...\n")
    
    checks = [
        ("Ripgrep", check_ripgrep),
        ("Python packages", check_python_packages),
        ("API key", check_api_key),
    ]
    
    results = []
    for name, check_func in checks:
        results.append(check_func())
        print()
    
    if all(results[:2]):  # ripgrep and packages are critical
        print("✅ All critical dependencies satisfied!")
        if not results[2]:
            print("⚠️  Remember to set your API key before running mimicode")
        return 0
    else:
        print("❌ Some critical dependencies are missing. Please install them.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
