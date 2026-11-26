-- Kindle touch reader: on each finger lift, send where the finger started and lifted (tap or swipe)
-- to the server and draw the image it returns.
-- Run with KOReader's LuaJIT:  luajit tap.lua /dev/input/eventN http://server:8080/tap /tmp/dashboard.png
-- Reads 16-byte input_event structs (32-bit ARM: timeval 8 bytes, type u16, code u16, value s32).

local dev, tap_url, img, mode = arg[1], arg[2], arg[3], arg[4]  -- mode "keys": page-turn buttons
if not (dev and tap_url and img) then
  io.stderr:write("usage: luajit tap.lua DEVICE TAP_URL IMAGE\n")
  os.exit(2)
end

local EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
local BTN_TOUCH = 0x14a
local ABS_X, ABS_Y = 0x00, 0x01
local ABS_MT_X, ABS_MT_Y, ABS_MT_TRACKING_ID = 0x35, 0x36, 0x39

local function u16(s, i) return s:byte(i) + s:byte(i + 1) * 256 end
local function s32(s, i)
  local v = s:byte(i) + s:byte(i + 1) * 256 + s:byte(i + 2) * 65536 + s:byte(i + 3) * 16777216
  if v >= 2147483648 then v = v - 4294967296 end
  return v
end

local function log(msg)
  io.stdout:write(os.date("%m-%d %H:%M:%S "), "tap.lua ", msg, "\n")
  io.stdout:flush()
end

local function send(x, y, sx, sy)
  local cmd = string.format(
    'curl -fsS -m 12 -o %s.tap "%s?x=%d&y=%d&sx=%d&sy=%d" && mv %s.tap %s && eips -g %s >/dev/null 2>&1',
    img, tap_url, x, y, sx, sy, img, img, img)
  local ok = os.execute(cmd)
  log(string.format("touch %d,%d -> %d,%d sent=%s", sx, sy, x, y, tostring(ok == 0 or ok == true)))
end

local function send_key(code)
  local cmd = string.format('curl -fsS -m 12 -o %s.key "%s?code=%d" && mv %s.key %s && eips -g %s >/dev/null 2>&1',
    img, tap_url, code, img, img, img)
  local ok = os.execute(cmd)
  log(string.format("key %d sent=%s", code, tostring(ok == 0 or ok == true)))
end

local f, err = io.open(dev, "rb")
if not f then log("cannot open " .. dev .. ": " .. tostring(err)); os.exit(1) end
log("listening on " .. dev)

local x, y, is_down = nil, nil, false
local has_mt = false  -- once multi-touch coordinates appear, ignore legacy ABS_X/ABS_Y (cyttsp5 sends bogus edge values there)
local sx, sy, want_start = nil, nil, false  -- first position of the current touch, captured at its first SYN
while true do
  local ev = f:read(16)
  if not ev or #ev < 16 then log("input closed"); break end
  local typ, code, value = u16(ev, 9), u16(ev, 11), s32(ev, 13)
  if mode == "keys" then
    if typ == EV_KEY and value == 1 then  -- press only (1); ignore release (0) and auto-repeat (2)
      local ok, e = pcall(send_key, code)
      if not ok then log("key send failed: " .. tostring(e)) end
    end
  elseif typ == EV_ABS and (code == ABS_MT_X or code == ABS_MT_Y) then
    has_mt = true
    if code == ABS_MT_X then x = value else y = value end
  elseif typ == EV_ABS and not has_mt and (code == ABS_X or code == ABS_Y) then
    if code == ABS_X then x = value else y = value end
  elseif (typ == EV_ABS and code == ABS_MT_TRACKING_ID and value >= 0) or (typ == EV_KEY and code == BTN_TOUCH and value == 1) then
    if not is_down then want_start = true end
    is_down = true
  elseif typ == EV_SYN and code == 0 and want_start and x and y then
    sx, sy, want_start = x, y, false
  elseif (typ == EV_ABS and code == ABS_MT_TRACKING_ID and value < 0) or (typ == EV_KEY and code == BTN_TOUCH and value == 0) then
    if is_down and x and y then
      is_down = false  -- one tap per lift, even though both release signals may arrive
      local ok, e = pcall(send, x, y, sx or x, sy or y)
      sx, sy = nil, nil
      if not ok then log("send failed: " .. tostring(e)) end
    end
  end
end
