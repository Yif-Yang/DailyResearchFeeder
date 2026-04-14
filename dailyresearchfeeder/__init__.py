from .config import load_settings

__version__ = "0.0.1"


def run_digest(*args, **kwargs):
	from .pipeline import run_digest as _run_digest

	return _run_digest(*args, **kwargs)


__all__ = ["__version__", "load_settings", "run_digest"]