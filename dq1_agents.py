import time
import mss
import cv2
import pytesseract
import numpy as np
import openai
import os
from collections import deque
from dotenv import load_dotenv # NEW: Import the library

# NEW: Load the environment variables from your .env.local file
load_dotenv(dotenv_path='.env.local')


# --- 1. CONFIGURATION ---

# -- File Paths (macOS) --
base_folder = os.path.expanduser('~/Library/Application Support/Mesen2/LuaScriptData/dq1_stats')
STATS_FILE_PATH = os.path.join(base_folder, "dq1_stats.txt")
ACTION_FILE_PATH = os.path.join(base_folder, "action.txt")

# -- Screen Capture --
MONITOR_REGION = {"top": 40, "left": 0, "width": 512, "height": 480}

# -- OpenRouter API Configuration --
# MODIFIED: Load the key from the environment instead of hardcoding it
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL_NAME = "google/gemini-2.0-flash-exp:free"
YOUR_SITE_URL = "http://localhost:8080"

# NEW: Add a check to ensure the API key was loaded successfully
if not OPENROUTER_API_KEY:
    raise ValueError("OpenRouter API key not found. Please check your .env.local file.")

# Initialize the API client pointing to OpenRouter's endpoint
client = openai.OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key=OPENROUTER_API_KEY,
)


# --- 2. HELPER FUNCTIONS (No changes needed below this line) ---

def read_game_state():
    """Reads the key-value pairs from the stats file written by Lua."""
    state = {}
    try:
        with open(STATS_FILE_PATH, 'r') as f:
            for line in f:
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    state[key] = int(value)
    except FileNotFoundError:
        print(f"Waiting for stats file at: {STATS_FILE_PATH}")
        return None
    except Exception as e:
        print(f"Error reading stats file: {e}")
        return None
    return state

def capture_and_ocr_screen():
    """Captures the game screen and extracts text using OCR."""
    with mss.mss() as sct:
        sct_img = sct.grab(MONITOR_REGION)
        frame = np.array(sct_img)
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
        _, thresh_frame = cv2.threshold(gray_frame, 150, 255, cv2.THRESH_BINARY_INV)
        try:
            text = pytesseract.image_to_string(thresh_frame)
            return " ".join(text.split()) # Clean up whitespace
        except pytesseract.TesseractNotFoundError:
            print("Tesseract not found. Please install it and add it to your PATH.")
            return ""

def construct_prompt(game_state, screen_text, history):
    """Builds a detailed prompt for the LLM."""
    if not game_state:
        return None
    prompt = f"""
You are an expert player of the NES game Dragon Quest 1. Your goal is to defeat the Dragonlord.
You are playing cautiously.

Current Status:
- HP: {game_state.get('hp', 'N/A')}
- MP: {game_state.get('mp', 'N/A')}
- Gold: {game_state.get('gold', 'N/A')}
- Level: {game_state.get('level', 'N/A')}
- Position: ({game_state.get('px', 'N/A')}, {game_state.get('py', 'N/A')})
- Map ID: {game_state.get('map_id', 'N/A')} (0 is Overworld)
- Enemy HP: {game_state.get('enemy_hp', 'N/A')} (0 means no battle)

Text on Screen:
"{screen_text}"

Recent History (last 3 actions):
{history}

Your Task:
Based on everything you see, what is the single best button to press right now?
The available buttons are: up, down, left, right, a (confirm/talk), b (cancel/menu).

Respond ONLY with a single word for the button to press. For example: A
"""
    return prompt

def query_llm(prompt):
    """Sends the prompt to the OpenRouter API and gets a response."""
    print("--- PROMPT TO LLM ---")
    print(prompt)
    print("---------------------")
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            extra_headers={
                "HTTP-Referer": YOUR_SITE_URL,
            }
        )
        action = response.choices[0].message.content.strip()
        return action
    except Exception as e:
        print(f"Error querying OpenRouter API: {e}")
        return "B" # Default to a safe action on error

def take_action(action):
    """Writes the chosen action to the action file for Lua to read."""
    try:
        with open(ACTION_FILE_PATH, 'w') as f:
            f.write(action)
    except Exception as e:
        print(f"Error writing action file: {e}")

# --- 3. THE MAIN LOOP ---
if __name__ == "__main__":
    action_history = deque(maxlen=3)
    print("Starting LLM Agent for Dragon Quest 1 (using OpenRouter)...")
    print("Ensure Mesen 2 is running with the Lua script.")
    time.sleep(3)
    while True:
        game_state = read_game_state()
        if not game_state:
            time.sleep(1)
            continue
        screen_text = capture_and_ocr_screen()
        prompt = construct_prompt(game_state, screen_text, list(action_history))
        if not prompt:
            time.sleep(1)
            continue
        chosen_action = query_llm(prompt)
        valid_actions = ["UP", "DOWN", "LEFT", "RIGHT", "A", "B"]
        if chosen_action in valid_actions:
            take_action(chosen_action)
            action_history.append(f"Took action '{chosen_action}' with HP={game_state.get('hp')}")
            print(f"ACTION SENT: {chosen_action}\n")
        else:
            print(f"LLM provided an invalid action: '{chosen_action}'. Defaulting to 'B'.")
            take_action("B") # Send a safe default action
            action_history.append("LLM provided invalid action.")
        time.sleep(5) # Delay to prevent spamming the API and to give the game time to react