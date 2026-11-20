"""Which repositories the factory works on, and the one-repository write guard."""
from __future__ import annotations

import pytest

from software_factory import github, repos


def test_an_entry_may_name_its_base_branch():
    assert repos.parse("example-co/api@release/2.0") == repos.Entry("example-co/api", "release/2.0")
    assert repos.parse("example-co/api") == repos.Entry("example-co/api", None)


@pytest.mark.parametrize("bad", ["example-co", "example-co/api@", "example-co/api@a..b", "example-co/api@x y",
                                 "example-co/api@-x", "example-co/api@x.lock", "/api"])
def test_bad_entries_are_refused(bad):
    with pytest.raises(repos.RepoSettingError):
        repos.parse(bad)


def test_one_repository_or_several_never_both():
    assert repos.entries({"FACTORY_REPO": "a/api"}) == [repos.Entry("a/api")]
    assert [e.full_name for e in repos.entries({"FACTORY_REPOS": ["a/api@dev", "a/web"]})] == ["a/api", "a/web"]
    with pytest.raises(repos.RepoSettingError, match="not both"):
        repos.entries({"FACTORY_REPO": "a/api", "FACTORY_REPOS": ["a/web"]})
    assert repos.entries({"FACTORY_REPO": "~/code/app"}) == []          # local folder mode


def test_short_names_must_be_unique():
    with pytest.raises(repos.RepoSettingError, match="share the name"):
        repos.entries({"FACTORY_REPOS": ["a/api", "b/api"]})


def test_tags_and_replies_pick_by_short_or_full_name():
    listed = repos.entries({"FACTORY_REPOS": ["a/api@dev", "a/web"]})
    assert repos.matching(["API", "urgent"], listed) == [listed[0]]
    assert repos.matching(["a/web"], listed) == [listed[1]]
    assert len(repos.matching(["api", "web"], listed)) == 2              # two tags: ask, never guess
    assert repos.from_answer("Use web please.", listed) == [listed[1]]
    assert repos.from_answer("not sure", listed) == []


def _repo(rid, name="a/api"):
    return github.Repo(connection="github", repository_id=rid, full_name=name, default_branch="main",
                       clone_url="x", base_branch="dev")


def test_writes_and_pushes_go_only_to_the_work_items_own_repository():
    github._TARGET.set(None)
    with pytest.raises(github.FactoryRefused):
        github._only_factory_repo(1)                     # nothing bound: nothing is written
    github.bind(_repo(1))
    github._only_factory_repo(1)
    with pytest.raises(github.FactoryRefused):
        github._only_factory_repo(2)                     # another listed repository is still refused
    with pytest.raises(github.FactoryRefused):
        github.push(repository_id=2, branch="factory/x", patch=b"x", patch_sha256="", base_sha="a" * 40,
                    expected_head=None, base_branch="dev")
    github._TARGET.set(None)


def test_old_saved_repositories_still_load_and_use_their_default_branch():
    old = {"connection": "github", "repository_id": 1, "full_name": "a/api", "default_branch": "main",
           "clone_url": "x", "local_path": None}
    assert github.Repo(**old).base == "main"
    assert _repo(1).base == "dev"
