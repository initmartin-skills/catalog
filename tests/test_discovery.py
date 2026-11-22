import base64
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


scan = module("discover_skills")
build = module("build_catalog")
HEAD, TREE, BLOB = "a" * 40, "b" * 40, "c" * 40
CONFIG = {"schema_version": 1, "owners": [{"login": "example", "type": "org"}],
          "exclude_repositories": [], "max_blob_bytes": 262144, "max_tree_entries": 1000}
LISTED = {"id": 42, "full_name": "example/toolbox", "name": "toolbox", "fork": True,
          "private": False, "default_branch": "main", "pushed_at": "one", "updated_at": "one"}


class Fake:
    def __init__(self, files=None, listed=None):
        self.listed = [copy.deepcopy(LISTED)] if listed is None else listed
        self.files = files or ["SKILL.md", "skills/second/SKILL.md"]
        self.calls = []
        self.fail = False
        self.truncated = False

    def pages(self, path):
        if self.fail == "listing":
            raise scan.ScanError("listing failed")
        return iter(self.listed)

    def get(self, path):
        self.calls.append(path)
        if self.fail:
            raise scan.ScanError("request failed")
        if path == "/repos/example/toolbox":
            return dict(LISTED, parent={"full_name": "author/toolbox"}, license={"spdx_id": "MIT"},
                        description="A collection", topics=["tools"])
        if "/git/ref/" in path:
            return {"object": {"sha": HEAD}}
        if "/git/commits/" in path:
            return {"tree": {"sha": TREE}}
        if "/git/trees/" in path:
            if self.truncated and "?recursive" in path:
                return {"truncated": True, "tree": []}
            if self.truncated and path.endswith(TREE):
                return {"tree": [{"path": "nested", "type": "tree", "mode": "040000", "sha": "d" * 40}]}
            paths = ["SKILL.md"] if self.truncated else self.files
            return {"truncated": False, "tree": [
                {"path": p, "type": "blob", "mode": "100644", "sha": BLOB, "size": 99} for p in paths]}
        if "/git/blobs/" in path:
            return {"encoding": "base64", "content": base64.b64encode(
                b"---\nname: example-skill\ndescription: >-\n  Useful for UI\n  design tasks.\n---\nNever execute this document.").decode()}
        raise AssertionError(path)


