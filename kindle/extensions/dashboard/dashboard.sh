#!/bin/sh
# Kindle side: pull the dashboard PNG from the server every 15 s and draw it.
# Usage: dashboard.sh start | stop     (KUAL menu calls these)

INTERVAL=${DASH_INTERVAL:-15}  # retry delay when the server is unreachable (normal updates are pushed)
FULL_REFRESH_EVERY=120  # full black/white flash every N redraws to clear e-ink ghosting
IMG=/tmp/dashboard.png
PIDFILE=/tmp/dashboard.pid
DIR=${DASH_DIR:-/mnt/us/extensions/dashboard}  # overridable for testing off-device
# server address: first line of server_url next to this script (git-ignored), e.g. http://192.168.1.10:8080
SERVER=$(head -n 1 "$DIR/server_url" 2>/dev/null | tr -d '\r ')
URL="${DASH_URL:-${SERVER:-http://192.168.1.10:8080}/dashboard.png}"
TAP_URL="${URL%/dashboard.png}/tap"
KEY_URL="${URL%/dashboard.png}/key"
LUAJIT=${DASH_LUAJIT:-/mnt/us/koreader/luajit}  # KOReader's LuaJIT runs the touch reader (tap.lua)
LOG="$DIR/dashboard.log"  # on the USB drive, so it can be read from a computer

FB_ROTATE_FILE=${DASH_FB_ROTATE:-/sys/class/graphics/fb0/rotate}
FB_ROTATION=0  # native panel orientation: the server's image and the touch mapping both assume it
LIGHT_FILE=/tmp/dashboard.brightness  # "auto" or 0-24, from the server's X-Brightness header
LIGHT_CHECK_SECONDS=2  # auto-brightness keeps nudging the front light; put it back this often
MAX_FAILURES=4  # consecutive fetch/draw failures before giving up and restoring the Kindle UI
EXIT_WATCH_DELAY=8  # seconds before touches count, so the KUAL tap that started us doesn't stop us

log() { echo "$(date '+%m-%d %H:%M:%S') $*" >> "$LOG"; }

watch_exit() {  # power button stops the dashboard; touch screen goes to tap.lua (music buttons); sensors ignored
  sleep "$EXIT_WATCH_DELAY"
  for ev in /sys/class/input/event*; do
    name=$(cat "$ev/device/name" 2>/dev/null)
    case "$name" in
      *cyttsp*|*_mt*|*zforce*|*[Tt]ouch*)
        dev="/dev/input/${ev##*/}"
        if [ -f "$LUAJIT" ]; then
          log "touch reader on $dev ($name)"
          "$LUAJIT" "$DIR/tap.lua" "$dev" "$TAP_URL" "$IMG" >> "$LOG" 2>&1 &
        else
          log "no LuaJIT at $LUAJIT: touch controls off"
        fi
        ;;
      *gpio-keys*)  # page-turn buttons: switch between dashboard and Home
        dev="/dev/input/${ev##*/}"
        if [ -f "$LUAJIT" ]; then
          log "page buttons on $dev ($name)"
          "$LUAJIT" "$DIR/tap.lua" "$dev" "$KEY_URL" "$IMG" keys >> "$LOG" 2>&1 &
        fi
        ;;
      *powerkey*|*pwrkey*|*max77796-key*)  # Oasis 2 power key shows up as snvs-powerkey and max77796-key
        dev="/dev/input/${ev##*/}"
        log "exit watcher on $dev ($name)"
        ( dd if="$dev" of=/dev/null bs=16 count=1 2>/dev/null && log "input on $dev: exiting" && /bin/sh "$0" stop ) &
        ;;
      *) log "ignoring input $ev ($name)" ;;
    esac
  done
}

kill_old() {  # one dashboard at a time: a second Start used to leave two touch readers, doubling every tap
  [ -f "$PIDFILE" ] && kill -9 "$(cat "$PIDFILE")" 2>/dev/null
  pkill -9 -f "dashboard.sh loop" 2>/dev/null
  pkill -f "tap.lua" 2>/dev/null
  pkill -f "dd if=/dev/input/" 2>/dev/null
  rm -f "$PIDFILE"
}

hold_light() {  # keep the front light at the dashboard's level; "auto" leaves the light sensor in charge
  while true; do
    want=$(cat "$LIGHT_FILE" 2>/dev/null)
    case "$want" in
      ''|auto) ;;
      *[!0-9]*) ;;
      *)
        have=$(lipc-get-prop com.lab126.powerd flIntensity 2>/dev/null)
        if [ "$have" != "$want" ]; then
          lipc-set-prop com.lab126.powerd flIntensity "$want" 2>/dev/null
        fi
        ;;
    esac
    sleep "$LIGHT_CHECK_SECONDS"
  done
}

restore_ui() {
  pkill -f "dd if=/dev/input/" 2>/dev/null  # stop exit watchers
  pkill -f "tap.lua" 2>/dev/null
  lipc-set-prop com.lab126.powerd preventScreenSaver 0
  start lab126_gui 2>/dev/null || start framework 2>/dev/null
}

