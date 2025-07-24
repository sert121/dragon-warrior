import time
import mss
import cv2
import pytesseract
import numpy as np
import ollama
import os
import json
from collections import deque
from dotenv import load_dotenv # NEW: Import the library
import os
from cerebras.cloud.sdk import Cerebras


# NEW: Load the environment variables from your .env.local file
load_dotenv(dotenv_path='.env.local')


# -- File Paths (macOS) --
base_folder = os.path.expanduser('~/Library/Application Support/Mesen2/LuaScriptData/dq1/')
STATS_FILE_PATH = os.path.join(base_folder, "dq1_stats.txt")
ACTION_FILE_PATH = os.path.join(base_folder, "action.txt")

# -- Screen Capture --
MONITOR_REGION = {"top": 40, "left": 0, "width": 512, "height": 480} # Adjust to your Mesen window

# -- Ollama Configuration --
# MODIFIED: Ensure your model name is correct for your local Ollama instance
OLLAMA_MODEL = 'hf.co/unsloth/Qwen2.5-Omni-7B-GGUF:Q4_K_M'

# --- NEW: MACRO DICTIONARY (THE "INPUT TREE") ---
# This dictionary translates a high-level action into a sequence of low-level button presses
# tailored for the NES version of Dragon Quest 1.
ACTION_MACROS = {
    # --- Simple Actions ---
    "MOVE_UP":    ["up"],
    "MOVE_DOWN":  ["down"],
    "MOVE_LEFT":  ["left"],
    "MOVE_RIGHT": ["right"],
    "EXIT_MENU":  ["b"],

    # --- Field Menu Macros (for outside of battle) ---
    # NOTE: These all assume you start by pressing 'A' to open the command window.
    "TALK":         ["a", "a"],
    "CHECK_STATUS": ["a", "menu-down", "a"],
    "GO_STAIRS":    ["a", "menu-down", "menu-down", "a"],
    "SEARCH":       ["a", "menu-down", "menu-down", "menu-down", "a"],
    "OPEN_SPELL_MENU": ["a", "menu-right", "a"],
    "OPEN_ITEM_MENU":  ["a", "menu-down", "menu-right", "a"],
    "OPEN_DOOR":    ["a", "menu-down", "menu-down", "menu-right", "a"],
    "TAKE_TREASURE": ["a", "menu-down", "menu-down", "menu-down", "menu-right", "a"],
    "GO_DOWN_IN_DIALOGUE": ["a"],

    # --- Battle Menu Macros ---
    # Assumes the battle menu is already open.
    "BATTLE_FIGHT": ["a"],
    "BATTLE_RUN":   ["menu-right", "menu-right", "a"],
    "BATTLE_SPELL": ["menu-right", "a"],
    "BATTLE_ITEM":  ["menu-right", "menu-right", "menu-right", "a"]
}

# --- 2. HELPER FUNCTIONS ---

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

def capture_screen():
    """Captures the game screen and returns the color image."""
    with mss.mss() as sct:
        sct_img = sct.grab(MONITOR_REGION)
        frame = np.array(sct_img)
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)


