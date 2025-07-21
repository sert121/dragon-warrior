import time
import mss
import cv2
import pytesseract
import numpy as np
import openai
import os
from collections import deque
from dotenv import load_dotenv # NEW: Import the library
import ollama  
from ollama import Image  
import os
from cerebras.cloud.sdk import Cerebras


# NEW: Load the environment variables from your .env.local file
load_dotenv(dotenv_path='.env.local')


# -- File Paths (macOS) --
base_folder = os.path.expanduser('~/Library/Application Support/Mesen2/LuaScriptData/dq1/')
STATS_FILE_PATH = os.path.join(base_folder, "dq1_stats.txt")
ACTION_FILE_PATH = os.path.join(base_folder, "action.txt")

# -- Screen Capture --
MONITOR_REGION = {"top": 40, "left": 0, "width": 512, "height": 480}

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
    """Captures the game screen and returns both the image and extracted text."""
    with mss.mss() as sct:
        sct_img = sct.grab(MONITOR_REGION)
        frame = np.array(sct_img)
        # get color image
        color_frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
        _, thresh_frame = cv2.threshold(gray_frame, 150, 255, cv2.THRESH_BINARY_INV)
        try:
            text = pytesseract.image_to_string(thresh_frame)
            text = " ".join(text.split())  # Clean up whitespace
        except pytesseract.TesseractNotFoundError:
            print("Tesseract not found. Please install it and add it to your PATH.")
            text = ""
        return color_frame, text

def construct_prompt(game_state, history):
    """Builds a detailed prompt for the LLM."""
    if not game_state:
        return None
    prompt = f"""
You are an expert player of the NES game Dragon Quest 1. Your goal is to defeat the Dragonlord.
You are playing cautiously. You will be provied a screenshot of the game screen.Dont get stuyck, look at the history to be unstuck.

Current Status:
- HP: {game_state.get('hp', 'N/A')}
- MP: {game_state.get('mp', 'N/A')}
- Gold: {game_state.get('gold', 'N/A')}
- Level: {game_state.get('level', 'N/A')}
- Position: ({game_state.get('px', 'N/A')}, {game_state.get('py', 'N/A')})
- Map ID: {game_state.get('map_id', 'N/A')} (0 is Overworld)
- Enemy HP: {game_state.get('enemy_hp', 'N/A')} (0 means no battle)

Recent History (last 3 actions):
{history}

Your Task:
Based on everything you see, what is the single best button to press right now?
The available buttons are: [up, down, left, right, a, b]
up: move up
down: move down
left: move left
right: move right
a: take action
b: back

if you are in a menu or a black box you should use:
[menu-up, menu-down, menu-left, menu-right]
tip: if you are in a interactive conversation, you should use a, to take action.
tip: if you are in a menu, you cant move left or right, you have to use menu-left to scroll all the way down before you can do any movement.

Respond ONLY with a single word for the button to press. For example: a
"""
    return prompt

def query_ollama(prompt, image):
    """Sends the prompt to ollama model gets a response via """
    # save the image to a file
    cv2.imwrite("game_screen.png", image)
    print("--- PROMPT TO LLM ---")
    print(prompt)
    print("---------------------")
    # Send a message with text and image  
    response = ollama.chat(  
        model='',  # Assuming this is your model name  
        messages=[  
            {  
                'role': 'user',  
                'content': prompt,  
                'images': ['game_screen.png']  # Can be file path, bytes, or base64  
            }  
        ]  
    )  
    
    print(response.message.content)
    return response.message.content.strip().lower()


def query_cerebras(prompt, image):
    client = Cerebras(
    api_key=os.environ.get("CEREBRAS_API_KEY"),
    )

    chat_completion = client.chat.completions.create(
    messages=[
    {"role": "user", "content": prompt, "images": ["game_screen.png"]}
    ],
    model="llama-4-scout-17b-16e-instruct",
    )

    response = chat_completion.choices[0].message.content
    return response.strip().lower()
    

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
    print("Ensure Mesen 2 is running with the Lua script.")
    time.sleep(3)
    while True:
        game_state = read_game_state()
        if not game_state:
            time.sleep(1)
            continue
        image, screen_text = capture_and_ocr_screen()
        prompt = construct_prompt(game_state, list(action_history))
        if not prompt:
            time.sleep(1)
            continue
        chosen_action = query_cerebras(prompt,image)

        valid_actions = ["up", "down", "left", "right", "a", "b", "menu-left", "menu-right", "menu-up", "menu-down"]
        if chosen_action.strip().lower() in valid_actions:
            take_action(chosen_action)
            game_state['action'] = chosen_action
            action_history.append(game_state)
            print(f"ACTION SENT: {chosen_action}\n")
        else:
            print(f"LLM provided an invalid action: '{chosen_action}'. Defaulting to 'B'.")
            take_action("B") # Send a safe default action
            action_history.append("LLM provided invalid action.")
        time.sleep(5) # Delay to prevent spamming the API and to give the game time to react

