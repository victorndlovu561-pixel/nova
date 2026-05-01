"""Simple config module for platform detection."""
import sys


def is_windows():
    """Check if running on Windows."""
    return sys.platform == "win32"


def is_mac():
    """Check if running on macOS."""
    return sys.platform == "darwin"


def is_linux():
    """Check if running on Linux."""
    return sys.platform.startswith("linux")


def get_os():
    """Get the current operating system name."""
    if is_windows():
        return "windows"
    elif is_mac():
        return "mac"
    elif is_linux():
        return "linux"
    return "unknown"
