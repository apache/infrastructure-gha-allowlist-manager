#!/usr/bin/python3

import os
import yaml
import requests
import sys
import re
import logging

GITHUB_TOKEN = os.environ["dfoulks1"]
DOCKERHUB_TOKEN = os.environ["dh_dfoulks"]
DEFAULT_EXPIRATION_DATE = "2050-01-01"
OUTPUT_LEVEL = 3  # 1-5, see Log.verbosity


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
        self.allowlist = {}
        self.logger = Log(
            {
                "logfile": "stdout",
                "verbosity": OUTPUT_LEVEL,
            }
        )

        # GitHub Session Handler
        self.gh = requests.Session()
        self.gh.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

        # DockerHub Session Handler
        self.dh = requests.Session()
        self.dh.headers.update(
            {
                "Authorization": f"Bearer {DOCKERHUB_TOKEN}",
                "Accept": "application/json",
            }
        )

    def gh_fetch(self, uri):
        self.logger.log.debug(f"Fetching {uri}...")
        try:
            data = self.gh.get(uri)
            data.raise_for_status()

        except:
            self.logger.log.error(f"{uri} Returned 404!")
            return None

        data = yaml.safe_load(data.content.decode("utf-8"))
        if isinstance(data, list):
            return data
        else:
            print(data["status"])

    def dh_fetch(self, uri):
        self.logger.log.debug(f"Fetching {uri}...")
        try:
            data = self.dh.get(uri)
            data.raise_for_status()
        except:
            self.logger.log.error(f"{uri} Failed!!!")
            return None

        data = yaml.safe_load(data.content.decode("utf-8"))["results"]
        if isinstance(data, list):
            return data
        else:
            print(data)

    def build_dh_action(self, action, tag):
        self.logger.log.info(f"Fetching tags for Dockerhub://{action}")
        dh_uri = f"https://registry.hub.docker.com/v2/repositories/"
        tags = self.dh_fetch(f"{dh_uri}/{action}/tags/?page_size=100")
        t = {}
        if "*" in tag:
            # set to the newest tagged image
            self.logger.log.info("Pinning DockerHub Image to newest Tagged Image")
            sha = max(tags, key=lambda x: x["name"])["digest"]
        else:
            self.logger.log.info(f"Ensuring {tag} is a valid tag")
            tl = [t["sha"] for t in tags if t["name"] == tag]
            if len(tl) == 0:
                sha = None
                self.logger.log.error(
                    f"Tag: {tag} is not found in {action} tags! Skipping..."
                )
            else:
                sha = tl[0]

        if sha:
            t[sha] = {"expires_at": f"{DEFAULT_EXPIRATION_DATE}"}
        else:
            return None

        return t

    def build_gh_action(self, action, tag):
        self.logger.log.info(f"Fetching Details on {action}")

        gh_uri = f"https://api.github.com/repos/{action}"
        tags = self.gh_fetch(f"{gh_uri}/git/refs/tags")
        heads = self.gh_fetch(f"{gh_uri}/git/refs/heads")

        if tags and heads:
            t = {}
            self.logger.log.info(f"Parsing: {action}@{tag}")
            if "*" in tag:
                # if globbed, set to hash of HEAD.
                # LPT: GitHub SHAs are directly comparable!
                self.logger.log.info("Pinning to the SHA of the current HEAD")
                sha = max(tags, key=lambda x: x["ref"])["object"]["sha"]

            elif tag == "latest":
                # set to the hash of 'refs/heads/latest'
                self.logger.log.info("Pinning to the SHA of refs/heads/latest")
                sha = [item for item in heads if item["ref"] == "refs/heads/latest"][0][
                    "object"
                ]["sha"]

            elif len(tag) == 40:
                # Lets pretend for now that any 40 character string is a SHA
                # TODO Validate that the 40 character string is a valid SHA
                self.logger.log.critical(
                    "Pretending that any 40 character string is a SHA..."
                )
                sha = tag

            else:
                # Check if the provided tag is valid, if so use it.
                self.logger.log.info(f"Pinning to the SHA of refs/heads/{tag}")
                sha = next(
                    (
                        item["object"]["sha"]
                        for item in tags
                        if item["ref"] == f"refs/tags/{tag}"
                    ),
                    None,
                )
                if sha is None:
                    self.logger.log.error(
                        f"Tag: {tag} not found in https://api.github.com/repos/{action}/git/refs/tags"
                    )
                    self.logger.log.error(f"Skipping {action}@{tag}")
                    return None

            # Expiration Date set as a GLOBAL
            t[sha] = {"expires_at": f"{DEFAULT_EXPIRATION_DATE}"}

            return t

    def parse_approved_patterns(self, file):
        allowlist = {}
        allowed = yaml.safe_load(file)
        for ap in allowed:
            # Do some work to make sure that the names are right first, _then_ parse the tags
            a = ap.split("/")

            # Parse Docker things first
            if a[0] == "docker:":
                # action = self.build_dh_action(ap)
                self.logger.log.critical("Parsing DockerHub entry")
                dkey, image, tag = ap.split(":")
                act = image.lstrip("//")
                action = self.build_dh_action(act, tag)

                # reset the action name to include the docker key `docker://`
                act = "//".join([dkey, act])

            # If it's not Docker it's GitHub
            else:
                # %s/%s
                if len(a) == 2:
                    org = a[0]
                    if a[1] != "*":
                        repo = a[1]
                    else:
                        self.logger.log.critical(
                            f"Invalid Entry (No repo provided): {ap}"
                        )
                        continue
                # %s, should not happen
                elif len(a) == 1:
                    print(a)

                # %s/%s/%s trunc'd to %s/%s
                elif len(a) >= 3:
                    org = a[0]
                    repo = a[1]

                act = f"{org}/{repo}"

                if "@" in act:
                    act, tag = act.split("@")
                else:
                    # In this case * is equivalent to HEAD of the default branch
                    tag = "*"

                action = self.build_gh_action(act, tag)

            if action:
                # Update the allowlist
                if act in self.allowlist:
                    allowlist[act].update(action)
                else:
                    allowlist[act] = action

        return allowlist


if __name__ == "__main__":
    c = Converter()
    c.logger.log.info("Parsing {FILENAME}")
    converted = c.parse_approved_patterns(open("approved_patterns.yml"))
    c.logger.log.info("Printing Generated actions.yml to file")
    yaml.dump(converted, open("actions.yaml", "w+"), default_flow_style=False)
    c.logger.log.info("Done!")
