Dragon Quest 1 is a classic JRPG designed for NES. 
# Gameplay
- Turn-based combat; Defeat Monsters, 
- Use attack with weapons, magic with spells to cause damage
- Use armor to add protection
- use heal to heal yourself in combat in exchange for MP
- when health is low, go to nearby town, find an inn, talk to the innkeeper and rent a room for 6 gold
- make sure enough gold is reserved for the inn in the wallet
- to gain gold, kill enemies, finish quests, unlock chests, go to dungeons
- basic rule - to open any door, you need magic keys, so at any given point of time you need to be keymaxxing

- in a space, if chests are present in an accessible room, priority is always to take all of it's contents
- when in front of chest - TAKE_TREASURE
- when in front of a door - OPEN_DOOR
- talk to armorer in towns and assess the quality of their items (Weapons, armor)
- if they have a better weapon, check if enough gold is available to buy the weapon. If you want to or not want to buy the item, select Yes or No. If yes, check dialogue box and confirm. If No, you can always go back into conversation menu and leave the conversation

ACTION_MACROS = {
    # --- Simple Actions ---
    "MOVE_UP":    ["UP"],
    "MOVE_DOWN":  ["DOWN"],
    "MOVE_LEFT":  ["LEFT"],
    "MOVE_RIGHT": ["RIGHT"],
    "EXIT_MENU":  ["B"], # Cancels out of a menu

    # --- Field Menu Macros (for outside of battle) ---
    # NOTE: These all assume you start by pressing 'A' to open the command window.
    "TALK":         ["A", "A"],                            # A (Menu) -> A (Selects TALK)
    "CHECK_STATUS": ["A", "DOWN", "A"],                    # A (Menu) -> Down -> A (Selects STATUS)
    "GO_STAIRS":    ["A", "DOWN", "DOWN", "A"],            # A (Menu) -> Down -> Down -> A (Selects STAIRS)
    "SEARCH":       ["A", "DOWN", "DOWN", "DOWN", "A"],    # A (Menu) -> Down -> Down -> Down -> A (Selects SEARCH)
    "OPEN_SPELL_MENU": ["A", "RIGHT", "A"],                # A (Menu) -> Right -> A (Selects SPELL)
    "OPEN_ITEM_MENU":  ["A", "DOWN", "RIGHT", "A"],        # A (Menu) -> Down -> Right -> A (Selects ITEM)
    "OPEN_DOOR":    ["A", "DOWN", "DOWN", "RIGHT", "A"],   # A (Menu) -> Down -> Down -> Right -> A (Selects DOOR)
    "TAKE_TREASURE": ["A", "DOWN", "DOWN", "DOWN", "RIGHT", "A"], # A (Menu) -> ... -> A (Selects TAKE)

    # --- Battle Menu Macros ---
    "BATTLE_FIGHT": ["A"],                         # Selects FIGHT (default cursor position)
    "BATTLE_RUN":   ["RIGHT", "RIGHT", "A"],      # Right -> Right -> A (Selects RUN)
    "BATTLE_SPELL": ["RIGHT", "A"],              # Right -> A (Selects SPELL)
    "BATTLE_ITEM":  ["RIGHT", "RIGHT", "RIGHT", "A"] # Right -> Right -> Right -> A (Selects ITEM)
}
    #-----Conversation----
    "TALK": {"A"}
    "SEQUENCE_TALK": ["A", "A"]                 # PRESS A until Downward Arrow Key no longer visible in Dialogue Box
    
