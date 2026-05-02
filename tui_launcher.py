#!/usr/bin/env python3
"""Simple launcher script for Mimicode TUI.

This script provides a convenient way to launch the TUI without
remembering command-line flags.
"""
import sys
import os


def check_requirements():
    """Check if required packages are installed."""
    missing = []
    
    try:
        import anthropic
    except ImportError:
        missing.append("anthropic")
    
    try:
        import textual
    except ImportError:
        missing.append("textual")
    
    if missing:
        print("❌ Missing required packages:", ", ".join(missing))
        print("\nInstall them with:")
        print("  pip install -r requirements.txt")
        print("\nOr individually:")
        for pkg in missing:
            print(f"  pip install {pkg}")
        return False
    
    return True


def check_api_key():
    """Check if ANTHROPIC_API_KEY is set."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("❌ ANTHROPIC_API_KEY environment variable is not set")
        print("\nSet it with:")
        print("  Linux/Mac:  export ANTHROPIC_API_KEY=your_key_here")
        print("  Windows:    set ANTHROPIC_API_KEY=your_key_here")
        print("  PowerShell: $env:ANTHROPIC_API_KEY=\"your_key_here\"")
        return False
    
    return True


def main():
    """Launch the TUI with basic checks."""
    print("🚀 Mimicode TUI Launcher")
    print("=" * 50)
    
    # Check requirements
    print("\n📦 Checking requirements...")
    if not check_requirements():
        sys.exit(1)
    print("✅ All packages installed")
    
    # Check API key
    print("\n🔑 Checking API key...")
    if not check_api_key():
        sys.exit(1)
    print("✅ API key configured")
    
    # Launch TUI
    print("\n🎨 Launching TUI...")
    print("=" * 50)
    print()
    
    try:
        from tui import main as tui_main
        
        # Pass session argument if provided
        session_id = None
        if len(sys.argv) > 1:
            session_id = sys.argv[1]
            print(f"📂 Using session: {session_id}\n")
        
        tui_main(session_id=session_id)
        
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
