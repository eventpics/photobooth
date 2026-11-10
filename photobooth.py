#!/usr/bin/env python3
"""EventPics Photobooth - the native interface.

    python3 photobooth.py                        # full screen, as it runs on the box
    python3 photobooth.py --window --scale 0.5   # for working on a desktop

Copyright (C) 2026 EventPics

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. It is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU General Public License for more details. You
should have received a copy of the licence along with this program; it is in
the file LICENSE, and also at <https://www.gnu.org/licenses/>.
"""

import sys

from booth.ui.app import main

if __name__ == "__main__":
    sys.exit(main())
