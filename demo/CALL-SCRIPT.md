# Call script: the Software Factory in about eight minutes

For a founder showing the factory on a sales call. Synthetic data only. Rehearse once before a call.

## Before the call (5 minutes)

- `demo/reset.sh OWNER/factory-sample` and check the three sample issues are open.
- `hubzoid run . --port 8701` and `hubzoid hub doctor .` all green.
- Tabs: the issue list, issue #1, the hub chat at http://127.0.0.1:8701, the Console's Work items.

## The call

1. **The problem (30 seconds).** "Your team has a backlog of small, well-understood fixes. Each one costs a developer an hour of context switching. The factory takes them to a reviewed draft pull request, and a person still decides what merges."
2. **The folder (1 minute).** Show `agents/`: five stations, each plain Markdown. "This is the whole factory. You can read every rule, and change them."
3. **Label an issue (1 minute).** Open issue #1 (the invoice rounds per line). Add the `factory` label. Point at the "Accepted" reply.
4. **While it works (2 minutes).** Open Work items in the Console: the stages filling in, the station calls. Explain: the implementer works in a sandbox with no credentials and no network. The reviewer is a separate agent that never wrote the code, checking the exact pushed commit.
5. **The result (2 minutes).** Open the draft pull request: the problem, the approach, the acceptance criteria with the reviewer's result for each, the test output, `Closes #1`. "It's a draft. Your developer reviews it, marks it ready and merges. The factory has no merge button."
6. **Chat (1 minute).** In the chat: "Plan a fix for issue #3, stop after the plan." Show the plan waiting under Waiting for you. "For work someone asks for directly, they approve the exact plan before anything is built."
7. **Make it yours (30 seconds).** "Point it at your repository, put your install command in one file, and tell it your team's rules. A rule becomes a reviewed change to a file, not a chat memory."

## Questions that come up

- *Which model?* "Your own Claude Code or Codex login. No API key needed. The reviewer can be a different vendor if you want."
- *Can it merge?* "No. There is no merge tool, and marking ready waits for the person who asked."
- *What if it gets it wrong?* "The reviewer sends it back up to twice, then it stops and tells you why. The branch stays for a person. Nothing ever looks approved when it wasn't."
- *Where does it run?* "Your laptop, or your own cloud. Your code never goes to us."
