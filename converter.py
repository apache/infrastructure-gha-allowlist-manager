#!/usr/bin/python3

import os
import yaml
import requests
import sys
import re
import logging

GITHUB_TOKEN = os.environ['dfoulks1']
DEFAULT_EXPIRATION_DATE = "2050-01-01"

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


class Converter:
    # Handles Converting the allowed_patterns list to an actions.yml that can be consumed by our workflow
    def __init__(self):
        self.ghurl = "https://api.github.com"
        self.s = requests.Session()
        self.mail_map = {}
        self.logger = Log({
            "logfile": "stdout",
            "verbosity": 5,
            }
        )
        self.allowlist = {}
        self.s.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def gh_fetch(self, uri):
        self.logger.log.debug(f"Fetching {uri}...")
        try:
            data = self.s.get(uri).content.decode("utf-8")
            data.raise_for_status()

        except:
            self.logger.log.debug(f"{uri} Returned 404!")
            return None

        if data.status == "404":
            self.logger.log.debug(f"{uri} Returned 404!")
            return None
        else:
           return(data.content.decode("utf-8"))

    def build_action(self, action, tag):
        self.logger.log.info(f"Fetching Details on {action}")
        
        gh_uri = f"https://api.github.com/repos/{action}"
        tags = self.gh_fetch(f"{gh_uri}/git/refs/tags")
        heads =self.gh_fetch(f"{gh_uri}/refs/heads")
        
        if tags and heads:
            t = {}
            self.logger.log.info(f"Parsing tag: {tag}")
            print(tags)
            if "*" in tag:
                # if globbed, set to hash of HEAD.
                # LPT: GitHub SHAs are directly comparable!
                self.logger.log.info("Pinning to the SHA of the current HEAD")
                sha = max(tags, key=lambda x: x['ref'])['object']['sha']

            elif tag == "latest":
                # set to the hash of 'refs/heads/latest'
                self.logger.log.info("Pinning to the SHA of refs/heads/latest")
                sha = [ item for item in headdata if headdata['ref'] == "refs/heads/latest" ][0]['object']['ref']

            elif len(tag) == 40:
                # Lets pretend for now that any 40 character string is a SHA
                # TODO Validate that the 40 character string is a valid SHA
                self.logger.log.alert("Pretending that any 40 character string is a SHA...")
                sha = tag

            else:
                # Check if the provided tag is valid, if so use it.
                self.logger.log.info(f"Pinning to the SHA of refs/heads/{tag}")
                sha = next(( item['object']['sha'] for item in dset if item['ref'] == f"refs/tags/{tag}"), None)
                if sha is None:
                    self.logger.log.error(f"Not found: https://github.com/{action}/tree/{tag}")
                    return

            # Expiration Date set as a GLOBAL
            t[sha] = { "expires_at": "{DEFAULT_EXPIRATION_DATE}" }
            
            return(t)
                    
    def parse_approved_patterns(self, file):
        allowlist = {}
        allowed = yaml.safe_load(file)
        for ap in allowed:
            # Do some work to make sure that the names are right first, _then_ parse the tags
            a = ap.split('/')
            if len(a) == 2:
                org = a[0]
                repo = a[1]
            elif len(a) == 1:
                print(a)
            elif len(a) >= 3:
                # Handle Docker
                if a[0] == "docker:":
                    self.logger.log.alert("Skipping Docker entries for now")
                    self.logger.log.alert(f"  -> {'/'.join(a)}")
                # Eveything else can just be [0:2]
                else:
                    org = a[0]
                    repo = a[1]

            # Action is set for everything but Docker things, which were skipped for now
            act = f"{org}/{repo}"

            if '@' in act:
                act, tag = act.split('@')
            else:
                # In this case * is equivalent to HEAD of the default branch
                tag = "*"
                
            action = self.build_action(act, tag)
            # Update the allowlist
            if act in self.allowlist:
                allowlist[act].update(action)
            else:
                allowlist[act] = action

if __name__ == "__main__":
    c = Converter()
    converted = c.parse_approved_patterns(open('approved_patterns.yml'))
    yaml.dump(converted, open('actions.yaml', 'w+'), default_flow_style=False)





