#!/usr/bin/env python3
"""Сбор данных локализации в data.json для дашборда."""
import os, json, fnmatch, subprocess
from datetime import datetime, timezone
import yaml

SRC_ROOT = os.environ.get("SRC_DIR", "_src")
OUT = "data.json"

def git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd, *args],
                       check=True, capture_output=True, text=True)
    return r.stdout.strip()

def last_change_dates(repo):
    """Один проход по истории: {файл: дата последнего коммита, затронувшего его}."""
    out = git(repo, "log", "--name-only", "--pretty=format:@%cI")
    dates, cur = {}, None
    for line in out.splitlines():
        if line.startswith("@"):
            cur = line[1:]
        elif line.strip() and cur:
            dates.setdefault(line, cur)  # первое вхождение = самый свежий коммит
    return dates

def match_any(files, patterns):
    res = []
    for f in files:
        for p in patterns:
            if (p.endswith("/**") and f.startswith(p[:-2])) or fnmatch.fnmatch(f, p):
                res.append(f)
                break
    return res

def lang_of(path):
    """Язык из имени файла: ComparePlus_german.xml -> german."""
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem.rsplit("_", 1)[1] if "_" in stem else None

def evaluate(proj, dates):
    slug = proj["source"]["repo"].split("/")[-1]
    repo = os.path.join(SRC_ROOT, slug)
    files = git(repo, "ls-files").splitlines()

    orig = match_any(files, proj["source"]["watch"])
    orig_dates = [dates[f] for f in orig if f in dates]
    src_date = max(orig_dates) if orig_dates else None

    groups = {}
    for f in match_any(files, [proj["source"]["locale_glob"]]):
        lang = lang_of(f)
        if lang:
            groups.setdefault(lang, []).append(f)

    threshold = proj["compare"].get("stale_after_days", 30)
    cards = []
    for lang in sorted(groups):
        ld = max((dates[f] for f in groups[lang] if f in dates), default=None)
        if not ld or not src_date:
            status, msg = "error", "нет данных"
        else:
            days = (datetime.fromisoformat(src_date) -
                    datetime.fromisoformat(ld)).days
            if days <= 0:
                status, msg = "ok", f"актуален ({ld[:10]})"
            elif days <= threshold:
                status, msg = "warn", f"отстаёт на {days} дн. (обновлён {ld[:10]})"
            else:
                status, msg = "stale", f"отстаёт на {days} дн. — нужны правки"
        cards.append({
            "id": proj["id"], "name": proj["name"], "locale": lang,
            "status": status, "message": msg,
            "source": proj["source"]["repo"],
            "last_locale_change": ld, "last_original_change": src_date,
        })
    return cards

def error_card(proj, text):
    return {"id": proj["id"], "name": proj["name"], "locale": "-",
            "status": "error", "message": text, "source": proj["source"]["repo"]}

def main():
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    cards = []
    for proj in cfg["projects"]:
        if proj["source"]["type"] != "github":
            continue  # weblate-адаптер подключим позже
        try:
            cards += evaluate(proj, last_change_dates(
                os.path.join(SRC_ROOT, proj["source"]["repo"].split("/")[-1])))
        except Exception as e:
            cards.append(error_card(proj, f"ошибка сбора: {e}"))

    data = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "projects": cards}
    json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"OK: {OUT}, карточек: {len(cards)}")

if __name__ == "__main__":
    main()
