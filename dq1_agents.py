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
import re
from cerebras.cloud.sdk import Cerebras
from openai import OpenAI
import base64
from helpers import TokenCounter
import random


from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly, kCGNullWindowID

# NEW: Load the environment variables from your .env.local file
load_dotenv(dotenv_path='.env')
random_seed =  random.randint(0, 1000000)

openrouter_key = os.getenv("OPENROUTER_API_KEY")
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=openrouter_key)


# -- File Paths (macOS) --
base_folder = os.path.expanduser('~/Library/Application Support/Mesen2/LuaScriptData/dq1/')
STATS_FILE_PATH = os.path.join(base_folder, "dq1_stats.txt")
ACTION_FILE_PATH = os.path.join(base_folder, "action.txt")


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
    "TAKE": ["a", "menu-down", "menu-down", "menu-down", "menu-right", "a"],
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

def get_window_bbox(app_name="Mesen"):
    window_list = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
    for window in window_list:
        name = window.get('kCGWindowName', '')
        owner = window.get('kCGWindowOwnerName', '')
        bounds = window.get('kCGWindowBounds', {})
        if app_name.lower() in owner.lower():
            x, y = int(bounds['X']), int(bounds['Y'])
            w, h = int(bounds['Width']), int(bounds['Height'])
            return {"top": y, "left": x, "width": w, "height": h}
    return None

def capture_screen():
    region = get_window_bbox("Mesen")
    if not region:
        print("Mesen window not found!")
        return None

    with mss.mss() as sct:
        sct_img = sct.grab(region)
        frame = np.array(sct_img)
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

def check_for_dialogue(token_counter):
    """Checks if the image contains dialogue text and extracts it."""
    prompt = """
    Look at this screenshot from Dragon Quest 1 (NES). 
    1. Is there any dialogue/text box visible in the image? It should be a message box with a down arrow, ideally more than one line.
    2. If yes, what does the text say? Extract and return the text content.
    3. If no dialogue, return 'no'.
    
    Format strictly in <dialogue>...</dialogue>.
    """

    # Encode the screenshot as base64
    with open("game_screen.png", "rb") as f:
        b64_image = base64.b64encode(f.read()).decode("utf-8")

    chat_completion = client.chat.completions.create(
        model="google/gemini-2.5-flash-lite",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "input_image", "image_url": f"data:image/png;base64,{b64_image}"},
            ],
        }],
    )

    # Track token usage
    if hasattr(chat_completion, 'usage') and chat_completion.usage:
        input_tokens = chat_completion.usage.prompt_tokens
        output_tokens = chat_completion.usage.completion_tokens
        token_counter.add_usage(input_tokens, output_tokens)
        print(f"Dialogue check tokens - Input: {input_tokens}, Output: {output_tokens}")

    response = chat_completion.choices[0].message.content

    # Extract text between dialogue tags if present
    dialogue_match = re.search(r'<dialogue>(.*?)</dialogue>', response, re.DOTALL)
    if dialogue_match and dialogue_match.group(1).strip():
        text = dialogue_match.group(1).strip()
        if text.lower() == "no":
            return None
        else:
            return text
    return None










