"""
Configuration for Canada Import Gap Analysis
"""

API_KEY = "cfd3d579a70a404b82c1e53936860f39"
BASE_URL = "https://comtradeapi.un.org/data/v1/get/C/A/HS"

# Country codes
CANADA_CODE = "124"
CHINA_CODE = "156"
WORLD_CODE = "0"

# Flow
IMPORT_FLOW = "M"

# Years with reliable data
DEFAULT_YEARS = [2021, 2022, 2023, 2024]

# Paths
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
