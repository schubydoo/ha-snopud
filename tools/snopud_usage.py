#!/usr/bin/env python3
"""Download interval usage from the MySnoPUD portal (my.snopud.com, MyMeter platform).

Credentials come from ~/.config/snopud.env (SNOPUD_USER, SNOPUD_PASS) or the
environment. Prints CSV to stdout (or --out). Nothing is written to disk except --out.

  snopud_usage.py --service electric --interval 15min --start 2026-09-24 --end 2026-09-26
"""
import argparse, datetime as dt, os, sys
from html.parser import HTMLParser
import requests

BASE = "https://my.snopud.com"
SERVICES = {"electric": "1", "water": "2"}
INTERVALS = {"15min": "3", "30min": "4", "hourly": "5", "daily": "6", "weekly": "8", "billing": "7"}
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36"


class FormParser(HTMLParser):
    """Collect the fields of one <form> the way a browser would serialize them."""

    def __init__(self, action=None):
        super().__init__()
        self.action, self.in_form, self.fields = action, action is None, []
        self._select = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form" and self.action and (a.get("action") or "").lower() == self.action.lower():
            self.in_form = True
        if not self.in_form or not a.get("name"):
            if tag == "option" and self._select is not None:
                if "selected" in a or self._select[1] is None:
                    self._select[1] = a.get("value") or ""
            return
        if tag == "input":
            t = (a.get("type") or "text").lower()
            if t in ("checkbox", "radio"):
                if "checked" in a:
                    self.fields.append([a["name"], a.get("value", "on")])
            elif t not in ("submit", "button", "file"):
                self.fields.append([a["name"], a.get("value", "")])
        elif tag == "select":
            self._select = [a["name"], None]

    def handle_endtag(self, tag):
        if tag == "select" and self._select is not None:
            if self.in_form:
                self.fields.append([self._select[0], self._select[1] or ""])
            self._select = None
        if tag == "form" and self.action:
            self.in_form = False


def ajax_html(r):
    """The portal wraps partial HTML as {"AjaxResults": [{"Value": "<html>"}, ...]}."""
    try:
        return "".join(x.get("Value") or "" for x in r.json().get("AjaxResults", []))
    except ValueError:
        return r.text


def form_fields(html, action=None):
    p = FormParser(action)
    p.feed(html)
    return p.fields


def set_field(fields, name, value):
    for f in fields:
        if f[0] == name:
            f[1] = value
            return
    fields.append([name, value])


def load_creds():
    user, pw = os.environ.get("SNOPUD_USER"), os.environ.get("SNOPUD_PASS")
    path = os.path.expanduser("~/.config/snopud.env")
    if (not user or not pw) and os.path.exists(path):
        for line in open(path):
            k, _, v = line.strip().partition("=")
            v = v.strip().strip('"').strip("'")
            if k == "SNOPUD_USER" and not user:
                user = v
            if k == "SNOPUD_PASS" and not pw:
                pw = v
    if not user or not pw:
        sys.exit("missing SNOPUD_USER / SNOPUD_PASS")
    return user, pw


def login(s, user, pw):
    home = s.get(BASE + "/")
    home.raise_for_status()
    token = next((v for k, v in form_fields(home.text) if k == "__RequestVerificationToken"), None)
    if not token:
        sys.exit("login page: no __RequestVerificationToken found")
    data = {"RedirectUrl": "", "LoginErrorMessage": "", "LoginEmail": user, "LoginPassword": pw,
            "ExternalLogin": "False", "TwoFactorRendered": "False", "SecretQuestionRendered": "False",
            "__RequestVerificationToken": token}
    r = s.post(BASE + "/Home/Login", data=data, headers={"X-Requested-With": "XMLHttpRequest", "Referer": BASE + "/"})
    r.raise_for_status()
    # The portal finishes the session through these two calls before the dashboard works.
    s.get(BASE + "/Integration/LoginActions", headers={"Referer": BASE + "/"}).raise_for_status()
    s.get(BASE + "/Integration/LoginActionsComplete", headers={"X-Requested-With": "XMLHttpRequest"})
    d = s.get(BASE + "/Dashboard")
    if "/Dashboard" not in d.url or "LoginPassword" in d.text:
        sys.exit(f"login failed (landed on {d.url}); portal said: {r.text[:200]!r}")


def download(s, service, interval, start, end):
    xhr = {"X-Requested-With": "XMLHttpRequest", "Referer": BASE + "/Dashboard"}
    html = ajax_html(s.get(BASE + "/Usage/InitializeDownloadSettings", headers=xhr))
    fields = form_fields(html, "/Usage/Download")
    if not fields:
        sys.exit("download form not found")
    current = next((v for k, v in fields if k == "SelectedServiceType"), None)
    if current != SERVICES[service]:
        set_field(fields, "SelectedServiceType", SERVICES[service])
        html = ajax_html(s.post(BASE + "/Usage/UpdateDownloadSettings", data=fields, headers=xhr))
        new = form_fields(html, "/Usage/Download") or form_fields(html)
        if not new:
            sys.exit("could not switch service type")
        fields = new
        set_field(fields, "SelectedServiceType", SERVICES[service])
    for k, v in (("FileFormat", "download-usage-csv"), ("SelectedFormat", "2"),
                 ("SelectedInterval", INTERVALS[interval]), ("Start", start), ("End", end)):
        set_field(fields, k, v)
    err = ajax_html(s.post(BASE + "/Usage/PresentDownloadErrors", data=fields, headers=xhr))
    if err.strip() not in ("", '""', "null"):
        print(f"portal validation message: {err.strip()[:300]}", file=sys.stderr)
    r = s.post(BASE + "/Usage/Download", data=fields, headers={"Referer": BASE + "/Dashboard", "Origin": BASE})
    r.raise_for_status()
    if "csv" not in r.headers.get("content-type", ""):
        sys.exit(f"expected CSV, got {r.headers.get('content-type')}: {r.text[:200]!r}")
    return r.text


def main():
    today = dt.date.today()
    p = argparse.ArgumentParser()
    p.add_argument("--service", choices=SERVICES, default="electric")
    p.add_argument("--interval", choices=INTERVALS, default="hourly")
    p.add_argument("--start", default=str(today - dt.timedelta(days=2)))
    p.add_argument("--end", default=str(today))
    p.add_argument("--out")
    a = p.parse_args()
    s = requests.Session()
    s.headers["User-Agent"] = UA
    login(s, *load_creds())
    csv = download(s, a.service, a.interval, a.start, a.end)
    if a.out:
        open(a.out, "w").write(csv)
    else:
        sys.stdout.write(csv)


if __name__ == "__main__":
    main()