def construct_prompt(game_state, history, dialogue_history):
    """MODIFIED: Builds a prompt asking for a high-level macro."""
    if not game_state:
        return None
    
    # Create a list of available macros to show the LLM
    available_macros = list(ACTION_MACROS.keys())

    prompt = f"""
You are an expert player of the NES game Dragon Quest 1. Your goal is to defeat the Dragonlord.
You are playing as an adventurer. You will be provided a screenshot of the game. Analyze it carefully.
You are the best player in the world at this game, so please navigate it accordingly. You need to move through doors, and may need keys that youll find in chests.
Look at the history to avoid getting stuck in loops.
Look at the map, try to explore all the grid cells if youre stuck.
If youre facing the wall, try to move away and explore an exit/nearest item you can interact with.
You should ideally keep moving and take fresh new actions/conversations in 10 states or more, if not youre doing somethning wrong.
Also if youre in a dialogue, you can only use the GO_DOWN_IN_DIALOGUE macro.


Recent Actions:
{history}

Recent Dialogue:
{dialogue_history}

HINT: Check on your last conversations/dialogue to get unstuck

Based on the screenshot and status, choose the best high-level action to perform right now.
You shall be provided an macro dictionary only choose macros from that dictionary.

Available Actions:

# --- Simple Actions ---
    "go_down_in_dialogue": go down in the dialogue
    "move_up":    moves up one tile in the game
    "move_down":  moves down one tile in the game
    "move_left":  moves left one tile in the game
    "move_right": moves right one tile in the game
    "exit_menu":  moves out of the menu

    # --- Field Menu Macros  ---
    # NOTE: These all assume you start by pressing 'A' to open the command window.
    "take": take something from the object youre interacting with
    "talk":         talk to the NPC
    "check_status": check your status for the battle
    "go_stairs":    go down the stairs
    "open_spell_menu": open the spell menu
    "open_item_menu":  open the item menu
    "open_door":    open the door

    # --- Misc Menu Macros -- 
    "search": try to find things when you dont have any other option (very obscure or rare to use, only use if you have no other options)


    # --- Battle Menu Macros ---
    # Assumes the battle menu is already open.
    "battle_fight": fight the enemy
    "battle_run":   run from the battle
    "battle_spell": use a spell
    "battle_item":  use an item

PLease remember also if youre in a dialogue, you can only use the go_down_in_dialogue macro, a dialogue is when you see a message box and a down arrow.
When you are in the command menu, to go back press exit_menu
When you are done with the dialogue you need to explore the area and also take actions to progress. Around you need to:
- Move around
- Explore the area
- Talk to other NPCs
- Take actions like opening a door, taking the stairs, and taking treasure from the chests.
- Remember to interact with objects as well, use TAKE or OPEN DOOR
Dont get stuck taking the same action if you are not in the dialogue.
Respond with your best action. wrap it in tags of <action> and </action>
Example: <action>talk</action>
"""

    prompt = f"""
You are an expert player of the NES game Dragon Quest 1. Your goal is to defeat the Dragonlord.
You are playing cautiously. You will be provided a screenshot of the game. Analyze it carefully.
Understand all the elements on the screen. Understand the game mechanics. Understand the core game loops. 
Talk to NPCs in the game to get information. 
Look at the history to avoid getting stuck in loops.

Some basic rules for gameplay

Exploration:
- Move around the world to find chests, enemies, items, etc.
- When in front of a chest, press TAKE_TREASURE to open it.
- When in front of a door, press OPEN_DOOR to open it.
- When in front of an NPC, press TALK to talk to them.
- To open doors in the game, you need to have magic keys. You can get magic keys by opening chests (in towns & dungeons), killing enemies or finding them in the world.
- To get more information about quests, world or dungeons in the game, you can talk to NPCs.
- To recover health, you can go to towns and find an inn. Talk to the innkeeper and rent a room for 10 gold.
- To buy spells, you can go to towns and find a magic shop. Talk to the magic shopkeeper and buy the spells.
- To recover MP, you can go to towns and find a magic shop. Talk to the magic shopkeeper and buy a potion.
- To buy weapons, armor, items, you can go to towns and find a shop. Talk to the shopkeeper and buy the items.

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

Available Actions:
{available_macros}

Respond ONLY with a JSON object containing your choice.
Example: {{"action": "TALK"}}
"""
   
    return prompt

