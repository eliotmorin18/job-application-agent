"""
Ancienne commande, gardée pour compatibilité :
    python main.py "<URL>"   ==   python -m cv.cli "<URL>"
Le pipeline est dans cv/cli.py.
"""

import sys

from cv.cli import main


if __name__ == "__main__":

    if len(sys.argv) != 2:
        print('Usage: python -m cv.cli "<URL>"   (ou : python main.py "<URL>")')
        sys.exit(1)

    main(sys.argv[1])
