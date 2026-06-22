#!/usr/bin/env python
"""Shim to allow GitHub to detect the package; the build is done with poetry.

Taken from https://github.com/Textualize/rich
"""

import setuptools

if __name__ == "__main__":
    setuptools.setup(name="nexia")
