import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("catalog_builder",ROOT/"scripts/build_catalog.py")
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

class CatalogContract(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((ROOT/"catalog.json").read_text(encoding="utf-8"))

    def approved(self):
        s=self.data["skills"][0]
        s.update(status="approved",reviewed_at="2026-11-22",used_in=["isolated UI design trial"])
        return s

    def test_current_snapshot_is_saved_not_installed(self):
        builder.validate(self.data)
        self.assertIsNone(builder.command(self.data["skills"][0]))
        self.assertNotIn("<pre><code>npx",builder.webpage(self.data))

    def test_duplicate_id_rejected(self):
        self.data["skills"].append(copy.deepcopy(self.data["skills"][0]))
        with self.assertRaises(ValueError): builder.validate(self.data)

    def test_branch_name_does_not_replace_commit(self):
        self.data["skills"][0]["commit"]="main"
        with self.assertRaises(ValueError): builder.validate(self.data)

    def test_approval_requires_real_review(self):
        self.data["skills"][0]["status"]="approved"
        with self.assertRaises(ValueError): builder.validate(self.data)

    def test_approval_requires_usage_evidence(self):
        self.data["skills"][0].update(status="approved",reviewed_at="2026-11-22")
        with self.assertRaises(ValueError): builder.validate(self.data)

    def test_saved_skill_cannot_enter_pack(self):
        self.data["packs"]["design"]=[self.data["skills"][0]["id"]]
        with self.assertRaises(ValueError): builder.validate(self.data)

    def test_approved_pack_pins_commit(self):
        s=self.approved()
        self.data["packs"]["design"]=[s["id"]]
        builder.validate(self.data)
        self.assertIn(s["fork"]+"@"+s["commit"],builder.command(s))
        self.assertIn("--skill oil-ui",builder.command(s))

    def test_invalid_paths_rejected(self):
        for path in ("../skill","/private/skill","a//b","a\\b","a?b","a#b"):
            with self.subTest(path=path):
                self.data["skills"][0]["path"]=path
                with self.assertRaises(ValueError): builder.validate(self.data)

    def test_untrusted_repo_url_rejected(self):
        self.data["skills"][0]["fork"]="https://evil.invalid/path"
        with self.assertRaises(ValueError): builder.validate(self.data)

    def test_html_content_is_escaped(self):
        payload='<img src=x onerror=alert(1)>'
        self.data["skills"][0]["summary"]=payload
        page=builder.webpage(builder.validate(self.data))
        self.assertNotIn(payload,page)
        self.assertIn("&lt;img",page)

    def test_invalid_date_rejected(self):
        self.data["skills"][0]["reviewed_at"]="2026-02-31"
        with self.assertRaises(ValueError): builder.validate(self.data)

    def test_root_path_resolves_skill_file(self):
        url=builder.file_url(self.data["skills"][0])
        self.assertTrue(url.endswith("/SKILL.md"))
        self.assertNotIn("/./",url)

    def test_empty_catalog_still_renders(self):
        self.data["skills"]=[]
        builder.validate(self.data)
        self.assertIn("尚未收录",builder.markdown(self.data))
        self.assertIn("没有匹配项",builder.webpage(self.data))

    def test_generated_files_are_deterministic(self):
        self.assertEqual(builder.markdown(self.data),builder.markdown(copy.deepcopy(self.data)))
        self.assertEqual(builder.webpage(self.data),builder.webpage(copy.deepcopy(self.data)))

if __name__=="__main__":
    unittest.main()