def query_llm(prompt, img, token_counter):
    with open("game_screen.png", "rb") as image_file:  
        b64_image = base64.b64encode(image_file.read()).decode("utf-8")  
  
    response =  None
    
    try:
        # with open(f"agent_log_{random_seed}.jsonl", "a", encoding="utf-8") as f:
        #     f.write(json.dumps({"step": "query_llm.request", "prompt": prompt}) + "\n")

        response = client.chat.completions.create(
            model="google/gemini-2.5-flash-lite",
            messages=[
                {"role": "user", "content":[
                {"type": "text", "text": prompt},
                {"type": "input_image", "image_url": f"data:image/png;base64,{b64_image}"},
                ]}],
        )
        print('MODEL RESPONSE', response)
        
        # Track token usage
        if hasattr(response, 'usage') and response.usage:
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            token_counter.add_usage(input_tokens, output_tokens)

            with open(f"logs/token_log_{random_seed}.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "step": "query_llm.tokens",
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens
                }) + "\n")

            print(f"Tokens used - Input: {input_tokens}, Output: {output_tokens}")
        
        action = response.choices[0].message.content.strip().lower()
        with open(f"logs/agent_log_{random_seed}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "step": "query_llm.response",
                "response": action
            }) + "\n")

    except Exception as e:
        print(e)
        return ''
    return action


def query_cerebras(prompt, image, token_counter):
    client = Cerebras(
    api_key=os.environ.get("CEREBRAS_API_KEY"),
    )
    try:
        chat_completion = client.chat.completions.create(
        messages=[
        {"role": "system", "content": "You are an expert player of the NES game Dragon Quest 1. Your goal is to defeat the Dragonlord. You are playing as an adventurer. You will be provided a screenshot of the game. Analyze it carefully. You are the best player in the world at this game, so please navigate it accordingly."},
        {"role": "user", "content": prompt, "images": ["game_screen.png"]}
        ],
        model="llama-4-scout-17b-16e-instruct",
        )

        # Track token usage
        if hasattr(chat_completion, 'usage') and chat_completion.usage:
            input_tokens = chat_completion.usage.prompt_tokens
            output_tokens = chat_completion.usage.completion_tokens
            token_counter.add_usage(input_tokens, output_tokens)
            print(f"Tokens used - Input: {input_tokens}, Output: {output_tokens}")

        response = chat_completion.choices[0].message.content
        response = response.strip().lower()
        print(response)
        return response
    except:
        return ''
    
    return response


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
        # print(llm_response_str)

        # Extract action from <ACTION> tags
        # import re
        # action_match = re.search(r'<action>(.*?)</action>', llm_response_str, re.IGNORECASE)
        # if not action_match:
        #     print("No <action> tags found in response")
        #     return None
            
        # action_key = action_match.group(1).upper()

        # Step 1: Parse the JSON response from the LLM
        
        action_match = re.search(r'```json(.*?)```', llm_response_str, re.DOTALL)
        if not action_match:
            print("No JSON found in response")
            return None

        json_str = action_match.group(1).strip()

        action_data = json.loads(json_str)
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

    token_counter = TokenCounter()
    action_history = deque(maxlen=100)
    dialogue_history = deque(maxlen=100)
    print("Starting LLM Agent for Dragon Quest 1 (Macro Execution Mode)...")
    time.sleep(3)
    img_count = 0
    while True:
        # 1. Read State and See Screen
        game_state = read_game_state()
        if not game_state:
            time.sleep(1)
            continue
        image = capture_screen()
        cv2.imwrite("game_screen.png", image) # for game state reading
        cv2.imwrite(f"game_state_folder/game_screen_{img_count}.png", image)  # for logging purposes
        img_count += 1


        dialogue = check_for_dialogue(token_counter)
        if dialogue:
            print(f"DIALOGUE: {dialogue}")
            dialogue_history.append(dialogue)

        # 2. Construct Prompt for a High-Level Action
        prompt = construct_prompt(game_state, list(action_history), dialogue_history)
        if not prompt:
            time.sleep(1)
            continue

        llm_json_response = query_llm(prompt, image, token_counter)

        executed_action = execute_macro(llm_json_response)
        
        # 5. Update History
        if executed_action:
            action_history.append(f"Action: {executed_action}, PX: {game_state.get('px')}, PY: {game_state.get('py')}")
            print(f"MACRO EXECUTED: {executed_action}\n")
        else:
            print("Macro execution failed. Doing nothing this turn.")
            action_history.append("Macro execution failed.")

        # 6. Wait before the next cycle
        time.sleep(5)