-- File paths for communication with the Python agent  
local STATS_FILE = "dq1_stats.txt"  
local ACTION_FILE = "action.txt"  
  
-- A table to hold the state of all controller buttons for a single frame.  
-- This is the table that emu.setInput() expects.  
local input_state = {  
  a = false, b = false, up = false, down = false,  
  left = false, right = false, select = false, start = false  
}  
  
-- RAM addresses for game data, from your working script.  
local o = {  
  hp       = 0x00C5, mp = 0x00C6, level = 0x00C7,  
  px       = 0x003A, py = 0x003B,  
  gold_lo  = 0x00BC, gold_hi = 0x00BD,  
  enemy_hp = 0x00E2, map_id = 0x0045  
}  
  
-- Variables for input handling  
local current_actions = {}  
local action_frames_remaining = 0  
local MAX_COMMANDS = 8  
  
-- Define which buttons are movement vs action buttons  
local movement_buttons = {left = true, right = true, up = true, down = true}  
local action_buttons = {a = true, b = true, select = true, start = true}  
  
-- Helper function to read 1 byte from CPU RAM.  
local function rb(addr)  
  return emu.read(addr, emu.memType.nesDebug)  
end  
  
-- Function to parse comma-separated commands  
local function parse_commands(command_string)  
  local commands = {}  
  local count = 0  
    
  for cmd in command_string:gmatch("([^,]+)") do  -- Split on commas  
    if count >= MAX_COMMANDS then  
      break  -- Limit to max 8 commands  
    end  
      
    local trimmed_cmd = cmd:match("^%s*(.-)%s*$")  -- Trim whitespace  
    if input_state[trimmed_cmd] ~= nil then  -- Only add valid commands  
      table.insert(commands, trimmed_cmd)  
      count = count + 1  
    end  
  end  
  return commands  
end  
  
-- Input handling function for inputPolled event  
local function on_input_polled()  
  -- Reset input state  
  for button, _ in pairs(input_state) do  
    input_state[button] = false  
  end  
  
  -- Check if we need to read new actions  
  if action_frames_remaining <= 0 then  
    local script_folder = emu.getScriptDataFolder()  
    if script_folder ~= "" then  
      local action_path = script_folder .. "/" .. ACTION_FILE  
      local file = io.open(action_path, "r")  
      if file then  
        local command = file:read("*a"):match("^%s*(.-)%s*$")  
        file:close()  
          
        if command and command ~= "" then  
          current_actions = parse_commands(command)  
          if #current_actions > 0 then  
            -- Check if any movement buttons are present  
            local has_movement = false  
            for _, action in ipairs(current_actions) do  
              if movement_buttons[action] then  
                has_movement = true  
                break  
              end  
            end  
              
            -- Use fixed 16 frames for movement, 2 frames for action buttons  
            if has_movement then  
              action_frames_remaining = 24  -- Fixed duration for reliable movement  
            else  
              action_frames_remaining = 2   -- Short duration for menu actions  
            end  
              
            -- Debug logging  
            emu.log("Parsed " .. #current_actions .. " commands for " .. action_frames_remaining .. " frames: " .. table.concat(current_actions, ", "))  
          end  
            
          -- Clear the action file  
          local f_write = io.open(action_path, "w")  
          f_write:write("")  
          f_write:close()  
        end  
      end  
    end  
  end  
  
  -- Apply all current actions if we have frames remaining  
  if action_frames_remaining and action_frames_remaining > 0 then  
    for _, action in ipairs(current_actions) do  
      input_state[action] = true  
    end  
    action_frames_remaining = action_frames_remaining - 1  
  end  
  
  -- Apply input with correct parameters (input_table, port, subport)  
  emu.setInput(input_state, 0, 0)  
end  
  
-- Frame handling function for stats and display  
local function on_frame()  
  -- Read all game stats into local variables  
  local hp   = rb(o.hp)  
  local mp   = rb(o.mp)  
  local lvl  = rb(o.level)  
  local px   = rb(o.px)  
  local py   = rb(o.py)  
  local gold = rb(o.gold_lo) + 256 * rb(o.gold_hi)  
  local ehp  = rb(o.enemy_hp)  
  local map  = rb(o.map_id)  
  
  -- Display stats on screen  
  emu.drawString(5, 5,  
    string.format("HP:%d MP:%d LV:%d GOLD:%d\nPOS:%d,%d MAP:%02X EHP:%d",  
                  hp, mp, lvl, gold, px, py, map, ehp))  
  
  -- Write stats to the external file for the AI  
  local script_folder = emu.getScriptDataFolder()  
  if script_folder ~= "" then  
    local stats_path = script_folder .. "/" .. STATS_FILE  
    local f = io.open(stats_path, "w")  
    if f then  
      f:write(string.format(  
        "hp=%d\nmp=%d\nlevel=%d\ngold=%d\npx=%d\npy=%d\nmap_id=%d\nenemy_hp=%d\n",  
        hp, mp, lvl, gold, px, py, map, ehp))  
      f:close()  
    end  
  end  
end  
  
-- Register input handling for inputPolled event  
emu.addEventCallback(on_input_polled, emu.eventType.inputPolled)  
  
-- Register stats/display for endFrame event    
emu.addEventCallback(on_frame, emu.eventType.endFrame)  
  
emu.displayMessage("DQ1 Final Interface (Corrected) Loaded", 2000)
