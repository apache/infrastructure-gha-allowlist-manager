#!/usr/bin/env python3
import re
import sys
import yaml
import asfpy.messaging
import asfpy.pubsub
import argparse
import requests
import logging
import json
import smtplib

ORG = "apache"
PUBLIC_INTERFACE = "infrastructure-actions"
APPROVED_PATTERNS_FILEPATH = "approved_patterns.yml"

github_timewait = 60


class Log:
    def __init__(self, config):
        self.config = config
        self.log = logging.getLogger(__name__)
        self.verbosity = {
            0: logging.INFO,
            1: logging.CRITICAL,
            2: logging.ERROR,
            3: logging.WARNING,
            4: logging.INFO,
            5: logging.DEBUG,
        }

        self.stdout_fmt = logging.Formatter(
            "{asctime} [{levelname}] {funcName}: {message}", style="{"
        )

        if self.config["logfile"] == "stdout":
            self.to_stdout = logging.StreamHandler(sys.stdout)
            self.to_stdout.setLevel(self.verbosity[self.config["verbosity"]])
            self.to_stdout.setFormatter(self.stdout_fmt)
            self.log.setLevel(self.verbosity[self.config["verbosity"]])
            self.log.addHandler(self.to_stdout)
        else:
            self.log.setLevel(self.verbosity[self.config["verbosity"]])
            logging.basicConfig(
                format="%(asctime)s [%(levelname)s] %(funcName)s: %(message)s",
                filename=self.config["logfile"],
            )


class AllowlistUpdater:
    """Scans pubsub for changes to a defined allowlist, and Handles the API requests to GitHub"""

    def __init__(self, config):
        self.config = config
        self.logger = Log(config)
        self.action_url = (
            f"https://api.github.com/orgs/{ORG}/actions/permissions/selected-actions"
        )
        self.raw_url = f"https://raw.githubusercontent.com/{ORG}/{PUBLIC_INTERFACE}/refs/heads/main/{APPROVED_PATTERNS_FILEPATH}"
        self.s = requests.Session()

        # Fetch the mail map
        self.logger.log.info("Building mail alias map")
        self.mail_map = {}
        raw_map = self.s.get(
            "https://whimsy.apache.org/public/committee-info.json"
        ).json()["committees"]
        [self.mail_map.update({item: raw_map[item]["mail_list"]}) for item in raw_map]

        # Add the GitHub Headers
        self.s.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.config['gha_token']}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

        self.pubsub = f"https://pubsub.apache.org:2070/git/{PUBLIC_INTERFACE}"

    def scan(self):
        self.logger.log.info("Connecting to %s" % self.pubsub)
        asfpy.pubsub.listen_forever(self.handler, self.pubsub, raw=True)

    def update(self, wlist):
        """Update the GitHub actions allowlist for the org"""
        self.logger.log.debug(wlist)
        data = {
            "github_owned_allowed": True,
            "verified_allowed": True,
            "patterns_allowed": wlist,
        }
        r = self.s.put(f"{self.action_url}", data=json.dumps(data))
        if r.status_code == 204:
            self.logger.log.info("Updated the global approved patterns list.")
        else:
            self.logger.log.error(f"Request returned: {r.status_code}")
            self.logger.log.error("There was a failure to update the GH Org")

    def handler(self, data):
        if "commit" in data and data["commit"]["project"] == PUBLIC_INTERFACE:
            # Check if modified files are in path
            p = re.compile(r"^{}$".format(APPROVED_PATTERNS_FILEPATH))
            results = [w for w in data["commit"].get("files", []) if p.match(w)]
            if len(results) > 0:
                self.logger.log.debug("Updated allowlist detected")
                wlist = yaml.safe_load(self.s.get(self.raw_url).content.decode("utf-8"))
                self.update(wlist)
        else:
            self.logger.log.info("Heartbeat Signal Detected")


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c",
        "--config",
        help="Configuration file",
        default="gha-allowlist-manager.yaml",
    )
    parser.add_argument(
        "--force-update",
        help="Configuration file",
        action="store_true",
        default="False",
    )
    args = parser.parse_args()
    setattr(args, "uri", "orgs/apache/actions/permissions/selected-actions")
    return args


if __name__ == "__main__":
    args = get_args()
    config = yaml.safe_load(open(args.config, "r").read())
    w = AllowlistUpdater(config)
    if args.force_update is True:
        w.logger.log.info(
            f"Fetching approved patterns from: {PUBLIC_INTERFACE}/{APPROVED_PATTERNS_FILEPATH} "
        )
        wlist = yaml.safe_load(w.s.get(w.raw_url).content.decode("utf-8"))
        w.update(wlist)
    else:
        w.scan()
