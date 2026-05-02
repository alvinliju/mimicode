#!/usr/bin/env python3
"""Verification script for TUI setup."""
import sys
import os
import io

# Ensure UTF-8 output on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


def print_header(text):
    """Print a formatted header."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def print_status(check_name, passed, message=""):
    """Print check status."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} - {check_name}")
    if message:
        print(f"      {message}")


def main():
    """Run verification checks."""
    print_header("Mimicode TUI Verification")
    
    all_passed = True
    
    # Check 1: Python version
    print("\n📌 Checking Python version...")
    py_version = sys.version_info
    passed = py_version >= (3, 10)
    print_status(
        "Python version",
        passed,
        f"Found: {py_version.major}.{py_version.minor}.{py_version.micro}" +
        ("" if passed else " (Need 3.10+)")
    )
    all_passed = all_passed and passed
    
    # Check 2: Required modules
    print("\n📌 Checking required modules...")
    
    modules = {
        "anthropic": "Anthropic API client",
        "textual": "Terminal UI framework",
        "pytest": "Testing framework (optional)"
    }
    
    for module_name, description in modules.items():
        try:
            __import__(module_name)
            print_status(module_name, True, description)
        except ImportError:
            print_status(module_name, False, f"{description} - Install with: pip install {module_name}")
            if module_name != "pytest":  # pytest is optional
                all_passed = False
    
    # Check 3: API Key
    print("\n📌 Checking API key...")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    passed = bool(api_key)
    print_status(
        "ANTHROPIC_API_KEY",
        passed,
        "Set" if passed else "Not set - Required for actual use"
    )
    if not passed:
        print("      Set with: export ANTHROPIC_API_KEY=your_key_here")
    
    # Check 4: Core files
    print("\n📌 Checking core files...")
    
    required_files = [
        ("agent.py", "Main agent script"),
        ("tui.py", "TUI implementation"),
        ("logger.py", "Logging system"),
        ("providers.py", "API providers"),
        ("tools.py", "Tool implementations"),
    ]
    
    for filename, description in required_files:
        exists = os.path.exists(filename)
        print_status(filename, exists, description)
        all_passed = all_passed and exists
    
    # Check 5: TUI can be imported
    print("\n📌 Checking TUI import...")
    try:
        from tui import MimicodeApp, main
        print_status("TUI module", True, "Can be imported successfully")
    except Exception as e:
        print_status("TUI module", False, f"Import error: {e}")
        all_passed = False
    
    # Check 6: Agent integration
    print("\n📌 Checking agent integration...")
    try:
        from agent import parse_args
        args = parse_args(["--tui"])
        passed = hasattr(args, 'tui') and args.tui
        print_status("--tui flag", passed, "Agent recognizes TUI flag")
        all_passed = all_passed and passed
    except Exception as e:
        print_status("--tui flag", False, f"Error: {e}")
        all_passed = False
    
    # Check 7: Documentation
    print("\n📌 Checking documentation...")
    
    docs = [
        "TUI_README.md",
        "QUICKSTART_TUI.md",
        "TUI_IMPLEMENTATION.md",
        "TUI_VISUAL_GUIDE.md",
        "RUN_TUI.md",
    ]
    
    docs_exist = all(os.path.exists(doc) for doc in docs)
    print_status("Documentation", docs_exist, f"{sum(os.path.exists(d) for d in docs)}/{len(docs)} files found")
    
    # Final summary
    print_header("Verification Summary")
    
    if all_passed and api_key:
        print("\n✅ All checks passed! You're ready to use the TUI.")
        print("\n🚀 Run the TUI with:")
        print("   python agent.py --tui")
        print("\n   Or use the launcher:")
        print("   python tui_launcher.py")
        return 0
    elif all_passed:
        print("\n⚠️  Setup is mostly complete, but you need to set ANTHROPIC_API_KEY")
        print("\n   Set it with:")
        print("   export ANTHROPIC_API_KEY=your_key_here")
        print("\n   Then try the demo:")
        print("   python demo_tui.py")
        return 0
    else:
        print("\n❌ Some checks failed. Please fix the issues above.")
        print("\n   Install missing packages:")
        print("   pip install -r requirements.txt")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nVerification cancelled.")
        sys.exit(1)
