# The one-prompt demo

From a fresh clone to a reviewed draft pull request on your own scratch repository, in about ten minutes. All data is the labelled synthetic sample in `fixtures/`.

## For Claude Code or Codex

Paste this from the cloned folder:

> Set up the Software Factory hub in this folder for a new private scratch repository called factory-sample under my GitHub account. Follow SETUP.md: create the scratch repository from fixtures/sample-repo and seed its issues with demo/seed_issues.py, set FACTORY_REPO, check the settings, prepare the sandbox, and show me the setup command and the GitHub permissions before anything touches the repository. Ask me to connect GitHub with a token I type myself. Run doctor and fix what it reports. Start the hub on port 8701, then add the factory label to issue #1 with gh and watch the work item until it ends. Tell me the draft pull request link, the reviewed commit and how long each step took. Do not merge anything, and do not touch any other repository.

What you see:

1. The settings, the setup command and the token permissions, before anything runs.
2. Doctor with every row green.
3. On issue #1: "Accepted", then progress notes after the classifier, the analyst and the implementer.
4. A draft pull request that fixes the rounding (sum first, round once), with the regression test passing, the reviewer's result for each acceptance criterion, and `Closes #1`.
5. The wrap-up on the issue with the pull request link.

## For a person

Follow `SETUP.md` steps 1 to 8. Time each step and note it.

## Make it yours, in the same session

> Point the factory at OWNER/REPO instead. Show me the settings diff, then change setup.command in sandboxes/factory.yaml to our install command and show me that too. Then propose this team rule for the factory brain: "Run the tests with python -m pytest -q before every commit." I will apply it.

Then ask for a plan on one of your own issues and check the plan mentions the rule.

## Run it again

```sh
demo/reset.sh OWNER/factory-sample
```

It closes the factory's pull requests, deletes factory branches and recreates the sample issues, in that repository only. The next run gives the same result.
