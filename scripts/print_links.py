"""Prints a link to every resource of the bundle, grouped by type. Runs after each deploy (postdeploy hook in
databricks.yml) and on its own: python3 scripts/print_links.py --target demo --profile <profile> --var catalog=<catalog>"""
import argparse
import json
import subprocess
import sys

GROUPS = [("apps", "App"), ("genie_spaces", "Genie agents"), ("pipelines", "Pipelines"), ("jobs", "Jobs"),
          ("experiments", "Prompts and traces"), ("schemas", "Schemas"), ("volumes", "Volumes")]


def cli(*args):
    return json.loads(subprocess.run(["databricks", *args], check=True, capture_output=True, text=True).stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--profile", default="")
    ap.add_argument("--var", action="append", default=[])
    a = ap.parse_args()
    profile = ["--profile", a.profile] if a.profile else []
    try:
        res = cli("bundle", "summary", "-t", a.target, "-o", "json", *profile,
                  *[x for v in a.var for x in ("--var", v)])["resources"]
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"Could not read the bundle summary: {e}", file=sys.stderr)
        return
    print("\nDeployed resources")
    for kind, title in GROUPS:
        items = res.get(kind, {})
        if not items:
            continue
        print(f"\n{title}")
        for key, r in sorted(items.items()):
            url = r.get("url")
            if kind == "apps":  # the app's own address, not its settings page
                try:
                    url = cli("apps", "get", r["name"], "-o", "json", *profile).get("url") or url
                except subprocess.CalledProcessError:
                    pass
            name = (r.get('title') or r.get('name') or key).split('/')[-1]
            print(f"  {name}: {url or '(not created yet)'}")


if __name__ == "__main__":
    main()
