import copy
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("policy", Path(__file__).parents[1] / "validate_pr_paths.py")
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)
REPO = "mhachem110/BankingReleasePlatform-AWS-EKS"


def pull_request(source="feature/app", target="dev", cloud=False, count=1):
    return {"head": {"ref": source, "sha": "a" * 40, "repo": {"full_name": REPO}},
            "base": {"ref": target, "sha": "b" * 40, "repo": {"full_name": REPO}},
            "user": {"id": 150286776 if cloud else 0}, "changed_files": count}


def file(path, status="modified", previous=None):
    result = {"filename": path, "status": status}
    if previous is not None:
        result["previous_filename"] = previous
    return result


class ScopeTests(unittest.TestCase):
    def test_application_paths(self):
        for path in ["apps/Account.Api/Program.cs", "tests/Payment.Api.Tests/Test.cs",
                     "apps/Payment.Api/Dockerfile", "compose.yaml", "README.md",
                     "scripts/test-local.ps1", "docs/application/run.md"]:
            with self.subTest(path=path):
                policy.validate(pull_request(), [file(path)], REPO)

    def test_app_cannot_change_cloud_or_unknown_files_even_when_owner_authored(self):
        paths = ["infra/bootstrap/main.tf", "helm/payment/values.yaml",
                 ".github/workflows/terraform-operations.yml", ".github/CODEOWNERS",
                 "scripts/bootstrap/write-backend-config.py", "scripts/governance/validate_pr_paths.py",
                 "docs/governance/README.md", "iam/bootstrap/trust.json", ".gitignore",
                 "AGENTS.md", "unknown/new-script.ps1", "apps/Account.Api/main.tf",
                 "tests/CODEOWNERS", "apps/Account.Api/config.tf.json"]
        for path in paths:
            with self.subTest(path=path), self.assertRaises(policy.PolicyError):
                policy.validate(pull_request(cloud=True), [file(path)], REPO)

    def test_rename_out_of_workflow_directory_is_rejected(self):
        with self.assertRaises(policy.PolicyError):
            policy.validate(pull_request(), [file("apps/readme.txt", "renamed", ".github/workflows/deploy.yml")], REPO)

    def test_rename_into_infrastructure_is_rejected(self):
        with self.assertRaises(policy.PolicyError):
            policy.validate(pull_request(), [file("infra/example.tf", "renamed", "apps/readme.txt")], REPO)

    def test_deleting_cloud_file_through_app_branch_is_rejected(self):
        with self.assertRaises(policy.PolicyError):
            policy.validate(pull_request(), [file(".github/CODEOWNERS", "removed")], REPO)

    def test_bootstrap_scope(self):
        for path in ["infra/bootstrap/main.tf", "infra/modules/state-bucket/main.tf",
                     "infra/backend/dev.s3.tfbackend.example", "scripts/bootstrap/helper.py",
                     "docs/phase2/IAM.md", ".github/workflows/terraform-validation.yml",
                     "infra/environments/dev/main.tf"]:
            with self.subTest(path=path):
                policy.validate(pull_request("bootstrap", cloud=True), [file(path)], REPO)

    def test_bootstrap_cannot_change_application_or_eks_or_policy(self):
        for path in ["apps/Account.Api/Program.cs", "infra/modules/eks/main.tf",
                     "infra/environments/dev/network/main.tf", ".github/CODEOWNERS",
                     ".github/workflows/branch-governance.yml"]:
            with self.subTest(path=path), self.assertRaises(policy.PolicyError):
                policy.validate(pull_request("bootstrap", cloud=True), [file(path)], REPO)

    def test_cloud_author_required_for_bootstrap_infra_and_promotions(self):
        for source, target in [("bootstrap", "dev"), ("infra", "dev"), ("dev", "stage"),
                               ("stage", "uat"), ("uat", "main")]:
            with self.subTest(source=source), self.assertRaises(policy.PolicyError):
                policy.validate(pull_request(source, target), [file("infra/bootstrap/main.tf")], REPO)

    def test_cloud_can_make_cross_cutting_infra_change(self):
        files = [file("infra/modules/eks/main.tf"), file("apps/Account.Api/Program.cs")]
        policy.validate(pull_request("infra", cloud=True, count=2), files, REPO)

    def test_app_only_infra_pr_is_rejected(self):
        with self.assertRaises(policy.PolicyError):
            policy.validate(pull_request("infra", cloud=True), [file("apps/Account.Api/Program.cs")], REPO)

    def test_cloud_promotions_can_contain_all_reviewed_workstreams(self):
        for source, target in [("dev", "stage"), ("stage", "uat"), ("uat", "main")]:
            with self.subTest(target=target):
                policy.validate(pull_request(source, target, cloud=True), [file("apps/Account.Api/Program.cs")], REPO)

    def test_legacy_branch_and_skipped_promotion_are_rejected(self):
        for source, target in [("feature/phase1-banking-apis", "dev"), ("dev", "main"),
                               ("feature/app/extra", "dev")]:
            with self.subTest(source=source), self.assertRaises(policy.PolicyError):
                policy.validate(pull_request(source, target, cloud=True), [file("README.md")], REPO)

    def test_forked_source_is_rejected(self):
        pr = pull_request()
        pr["head"]["repo"]["full_name"] = "test-fixture/fork"
        with self.assertRaises(policy.PolicyError):
            policy.validate(pr, [file("README.md")], REPO)

    def test_state_keys_generated_inputs_and_binaries_are_rejected(self):
        paths = ["infra/bootstrap/terraform.tfstate.backup", "infra/x.tfplan", "infra/x.tfvars",
                 "infra/x.tfbackend", "infra/private.key", "apps/Account.Api/bin/a.dll",
                 "infra/.terraform/provider.exe", "infra/.env", "infra/backend_override.tf"]
        for path in paths:
            with self.subTest(path=path), self.assertRaises(policy.PolicyError):
                policy.validate(pull_request("infra", cloud=True), [file(path)], REPO)

    def test_noncanonical_and_control_character_paths_are_rejected(self):
        for path in ["../infra/x.tf", "/apps/x.cs", "apps//x.cs", "apps/./x.cs", "apps\\x.cs", "apps/x\n::error::bad"]:
            with self.subTest(path=path), self.assertRaises(policy.PolicyError):
                policy.validate(pull_request(), [file(path)], REPO)

    def test_rename_missing_original_path_is_rejected(self):
        with self.assertRaises(policy.PolicyError):
            policy.validate(pull_request(), [file("apps/x.cs", "renamed")], REPO)

    def test_truncated_list_is_rejected(self):
        with self.assertRaises(policy.PolicyError):
            policy.validate(pull_request(count=2), [file("README.md")], REPO)


