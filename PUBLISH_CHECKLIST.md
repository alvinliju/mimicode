# Publishing Checklist for Global Installation

Follow these steps to enable global installation of mimicode via curl.

## Step 1: Update GitHub Repository URLs

Replace `YOUR_USERNAME` with your actual GitHub username in these files:

### Files to Update:
- [ ] `install.sh` (lines 64, 89, 106)
- [ ] `uninstall.sh` (line 59)
- [ ] `README.md` (lines 19, 37, 79, 160, 165)

### Quick Update Command:

```bash
# Replace YOUR_USERNAME with your actual GitHub username
GITHUB_USER="your-github-username"

# macOS
sed -i '' "s/YOUR_USERNAME/$GITHUB_USER/g" install.sh uninstall.sh README.md

# Linux
sed -i "s/YOUR_USERNAME/$GITHUB_USER/g" install.sh uninstall.sh README.md
```

Verify the changes:
```bash
rg "YOUR_USERNAME" install.sh uninstall.sh README.md
# Should return no results after updating
```

## Step 2: Local Testing

- [ ] Run test script: `./test-install.sh`
- [ ] Test local installation: `bash install.sh`
- [ ] Verify command works: `mimicode --help`
- [ ] Test uninstall: `bash uninstall.sh`
- [ ] Confirm cleanup: `ls ~/.mimicode` (should not exist)

## Step 3: Commit and Push

```bash
git add install.sh uninstall.sh mimicode mimicode.bat \
        README.md SETUP_GUIDE.md test-install.sh \
        PUBLISH_CHECKLIST.md

git commit -m "Add global installation support

- Add install.sh for one-command global installation
- Add uninstall.sh for clean removal
- Update mimicode launcher to auto-setup environment
- Add Windows support with mimicode.bat
- Add comprehensive documentation"

git push origin main
```

## Step 4: Test Remote Installation

After pushing to GitHub:

```bash
# Download installer from GitHub
curl -fsSL https://raw.githubusercontent.com/Nihalsaeed/mimicode/main/install.sh -o /tmp/mimicode-install.sh

# Run it
bash /tmp/mimicode-install.sh

# Verify it works
cd /tmp
mkdir test-project
cd test-project
echo "print('hello')" > test.py
mimicode --help

# Test uninstall
curl -fsSL https://raw.githubusercontent.com/Nihalsaeed/mimicode/main/uninstall.sh -o /tmp/mimicode-uninstall.sh
bash /tmp/mimicode-uninstall.sh
```

## Step 5: Create GitHub Release (Optional)

1. Go to your repository on GitHub
2. Click "Releases" → "Create a new release"
3. Tag version: `v1.0.0`
4. Release title: "Global Installation Support"
5. Description:
   ```markdown
   ## New: Easy Global Installation
   
   Install mimicode globally with:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/Nihalsaeed/mimicode/main/install.sh -o /tmp/mimicode-install.sh
   bash /tmp/mimicode-install.sh
   ```
   
   ## Features
   - Run `mimicode` from any directory
   - Auto-manages virtual environment
   - Auto-installs dependencies
   - Works on files in current directory
   
   ## Prerequisites
   - Python 3.8+
   - ripgrep
   - git
   
   See [README.md](README.md) for full installation instructions.
   ```

## Step 6: Update Documentation

Add a badge to README.md (optional):

```markdown
[![Install](https://img.shields.io/badge/install-curl%20script-blue)](https://raw.githubusercontent.com/$GITHUB_USER/mimicode/main/install.sh)
```

## Verification Checklist

Before announcing:

- [ ] `YOUR_USERNAME` replaced in all files
- [ ] Local install/uninstall works
- [ ] Remote install from GitHub works
- [ ] Can run `mimicode` from any directory
- [ ] Agent works on files in current directory
- [ ] `/cwd` command works in TUI
- [ ] Dependencies auto-install
- [ ] API key warning shows when not set
- [ ] README.md has clear installation instructions
- [ ] SETUP_GUIDE.md is accurate

## Post-Publication

Share the installation command:

```bash
# Download installer
curl -fsSL https://raw.githubusercontent.com/Nihalsaeed/mimicode/main/install.sh -o /tmp/mimicode-install.sh

# Run installer
bash /tmp/mimicode-install.sh

# Set API key
export ANTHROPIC_API_KEY="your-key"

# Run from anywhere
cd ~/my-project
mimicode
```

## Rollback Plan

If issues are found:

1. Document the issue
2. Fix locally
3. Test with `./test-install.sh`
4. Push fix
5. Ask users to re-run installer to update

## Support

Expected user questions:

**Q: How do I update?**
A: Download and re-run the installer:
```bash
curl -fsSL https://raw.githubusercontent.com/Nihalsaeed/mimicode/main/install.sh -o /tmp/mimicode-install.sh
bash /tmp/mimicode-install.sh
```

**Q: Where is mimicode installed?**
A: Repository: `~/.mimicode`, Command: `/usr/local/bin/mimicode` or `~/.local/bin/mimicode`

**Q: How do I uninstall?**
A: Download and run the uninstaller:
```bash
curl -fsSL https://raw.githubusercontent.com/Nihalsaeed/mimicode/main/uninstall.sh -o /tmp/mimicode-uninstall.sh
bash /tmp/mimicode-uninstall.sh
```

**Q: Can I use a different installation directory?**
A: Yes: `MIMICODE_INSTALL_DIR=/custom/path bash install.sh`

**Q: My sessions disappeared after updating**
A: Sessions are stored in the directory where you run mimicode, not in `~/.mimicode`

## Success Metrics

- [ ] Users can install with one command
- [ ] Installation works on macOS, Linux
- [ ] Users can run from any directory
- [ ] Updates work smoothly
- [ ] Uninstall is clean

## Files Created

- `install.sh` - Global installation script
- `uninstall.sh` - Clean removal script  
- `mimicode` - Enhanced local launcher
- `mimicode.bat` - Windows local launcher
- `test-install.sh` - Installation test script
- `SETUP_GUIDE.md` - Detailed setup documentation
- `PUBLISH_CHECKLIST.md` - This file
- Updated `README.md` - New Quick Start section

---

**Status**: Ready to publish after replacing YOUR_USERNAME

**Contact**: Open an issue on GitHub if problems occur
