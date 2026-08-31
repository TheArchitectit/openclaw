#!/usr/bin/env python3
"""Stub adapter used by test.py: dumps env and args as parseable lines.

Prints one STUB-ENV <name>=<value> line per environment variable and one
STUB-ARGS <argv> line, so tests can assert exactly what the launcher handed
to the adapter process without any real adapter or network access.
"""

import os
import sys

for name, value in sorted(os.environ.items()):
    print(f"STUB-ENV {name}={value}")
print(f"STUB-ARGS {' '.join(sys.argv[1:])}")
