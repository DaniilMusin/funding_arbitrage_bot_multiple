#!/usr/bin/env python3
"""
Patch for Cython to work with Python 3.13+
This script adds compatibility for the removed 'cgi' module
"""

import os
import sys
import shutil
from pathlib import Path

def create_cgi_compatibility():
    """Create a compatibility module for the removed 'cgi' module"""
    
    # Find Cython installation
    try:
        import Cython
        cython_path = Path(Cython.__file__).parent
    except ImportError:
        print("Cython not found")
        return False
    
    # Create compatibility module
    tempita_path = cython_path / "Tempita"
    if not tempita_path.exists():
        print("Tempita directory not found")
        return False
    
    # Create a simple cgi compatibility module
    cgi_compat_content = '''"""
Compatibility module for the removed 'cgi' module in Python 3.13+
This provides minimal functionality needed by Cython's Tempita
"""

import urllib.parse

def parse_header(line):
    """Parse a Content-type like header."""
    parts = line.split(';')
    key = parts[0].strip()
    pdict = {}
    for p in parts[1:]:
        if '=' in p:
            name, value = p.split('=', 1)
            pdict[name.strip()] = value.strip().strip('"')
    return key, pdict

def parse_multipart(fp, pdict, encoding="utf-8", errors="replace"):
    """Parse multipart form data."""
    # This is a minimal implementation
    # In practice, you might want to use a more robust solution
    boundary = pdict.get('boundary', '').encode('ascii')
    if not boundary:
        return {}
    
    # This is a very basic implementation
    # For production use, consider using a proper multipart parser
    return {}

# Add other functions as needed
def parse_qs(qs, keep_blank_values=0, strict_parsing=0, encoding='utf-8', errors='replace'):
    """Parse a query string."""
    return urllib.parse.parse_qs(qs, keep_blank_values, strict_parsing, encoding, errors)

def parse_qsl(qs, keep_blank_values=0, strict_parsing=0, encoding='utf-8', errors='replace'):
    """Parse a query string into a list of tuples."""
    return urllib.parse.parse_qsl(qs, keep_blank_values, strict_parsing, encoding, errors)
'''
    
    # Write the compatibility module
    cgi_compat_file = tempita_path / "_cgi_compat.py"
    with open(cgi_compat_file, 'w') as f:
        f.write(cgi_compat_content)
    
    # Patch the _tempita.py file
    tempita_file = tempita_path / "_tempita.py"
    if tempita_file.exists():
        with open(tempita_file, 'r') as f:
            content = f.read()
        
        # Replace the import
        if 'import cgi' in content:
            content = content.replace('import cgi', 'from . import _cgi_compat as cgi')
            
            with open(tempita_file, 'w') as f:
                f.write(content)
            print("Successfully patched _tempita.py")
            return True
    
    return False

if __name__ == "__main__":
    if create_cgi_compatibility():
        print("Cython patch applied successfully!")
    else:
        print("Failed to apply Cython patch")
        sys.exit(1)