"""
Script de execução para lançamento de GNRE no ERP ADMSIS.
Uso:
    python run_gnre.py "GNRE NF 54949.pdf"
    ou apenas:
    python run_gnre.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from run_gnre import main

if __name__ == "__main__":
    main()
