"""One-off check (safe to delete): do other public projects that read the ITF junior ranking feed hold saved
copies going back further? Read-only: lists ranking-looking data files, how many saved versions each has, and the
date range of those versions. Nothing is saved."""
import subprocess, os, re

REPOS = ["giroldoM/ITF_Intelligence", "genaromoraes/versaoantiga_itf-juniors-live-ranking", "ageorg06/tennis_scrapper",
         "png8nftp9y-alt/png8nftp9y-alt.github.io", "Abhinav-FP/TennisNodeBackend"]
for repo in REPOS:
    d = "/tmp/" + repo.replace("/", "_")
    r = subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout", f"https://github.com/{repo}.git", d], capture_output=True, text=True)
    if r.returncode:
        print(f"===== {repo}: clone failed {r.stderr[:200]}"); continue
    git = lambda *a: subprocess.run(["git", "-C", d, *a], capture_output=True, text=True).stdout
    dates = git("log", "--all", "--format=%cs").split()
    print(f"===== {repo}: {len(dates)} commits, {dates[-1] if dates else '-'} to {dates[0] if dates else '-'}")
    files = [f for f in git("ls-tree", "-r", "--name-only", "HEAD").splitlines()
             if re.search(r"\.(csv|json|jsonl|xlsx|parquet|sqlite|db)$", f, re.I) and re.search(r"rank|junior|jr|itf|player|snapshot|hist", f, re.I)
             and "node_modules" not in f and "package" not in f]
    print(f"  data-looking files: {len(files)}")
    for f in files[:40]:
        vers = git("log", "--all", "--format=%cs", "--", f).split()
        size = git("cat-file", "-s", f"HEAD:{f}").strip()
        head = git("show", f"HEAD:{f}")[:160].replace("\n", " | ")
        print(f"  {f}  [{size} bytes, {len(vers)} versions, {vers[-1] if vers else '-'} to {vers[0] if vers else '-'}]  {head}")
    names = [f for f in git("ls-tree", "-r", "--name-only", "HEAD").splitlines() if re.search(r"20(1|2)\d[-_]?\d\d", f)]
    print(f"  files with a date in the name: {len(names)}", names[:15])