give_up() {  # restore the normal Kindle screen and end the loop
  log "giving up: $*"
  eips 1 1 "Dashboard stopped: $* - restoring Kindle"
  sleep 3
  rm -f "$PIDFILE"
  [ -n "$HOLD_PID" ] && kill "$HOLD_PID" 2>/dev/null  # stop holding the front light
  restore_ui
  exit 0
}

lock_orientation() {  # turning the Kindle must not rotate the dashboard (black bar stays at the bottom)
  lipc-set-prop com.lab126.winmgr orientationLock U 2>/dev/null  # only works while the window manager runs
  [ -w "$FB_ROTATE_FILE" ] || return 0
  if [ "$(cat "$FB_ROTATE_FILE" 2>/dev/null)" != "$FB_ROTATION" ]; then
    echo "$FB_ROTATION" > "$FB_ROTATE_FILE" && log "orientation reset to $FB_ROTATION"
  fi
}

draw() {  # $1 = 1 for a full (flashing) refresh. (KOReader's FBInk has image support disabled, so eips.)
  lock_orientation
  flash=""; [ "$1" = 1 ] && flash="-f"
  out=$(eips $flash -g "$IMG" 2>&1) && return 0
  log "eips failed: $out"
  return 1
}

loop() {
  trap '' HUP TERM  # stopping the Kindle UI signals everything it launched (KUAL -> us); ignore it
  echo $$ > "$PIDFILE"  # so stop can kill exactly this loop
  : > "$LOG"
  log "starting; url=$URL; screen rotation was $(cat "$FB_ROTATE_FILE" 2>/dev/null || echo unknown)"
  log "eips -i: $(eips -i 2>&1 | tr '\n' ' ' | cut -c1-300)"
  lipc-set-prop com.lab126.powerd preventScreenSaver 1
  stop lab126_gui 2>/dev/null || stop framework 2>/dev/null   # stop the Kindle UI drawing over us
  sleep 3
  watch_exit &
  hold_light &
  HOLD_PID=$!
  n=0
  fails=0
  ver=0  # server picture version; the server holds each request until the picture changes (long poll)
  while true; do
    batt=$(lipc-get-prop com.lab126.powerd battLevel 2>/dev/null || gasgauge-info -c 2>/dev/null | tr -dc 0-9)
    if curl -fsS -m 40 -D "$IMG.hdr" -o "$IMG.new" "$URL?battery=$batt&wait=$ver" 2>>"$LOG"; then
      ver=$(grep -i '^X-Version:' "$IMG.hdr" | tr -dc 0-9)
      ver=${ver:-0}
      light=$(grep -i '^X-Brightness:' "$IMG.hdr" | cut -d: -f2 | tr -dc 'a-z0-9')
      if [ -n "$light" ] && [ "$light" != "$(cat "$LIGHT_FILE" 2>/dev/null)" ]; then
        echo "$light" > "$LIGHT_FILE" && log "screen light -> $light"
      fi
      fails=0
      if cmp -s "$IMG.new" "$IMG"; then
        rm -f "$IMG.new"  # already on screen (e.g. tap.lua drew it): skip the e-ink redraw
      else
        mv "$IMG.new" "$IMG"
        full=0; [ $((n % FULL_REFRESH_EVERY)) -eq 0 ] && full=1
        if draw $full; then
          [ $n -lt 3 ] && log "drew image $n (full=$full, version=$ver, batt=$batt)"
        else
          fails=$((fails + 1))
        fi
        n=$((n + 1))
      fi
    else
      fails=$((fails + 1))
      log "fetch failed ($fails/$MAX_FAILURES)"
      eips 1 1 "fetch failed $(date +%H:%M) - retrying ($fails/$MAX_FAILURES)"
      sleep "$INTERVAL"  # server unreachable: back off instead of retrying in a tight loop
    fi
    [ $fails -ge $MAX_FAILURES ] && give_up "$fails failures in a row"
  done
}

case "$1" in
  start)  # stop any earlier run first, then start fresh in its own session
    kill_old  # then setsid: own session, so stopping the Kindle UI (which launched KUAL) doesn't take us down
    if command -v setsid >/dev/null 2>&1; then setsid /bin/sh "$0" loop >/dev/null 2>&1 < /dev/null &
    else nohup /bin/sh "$0" loop >/dev/null 2>&1 < /dev/null & fi ;;   # FAT storage: no exec bit, so run via sh
  loop) loop ;;
  stop)
    [ -f "$PIDFILE" ] && kill -9 "$(cat "$PIDFILE")" 2>/dev/null  # -9: the loop ignores TERM on purpose
    rm -f "$PIDFILE"
    pkill -9 -f "dashboard.sh loop" 2>/dev/null  # fallback if the pid file is missing
    restore_ui
    ;;
  *) echo "usage: $0 start|stop" ;;
esac
