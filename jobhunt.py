#!/usr/bin/env python3
"""Daily remote developer and internship job scraper.

  python jobhunt.py check      # test each source without database writes
  python jobhunt.py run        # fetch, score, store, write today's digest
  python jobhunt.py top [N]    # show the best open jobs
"""

from jobhunt_app.cli import main


if __name__ == "__main__":
    main()