class DiscoveryBehavior(unittest.TestCase):
    def discover(self, api, previous=None, refresh=False):
        return scan.discover(api, CONFIG, previous, "2026-11-22", refresh)

    def test_nested_and_root_skills_import_as_saved(self):
        snapshot, report = self.discover(Fake())
        skills = snapshot["repositories"]["42"]["skills"]
        self.assertEqual({s["path"] for s in skills}, {".", "skills/second"})
        self.assertEqual(len({s["id"] for s in skills}), 2)
        self.assertTrue(all(s["status"] == "saved" and s["category"] == "inbox" for s in skills))
        self.assertEqual(skills[0]["summary"], "Useful for UI design tasks.")
        self.assertEqual(report["skills_found"], 2)

    def test_private_and_nonfork_repositories_are_never_read(self):
        api = Fake(listed=[dict(LISTED, private=True), dict(LISTED, fork=False)])
        snapshot, _ = self.discover(api)
        self.assertEqual(snapshot["repositories"], {})
        self.assertEqual(api.calls, [])

    def test_unchanged_repo_uses_cache(self):
        snapshot, _ = self.discover(Fake())
        api = Fake()
        second, report = self.discover(api, snapshot)
        self.assertEqual(api.calls, [])
        self.assertEqual(snapshot, second)
        self.assertEqual(report["cached"], 1)

    def test_force_refresh_rescans_but_reuses_unchanged_blobs(self):
        snapshot, _ = self.discover(Fake())
        api = Fake()
        self.discover(api, snapshot, refresh=True)
        self.assertTrue(any("/git/trees/" in p for p in api.calls))
        self.assertFalse(any("/git/blobs/" in p for p in api.calls))

    def test_repository_failure_retains_last_good_skills(self):
        snapshot, _ = self.discover(Fake())
        api = Fake()
        api.fail = True
        second, report = self.discover(api, snapshot, refresh=True)
        self.assertEqual(second["repositories"]["42"]["skills"], snapshot["repositories"]["42"]["skills"])
        self.assertEqual(len(report["errors"]), 1)
        self.assertTrue(second["repositories"]["42"]["error"])

    def test_listing_failure_does_not_mean_deletion(self):
        api = Fake()
        api.fail = "listing"
        with self.assertRaises(scan.ScanError):
            self.discover(api, {"repositories": {"42": {"skills": ["keep me"]}}})

    def test_partial_blob_failure_keeps_progress_and_retries_only_failed_blob(self):
        api = Fake()
        original = api.get
        attempts = []
        def get(path):
            if "/git/blobs/" in path:
                attempts.append(path)
                if len(attempts) == 2:
                    raise scan.ScanError("temporary rate limit")
            return original(path)
        api.get = get
        snapshot, report = self.discover(api)
        skills = snapshot["repositories"]["42"]["skills"]
        self.assertEqual(len(skills), 2)
        self.assertIsNone(skills[0]["metadata_error"])
        self.assertTrue(skills[1]["metadata_error"])
        self.assertEqual(len(report["errors"]), 1)
        retry = Fake()
        recovered, report = self.discover(retry, snapshot)
        self.assertEqual(sum("/git/blobs/" in p for p in retry.calls), 1)
        self.assertFalse(recovered["repositories"]["42"]["error"])
        self.assertTrue(all(not s["metadata_error"] for s in recovered["repositories"]["42"]["skills"]))
        self.assertEqual(report["errors"], [])

    def test_removed_public_fork_keeps_historical_record(self):
        snapshot, _ = self.discover(Fake())
        second, report = self.discover(Fake(listed=[]), snapshot)
        self.assertFalse(second["repositories"]["42"]["available"])
        self.assertEqual(len(second["repositories"]["42"]["skills"]), 2)
        self.assertEqual(report["unavailable"], 1)

    def test_explicit_exclusion_removes_auto_records(self):
        snapshot, _ = self.discover(Fake())
        config = dict(CONFIG, exclude_repositories=["example/toolbox"])
        second, _ = scan.discover(Fake(), config, snapshot, "2026-11-22")
        self.assertEqual(second["repositories"], {})

    def test_truncated_tree_is_walked(self):
        api = Fake()
        api.truncated = True
        snapshot, _ = self.discover(api)
        self.assertEqual(snapshot["repositories"]["42"]["skills"][0]["path"], "nested")

    def test_pagination_reads_more_than_one_hundred_repositories(self):
        api = scan.GitHub()
        requests = []
        def get(path):
            requests.append(path)
            return [LISTED] * (100 if path.endswith("&page=1") else 1)
        api.get = get
        self.assertEqual(len(list(api.pages("/orgs/example/repos?type=public"))), 101)
        self.assertEqual(len(requests), 2)

    def test_symlinks_and_nonstandard_paths_are_not_followed(self):
        api = Fake()
        original = api.get
        def get(path):
            if "/git/trees/" in path:
                return {"tree": [
                    {"path": "SKILL.md", "type": "blob", "mode": "120000", "sha": BLOB},
                    {"path": "../SKILL.md", "type": "blob", "mode": "100644", "sha": BLOB},
                    {"path": "NOTSKILL.md", "type": "blob", "mode": "100644", "sha": BLOB}
                ]}
            return original(path)
        api.get = get
        snapshot, _ = self.discover(api)
        self.assertEqual(snapshot["repositories"]["42"]["skills"], [])
        self.assertFalse(any("/git/blobs/" in p for p in api.calls))

    def test_metadata_is_text_not_executable_yaml(self):
        self.assertEqual(scan.metadata("---\nname: !!python/object/apply:os.system bad\n---")["name"], "")
        self.assertEqual(scan.metadata("---\nname: 'quoted name'\ndescription: \"text: more\"\n---"),
                         {"name": "quoted name", "description": "text: more"})

    def test_manual_approval_summary_and_adopted_commit_win(self):
        snapshot, _ = self.discover(Fake())
        auto = snapshot["repositories"]["42"]["skills"][0]
        manual = dict(auto, id="my-curated-skill", summary="我填写的用途", category="design",
                      status="approved", reviewed_at="2026-11-22", used_in=["A real task"],
                      commit="e" * 40, fork="example/old-name")
        curated = {"schema_version": 1, "title": "Test", "categories": ["design"],
                   "skills": [manual], "packs": {"daily": ["my-curated-skill"]}}
        untouched = copy.deepcopy(curated)
        merged = build.validate(build.merge_catalog(curated, snapshot))
        self.assertEqual(curated, untouched)
        self.assertEqual(len(merged["skills"]), 2)
        result = next(s for s in merged["skills"] if s["id"] == "my-curated-skill")
        self.assertEqual(result["summary"], "我填写的用途")
        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["commit"], "e" * 40)
        self.assertEqual(result["latest_commit"], HEAD)
        self.assertEqual(result["fork"], "example/toolbox")
        self.assertIn("来源已有更新", build.source_note(result))

    def test_missing_or_failed_source_disables_install_command(self):
        snapshot, _ = self.discover(Fake())
        manual = dict(snapshot["repositories"]["42"]["skills"][0], status="approved",
                      reviewed_at="2026-11-22", used_in=["Test"])
        curated = {"schema_version": 1, "title": "Test", "categories": ["inbox"],
                   "skills": [manual], "packs": {}}
        snapshot["repositories"]["42"]["skills"] = []
        merged = build.merge_catalog(curated, snapshot)
        self.assertEqual(merged["skills"][0]["source_status"], "missing-skill")
        self.assertIsNone(build.command(merged["skills"][0]))

    def test_imported_markup_is_escaped_in_site(self):
        snapshot, _ = self.discover(Fake())
        snapshot["repositories"]["42"]["skills"][0]["summary"] = "<script>alert(1)</script>"
        curated = {"schema_version": 1, "title": "Test", "categories": ["inbox"], "skills": [], "packs": {}}
        merged = build.validate(build.merge_catalog(curated, snapshot))
        page = build.webpage(merged)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)


if __name__ == "__main__":
    unittest.main()
