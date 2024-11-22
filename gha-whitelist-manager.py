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


class WhitelistUpdater:
    """ Scans pubsub for changes to a defined whitelist, and Handles the API requests to GitHub """
    def __init__(self, config):
        self.config = config
        self.ghurl = f"https://api.github.com/orgs/{ORG}/actions/permissions/selected-actions"
        self.s = requests.Session()
        self.mail_map = {} 
        raw_map = self.s.get("https://whimsy.apache.org/public/committee-info.json").json()['committees']
        [ self.mail_map.update({ item: raw_map[item]['mail_list']}) for item in raw_map ]
        self.s.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.config['gha_token']}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        self.pubsub = "https://pubsub.apache.org:2070/git/commit"
        self.logger = Log(config)
    def scan(self):
        self.logger.log.info("Connecting to %s" % self.pubsub)
        asfpy.pubsub.listen_forever(self.handler, self.pubsub, raw=True)
    
    def update(self, wlist):
        """Update the GitHub actions whitelist for the org"""
        data = {
            "github_owned_allowed": True,
            "verified_allowed": False,
            "patterns_allowed": wlist,
        }
        r = s.put("%s/%s" % (self.ghurl, ), data=json.dumps(data))
        if results.status_code == 204:
            print("Updated.")

    def handler(self, data):
        if "commit" in data and data["commit"]["project"] == PUBLIC_INTERFACE:
            # Check if modified files are in path
            p = re.compile(r"^{APPROVED_PATTERNS_FILEPATH}$")
            results = [w for w in data["commit"].get("files", []) if p.match(w)]
            print(results)
            if len(results) > 0:
                self.logger.log.debug("Updated whitelist detected")

                # get the new yaml file contents with a rawusercontent translation
                # trigger self.update with the contents
                self.logger.log.debug("Nothing doin!! got no code ;)")
        else:
             self.logger.log.info("Heartbeat Signal Detected")

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", help="Configuration file", default="config.yml")
    args = parser.parse_args()
    setattr(args, "uri", "orgs/asf-transfer/actions/permissions/selected-actions")
    return args

if __name__ == "__main__":
    args = get_args()
    config = yaml.safe_load(open(args.config, "r").read())
    w = WhitelistUpdater(config)
    w.scan()
