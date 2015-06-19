#!/usr/bin/env python
# Copyright 2015 Cloudbase Solutions Srl
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import sys

import git
import requests
import sqlite3
import yaml


def get_remote_git_ref(remote_url, branch="master"):
    g = git.Git(".")
    ref_info = g.ls_remote(remote_url, "refs/heads/" + branch).split('\t')
    if ref_info[0]:
        return ref_info[0]


def check_db(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS jobs("
        "job_name varchar(200) NOT NULL, "
        "remote_url varchar(400) NOT NULL, "
        "branch varchar(400) NOT NULL, "
        "last_ref varchar(100) NOT NULL, "
        "PRIMARY KEY (job_name, remote_url, branch))")


def get_last_git_ref(db_path, job_name, remote_url, branch):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT last_ref FROM jobs "
        "WHERE job_name=? AND remote_url=? AND branch=?",
        (job_name, remote_url, branch))
    row = cur.fetchone()
    if row:
        return row[0]


def set_last_git_ref(db_path, job_name, remote_url, branch, curr_ref):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "UPDATE jobs set last_ref=? "
        "WHERE job_name=? AND remote_url=? AND branch=?",
        (curr_ref, job_name, remote_url, branch))
    if not cur.rowcount:
        cur.execute(
            "INSERT INTO jobs (job_name, remote_url, branch, last_ref) "
            "VALUES (?, ?, ?, ?)",
            (job_name, remote_url, branch, curr_ref))
    conn.commit()


def exec_action_url(action_url):
    print "Executing action: %s" % action_url
    response = requests.get(action_url)
    response.raise_for_status()


def process_job(db_path, job_name, job_config):
    run_action = True
    action_url = job_config.get('action_url')
    if not action_url:
        raise ValueError("action_url is required for job %s" % job_name)

    for repo in job_config.get('repos', []):
        remote_url = repo.get('remote_url')
        if not remote_url:
            raise ValueError("remote_url is required for a repository")
        branch = repo.get('branch', 'master')

        curr_ref = get_remote_git_ref(remote_url, branch)
        if not curr_ref:
            raise Exception(
                "Cannot find a ref for git repo %(remote_url)s, "
                "branch %(branch)s, make sure the branch exists" %
                {"remote_url": remote_url, "branch": branch})

        previous_ref = get_last_git_ref(
            db_path, job_name, remote_url, branch)

        print "Repo url: %s" % remote_url
        print "Curr ref: %s" % curr_ref
        print "Previous ref: %s" % previous_ref

        if curr_ref != previous_ref:
            if run_action:
                exec_action_url(action_url)
                run_action = False
            set_last_git_ref(
                db_path, job_name, remote_url, branch, curr_ref)


def main():
    if len(sys.argv) != 2:
        print "Usage: %s <config.yaml>" % sys.argv[0]
        return

    config_file = sys.argv[1]
    with open(config_file, 'rb') as s:
        config = yaml.load(s)

    db_path = config.get("config", {}).get("db", "gitpoll.s3db")
    check_db(db_path)

    jobs = config.get('jobs', {})
    for job_name in jobs:
        try:
            process_job(db_path, job_name, jobs[job_name])
        except Exception as ex:
            print "job failed: %s" % job_name
            print ex


if __name__ == "__main__":
    main()
