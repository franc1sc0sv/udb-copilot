from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("udb-copilot")
except PackageNotFoundError:  # running from a source tree
    __version__ = "0.0.0"
