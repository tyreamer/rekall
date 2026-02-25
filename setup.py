from setuptools import setup, find_packages

setup(
    name="rekall",
    version="0.1.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=[
        "pyyaml",
    ],
    entry_points={
        "console_scripts": [
            "rekall=rekall.cli:main",
        ]
    }
)
