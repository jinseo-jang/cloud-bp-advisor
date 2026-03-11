import os
from dotenv import load_dotenv

load_dotenv()
GEMINI_FLASH_MODEL = os.environ.get("GEMINI_FLASH_MODEL", "gemini-3-flash-preview")
GEMINI_PRO_MODEL = os.environ.get("GEMINI_PRO_MODEL", "gemini-3-pro-preview")
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "duper-project-1")
GCP_REGION = os.environ.get("GCP_REGION", "asia-northeast3")
