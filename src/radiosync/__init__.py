"""radiosync: master channel catalog that generates validated CHIRP images.

Changelog:
- 0.1.11 (2026-11-02): English documentation; Spanish and English stopwords in name fitting.
- 0.1.10 (2026-11-02): neutral test examples; merged .gitignore for publication.
- 0.1.9 (2026-11-01): documentation, generic examples, stricter ignore rules.
- 0.1.8 (2026-11-01): optional --sort by RX frequency.
- 0.1.7 (2026-11-01): set-prefixed output comments.
- 0.1.6 (2026-11-01): compact model/date/hash build filenames.
- 0.1.5 (2026-11-01): internal user storage; flat outputs in cwd or --output.
- 0.1.4 (2026-11-01): names shortened to each model's length (radiosync.names).
- 0.1.3 (2026-11-01): CSV/image imports drop channel power.
- 0.1.2 (2026-11-01): --power low|mid|high; per-model power levels and default.
- 0.1.1 (2026-11-01): installable with pipx; project lookup outside the project directory.
- 0.1.0 (2026-11-01): initial version.
"""

__version__ = "0.1.11"
CURRENT_VERSION = __version__