def construct_prompt(game_state, history):
    """MODIFIED: Builds a prompt asking for a high-level macro."""
    if not game_state:
        return None
    
    # Create a list of available macros to show the LLM
    available_macros = list(ACTION_MACROS.keys())

    prompt = f"""
You are an expert player of the NES game Dragon Quest 1. Your goal is to defeat the Dragonlord.
You are playing cautiously. You will be provided a screenshot of the game. Analyze it carefully.
You are the best player in the world at this game, so please navigate it accordingly.

Look at the history to avoid getting stuck in loops.
Also if youre in a dialogue, you can only use the GO_DOWN_IN_DIALOGUE macro.

Current Status:
- HP: {game_state.get('hp', 'N/A')}
- MP: {game_state.get('mp', 'N/A')}
- Gold: {game_state.get('gold', 'N/A')}
- Level: {game_state.get('level', 'N/A')}
- Position: ({game_state.get('px', 'N/A')}, {game_state.get('py', 'N/A')})
- Map ID: {game_state.get('map_id', 'N/A')} (0 is Overworld)
- Enemy HP: {game_state.get('enemy_hp', 'N/A')} (0 means no battle)

Recent Actions:
{history}

Based on the screenshot and status, choose the best high-level action to perform right now.
You shall be provided an macro dictionary only choose macros from that dictionary.

Available Actions:

    # --- Simple Actions ---
    "MOVE_UP":    moves up one tile in the game
    "MOVE_DOWN":  moves down one tile in the game
    "MOVE_LEFT":  moves left one tile in the game
    "MOVE_RIGHT": moves right one tile in the game
    "EXIT_MENU":  moves out of the menu or 

    # --- Field Menu Macros (for outside of battle) ---
    # NOTE: These all assume you start by pressing 'A' to open the command window.
    "TALK":         talk to the NPC
    "CHECK_STATUS": check your status for the battle
    "GO_STAIRS":    go down the stairs
    "SEARCH":       search the area
    "OPEN_SPELL_MENU": open the spell menu
    "OPEN_ITEM_MENU":  open the item menu
    "OPEN_DOOR":    open the door
    "TAKE_TREASURE": take the treasure
    "GO_DOWN_IN_DIALOGUE": go down in the dialogue

    # --- Battle Menu Macros ---
    # Assumes the battle menu is already open.
    "BATTLE_FIGHT": fight the enemy
    "BATTLE_RUN":   run from the battle
    "BATTLE_SPELL": use a spell
    "BATTLE_ITEM":  use an item

Respond ONLY with a JSON object containing your choice.
Example: {{"action": "TALK"}}
"""
    return prompt

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


def write_action_to_file(action):
    """NEW: A simple helper to write a single button press to the action file."""
    try:
        with open(ACTION_FILE_PATH, 'w') as f:
            f.write(action)
    except Exception as e:
        print(f"Error writing action file: {e}")

def execute_macro(llm_response_str):
    """NEW: The Macro Executor function."""
    try:
        # Step 1: Parse the JSON response from the LLM
        action_data = json.loads(llm_response_str)
        action_key = action_data.get('action').upper()

        if action_key and action_key in ACTION_MACROS:
            # Step 2: Look up the button sequence in our dictionary
            button_sequence = ACTION_MACROS[action_key]
            print(f"Executing Macro '{action_key}': {button_sequence}")
            
            # Step 3: Execute the sequence of button presses
            for button in button_sequence:
                write_action_to_file(button)
                # Wait a very short time between presses for the game to register them
                time.sleep(0.2)
            return action_key # Return the successful action key for history
        else:
            print(f"Error: Macro '{action_key}' not found or invalid.")
            return None
            
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error parsing LLM JSON response: '{llm_response_str}'. Error: {e}")
        return None

# --- 3. THE MAIN LOOP ---
if __name__ == "__main__":

    action_history = deque(maxlen=10)
    print("Starting LLM Agent for Dragon Quest 1 (Macro Execution Mode)...")
    print(f"Using local model: {OLLAMA_MODEL}")
    print("Ensure Mesen 2 is running with the Lua script and Ollama is running.")
    time.sleep(3)

    while True:
        # 1. Read State and See Screen
        game_state = read_game_state()
        if not game_state:
            time.sleep(1)
            continue
        image = capture_screen()

        # 2. Construct Prompt for a High-Level Action
        prompt = construct_prompt(game_state, list(action_history))
        if not prompt:
            time.sleep(1)
            continue

        # 3. Ask the LLM for a Decision (which returns a JSON string)
        llm_json_response = query_cerebras(prompt, image)

        # 4. Execute the Chosen Macro
        executed_action = execute_macro(llm_json_response)
        
        # 5. Update History
        if executed_action:
            action_history.append(f"Action: {executed_action}, HP: {game_state.get('hp')}")
            print(f"MACRO EXECUTED: {executed_action}\n")
        else:
            print("Macro execution failed. Doing nothing this turn.")
            action_history.append("Macro execution failed.")

        # 6. Wait before the next cycle
        time.sleep(5)