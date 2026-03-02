"""Package setup for spec-engine."""

from setuptools import setup, find_packages

setup(
    name="spec-engine",
    version="1.0.0",
    description="Automated OpenAPI 3.1 spec generator for enterprise API repositories",
    packages=find_packages(),
    install_requires=[
        "click>=8.1.0",
        "ruamel.yaml>=0.18.0",
        "httpx>=0.27.0",
        "pydantic>=2.0.0",
        "javalang>=0.13.0",
        "PyYAML>=6.0",
    ],
    extras_require={
        "dev": [
            "pytest>=8.0.0",
            "pytest-cov>=5.0.0",
            "responses>=0.25.0",
            "respx>=0.20.0",
        ]
    },
    entry_points={
        "console_scripts": ["spec-engine=spec_engine.cli:cli"]
    },
    python_requires=">=3.11",
    package_data={
        "spec_engine": [
            "scanner/express_ast.js",
            "inferrer/ts_schema.js",
        ]
    },
)
