#!/usr/bin/env python3
"""
Setup script for Convoy - installs package and registers .convoy files on Windows
"""

import sys
import subprocess
import os
import platform


def install_package():
    """Install convoy in editable mode"""
    print("📦 Installing convoy...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", "."],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    if result.returncode != 0:
        print("❌ Failed to install convoy")
        sys.exit(1)
    print("✓ Convoy installed successfully")


def register_windows_file_type():
    """Register .convoy files with Windows Registry"""
    if platform.system() != "Windows":
        print("⚠️  Not on Windows, skipping file type registration")
        return
    
    try:
        import winreg
    except ImportError:
        print("⚠️  winreg not available, skipping file type registration")
        return
    
    print("📋 Registering .convoy file type on Windows...")
    
    try:
        # Get the path to the convoy command
        convoy_path = subprocess.check_output(
            [sys.executable, "-m", "site", "--user-scripts"],
            text=True
        ).strip()
        
        # On Windows, the executable might be convoy.exe or convoy.bat
        convoy_exe = os.path.join(convoy_path, "convoy.exe")
        if not os.path.exists(convoy_exe):
            convoy_exe = os.path.join(convoy_path, "convoy")
        
        if not os.path.exists(convoy_exe):
            print(f"⚠️  Could not find convoy executable at {convoy_exe}")
            return
        
        # Open/create registry keys
        with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, ".convoy") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "ConvoyPackage")
        
        with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, "ConvoyPackage") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "Convoy Package File")
        
        # Set the command to run when double-clicked
        command = f'"{convoy_exe}" run --fast "%1"'
        with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, r"ConvoyPackage\shell\open\command") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)
        
        print(f"✓ Registered .convoy files")
        print(f"  Command: {command}")
        print("✓ You can now double-click .convoy files to run them!")
        
    except Exception as e:
        print(f"❌ Failed to register file type: {e}")
        print("   You may need to run this script as Administrator")
        sys.exit(1)


def main():
    print("🚀 Convoy Setup")
    print("=" * 50)
    
    # Install the package
    install_package()
    
    # Register file type on Windows
    register_windows_file_type()
    
    print("=" * 50)
    print("✓ Setup complete!")
    print("\n📝 Usage:")
    print("  convoy build          # Build a .convoy file")
    print("  convoy run file.convoy # Run a .convoy file")
    print("  convoy-settings       # Open settings GUI")


if __name__ == "__main__":
    main()
