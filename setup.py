#!/usr/bin/env python3
from setuptools import setup, find_packages

setup(
    name="cli-agent-logger",
    version="1.0.0",
    description="Generic CLI agent logger for capturing API requests across any source",
    author="Claude",
    packages=find_packages(),
    install_requires=[],
    entry_points={
        'console_scripts': [
            'claude-with-logging=src.claude_session:main',
        ],
    },
    python_requires='>=3.6',
)