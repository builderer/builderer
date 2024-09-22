#!/usr/bin/env python

from setuptools import setup

setup(
    name="builderer",
    packages=[
        "builderer",
        "builderer.details",
        "builderer.details.targets",
        "builderer.details.tools",
        "builderer.generators.make",
        "builderer.generators.msbuild",
    ],
    python_requires=">=3.9",
    entry_points={"console_scripts": ["builderer = builderer.__main__:main"]},
)
