#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run as root / Запустите от root'; exit 1; }
python3 - <<'PY'
from pathlib import Path
import os,shutil,time
root=Path('/opt/amnezia-control/dist')
js=root/'app.js';html=root/'index.html'
originals={p:p.read_text(encoding='utf-8') for p in (js,html)}
old="$('#refresh').onclick=load;"
fixed="$('#refresh').onclick=()=>load();"
assert originals[js].count(old)==1 or originals[js].count(fixed)==1,'Unexpected refresh handler; no files changed'
updated={js:originals[js].replace(old,fixed),html:originals[html].replace('app.js?v=061"','app.js?v=061-refresh1"')}
changed=[p for p in originals if updated[p]!=originals[p]]
if not changed:
    print('Already fixed / Уже исправлено');raise SystemExit(0)
backup=Path('/var/lib/amnezia-control/repair-backups')/('refresh-'+str(time.time_ns()))
backup.mkdir(parents=True,mode=0o700)
for p in changed:shutil.copy2(p,backup/p.name)
try:
    for p in changed:
        temp=p.with_name(p.name+'.refresh.tmp')
        temp.write_text(updated[p],encoding='utf-8')
        os.chmod(temp,p.stat().st_mode & 0o777);os.replace(temp,p)
except Exception:
    for p in changed:shutil.copy2(backup/p.name,p)
    raise
print('Fixed / Исправлено. Backup / Копия:',backup)
print('Refresh browser with Ctrl+F5 / Обновите браузер: Ctrl+F5')
PY