class CollectionTests(unittest.TestCase):
    def test_paginated_list_is_complete(self):
        pr = pull_request(count=101)
        pages = [pr, [file(f"apps/file{i}.cs") for i in range(100)], [file("apps/last.cs")], pr]
        calls = []
        def getter(repo, suffix):
            calls.append(suffix)
            return pages.pop(0)
        result, files = policy.collect(REPO, 9, "a" * 40, getter)
        self.assertEqual(len(files), 101)
        self.assertIn("page=2", calls[2])
        policy.validate(result, files, REPO)

    def test_missing_page_fails_closed(self):
        pr = pull_request(count=101)
        pages = [pr, [file(f"apps/file{i}.cs") for i in range(100)], [], pr]
        with self.assertRaises(policy.PolicyError):
            policy.collect(REPO, 9, "a" * 40, lambda *_: pages.pop(0))

    def test_head_moved_before_read_is_rejected(self):
        with self.assertRaises(policy.PolicyError):
            policy.collect(REPO, 9, "c" * 40, lambda *_: pull_request())

    def test_pr_changes_during_read_are_rejected(self):
        before = pull_request()
        after = copy.deepcopy(before)
        after["base"]["sha"] = "c" * 40
        pages = [before, [file("README.md")], after]
        with self.assertRaises(policy.PolicyError):
            policy.collect(REPO, 9, "a" * 40, lambda *_: pages.pop(0))

    def test_github_file_limit_is_not_silently_truncated(self):
        with self.assertRaises(policy.PolicyError):
            policy.collect(REPO, 9, "a" * 40, lambda *_: pull_request(count=3001))

    def test_bad_pr_number_is_rejected_before_network(self):
        with self.assertRaises(policy.PolicyError):
            policy.collect(REPO, "../../other", "a" * 40, lambda *_: self.fail("Unexpected request"))


if __name__ == "__main__":
    unittest.main()
